import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from autocad_channel import Channel, atomic, lease


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.frame = dict(kind='autocad', pid=123, hwnd=42, processStart=time.time()-60)
        self.frames = [self.frame]
        self.doc = dict(id='document-one', name='未命名.dwg', path='', busy=False)
        self.posts = []
        self.channel = Channel(self.root, lambda: self.frames, lambda f: dict(document=dict(self.doc), guard_protocol=3))

    async def asyncTearDown(self):
        self.temp.cleanup()

    def post(self, request):
        self.posts.append(request)

    async def test_closed_cad_interrupts_and_does_not_replay_after_reopen(self):
        def close(request):
            self.post(request)
            self.frames = []
        result = await self.channel.dispatch('execute-lisp', {'code_file': 'private.lsp'}, close, timeout=.1)
        self.assertEqual(result['code'], 'RECOVERY_REQUIRED')
        self.assertFalse(list((self.root/'ipc').glob('autocad_mcp_cmd_*.json')))
        self.frames = [{**self.frame, 'pid': 124, 'processStart': time.time()+1}]
        self.doc['id'] = 'document-two'
        result = await self.channel.dispatch('create-circle', {}, self.post, timeout=.1)
        self.assertEqual(result['code'], 'RECOVERY_REQUIRED')
        self.assertEqual(len(self.posts), 1)
        state = self.channel.state()
        self.assertTrue(state['can_confirm'])
        self.channel.confirm(state['recovery']['request_id'], state['target_token'])
        self.assertEqual(len(self.posts), 1, 'confirmation must never replay')
        def finish(request):
            self.post(request)
            atomic(self.root/'ipc'/f"autocad_mcp_result_{request['request_id']}.json", {'request_id':request['request_id'],'ok':True,'payload':{'count':1}})
        self.assertTrue((await self.channel.dispatch('create-circle', {}, finish, timeout=.1))['ok'])
        self.assertEqual(len(self.posts), 2)

    async def test_timeout_in_live_process_requires_reopen_not_just_confirmation(self):
        result = await self.channel.dispatch('create-circle', {}, self.post, timeout=.01)
        self.assertEqual(result['code'], 'RECOVERY_REQUIRED')
        state = Channel(self.root, lambda: self.frames, self.channel.context).state()
        self.assertFalse(state['can_confirm'])
        with self.assertRaises(ValueError):
            self.channel.confirm(state['recovery']['request_id'], state['target_token'])
        self.assertEqual(len(self.posts), 1)

    async def test_confirmation_fences_document_switch_and_busy(self):
        await self.channel.dispatch('create-circle', {}, self.post, timeout=.01)
        self.frames = [{**self.frame, 'processStart': time.time()+1}]
        old = self.channel.state()
        self.doc['id'] = 'changed'
        with self.assertRaises(ValueError): self.channel.confirm(old['recovery']['request_id'], old['target_token'])
        now = self.channel.state()
        self.doc['busy'] = True
        with self.assertRaises(ValueError): self.channel.confirm(now['recovery']['request_id'], now['target_token'])

    async def test_matching_late_receipt_retained_but_does_not_auto_clear_recovery(self):
        await self.channel.dispatch('create-circle', {}, self.post, timeout=.01)
        request = self.posts[0]
        atomic(self.root/'ipc'/f"autocad_mcp_result_{request['request_id']}.json", {'request_id':request['request_id'],'ok':True})
        state = self.channel.state()
        self.assertTrue(state['recovery']['completion_received'])
        self.assertEqual((await self.channel.dispatch('create-circle', {}, self.post, timeout=.01))['code'], 'RECOVERY_REQUIRED')

    async def test_unknown_legacy_mutation_is_never_auto_cleared(self):
        atomic(self.root/'ipc/pcad-pending.json', {'request_id':'legacy','command':'execute-lisp','params':{},'ts':50})
        self.assertEqual((await self.channel.dispatch('create-circle', {}, self.post, timeout=.01))['code'], 'RECOVERY_REQUIRED')
        self.assertEqual(self.posts, [])

    async def test_dead_readonly_ping_can_be_archived_without_replay(self):
        atomic(self.root/'ipc/pcad-pending.json', {'request_id':'legacy','command':'ping','params':{},'ts':50})
        state = self.channel.state()
        self.assertIsNone(state['recovery'])
        self.assertFalse((self.root/'ipc/pcad-pending.json').exists())
        self.assertEqual(self.posts, [])

    async def test_live_lease_and_wrong_native_protocol_fail_closed(self):
        with lease(self.root/'ipc'):
            self.assertEqual((await self.channel.dispatch('ping', {}, self.post, timeout=.01))['code'], 'DESKTOP_BUSY_OTHER_CLIENT')
        self.channel.context = lambda f: dict(guard_protocol=1, document=self.doc)
        self.assertEqual((await self.channel.dispatch('create-circle', {}, self.post, timeout=.01))['code'], 'BRIDGE_UPDATE_REQUIRED')
        self.assertEqual(self.posts, [])

    async def test_no_context_and_ambiguous_target_do_not_post(self):
        self.frames += [{**self.frame, 'pid': 124}]
        self.assertEqual((await self.channel.dispatch('create-circle', {}, self.post, timeout=.01))['code'], 'SELECT_TARGET')
        self.frames=[]
        self.assertEqual((await self.channel.dispatch('create-circle', {}, self.post, timeout=.01))['code'], 'CAD_CLOSED')
        self.assertEqual(self.posts, [])

    async def test_blocked_notification_does_not_block_timeout_or_next_request(self):
        release=threading.Event()
        def wedged(request):
            self.post(request)
            release.wait(3)
        try:
            started=time.monotonic()
            result=await self.channel.dispatch('create-circle',{},wedged,timeout=.02)
            self.assertEqual(result['code'],'RECOVERY_REQUIRED')
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual((await self.channel.dispatch('create-circle',{},self.post,.02))['code'],'RECOVERY_REQUIRED')
            self.assertEqual(len(self.posts),1)
        finally:release.set()

    async def test_notification_failure_preserves_uncertainty(self):
        def denied(request):raise OSError('PostMessage denied')
        with self.assertRaises(OSError):await self.channel.dispatch('create-circle',{},denied,.2)
        self.assertEqual(self.channel.state()['recovery']['stage'],'unknown')
        self.assertFalse(self.channel.state()['can_confirm'])

    async def test_native_unfinished_prompt_is_unknown_not_completed(self):
        def prompt(request):
            atomic(self.root/'ipc'/f"toolkit-receipt-{request['request_id']}.json",dict(request_id=request['request_id'],phase='waiting_input'))
        started=time.monotonic()
        result=await self.channel.dispatch('execute-lisp',{},prompt,timeout=5)
        self.assertEqual(result['code'],'RECOVERY_REQUIRED')
        self.assertLess(time.monotonic()-started,1)
        self.assertEqual(self.channel.state()['recovery']['reason'],'native_waiting_for_input')

    async def test_native_rejection_is_completed_and_does_not_create_recovery(self):
        def reject(request):
            atomic(self.root/'ipc'/f"autocad_mcp_result_{request['request_id']}.json",dict(request_id=request['request_id'],ok=False,error='TARGET_DOCUMENT_CHANGED_NOT_EXECUTED'))
        result=await self.channel.dispatch('create-circle',{},reject,.3)
        self.assertFalse(result['ok'])
        self.assertIsNone(self.channel.state()['recovery'])
        self.assertFalse(self.channel.pending.exists())

    async def test_busy_and_modal_context_never_get_notification(self):
        self.doc['busy']=True
        self.assertEqual((await self.channel.dispatch('create-circle',{},self.post,.01))['code'],'CAD_BUSY')
        self.doc['busy']=False
        self.channel.context=lambda f:dict(guard_protocol=3,document=self.doc,modal=True)
        self.assertEqual((await self.channel.dispatch('create-circle',{},self.post,.01))['code'],'CAD_BUSY')
        self.assertEqual(self.posts,[])

    async def test_orphan_runnable_mail_is_not_executed_with_new_batch(self):
        atomic(self.root/'ipc/autocad_mcp_cmd_orphan.json',dict(request_id='orphan',command='create-circle',params={},ts=50))
        self.assertEqual((await self.channel.dispatch('create-circle',{},self.post,.01))['code'],'RECOVERY_REQUIRED')
        self.assertEqual(self.posts,[])

    async def test_malformed_evidence_fails_closed(self):
        self.channel.ipc.mkdir();self.channel.pending.write_text('{broken')
        with self.assertRaises(ValueError):await self.channel.dispatch('create-circle',{},self.post,.01)
        self.assertEqual(self.posts,[])
        self.assertEqual(self.channel.pending.read_text(),'{broken')

    async def test_native_phase_visible_while_other_client_owns_lease(self):
        started=threading.Event();release=threading.Event()
        def post(request):
            self.post(request)
            atomic(self.root/'ipc'/f"toolkit-receipt-{request['request_id']}.json",dict(request_id=request['request_id'],phase='executing'))
            started.set();release.wait(2)
        work=asyncio.create_task(self.channel.dispatch('create-circle',{},post,.5))
        try:
            while not started.is_set():await asyncio.sleep(.01)
            state=self.channel.state()
            self.assertEqual(state['active']['native_phase'],'executing')
            other=await self.channel.dispatch('create-circle',{},self.post,.01)
            self.assertEqual(other['code'],'DESKTOP_BUSY_OTHER_CLIENT')
            self.assertEqual(len(self.posts),1)
            await work
        finally:release.set()

    async def test_killed_mcp_process_releases_os_lock_but_keeps_recovery(self):
        script=self.root/'worker.py'
        script.write_text('''import sys,asyncio,time,json
sys.path.insert(0,sys.argv[1])
from autocad_channel import Channel
frame=json.loads(sys.argv[3])
channel=Channel(sys.argv[2],lambda:[frame],lambda f:dict(guard_protocol=3,document=dict(id="doc",busy=False)))
asyncio.run(channel.dispatch("create-circle",{},lambda r:time.sleep(60),60))
''')
        child=subprocess.Popen([sys._base_executable,str(script),str(Path(__file__).resolve().parents[1]/'engine'),str(self.root),json.dumps(self.frame)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not self.channel.pending.exists() and time.monotonic()<deadline:await asyncio.sleep(.02)
            self.assertTrue(self.channel.pending.exists())
            child.terminate();child.wait(5)
            state=self.channel.state()
            self.assertEqual(state['recovery']['command'],'create-circle')
            self.assertFalse(state['can_confirm'])
            self.frames=[{**self.frame,'processStart':time.time()+1}]
            self.assertTrue(self.channel.state()['can_confirm'])
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stderr.close()

    async def test_existing_other_cad_cannot_pose_as_reopened_target(self):
        await self.channel.dispatch('create-circle',{},self.post,timeout=.01)
        self.frames=[{**self.frame,'pid':124,'processStart':time.time()-30}]
        state=self.channel.state()
        self.assertTrue(state['recovery']['closed_observed'])
        self.assertFalse(state['can_confirm'])

    @unittest.skipUnless(os.name=='nt','Windows process object regression')
    async def test_terminated_cad_identity_is_dead_even_while_popen_retains_handle(self):
        from autocad_channel import local_channel
        from rhino_instances import process_start
        child=subprocess.Popen([sys._base_executable,'-c','import time;time.sleep(30)'])
        try:
            frame=dict(pid=child.pid,hwnd=42,processStart=process_start(child.pid))
            channel=local_channel(self.root)
            self.assertTrue(channel.alive(frame))
            child.terminate();child.wait(5)
            self.assertFalse(channel.alive(frame))
        finally:
            if child.poll() is None:child.kill();child.wait()


if __name__ == '__main__': unittest.main()
