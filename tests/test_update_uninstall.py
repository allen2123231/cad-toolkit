import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from manager import Manager
from common import atomic_json
from uninstall_cleanup import remove_rhino

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Toolkit update 中文 ')
        self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'CODEX_HOME':str(self.base/'codex')});self.env.start()
        self.manager=Manager(self.base/'installed')
        self.manager.root.mkdir()
        self.manager.state.update(active={'inventor':'old'},candidate={'path':'old','selected':['inventor']},auto_enable_pending=[])
        self.manager.save()
        doc=self.manager.config.load();doc['model']='user-model';doc['plugins']={'cad-toolkit@cad-toolkit-local':{'enabled':False,'mcp_servers':{'inventor':{'enabled':False}}},'other':{'enabled':True}};self.manager.config.save(doc)
        (self.manager.root/'ui-state.json').write_text('{"custom":"kept"}')
    def tearDown(self): self.env.stop();self.temp.cleanup()
    def prepare(self,*args,**kwargs): self.manager.state['candidate']={'path':'new','selected':['inventor']}
    def test_update_preserves_policy_and_settings(self):
        before=self.manager.config.load().unwrap()
        with patch('manager.processes',return_value=[]),patch.object(self.manager,'install',side_effect=self.prepare),patch.object(self.manager,'register_plugin'):
            self.manager.update('payload',['inventor'])
        self.assertEqual(self.manager.config.load().unwrap(),before)
        self.assertEqual(self.manager.state['active'],{'inventor':'new'})
        self.assertEqual(self.manager.state['previous'],{'inventor':'old'})
        self.assertEqual((self.manager.root/'ui-state.json').read_text(),'{"custom":"kept"}')
    def test_failure_rolls_back_active_state_and_policy(self):
        state=copy.deepcopy(self.manager.state);config=self.manager.config.load().unwrap()
        with patch('manager.processes',return_value=[]),patch.object(self.manager,'install',side_effect=self.prepare),patch.object(self.manager,'register_plugin',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):self.manager.update('payload',['inventor'])
        self.assertEqual(self.manager.state,state);self.assertEqual(self.manager.config.load().unwrap(),config)
    def test_update_rejects_changed_selection_and_open_cad(self):
        with self.assertRaises(RuntimeError):self.manager.update('payload',['rhino'])
        with patch('manager.processes',return_value=[{'pid':12}]):
            with self.assertRaises(RuntimeError):self.manager.update('payload',['inventor'])
            with self.assertRaises(RuntimeError):self.manager.update('payload',['inventor'],live_autocad=True)
    def test_uninstall_refuses_any_open_cad_before_changes(self):
        state=copy.deepcopy(self.manager.state)
        with patch('manager.processes',return_value=[{'pid':12}]):
            with self.assertRaises(RuntimeError):self.manager.uninstall()
        self.assertEqual(self.manager.state,state)

class ComponentRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'CODEX_HOME':str(self.base/'codex'),'LOCALAPPDATA':str(self.base),'APPDATA':str(self.base/'roaming')});self.env.start()
        self.manager=Manager(self.base/'installed');self.manager.root.mkdir()
        self.target=self.manager.root/'versions/shared';self.target.mkdir(parents=True)
        self.mapping={c:str(self.target) for c in ('rhino','autocad','inventor')}
        atomic_json(self.target/'ready.json',{'selected':list(self.mapping),'version':'fixture'})
        for c in self.mapping:
            python=self.target/'envs'/c/'Scripts/python.exe';python.parent.mkdir(parents=True);python.write_bytes(b'fixture')
        self.manager.state.update(active=dict(self.mapping),prepared=dict(self.mapping),previous=dict(self.mapping),candidate={'path':str(self.target),'selected':list(self.mapping)},auto_enable_pending=list(self.mapping))
        self.manager.config.set_policy(set(self.mapping),self.manager.state['originals']);self.manager.save()
        self.process=patch('manager.processes',return_value=[]);self.process.start()
        self.plugin=patch.object(self.manager,'register_plugin');self.register=self.plugin.start()
        self.rhino=patch('uninstall_cleanup.remove_rhino',return_value={'removed':[],'preserved':[]});self.remove_rhino=self.rhino.start()
        self.autocad=patch('autocad_setup.remove_bundle');self.remove_bundle=self.autocad.start()
    def tearDown(self):
        for mock in (self.autocad,self.rhino,self.plugin,self.process,self.env):mock.stop()
        self.temp.cleanup()
    def test_single_removal_preserves_others_and_excludes_cached_recovery(self):
        self.manager.remove_component(['rhino'])
        self.assertEqual(set(self.manager.prepared()),{'autocad','inventor'})
        for key in ('active','prepared','previous'):self.assertEqual(set(self.manager.state[key]),{'autocad','inventor'})
        self.assertNotIn('rhino',self.manager.state['candidate']['selected'])
        policy=self.manager.config.load()['plugins']['cad-toolkit@cad-toolkit-local']['mcp_servers']
        self.assertFalse(policy['rhino']['enabled']);self.assertTrue(policy['autocad']['enabled']);self.assertTrue(policy['inventor']['enabled'])
        self.remove_rhino.assert_called_once();self.remove_bundle.assert_not_called()
        self.assertTrue((self.target/'envs/inventor/Scripts/python.exe').exists())
        restarted=Manager(self.manager.root);self.assertNotIn('rhino',restarted.prepared())
        self.manager.record_prepared('rhino',self.target);self.assertIn('rhino',self.manager.prepared())
    def test_autocad_removal_handles_lt_and_only_removes_autocad(self):
        with patch('manager.processes',side_effect=lambda n:[{'pid':1}] if n=='acadlt.exe' else []):
            before=copy.deepcopy(self.manager.state)
            with self.assertRaises(RuntimeError):self.manager.remove_component(['autocad'])
            self.assertEqual(self.manager.state,before);self.register.assert_not_called()
        self.manager.remove_component(['autocad']);self.remove_bundle.assert_called();self.remove_rhino.assert_not_called()
        self.assertEqual(set(self.manager.prepared()),{'rhino','inventor'})
    def test_inventor_removal_does_not_touch_native_plugins_or_unrelated_preferences(self):
        doc=self.manager.config.load();doc['model']='keep';doc['plugins']['other']={'enabled':True};self.manager.config.save(doc)
        with patch('manager.processes',side_effect=lambda n:[{'pid':2}] if n=='Rhino.exe' else []):self.manager.remove_component(['inventor'])
        self.remove_bundle.assert_not_called();self.remove_rhino.assert_not_called()
        self.assertEqual(self.manager.config.load()['model'],'keep');self.assertTrue(self.manager.config.load()['plugins']['other']['enabled'])
    def test_failed_registration_remains_disabled_and_can_retry_cleanup(self):
        self.register.side_effect=RuntimeError('fixture')
        with self.assertRaises(RuntimeError):self.manager.remove_component(['rhino'])
        self.assertNotIn('rhino',Manager(self.manager.root).prepared())
        self.register.side_effect=None;self.manager.remove_component(['rhino']);self.remove_rhino.assert_called_once()
        self.assertNotIn('rhino',self.manager.state['component_removals'])
    def test_regenerated_plugin_contains_only_remaining_tools_and_skills(self):
        import shutil
        shutil.copytree(Path(__file__).resolve().parents[1]/'plugins/cad-toolkit',self.target/'payload/plugins/cad-toolkit')
        self.register.side_effect=lambda mapping,target,enabled:Manager.register_plugin(self.manager,mapping,target,enabled)
        with patch('manager.find_codex',return_value='fixture-codex'),patch('manager.run',return_value=''):
            self.manager.remove_component(['rhino'])
        plugin=self.manager.root/'marketplace/plugins/cad-toolkit'
        commands=json.loads((plugin/'.mcp.json').read_text())['mcpServers']
        self.assertEqual(set(commands),{'autocad','inventor'})
        self.assertFalse((plugin/'skills/rhino-modeling').exists())
        self.assertTrue((plugin/'skills/inventor-modeling').exists())

    def test_invalid_scope_rejected_before_changes(self):
        for selected in ([],['rhino','inventor'],['unknown']):
            with self.assertRaises(ValueError):self.manager.remove_component(selected)
        self.register.assert_not_called()


class NativeCleanupTests(unittest.TestCase):
    def test_old_receipt_does_not_hide_a_matching_new_same_version_package(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);targets=[]
            for name,content in [('old',b'old build'),('new',b'new build')]:
                target=base/name;folder=target/'payload/cad/rhino';folder.mkdir(parents=True);package=folder/'fixture.yak'
                with zipfile.ZipFile(package,'w') as z:z.writestr('RhinoMCP.rhp',content)
                atomic_json(target/'payload/bundle.json',{'components':{'rhino':{'plugin_asset':{'version':'0.5.3'},'plugin_file':package.name}},'files':{'cad/rhino/'+package.name:hashlib.sha256(package.read_bytes()).hexdigest()}})
                atomic_json(target/'rhino-plugin.json',{'version':'0.5.3'});targets.append(target)
            installed=base/'roaming/McNeel/Rhinoceros/packages/8.0/rhinomcp/0.5.3';installed.mkdir(parents=True);(installed/'RhinoMCP.rhp').write_bytes(b'new build')
            result=remove_rhino(targets,base/'backup',base/'roaming')
            self.assertEqual(len(result['removed']),1);self.assertEqual(result['preserved'],[])

    def test_only_verified_owned_plugin_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);target=base/'target';payload=target/'payload';folder=payload/'cad/rhino';folder.mkdir(parents=True)
            package=folder/'fixture.yak'
            with zipfile.ZipFile(package,'w') as z:z.writestr('RhinoMCP.rhp',b'owned plugin')
            atomic_json(payload/'bundle.json',{'components':{'rhino':{'plugin_asset':{'version':'0.5.3'},'plugin_file':package.name}},'files':{'cad/rhino/'+package.name:hashlib.sha256(package.read_bytes()).hexdigest()}})
            atomic_json(target/'rhino-plugin.json',{'version':'0.5.3'})
            installed=base/'roaming/McNeel/Rhinoceros/packages/8.0/rhinomcp/0.5.3';installed.mkdir(parents=True)
            rhp=installed/'RhinoMCP.rhp';rhp.write_bytes(b'changed by someone else')
            result=remove_rhino([target],base/'backup',base/'roaming');self.assertTrue(result['preserved']);self.assertTrue(rhp.exists())
            rhp.write_bytes(b'owned plugin');result=remove_rhino([target],base/'backup',base/'roaming')
            self.assertEqual(len(result['removed']),1);self.assertFalse(installed.exists());self.assertTrue((base/'backup/rhino/0.5.3/RhinoMCP.rhp').exists())
