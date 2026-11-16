"""Install the pinned Rhino package with Rhino's own per-user package manager."""
import os
import hashlib
from pathlib import Path
import zipfile

from common import read_json, run, sha256, within


def find_yak(rhino_exe=None):
    if rhino_exe:
        executable = Path(rhino_exe)
        candidate = executable.with_name("Yak.exe")
        if executable.name.lower() != "rhino.exe" or not executable.is_file() or not candidate.is_file():
            raise RuntimeError("指定的 Rhino 8 程式位置沒有 Yak.exe，請重新選擇 Rhino.exe。")
        return candidate

    candidates = []
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\Rhino.exe") as key:
                    executable = Path(winreg.QueryValue(key, None).strip('"'))
                    candidates.append(executable.with_name("Yak.exe"))
            except OSError:
                pass
    except ImportError:
        pass
    for name in ("PROGRAMFILES", "ProgramW6432"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "Rhino 8/System/Yak.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("找不到 Rhino 8 的套件管理工具。請先安裝 Rhino 8，或在「選擇軟體」指定 Rhino.exe。")


def install_plugin(target, rhino_exe=None):
    payload = Path(target) / "payload"
    manifest = read_json(payload / "bundle.json")
    spec = manifest["components"]["rhino"]
    name = spec.get("plugin_file", "")
    if not name or Path(name).name != name or not name.endswith(".yak"):
        raise RuntimeError("此安裝包未包含自動連線版 Rhino 外掛，請下載新版 Toolkit。")
    relative = "cad/rhino/" + name
    package = within(payload, relative)
    expected = manifest["files"].get(relative)
    if not expected or not package.is_file() or sha256(package) != expected:
        raise ValueError("Rhino 外掛安裝包 SHA-256 不符，請重新下載同一版本。")
    version = spec["plugin_asset"]["version"]
    installed = Path(os.environ.get('APPDATA', '')) / 'McNeel/Rhinoceros/packages/8.0/rhinomcp' / version
    if installed.is_dir():
        try:
            with zipfile.ZipFile(package) as archive:
                files = [f for f in archive.infolist() if not f.is_dir()]
                verified = bool(files) and all((installed / f.filename).is_file()
                                              and sha256(installed / f.filename) == hashlib.sha256(archive.read(f)).hexdigest()
                                              for f in files)
            if verified:
                return {'version': version, 'method': 'yak', 'already_installed': True, 'output': '已安裝相同且通過驗證的完整套件。'}
        except (OSError, zipfile.BadZipFile):
            pass
    output = run([find_yak(rhino_exe), "install", package], timeout=120)
    return {"version": spec["plugin_asset"]["version"], "method": "yak", "output": output.strip()}
