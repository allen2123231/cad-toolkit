"""Install the pinned Rhino package with Rhino's own per-user package manager."""
import os
import hashlib
from pathlib import Path
import zipfile
import subprocess
import csv
import datetime as dt
import uuid

from common import read_json, run, sha256, within


class RhinoInstallError(RuntimeError):
    error_code='RHINO_SETUP_FAILED'
    def __init__(self,message,details):
        super().__init__(message+'\n'+details);self.user_message=message


def rhino_running():
    result=subprocess.run(['tasklist.exe','/FI','IMAGENAME eq Rhino.exe','/FO','CSV','/NH'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8,creationflags=0x08000000)
    if result.returncode:raise RuntimeError('無法確認 Rhino 是否已關閉，請稍後重試。')
    return any(row and row[0].lower()=='rhino.exe' for row in csv.reader(result.stdout.splitlines()))


def verified_install(installed,expected):
    return bool(expected) and all(within(installed,name).is_file() and sha256(within(installed,name))==digest for name,digest in expected.items())


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
    if not version or Path(version).name!=version:raise ValueError('Rhino 外掛版本格式不正確。')
    base=Path(os.environ['APPDATA'])/'McNeel/Rhinoceros/packages/8.0/rhinomcp'
    if base.is_symlink() or base.is_junction():raise RuntimeError('RhinoMCP 安裝目錄是重新導向的資料夾，請先檢查套件位置。')
    installed=within(base,version)
    with zipfile.ZipFile(package) as archive:
        expected={f.filename:hashlib.sha256(archive.read(f)).hexdigest() for f in archive.infolist() if not f.is_dir()}
    if not expected:raise ValueError('Rhino 外掛安裝包是空的。')
    for name in expected:within(installed,name)
    if verified_install(installed,expected):
        return {'version':version,'method':'yak','already_installed':True,'output':'已安裝相同且通過驗證的完整套件。'}
    if rhino_running():raise RuntimeError('請先儲存工作並關閉 Rhino，再安裝或替換 RhinoMCP 外掛。')
    yak=find_yak(rhino_exe)
    backup=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'McpToolkitBackups'/('rhino-replace-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    old=[]
    if base.exists():
        for source in base.iterdir():
            if not source.is_dir():continue
            if source.is_symlink() or source.is_junction() or any(p.is_symlink() or p.is_junction() for p in source.rglob('*')):raise RuntimeError('舊 RhinoMCP 目錄含重新導向項目，已保留原外掛並停止替換。')
            old.append(source)
    # Keep the native-directory swap atomic even with redirected roaming profiles.
    if backup.resolve().anchor.lower()!=base.resolve().anchor.lower():backup=base.resolve().parent.parent.parent/'McpToolkitBackups'/backup.name
    moved=[];started=False
    try:
        for source in old:
            target=within(backup,'previous/'+source.name);target.parent.mkdir(parents=True,exist_ok=True)
            source=source.resolve();source.rename(target);moved.append((source,target))
        if rhino_running():raise RuntimeError('Rhino 已重新開啟，請先儲存並關閉 Rhino，再重試外掛安裝。')
        started=True
        output=run([yak,'install',package],timeout=120)
        if not verified_install(installed,expected):raise RuntimeError('Rhino 外掛安裝後驗證未通過；已停止使用不完整的新版並還原舊版。')
    except Exception as error:
        try:
            if started and installed.exists():
                failed=within(backup,'failed-new/'+version);failed.parent.mkdir(parents=True,exist_ok=True);installed.rename(failed)
            for source,target in reversed(moved):
                if target.exists():source.parent.mkdir(parents=True,exist_ok=True);target.rename(source)
        except OSError as restore_error:
            raise RhinoInstallError('RhinoMCP 原檔已備份，但檔案仍被占用，請先儲存並關閉 Rhino 後重試；備份位置在詳細資料。',f'{error}\nRestore: {restore_error}\nBackup: {backup}') from restore_error
        if isinstance(error,OSError) or str(error).startswith('指令失敗'):
            raise RhinoInstallError('RhinoMCP 安裝未完成，原外掛已保留。請儲存並關閉 Rhino 後重試；仍失敗時可展開詳細資料。',f'{error}\nBackup: {backup}') from error
        raise
    return {'version':version,'method':'yak','output':output.strip(),'backup':str(backup) if moved else None}
