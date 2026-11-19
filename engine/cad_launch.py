"""Visible CAD launch/recovery shared by the UI and all managed MCP services.

Readiness is a visible main frame, never merely a live process. No COM creation,
shell scripts, CAD commands or automatic duplicate instances are used here.
"""
import csv
import json
import os
from pathlib import Path
import subprocess
import time

import window_scan
from rhino_instances import process_start
from window_store import window_lock
from cad_products import EXECUTABLES,default_candidates

NAMES = {"rhino": "Rhino", "autocad": "AutoCAD", "inventor": "Inventor"}
EXES = {"rhino": "Rhino.exe", "autocad": "acad.exe", "inventor": "Inventor.exe"}


def processes(kind):
    result = subprocess.run(["tasklist.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, creationflags=0x08000000)
    if result.returncode: raise RuntimeError("無法檢查軟體是否已開啟。")
    return [int(r[1]) for r in csv.reader(result.stdout.splitlines()) if len(r)>1 and r[0].casefold() in {n.casefold() for n in EXECUTABLES[kind]}]


def load(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError): return {}


def executable(root, kind):
    state = load(Path(root) / "ui-state.json")
    custom = state.get("Paths", {}).get(kind)
    if custom and Path(custom).is_file() and Path(custom).name.casefold() in {n.casefold() for n in EXECUTABLES[kind]}: return Path(custom)
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for exe in EXECUTABLES[kind]:
            for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r"Software\Microsoft\Windows\CurrentVersion\App Paths"+"\\"+exe,0,winreg.KEY_READ|view) as key:
                        value=Path(winreg.QueryValue(key,None).strip('"'))
                        if value.is_file() and value.name.casefold()==exe.casefold():return value
                except OSError:pass
    program = Path(os.environ.get("ProgramW6432", os.environ.get("PROGRAMFILES", "C:/Program Files")))
    candidates = default_candidates(program,kind)
    return next((p for p in candidates if p.is_file()), None)


def application_state(root, kind):
    frames = [w for w in window_scan.scan(include_hidden=True) if w["kind"]==kind]
    visible = [w for w in frames if w.get("visible", True)]
    pids = processes(kind)
    if visible:
        return {"state":"window_open", "message":NAMES[kind]+" 視窗已開啟，正在確認 MCP 連線。", "windows":visible, "pids":pids}
    if frames:
        return {"state":"hidden", "message":NAMES[kind]+" 目前只有背景視窗。", "windows":frames, "pids":pids}
    if pids:
        starts = [process_start(pid) for pid in pids]
        starting = any(v is not None and time.time()-v < 120 for v in starts)
        return {"state":"starting" if starting else "needs_attention", "message":NAMES[kind]+(" 正在啟動，請等待視窗與授權畫面。" if starting else " 的背景程序尚未提供主視窗，請檢查登入或授權畫面。"), "windows":[], "pids":pids}
    return {"state":"stopped", "message":NAMES[kind]+" 尚未開啟。", "windows":[], "pids":[]}


def ensure_started(root, kind):
    with window_lock(root, "launch"+kind, timeout=8):
        state = application_state(root, kind)
        if kind=='autocad' and state['state']=='window_open':
            custom=load(Path(root)/'ui-state.json').get('Paths',{}).get(kind)
            product='AutoCAD LT' if custom and Path(custom).name.casefold()=='acadlt.exe' else 'AutoCAD' if custom else None
            if len(state['windows'])!=1 or (product and state['windows'][0].get('product') not in (None,product)):
                return {**state,'state':'needs_attention','message':'目前 AutoCAD／LT 視窗與選擇的程式不一致，或有多個視窗。請先保留要操作的唯一視窗，再重新檢查；不會自動改連其他視窗。'}
        if state["state"] == "window_open":
            if len(state["windows"])==1: window_scan.locate(state["windows"][0])
            return state
        if state["state"] == "hidden":
            for w in state["windows"]: window_scan.locate(w)
            return {**state, "state":"starting", "message":"正在顯示既有的 "+NAMES[kind]+" 視窗，不會另開重複程序。"}
        if state["pids"]:
            return state  # Never turn a slow start into a second CAD process.
        marker = Path(root) / "application-launches" / (kind+".json")
        previous = load(marker)
        if time.time()-previous.get("at",0) < 15:
            return {**state, "state":"starting", "message":"剛才已要求開啟 "+NAMES[kind]+"，正在等待啟動結果。"}
        path = executable(root, kind)
        if path is None:
            return {**state, "state":"not_installed", "message":"尚未找到 "+NAMES[kind]+("／AutoCAD LT" if kind=='autocad' else '')+" 主程式位置。若軟體已安裝，請在 Toolkit 按「選擇程式」指定 "+('acad.exe 或 acadlt.exe' if kind=='autocad' else EXES[kind])+"；MCP 元件不需要重新安裝。"}
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 1  # Requested interactive CAD must be visible.
        arguments = [str(path), *({"rhino":["/nosplash"], "autocad":["/nologo"], "inventor":[]}[kind])]
        child = subprocess.Popen(arguments, startupinfo=startup, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        marker.parent.mkdir(parents=True, exist_ok=True)
        temp = marker.with_suffix(".tmp");temp.write_text(json.dumps({"pid":child.pid,"at":time.time(),"executable":str(path)}),encoding="utf-8");temp.replace(marker)
        # Retain the licensing diagnostic's existing timestamp contract.
        import datetime as dt
        launches = Path(root) / "launches.json"; data = load(launches)
        data[kind] = dt.datetime.now(dt.timezone.utc).isoformat()
        temp = launches.with_suffix(".tmp");temp.write_text(json.dumps(data),encoding="utf-8");temp.replace(launches)
        return {"state":"starting", "message":"正在開啟 "+NAMES[kind]+"，請等待主視窗與 MCP 準備完成。", "pid":child.pid,"windows":[]}


def wait_for_application(root, kind, seconds=30):
    deadline = time.monotonic()+min(max(int(seconds),0),45)
    while True:
        state = application_state(root, kind)
        if state["state"] not in ("starting",) or time.monotonic()>=deadline: return state
        time.sleep(min(1, max(0,deadline-time.monotonic())))


def tools():
    return [
        {"name":"open_application", "description":"Open this CAD application visibly, or restore its hidden main window. Reuses existing instances; never starts a duplicate while startup is in progress. No CAD document is modified. Use this instead of shell commands or hidden startup.", "annotations":{"readOnlyHint":False,"destructiveHint":False,"openWorldHint":False,"idempotentHint":True}, "inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
        {"name":"get_application_state", "description":"Wait for this application's visible main window. window_open means the window exists; subsequently check the CAD MCP bridge. Keep waiting on starting; do not launch another process.", "annotations":{"readOnlyHint":True,"destructiveHint":False,"openWorldHint":False,"idempotentHint":True}, "inputSchema":{"type":"object","properties":{"wait_seconds":{"type":"integer","minimum":0,"maximum":45,"default":30}},"additionalProperties":False}},
    ]
