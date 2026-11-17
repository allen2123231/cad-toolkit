import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from window_store import Store, window_lock
from rhino_router import Router
from window_scan import main_frame
import history


def window(number=1, **changes):
    return {"kind": "rhino", "pid": number, "hwnd": number*10, "processStart": 1000.0+number,
            "instance_id": str(number)*32, "host": "127.0.0.1", "port": 1998+number,
            "guard_protocol": 1, "document_serial": number, "document_epoch": 0,
            "document": "同名未儲存文件", **changes}


class WindowBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="MCP 視窗 ")
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.native = [window(), window(2)]
        self.windows = self.store.sync(self.native)

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, number=0):
        request = self.store.request()
        return self.store.bind(request["request_id"], self.windows[number]["window_id"])

    def test_names_survive_toolkit_restart_and_document_rename(self):
        self.store.rename(self.windows[0]["window_id"], "造型工作台")
        self.native[0].update(document="另存新檔.3dm", documentPath="C:/new.3dm")
        windows = Store(self.root).sync(self.native)
        self.assertEqual(next(w for w in windows if w["pid"] == 1)["display_name"], "造型工作台")
        self.assertEqual({w["window_id"] for w in windows}, {w["window_id"] for w in self.windows})
        with self.assertRaisesRegex(ValueError, "已有"):
            self.store.rename(self.windows[1]["window_id"], "造型工作台")

    def test_native_dialogs_and_internal_helpers_are_not_main_windows(self):
        self.assertTrue(main_frame("inventor","AfxMDIFrame140u"))
        self.assertTrue(main_frame("autocad","AfxMDIFrame140u"))
        self.assertTrue(main_frame("rhino","Afx:0001:8:0003:0000"))
        self.assertFalse(main_frame("rhino","Afx:0001:0:0003:0000"))
        self.assertFalse(main_frame("inventor","Afx:0001:0"))
        self.assertFalse(main_frame("autocad","#32770"))

    def test_restarted_process_cannot_inherit_binding_even_when_port_pid_and_name_reused(self):
        old = self.bind()
        self.store.sync([window(processStart=5000, instance_id="new-instance"), self.native[1]])
        with self.assertRaises(ValueError): self.store.binding(old["id"])
        self.assertEqual(self.store.request_status(old["request_id"])["state"], "disconnected")

    def test_same_process_different_native_frames_have_separate_names(self):
        windows = self.store.sync([window(kind="autocad", guard_protocol=0), window(kind="autocad", hwnd=11, guard_protocol=0)])
        self.assertEqual(len(windows), 2)
        self.assertEqual({w["display_name"] for w in windows}, {"AutoCAD 01", "AutoCAD 02"})

    def test_simultaneous_claim_is_exclusive_across_store_instances(self):
        requests = [self.store.request()["request_id"] for _ in range(8)]
        def claim(request):
            try: return Store(self.root).bind(request, self.windows[0]["window_id"])["id"]
            except ValueError: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            answers = list(pool.map(claim, requests))
        self.assertEqual(sum(a is not None for a in answers), 1)

    def test_cancel_expiry_legacy_plugin_and_failed_transfer_do_not_steal_window(self):
        old = self.bind()
        cancelled = self.store.request()["request_id"]; self.store.cancel(cancelled)
        with self.assertRaises(ValueError): self.store.bind(cancelled, old["window_id"], old["id"])
        self.assertEqual(self.store.binding(old["id"])["id"], old["id"])
        req = self.store.request()["request_id"]
        with self.store.db() as db: db.execute("UPDATE requests SET created=0 WHERE id=?", (req,))
        self.assertEqual(self.store.request_status(req)["state"], "expired")
        self.store.sync([window(guard_protocol=0)])
        with self.assertRaisesRegex(ValueError, "更新"):
            self.store.bind(self.store.request()["request_id"], self.store.windows()[0]["window_id"])

    def test_transfer_revokes_old_handle_atomically(self):
        old = self.bind()
        request = self.store.request()["request_id"]
        new = self.store.bind(request, old["window_id"], old["id"])
        with self.assertRaises(ValueError): self.store.binding(old["id"])
        self.assertEqual(self.store.binding(new["id"])["window_id"], old["window_id"])

    def test_switch_away_and_back_requires_confirmation_and_stale_status_cannot_undo_it(self):
        binding = self.bind()
        changed = {"document_serial": 1, "document_epoch": 2, "document": "同名未儲存文件"}
        self.store.observe(binding["id"], changed)
        self.store.observe(binding["id"], {**changed, "document_epoch": 0})
        self.assertEqual(json.loads(self.store.binding(binding["id"])["pending"])["document_epoch"], 2)
        with self.assertRaises(ValueError): self.store.confirm(binding["id"], 1, 1)
        self.store.confirm(binding["id"], 1, 2)
        self.assertIsNone(self.store.binding(binding["id"])["pending"])
        self.assertEqual(self.store.binding(binding["id"])["document_epoch"], 2)

    def test_os_lock_releases_on_process_death(self):
        script = "import sys,time;from window_store import window_lock\nwith window_lock(sys.argv[1],'abc'):\n print('locked',flush=True);time.sleep(60)\n"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "engine")}
        p = subprocess.Popen([sys.executable, "-c", script, str(self.root)], env=env, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(), "locked")
            with self.assertRaises(TimeoutError):
                with window_lock(self.root, "abc", timeout=.1): pass
            p.kill(); p.wait()
            with window_lock(self.root, "abc", timeout=.5): pass
        finally:
            if p.poll() is None: p.kill(); p.wait()
            p.stdout.close()


