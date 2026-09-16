"""CAD Toolkit lifecycle manager. GUI and automation share this implementation."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from common import COMPONENTS, SKILLS, atomic_json, extract_zip, install_lock, read_json, run, sha256, within
from probe import Client

def emit(message, **values):
    print(json.dumps({"message": message, **values}, ensure_ascii=False), flush=True)

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()

def codex_home():
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

def find_codex():
    found = shutil.which("codex.exe") or shutil.which("codex")
    if found: return found
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI/Codex/bin"
    candidates = sorted(base.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates: return str(candidates[0])
    raise RuntimeError("找不到 Codex CLI。請先安裝或更新 Codex，再重新執行。")

def processes(name):
    if os.name != "nt": return []
    import csv, io
    output = run(["tasklist.exe", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {name}"])
    return [{"name": row[0], "pid": row[1]} for row in csv.reader(io.StringIO(output))
            if len(row) > 1 and row[0].lower() == name.lower()]

def mcp_command(version_dir, component):
    version_dir = Path(version_dir)
    scripts = version_dir / "envs" / component / "Scripts"
    if component == "rhino": return [str(scripts / "rhinomcp.exe")]
    return [str(scripts / "python.exe"), "-X", "utf8", "-m",
            "autocad_mcp" if component == "autocad" else "src.server"]

def mcp_env(root):
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", AUTOCAD_MCP_BACKEND="file_ipc",
               AUTOCAD_MCP_IPC_DIR=str(Path(root) / "ipc"), AUTOCAD_MCP_IPC_TIMEOUT="8")
    return env

def plugin_files(destination, template, commands, version, env):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = read_json(Path(template) / "plugin.json")
    metadata["version"] = version
    atomic_json(destination / "plugin.json", metadata)
    legacy = dict(metadata)
    legacy.pop("$schema", None)
    legacy["interface"] = legacy.pop("extensions")["com.openai"]["interface"]
    legacy.update(skills="./skills/", mcpServers="./.mcp.json")
    atomic_json(destination / ".codex-plugin/plugin.json", legacy)
    portable, compatible = {}, {}
    for name, cmd in commands.items():
        value = {"command": cmd[0], "args": cmd[1:], "env": {key: env[key] for key in (
            "PYTHONUTF8", "PYTHONIOENCODING", "AUTOCAD_MCP_BACKEND", "AUTOCAD_MCP_IPC_DIR", "AUTOCAD_MCP_IPC_TIMEOUT")}}
        compatible[name] = value
        portable[name] = {"type": "stdio", **value}
    atomic_json(destination / "mcp.json", {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", "mcpServers": portable})
    atomic_json(destination / ".mcp.json", {"mcpServers": compatible})
    skill_root = destination / "skills"
    if skill_root.exists(): shutil.rmtree(skill_root)
    skill_root.mkdir()
    for skill, requirements in SKILLS.items():
        if all(r in commands for r in requirements):
            shutil.copytree(Path(template) / "skills" / skill, skill_root / skill)

class ConfigEditor:
    """Edit individual TOML enabled keys; keep unrelated content and restore only owned changes."""
    def __init__(self, home, backups):
        import tomlkit
        self.tomlkit = tomlkit
        self.path = Path(home) / "config.toml"
        self.backups = Path(backups)

    def load(self):
        return self.tomlkit.parse(self.path.read_text(encoding="utf-8") if self.path.exists() else "")

    def save(self, doc):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.backups / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".toml"))
        temp = self.path.with_suffix(".cad-toolkit.tmp")
        temp.write_text(self.tomlkit.dumps(doc), encoding="utf-8")
        os.replace(temp, self.path)

    def conflicts(self, doc, component):
        result = []
        for name, config in doc.get("mcp_servers", {}).items():
            text = json.dumps({"name": name, "command": config.get("command"), "args": config.get("args"), "cwd": config.get("cwd")}).lower()
            if component in text and config.get("enabled", True): result.append(name)
        return result

    def set_policy(self, enabled, originals):
        doc = self.load()
        for component in enabled:
            for name in self.conflicts(doc, component):
                originals.setdefault(name, {"present": "enabled" in doc["mcp_servers"][name],
                                           "value": doc["mcp_servers"][name].get("enabled", True),
                                           "identity": {k: v for k, v in doc["mcp_servers"][name].items() if k != "enabled"}})
                doc["mcp_servers"][name]["enabled"] = False
        plugin = doc.setdefault("plugins", {}).setdefault("cad-toolkit@cad-toolkit-local", {})
        policy = plugin.setdefault("mcp_servers", {})
        for c in COMPONENTS: policy.setdefault(c, {})["enabled"] = c in enabled
        self.save(doc)

    def restore_originals(self, originals):
        doc = self.load()
        for name, prior in originals.items():
            server = doc.get("mcp_servers", {}).get(name)
            if (server is not None and server.get("enabled") is False
                    and {k: v for k, v in server.items() if k != "enabled"} == prior.get("identity")):
                if prior["present"]: server["enabled"] = prior["value"]
                else: del server["enabled"]
        self.save(doc)

class Manager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state_path = self.root / "state.json"
        self.state = read_json(self.state_path) if self.state_path.exists() else {
            "schema": 1, "active": {}, "candidate": None, "previous": None, "originals": {}}
        self.config = ConfigEditor(codex_home(), self.root / "backups")

    def save(self): atomic_json(self.state_path, self.state)

    def preflight(self):
        cad = {c: processes(n) for c, n in zip(COMPONENTS, ("acad.exe", "Inventor.exe", "Rhino.exe"))}
        try: cli = find_codex()
        except RuntimeError as e: cli = str(e)
        doc = self.config.load()
        result = {"cad": cad, "codex": cli, "conflicts": {c: self.config.conflicts(doc, c) for c in COMPONENTS},
                  "active": self.state["active"], "candidate": self.state["candidate"]}
        emit("環境檢查完成；現有設定尚未切換", result=result)
        return result

    def install(self, payload, selected, setup=None):
        payload = Path(payload).resolve()
        manifest = read_json(payload / "bundle.json")
        version = manifest["version"]
        if not re.fullmatch(r"[0-9A-Za-z.+-]+", version): raise ValueError("版本格式錯誤")
        for relative, expected in manifest["files"].items():
            if sha256(within(payload, relative)) != expected: raise ValueError(f"安裝來源損毀：{relative}")
        # Environments use their final absolute paths; relocating a venv breaks console launchers.
        key = version + "-" + "-".join(sorted(selected)) + "-" + sha256(payload / "bundle.json")[:12]
        target = within(self.root, "versions/" + key)
        if target.exists() and not (target / "ready.json").exists():
            if str(target) in self.state["active"].values(): raise RuntimeError("不能覆寫正在使用的版本")
            shutil.rmtree(target)
        if not (target / "ready.json").exists():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(payload, target / "payload", dirs_exist_ok=True)
            runtime = target / "payload/runtime/python.exe"
            uv = target / "payload/uv.exe"
            env = os.environ.copy()
            env.update(UV_NO_MANAGED_PYTHON="1", UV_PYTHON_DOWNLOADS="never", PYTHONUTF8="1")
            for c in selected:
                emit(f"建立 {c} 獨立 Python 環境")
                venv = target / "envs" / c
                run([uv, "venv", "--python", runtime, venv], env=env)
                run([uv, "pip", "install", "--python", venv / "Scripts/python.exe", "--offline", "--no-index",
                     "--find-links", target / "payload/wheels" / c, "--require-hashes", "-r",
                     target / "payload/locks" / (c + ".txt")], env=env)
                wheels = list((target / "payload/wheels" / c).glob(manifest["components"][c]["wheel"]))
                if len(wheels) != 1: raise ValueError("找不到唯一的 MCP 套件")
                run([uv, "pip", "install", "--python", venv / "Scripts/python.exe", "--no-deps", "--offline", wheels[0]], env=env)
                # AutoCAD handshake must work even before AutoCAD starts. Offline only for this smoke check.
                probe_env = mcp_env(self.root)
                if c == "autocad": probe_env["AUTOCAD_MCP_BACKEND"] = "ezdxf"
                with Client(mcp_command(target, c), probe_env) as client:
                    client.initialize()
                    count = len(client.request("tools/list").get("tools", []))
                    if not count: raise RuntimeError(f"{c} 沒有提供工具")
                emit(f"{c} MCP 啟動通過：{count} 個工具（尚未驗證 CAD 連線）")
            atomic_json(target / "ready.json", {"version": version, "selected": selected, "installed_at": utc()})
        self.root.joinpath("ipc").mkdir(exist_ok=True)
        lisp = target / "payload/cad/autocad/mcp_dispatch.lsp"
        if "autocad" in selected:
            cad_dir = target / "autocad"
            shutil.copytree(lisp.parent, cad_dir, dirs_exist_ok=True)
            text = lisp.read_text(encoding="utf-8")
            ipc = (self.root / "ipc").as_posix() + "/"
            text = text.replace('(setq *mcp-ipc-dir* "C:/temp/")', '(setq *mcp-ipc-dir* ' + json.dumps(ipc, ensure_ascii=False) + ')')
            (cad_dir / "mcp_dispatch.lsp").write_text(text, encoding="utf-8")
            # Match the upstream wheel's LISP_DIR for actionable error messages.
            shutil.copytree(cad_dir, target / "envs/autocad/Lib/lisp-code", dirs_exist_ok=True)
        self.state["candidate"] = {"path": str(target), "selected": selected, "version": version}
        self.save()
        if setup: self.register_windows(Path(setup))
        emit("元件安裝完成。請完成 CAD 端設定並診斷，通過後再切換 Plugin。", candidate=self.state["candidate"],
             autocad_lisp=str(target / "autocad/mcp_dispatch.lsp"), rhino_plugin=str(target / "payload/cad/rhino/rhinomcp.rhp"))

    def register_windows(self, setup):
        if os.name != "nt": return
        import winreg
        app = self.root / "CadToolkitSetup.exe"
        if setup.resolve() != app.resolve(): shutil.copy2(setup, app)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CadToolkit"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            for name, value in {"DisplayName": "CAD Toolkit", "DisplayVersion": self.state["candidate"]["version"],
                                "Publisher": "allen2123231", "InstallLocation": str(self.root),
                                "UninstallString": f'"{app}" --uninstall'}.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/CAD Toolkit.url"
        shortcut.write_text("[InternetShortcut]\nURL=" + app.as_uri() + "\n", encoding="utf-8")

    def diagnose(self, selected, active=False):
        candidate = self.state.get("candidate")
        result = {}
        for c in selected:
            target = self.state["active"].get(c) if active else (candidate or {}).get("path")
            status = {"installed": False, "mcp": False, "cad": False, "bridge": False, "document": None}
            result[c] = status
            if not target or not (Path(target) / "envs" / c).exists():
                status["message"] = "尚未安裝"; continue
            status["installed"] = True
            proc = processes({"autocad": "acad.exe", "inventor": "Inventor.exe", "rhino": "Rhino.exe"}[c])
            status["cad"] = bool(proc)
            status["processes"] = proc
            try:
                # Always distinguish successful MCP startup from successful CAD communication.
                env = mcp_env(self.root)
                if c == "autocad" and len(proc) != 1: env["AUTOCAD_MCP_BACKEND"] = "ezdxf"
                with Client(mcp_command(target, c), env) as client:
                    client.initialize(); tools = client.request("tools/list")
                    status["mcp"] = bool(tools.get("tools"))
                    if len(proc) != 1:
                        status["message"] = "CAD 尚未啟動" if not proc else "多個 CAD 程序：請先確認唯一目標後重試"
                        continue
                    if c == "autocad":
                        helper = Path(__file__).with_name("autocad_readonly.py")
                        python = Path(target) / "envs/autocad/Scripts/python.exe"
                        before = json.loads(run([python, helper], timeout=20))
                        if before["cmdactive"] != 0: raise RuntimeError("AutoCAD 有進行中的指令，請完成後再診斷")
                        info = client.call("system", {"operation": "status"})
                        status["backend_status"] = info
                        if not isinstance(info, dict) or info.get("payload", info).get("backend") != "file_ipc":
                            raise RuntimeError("尚未連接 file_ipc")
                        document = client.call("drawing", {"operation": "info"})
                        if isinstance(document, dict) and document.get("ok") is False: raise RuntimeError(str(document))
                        after = json.loads(run([python, helper], timeout=20))
                        if before != after: raise RuntimeError("AutoCAD 文件狀態在診斷期間改變，請重新確認目標")
                        status["document"] = {"identity": after, "drawing_info": document}
                    elif c == "rhino":
                        caps = client.call("describe_capabilities")
                        if not isinstance(caps, dict) or caps.get("plugin_matches_server") is not True:
                            raise RuntimeError("Rhino 外掛與 MCP 版本未確認一致：" + str(caps))
                        status["capabilities"] = caps
                        status["document"] = client.call("get_document_summary")
                    else:
                        # The upstream connect() may launch Inventor. Bind GetActiveObject directly
                        # in a read-only helper instead, so diagnostics can never launch a new instance.
                        helper = Path(__file__).with_name("inventor_readonly.py")
                        text = run([Path(target) / "envs/inventor/Scripts/python.exe", helper], timeout=30)
                        status["document"] = json.loads(text)
                    status["bridge"] = True
                    status["message"] = "連線成功（唯讀檢查）"
            except Exception as e: status["message"] = str(e)
            finally: emit(f"{c}：{status.get('message', '檢查完成')}", component=c, result=status)
        report = {"at": utc(), "candidate": candidate, "results": result}
        atomic_json(self.root / "diagnostics.json", report)
        return result

    def register_plugin(self, mapping, template_target, enabled):
        marketplace = self.root / "marketplace"
        commands = {c: mcp_command(path, c) for c, path in mapping.items()}
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
        version = read_json(Path(template_target) / "ready.json")["version"] + "+codex." + stamp
        plugin_files(marketplace / "plugins/cad-toolkit", Path(template_target) / "payload/plugins/cad-toolkit",
                     commands, version, mcp_env(self.root))
        atomic_json(marketplace / ".agents/plugins/marketplace.json", {"name": "cad-toolkit-local",
            "interface": {"displayName": "CAD Toolkit"}, "plugins": [{"name": "cad-toolkit",
                "source": {"source": "local", "path": "./plugins/cad-toolkit"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]})
        self.config.set_policy(enabled, self.state["originals"])
        self.save()  # Persist restoration data before any external command.
        cli = find_codex()
        run([cli, "plugin", "marketplace", "add", str(marketplace)], timeout=60)
        run([cli, "plugin", "add", "cad-toolkit@cad-toolkit-local"], timeout=90)
        self.state["plugin_registered"] = True
        self.save()

    def activate(self, selected):
        candidate = self.state.get("candidate")
        if not candidate or not set(selected).issubset(candidate["selected"]): raise RuntimeError("請先安裝所選元件")
        checks = self.diagnose(selected)
        failed = [c for c in selected if not checks[c]["bridge"]]
        if failed: raise RuntimeError("以下元件尚未通過 CAD 連線驗證，保留現有設定：" + ", ".join(failed))
        previous = dict(self.state["active"])
        desired = {**previous, **{c: candidate["path"] for c in selected}}
        self.state["previous"] = previous
        self.save()
        try:
            self.register_plugin(desired, candidate["path"], set(desired))
            self.state["active"] = desired
            self.save()
        except Exception:
            self.config.restore_originals(self.state["originals"])
            self.config.set_policy(set(previous), self.state["originals"])
            if previous: self.register_plugin(previous, next(iter(previous.values())), set(previous))
            raise
        emit("Plugin 已切換。請在 Codex 開啟新對話驗證工具；目前對話不會熱更新。", active=desired)

    def rollback(self):
        previous = self.state.get("previous")
        if previous is None: raise RuntimeError("沒有可還原的切換紀錄")
        # Rhino registrations are external; never switch a loaded plugin silently.
        if self.state["active"].get("rhino") != previous.get("rhino") and processes("Rhino.exe"):
            raise RuntimeError("請先自行儲存工作並關閉 Rhino，再還原及重新註冊對應外掛")
        self.config.restore_originals(self.state["originals"])
        self.config.set_policy(set(previous), self.state["originals"])
        if previous: self.register_plugin(previous, next(iter(previous.values())), set(previous))
        self.state["previous"], self.state["active"] = self.state["active"], previous
        self.save()
        emit("已還原上一組 MCP 設定；請重新啟動 Codex 對話。", active=previous)

    def uninstall(self):
        if processes("Rhino.exe") and "rhino" in self.state["active"]:
            raise RuntimeError("請先自行儲存工作並關閉 Rhino，再解除安裝")
        self.config.set_policy(set(), self.state["originals"])
        if self.state.get("plugin_registered"):
            cli = find_codex()
            run([cli, "plugin", "remove", "cad-toolkit@cad-toolkit-local"], timeout=60)
            run([cli, "plugin", "marketplace", "remove", "cad-toolkit-local"], timeout=60)
            self.state["plugin_registered"] = False
        self.config.restore_originals(self.state["originals"])
        self.state["active"] = {}; self.state["uninstalled_at"] = utc(); self.save()
        if os.name == "nt":
            import winreg
            try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CadToolkit")
            except FileNotFoundError: pass
            shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/CAD Toolkit.url"
            shortcut.unlink(missing_ok=True)
        emit("已解除 Plugin 並還原舊設定。版本檔案與備份保留在安裝目錄，可在 CAD 關閉後手動刪除。")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "install", "diagnose", "activate", "rollback", "uninstall"])
    parser.add_argument("--root", default=str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CadToolkit"))
    parser.add_argument("--components", default="autocad,inventor,rhino")
    parser.add_argument("--payload")
    parser.add_argument("--setup")
    parser.add_argument("--active", action="store_true")
    args = parser.parse_args()
    selected = list(dict.fromkeys(args.components.split(",")))
    if not selected or not set(selected).issubset(COMPONENTS): parser.error("請選擇有效的 CAD 元件")
    try:
        with install_lock(args.root):
            manager = Manager(args.root)
            if args.action == "install": manager.install(args.payload, selected, args.setup)
            elif args.action == "diagnose": manager.diagnose(selected, args.active)
            elif args.action == "activate": manager.activate(selected)
            else: getattr(manager, args.action)()
    except Exception as e:
        emit(str(e), error=True)
        return 1
    return 0

if __name__ == "__main__": sys.exit(main())
