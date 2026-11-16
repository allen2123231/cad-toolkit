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
from rhino_instances import collect, choose
from common import read_json, atomic_json
from probe import Client

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
                   if len(row) > 1 and row[0].lower() == exe.lower()] for kind, exe in PROCESSES.items()}


def discover(root, config):
    state = load(Path(root) / "state.json")
    try:
        config_data = tomllib.loads(Path(config).read_text(encoding="utf-8"))
        settings = config_data.get("mcp_servers", {})
    except (OSError, ValueError):
        settings = {}
        config_data = {}
    sources = {}
    for kind in NAMES:
        target = state.get("active", {}).get(kind)
        pending = kind in state.get('auto_enable_pending', [])
        if pending:
            target = (state.get('candidate') or {}).get('path')
        if target:
            policy = config_data.get("plugins", {}).get("cad-toolkit@cad-toolkit-local", {})
            enabled = policy.get("enabled", True) and policy.get("mcp_servers", {}).get(kind, {}).get("enabled", False)
            scripts = Path(target) / "envs" / kind / "Scripts"
            command = [str(scripts / "rhinomcp.exe")] if kind == "rhino" else [str(scripts / "python.exe"), "-X", "utf8", "-m", "autocad_mcp" if kind == "autocad" else "src.server"]
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
        else:
            candidate = state.get("candidate") or {}
            if kind in candidate.get("selected", []):
                scripts = Path(candidate["path"]) / "envs" / kind / "Scripts"
                sources[kind] = {"python": str(scripts / "python.exe"), "target": candidate["path"],
                                 "managed": True, "enabled": False}
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
        return {"code": "READY"}


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


def row(kind, source, pids, root, manifest, choices):
    info = {"id": kind, "name": NAMES[kind], "code": "NOT_INSTALLED", "installed": False,
            "managed": source.get("managed", False), "enabled": source.get("enabled", False), "pending": source.get("pending", False), "pids": pids,
            "document": None, "endpoint": "TCP · 等待 Rhino" if kind == "rhino" else "檔案 IPC · 無網路端口" if kind == "autocad" else "COM · 無網路端口",
            "version": None, "expected_version": None, "update": "unknown", "instances": []}
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
        if not pids:
            info["code"] = "LICENSING_ERROR" if licensing_error(root, kind) else "CAD_NOT_RUNNING"
            return info
        if kind == "rhino":
            instances = collect(pids)
            info["instances"] = instances
            instance = choose(root, pids, instances)
            if not instance:
                info["code"] = "SELECT_TARGET" if len(pids) > 1 else "BRIDGE_NOT_CONNECTED"
                return info
            info.update(endpoint=f"127.0.0.1:{instance['port']}", selected_pid=instance["pid"], plugin_version=(instance.get("version") or "").split("+")[0])
            if "command" not in source:
                info["code"] = "NOT_ENABLED"
                return info
            info.update(probe(source, kind, root, instance["port"]))
        else:
            if len(pids) != 1:
                info["code"] = "SELECT_TARGET"
                return info
            app = native(source, kind)
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
        if not source.get("enabled") and info["code"] == "READY":
            info["code"] = "NOT_ENABLED"
    except Exception as exc:
        info["code"] = "LICENSING_ERROR" if licensing_error(root, kind) else "BRIDGE_NOT_CONNECTED"
        info["message"] = str(exc)[-800:]
    return info


def snapshot(root, config, manifest):
    sources = discover(root, config)
    pids = running_processes()
    choices = load(Path(root) / "targets.json")
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
    return {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "rows": rows, "history": history.recent(root)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["snapshot", "row", "clear-history", "select"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", default=str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"))
    parser.add_argument("--manifest")
    parser.add_argument("--kind", choices=list(NAMES))
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    if args.action == "row":
        data = json.load(sys.stdin)
        value = row(args.kind, data["source"], data["pids"], args.root, data["manifest"], data["choices"])
    elif args.action == "snapshot":
        value = snapshot(args.root, args.config, load(args.manifest) if args.manifest else {})
    elif args.action == "clear-history":
        history.clear(args.root)
        value = {"ok": True}
    else:
        if args.kind != "rhino":
            raise ValueError("目前只支援選取 Rhino 的原生連線實例。")
        file = Path(os.environ["LOCALAPPDATA"]) / "RhinoMCP/instances" / f"{args.pid}.json"
        matches = [i for i in collect(running_processes()["rhino"]) if i['pid'] == args.pid]
        if len(matches) != 1:
            raise ValueError("這個 Rhino 已關閉，請重新選取。")
        instance = matches[0]
        choices = load(Path(args.root) / "targets.json")
        choices["rhino"] = {"pid": args.pid, "processStart": instance.get("processStart")}
        atomic_json(Path(args.root) / "targets.json", choices)
        value = {"ok": True}
    print(json.dumps(value, ensure_ascii=True))


if __name__ == "__main__":
    main()
