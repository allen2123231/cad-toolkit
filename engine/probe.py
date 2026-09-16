"""A bounded NDJSON MCP client; never sends a modeling command."""
import json
import os
import queue
import subprocess
import threading
import time

class Client:
    def __init__(self, command, env=None):
        self.p = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", errors="replace",
                                  creationflags=0x08000000 if os.name == "nt" else 0)
        self.messages = queue.Queue()
        self.errors = []
        self.counter = 0
        def read():
            for line in self.p.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: pass
            self.messages.put({"eof": True})
        def stderr():
            for line in self.p.stderr:
                self.errors.append(line[-1000:])
                self.errors[:] = self.errors[-20:]
        self.reader = threading.Thread(target=read, daemon=True)
        self.err_reader = threading.Thread(target=stderr, daemon=True)
        self.reader.start(); self.err_reader.start()

    def request(self, method, params=None, timeout=35):
        self.counter += 1
        self.send({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try: response = self.messages.get(timeout=max(.01, deadline-time.monotonic()))
            except queue.Empty: break
            if response.get("eof"):
                raise RuntimeError("MCP 已退出：" + "".join(self.errors)[-1800:])
            if response.get("id") == self.counter:
                if "error" in response: raise RuntimeError(str(response["error"]))
                return response.get("result", {})
        raise TimeoutError(f"MCP {method} 逾時")

    def send(self, value):
        self.p.stdin.write(json.dumps(value) + "\n"); self.p.stdin.flush()

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "cad-toolkit-diagnostics", "version": "0.1.0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def call(self, name, arguments=None):
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"): raise RuntimeError(str(result))
        if result.get("structuredContent") is not None: return self.decode(result["structuredContent"])
        texts = [i["text"] for i in result.get("content", []) if i.get("type") == "text"]
        return self.decode("\n".join(texts))

    @staticmethod
    def decode(value):
        # SDK 1.x can put a JSON-encoded tool string under structuredContent.result.
        # Decode before judging success, otherwise {result: '{error:...}'} looks successful.
        for _ in range(5):
            if isinstance(value, dict) and set(value) == {"result"}:
                value = value["result"]; continue
            if isinstance(value, str):
                try: value = json.loads(value); continue
                except ValueError: pass
            break
        if isinstance(value, dict) and (value.get("error") or value.get("ok") is False):
            raise RuntimeError(str(value))
        if isinstance(value, str) and value.lower().startswith(("error", "not connected")):
            raise RuntimeError(value)
        return value

    def close(self):
        if self.p.poll() is None:
            self.p.stdin.close()
            try: self.p.wait(3)
            except subprocess.TimeoutExpired:
                self.p.terminate()
                try: self.p.wait(3)
                except subprocess.TimeoutExpired: self.p.kill(); self.p.wait()
        self.reader.join(2); self.err_reader.join(2)
        for pipe in (self.p.stdin, self.p.stdout, self.p.stderr):
            if pipe and not pipe.closed: pipe.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
