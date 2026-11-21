"""Opt-in destructive interruption test, confined to a newly owned CAD process.

Never targets existing CAD processes/documents. The harness filters enumeration
to its own PID so another person's open CAD can remain untouched. Production
continues to reject multiple target windows. This tests native LISP + WM_CHAR
on the installed product; running it on full AutoCAD is NOT LT certification.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'engine'))
from autocad_channel import Channel, atomic, local_channel
from autocad_context import read_context
from manager import Manager
import window_scan


async def run(args):
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    root=output/'root';target=output/'candidate'
    cad=target/'payload/cad/autocad';cad.mkdir(parents=True)
    import shutil
    shutil.copy2(REPO/'.build/payload/cad/autocad/mcp_dispatch.lsp',cad/'mcp_dispatch.lsp')
    manager=Manager.__new__(Manager);manager.root=root;manager.prepare_autocad(target)
    text=(target/'autocad/mcp_dispatch.lsp').read_text(encoding='utf-8')
    checkpoint=output/'partial-saved.txt'
    text=text.replace('    ;; --- Ping ---','''    ((= cmd-name "toolkit-test-interactive")
      (command "_.LINE")
      (cons T "true"))
    ((= cmd-name "toolkit-test-delay")
      (setq toolkit-until (+ (getvar "MILLISECS") 2500))
      (while (< (getvar "MILLISECS") toolkit-until))
      (cons T "true"))
    ((= cmd-name "toolkit-test-interrupt")
      (entmakex (list '(0 . "CIRCLE") '(10 0.0 0.0 0.0) '(40 . 15.0)))
      (command "_.QSAVE")
      (setq toolkit-fp (open "'''+checkpoint.as_posix()+'''" "w"))
      (write-line "partial geometry saved" toolkit-fp) (close toolkit-fp)
      (setq toolkit-until (+ (getvar "MILLISECS") 30000))
      (while (< (getvar "MILLISECS") toolkit-until))
      (cons T "true"))
    ;; --- Ping ---''',1)
    # The installed application's owned bundle is an implicitly trusted source.
    # No change to SECURELOAD, TRUSTEDPATHS or the production dispatcher.
    bundle=Path(os.environ['APPDATA'])/'Autodesk/ApplicationPlugins/McpToolkit.bundle/Contents'
    if not bundle.is_dir():raise RuntimeError('Install the Toolkit bundle before this opt-in test.')
    candidate=bundle/('toolkit-test-'+uuid.uuid4().hex+'.lsp')
    candidate.write_text(text,encoding='utf-8')
    script=output/'startup.scr'
    script.write_text('(load "'+candidate.as_posix()+'")\n(setvar "INSUNITS" 4)\n(princ)\n',encoding='ascii')
    owned=None;owned_frame=None;checks=[]
    existing=[{k:w[k] for k in ('pid','hwnd','processStart')} for w in window_scan.scan() if w['kind']=='autocad']
    def check(label,condition,**details):
        checks.append(dict(test=label,passed=bool(condition),**details));print(json.dumps(checks[-1]),flush=True)
        atomic(output/'report.json',dict(product='AutoCAD native integration (not LT)',checks=checks))
        if not condition:raise AssertionError(label+': '+str(details))
    def frames():return [w for w in window_scan.scan(include_hidden=True) if owned and w['kind']=='autocad' and w['pid']==owned.pid]
    base=local_channel(root)
    channel=Channel(root,frames,base.context,base.alive)
    def stop_owned():
        nonlocal owned
        if owned and owned.poll() is None:
            # Popen retains the handle of the process WE launched (no PID lookup,
            # no taskkill by executable name, no user documents in this process).
            owned.terminate();owned.wait(timeout=15)
    async def start(document=None):
        nonlocal owned,owned_frame
        argv=[args.exe,'/nologo']
        if document:argv.append(str(document))
        else:argv+=['/t',args.template]
        argv+=['/b',str(script)]
        info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=1
        owned=subprocess.Popen(argv,startupinfo=info,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            if owned.poll() is not None:raise RuntimeError('Owned CAD exited during startup')
            current=frames()
            if len(current)==1:
                try:
                    context=read_context(root,current[0])
                    if context.get('guard_protocol')==2 and not context['document']['busy']:
                        owned_frame=current[0]
                        await asyncio.sleep(2)
                        return
                except RuntimeError:pass
            await asyncio.sleep(1)
        raise TimeoutError('Owned CAD startup did not load the native candidate')
    def post(request):
        import ctypes
        from ctypes import wintypes as W
        current=frames()
        if len(current)!=1 or current[0]['hwnd']!=request['toolkit_hwnd']:raise RuntimeError('Owned frame changed')
        u,_=window_scan.api()
        child=u.FindWindowExW(request['toolkit_hwnd'],None,'MDIClient',None)
        if not child:raise RuntimeError('Owned MDIClient missing')
        u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.PostMessageW.restype=W.BOOL
        for char in '(c:mcp-dispatch)\r':
            if not u.PostMessageW(child,0x102,ord(char),0):raise ctypes.WinError(ctypes.get_last_error())
    async def call(command,params=None,timeout=10):
        result=await channel.dispatch(command,params or {},post,timeout)
        await asyncio.sleep(.3)
        return result
    try:
        await start()
        check('new owned CAD loaded guarded native bridge',(await call('ping'))['ok'],pid=owned.pid)
        count=await call('entity-count');check('empty test drawing',count.get('payload',{}).get('count')==0,result=count)
        saved=output/'recovery-test.dwg'
        result=await call('drawing-save',{'path':saved.as_posix()})
        check('baseline saved',result.get('ok') and saved.is_file(),result=result)
        def wrong_document(request):
            value=dict(request,toolkit_document='not-the-current-document')
            atomic(root/'ipc'/f"autocad_mcp_cmd_{request['request_id']}.json",value);post(request)
        result=await channel.dispatch('create-circle',{'cx':1,'cy':1,'radius':3},wrong_document,5)
        check('native rejects stale document before drawing',not result.get('ok') and 'TARGET_DOCUMENT_CHANGED' in str(result),result=result)
        active=asyncio.create_task(call('toolkit-test-delay'))
        await asyncio.sleep(.5)
        during=channel.state()
        result=await call('create-circle',{'cx':1,'cy':1,'radius':3})
        check('second operation rejected while native work runs',result.get('code')=='DESKTOP_BUSY_OTHER_CLIENT',result=result)
        check('reactor/native phase observable without mailbox',during.get('active',{}).get('native_phase')=='executing',state=during)
        check('busy operation completes',(await active)['ok'])
        active=asyncio.create_task(call('toolkit-test-interrupt',timeout=40))
        deadline=time.monotonic()+15
        while not checkpoint.exists() and time.monotonic()<deadline:await asyncio.sleep(.1)
        check('partial geometry checkpoint reached',checkpoint.exists())
        interrupted_at=time.monotonic()
        stop_owned()
        result=await active
        elapsed=time.monotonic()-interrupted_at
        check('CAD death interrupts promptly instead of waiting timeout',result.get('code')=='RECOVERY_REQUIRED' and elapsed<5,result=result,seconds=elapsed)
        state=channel.state();atomic(output/'closed-state.json',state)
        check('dead mailbox quarantined',not list((root/'ipc').glob('autocad_mcp_cmd_*.json')))
        result=await call('create-circle',{'cx':30,'cy':0,'radius':4})
        check('next batch received but not run',result.get('code')=='RECOVERY_REQUIRED')
        await start(saved)
        state=channel.state();atomic(output/'reopened-state.json',state)
        check('reopen requires explicit confirmation',state['can_confirm'] and state['recovery'] is not None,current_document=state['current_document'])
        # Harness stands in for the human's UI confirmation, after checking exact
        # path, new process identity, units, and non-busy state.
        check('reopened correct saved drawing',Path(state['current_document']['path'])==saved and state['current_document']['units']==4)
        channel.confirm(state['recovery']['request_id'],state['target_token'])
        count=await call('entity-count')
        check('partial circle present; old batch not replayed',count.get('payload',{}).get('count')==1,result=count)
        await asyncio.sleep(1)
        count=await call('entity-count');check('no delayed replay after confirmation',count.get('payload',{}).get('count')==1)
        result=await call('create-circle',{'cx':50,'cy':0,'radius':5})
        count=await call('entity-count')
        check('explicit new operation works once',result.get('ok') and count.get('payload',{}).get('count')==2,result=count)
        await call('drawing-save')
        result=await call('toolkit-test-delay',timeout=.2)
        check('live native timeout enters recovery',result.get('code')=='RECOVERY_REQUIRED')
        await asyncio.sleep(3)
        late=channel.state()
        check('late receipt does not silently release barrier',late['recovery']['completion_received'] and not late['can_confirm'])
        check('new batch after late receipt still blocked',(await call('create-circle',{'cx':80,'cy':0,'radius':5})).get('code')=='RECOVERY_REQUIRED')
        stop_owned();await start(saved)
        recovered=channel.state()
        check('second reopen offers explicit recovery',recovered['can_confirm'])
        channel.confirm(recovered['recovery']['request_id'],recovered['target_token'])
        count=await call('entity-count')
        check('timeout and blocked batches never replayed',count.get('payload',{}).get('count')==2,result=count)
        delayed=[]
        def delayed_notification(request):
            delayed.append(request)
            time.sleep(1)
            post(request)
        result=await channel.dispatch('create-circle',{'cx':90,'cy':0,'radius':5},delayed_notification,timeout=.2)
        check('notification delay enters recovery',result.get('code')=='RECOVERY_REQUIRED')
        await asyncio.sleep(1.5)
        reply=json.loads((root/'ipc'/f"autocad_mcp_result_{delayed[0]['request_id']}.json").read_text(encoding='utf-8-sig'))
        check('late notification cannot execute after recovery barrier',not reply['ok'] and reply['error']=='RECOVERY_BARRIER_NOT_EXECUTED',reply=reply)
        stop_owned();await start(saved)
        recovered=channel.state();channel.confirm(recovered['recovery']['request_id'],recovered['target_token'])
        count=await call('entity-count');check('late notification did not add geometry',count.get('payload',{}).get('count')==2,result=count)
        result=await call('toolkit-test-interactive')
        state=channel.state()
        check('unfinished native prompt enters recovery without implicit ESC',result.get('code')=='RECOVERY_REQUIRED' and state['recovery']['reason']=='native_waiting_for_input',result=result)
        check('commands after unfinished prompt are received and blocked',(await call('create-circle',{'cx':90,'cy':0,'radius':5})).get('code')=='RECOVERY_REQUIRED')
        check('user CAD frames retained',all(any(all(w.get(k)==v for k,v in old.items()) for w in window_scan.scan()) for old in existing))
        print('Native recovery checks passed. '+str(output/'report.json'),flush=True)
    finally:
        stop_owned();candidate.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',required=True);parser.add_argument('--template',required=True);parser.add_argument('--output',required=True)
    asyncio.run(run(parser.parse_args()))
