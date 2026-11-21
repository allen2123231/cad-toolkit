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
    async def test_busy_or_changed_document_never_sends_probe(self):
        self.doc['busy']=True
        self.assertFalse((await self.prepare(lambda r:self.fail('sent')))['ok'])
        self.doc['busy']=False;self.doc['id']='other'
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
