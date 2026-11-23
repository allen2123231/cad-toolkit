import json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from common import atomic_json,sha256
from rhino_setup import install_plugin,write_manager_locator
from rhino_tray import owned_tray_paths,retire

class TrayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'APPDATA':str(self.root/'roaming'),'LOCALAPPDATA':str(self.root/'local')});env.start();self.addCleanup(env.stop)
        self.base=self.root/'roaming/McNeel/Rhinoceros/packages/8.0/rhinomcp'
        self.old=self.base/'0.5.3';self.old.mkdir(parents=True)
        (self.old/'RhinoMCPTray.exe').write_bytes(b'owned GUI')
        self.target=self.root/'toolkit/versions/new';self.package=self.target/'payload/cad/rhino/managed.yak';self.package.parent.mkdir(parents=True)
        self.make_package()
    def make_package(self,extra=False):
        with zipfile.ZipFile(self.package,'w') as z:
            z.writestr('net8.0/RhinoMCP.rhp',b'new native plugin')
            z.writestr('net8.0/toolkit-integration.json',json.dumps(dict(schema=1,mode='mcp-toolkit')))
            if extra:z.writestr('net8.0/RhinoMCPTray.exe',b'forbidden')
        atomic_json(self.target/'payload/bundle.json',dict(components={'rhino':dict(plugin_file='managed.yak',plugin_asset=dict(version='0.5.4'))},files={'cad/rhino/managed.yak':sha256(self.package)}))
    def yak(self,*args,**kwargs):
        with zipfile.ZipFile(self.package) as z:z.extractall(self.base/'0.5.4')
        return 'Installed'
    def test_cleanup_only_passes_owned_executables_and_never_uses_process_names_to_stop(self):
        with patch('rhino_tray.tray_pids',return_value=[1,2]),patch('rhino_tray.stop_owned',side_effect=[True,False]) as stop:
            self.assertEqual(retire(self.base,[self.old]),[1])
        for call in stop.call_args_list:self.assertEqual(call.args[1],{os.path.normcase(str((self.old/'RhinoMCPTray.exe').resolve()))})
    def test_foreign_package_directory_is_rejected(self):
        with self.assertRaises(ValueError):owned_tray_paths(self.base,[self.root/'OtherPlugin'])
    def test_managed_package_retires_gui_and_installs_without_tray(self):
        yak=self.root/'Rhino/System/Yak.exe';yak.parent.mkdir(parents=True);yak.touch();rhino=yak.with_name('Rhino.exe');rhino.touch()
        with patch('rhino_setup.rhino_running',return_value=False),patch('rhino_tray.retire',return_value=[44]) as retired,patch('rhino_setup.run',side_effect=self.yak):
            result=install_plugin(self.target,str(rhino))
        self.assertTrue(result['toolkit_managed']);self.assertEqual(result['retired_trays'],[44]);retired.assert_called_once()
        self.assertFalse(list((self.base/'0.5.4').rglob('RhinoMCPTray.exe')))
    def test_running_rhino_does_not_retire_gui_or_replace_plugin(self):
        with patch('rhino_setup.rhino_running',return_value=True),patch('rhino_tray.retire') as retired:
            with self.assertRaises(RuntimeError):install_plugin(self.target)
        retired.assert_not_called();self.assertTrue(self.old.exists())
    def test_managed_archive_with_tray_is_rejected(self):
        self.make_package(extra=True)
        with self.assertRaises(ValueError):install_plugin(self.target)
    def test_locator_supports_custom_root_without_changing_immutable_plugin(self):
        custom=self.root/'Custom 中文 位置';write_manager_locator(custom)
        data=json.loads((self.root/'local/RhinoMCP/toolkit-manager.json').read_text())
        self.assertEqual(Path(data['root']),custom.resolve());self.assertEqual(data['schema'],1)

if __name__=='__main__':unittest.main()
