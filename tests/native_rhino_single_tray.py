"""Opt-in acceptance: new empty Rhino windows, real bound MCP calls, no user files.

The first window uses the production launch tool. A second, explicitly owned
visible process is a test fixture for multi-window isolation, not a routing bypass.
The test selects only its own attested windows through the same Store.bind API
as the Toolkit picker. It leaves the first empty window available for review.
"""
import json,os,signal,subprocess,sys,time
from pathlib import Path

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'engine'))
from probe import Client
from manager import mcp_command,mcp_env
from window_store import Store
import window_scan

root=Path(os.environ['LOCALAPPDATA'])/'McpToolkit';output=REPO/'test-results/rhino-single-tray-native';output.mkdir(exist_ok=True)
state=json.loads((root/'state.json').read_text());target=Path(state['prepared']['rhino'])
command=[str(target/'envs/rhino/Scripts/python.exe'),'-X','utf8',str(root/'marketplace/plugins/cad-toolkit/tools/relay.py'),'--root',str(root),'--component','rhino','--',*mcp_command(target,'rhino')]
checks=[];store=Store(root)
def check(label,condition,**details):
    checks.append(dict(test=label,passed=bool(condition),**details));print(json.dumps(checks[-1],ensure_ascii=False),flush=True)
    (output/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
    if not condition:raise AssertionError(label)
def processes(name):
    raw=subprocess.check_output(['powershell.exe','-NoProfile','-Command',"Get-CimInstance Win32_Process -Filter \"Name = '"+name+"'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"],text=True,encoding='utf8',creationflags=0x08000000).strip()
    if not raw:return []
    rows=json.loads(raw);return rows if isinstance(rows,list) else [rows]
def wait_window(pid):
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        frames=[w for w in window_scan.scan() if w['kind']=='rhino' and w['pid']==pid and w.get('guard_protocol')==1]
        if len(frames)==1:return frames[0]
        time.sleep(.5)
    raise TimeoutError('New Rhino did not automatically load its MCP plugin')
def bind(client,request,pid):
    frame=wait_window(pid);window_scan.refresh(root)
    window=next(w for w in store.windows() if w['kind']=='rhino' and w['pid']==pid)
    check('native plugin automatically starts in managed mode',frame.get('toolkit_managed') is True and frame.get('version','').split('+')[0]=='0.5.4',pid=pid,port=frame['port'])
    check('test window has no existing file',not frame.get('documentPath'),pid=pid)
    store.bind(request['request_id'],window['window_id'])
    result=client.call('get_window_binding',{'request_id':request['request_id'],'wait_seconds':0})
    check('picker API binds exact owned window',result['state']=='bound' and result['window_id']==window['window_id'],window_name=result['window_name'])
    return result['binding_id'],frame

check('no existing user Rhino is used',not processes('Rhino.exe'))
second=None;bindings=[];objects=[]
with Client(command,env=mcp_env(root),timeout=60) as client:
    client.initialize()
    first=client.call('request_window_binding',{'label':'系統匣測試 A'})
    launch=json.loads((root/'application-launches/rhino.json').read_text());first_pid=launch['pid']
    a,frame_a=bind(client,first,first_pid);bindings.append(a)
    info=client.call('get_document_summary',{'binding_id':a})
    check('first test document is empty',info['object_count']==0)
    capabilities=client.call('describe_capabilities',{'binding_id':a})
    check('native window guard remains available',capabilities.get('toolkit_guard_protocol')==1)
    check('no additional RhinoMCP tray after automatic connection',not processes('RhinoMCPTray.exe'))
    # A fresh visible fixture process is necessary to test two real windows.
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=1
    second=subprocess.Popen([frame_a['executable'],'/nosplash'],startupinfo=startup,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    wait_window(second.pid)
    other=client.call('request_window_binding',{'label':'系統匣測試 B'})
    b,frame_b=bind(client,other,second.pid);bindings.append(b)
    check('two windows keep independent identities and bindings',a!=b and frame_a['instance_id']!=frame_b['instance_id'] and frame_a['hwnd']!=frame_b['hwnd'])
    check('second test document is empty',client.call('get_document_summary',{'binding_id':b})['object_count']==0)
    for handle,name,x in [(a,'toolkit-tray-test-A',11),(b,'toolkit-tray-test-B',-11)]:
        created=client.call('create_object',{'binding_id':handle,'type':'POINT','name':name,'params':{'x':x,'y':0,'z':0}})
        objects.append((handle,created['id']))
    check('commands stay in their own windows',client.call('get_document_summary',{'binding_id':a})['object_count']==1 and client.call('get_document_summary',{'binding_id':b})['object_count']==1)
    for handle,object_id in objects:
        result=client.call('get_object_info',{'binding_id':handle,'id':object_id});check('created object reads back through its binding',result['id']==object_id)
    third=client.call('request_window_binding',{'label':'系統匣占用測試'})
    occupied=False
    try:store.bind(third['request_id'],store.binding(a)['window_id'])
    except ValueError:occupied=True
    store.cancel(third['request_id']);check('third connection cannot take an occupied window',occupied)
    for handle,object_id in objects:client.call('delete_object',{'binding_id':handle,'id':object_id})
    objects=[]
    check('only test objects were removed; both documents empty',all(client.call('get_document_summary',{'binding_id':h})['object_count']==0 for h in bindings))
    # The manager alone is stopped; Rhino and its bound MCP workers stay alive.
    owned_manager=[p for p in processes('McpToolkit.exe') if Path(p.get('ExecutablePath') or '').resolve()==(root/'McpToolkit.exe').resolve()]
    for p in owned_manager:os.kill(p['ProcessId'],signal.SIGTERM)
    time.sleep(.5)
    client.call('run_command',{'binding_id':a,'command':'_mcpwindow','echo':False})
    time.sleep(3)
    client.call('run_command',{'binding_id':a,'command':'_mcpwindow','echo':False})
    time.sleep(2)
    managers=[p for p in processes('McpToolkit.exe') if Path(p.get('ExecutablePath') or '').resolve()==(root/'McpToolkit.exe').resolve()]
    check('native status entry opens only one Toolkit manager',len(managers)==1)
    check('binding survives manager restart',client.call('get_document_summary',{'binding_id':a})['object_count']==0)
    check('multiple Rhino windows and manager restart never create a native tray',not processes('RhinoMCPTray.exe'))
    for handle in bindings:client.call('release_window_binding',{'binding_id':handle})
    bindings=[]
    # Terminate only the second fixture after verifying the original empty doc.
    current=wait_window(second.pid)
    if current['document_serial']==frame_b['document_serial'] and not current.get('documentPath'):
        second.terminate();second.wait(15)
    check('first Rhino remains open for review',any(w['pid']==first_pid for w in window_scan.scan()))
    check('final tray state contains no RhinoMCPTray process',not processes('RhinoMCPTray.exe'))
print('Native Rhino single-tray acceptance completed; first empty test window is unsaved.',flush=True)
