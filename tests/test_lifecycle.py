import itertools
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from common import atomic_json, download, extract_zip, read_json, sha256, within
from manager import COMPONENTS, SKILLS, ConfigEditor, Manager, mcp_env, plugin_files
from probe import Client

class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="CAD 測試 ")
        self.base = Path(self.temp.name)
        self.home = self.base / "Codex 設定"
        self.home.mkdir()
        self.env = patch.dict(os.environ, {"CODEX_HOME": str(self.home)})
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

class FileTests(Fixture):
    def test_atomic_replacement(self):
        file = self.base / "state.json"
        atomic_json(file, {"中文": 1}); atomic_json(file, {"中文": 2})
        self.assertEqual(read_json(file), {"中文": 2})
        self.assertFalse(file.with_suffix(".json.tmp").exists())

    def test_zip_traversal_rejected_before_extract(self):
        for entry in ("../escape.txt", "folder/../../escape.txt", "..\\escape.txt"):
            with self.subTest(entry=entry):
                archive = self.base / "bad.zip"
                with zipfile.ZipFile(archive, "w") as z: z.writestr("good.txt", "a"); z.writestr(entry, "bad")
                with self.assertRaises(ValueError): extract_zip(archive, self.base / "out")
                self.assertFalse((self.base / "out/good.txt").exists())

    def test_http_download_rejected(self):
        with self.assertRaises(ValueError): download("http://example.org/file", self.base / "file")

    def test_hash_failure_preserves_prior_file(self):
        import io
        dest = self.base / "file"
        dest.write_bytes(b"old")
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"corrupt")):
            with self.assertRaises(ValueError): download("https://example.org/file", dest, "0"*64)
        self.assertEqual(dest.read_bytes(), b"old")
        self.assertFalse(dest.with_suffix(".part").exists())

    def test_interrupted_download_preserves_prior_file(self):
        dest = self.base / "file"; dest.write_bytes(b"old")
        with patch("urllib.request.urlopen", side_effect=TimeoutError("offline")):
            with self.assertRaises(TimeoutError): download("https://example.org/file", dest, "0"*64)
        self.assertEqual(dest.read_bytes(), b"old")

class PluginTests(Fixture):
    def test_all_seven_component_combinations(self):
        for n in range(1, 4):
            for selected in itertools.combinations(COMPONENTS, n):
                with self.subTest(selected=selected):
                    dest = self.base / "Plugin 中文 空白"
                    commands = {c: [str(self.base / c / "python.exe"), "-m", c] for c in selected}
                    plugin_files(dest, ROOT / "plugins/cad-toolkit", commands, "0.1.0-preview.1", mcp_env(self.base))
                    actual = read_json(dest / "mcp.json")["mcpServers"]
                    self.assertEqual(set(actual), set(selected))
                    for c in selected: self.assertEqual(actual[c]["command"], commands[c][0])
                    expected = {s for s, req in SKILLS.items() if all(c in selected for c in req)}
                    self.assertEqual({p.name for p in (dest / "skills").iterdir()}, expected)
                    self.assertEqual(read_json(dest / "plugin.json")["version"], read_json(dest / ".codex-plugin/plugin.json")["version"])

class ConfigTests(Fixture):
    def setUp(self):
        super().setUp()
        self.file = self.home / "config.toml"
        self.file.write_text('# 保留註解\nmodel = "my-model"\n[mcp_servers.autocad-mcp]\ncommand = "old.exe"\n[mcp_servers.inventor]\ncommand = "old-inventor.exe"\nenabled = false\n[mcp_servers.other]\ncommand = "unrelated.exe"\n', encoding="utf-8")
        self.editor = ConfigEditor(self.home, self.base / "backups")

    def test_switch_and_restore_preserve_unrelated_and_comments(self):
        original = self.file.read_text(encoding="utf-8")
        prior = {}
        self.editor.set_policy({"autocad"}, prior)
        doc = self.editor.load()
        self.assertFalse(doc["mcp_servers"]["autocad-mcp"]["enabled"])
        self.assertTrue(doc["plugins"]["cad-toolkit@cad-toolkit-local"]["mcp_servers"]["autocad"]["enabled"])
        self.assertFalse(doc["plugins"]["cad-toolkit@cad-toolkit-local"]["mcp_servers"]["rhino"]["enabled"])
        self.editor.restore_originals(prior)
        after = self.editor.load()
        self.assertNotIn("enabled", after["mcp_servers"]["autocad-mcp"])
        self.assertFalse(after["mcp_servers"]["inventor"]["enabled"])
        self.assertEqual(after["mcp_servers"]["other"]["command"], "unrelated.exe")
        self.assertIn("# 保留註解", self.file.read_text(encoding="utf-8"))
        self.assertTrue(list((self.base / "backups").glob("*.toml")))

    def test_changed_user_entry_not_restored(self):
        prior = {}; self.editor.set_policy({"autocad"}, prior)
        doc = self.editor.load(); doc["mcp_servers"]["autocad-mcp"]["command"] = "user-change.exe"
        self.editor.save(doc); self.editor.restore_originals(prior)
        self.assertFalse(self.editor.load()["mcp_servers"]["autocad-mcp"]["enabled"])

    def test_repeated_switch_preserves_original_enabled_value(self):
        prior = {}; self.editor.set_policy({"autocad"}, prior); self.editor.set_policy({"autocad"}, prior)
        self.editor.restore_originals(prior)
        self.assertNotIn("enabled", self.editor.load()["mcp_servers"]["autocad-mcp"])

