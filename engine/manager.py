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
import copy

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from common import COMPONENTS, SKILLS, atomic_json, atomic_text, extract_zip, install_lock, read_json, run, sha256, within
from probe import Client
from experience import Cancelled, friendly_error, outcome
from component_state import prepared_targets,component_ready

def emit(message, **values):
    # ASCII JSON transport works even on Windows consoles configured for CP1252.
    # The GUI decodes Unicode escapes before displaying Traditional Chinese.
    print(json.dumps({"schema": 2, "step": "operation", "component": None, "outcome": "progress",
                      "progress": None, "error_code": None, "next_action": None,
                      "message": message, **values}, ensure_ascii=True), flush=True)

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()

def codex_home():
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

def find_codex():
    supplied = os.environ.get('MCP_TOOLKIT_CODEX')
    if supplied and Path(supplied).is_file(): return supplied
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
    if component == "inventor":
        bootstrap = version_dir / "payload/engine/inventor_session.py"
        if bootstrap.exists(): return [str(scripts / "python.exe"), "-X", "utf8", str(bootstrap)]
    return [str(scripts / "python.exe"), "-X", "utf8", "-m",
            "autocad_mcp" if component == "autocad" else "src.server"]

def mcp_env(root):
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", AUTOCAD_MCP_BACKEND="file_ipc",
               AUTOCAD_MCP_IPC_DIR=str(Path(root) / "ipc"), AUTOCAD_MCP_IPC_TIMEOUT="8")
    return env

