"""Exercise real Codex plugin commands in an isolated CODEX_HOME, without starting CAD tools."""
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / ".build/payload/engine/vendor"))
from common import read_json, run
from manager import Manager, find_codex
installed = Path(os.environ["LOCALAPPDATA"]) / "CadToolkit"
target = read_json(installed / "state.json")["candidate"]["path"]
test_root = ROOT / "test-results" / "Codex 中文 隔離"
os.environ["CODEX_HOME"] = str(test_root / "codex-home")
manager = Manager(test_root / "toolkit")
manager.register_plugin({"autocad": target, "inventor": target, "rhino": target}, target, set())
result = run([find_codex(), "plugin", "list", "--marketplace", "cad-toolkit-local", "--json"], timeout=90)
(test_root / "plugin-list.json").write_text(result, encoding="utf-8")
print(result[:6000])
