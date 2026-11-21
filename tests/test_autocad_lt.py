import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import cad_launch
import runtime


class LTTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Toolkit LT 中文 ');self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def test_lt_2027_default_install_is_found(self):
        exe=self.root/'Autodesk/AutoCAD LT 2027/acadlt.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'not executable')
        with patch.dict(os.environ,{'ProgramW6432':str(self.root)}),patch('winreg.OpenKey',side_effect=FileNotFoundError()):
            self.assertEqual(cad_launch.executable(self.root,'autocad'),exe)

    def test_lt_running_process_is_not_missed(self):
        result=Mock(returncode=0,stdout='"acadlt.exe","1234","Console","1","10 K"\n')
        with patch('cad_launch.subprocess.run',return_value=result):self.assertEqual(cad_launch.processes('autocad'),[1234])

    def test_snapshot_counts_full_and_lt_for_ambiguity(self):
        result=Mock(returncode=0,stdout='"acad.exe","1234","Console","1","10 K"\n"acadlt.exe","5678","Console","1","10 K"\n')
        with patch('runtime.subprocess.run',return_value=result):self.assertEqual(runtime.running_processes()['autocad'],[1234,5678])

    def test_existing_lt_is_reused_without_launch(self):
        frame={'kind':'autocad','pid':1234,'hwnd':42,'visible':True}
        with patch('cad_launch.window_scan.scan',return_value=[frame]),patch('cad_launch.subprocess.run',return_value=Mock(returncode=0,stdout='"acadlt.exe","1234","Console","1","10 K"\n')),patch('window_scan.locate'),patch('cad_launch.subprocess.Popen') as spawn:
            self.assertEqual(cad_launch.ensure_started(self.root,'autocad')['state'],'window_open');spawn.assert_not_called()

    def context(self,**changes):
        import time
        frame={'kind':'autocad','pid':1234,'hwnd':42,'processStart':time.time()-60,'visible':True,'product':'AutoCAD LT'}
        value={'schema':1,'hwnd':42,'product':'acadlt','version':'26.0','document':{'name':'未命名.dwg','path':'','dirty':False,'busy':False,'units':4}}
        value.update(changes);path=self.root/'ipc/toolkit-context-42.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8');return frame,path

    def test_lt_readiness_uses_native_context_and_matching_bridge_without_external_com(self):
        frame,_=self.context();source={'python':sys.executable,'command':[sys.executable],'enabled':True}
        with patch('runtime.version',return_value='3.2.0'),patch('runtime.native',side_effect=AssertionError('LT must not use external COM')),patch('runtime.probe',return_value={'code':'READY','bridge_hwnd':42}):
            result=runtime.row('autocad',source,[1234],self.root,{}, {},frames=[frame])
        self.assertEqual(result['code'],'READY');self.assertEqual(result['product'],'AutoCAD LT');self.assertEqual(result['document']['name'],'未命名.dwg')

    def test_wrong_bridge_cannot_be_marked_ready(self):
        frame,_=self.context()
        with patch('runtime.version',return_value='3.2.0'),patch('runtime.probe',return_value={'code':'READY','bridge_hwnd':999}):
            result=runtime.row('autocad',{'python':sys.executable,'command':[],'enabled':True},[1234],self.root,{}, {},frames=[frame])
        self.assertEqual(result['code'],'TARGET_MISMATCH')

    def test_missing_native_context_remains_installed_and_never_calls_com(self):
        frame,path=self.context();path.unlink()
        with patch('runtime.version',return_value='3.2.0'),patch('runtime.native') as com,patch('runtime.probe') as probe:
            result=runtime.row('autocad',{'python':sys.executable,'enabled':True},[1234],self.root,{}, {},frames=[frame])
        self.assertTrue(result['installed']);self.assertEqual(result['code'],'BRIDGE_NOT_CONNECTED');com.assert_not_called();probe.assert_not_called()

    def test_reused_hwnd_with_old_context_is_rejected(self):
        from autocad_context import read_context
        frame,path=self.context();os.utime(path,(frame['processStart']-1,frame['processStart']-1))
        with self.assertRaises(RuntimeError):read_context(self.root,frame)

    def test_mismatched_native_context_is_rejected(self):
        from autocad_context import read_context
        frame,_=self.context(hwnd=999)
        with self.assertRaises(RuntimeError):read_context(self.root,frame)

    def test_busy_lt_does_not_receive_probe_commands(self):
        frame,path=self.context();value=json.loads(path.read_text());value['document']['busy']=True;path.write_text(json.dumps(value))
        with patch('runtime.version',return_value='3.2.0'),patch('runtime.probe') as probe:
            result=runtime.row('autocad',{'python':sys.executable,'enabled':True},[1234],self.root,{}, {},frames=[frame])
        self.assertEqual(result['code'],'BUSY');probe.assert_not_called()

    def test_saved_lt_selection_does_not_reuse_running_full_autocad(self):
        (self.root/'ui-state.json').write_text(json.dumps({'Paths':{'autocad':'D:/AutoCAD LT 2027/acadlt.exe'}}))
        state={'state':'window_open','pids':[1234],'windows':[{'pid':1234,'hwnd':42,'product':'AutoCAD'}]}
        with patch('cad_launch.application_state',return_value=state),patch('cad_launch.subprocess.Popen') as launch:
            result=cad_launch.ensure_started(self.root,'autocad')
        self.assertEqual(result['state'],'needs_attention');launch.assert_not_called()

    def test_file_ipc_window_selection_does_not_depend_on_english_document_title(self):
        from autocad_session import find_managed_window
        with patch('window_scan.scan',return_value=[{'kind':'autocad','hwnd':42,'visible':True,'title':'AutoCAD LT 2027 - 圖面1'}]):self.assertEqual(find_managed_window(),42)
        with patch('window_scan.scan',return_value=[{'kind':'autocad','hwnd':42},{'kind':'autocad','hwnd':99}]):self.assertIsNone(find_managed_window())

    def test_per_document_bundle_contains_passive_native_status_and_creates_ipc(self):
        from manager import Manager
        from autocad_setup import install_bundle
        target=self.root/'version';source=target/'payload/cad/autocad';source.mkdir(parents=True)
        (source/'mcp_dispatch.lsp').write_text('(setq *mcp-ipc-dir* "C:/temp/")',encoding='utf-8');(target/'ready.json').write_text('{"version":"0.5.0-beta.5"}')
        manager=Manager.__new__(Manager);manager.root=self.root;manager.prepare_autocad(target)
        prepared=(target/'autocad/mcp_dispatch.lsp').read_text(encoding='utf-8')
        self.assertIn('mcp-toolkit-context-write',prepared);self.assertIn(':vlr-documentBecameCurrent',prepared);self.assertTrue((self.root/'ipc').is_dir())
        self.assertIn('RECOVERY_BARRIER_NOT_EXECUTED',prepared)
        self.assertIn('TARGET_DOCUMENT_CHANGED_NOT_EXECUTED',prepared)
        self.assertIn('"waiting_input"',prepared)
        self.assertGreater(prepared.rfind('(defun c:mcp-dispatch'),prepared.find('(defun mcp-toolkit-context-write'))
        receipt=install_bundle(target,self.root/'appdata');bundle=Path(receipt['bundle'])
        self.assertEqual((bundle/'Contents/mcp_dispatch.lsp').read_text(encoding='utf-8'),prepared)
        self.assertIn('PerDocument="True"',(bundle/'PackageContents.xml').read_text())
        self.assertIn('ACADLT',(bundle/'PackageContents.xml').read_text())
        import xml.etree.ElementTree as ET
        package=ET.parse(bundle/'PackageContents.xml').getroot()
        self.assertIn('ACADLT',package.find('RuntimeRequirements').get('Platform'))
        self.assertEqual(package.get('AppVersion'),'0.5.0.5')

    def test_managed_command_uses_guarded_bootstrap(self):
        from manager import mcp_command
        bootstrap=self.root/'payload/engine/autocad_session.py';bootstrap.parent.mkdir(parents=True);bootstrap.write_text('')
        self.assertEqual(mcp_command(self.root,'autocad')[-1],str(bootstrap))

    def test_lt_readonly_status_never_attaches_external_com(self):
        from autocad_readonly import read
        frame,_=self.context()
        with patch('window_scan.scan',return_value=[frame]),patch.dict(sys.modules,{'pythoncom':None,'win32com.client':None}):
            value=read(self.root)
        self.assertEqual(value['cmdactive'],0);self.assertEqual(value['name'],'未命名.dwg')

    def test_native_lt_transport_does_not_import_external_com(self):
        from autocad_session import guarded_backend
        class Base:
            def _post_text(self,text):self.sent=text
        backend=guarded_backend(Base,lambda **kw:kw)();backend._toolkit_frame={'product':'AutoCAD LT','kind':'autocad','pid':123,'hwnd':42,'processStart':1};backend._hwnd=42;backend._command_hwnd=43
        api=Mock();api.IsChild.return_value=True;api.PostMessageW.return_value=True
        with patch.dict(sys.modules,{'pythoncom':None,'win32com.client':None}),patch('ctypes.WinDLL',return_value=api),patch('window_scan.scan',return_value=[backend._toolkit_frame]):backend._post_text('(c:mcp-dispatch)')
        self.assertEqual(api.PostMessageW.call_count,len('(c:mcp-dispatch)\r'))

    def test_restarted_window_is_blocked_before_any_ipc_operation(self):
        import asyncio,types
        from autocad_session import guarded_backend
        class Base:
            async def _dispatch(self,*args,**kwargs):raise AssertionError('must not dispatch')
        result=lambda **kw:types.SimpleNamespace(**kw)
        backend=guarded_backend(Base,result)();backend._toolkit_frame={'pid':123,'hwnd':42,'processStart':1};backend._hwnd=42
        class RaceChannel:
            async def dispatch(self,command,params,post,timeout):
                post({'toolkit_frame':{'pid':123,'hwnd':42,'processStart':1},'toolkit_hwnd':42})
        backend._toolkit_channel=RaceChannel()
        frame={'kind':'autocad','pid':123,'hwnd':42,'processStart':2,'visible':True}
        with patch('window_scan.scan',return_value=[frame]):value=asyncio.run(backend._dispatch('ping',{}))
        self.assertFalse(value.ok)

    def test_nondefault_lt_app_paths_registration_is_found(self):
        import winreg
        from unittest.mock import MagicMock
        exe=self.root/'另一個磁碟/AutoCAD LT 2027/acadlt.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'fixture')
        key=MagicMock();key.__enter__.return_value=key
        def open_key(hive,path,*args):
            if path.endswith('acadlt.exe'):return key
            raise FileNotFoundError()
        with patch('winreg.OpenKey',side_effect=open_key),patch('winreg.QueryValue',return_value='"'+str(exe)+'"'):
            self.assertEqual(cad_launch.executable(self.root,'autocad'),exe)

    def test_custom_lt_program_path_is_retained(self):
        exe=self.root/'自訂位置/acadlt.exe';exe.parent.mkdir();exe.write_bytes(b'fixture');(self.root/'ui-state.json').write_text(json.dumps({'Paths':{'autocad':str(exe)}}))
        with patch('winreg.OpenKey',side_effect=AssertionError('saved path should be used')):self.assertEqual(cad_launch.executable(self.root,'autocad'),exe)

if __name__=='__main__':unittest.main()