FIXTURE = '''import json,sys,os,time
from pathlib import Path
for line in sys.stdin:
 m=json.loads(line);method=m.get('method');params=m.get('params') or {};answer={}
 if 'id' not in m:continue
 if method=='initialize':answer={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
 elif method=='tools/list':answer={'tools':[{'name':'create_object','inputSchema':{'type':'object','properties':{'secret':{'type':'string'}},'required':[]}}]}
 elif method=='tools/call':
  guard=json.loads(Path(os.environ['RHINO_MCP_GUARD_FILE']).read_text());port=os.environ['RHINO_MCP_PORT']
  native=json.loads((Path(os.environ['FIXTURE_ROOT'])/(port+'.json')).read_text())
  Path(os.environ['RHINO_MCP_GUARD_FILE']+'.observed').write_text(json.dumps(native))
  bad=(guard['document_serial'],guard['document_epoch'],guard['instance_id'])!=(native['document_serial'],native['document_epoch'],native['instance_id'])
  if not bad:
   time.sleep(.15)
   with (Path(os.environ['FIXTURE_ROOT'])/(port+'.commands')).open('a') as f:f.write('created\\n')
  answer={'isError':bad,'content':[{'type':'text','text':json.dumps({'port':port,'blocked':bad})}]}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':answer}),flush=True)
'''


