"""Toolkit-only native maintenance. Never executes caller-supplied drawing code."""
import argparse,asyncio,json,os,time,queue,threading
from pathlib import Path
from autocad_channel import local_channel,identity,lease,read,failed
from common import sha256
from autocad_session import guarded_backend
import window_scan


def notifier(frame):
    sender=guarded_backend(object,None)();sender._toolkit_frame=frame;sender._hwnd=frame['hwnd']
    u,_=window_scan.api();sender._command_hwnd=u.FindWindowExW(frame['hwnd'],None,'MDIClient',None)
    def post(request):
        sender._post_text('(c:mcp-recover)')
    return sender,post


async def upgrade_loaded_bridge(root,channel):
    # One-time protocol upgrade for this local installation: the old native
    # recovery barrier stays in place throughout loading. Only the exact owned,
    # installed, hash-verified bundle can be loaded, never an arbitrary path.
    with lease(channel.ipc):
        frame,context,error=channel.target();record=read(channel.recovery)
        if error:return failed(error)
        if context.get('guard_protocol')==4:return dict(ok=True)
        if context.get('guard_protocol')!=3 or not record or record.get('frame')!=identity(frame) or record.get('document',{}).get('id')!=context['document']['id']:
            return failed('BRIDGE_UPDATE_REQUIRED')
        target=Path(read(Path(root)/'state.json')['active']['autocad']).resolve()
        if not target.is_relative_to((Path(root)/'versions').resolve()):return failed('BRIDGE_UPDATE_REQUIRED')
        receipt=read(target/'autocad-plugin.json',{})
        bundle=Path(os.environ['APPDATA'])/'Autodesk/ApplicationPlugins/McpToolkit.bundle/Contents/mcp_dispatch.lsp'
        source=target/'autocad/mcp_dispatch.lsp'
        if not bundle.is_file() or sha256(bundle)!=receipt.get('dispatcher_sha256') or sha256(source)!=sha256(bundle):
            return failed('BRIDGE_UPDATE_REQUIRED')
        sender,_=notifier(frame)
        # This fixed installation maintenance action is not exposed as an MCP
        # code executor and never clears/acknowledges the recovery barrier.
        done=queue.Queue()
        def load_owned():
            try:sender._post_text('(load "'+bundle.as_posix()+'" nil)');done.put(None)
            except Exception as exc:done.put(exc)
        threading.Thread(target=load_owned,daemon=True).start()
        deadline=time.monotonic()+8
        while done.empty() and time.monotonic()<deadline:await asyncio.sleep(.05)
        if done.empty() or done.get() is not None:return failed('BRIDGE_UPDATE_REQUIRED')
        settle=time.monotonic()+2
        while True:
            current,new_context,error=channel.target()
            if (not error and (new_context or {}).get('guard_protocol')==4) or time.monotonic()>=settle:break
            await asyncio.sleep(.05)
        if error or identity(current)!=identity(frame) or new_context.get('guard_protocol')!=4 or new_context['document']['id']!=context['document']['id']:
            return failed('BRIDGE_UPDATE_REQUIRED')
        return dict(ok=True)


async def prepare(root,request_id,target_token):
    channel=local_channel(root)
    state=channel.state()
    if not state.get('recovery') or state['recovery']['request_id']!=request_id or state.get('target_token')!=target_token:
        return failed('RECOVERY_TARGET_CHANGED')
    upgrade=await upgrade_loaded_bridge(root,channel)
    if not upgrade.get('ok'):return upgrade
    frame,context,error=channel.target()
    if error:return failed(error)
    _,post=notifier(frame)
    # The upgrade may add a switch serial; require the current verified token.
    return await channel.prepare_recovery(request_id,channel._token(frame,context),post)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--request-id',required=True);parser.add_argument('--target-token',required=True)
    args=parser.parse_args()
    try:value=asyncio.run(prepare(Path(args.root),args.request_id,args.target_token))
    except Exception as exc:value=dict(ok=False,error='恢復檢查未完成：'+str(exc))
    print(json.dumps(value,ensure_ascii=True))
