"""Opt-in Windows integration check: isolated Codex homes, real wheels and CLI.

Does not activate MCPs, register Windows shortcuts, or call CAD tools.
"""
import contextlib
import itertools
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
sys.path.insert(0,str(ROOT/'.build/payload/engine/vendor'))
import manager as lifecycle
from common import atomic_json, read_json, sha256
from experience import Cancelled

payload=ROOT/'.build/payload'
base=ROOT/'test-results/七種安裝 組合'
base.mkdir(parents=True,exist_ok=True)
real_config=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
before=sha256(real_config) if real_config.exists() else None
original_home=os.environ.get('CODEX_HOME')
results=[]
try:
    for n in range(1,4):
        for selected in itertools.combinations(lifecycle.COMPONENTS,n):
            folder=base/('-'.join(selected));folder.mkdir(exist_ok=True)
            os.environ['CODEX_HOME']=str(folder/'隔離 Codex')
            service=lifecycle.Manager(folder/'Toolkit')
            # Seed the previous schema as an upgrade fixture. It must remain compatible.
            service.state.setdefault('previous',None);service.save()
            log=folder/'install.log'
            with log.open('w',encoding='utf-8') as output,contextlib.redirect_stdout(output):
                if n==3:
                    emit=lifecycle.emit
                    marker=service.root/'cancel.request';service.cancel_file=marker
                    fired=[False]
                    def cancelling(message,**values):
                        emit(message,**values)
                        if values.get('step')=='install' and values.get('outcome')=='completed' and not fired[0]:
                            marker.write_text('stop');fired[0]=True
                    lifecycle.emit=cancelling
                    try:
                        try:service.install(payload,list(selected))
                        except Cancelled:pass
                        assert fired[0], 'Cancellation boundary was not exercised'
                    finally:lifecycle.emit=emit;marker.unlink(missing_ok=True)
                service.install(payload,list(selected))
                target=Path(service.state['candidate']['path'])
                first_markers={c:sha256(target/(c+'.complete.json')) for c in selected}
                service.install(payload,list(selected))
                assert all(sha256(target/(c+'.complete.json'))==value for c,value in first_markers.items()), 'Repeated installation rebuilt completed environment'
            assert service.state['active']=={}, 'Installation activated a CAD connection'
            config=service.config.load()
            policy=config['plugins']['cad-toolkit@cad-toolkit-local']['mcp_servers']
            assert not any(p['enabled'] for p in policy.values())
            assert read_json(target/'ready.json')['selected']==list(selected)
            results.append({'selected':selected,'passed':True,'repeated_install':True,'tools':{c:read_json(target/(c+'.complete.json'))['tools'] for c in selected}})
            print('PASS '+','.join(selected),flush=True)
finally:
    if original_home is None:os.environ.pop('CODEX_HOME',None)
    else:os.environ['CODEX_HOME']=original_home
    after=sha256(real_config) if real_config.exists() else None
    assert before==after,'User Codex config changed'
atomic_json(base/'report.json',{'passed':True,'results':results,'user_config_unchanged':True,'cad_calls':0,'cancel_resume':True})
print('Seven real isolated installations passed. No CAD calls or user configuration changes.')