class LifecycleTests(Fixture):
    def test_corrupt_payload_never_changes_active_version(self):
        payload = self.base / "payload"; payload.mkdir()
        (payload / "x").write_text("bad")
        atomic_json(payload / "bundle.json", {"version": "0.1.0", "files": {"x": "0"*64}})
        m = Manager(self.base / "install")
        m.state["active"] = {"rhino": "previous"}; m.save()
        with self.assertRaises(ValueError): m.install(payload, ["rhino"])
        self.assertEqual(read_json(m.state_path)["active"], {"rhino": "previous"})

    def test_failed_diagnostic_blocks_activation(self):
        m = Manager(self.base / "install")
        m.state["candidate"] = {"path": "candidate", "selected": ["rhino"]}
        with patch.object(m, "diagnose", return_value={"rhino": {"bridge": False}}), patch.object(m, "register_plugin") as register:
            with self.assertRaises(RuntimeError): m.activate(["rhino"])
            register.assert_not_called()
        self.assertEqual(m.state["active"], {})

    def test_successful_activation_saves_previous(self):
        m = Manager(self.base / "install")
        m.state["active"] = {"inventor": "old"}
        m.state["candidate"] = {"path": "new", "selected": ["inventor"]}
        with patch.object(m, "diagnose", return_value={"inventor": {"bridge": True}}), patch.object(m, "register_plugin"):
            m.activate(["inventor"])
        self.assertEqual(m.state["active"], {"inventor": "new"})
        self.assertEqual(m.state["previous"], {"inventor": "old"})

    def test_registration_failure_preserves_active(self):
        m = Manager(self.base / "install")
        m.state["active"] = {"inventor": "old"}
        m.state["candidate"] = {"path": "new", "selected": ["inventor"]}
        with patch.object(m, "diagnose", return_value={"inventor": {"bridge": True}}), patch.object(m, "register_plugin", side_effect=[RuntimeError("fail"), None]):
            with self.assertRaises(RuntimeError): m.activate(["inventor"])
        self.assertEqual(m.state["active"], {"inventor": "old"})

    def test_running_rhino_blocks_rollback(self):
        m = Manager(self.base / "install")
        m.state.update(active={"rhino": "new"}, previous={"rhino": "old"})
        with patch("manager.processes", return_value=[{"pid": 1}]):
            with self.assertRaises(RuntimeError): m.rollback()
        self.assertEqual(m.state["active"], {"rhino": "new"})

    def test_rollback_restores_prior_mapping(self):
        m = Manager(self.base / "install")
        m.state.update(active={"inventor": "new"}, previous={"inventor": "old"})
        with patch.object(m, "register_plugin"), patch("manager.processes", return_value=[]): m.rollback()
        self.assertEqual(m.state["active"], {"inventor": "old"})

    def test_multi_instance_never_sends_cad_calls(self):
        from unittest.mock import MagicMock
        m = Manager(self.base / "install")
        target = self.base / "version"
        (target / "envs/rhino").mkdir(parents=True)
        m.state["candidate"] = {"path": str(target), "selected": ["rhino"]}
        fake = MagicMock(); fake.__enter__.return_value = fake
        fake.request.return_value = {"tools": [{"name": "describe_capabilities"}]}
        with patch("manager.Client", return_value=fake), patch("manager.processes", return_value=[{"pid": 1}, {"pid": 2}]):
            result = m.diagnose(["rhino"])
        fake.call.assert_not_called()
        self.assertFalse(result["rhino"]["bridge"])
        self.assertTrue(result["rhino"]["mcp"])

class ProtocolTests(Fixture):
    def test_wrapped_tool_error_is_not_success(self):
        with self.assertRaises(RuntimeError): Client.decode({"result": '{"error":"dispatcher not loaded"}'})
        with self.assertRaises(RuntimeError): Client.decode('{"ok": false, "error": "timeout"}')
        with self.assertRaises(RuntimeError): Client.decode("Error getting document summary: disconnected")

    def test_wrapped_status_is_decoded(self):
        self.assertEqual(Client.decode({"result": '{"ok":true,"payload":{"backend":"file_ipc"}}'})["payload"]["backend"], "file_ipc")

    def test_ndjson_initialize_list_and_close(self):
        server = self.base / "mock.py"
        server.write_text('import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n if "id" in r: print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":{"tools":[{"name":"read"}]}}),flush=True)\n')
        with Client([sys.executable, str(server)]) as client:
            client.initialize()
            self.assertEqual(client.request("tools/list")["tools"][0]["name"], "read")
        self.assertIsNotNone(client.p.poll())

if __name__ == "__main__": unittest.main()
