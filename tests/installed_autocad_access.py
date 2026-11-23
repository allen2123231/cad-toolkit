"""Opt-in: verify installed stdio route in a newly launched, disposable drawing.

Refuses existing CAD processes. Leaves a saved test DWG open for review.
No external COM or direct mailbox commands are used for drawing inspection.
"""
import json
import os
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'engine'))
from probe import Client

root=Path(os.environ['LOCALAPPDATA'])/'McpToolkit'
spec=json.loads((root/'marketplace/plugins/cad-toolkit/.mcp.json').read_text())['mcpServers']['autocad']
output=REPO/'test-results/access-installed';output.mkdir(exist_ok=True)
checks=[]
def check(name,passed,**details):
    checks.append(dict(test=name,passed=bool(passed),**details))
    (output/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(checks[-1],ensure_ascii=False),flush=True)
    if not passed:raise AssertionError(name)

with Client([spec['command'],*spec['args']],env={**os.environ,**spec['env']},timeout=65) as client:
    client.initialize()
    app=client.call('get_application_state',{'wait_seconds':0})
    check('no user CAD process will be used',not app.get('pids'))
    state=client.call('get_recovery_state')
    check('no unknown user modification will be acknowledged',state.get('recovery') is None)
    launch=client.call('open_application')
    check('installed tool starts CAD',launch.get('state')=='starting' and bool(launch.get('pid')),pid=launch.get('pid'))
    deadline=time.monotonic()+60
    while True:
        app=client.call('get_application_state',{'wait_seconds':5})
        if app.get('state')=='window_open' or time.monotonic()>=deadline:break
        time.sleep(.5)
    check('visible owned window opens',app.get('state')=='window_open' and len(app.get('windows',[]))==1 and app['windows'][0]['pid']==launch['pid'],state=app)
    deadline=time.monotonic()+40
    while True:
        state=client.call('get_recovery_state')
        if state.get('read_available'):break
        if time.monotonic()>=deadline:raise RuntimeError('Native read bridge did not become ready')
        time.sleep(.5)
    info=client.call('drawing',{'operation':'info'})
    check('installed native read works',info.get('ok'),result=info)
    count=client.call('entity',{'operation':'count'})['payload']['count']
    result=client.call('entity',{'operation':'create_circle','data':{'cx':25,'cy':25,'radius':10},'include_screenshot':False})
    after=client.call('entity',{'operation':'count'})['payload']['count']
    check('installed mutation executes once',result.get('ok') and after==count+1,before=count,after=after)
    path=output/'installed-access-test.dwg'
    result=client.call('drawing',{'operation':'save','data':{'path':path.as_posix()}})
    check('test DWG saved',result.get('ok') and path.exists(),path=str(path))
    variables=client.call('drawing',{'operation':'get_variables','data':{'names':['DWGNAME','DBMOD','CMDACTIVE']}})
    check('readback after save is clean',variables.get('payload',{}).get('DBMOD')==0,result=variables)
    state=client.call('get_recovery_state')
    check('read and write availability reported separately',state.get('read_available') and state.get('write_available') and state.get('recovery') is None,state=state)
