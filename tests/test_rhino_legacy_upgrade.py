import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from common import atomic_json,sha256
from rhino_setup import install_plugin
from manager import Manager

class LegacyRhinoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Rhino 舊版重裝 ');self.base=Path(self.temp.name).resolve()
        self.env=patch.dict(os.environ,{'APPDATA':str(self.base/'roaming'),'LOCALAPPDATA':str(self.base/'local')});self.env.start()
        self.target=self.base/'toolkit/versions/new';self.package=self.target/'payload/cad/rhino/rhinomcp.yak';self.package.parent.mkdir(parents=True)
        with zipfile.ZipFile(self.package,'w') as archive:archive.writestr('net8.0/RhinoMCP.rhp',b'new verified plugin')
        atomic_json(self.target/'payload/bundle.json',{'components':{'rhino':{'plugin_file':self.package.name,'plugin_asset':{'version':'0.5.3'}}},'files':{'cad/rhino/'+self.package.name:sha256(self.package)}})
        self.installed=self.base/'roaming/McNeel/Rhinoceros/packages/8.0/rhinomcp/0.5.3'
        self.old=self.installed/'net8.0/RhinoMCP.rhp';self.old.parent.mkdir(parents=True);self.old.write_bytes(b'old same-version plugin')
        self.rhino=self.base/'Rhino 8/Rhino.exe';self.rhino.parent.mkdir();self.rhino.touch();self.rhino.with_name('Yak.exe').touch()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def install(self,args,**kwargs):
        if self.installed.exists():raise RuntimeError('Package already installed / old files conflict')
        with zipfile.ZipFile(self.package) as archive:archive.extractall(self.installed)
        return 'Successfully installed'
    def test_same_version_old_files_are_backed_up_before_yak_install(self):
        with patch('rhino_setup.rhino_running',return_value=False,create=True),patch('rhino_setup.run',side_effect=self.install):result=install_plugin(self.target,str(self.rhino))
        self.assertEqual(self.old.read_bytes(),b'new verified plugin')
        backup=Path(result['backup']);self.assertTrue(any(p.read_bytes()==b'old same-version plugin' for p in backup.rglob('*.rhp')))
    def test_failed_install_restores_original_plugin(self):
        def fail(args,**kwargs):
            self.assertFalse(self.installed.exists());self.old.parent.mkdir(parents=True);self.old.write_bytes(b'partial new files');raise RuntimeError('fixture Yak failure')
        with patch('rhino_setup.rhino_running',return_value=False,create=True),patch('rhino_setup.run',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'fixture Yak failure'):install_plugin(self.target,str(self.rhino))
        self.assertEqual(self.old.read_bytes(),b'old same-version plugin')
    def test_loaded_old_plugin_requires_close_before_any_change(self):
        with patch('rhino_setup.rhino_running',return_value=True,create=True),patch('rhino_setup.run') as run:
            with self.assertRaisesRegex(RuntimeError,'關閉 Rhino'):install_plugin(self.target,str(self.rhino))
        run.assert_not_called();self.assertEqual(self.old.read_bytes(),b'old same-version plugin')

    def test_incomplete_yak_success_is_rejected_and_restores_original(self):
        with patch('rhino_setup.rhino_running',return_value=False),patch('rhino_setup.run',return_value='Already installed'):
            with self.assertRaisesRegex(RuntimeError,'驗證'):install_plugin(self.target,str(self.rhino))
        self.assertEqual(self.old.read_bytes(),b'old same-version plugin')

    def test_older_versions_are_archived_but_other_plugins_stay_untouched(self):
        older=self.installed.parent/'0.5.2/net8.0/RhinoMCP.rhp';older.parent.mkdir(parents=True);older.write_bytes(b'older version')
        other=self.installed.parent.parent/'OtherPlugin/1.0/Other.rhp';other.parent.mkdir(parents=True);other.write_bytes(b'keep other plugin')
        with patch('rhino_setup.rhino_running',return_value=False),patch('rhino_setup.run',side_effect=self.install):result=install_plugin(self.target,str(self.rhino))
        self.assertFalse(older.exists());self.assertTrue(any(p.read_bytes()==b'older version' for p in Path(result['backup']).rglob('*.rhp')))
        self.assertEqual(other.read_bytes(),b'keep other plugin')

    def test_backup_failure_keeps_existing_native_files(self):
        with patch('rhino_setup.rhino_running',return_value=False),patch('pathlib.Path.rename',side_effect=PermissionError('locked')),patch('rhino_setup.run') as run:
            with self.assertRaisesRegex(RuntimeError,'原外掛已保留'):install_plugin(self.target,str(self.rhino))
        run.assert_not_called();self.assertEqual(self.old.read_bytes(),b'old same-version plugin')

    def test_already_installed_package_still_requests_restart_for_loaded_old_version(self):
        atomic_json(self.target/'ready.json',{'version':'test','selected':['rhino']})
        manager=Manager(self.base/'toolkit');manager.state['candidate']={'path':str(self.target),'selected':['rhino']}
        with patch('rhino_setup.install_plugin',return_value={'version':'0.5.3','already_installed':True}),patch('manager.processes',return_value=[{'pid':123}]),patch('rhino_instances.collect',return_value=[{'version':'0.5.2','guard_protocol':1}]):manager.configure_rhino()
        self.assertTrue(__import__('json').loads((self.target/'rhino-plugin.json').read_text())['restart_required'])