def plugin_files(destination, template, commands, version, env, history_root=None):
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
        if history_root:
            tools_dir = destination / "tools"
            tools_dir.mkdir(exist_ok=True)
            for helper in ("relay.py", "history.py", "rhino_instances.py", "rhino_router.py", "window_store.py", "window_scan.py", "probe.py", "cad_launch.py"):
                shutil.copy2(Path(__file__).with_name(helper), tools_dir / helper)
            python = Path(cmd[0]).with_name("python.exe")
            cmd = [str(python), "-X", "utf8", str(tools_dir / "relay.py"), "--root", str(history_root), "--component", name, "--", *cmd]
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
        atomic_text(self.path,self.tomlkit.dumps(doc))

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
        if enabled: plugin["enabled"] = True
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
        self.cancel_file = None

    def checkpoint(self):
        if self.cancel_file and self.cancel_file.exists(): raise Cancelled()

    def save(self): atomic_json(self.state_path, self.state)

    def prepared(self):return prepared_targets(self.root,self.state)

    def enabled_components(self,components):
        policy=self.config.load().get('plugins',{}).get('cad-toolkit@cad-toolkit-local',{}).get('mcp_servers',{})
        return {c for c in components if policy.get(c,{}).get('enabled',True)}

    def record_prepared(self,component,target):
        prepared=self.prepared();prepared[component]=str(target);self.state['prepared']=prepared;self.save()

    def prepare_autocad(self,target):
        target=Path(target);lisp=target/'payload/cad/autocad/mcp_dispatch.lsp';cad_dir=target/'autocad'
        shutil.copytree(lisp.parent,cad_dir,dirs_exist_ok=True)
        ipc=(self.root/'ipc').as_posix()+'/'
        text=lisp.read_text(encoding='utf-8').replace('(setq *mcp-ipc-dir* "C:/temp/")','(setq *mcp-ipc-dir* '+json.dumps(ipc,ensure_ascii=False)+')')
        (cad_dir/'mcp_dispatch.lsp').write_text(text,encoding='utf-8')
        shutil.copytree(cad_dir,target/'envs/autocad/Lib/lisp-code',dirs_exist_ok=True)

    def preflight(self):
        cad = {c: processes(n) for c, n in zip(COMPONENTS, ("acad.exe", "Inventor.exe", "Rhino.exe"))}
        try: cli = find_codex()
        except RuntimeError as e: cli = str(e)
        doc = self.config.load()
        result = {"cad": cad, "codex": cli, "conflicts": {c: self.config.conflicts(doc, c) for c in COMPONENTS},
                  "active": self.state["active"], "candidate": self.state["candidate"]}
        emit("環境檢查完成；現有設定尚未切換", result=result)
        return result

    def install(self, payload, selected, setup=None, defer_plugin=False):
        payload = Path(payload).resolve()
        manifest = read_json(payload / "bundle.json")
        version = manifest["version"]
        if not re.fullmatch(r"[0-9A-Za-z.+-]+", version): raise ValueError("版本格式錯誤")
        for relative, expected in manifest["files"].items():
            self.checkpoint()
            if sha256(within(payload, relative)) != expected: raise ValueError(f"安裝來源損毀：{relative}")
        self.state['prepared']=self.prepared()
        self.root.joinpath('ipc').mkdir(parents=True,exist_ok=True)
        # Environments use their final absolute paths; relocating a venv breaks console launchers.
        key = version + "-" + "-".join(sorted(selected)) + "-" + sha256(payload / "bundle.json")[:12]
        target = within(self.root, "versions/" + key)
        self.install_target=str(target)
        if target.exists() and not (target / "ready.json").exists() and str(target) in self.state["active"].values():
            raise RuntimeError("不能覆寫正在使用的版本")
        if not (target / "ready.json").exists():
            target.mkdir(parents=True, exist_ok=True)
            emit("正在準備固定版本檔案；完成後可安全停止。", step="prepare")
            shutil.copytree(payload, target / "payload", dirs_exist_ok=True)
            self.checkpoint()
            runtime = target / "payload/runtime/python.exe"
            uv = target / "payload/uv.exe"
            env = os.environ.copy()
            env.update(UV_NO_MANAGED_PYTHON="1", UV_PYTHON_DOWNLOADS="never", PYTHONUTF8="1")
            for index, c in enumerate(selected):
                self.checkpoint()
                marker = target / (c + ".complete.json")
                if marker.exists() and (target / "envs" / c / "Scripts/python.exe").exists():
                    if c=='autocad':self.prepare_autocad(target)
                    self.record_prepared(c,target)
                    emit(f"{c} 已完成，接續下一項。", step="install", component=c, outcome="completed", progress=100*(index+1)/len(selected))
                    continue
                emit(f"正在安裝 {c}；請稍候。", step="install", component=c, progress=100*index/len(selected))
                venv = target / "envs" / c
                run([uv, "venv", "--clear", "--python", runtime, venv], env=env)
                self.checkpoint()
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
                if c=='autocad':self.prepare_autocad(target)
                atomic_json(marker, {"tools": count, "at": utc()})
                self.record_prepared(c,target)
                emit(f"{c} 安裝完成，接下來需要在 CAD 內設定。", step="install", component=c, outcome="completed", progress=100*(index+1)/len(selected))
            atomic_json(target / "ready.json", {"version": version, "selected": selected, "installed_at": utc()})
        self.checkpoint()
        self.root.joinpath("ipc").mkdir(exist_ok=True)
        lisp = target / "payload/cad/autocad/mcp_dispatch.lsp"
        if "autocad" in selected:
            self.prepare_autocad(target)
        for c in selected:self.record_prepared(c,target)
        self.state["candidate"] = {"path": str(target), "selected": selected, "version": version}
        self.save()
        # Cancellation is deferred during the configuration transaction.
        emit("正在完成 Plugin 設定，請等候完成；這個階段不能中斷。", step="configure", cancellable=False)
        if setup: self.register_windows(Path(setup))
        # Install the Plugin with new servers disabled; existing CAD MCPs keep running.
        if not defer_plugin:
            self.register_plugin(self.state["active"], str(target), set(self.state["active"]))
        emit("元件安裝完成。請完成 CAD 端設定並診斷，通過後再切換 Plugin。", candidate=self.state["candidate"],
             autocad_lisp=str(target / "autocad/mcp_dispatch.lsp"), rhino_plugin=str(target / "payload/cad/rhino/rhinomcp.rhp"))

    def configure_plugin(self):
        candidate = self.state.get('candidate')
        prepared=self.prepared()
        template=(candidate or {}).get('path') or next(iter(prepared.values()),None)
        if not template:
            raise RuntimeError('請先完成連線工具安裝。')
        self.checkpoint()
        emit('正在安裝 Plugin，完成前請勿關閉。', step='configure', cancellable=False)
        self.register_plugin(self.state['active'], template, self.enabled_components(self.state['active']))
        emit('Plugin 已安裝。新元件保持停用，請先逐套檢查連線。', step='plugin', outcome='completed')

    def setup(self, payload, selected, setup=None):
        failure=None
        try:self.install(payload, selected, setup, defer_plugin=True)
        except Cancelled:raise
        except Exception as exc:
            target=getattr(self,'install_target',None)
            prepared=self.prepared()
            completed=[c for c in selected if prepared.get(c)==target and component_ready(target,c)] if target else []
            if not completed:raise
            selected=completed;failure=exc
            if setup:self.register_windows(Path(setup),read_json(Path(payload)/'bundle.json')['version'])
        pending = set(self.state.get('auto_enable_pending', []))
        for component in selected:
            try:
                if component == 'autocad': self.configure_autocad()
                elif component == 'rhino': self.configure_rhino()
                pending.add(component)
            except Exception as exc:
                pending.discard(component)
                emit(f'{component} 元件已安裝，連線設定需要處理。', step='setup', component=component,
                     outcome='needs_action', next_action=getattr(exc,'user_message',str(exc)),details=str(exc))
        self.configure_plugin()
        self.state['auto_enable_pending'] = sorted(pending)
        self.save()
        if failure is not None:
            emit('部分元件安裝失敗；已完成的 MCP 與原有安裝均已保留，可只重試失敗的元件。',step='setup',outcome='needs_action')
            raise failure
        emit('安裝完成。開啟軟體後會自動檢查並啟用連線，不需要輸入啟動指令。', step='setup', outcome='completed')

    def configure_rhino(self):
        from rhino_setup import install_plugin
        target=self.prepared().get('rhino')
        if not target or not component_ready(target,'rhino'):
            raise RuntimeError('請先完成 Rhino 連線工具安裝。')
        self.checkpoint()
        emit('正在安裝 Rhino 自動連線外掛，完成前請勿關閉。', step='configure_rhino', component='rhino', cancellable=False)
        result = install_plugin(target, getattr(self, 'rhino_exe', None))
        opened=processes('Rhino.exe')
        restart=bool(opened) and not result.get('already_installed',False)
        if opened and result.get('already_installed'):
            from rhino_instances import collect
            loaded=collect([int(p['pid']) for p in opened])
            restart=len(loaded)!=len(opened) or any(v.get('guard_protocol')!=1 or v.get('version','').split('+')[0]!=result['version'] for v in loaded)
        result.update(restart_required=restart,installed_at=utc())
        atomic_json(Path(target) / 'rhino-plugin.json', result)
        message = ('外掛已安裝。請自行儲存工作並重新開啟 Rhino，新版會自動連線。'
                   if result['restart_required'] else '外掛已安裝。現在開啟 Rhino，文件準備好後會自動連線。')
        emit(message, step='configure_rhino', component='rhino', outcome='completed', result=result)

    def update(self, payload, selected, setup=None):
        """Upgrade the installed set while preserving user policy and root data."""
        installed = set(self.prepared())
        if set(selected) != installed or not installed:
            raise RuntimeError('更新必須沿用目前已安裝的 MCP 清單。')
        if any(processes({'rhino':'Rhino.exe','autocad':'acad.exe','inventor':'Inventor.exe'}[c]) for c in selected):
            raise RuntimeError('請先儲存並關閉 CAD 軟體，再重新按更新。')
        before = copy.deepcopy(self.state)
        policy = copy.deepcopy(self.config.load().get('plugins', {}).get('cad-toolkit@cad-toolkit-local', {}))
        backup = self.root / 'backups' / ('update-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir(parents=True)
        atomic_json(backup / 'state.json', before)
        for name in ('ui-state.json', 'updates.json', 'McpToolkit.exe', 'CadToolkitSetup.exe'):
            path = self.root / name
            if path.is_file(): shutil.copy2(path, backup / name)
        if (self.root / 'windows.sqlite3').exists():
            import sqlite3
            with sqlite3.connect(self.root / 'windows.sqlite3') as src, sqlite3.connect(backup / 'windows.sqlite3') as dst: src.backup(dst)
        enabled = {c for c in selected if policy.get('mcp_servers', {}).get(c, {}).get('enabled', c in before['active'])}
        def restore_policy():
            doc = self.config.load()
            doc.setdefault('plugins', {})['cad-toolkit@cad-toolkit-local'] = copy.deepcopy(policy)
            self.config.save(doc)
        try:
            self.install(payload, selected, defer_plugin=True)
            for c in selected:
                if c == 'rhino': self.configure_rhino()
                elif c == 'autocad': self.configure_autocad()
            target = self.state['candidate']['path']
            desired = {c: target for c in before['active']}
            self.register_plugin(desired, target, enabled)
            restore_policy()
            self.state['previous'] = before['active']
            self.state['active'] = desired
            self.state['auto_enable_pending'] = before.get('auto_enable_pending', [])
            self.save()
            if setup: self.register_windows(Path(setup))
        except Exception:
            self.state = before
            self.save()
            try:
                old = (before.get('candidate') or {}).get('path') or next(iter(before['active'].values()), None)
                if old:
                    self.register_plugin(before['active'], old, enabled)
                    if 'autocad' in selected:
                        from autocad_setup import install_bundle
                        install_bundle(before['active'].get('autocad', old))
                    if 'rhino' in selected:
                        from rhino_setup import install_plugin
                        install_plugin(before['active'].get('rhino', old))
                for name in ('McpToolkit.exe', 'CadToolkitSetup.exe'):
                    if (backup / name).exists(): shutil.copy2(backup / name, self.root / name)
            finally:
                restore_policy()
                self.state = before
                self.save()
            raise
        emit('更新完成。原安裝位置、啟用設定、視窗名稱與指令紀錄已保留，請重新啟動 Codex。', step='update', outcome='completed', backup=str(backup))

    def configure_autocad(self):
        from autocad_setup import install_bundle
        target=self.prepared().get('autocad')
        if not target:
            raise RuntimeError('請先完成 AutoCAD 連線工具安裝。')
        self.checkpoint()
        self.prepare_autocad(target)
        result = install_bundle(target)
        result['restart_required'] = bool(processes('acad.exe'))
        emit('AutoCAD 自動連線已設定。若已開啟，請儲存工作並重新開啟；之後不需要 APPLOAD。',
             step='configure_autocad', component='autocad', outcome='completed', result=result)

    def register_windows(self, setup, version=None):
        if os.name != "nt": return
        import winreg
        app = self.root / "CadToolkitSetup.exe"
        if setup.resolve() != app.resolve(): shutil.copy2(setup, app)
        desktop_app = self.root / "McpToolkit.exe"
        if setup.resolve() != desktop_app.resolve(): shutil.copy2(setup, desktop_app)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CadToolkit"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            for name, value in {"DisplayName": "MCP Toolkit", "DisplayVersion": version or self.state["candidate"]["version"],
                                "Publisher": "allen2123231", "InstallLocation": str(self.root),
                                "UninstallString": f'"{app}" --uninstall'}.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/MCP Toolkit.lnk"
        run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
             Path(__file__).with_name("create_shortcut.ps1"), "-Target", desktop_app, "-LinkPath", shortcut,
             "-Arguments", f'"--root={self.root}"'], timeout=30)

    def diagnose(self, selected, active=False):
        candidate = self.state.get("candidate")
        prepared=self.prepared()
        result = {}
        for c in selected:
            target = self.state["active"].get(c) if active else prepared.get(c)
            status = {"installed": False, "mcp": False, "cad": False, "bridge": False, "document": None}
            result[c] = status
            if not target or not (Path(target) / "envs" / c).exists():
                status["message"] = "尚未安裝"
                status.update(outcome(c, status))
                emit(f"{c}：尚未安裝", step="diagnose", component=c, result=status, outcome="needs_action", error_code=status['code'], next_action=status['next_action'])
                continue
            status["installed"] = True
            proc = processes({"autocad": "acad.exe", "inventor": "Inventor.exe", "rhino": "Rhino.exe"}[c])
            status["cad"] = bool(proc)
            status["processes"] = proc
            try:
                # Always distinguish successful MCP startup from successful CAD communication.
                env = mcp_env(self.root)
                if c == 'rhino':
                    from rhino_instances import collect
                    instances = [v for v in collect([int(p['pid']) for p in proc]) if v.get('guard_protocol') == 1]
                    instance = instances[0] if instances else None  # Read-only health check, never a conversation target.
                    if instance:
                        env['RHINO_MCP_PORT'] = str(instance['port'])
                        proc = [p for p in proc if int(p['pid']) == instance['pid']]
                        status['processes'] = proc
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
                        if before.get('document_missing'):
                            status['document_missing'] = True
                            status['message'] = 'AutoCAD 尚未開啟圖面'
                            continue
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
                        if caps.get("toolkit_guard_protocol") != 1:
                            raise RuntimeError("請更新配對的 Rhino MCP 外掛並重新開啟 Rhino，以啟用視窗綁定。")
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
            finally:
                enabled = self.state['active'].get(c) == target and self.state.get('plugin_registered', False)
                policy = self.config.load().get('plugins', {}).get('cad-toolkit@cad-toolkit-local', {})
                enabled = enabled and policy.get('enabled', True) and policy.get('mcp_servers', {}).get(c, {}).get('enabled', False)
                status.update(outcome(c, status, enabled))
                emit(f"{c}：{status.get('message', '檢查完成')}", step="diagnose", component=c, result=status,
                     outcome="completed" if status['ready'] else "needs_action", error_code=None if status['ready'] else status['code'], next_action=status['next_action'])
        report = {"at": utc(), "candidate": candidate, "results": result}
        atomic_json(self.root / "diagnostics.json", report)
        return result

    def register_plugin(self, mapping, template_target, enabled):
        marketplace = self.root / "marketplace"
        candidate = self.state.get("candidate")
        mapping={**self.prepared(),**mapping}
        commands = {c: mcp_command(path, c) for c, path in mapping.items()}
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
        version = read_json(Path(template_target) / ("ready.json" if (Path(template_target)/'ready.json').exists() else "payload/bundle.json"))["version"] + "+codex." + stamp
        plugin_files(marketplace / "plugins/cad-toolkit", Path(template_target) / "payload/plugins/cad-toolkit",
                     commands, version, mcp_env(self.root), history_root=self.root)
        atomic_json(marketplace / ".agents/plugins/marketplace.json", {"name": "cad-toolkit-local",
            "interface": {"displayName": "MCP Toolkit"}, "plugins": [{"name": "cad-toolkit",
                "source": {"source": "local", "path": "./plugins/cad-toolkit"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]})
        self.config.set_policy(enabled, self.state["originals"])
        self.save()  # Persist restoration data before any external command.
        cli = find_codex()
        run([cli, "plugin", "marketplace", "add", str(marketplace)], timeout=60)
        run([cli, "plugin", "add", "cad-toolkit@cad-toolkit-local"], timeout=90)
        self.state["plugin_registered"] = True
        self.state["plugin_candidate_path"] = candidate['path'] if candidate else template_target
        self.save()

    def activate(self, selected):
        candidate = self.state.get("candidate")
        prepared=self.prepared()
        if not set(selected).issubset(prepared): raise RuntimeError("請先安裝所選元件")
        checks = self.diagnose(selected)
        failed = [c for c in selected if not checks[c]["bridge"]]
        failed += [c for c in selected if checks[c].get('code') == 'NO_DOCUMENT' and c not in failed]
        if failed: raise RuntimeError("以下元件尚未通過 CAD 連線驗證，保留現有設定：" + ", ".join(failed))
        self.checkpoint()
        previous = dict(self.state["active"])
        desired = {**previous, **{c: prepared[c] for c in selected}}
        self.state["previous"] = previous
        self.save()
        try:
            emit("正在切換這套工具的設定；完成前請勿關閉。", step="configure", cancellable=False)
            self.register_plugin(desired, prepared[selected[0]], self.enabled_components(previous)|set(selected))
            self.state["active"] = desired
            self.state['auto_enable_pending'] = [c for c in self.state.get('auto_enable_pending', []) if c not in selected]
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
        self.checkpoint()
        emit("正在還原設定，請等候完成。", step="configure", cancellable=False)
        self.config.restore_originals(self.state["originals"])
        self.config.set_policy(set(previous), self.state["originals"])
        if previous: self.register_plugin(previous, next(iter(previous.values())), set(previous))
        self.state["previous"], self.state["active"] = self.state["active"], previous
        self.state['auto_enable_pending'] = []
        self.save()
        if previous.get("autocad"):
            from autocad_setup import install_bundle
            install_bundle(previous["autocad"])
        emit("已還原上一組 MCP 設定；請重新啟動 Codex 對話。", active=previous)

    def uninstall(self):
        if any(processes(name) for name in ('Rhino.exe','acad.exe','Inventor.exe')):
            raise RuntimeError("請先自行儲存工作並關閉 CAD，再解除安裝")
        targets = set(self.prepared().values()) | set((self.state.get('previous') or {}).values())
        if self.state.get('candidate'): targets.add(self.state['candidate']['path'])
        versions = self.root / 'versions'
        if versions.is_dir():
            targets.update(str(p.resolve()) for p in versions.iterdir() if p.is_dir() and not p.is_symlink() and not p.is_junction() and (p / 'ready.json').is_file())
        backup = Path(os.environ.get('LOCALAPPDATA', self.root.parent)) / 'McpToolkitBackups' / ('uninstall-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir(parents=True)
        atomic_json(backup / 'state.json', self.state)
        for name in ('ui-state.json','updates.json','windows.sqlite3','windows.sqlite3-wal','windows.sqlite3-shm','history.sqlite3'):
            if (self.root / name).is_file(): shutil.copy2(self.root / name, backup / name)
        if self.config.path.is_file(): shutil.copy2(self.config.path, backup / 'config-before.toml')
        self.checkpoint()
        emit("正在移除 Toolkit 設定並還原舊設定，請等候完成。", step="configure", cancellable=False)
        self.config.set_policy(set(), self.state["originals"])
        if self.state.get("plugin_registered"):
            cli = find_codex()
            run([cli, "plugin", "remove", "cad-toolkit@cad-toolkit-local"], timeout=60)
            run([cli, "plugin", "marketplace", "remove", "cad-toolkit-local"], timeout=60)
            self.state["plugin_registered"] = False
        self.config.restore_originals(self.state["originals"])
        target = self.prepared().get("autocad")
        if target:
            from autocad_setup import remove_bundle
            remove_bundle(target)
        from uninstall_cleanup import remove_rhino
        native = remove_rhino(targets, backup)
        atomic_json(backup / 'native-removal.json', native)
        self.state["active"] = {}; self.state['auto_enable_pending'] = []; self.state["uninstalled_at"] = utc(); self.save()
        if os.name == "nt":
            import winreg
            for product in ('CadToolkit','McpToolkit'):
                key_path = r'Software\Microsoft\Windows\CurrentVersion\Uninstall' + '\\' + product
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        location = winreg.QueryValueEx(key, 'InstallLocation')[0]
                    if Path(location).resolve() == self.root: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
                except FileNotFoundError: pass
            if native['removed']:
                def remove_key(path):
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
                            children=[winreg.EnumKey(key,i) for i in range(winreg.QueryInfoKey(key)[0])]
                        for name in children: remove_key(path+'\\'+name)
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
                    except FileNotFoundError: pass
                remove_key(r'Software\McNeel\Rhinoceros\8.0\Plug-ins\f0b5b632-cc3c-43e7-bc88-da29c47b98bc')
            shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/CAD Toolkit.lnk"
            shortcut.unlink(missing_ok=True)
            (shortcut.parent / "MCP Toolkit.lnk").unlink(missing_ok=True)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                try:
                    command = winreg.QueryValueEx(key, "McpToolkit")[0]
                    if str(self.root).lower() in command.lower():
                        winreg.DeleteValue(key, "McpToolkit")
                except FileNotFoundError:
                    pass
        emit("MCP 與 Plugin 已解除安裝，設定已備份；接著清除 Toolkit 安裝資料夾。", outcome='needs_action' if native['preserved'] else 'completed', backup=str(backup), preserved=native['preserved'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "setup", "update", "install", "configure_plugin", "configure_rhino", "configure_autocad", "diagnose", "activate", "rollback", "uninstall"])
    parser.add_argument("--root", default=str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "McpToolkit"))
    parser.add_argument("--components", default="autocad,inventor,rhino")
    parser.add_argument("--payload")
    parser.add_argument("--setup")
    parser.add_argument("--rhino-exe")
    parser.add_argument("--defer-plugin", action="store_true", help="Prepare components; register Plugin in a separate step")
    parser.add_argument("--active", action="store_true")
    parser.add_argument("--cancel-file")
    args = parser.parse_args()
    selected = list(dict.fromkeys(args.components.split(",")))
    if not selected or not set(selected).issubset(COMPONENTS): parser.error("請選擇有效的 CAD 元件")
    try:
        with install_lock(args.root):
            manager = Manager(args.root)
            manager.rhino_exe = args.rhino_exe
            if args.cancel_file:
                marker = Path(args.cancel_file).resolve()
                if marker.parent != manager.root: raise ValueError('取消標記必須位於安裝目錄')
                manager.cancel_file = marker
            if args.action == "install": manager.install(args.payload, selected, args.setup, args.defer_plugin)
            elif args.action == "setup": manager.setup(args.payload, selected, args.setup)
            elif args.action == "update": manager.update(args.payload, selected, args.setup)
            elif args.action == "diagnose": manager.diagnose(selected, args.active)
            elif args.action == "activate": manager.activate(selected)
            else: getattr(manager, args.action)()
    except Exception as e:
        code, message = friendly_error(e)
        emit(message, error=True, outcome="cancelled" if code == 'CANCELLED' else "failed", error_code=code, details=str(e))
        return 1
    return 0

if __name__ == "__main__": sys.exit(main())
