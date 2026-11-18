import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from common import atomic_json,sha256
from manager import Manager
import runtime


class ComponentRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Toolkit 單項修復 ')
        self.base=Path(self.temp.name);self.root=self.base/'installed'
        self.environment=patch.dict(os.environ,{'CODEX_HOME':str(self.base/'private-codex')});self.environment.start()
        self.manager=Manager(self.root)
        self.old=self.root/'versions/all-three';self.payload=self.base/'payload'
        atomic_json(self.payload/'bundle.json',{'version':'0.5.0-beta.1','files':{},'components':{}})
        self.new=self.root/('versions/0.5.0-beta.1-rhino-'+sha256(self.payload/'bundle.json')[:12])
        for target,selected in [(self.old,['autocad','inventor','rhino']),(self.new,['rhino'])]:
            atomic_json(target/'ready.json',{'version':'0.5.0-beta.1','selected':selected})
            for component in selected:
                python=target/'envs'/component/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_text('fixture')
        self.manager.state.update(active={},candidate={'path':str(self.old),'selected':['autocad','inventor','rhino'],'version':'0.5.0-beta.1'},auto_enable_pending=['autocad','inventor'])
        self.manager.save()
    def tearDown(self):self.environment.stop();self.temp.cleanup()
    def repair(self):self.manager.install(self.payload,['rhino'],defer_plugin=True)
    def test_repair_keeps_pending_components_on_their_own_installed_environments(self):
        self.repair()
        found=runtime.discover(self.root,self.base/'private-codex/config.toml')
        for component in ['autocad','inventor']:
            self.assertIn(component,found)
            self.assertEqual(found[component]['target'],str(self.old))
            self.assertTrue(Path(found[component]['python']).is_file())
        self.assertEqual(found['rhino']['target'],str(self.new))
    def test_repair_keeps_all_three_servers_in_generated_plugin(self):
        self.repair();captured={}
        def capture(destination,template,commands,*args,**kwargs):captured.update(commands)
        with patch('manager.plugin_files',side_effect=capture),patch('manager.find_codex',return_value='fixture-codex'),patch('manager.run',return_value=''):
            self.manager.configure_plugin()
        self.assertEqual(set(captured),{'rhino','autocad','inventor'})

    def test_each_of_the_three_components_can_be_repaired_independently(self):
        for component in ['rhino','autocad','inventor']:
            with self.subTest(component=component):
                before=runtime.discover(self.root,self.base/'private-codex/config.toml')
                target=self.root/('versions/0.5.0-beta.1-'+component+'-'+sha256(self.payload/'bundle.json')[:12])
                atomic_json(target/'ready.json',{'version':'0.5.0-beta.1','selected':[component]})
                python=target/'envs'/component/'Scripts/python.exe';python.parent.mkdir(parents=True,exist_ok=True);python.write_text('fixture')
                if component=='autocad':
                    lisp=target/'payload/cad/autocad/mcp_dispatch.lsp';lisp.parent.mkdir(parents=True);lisp.write_text('(setq *mcp-ipc-dir* "C:/temp/")')
                self.manager.install(self.payload,[component],defer_plugin=True)
                after=runtime.discover(self.root,self.base/'private-codex/config.toml')
                self.assertEqual(set(after),set(before))
                for other in set(before)-{component}:self.assertEqual(after[other]['target'],before[other]['target'])

    def test_legacy_overwritten_inventory_is_recovered_without_enabling_it(self):
        self.manager.state['candidate']={'path':str(self.new),'selected':['rhino']}
        self.manager.state['auto_enable_pending']=[];self.manager.save()
        found=runtime.discover(self.root,self.base/'missing.toml')
        self.assertEqual(set(found),{'autocad','inventor','rhino'})
        self.assertTrue(all(not source['enabled'] for source in found.values()))

    def test_pending_component_can_activate_after_another_component_was_repaired(self):
        self.repair()
        with patch.object(self.manager,'diagnose',return_value={'autocad':{'bridge':True,'code':'NOT_ENABLED'}}),patch.object(self.manager,'register_plugin'):
            self.manager.activate(['autocad'])
        self.assertEqual(self.manager.state['active']['autocad'],str(self.old))

    def test_repair_does_not_reenable_an_unrelated_disabled_component(self):
        self.manager.state['active']={'autocad':str(self.old),'inventor':str(self.old)}
        doc=self.manager.config.load();doc['plugins']={'cad-toolkit@cad-toolkit-local':{'mcp_servers':{'autocad':{'enabled':False},'inventor':{'enabled':True}}}};self.manager.config.save(doc)
        self.repair()
        with patch.object(self.manager,'register_plugin') as register:self.manager.configure_plugin()
        self.assertEqual(register.call_args.args[2],{'inventor'})
        with patch.object(self.manager,'diagnose',return_value={'rhino':{'bridge':True,'code':'NOT_ENABLED'}}),patch.object(self.manager,'register_plugin') as register:self.manager.activate(['rhino'])
        self.assertEqual(register.call_args.args[2],{'inventor','rhino'})

    def test_mid_install_failure_registers_only_completed_components(self):
        root=self.base/'partial';manager=Manager(root);payload=self.base/'partial-payload'
        atomic_json(payload/'bundle.json',{'version':'0.5.0-beta.1','files':{},'components':{c:{'wheel':c+'.whl'} for c in ['inventor','rhino']}})
        for c in ['inventor','rhino']:
            wheel=payload/'wheels'/c/(c+'.whl');wheel.parent.mkdir(parents=True);wheel.write_bytes(b'fixture')
        def run(args,**kwargs):
            if str(args[0])=='fixture-codex':return ''
            if args[1]=='venv':
                target=Path(args[-1]);
                if target.name=='rhino':raise RuntimeError('fixture Rhino install failure')
                python=target/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_text('fixture')
            return ''
        class Client:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def initialize(self):return {}
            def request(self,*args):return {'tools':[{'name':'system'}]}
        captured={}
        def plugin(destination,template,commands,*args,**kwargs):captured.update(commands)
        with patch('manager.run',side_effect=run),patch('manager.Client',Client),patch('manager.find_codex',return_value='fixture-codex'),patch('manager.plugin_files',side_effect=plugin):
            with self.assertRaisesRegex(RuntimeError,'fixture Rhino'):manager.setup(payload,['inventor','rhino'])
        self.assertEqual(set(captured),{'inventor'})
        self.assertEqual(manager.state['auto_enable_pending'],['inventor'])
        found=runtime.discover(root,self.base/'private-codex/config.toml')
        self.assertIn('inventor',found);self.assertTrue(Path(found['inventor']['python']).is_file());self.assertNotIn('rhino',found)
        self.assertFalse((Path(found['inventor']['target'])/'ready.json').exists())
