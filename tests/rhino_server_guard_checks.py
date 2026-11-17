"""Run with the packaged Rhino Python environment, not the installer environment."""
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from rhinomcp.server import RhinoConnection, RhinoError


class GuardChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.guard=Path(self.temp.name)/"guard.json"
        self.guard.write_text(json.dumps({"protocol":1,"instance_id":"a"*32,"hwnd":1,"document_serial":1,"document_epoch":0}),encoding="utf-8")
        self.env=patch.dict(os.environ,{"RHINO_MCP_GUARD_FILE":str(self.guard)});self.env.start()

    def tearDown(self):
        self.env.stop();self.temp.cleanup()

    def test_unreadable_capabilities_never_fall_back_to_mutation(self):
        c=RhinoConnection("127.0.0.1",1)
        with patch.object(c,"_plugin_capabilities",return_value=None),patch.object(c,"_send_command_once") as sent:
            with self.assertRaises(RhinoError):c.send_command("create_object",{"type":"POINT","params":{"x":0,"y":0,"z":0}})
            sent.assert_not_called()

    def test_legacy_response_can_only_receive_readonly_capability_probe(self):
        c=RhinoConnection("127.0.0.1",1);sock=Mock();c.sock=sock
        response=json.dumps({"status":"success","result":{"version":"0.5.2","commands":[{"name":"create_object"}]}}).encode()
        wire=bytearray(len(response).to_bytes(4,"big")+response)
        def recv(n):
            chunk=bytes(wire[:n]);del wire[:n];return chunk
        sock.recv.side_effect=recv
        with self.assertRaises(RhinoError):c.send_command("create_object",{"type":"POINT","params":{"x":0,"y":0,"z":0}})
        commands=[json.loads(call.args[0][4:])["type"] for call in sock.sendall.call_args_list]
        self.assertEqual(commands,["describe_capabilities"])

    def test_missing_guard_never_sends_a_command(self):
        c=RhinoConnection("127.0.0.1",1);sock=Mock();c.sock=sock;self.guard.unlink()
        with self.assertRaises(RhinoError):c._send_command_once("create_object",{})
        sock.sendall.assert_not_called()

    def test_timeout_marks_unknown_outcome_and_does_not_retry_mutation(self):
        c=RhinoConnection("127.0.0.1",1);sock=Mock();c.sock=sock
        c._capabilities={"version":"0.5.3","toolkit_guard_protocol":1,"commands":[{"name":"create_object","read_only":False}]}
        sock.recv.side_effect=socket.timeout()
        with self.assertRaises(Exception):c.send_command("create_object",{"type":"POINT","params":{"x":0,"y":0,"z":0}})
        self.assertEqual(sock.sendall.call_count,1)
        self.assertTrue(Path(str(self.guard)+".uncertain").is_file())


if __name__=="__main__":unittest.main()
