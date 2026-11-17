"""Resolve a Rhino by PID and creation time, never by whichever port answers."""
import datetime as dt
import json
import os
from pathlib import Path


def process_start(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(ctypes.c_ulonglong)] * 4)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        values = [ctypes.c_ulonglong() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(v) for v in values]):
            return None
        return values[0].value / 10_000_000 - 11644473600
    finally:
        kernel.CloseHandle(handle)


def collect(pids):
    result = []
    folder = Path(os.environ.get("LOCALAPPDATA", "")) / "RhinoMCP/instances"
    for file in folder.glob("*.json"):
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
            if value.get("pid") not in pids or value.get("host") not in ("127.0.0.1", "localhost", "::1"):
                continue
            if not isinstance(value.get("port"), int) or not 1 <= value["port"] <= 65535:
                continue
            if value.get("guard_protocol") == 1:
                identity = value.get("instance_id", "")
                if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
                    continue
                if not all(isinstance(value.get(k), int) and value[k] >= 0 for k in ("hwnd", "document_serial", "document_epoch")):
                    continue
            created = dt.datetime.fromisoformat(value["processStart"].replace("Z", "+00:00")).timestamp()
            actual = process_start(value["pid"])
            if actual is None or abs(actual-created) > 1:
                continue
            result.append(value)
        except (OSError, ValueError, KeyError):
            continue
    return result
