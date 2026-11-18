"""Remove verified Toolkit-owned native payloads; preserve foreign/modified files."""
import hashlib
import os
from pathlib import Path
import shutil
import zipfile
from common import read_json, sha256, within


def remove_rhino(targets, backup, appdata=None):
    base = Path(appdata or os.environ['APPDATA']) / 'McNeel/Rhinoceros/packages/8.0/rhinomcp'
    result = {'removed': [], 'preserved': []}
    seen = set();unmatched=[]
    for target in targets:
        payload = Path(target) / 'payload'
        receipt = Path(target) / 'rhino-plugin.json'
        if not receipt.is_file(): continue
        installed=None
        try:
            manifest = read_json(payload / 'bundle.json')
            spec = manifest['components']['rhino']
            version = spec['plugin_asset']['version']
            if read_json(receipt).get('version') != version: raise ValueError('Plugin ownership receipt mismatch')
            if not version or Path(version).name != version: raise ValueError('Invalid package version')
            raw = base / version
            if base.is_symlink() or base.is_junction() or raw.is_symlink() or raw.is_junction(): raise ValueError('Reparse point preserved')
            installed = within(base, version)
            if installed in seen or not installed.exists(): continue
            package = within(payload, 'cad/rhino/' + spec['plugin_file'])
            if sha256(package) != manifest['files']['cad/rhino/' + spec['plugin_file']]: raise ValueError('Package checksum mismatch')
            with zipfile.ZipFile(package) as archive:
                expected = {f.filename: hashlib.sha256(archive.read(f)).hexdigest() for f in archive.infolist() if not f.is_dir()}
            actual = {p.relative_to(installed).as_posix() for p in installed.rglob('*') if p.is_file()}
            if installed.is_symlink() or installed.is_junction() or any(p.is_symlink() or p.is_junction() for p in installed.rglob('*')):
                raise ValueError('Reparse point preserved')
            if actual != set(expected) or not all(within(installed, name).is_file() and sha256(within(installed, name)) == digest for name,digest in expected.items()):
                raise ValueError('Modified or foreign plugin files preserved')
            destination = within(backup, 'rhino/' + version)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(installed), str(destination))
            result['removed'].append(str(installed))
            seen.add(installed)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            unmatched.append((installed,str(exc)))
    result['preserved']=[message for path,message in unmatched if path is None or str(path) not in result['removed']]
    if base.exists() and not any(base.iterdir()): base.rmdir()
    return result
