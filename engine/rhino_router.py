"""Rhino MCP gateway: explicit handles, per-window workers, native execution guards.

The outer MCP transport can serve any number of conversations. It never carries
an implicit selection and it never treats a transport/process ID as a chat ID.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import history
from probe import Client
from window_store import Store, window_lock
import window_scan
from cad_launch import ensure_started, wait_for_application, tools as application_tools

LOCAL = {"get_modeling_guidance", "get_rhinoscript_docs", "search_rhinoscript_functions", "list_rhinoscript_modules", "get_module_functions"}
INSTRUCTIONS = """Rhino is managed by MCP Toolkit. Before any Rhino operation, call
request_window_binding ONCE for this conversation. It automatically opens Rhino
visibly if needed, or restores its hidden window; never start CAD with shell
commands or hidden flags. Tell the user to choose a
window in the Toolkit popup, then use get_window_binding(request_id,
wait_seconds=45) to wait for the selection. If still pending, wait again on the
SAME request until chosen/cancelled/expired; do not busy-poll or create duplicates.
Retain the returned binding_id in this
conversation and include it on EVERY Rhino operation. Never borrow another
conversation's handle, choose by filename/port, or silently change targets.
If document confirmation is required, tell the user to confirm in Toolkit;
only resend a command after confirmation. Nothing is automatically replayed.
Do not release or transfer a binding without the user's request.
Do not ask the user to type mcpstart or drag an RHP file. If the automatic bridge
cannot become ready, use Toolkit's installation/repair flow instead.
"""


def tool(name, description, properties, required=()):
    return {"name": name, "description": description, "annotations":{"readOnlyHint":name=="get_window_binding","destructiveHint":False,"openWorldHint":False}, "inputSchema": {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}}


TOOLS = application_tools() + [
    tool("request_window_binding", "Request a Rhino window selection in MCP Toolkit for this conversation. Call once, retain request_id, and wait for the user to choose. No CAD command is run.", {"label": {"type": "string", "description": "Optional short user-readable connection name, not a claimed Codex chat ID."}}),
    tool("get_window_binding", "Wait for an existing window selection request. Returns pending, bound (with binding_id), cancelled, expired, or disconnected. Use a bounded wait so selection can resume the conversation automatically; do not create duplicate requests.", {"request_id": {"type": "string"}, "wait_seconds": {"type": "integer", "minimum": 0, "maximum": 45, "default": 30}}, ["request_id"]),
    tool("release_window_binding", "Release this conversation's binding only when requested by the user. Waits for running commands. Never closes Rhino or a document.", {"binding_id": {"type": "string"}}, ["binding_id"]),
]


def result(data, error=False):
    return {"isError": error, "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}


def wake_ui(root):
    # Start the installed manager in background mode; its pending-request watcher
    # opens only the requested picker. No visible command window is created.
    app = Path(root) / "McpToolkit.exe"
    if not app.is_file():
        raise ValueError("請開啟已安裝的 MCP Toolkit，再重新要求選窗。")
    subprocess.Popen([str(app), "--background", "--root="+str(root)], creationflags=0x08000000, close_fds=True)


class Router:
    def __init__(self, root, command, cwd=None, env=None):
        self.root, self.command, self.cwd = Path(root), command, cwd
        self.env = {**os.environ, **(env or {})}
        self.store = Store(root)
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.catalog_lock = threading.Lock()
        # The catalog never connects to a CAD instance. All document operations
        # must go through a bound worker and its native guard.
        self.catalog = Client(command, {**self.env, "RHINO_MCP_PORT": "1"}, cwd=cwd, timeout=20)
        self.catalog.initialize()

    def worker(self, binding):
        w = binding["window"]
        key = (binding["id"], w["port"])
        with self.clients_lock:
            client = self.clients.get(key)
            if client is None or client.p.poll() is not None:
                env = {**self.env, "RHINO_MCP_PORT": str(w["port"]), "RHINO_MCP_HOST": "127.0.0.1", "RHINO_MCP_GUARD_FILE": str(self.guard_file(binding["id"]))}
                env["RHINO_MCP_TIMEOUT"] = "120"
                client = Client(self.command, env, cwd=self.cwd, timeout=180)
                client.initialize()
                self.clients[key] = client
            return client

    def guard_file(self, binding_id):
        return self.root / "guards" / (binding_id+".json")

    def validate(self, binding):
        w = binding["window"]
        # Refresh native status, not the UI selection. No file/port-only match.
        candidates = window_scan.scan()
        matches = [v for v in candidates if (v["pid"], v["processStart"], v["hwnd"], v.get("instance_id")) == (w["pid"], w["processStart"], w["hwnd"], w.get("instance_id"))]
        if len(matches) != 1 or matches[0].get("guard_protocol") != 1:
            self.store.release(binding["id"])
            raise ValueError("原本的 Rhino 已離線或外掛需要更新；請重新選窗，此次工具未執行。")
        # The verified instance can change port without changing window identity.
        w.update(matches[0])
        return binding

    def call(self, name, args):
        if name == "open_application":
            value = ensure_started(self.root, "rhino")
            return result(value, value["state"] in ("not_installed", "needs_attention"))
        if name == "get_application_state":
            return result(wait_for_application(self.root,"rhino",args.get("wait_seconds",30)))
        if name == "request_window_binding":
            # Check the application before persisting a request that cannot be shown.
            wake_ui(self.root)
            request = self.store.request(args.get("label"))
            try:
                application = ensure_started(self.root, "rhino")
            except Exception:
                self.store.cancel(request["request_id"])
                raise
            if application["state"] in ("not_installed", "needs_attention"):
                self.store.cancel(request["request_id"])
                return result(application, True)
            return result({**request, "application": application})
        if name == "get_window_binding":
            deadline = time.monotonic()+min(max(int(args.get("wait_seconds", 30)), 0), 45)
            while True:
                status = self.store.request_status(args["request_id"])
                if status["state"] != "pending" or time.monotonic() >= deadline:
                    return result(status)
                time.sleep(min(.3, max(0, deadline-time.monotonic())))
        if name == "release_window_binding":
            b = self.store.binding(args["binding_id"])
            with window_lock(self.root, b["window_id"]):
                self.store.release(b["id"])
            return result({"state": "released"})
        if name in LOCAL:
            with self.catalog_lock:
                return self.catalog.request("tools/call", {"name": name, "arguments": args})
        binding_id = args.get("binding_id")
        if not binding_id:
            raise ValueError("請先呼叫 request_window_binding，在 Toolkit 選窗後取得 binding_id；此次工具未執行。")
        b = self.store.binding(binding_id)
        identity = uuid.uuid4().hex
        history.started(self.root, identity, "rhino", name, binding_id, b["window_id"], b["window"]["display_name"], b["label"])
        outcome = "blocked"
        try:
            with window_lock(self.root, b["window_id"], timeout=180):
                b = self.validate(self.store.binding(binding_id))
                if b["busy"] == -1:
                    raise ValueError("先前指令結果未確認。請檢查並儲存文件，再重新開啟 Rhino；此次工具未執行。")
                # Confirmation and transfer also take this same cross-process lock.
                # Publish a frozen guard before creating/using the child worker.
                guard = {"protocol": 1, "instance_id": b["window"]["instance_id"], "hwnd": b["window"]["hwnd"], "document_serial": b["document_serial"], "document_epoch": b["document_epoch"]}
                path = self.guard_file(binding_id); path.parent.mkdir(exist_ok=True)
                temp = path.with_suffix(".tmp"); temp.write_text(json.dumps(guard), encoding="utf-8"); temp.replace(path)
                observed = Path(str(path)+".observed")
                observed.unlink(missing_ok=True)
                uncertain = Path(str(path)+".uncertain")
                uncertain.unlink(missing_ok=True)
                with self.store.db() as db:
                    db.execute("UPDATE bindings SET busy=? WHERE id=?", (os.getpid(), binding_id))
                try:
                    client = self.worker(b)
                    forwarded = {k: v for k, v in args.items() if k != "binding_id"}
                    answer = client.request("tools/call", {"name": name, "arguments": forwarded})
                    from relay import tool_failed
                    outcome = "failed" if tool_failed({"result": answer}) else "succeeded"
                    if uncertain.exists():
                        answer = result({"error": "Rhino 的指令結果尚未確認。請檢查並儲存文件，再重新開啟 Rhino；Toolkit 不會重播這次指令。"}, True)
                    elif outcome == "failed" and "mcpstart" in json.dumps(answer).lower():
                        answer = result({"error": "Rhino 連線已中斷。請在 MCP Toolkit 檢查連線或修復外掛；已載入外掛的 Rhino 請先儲存再重新開啟。"}, True)
                    return answer
                except BaseException:
                    # A timeout has an unknown CAD outcome. Never retry it; retire
                    # the worker so a late response cannot satisfy the next call.
                    outcome = "interrupted"
                    with self.store.db() as db:
                        db.execute("UPDATE bindings SET busy=-1 WHERE id=?", (binding_id,))
                    with self.clients_lock:
                        worker = self.clients.pop((binding_id, b["window"]["port"]), None)
                    if worker: worker.close()
                    raise
                finally:
                    if uncertain.exists():
                        outcome = "interrupted"
                        with self.store.db() as db:
                            db.execute("UPDATE bindings SET busy=-1 WHERE id=?", (binding_id,))
                    if observed.exists():
                        context = json.loads(observed.read_text(encoding="utf-8"))
                        if context.get("instance_id") != b["window"]["instance_id"] or context.get("hwnd") != b["window"]["hwnd"]:
                            self.store.release(binding_id)
                        else:
                            self.store.observe(binding_id, context)
                    with self.store.db() as db:
                        db.execute("UPDATE bindings SET busy=0 WHERE id=? AND busy!=-1", (binding_id,))
        finally:
            history.finished(self.root, identity, outcome)

    def request(self, method, params):
        if method == "initialize":
            return {"protocolVersion": params.get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "MCP Toolkit Rhino", "version": "0.5.0-beta.2"}, "instructions": INSTRUCTIONS}
        if method == "tools/call":
            try:
                return self.call(params["name"], params.get("arguments") or {})
            except Exception as exc:
                return result({"error": str(exc)}, True)
        with self.catalog_lock:
            answer = self.catalog.request(method, params)
        if method == "tools/list":
            answer = copy.deepcopy(answer)
            for t in answer.get("tools", []):
                if t["name"] not in LOCAL:
                    schema = t["inputSchema"]
                    schema.setdefault("properties", {})["binding_id"] = {"type": "string", "description": "This conversation's binding_id returned by get_window_binding. Never use a different conversation's handle."}
                    required = schema.setdefault("required", [])
                    if "binding_id" not in required: required.append("binding_id")
            answer["tools"].extend(TOOLS)
        return answer

    def close(self):
        for client in [self.catalog, *self.clients.values()]:
            client.close()


def run(root, command, cwd=None, env=None):
    router = Router(root, command, cwd, env)
    output = threading.Lock()
    def handle(message):
        try:
            answer = {"jsonrpc": "2.0", "id": message["id"], "result": router.request(message["method"], message.get("params") or {})}
        except Exception as exc:
            answer = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32603, "message": str(exc)}}
        with output:
            sys.stdout.write(json.dumps(answer, ensure_ascii=True)+"\n"); sys.stdout.flush()
    try:
        with ThreadPoolExecutor(max_workers=16) as pool:
            for line in sys.stdin:
                try:
                    message = json.loads(line)
                    if "id" in message: pool.submit(handle, message)
                except ValueError:
                    continue
    finally:
        router.close()
    return 0