class RoutingIntegrationTests(unittest.TestCase):
    bind = WindowBindingTests.bind
    def setUp(self):
        WindowBindingTests.setUp(self)
        self.script = self.root / "server fixture.py"; self.script.write_text(FIXTURE, encoding="utf-8")
        for w in self.native: (self.root / f'{w["port"]}.json').write_text(json.dumps(w), encoding="utf-8")
        self.router = Router(self.root, [sys.executable, str(self.script)], env={"FIXTURE_ROOT": str(self.root)})
        self.scan_patch = patch("window_scan.scan", side_effect=lambda: self.native);self.scan_patch.start()

    def tearDown(self):
        self.scan_patch.stop();self.router.close();WindowBindingTests.tearDown(self)

    def test_one_mcp_router_routes_two_conversations_independently(self):
        a,b=self.bind(0),self.bind(1)
        schema=self.router.request("tools/list",{})["tools"]
        self.assertIn("binding_id",schema[0]["inputSchema"]["required"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            calls=[pool.submit(self.router.request,"tools/call",{"name":"create_object","arguments":{"binding_id":x["id"],"secret":"do-not-log"}}) for x in (a,b)]
            answers=[f.result() for f in calls]
        self.assertTrue(all(not x["isError"] for x in answers))
        self.assertEqual({json.loads(x["content"][0]["text"])["port"] for x in answers},{"1999","2000"})
        self.assertEqual((self.root/"1999.commands").read_text(),"created\n")
        self.assertEqual((self.root/"2000.commands").read_text(),"created\n")
        self.assertEqual({r["binding_id"] for r in history.recent(self.root)},{a["id"],b["id"]})
        self.assertNotIn(b"do-not-log",(self.root/"history.sqlite3").read_bytes())

    def test_bounded_selection_wait_resumes_without_another_user_message(self):
        req=self.store.request()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            waiting=pool.submit(self.router.request,"tools/call",{"name":"get_window_binding","arguments":{"request_id":req["request_id"],"wait_seconds":2}})
            time.sleep(.05)
            binding=self.store.bind(req["request_id"],self.windows[0]["window_id"])
            answer=waiting.result(timeout=3)
        self.assertEqual(json.loads(answer["content"][0]["text"])["binding_id"],binding["id"])

    def test_request_starts_rhino_before_waiting_for_a_window(self):
        starter=Mock(return_value={'state':'starting','message':'正在開啟 Rhino'})
        with patch('rhino_router.wake_ui'),patch('rhino_router.ensure_started',starter,create=True):
            answer=self.router.request('tools/call',{'name':'request_window_binding','arguments':{}})
        starter.assert_called_once_with(self.root,'rhino')
        self.assertEqual(json.loads(answer['content'][0]['text'])['application']['state'],'starting')

    def test_missing_stale_and_released_handles_never_execute(self):
        a=self.bind()
        missing=self.router.request("tools/call",{"name":"create_object","arguments":{}})
        self.assertTrue(missing["isError"])
        self.store.release(a["id"])
        stale=self.router.request("tools/call",{"name":"create_object","arguments":{"binding_id":a["id"]}})
        self.assertTrue(stale["isError"]);self.assertFalse((self.root/"1999.commands").exists())
        cli=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/"engine/runtime.py"),"rename-window","--root",str(self.root),"--window-id","gone","--name","test"],capture_output=True,text=True,encoding="utf-8",timeout=15)
        self.assertEqual(cli.returncode,2)
        self.assertIn("error",json.loads(cli.stdout))
        self.assertNotIn("Traceback",cli.stdout+cli.stderr)

    def test_native_change_blocks_until_explicit_confirmation_without_replay(self):
        a=self.bind()
        changed={**self.native[0],"document_serial":22,"document_epoch":1}
        (self.root/"1999.json").write_text(json.dumps(changed),encoding="utf-8")
        call={"name":"create_object","arguments":{"binding_id":a["id"]}}
        self.assertTrue(self.router.request("tools/call",call)["isError"])
        self.assertFalse((self.root/"1999.commands").exists())
        self.store.confirm(a["id"],22,1)
        self.assertFalse((self.root/"1999.commands").exists(),"Confirmation must not replay the blocked command")
        self.assertFalse(self.router.request("tools/call",call)["isError"])

    def test_transfer_waits_for_inflight_then_old_queued_calls_are_rejected(self):
        a=self.bind()
        call={"name":"create_object","arguments":{"binding_id":a["id"]}}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            running=pool.submit(self.router.request,"tools/call",call)
            deadline=time.monotonic()+3
            while not self.store.binding(a["id"])["busy"] and time.monotonic()<deadline:time.sleep(.01)
            request=self.store.request()["request_id"]
            with window_lock(self.root,a["window_id"]):
                new=self.store.bind(request,a["window_id"],a["id"])
            self.assertFalse(running.result()["isError"])
        self.assertTrue(self.router.request("tools/call",call)["isError"])
        self.assertFalse(self.router.request("tools/call",{"name":"create_object","arguments":{"binding_id":new["id"]}})["isError"])

    def test_unknown_command_outcome_cannot_be_replayed_or_transferred(self):
        a=self.bind()
        with patch.object(self.router,"worker",side_effect=TimeoutError("unknown outcome")):
            answer=self.router.request("tools/call",{"name":"create_object","arguments":{"binding_id":a["id"]}})
        self.assertTrue(answer["isError"])
        self.assertEqual(self.store.binding(a["id"])["busy"],-1)
        with self.assertRaisesRegex(ValueError,"未確認"):
            self.store.bind(self.store.request()["request_id"],a["window_id"],a["id"])
        self.assertTrue(self.router.request("tools/call",{"name":"create_object","arguments":{"binding_id":a["id"]}})["isError"])
        self.assertFalse((self.root/"1999.commands").exists())
        other=self.bind(1)
        worker=Mock()
        def uncertain_response(*args,**kwargs):
            Path(str(self.router.guard_file(other['id']))+'.uncertain').write_text('unknown')
            return {'isError':True,'content':[{'type':'text','text':'Timeout; run mcpstart and retry'}]}
        worker.request.side_effect=uncertain_response
        with patch.object(self.router,'worker',return_value=worker):
            answer=self.router.request('tools/call',{'name':'create_object','arguments':{'binding_id':other['id']}})
        self.assertNotIn('mcpstart',json.dumps(answer).lower())
        self.assertEqual(self.store.binding(other['id'])['busy'],-1)


if __name__ == "__main__": unittest.main()
