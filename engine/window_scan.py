"""Enumerate native CAD frames without COM attachment or application activation."""
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import re

from rhino_instances import collect, process_start
from window_store import Store


def api():
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u.GetWindow.argtypes = [W.HWND, W.UINT]; u.GetWindow.restype = W.HWND
    u.IsWindow.argtypes = [W.HWND]; u.IsWindowVisible.argtypes = [W.HWND]
    u.IsIconic.argtypes = [W.HWND]
    u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    u.GetWindowTextLengthW.argtypes = [W.HWND]
    u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    u.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]; u.FindWindowExW.restype = W.HWND
    u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, ctypes.POINTER(ctypes.c_size_t)]
    u.ShowWindowAsync.argtypes = [W.HWND, ctypes.c_int]; u.SetForegroundWindow.argtypes = [W.HWND]
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; k.OpenProcess.restype = W.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    k.CloseHandle.argtypes = [W.HANDLE]
    return u, k


def text(u, hwnd):
    buffer = ctypes.create_unicode_buffer(u.GetWindowTextLengthW(hwnd)+1)
    u.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def main_frame(kind, cls):
    if kind in ("autocad", "inventor"):
        return cls.startswith("AfxMDIFrame")
    if kind == "rhino":
        parts = cls.split(":")
        return len(parts) > 2 and parts[0] == "Afx" and parts[2] == "8"
    return False


def scan(include_hidden=False):
    if os.name != "nt":
        return []
    u, k = api()
    result, cache = [], {}
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def visit(hwnd, _):
        if (not include_hidden and not u.IsWindowVisible(hwnd)) or u.GetWindow(hwnd, 4):
            return True
        title = text(u, hwnd)
        cls = ctypes.create_unicode_buffer(256); u.GetClassNameW(hwnd, cls, 256)
        if not title or cls.value in ("#32770", "tooltips_class32"):
            return True
        pid = W.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in cache:
            handle = k.OpenProcess(0x1000, False, pid.value)
            path = ctypes.create_unicode_buffer(32768); size = W.DWORD(len(path))
            try:
                found = handle and k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
                kind = {"rhino.exe": "rhino", "acad.exe": "autocad", "inventor.exe": "inventor"}.get(Path(path.value).name.lower()) if found else None
                cache[pid.value] = (kind, process_start(pid.value) if kind else None)
            finally:
                if handle: k.CloseHandle(handle)
        kind, start = cache[pid.value]
        # CAD frames have native Rhino/Afx classes. Exclude floating tool palettes,
        # splash windows and dialogs; document MDI children are never enumerated.
        if kind and start is not None and (kind == "rhino" or main_frame(kind, cls.value)):
            result.append({"kind": kind, "pid": pid.value, "processStart": start, "hwnd": int(hwnd), "title": title, "class": cls.value, "visible": bool(u.IsWindowVisible(hwnd))})
        return True

    callback = callback_type(visit)
    u.EnumWindows.argtypes = [callback_type, W.LPARAM]
    if not u.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    native = {v["pid"]: v for v in collect([i["pid"] for i in result if i["kind"] == "rhino"])}
    verified = []
    for item in result:
        value = native.get(item["pid"]) if item["kind"] == "rhino" else None
        if value and value.get("hwnd") and int(value["hwnd"]) != item["hwnd"]:
            continue
        if item["kind"] == "rhino" and not (value and value.get("hwnd")) and not main_frame("rhino", item["class"]):
            continue
        if value and (not value.get("hwnd") or int(value["hwnd"]) == item["hwnd"]):
            # Keep the OS creation time canonical; the native string was verified
            # by collect(), and cannot identify a subsequently recycled PID.
            item.update({k: v for k, v in value.items() if k not in ("processStart", "pid", "hwnd")})
        verified.append(item)
    return verified


def valid(window):
    u, _ = api()
    pid = W.DWORD(); u.GetWindowThreadProcessId(int(window["hwnd"]), ctypes.byref(pid))
    start = process_start(pid.value)
    return bool(u.IsWindow(int(window["hwnd"])) and pid.value == window["pid"] and start is not None and abs(start-float(window["processStart"])) < .001)


def locate(window):
    if not valid(window):
        raise ValueError("這個視窗已關閉，請重新選取。")
    u, _ = api()
    u.ShowWindowAsync(window["hwnd"], 9 if u.IsIconic(window["hwnd"]) else 5)
    u.SetForegroundWindow(window["hwnd"])


def title(u, hwnd):
    value = text(u, hwnd)
    mdi = u.FindWindowExW(hwnd, None, "MDIClient", None)
    if mdi:
        maximized = ctypes.c_int(); child = ctypes.c_size_t()
        if u.SendMessageTimeoutW(mdi, 0x229, 0, ctypes.addressof(maximized), 2, 150, ctypes.byref(child)) and maximized.value and child.value:
            suffix = " - [" + text(u, child.value) + "]"
            if value.endswith(suffix): value = value[:-len(suffix)]
    return value


def apply_names(root, windows, clear=False):
    u, _ = api()
    for w in windows:
        if not valid(w): continue
        if w["kind"] == "rhino" and w.get("guard_protocol") != 1:
            continue  # Old plug-ins own a different title prefix; never fight it.
        # The new Rhino plug-in owns its title on Idle. Other CAD frames are
        # updated only when needed, with a bounded message to an unresponsive app.
        if w["kind"] == "rhino" and w.get("guard_protocol") == 1:
            folder = Path(os.environ["LOCALAPPDATA"]) / "RhinoMCP/names"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (w["instance_id"]+".json")
            data = json.dumps({"name": w["display_name"], "enabled": not clear}, ensure_ascii=False)
            if not target.exists() or target.read_text(encoding="utf-8") != data:
                temp = target.with_suffix(".tmp"); temp.write_text(data, encoding="utf-8"); temp.replace(target)
            continue
        original = title(u, w["hwnd"])
        base = re.sub(r"^\[MCP Toolkit: [^\]\r\n]*\] ", "", original)
        value = base if clear else f'[MCP Toolkit: {w["display_name"]}] {base}'
        if value != original:
            buffer = ctypes.create_unicode_buffer(value); answer = ctypes.c_size_t()
            u.SendMessageTimeoutW(w["hwnd"], 0xC, 0, ctypes.addressof(buffer), 2, 150, ctypes.byref(answer))


def refresh(root, names=False):
    store = Store(root)
    windows = store.sync(scan())
    for w in windows:
        if w.get("binding") and w.get("guard_protocol") == 1:
            store.observe(w["binding"]["id"], {k: w.get(k) for k in ("document_serial", "document_epoch", "document", "documentPath")})
    if names: apply_names(root, windows)
    panel=store.panel()
    if panel["requests"] and not any(w["kind"]=="rhino" for w in panel["windows"]):
        from cad_launch import application_state
        panel["application"]=application_state(root,"rhino")
    return panel
