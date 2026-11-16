import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from test_lifecycle import Fixture
from common import atomic_json, sha256
from manager import Manager
from rhino_setup import find_yak, install_plugin


class RhinoSetupTests(Fixture):
    def prepare(self):
        target = self.base / 'Toolkit/versions/test-rhino'
        package = target / 'payload/cad/rhino/rhinomcp-0.5.2-rh8_17-any.yak'
        package.parent.mkdir(parents=True)
        package.write_bytes(b'verified release package')
        relative = 'cad/rhino/' + package.name
        atomic_json(target / 'payload/bundle.json', {
            'components': {'rhino': {'plugin_file': package.name, 'plugin_asset': {'version': '0.5.2'}}},
            'files': {relative: sha256(package)},
        })
        atomic_json(target / 'ready.json', {'version': 'test'})
        rhino = self.base / 'Rhino 8/System/Rhino.exe'
        rhino.parent.mkdir(parents=True)
        rhino.touch()
        rhino.with_name('Yak.exe').touch()
        return target, package, rhino

    def test_uses_selected_rhino_and_keeps_paths_with_spaces_as_arguments(self):
        target, package, rhino = self.prepare()
        with patch('rhino_setup.run', return_value='Successfully installed rhinomcp (0.5.2)') as run:
            result = install_plugin(target, str(rhino))
        run.assert_called_once_with([rhino.with_name('Yak.exe'), 'install', package], timeout=120)
        self.assertEqual(result['version'], '0.5.2')

    def test_corrupt_package_is_rejected_before_execution(self):
        target, package, rhino = self.prepare()
        package.write_bytes(b'tampered')
        with patch('rhino_setup.run') as run:
            with self.assertRaises(ValueError): install_plugin(target, str(rhino))
        run.assert_not_called()

    def test_package_name_cannot_escape_the_bundle(self):
        target, _, rhino = self.prepare()
        manifest = target / 'payload/bundle.json'
        data = json.loads(manifest.read_text())
        data['components']['rhino']['plugin_file'] = '../../outside.yak'
        atomic_json(manifest, data)
        with patch('rhino_setup.run') as run:
            with self.assertRaises(RuntimeError): install_plugin(target, str(rhino))
        run.assert_not_called()

    def test_missing_rhino_has_an_actionable_error(self):
        with self.assertRaisesRegex(RuntimeError, '重新選擇 Rhino.exe'):
            find_yak(str(self.base / 'missing/Rhino.exe'))

    def test_configure_preserves_active_mapping_and_reports_restart(self):
        target, _, rhino = self.prepare()
        manager = Manager(self.base / 'Toolkit')
        manager.rhino_exe = str(rhino)
        manager.state.update(candidate={'path': str(target), 'selected': ['rhino']}, active={'inventor': 'existing'})
        with patch('rhino_setup.run', return_value='installed'), patch('manager.processes', return_value=[{'pid': 1}]), contextlib.redirect_stdout(io.StringIO()):
            manager.configure_rhino()
        result = json.loads((target / 'rhino-plugin.json').read_text(encoding='utf-8'))
        self.assertTrue(result['restart_required'])
        self.assertEqual(manager.state['active'], {'inventor': 'existing'})

    def test_failed_yak_does_not_record_success(self):
        target, _, rhino = self.prepare()
        manager = Manager(self.base / 'Toolkit')
        manager.rhino_exe = str(rhino)
        manager.state['candidate'] = {'path': str(target), 'selected': ['rhino']}
        with patch('rhino_setup.run', side_effect=RuntimeError('install failed')), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): manager.configure_rhino()
        self.assertFalse((target / 'rhino-plugin.json').exists())

    def test_unprepared_candidate_cannot_install_external_plugin(self):
        manager = Manager(self.base / 'Toolkit')
        with patch('rhino_setup.install_plugin') as install:
            with self.assertRaises(RuntimeError): manager.configure_rhino()
        install.assert_not_called()
