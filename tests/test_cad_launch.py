from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import cad_launch


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='MCP 啟動 ');self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_first_start_explicitly_shows_interactive_cad_and_does_not_spawn_twice(self):
        state={'state':'stopped','pids':[],'windows':[]}
        with patch('cad_launch.application_state',return_value=state),patch('cad_launch.executable',return_value=Path('C:/CAD/Rhino.exe')),patch('cad_launch.subprocess.Popen',return_value=Mock(pid=123)) as spawn:
            first=cad_launch.ensure_started(self.root,'rhino');second=cad_launch.ensure_started(self.root,'rhino')
        self.assertEqual(first['state'],'starting');self.assertEqual(second['state'],'starting')
        self.assertEqual(spawn.call_count,1)
        self.assertEqual(spawn.call_args.kwargs['startupinfo'].wShowWindow,1)
        self.assertNotIn('creationflags',spawn.call_args.kwargs)
    def test_hidden_main_frame_is_restored_without_another_process(self):
        frame={'hwnd':100,'pid':10}
        with patch('cad_launch.application_state',return_value={'state':'hidden','windows':[frame],'pids':[10]}),patch('window_scan.locate') as show,patch('cad_launch.subprocess.Popen') as spawn:
            value=cad_launch.ensure_started(self.root,'autocad')
        show.assert_called_once_with(frame);spawn.assert_not_called();self.assertEqual(value['state'],'starting')
    def test_existing_startup_or_license_wait_never_creates_a_duplicate(self):
        for state in ('starting','needs_attention'):
            with self.subTest(state=state),patch('cad_launch.application_state',return_value={'state':state,'windows':[],'pids':[10]}),patch('cad_launch.subprocess.Popen') as spawn:
                self.assertEqual(cad_launch.ensure_started(self.root,'inventor')['state'],state);spawn.assert_not_called()
    def test_wait_observes_visible_frame_instead_of_process_only(self):
        with patch('cad_launch.application_state',side_effect=[{'state':'starting'},{'state':'window_open'}]),patch('cad_launch.time.sleep'):
            self.assertEqual(cad_launch.wait_for_application(self.root,'rhino',5)['state'],'window_open')
    def test_missing_application_is_reported_without_creating_a_process(self):
        with patch('cad_launch.application_state',return_value={'state':'stopped','windows':[],'pids':[]}),patch('cad_launch.executable',return_value=None),patch('cad_launch.subprocess.Popen') as spawn:
            value=cad_launch.ensure_started(self.root,'inventor')
        self.assertEqual(value['state'],'not_installed');spawn.assert_not_called()


if __name__=='__main__':unittest.main()
