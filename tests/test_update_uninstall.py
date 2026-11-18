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
    def test_uninstall_refuses_any_open_cad_before_changes(self):
        state=copy.deepcopy(self.manager.state)
        with patch('manager.processes',return_value=[{'pid':12}]):
            with self.assertRaises(RuntimeError):self.manager.uninstall()
        self.assertEqual(self.manager.state,state)

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
