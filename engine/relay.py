"""Transparent NDJSON stdio relay with metadata-only local command receipts."""
import argparse
import json
import os
import subprocess
import sys
import threading
import uuid
import history


def rhino_processes():
    import csv
    value = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq Rhino.exe", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                           creationflags=0x08000000)
    return [int(row[1]) for row in csv.reader(value.stdout.splitlines()) if len(row) > 1 and row[0].lower() == 'rhino.exe']


def tool_failed(message):
    if "error" in message:
        return True
    result = message.get("result", {})
    if not isinstance(result, dict):
        return False
    if result.get("isError"):
        return True
    value = result.get("structuredContent")
    if value is None:
        value = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    for _ in range(5):
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        elif isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value.lower().startswith(("error", "not connected"))
        else:
            break
    return isinstance(value, dict) and (bool(value.get("error")) or value.get("ok") is False)


def run(root, component, command, cwd=None, env=None):
    rhino_instance = None
    if component == "rhino":
        from rhino_instances import choose
        rhino_instance = choose(root, rhino_processes())
        if rhino_instance:
            env = {**os.environ, **(env or {}), "RHINO_MCP_PORT": str(rhino_instance["port"])}
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=sys.stderr.buffer, creationflags=0x08000000 if os.name == "nt" else 0)
    pending = {}
    lock = threading.Lock()
    output_lock = threading.Lock()
    prefix = uuid.uuid4().hex

    def emit(line):
        with output_lock:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    def receipt(fn, *args):
        try:
            fn(root, *args)
        except Exception:
            pass  # Telemetry must never break a CAD command or pollute stdout.

    def requests():
        nonlocal rhino_instance
        try:
            for line in sys.stdin.buffer:
                try:
                    message = json.loads(line)
                    if message.get("method") == "tools/call" and "id" in message:
                        key = json.dumps(message["id"])
                        identity = prefix + ":" + key
                        tool = message.get("params", {}).get("name", "unknown")
                        receipt(history.started, identity, component, tool)
                        if component == 'rhino' and tool not in ('get_modeling_guidance', 'get_rhinoscript_docs', 'search_rhinoscript_functions', 'list_rhinoscript_modules', 'get_module_functions'):
                            from rhino_instances import choose
                            choice = choose(root, rhino_processes())
                            port = int((env or os.environ).get('RHINO_MCP_PORT', '1999'))
                            valid = choice and choice['port'] == port and (rhino_instance is None or (choice['pid'], choice['processStart']) == (rhino_instance['pid'], rhino_instance['processStart']))
                            if not valid:
                                receipt(history.finished, identity, 'blocked')
                                reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': {'isError': True, 'content': [{'type': 'text', 'text': '請在 MCP Toolkit 選擇正在執行的 Rhino，並在 Codex 開啟新對話；此次工具未執行。'}]}}
                                emit((json.dumps(reply, ensure_ascii=True)+'\n').encode('utf-8'))
                                continue
                            rhino_instance = choice
                        with lock:
                            pending[key] = identity
                except (ValueError, AttributeError, TypeError):
                    pass
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    pump = threading.Thread(target=requests, daemon=True)
    pump.start()
    try:
        for line in child.stdout:
            try:
                message = json.loads(line)
                if "id" in message:
                    with lock:
                        identity = pending.pop(json.dumps(message["id"]), None)
                    if identity:
                        receipt(history.finished, identity, "failed" if tool_failed(message) else "succeeded")
            except (ValueError, AttributeError, TypeError):
                pass
            emit(line)
    finally:
        with lock:
            remaining = list(pending.values())
        for identity in remaining:
            receipt(history.finished, identity, "interrupted")
        if child.poll() is None:
            try:
                child.wait(3)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(3)
                except subprocess.TimeoutExpired:
                    child.kill()
        child.stdout.close()
    return child.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--component", required=True, choices=["rhino", "autocad", "inventor"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Missing MCP command")
    sys.exit(run(args.root, args.component, command))
