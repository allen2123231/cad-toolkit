"""Retire only GUI executables inside verified, owned RhinoMCP package folders."""
import csv,ctypes,os,subprocess
from pathlib import Path


def owned_tray_paths(base,versions):
    base=Path(base).resolve();paths=set()
    for version in versions:
        version=Path(version).resolve()
        if version.parent!=base:raise ValueError('Tray cleanup target is outside the RhinoMCP package directory')
        for exe in version.rglob('RhinoMCPTray.exe'):
            if exe.is_symlink() or not exe.resolve().is_relative_to(version):raise ValueError('Tray executable redirects outside its package')
            paths.add(os.path.normcase(str(exe.resolve())))
    return paths


def tray_pids():
    result=subprocess.run(['tasklist.exe','/FI','IMAGENAME eq RhinoMCPTray.exe','/FO','CSV','/NH'],
                          capture_output=True,text=True,encoding='utf8',errors='replace',timeout=8,creationflags=0x08000000)
    if result.returncode:raise RuntimeError('無法確認舊 RhinoMCP 系統匣程式。')
    return [int(row[1]) for row in csv.reader(result.stdout.splitlines()) if len(row)>1 and row[0].casefold()=='rhinomcptray.exe']


def stop_owned(pid,paths):
    from ctypes import wintypes as W
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)];k.QueryFullProcessImageNameW.restype=W.BOOL
    k.TerminateProcess.argtypes=[W.HANDLE,W.UINT];k.TerminateProcess.restype=W.BOOL
    k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];k.WaitForSingleObject.restype=W.DWORD
    k.CloseHandle.argtypes=[W.HANDLE]
    handle=k.OpenProcess(0x101001,False,pid)
    if not handle:return False
    try:
        if k.WaitForSingleObject(handle,0)==0:return False
        name=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(name))
        if not k.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):return False
        if os.path.normcase(str(Path(name.value).resolve())) not in paths:return False
        # The held kernel handle identifies the exact GUI process, even if its
        # PID is recycled. No CAD process or arbitrary same-name exe is stopped.
        if not k.TerminateProcess(handle,0):raise ctypes.WinError(ctypes.get_last_error())
        if k.WaitForSingleObject(handle,3000)!=0:raise RuntimeError('舊 RhinoMCP 系統匣程式尚未結束。')
        return True
    finally:k.CloseHandle(handle)


def retire(base,versions):
    paths=owned_tray_paths(base,versions)
    if not paths:return []
    return [pid for pid in tray_pids() if stop_owned(pid,paths)]
