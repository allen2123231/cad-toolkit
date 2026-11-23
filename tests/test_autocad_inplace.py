"""Same-process recovery requires a fresh native fence, never merely an idle flag."""
import json
from pathlib import Path
import sys,tempfile,time,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from autocad_channel import Channel,atomic

class InPlaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.frame=dict(kind='autocad',pid=123,hwnd=42,processStart=time.time()-60)
        self.doc=dict(id='doc',busy=False,switch_serial=1)
        self.channel=Channel(self.root,lambda:[self.frame],lambda f:dict(guard_protocol=4,document=dict(self.doc)))
        self.record=dict(request_id='old',command='create-circle',document=dict(self.doc),frame={k:self.frame[k] for k in ('pid','hwnd','processStart')},ts=time.time(),stage='unknown')
        atomic(self.channel.recovery,self.record)
        atomic(self.channel.pending,dict(request_id='old',command='create-circle'))
        atomic(self.channel.ipc/'autocad_mcp_cmd_old.json',dict(request_id='old',command='create-circle'))
    def native(self,r):
        self.assertEqual(r['access'],'recover')
        atomic(self.channel.ipc/'toolkit-revoked-old.json',dict(request_id='old',probe_id=r['request_id']))
        atomic(self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json",dict(request_id=r['request_id'],ok=True,payload=dict(fenced_request_id='old',document_id='doc',probe_id=r['request_id'])))
    async def prepare(self,post=None):
        s=self.channel.state()
        return await self.channel.prepare_recovery('old',s['target_token'],post or self.native,.2)
    async def test_same_process_can_confirm_only_after_native_fence(self):
        self.assertFalse(self.channel.state()['can_confirm'])
        result=await self.prepare();self.assertTrue(result['ok'])
        s=self.channel.state();self.assertTrue(s['can_confirm']);self.assertFalse(s['write_available'])
        self.assertFalse(self.channel.pending.exists())
        self.channel.confirm('old',s['target_token'])
        self.assertTrue(self.channel.state()['write_available'])
        self.assertTrue((self.channel.ipc/'toolkit-revoked-old.json').exists())
    async def test_failed_probe_never_enables_confirmation_or_clears_mail(self):
        self.assertFalse((await self.prepare(lambda r:None))['ok'])
        self.assertFalse(self.channel.state()['can_confirm']);self.assertTrue(self.channel.pending.exists())
    async def test_forged_ack_without_native_revocation_is_rejected(self):
        def forged(r):
            atomic(self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json",dict(request_id=r['request_id'],ok=True,payload=dict(fenced_request_id='old',document_id='doc',probe_id=r['request_id'])))
        self.assertFalse((await self.prepare(forged))['ok']);self.assertTrue(self.channel.pending.exists())
    async def test_switch_away_and_back_invalidates_confirmation(self):
        await self.prepare();old=self.channel.state()['target_token'];self.doc['switch_serial']=3
        self.assertFalse(self.channel.state()['can_confirm'])
        with self.assertRaises(ValueError):self.channel.confirm('old',old)
    async def test_busy_or_changed_process_never_sends_probe(self):
        self.doc['busy']=True
        self.assertFalse((await self.prepare(lambda r:self.fail('sent')))['ok'])
        self.doc['busy']=False;self.frame['processStart']+=1
        self.assertFalse((await self.prepare(lambda r:self.fail('sent')))['ok'])
    async def test_document_switch_requires_application_idle_native_proof(self):
        self.doc.update(id='other',switch_serial=2)
        def native(r):
            self.native(r)
            path=self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json"
            reply=json.loads(path.read_text())
            reply['payload'].update(document_id='other',application_idle=True,initial_switch_serial=2,verified_switch_serial=2)
            atomic(path,reply)
        result=await self.prepare(native)
        self.assertTrue(result['ok'],result)
        state=self.channel.state()
        self.assertTrue(state['can_confirm']);self.assertFalse(state['write_available'])
        self.assertEqual(state['recovery']['document']['id'],'doc')
        self.channel.confirm('old',state['target_token'])
        self.assertTrue(self.channel.state()['write_available'])
    async def test_document_switch_without_application_idle_proof_keeps_barrier(self):
        self.doc.update(id='other',switch_serial=2)
        self.assertFalse((await self.prepare())['ok'])
        self.assertTrue(self.channel.pending.exists())
        self.assertFalse(self.channel.state()['can_confirm'])
    async def test_inactive_document_busy_keeps_mail_and_explains_recovery_failure(self):
        self.doc.update(id='other',switch_serial=2)
        def native(r):
            self.assertEqual(r['params']['require_application_idle'],1)
            atomic(self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json",dict(request_id=r['request_id'],ok=False,error='RECOVERY_DOCUMENT_BUSY_OR_UNVERIFIED'))
        result=await self.prepare(native)
        self.assertEqual(result['code'],'RECOVERY_DOCUMENT_BUSY_OR_UNVERIFIED')
        self.assertTrue(self.channel.pending.exists())
        self.assertFalse(self.channel.state()['can_confirm'])
    async def test_native_inspection_switches_are_bound_to_fresh_confirmation(self):
        self.doc.update(id='other',switch_serial=2)
        def native(r):
            self.native(r);self.doc['switch_serial']=4
            path=self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json"
            reply=json.loads(path.read_text())
            reply['payload'].update(document_id='other',application_idle=True,initial_switch_serial=2,verified_switch_serial=4)
            atomic(path,reply)
        old=self.channel.state()['target_token']
        self.assertTrue((await self.prepare(native))['ok'])
        state=self.channel.state();self.assertTrue(state['can_confirm'])
        with self.assertRaises(ValueError):self.channel.confirm('old',old)
        self.doc['switch_serial']=6
        self.assertFalse(self.channel.state()['can_confirm'])
    async def test_switch_after_native_proof_never_allows_confirmation(self):
        self.doc.update(id='other',switch_serial=2)
        def native(r):
            self.native(r);self.doc['switch_serial']=6
            path=self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json"
            reply=json.loads(path.read_text())
            reply['payload'].update(document_id='other',application_idle=True,initial_switch_serial=2,verified_switch_serial=4)
            atomic(path,reply)
        self.assertEqual((await self.prepare(native))['code'],'RECOVERY_PROOF_INVALID')
        self.assertTrue(self.channel.pending.exists())
    async def test_legacy_native_bridge_explains_cross_document_update_requirement(self):
        self.doc.update(id='other',switch_serial=2)
        self.assertEqual((await self.prepare())['code'],'RECOVERY_CROSS_DOCUMENT_UPDATE_REQUIRED')
    async def test_unidentified_legacy_request_cannot_use_cross_document_recovery(self):
        self.record.pop('document');self.record['legacy']=True
        atomic(self.channel.recovery,self.record)
        self.assertFalse((await self.prepare(lambda r:self.fail('sent')))['ok'])
    async def test_rewritten_old_mail_invalidates_confirmation(self):
        await self.prepare();atomic(self.channel.ipc/'autocad_mcp_cmd_old.json',dict(request_id='old'))
        self.assertFalse(self.channel.state()['can_confirm'])
    async def test_proof_survives_toolkit_restart_but_requires_revocation_file(self):
        await self.prepare()
        restarted=Channel(self.root,self.channel.frames,self.channel.context)
        self.assertTrue(restarted.state()['can_confirm'])
        (self.channel.ipc/'toolkit-revoked-old.json').unlink()
        self.assertFalse(restarted.state()['can_confirm'])
    async def test_old_native_bridge_cannot_offer_inplace_recovery(self):
        self.channel.context=lambda f:dict(guard_protocol=3,document=dict(self.doc))
        self.assertEqual((await self.prepare(lambda r:self.fail('sent')))['code'],'BRIDGE_UPDATE_REQUIRED')
    async def test_stale_target_token_cannot_send_maintenance_request(self):
        result=await self.channel.prepare_recovery('old','stale',lambda r:self.fail('sent'),.2)
        self.assertFalse(result['ok']);self.assertTrue(self.channel.pending.exists())
    async def test_other_pending_mail_cannot_be_quarantined_as_old_request(self):
        atomic(self.channel.ipc/'autocad_mcp_cmd_other.json',dict(request_id='other'))
        result=await self.prepare(lambda r:self.fail('sent'))
        self.assertEqual(result['code'],'RECOVERY_MAIL_CONFLICT')
        self.assertTrue((self.channel.ipc/'autocad_mcp_cmd_other.json').exists())

if __name__=='__main__':unittest.main()
