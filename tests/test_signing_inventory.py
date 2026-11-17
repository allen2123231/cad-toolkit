import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('signing_inventory',Path(__file__).resolve().parents[1]/'scripts/signing_inventory.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class SigningInventoryTests(unittest.TestCase):
    def test_nested_native_wheels_and_yak_are_inventoried_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);exe=root/'setup.exe';exe.write_bytes(b'MZ fixture')
            wheel=io.BytesIO()
            with zipfile.ZipFile(wheel,'w') as z:z.writestr('package/native.pyd',b'MZ native');z.writestr('readme.txt','not executable')
            package=root/'payload.zip'
            with zipfile.ZipFile(package,'w') as z:z.writestr('wheels/native.whl',wheel.getvalue());z.writestr('engine/setup.ps1','script');z.writestr('runtime/python.exe',exe.read_bytes())
            result=module.inventory(package,exe,root/'audit.json')
            self.assertEqual(len(result['files']),4)
            self.assertTrue(any(f['source'].endswith('native.whl!/package/native.pyd') for f in result['files']))
            self.assertEqual(len({f['sha256'] for f in result['files']}),3)
            self.assertTrue(all(Path(f['path']).is_file() for f in result['files']))
    def test_archive_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);exe=root/'setup.exe';exe.write_bytes(b'MZ')
            package=root/'payload.zip'
            with zipfile.ZipFile(package,'w') as z:z.writestr('../escape.exe',b'MZ')
            with self.assertRaises(ValueError):module.inventory(package,exe,root/'audit.json')
