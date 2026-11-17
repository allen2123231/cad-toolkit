import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import types
import runpy
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import history
import runtime
from autocad_setup import install_bundle, remove_bundle, PRODUCT
from common import atomic_json
from manager import plugin_files, mcp_env, Manager
from relay import tool_failed
import rhino_instances


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="MCP Toolkit 中文 ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_relay_preserves_wire_and_records_errors_without_secrets(self):
        child = self.root / "mcp fixture.py"
        child.write_text("import sys,json\nfor line in sys.stdin:\n m=json.loads(line)\n if m.get('method')=='tools/call':\n  result={'isError':m['params']['name']=='fail','content':[{'type':'text','text':'secret-output'}]}\n  print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)\n", encoding="utf-8")
        calls = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": {"password": "secret-input"}}} for i, name in enumerate(("drawing", "fail"))]
        result = subprocess.run([sys.executable, str(ROOT / "engine/relay.py"), "--root", str(self.root), "--component", "autocad", "--", sys.executable, str(child)],
                                input="".join(json.dumps(m)+"\n" for m in calls), text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([m["id"] for m in responses], [0, 1])
        self.assertEqual(responses[0]["result"]["content"][0]["text"], "secret-output")
        rows = history.recent(self.root)
        self.assertEqual({r["tool"]: r["outcome"] for r in rows}, {"drawing": "succeeded", "fail": "failed"})
        self.assertNotIn("secret-", json.dumps(rows))
        self.assertTrue(all(r["duration_ms"] >= 0 for r in rows))

    def test_legacy_error_envelopes_are_not_recorded_as_success(self):
        for result in ({"isError": True}, {"structuredContent": {"result": '{"ok":false,"error":"busy"}'}}, {"content": [{"type": "text", "text": "Not connected to Inventor"}]}, {"structuredContent": None, "content": [{"type": "text", "text": '{"error":"busy"}'}]}):
            self.assertTrue(tool_failed({"result": result}), result)
        self.assertFalse(tool_failed({"result": {"content": [{"type": "text", "text": "Connected but no document open."}]}}))

    def test_history_durable_clear_and_retention(self):
        with patch("history.time.time", return_value=1):
            history.started(self.root, "old", "rhino", "old")
        history.started(self.root, "new", "rhino", "new")
        self.assertEqual([r["id"] for r in history.recent(self.root)], ["new"])
        history.finished(self.root, "new", "interrupted")
        self.assertEqual(history.recent(self.root)[0]["outcome"], "interrupted")
        history.clear(self.root)
        self.assertEqual(history.recent(self.root), [])

    def test_owned_bundle_installs_per_document_and_preserves_foreign_files(self):
        target = self.root / "target"
        (target / "autocad").mkdir(parents=True)
        (target / "autocad/mcp_dispatch.lsp").write_text('(setq *mcp-ipc-dir* "C:/中文/ipc/")', encoding="utf-8")
        atomic_json(target / "ready.json", {"version": "0.3.0-preview.1"})
        result = install_bundle(target, self.root / "appdata")
        bundle = Path(result["bundle"])
        xml = ET.parse(bundle / "PackageContents.xml").getroot()
        self.assertEqual(xml.get("ProductCode"), PRODUCT)
        self.assertEqual(xml.find("Components/ComponentEntry").get("PerDocument"), "True")
        self.assertEqual((bundle / "Contents/mcp_dispatch.lsp").read_text(encoding="utf-8"), (target / "autocad/mcp_dispatch.lsp").read_text(encoding="utf-8"))
        install_bundle(target, self.root / "appdata")
        remove_bundle(target, self.root / "appdata")
        self.assertFalse(bundle.exists())
        bundle.mkdir(parents=True)
        (bundle / "PackageContents.xml").write_text('<ApplicationPackage ProductCode="foreign"/>')
        with self.assertRaises(ValueError):
            install_bundle(target, self.root / "appdata")
        remove_bundle(target, self.root / "appdata")
        self.assertTrue(bundle.exists())

    def test_generated_managed_plugin_uses_transparent_history_relay(self):
        dest = self.root / "plugin"
        child = str(self.root / "rhino/Scripts/rhinomcp.exe")
        plugin_files(dest, ROOT / "plugins/cad-toolkit", {"rhino": [child]}, "test", mcp_env(self.root), history_root=self.root)
        server = json.loads((dest / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["rhino"]
        self.assertEqual(Path(server["command"]).name, "python.exe")
        self.assertEqual(server["args"][-2:], ["--", child])
        self.assertTrue((dest / "tools/relay.py").exists())

    def test_external_and_managed_configuration_are_distinguished(self):
        config = self.root / "config.toml"
        config.write_text('[mcp_servers.inventor]\ncommand="C:/Python/python.exe"\nargs=["-m","src.server"]\ncwd="C:/inventor"\n', encoding="utf-8")
        source = runtime.discover(self.root, config)["inventor"]
        self.assertFalse(source["managed"])
        self.assertTrue(source["enabled"])
        atomic_json(self.root / "state.json", {"active": {"inventor": "C:/managed"}})
        config.write_text('[plugins."cad-toolkit@cad-toolkit-local".mcp_servers.inventor]\nenabled=false\n')
        source = runtime.discover(self.root, config)["inventor"]
        self.assertTrue(source["managed"])
        self.assertFalse(source["enabled"])

    def test_cad_closed_or_multiple_never_calls_a_bridge_or_launches_cad(self):
        source = {"python": sys.executable, "command": [sys.executable], "enabled": True}
        with patch("runtime.version", return_value="0.1.0"), patch("runtime.native") as native, patch("runtime.probe") as probe:
            self.assertEqual(runtime.row("inventor", source, [], self.root, {}, {})["code"], "CAD_NOT_RUNNING")
            self.assertEqual(runtime.row("inventor", source, [10, 11], self.root, {}, {}, frames=[{"kind":"inventor","pid":10,"hwnd":123},{"kind":"inventor","pid":11,"hwnd":124}])["code"], "SELECT_TARGET")
            native.assert_not_called(); probe.assert_not_called()

    def test_inventor_home_is_usable_and_version_is_not_claimed_latest(self):
        source = {"python": sys.executable, "enabled": True}
        with patch("runtime.version", return_value="0.1.0"), patch("runtime.native", return_value={"ready": True, "hwnd": 123, "version": "2027.1", "document": None}):
            row = runtime.row("inventor", source, [10], self.root, {"components": {"inventor": {"package_version": "0.1.0"}}}, {}, frames=[{"kind":"inventor","pid":10,"hwnd":123,"processStart":1}])
        self.assertEqual(row["code"], "READY")
        self.assertEqual(row["update"], "compatible")
        self.assertIsNone(row["document"])

    def test_inventor_adapter_attaches_lazily_without_starting_a_process(self):
        class Original:
            _app = None
        server = types.SimpleNamespace(inv=Original())
        app = types.SimpleNamespace(SoftwareVersion=types.SimpleNamespace(DisplayVersion="2027.1"))
        client = types.SimpleNamespace(GetActiveObject=lambda name: app)
        modules = {"pythoncom": types.SimpleNamespace(CoInitialize=lambda: None), "win32com": types.SimpleNamespace(client=client),
                   "win32com.client": client, "src": types.SimpleNamespace(server=server)}
        with patch.dict(sys.modules, modules):
            runpy.run_path(str(ROOT / "engine/inventor_session.py"))
            self.assertIsNone(server.inv._app, "MCP startup must not touch CAD")
            self.assertEqual(server.inv.app, app)
            self.assertTrue(server.inv.is_connected())
            server.inv._app = None
            with patch.object(client, 'GetActiveObject', side_effect=RuntimeError('No running Inventor')):
                self.assertFalse(server.inv.is_connected())
                with self.assertRaisesRegex(RuntimeError, '開啟 Inventor'):
                    server.inv.connect()

    def test_rhino_pid_reuse_and_ambiguous_targets_are_rejected(self):
        folder = self.root / 'RhinoMCP/instances';folder.mkdir(parents=True)
        instance = {'pid': 42, 'host': '127.0.0.1', 'port': 2000, 'processStart': '2026-11-16T00:00:00Z'}
        atomic_json(folder / '42.json', instance)
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}), patch('rhino_instances.process_start', return_value=1794787200.0):
            self.assertEqual(rhino_instances.collect([42]), [instance])
            self.assertEqual(rhino_instances.collect([42, 43]), [instance])
            with patch('rhino_instances.process_start', return_value=1794787300.0):
                self.assertEqual(rhino_instances.collect([42]), [])

    def test_new_setup_queues_only_successfully_configured_components(self):
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'codex')}):
            manager = Manager(self.root / 'toolkit')
        with patch.object(manager, 'install'), patch.object(manager, 'configure_plugin'), patch.object(manager, 'configure_autocad'), patch.object(manager, 'configure_rhino', side_effect=RuntimeError('Rhino missing')):
            manager.setup(self.root, ['rhino', 'autocad', 'inventor'])
        self.assertEqual(manager.state['auto_enable_pending'], ['autocad', 'inventor'])
        self.assertEqual(manager.state['active'], {})

    def test_windows_product_version_matches_the_install_manifest(self):
        project = ET.parse(ROOT / 'installer/CadToolkitSetup.csproj').getroot()
        source = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(project.find('PropertyGroup/Version').text, source['version'])


if __name__ == "__main__":
    unittest.main()
