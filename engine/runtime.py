"""Live desktop status and bounded bridge checks, independent of the installer UI."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib
import history
from rhino_instances import collect
from window_store import Store, window_lock
import window_scan
from common import read_json, atomic_json
from probe import Client
from component_state import prepared_targets
from cad_products import EXECUTABLES

NAMES = {"rhino": "Rhino", "autocad": "AutoCAD", "inventor": "Inventor"}
PROCESSES = {"rhino": "Rhino.exe", "autocad": "acad.exe", "inventor": "Inventor.exe"}
PACKAGES = {"rhino": "rhinomcp", "autocad": "autocad-mcp", "inventor": "inventor-mcp-server"}


def load(path, default=None):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return {} if default is None else default


def running_processes():
    import csv
    flags = 0x08000000 if os.name == "nt" else 0
    result = subprocess.run(["tasklist.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags, timeout=8)
    return {kind: [int(row[1]) for row in csv.reader(result.stdout.splitlines())
                   if len(row) > 1 and row[0].casefold() in {n.casefold() for n in EXECUTABLES[kind]}] for kind in PROCESSES}


def discover(root, config):
    state = load(Path(root) / "state.json")
    try:
        config_data = tomllib.loads(Path(config).read_text(encoding="utf-8"))
        settings = config_data.get("mcp_servers", {})
    except (OSError, ValueError):
        settings = {}
        config_data = {}
    sources = {}
    prepared=prepared_targets(root,state)
    for kind in NAMES:
        target = state.get("active", {}).get(kind)
        pending = kind in state.get('auto_enable_pending', [])
        if pending:
            target = prepared.get(kind)
        if not target:target=prepared.get(kind)
        if target:
            policy = config_data.get("plugins", {}).get("cad-toolkit@cad-toolkit-local", {})
            enabled = kind in state.get('active',{}) and policy.get("enabled", True) and policy.get("mcp_servers", {}).get(kind, {}).get("enabled", False)
            scripts = Path(target) / "envs" / kind / "Scripts"
            command = [str(scripts / "rhinomcp.exe")] if kind == "rhino" else [str(scripts / "python.exe"), "-X", "utf8", "-m", "autocad_mcp" if kind == "autocad" else "src.server"]
            bootstrap=Path(target)/'payload/engine/autocad_session.py'
            if kind=='autocad' and bootstrap.is_file():command=[str(scripts/'python.exe'),'-X','utf8',str(bootstrap)]
            sources[kind] = {"command": command, "python": str(scripts / "python.exe"), "target": target,
                             "managed": True, "enabled": enabled and not pending, "pending": pending, "env": {"AUTOCAD_MCP_IPC_DIR": str(Path(root) / "ipc")}}
            continue
        matches = [(key, value) for key, value in settings.items() if value.get("enabled", True)
                   and kind in json.dumps({"name": key, **{k: value.get(k) for k in ("command", "args", "cwd")}}).lower()
                   and not value.get("env", {}).get("INVENTOR_MCP_ISOLATED")]
        if len(matches) == 1:
            key, value = matches[0]
            executable = Path(value.get("command", ""))
            python = executable if executable.name.lower() in ("python.exe", "pythonw.exe") else executable.with_name("python.exe")
            sources[kind] = {"command": [str(executable), *value.get("args", [])], "python": str(python),
                             "cwd": value.get("cwd"), "env": value.get("env", {}), "managed": False, "enabled": True}
    return sources


def version(source, kind):
    # Query distribution metadata, not MCP SDK serverInfo.version.
    env = {**os.environ, **source.get("env", {}), "PYTHONUTF8": "1"}
    value = subprocess.run([source["python"], "-c", "import importlib.metadata as m; print(m.version(" + repr(PACKAGES[kind]) + "))"],
                           cwd=source.get("cwd"), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=0x08000000 if os.name == "nt" else 0, timeout=6)
    return value.stdout.strip() if value.returncode == 0 else None


def probe(source, kind, root, port=None):
    env = {**os.environ, **source.get("env", {}), "PYTHONUTF8": "1", "AUTOCAD_MCP_BACKEND": "file_ipc",
           "AUTOCAD_MCP_AUTOLOAD": "1" if source.get("managed") else "0", "AUTOCAD_MCP_IPC_TIMEOUT": "6"}
    if port:
        env["RHINO_MCP_PORT"] = str(port)
    with Client(source["command"], env, cwd=source.get("cwd"), timeout=3) as client:
        client.initialize()
        if kind == "rhino":
            caps = client.call("describe_capabilities")
            if caps.get("plugin_matches_server") is not True:
                return {"code": "VERSION_MISMATCH", "plugin_version": caps.get("version"), "message": "服務與 Rhino 外掛版本不同，請安裝配對版本。"}
            try:
                doc = client.call("get_context")
            except RuntimeError as exc:
                if "Object reference not set" in str(exc) or "No active document" in str(exc):
                    return {"code": "NO_DOCUMENT", "plugin_version": caps["version"], "message": "橋接已連線，請在 Rhino 開啟或新增文件。"}
                raise
            return {"code": "READY", "plugin_version": caps["version"], "document": {"name": doc.get("document_name"), "path": doc.get("document_path"), "units": doc.get("units")}}
        status = client.call("system", {"operation": "status"})
        if status.get("payload", status).get("backend") != "file_ipc":
            raise RuntimeError("AutoCAD 未連接實機橋接")
        client.call("drawing", {"operation": "info"})
        return {"code": "READY","bridge_hwnd":status.get('payload',status).get('hwnd')}


def native(source, kind):
    env = {**os.environ, **source.get("env", {}), "PYTHONUTF8": "1"}
    value = subprocess.run([source["python"], str(Path(__file__).with_name("native_status.py")), kind],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7,
                           creationflags=0x08000000 if os.name == "nt" else 0)
    if value.returncode:
        raise RuntimeError(value.stderr[-700:])
    return json.loads(value.stdout)


def licensing_error(root, kind):
    if kind != 'inventor':
        return False
    launch = load(Path(root) / 'launches.json').get(kind)
    try:
        since = dt.datetime.fromisoformat(launch).timestamp()
        if time.time() - since > 300:
            return False
    except (TypeError, ValueError):
        return False
    folder = Path(os.environ.get('LOCALAPPDATA', '')) / 'Autodesk'
    files = [p for p in folder.glob('Inventor */Logs/*License*.log') if p.stat().st_mtime >= since]
    if not files:
        return False
    file = max(files, key=lambda p: p.stat().st_mtime)
    with file.open('rb') as stream:
        stream.seek(max(0, file.stat().st_size - 32000))
        raw = stream.read()
    text = raw.decode('utf-8', errors='replace').replace('\x00', '')
    return text.rfind('Unable to connect with a Licensing component') > max(text.rfind('IsAuthorized = true'), text.rfind('IsAuthorized=true'), text.rfind('code = 0'))


def window_identity(window):
    return {k:window.get(k) for k in ("pid","hwnd","processStart","instance_id")}


def visible_status(info, frames, pids):
    """Fail closed when a successful probe no longer has its verified frame."""
    if info.get("code") != "READY": return info
    current = [window_identity(w) for w in frames if w["kind"]==info["id"] and w["pid"] in pids and w.get("visible",True)]
    if not any(w in current for w in info.get("verified_windows",[])):
        info.update(code="BACKGROUND_ONLY" if pids else "CAD_NOT_RUNNING",document=None,verified_windows=[])
    return info


def row(kind, source, pids, root, manifest, choices, frames=None):
    info = {"id": kind, "name": NAMES[kind], "code": "NOT_INSTALLED", "installed": False,
            "managed": source.get("managed", False), "enabled": source.get("enabled", False), "pending": source.get("pending", False), "pids": pids,
            "document": None, "endpoint": "TCP · 等待 Rhino" if kind == "rhino" else "檔案 IPC · 無網路端口" if kind == "autocad" else "COM · 無網路端口",
            "version": None, "expected_version": None, "update": "unknown", "instances": [], "verified_windows": []}
    spec = manifest.get("components", {}).get(kind, {})
    info["expected_version"] = spec.get("package_version") or (spec.get("plugin_asset") or {}).get("version")
    if not source or not Path(source.get("python", "")).is_file():
        return info
    info["installed"] = True
    try:
        info["version"] = version(source, kind)
        if info["version"] and info["expected_version"]:
            from_version = tuple(int(x) for x in info["version"].split(".") if x.isdigit())
            to_version = tuple(int(x) for x in info["expected_version"].split(".") if x.isdigit())
            info["update"] = "compatible" if info["version"] == info["expected_version"] else "available" if from_version < to_version else "different"
        if kind=='autocad':
            from autocad_channel import local_channel
            recovery=local_channel(root).state()
            if recovery.get('recovery'):
                info.update(code='RECOVERY_REQUIRED',recovery=recovery,
                            read_available=recovery.get('read_available',False),write_available=False,
                            message='修改暫停；'+('可透過 MCP 唯讀查圖。' if recovery.get('read_available') else '唯讀查詢目前尚未就緒。')+'請檢查並確認圖面；不會自動補送。')
                return info
            if recovery.get('code')=='DESKTOP_BUSY_OTHER_CLIENT':
                info.update(code='BUSY',message='另一個要求正在使用通道；背景檢查不會插入繪圖指令。')
                return info
        if not pids:
            if kind=='autocad':
                from cad_launch import executable
                from cad_products import product_for_executable
                path=executable(root,kind)
                if path:info['product']=product_for_executable(path);info['name']=info['product'] or info['name']
            info["code"] = "LICENSING_ERROR" if licensing_error(root, kind) else "CAD_NOT_RUNNING"
            return info
        frames = window_scan.scan() if frames is None else frames
        visible = [w for w in frames if w["kind"]==kind and w["pid"] in pids and w.get("visible",True)]
        if kind=='autocad' and len(visible)==1 and visible[0].get('product'):info['product']=visible[0]['product'];info['name']=info['product']
        if not visible:
            info["code"] = "BACKGROUND_ONLY"
            info["message"] = "只有背景程序，尚無可見的主視窗；按「開啟 "+NAMES[kind]+"」可顯示視窗。"
            return info
        if kind == "rhino":
            instances = collect([w["pid"] for w in visible])
            info["instances"] = instances
            supported = [i for i in instances if i.get("guard_protocol") == 1 and any(w["pid"]==i["pid"] and w["hwnd"]==i.get("hwnd") for w in visible)]
            if not supported:
                info["code"] = "VERSION_MISMATCH" if instances else "STARTING" if any(time.time()-float(w.get("processStart",0))<120 for w in visible) else "BRIDGE_NOT_CONNECTED"
                if instances: info["message"] = "請更新 Rhino MCP 外掛並重新開啟 Rhino，以啟用獨立視窗綁定。"
                return info
            instance = supported[0]  # Health probe only; never selects a tool target.
            info["verified_windows"] = [window_identity(w) for w in visible if w["pid"]==instance["pid"] and w["hwnd"]==instance["hwnd"]]
            info.update(endpoint="各視窗獨立 TCP 端口", plugin_version=(instance.get("version") or "").split("+")[0])
            if "command" not in source:
                info["code"] = "NOT_ENABLED"
                return info
            info.update(probe(source, kind, root, instance["port"]))
        else:
            if len(pids) != 1:
                info["code"] = "SELECT_TARGET"
                return info
            if kind=='autocad' and visible[0].get('product')=='AutoCAD LT':
                from autocad_context import read_context
                app=read_context(root,visible[0])
                info['name']='AutoCAD LT';info['product']='AutoCAD LT'
            else:app = native(source, kind)
            matched = [w for w in visible if w["hwnd"]==app.get("hwnd")]
            if not matched:
                info["code"]="TARGET_MISMATCH"
                info["message"]="MCP 尚未附加到可見的軟體視窗，請重新檢查連線。"
                return info
            info["verified_windows"] = [window_identity(w) for w in matched]
            info.update(document=app.get("document"), cad_version=app.get("version"), hwnd=app.get("hwnd"))
            if kind == "inventor":
                info["code"] = "READY" if app.get("ready") else "LICENSING_ERROR" if licensing_error(root, kind) else "STARTING"
            elif not app.get("document"):
                info["code"] = "NO_DOCUMENT"
            elif app["document"].get("busy"):
                info["code"] = "BUSY"
            elif "command" not in source:
                info["code"] = "NOT_ENABLED"
            else:
                info.update(probe(source, kind, root))
                if app.get('product')=='AutoCAD LT' and info.get('code')=='READY' and info.get('bridge_hwnd')!=app['hwnd']:
                    info['code']='TARGET_MISMATCH';info['message']='AutoCAD LT 橋接視窗身分不符，已停止連線。'
        if not source.get("enabled") and info["code"] == "READY":
            info["code"] = "NOT_ENABLED"
    except Exception as exc:
        info["code"] = "VERSION_MISMATCH" if kind=='autocad' and 'BRIDGE_UPDATE_REQUIRED' in str(exc) else "LICENSING_ERROR" if licensing_error(root, kind) else "BRIDGE_NOT_CONNECTED"
        info["message"] = str(exc)[-800:]
    return info


def snapshot(root, config, manifest):
    sources = discover(root, config)
    pids = running_processes()
    choices = {}
    # Isolate COM and MCP waits from UI; calls are bounded by their child process.
    def get(kind):
        try:
            command = [sys.executable, str(Path(__file__).resolve()), "row", "--root", str(root), "--kind", kind]
            data = {"source": sources.get(kind, {}), "pids": pids[kind], "manifest": manifest, "choices": choices}
            child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                output, error = child.communicate(json.dumps(data), timeout=22)
            except subprocess.TimeoutExpired:
                if child.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill.exe", "/PID", str(child.pid), "/T", "/F"], capture_output=True,
                                       creationflags=0x08000000, timeout=5)
                    else:
                        child.kill()
                child.communicate(timeout=5)
                raise
            if child.returncode:
                raise RuntimeError(error[-500:])
            return json.loads(output)
        except Exception:
            return {"id": kind, "name": NAMES[kind], "code": "CHECK_TIMEOUT", "installed": bool(sources.get(kind)),
                    "managed": sources.get(kind, {}).get("managed", False), "pids": pids[kind], "update": "unknown", "instances": [],
                    "message": "軟體未在時間內回應；不會另外啟動或關閉 CAD。"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(get, NAMES))
    # A window can close while its bridge check is in flight.
    current_frames = window_scan.scan()
    current_pids = running_processes()
    rows = [visible_status(r,current_frames,current_pids[r["id"]]) for r in rows]
    return {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "rows": rows, "history": history.recent(root)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "row", "clear-history", "windows", "rename-window", "locate-window", "bind-window", "cancel-binding", "release-binding", "confirm-document", "clear-window-titles", "open-cad", "application-state", "confirm-autocad-recovery"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", default=str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"))
    parser.add_argument("--manifest")
    parser.add_argument("--kind", choices=list(NAMES))
    parser.add_argument("--pid", type=int)
    parser.add_argument("--window-id")
    parser.add_argument("--request-id")
    parser.add_argument("--binding-id")
    parser.add_argument("--name")
    parser.add_argument("--serial", type=int)
    parser.add_argument("--epoch", type=int)
    parser.add_argument("--target-token")
    parser.add_argument("--wait-seconds",type=int,default=0)
    args = parser.parse_args()
    if args.action == "row":
        data = json.load(sys.stdin)
        value = row(args.kind, data["source"], data["pids"], args.root, data["manifest"], data["choices"])
    elif args.action == "snapshot":
        value = snapshot(args.root, args.config, load(args.manifest) if args.manifest else {})
    elif args.action == "clear-history":
        history.clear(args.root)
        value = {"ok": True}
    elif args.action == "windows":
        value = window_scan.refresh(args.root, names=True)
        from autocad_channel import local_channel
        value['autocad_recovery']=local_channel(args.root).state()
    elif args.action == 'confirm-autocad-recovery':
        from autocad_channel import local_channel
        value=local_channel(args.root).confirm(args.request_id,args.target_token)
    elif args.action in ("open-cad","application-state"):
        from cad_launch import ensure_started, wait_for_application
        if not args.kind: raise ValueError("請指定要開啟的軟體。")
        value = ensure_started(args.root,args.kind) if args.action=="open-cad" else wait_for_application(args.root,args.kind,args.wait_seconds)
    else:
        store = Store(args.root)
        panel = window_scan.refresh(args.root)
        window = next((w for w in panel["windows"] if w["window_id"] == args.window_id), None)
        if args.action == "clear-window-titles":
            window_scan.apply_names(args.root, panel["windows"], clear=True)
        elif args.action == "cancel-binding":
            store.cancel(args.request_id)
        elif args.action in ("release-binding", "confirm-document"):
            b = store.binding(args.binding_id)
            with window_lock(args.root, b["window_id"], timeout=25):
                b = store.binding(args.binding_id)
                if args.action == "release-binding": store.release(args.binding_id)
                else:
                    current = b["window"]
                    if (current.get("document_serial"), current.get("document_epoch")) != (args.serial, args.epoch):
                        raise ValueError("文件再次切換，請重新確認。")
                    store.confirm(args.binding_id, args.serial, args.epoch)
        else:
            if not window: raise ValueError("視窗已關閉，請重新選取。")
            if args.action == "rename-window":
                store.rename(args.window_id, args.name or "")
                window_scan.apply_names(args.root, store.windows())
            elif args.action == "locate-window": window_scan.locate(window)
            elif args.action == "bind-window":
                with window_lock(args.root, args.window_id, timeout=25):
                    # Refresh again after waiting for an in-flight command.
                    window_scan.refresh(args.root)
                    store.bind(args.request_id, args.window_id, args.binding_id)
        value = {"ok": True}
    print(json.dumps(value, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TimeoutError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        sys.exit(2)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "無法完成這次要求，請重新檢查視窗或到「MCP 管理」修復元件。"}, ensure_ascii=True))
        sys.exit(1)
