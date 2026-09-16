"""Optional read-only acceptance against an already loaded dispatcher, never loads LISP."""
import argparse
import json
import os
from pathlib import Path
import sys
import win32com.client
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from common import read_json
from probe import Client
parser = argparse.ArgumentParser()
parser.add_argument("--ipc", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()
app = win32com.client.GetActiveObject("AutoCAD.Application")
doc = app.ActiveDocument
before = {"path": doc.FullName, "dbmod": doc.GetVariable("DBMOD"), "cmdactive": doc.GetVariable("CMDACTIVE")}
if before["cmdactive"] != 0: raise RuntimeError("AutoCAD 有進行中的指令，不執行診斷")
target = read_json(Path(os.environ["LOCALAPPDATA"]) / "CadToolkit/state.json")["candidate"]["path"]
env = os.environ.copy()
env.update(AUTOCAD_MCP_BACKEND="file_ipc", AUTOCAD_MCP_IPC_DIR=args.ipc, AUTOCAD_MCP_IPC_TIMEOUT="8", PYTHONUTF8="1")
with Client([str(Path(target) / "envs/autocad/Scripts/python.exe"), "-m", "autocad_mcp"], env) as client:
    client.initialize()
    backend = client.call("system", {"operation": "status"})
    drawing = client.call("drawing", {"operation": "info"})
after = {"path": doc.FullName, "dbmod": doc.GetVariable("DBMOD"), "cmdactive": doc.GetVariable("CMDACTIVE")}
report = {"backend": backend, "drawing": drawing, "before": before, "after": after, "unchanged": before == after}
Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
if not report["unchanged"]: raise RuntimeError("文件狀態改變，請檢查報告")
