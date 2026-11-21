"""Transparent NDJSON stdio relay with metadata-only local command receipts."""
import argparse
import json
import os
import subprocess
import sys
import threading
import uuid
import history
from cad_launch import ensure_started, wait_for_application, tools as application_tools


def recovery_tool():
    return dict(name='get_recovery_state',description='Read AutoCAD/LT interruption and native bridge state without using the CAD command mailbox. Never retries work. Recovery requires the user to reopen CAD and confirm the drawing in Toolkit; after confirmation explicitly send new operations.',
                inputSchema={'type':'object','properties':{},'additionalProperties':False},annotations={'readOnlyHint':True,'openWorldHint':False})


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
    if component == "rhino":
        from rhino_router import run as route
        return route(root, command, cwd, env)
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

    def application_reply(message):
        tool=message['params']['name'];arguments=message['params'].get('arguments') or {}
        try:
            value=ensure_started(root,component) if tool=='open_application' else wait_for_application(root,component,arguments.get('wait_seconds',30))
            answer={'isError':value['state'] in ('not_installed','needs_attention'),'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}]}
        except Exception as exc:
            answer={'isError':True,'content':[{'type':'text','text':str(exc)}]}
        try:emit((json.dumps({'jsonrpc':'2.0','id':message['id'],'result':answer},ensure_ascii=True)+'\n').encode('utf-8'))
        except (OSError,ValueError):pass  # Caller may have disconnected while CAD starts.

    def requests():
        try:
            for line in sys.stdin.buffer:
                try:
                    message = json.loads(line)
                    if component=='autocad' and message.get('method')=='tools/call' and 'id' in message:
                        from autocad_channel import local_channel,failed
                        from autocad_access import readonly_tool
                        name=message.get('params',{}).get('name')
                        if name not in ('open_application','get_application_state'):
                            state=local_channel(root).state()
                            is_read=readonly_tool(name,message.get('params',{}).get('arguments') or {})
                            if name=='get_recovery_state' or (state.get('recovery') and not is_read) or state.get('code')=='DESKTOP_BUSY_OTHER_CLIENT':
                                value=state if name=='get_recovery_state' else failed('RECOVERY_REQUIRED' if state.get('recovery') else 'DESKTOP_BUSY_OTHER_CLIENT')
                                identity=prefix+':'+json.dumps(message['id'])
                                receipt(history.started,identity,component,name)
                                receipt(history.finished,identity,'succeeded' if name=='get_recovery_state' else 'blocked')
                                answer={'isError':name!='get_recovery_state','content':[{'type':'text','text':json.dumps(value,ensure_ascii=True)}]}
                                emit((json.dumps({'jsonrpc':'2.0','id':message['id'],'result':answer})+'\n').encode())
                                continue
                    if message.get("method") == "tools/call" and "id" in message and message.get("params",{}).get("name") in ("open_application", "get_application_state"):
                        # Readiness may wait 45 seconds. Keep the NDJSON reader
                        # free to accept recovery/status and reject unsafe work.
                        threading.Thread(target=application_reply,args=(message,),daemon=True).start()
                        continue
                    if message.get("method") == "tools/call" and "id" in message:
                        key = json.dumps(message["id"])
                        identity = prefix + ":" + key
                        tool = message.get("params", {}).get("name", "unknown")
                        receipt(history.started, identity, component, tool)
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
                if isinstance(message.get("result"),dict):
                    result = message["result"]
                    if "tools" in result:
                        result["tools"].extend(application_tools())
                        if component=='autocad':result['tools'].append(recovery_tool())
                        line = (json.dumps(message,ensure_ascii=True)+"\n").encode("utf-8")
                    elif "serverInfo" in result:
                        if component=='autocad':result['instructions']=result.get('instructions','')+'\nThis Toolkit server supports AutoCAD and AutoCAD LT. Check application state and product first. AutoCAD LT supports 2D drafting through the LISP/file-IPC bridge; never promise full AutoCAD 3D solid, surface, .NET or external COM capabilities in LT. If multiple AutoCAD/LT instances are open, stop and request one unambiguous target. Do not ask the user to type connection commands. On RECOVERY_REQUIRED, CAD_CLOSED, or an unknown result, use get_recovery_state/open_application to assist recovery. Never automatically repeat the previous command, including after reconnect or user confirmation. Requests blocked during recovery were NOT queued. Ask the user to inspect and confirm the drawing in Toolkit, then explicitly submit new work. Audited read-only operations remain available during write recovery through the isolated native read inbox. Use these managed tools for inspection. NEVER bypass recovery by using external COM, shell, raw mailbox files, SendCommand or arbitrary LISP. A successful read does not release the write barrier. This policy covers Toolkit-managed access, not third-party CAD clients.'
                        result["instructions"] = result.get("instructions","")+"\nBefore CAD operations, use open_application and get_application_state to obtain a visible main window. Never launch CAD with hidden shell flags, and never start a second process while the first is starting. A process alone is not readiness. Check the MCP bridge after the window opens. Do not ask the user for APPLOAD or manual connection commands; use Toolkit's installation/repair flow when necessary."
                        line = (json.dumps(message,ensure_ascii=True)+"\n").encode("utf-8")
                if "id" in message:
                    with lock:
                        identity = pending.pop(json.dumps(message["id"]), None)
                    if identity:
                        outcome="failed" if tool_failed(message) else "succeeded"
                        if component=='autocad' and outcome=='failed' and 'RECOVERY_REQUIRED' in json.dumps(message):outcome='interrupted'
                        receipt(history.finished, identity, outcome)
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
