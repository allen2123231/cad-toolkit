"""Regression tests for independent read access and conservative write recovery."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from autocad_channel import Channel, atomic


class AccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.frame=dict(kind='autocad',pid=1,hwnd=2,processStart=time.time()-60)
        self.context=dict(guard_protocol=3,document=dict(id='doc',busy=False))
        self.channel=Channel(self.root,lambda:[self.frame],lambda f:self.context)

    def barrier(self,command='create-circle'):
        atomic(self.channel.recovery,dict(request_id='old',command=command,frame={k:self.frame[k] for k in ('pid','hwnd','processStart')},ts=time.time(),stage='unknown'))

    async def test_read_during_unknown_write_preserves_barrier_and_write_mail(self):
        self.barrier()
        old=dict(request_id='old',command='create-circle',params={})
        atomic(self.channel.pending,old)
        atomic(self.channel.ipc/'autocad_mcp_cmd_old.json',old)
        before=self.channel.recovery.read_bytes()
        def finish(r):
            self.assertTrue((self.channel.ipc/f"autocad_mcp_read_{r['request_id']}.json").exists())
            atomic(self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json",dict(request_id=r['request_id'],ok=True,payload={'count':7}))
        result=await self.channel.dispatch('entity-count',{},finish,.3)
        self.assertTrue(result['ok'])
        self.assertEqual(result['payload']['count'],7)
        self.assertEqual(json.loads(before)['request_id'],self.channel.state()['recovery']['request_id'])
        self.assertTrue((self.channel.ipc/'autocad_mcp_cmd_old.json').exists())
        self.assertEqual((await self.channel.dispatch('create-circle',{},lambda r:self.fail('write sent'),.1))['code'],'RECOVERY_REQUIRED')

    async def test_read_timeout_does_not_create_write_recovery(self):
        result=await self.channel.dispatch('drawing-info',{},lambda r:None,.01)
        self.assertEqual(result['code'],'READ_FAILED')
        self.assertIsNone(self.channel.state()['recovery'])
        self.assertFalse(self.channel.pending.exists())
        self.assertFalse(list(self.channel.ipc.glob('autocad_mcp_read_*.json')))

    async def test_proven_not_sent_never_requires_restart_and_records_error(self):
        from autocad_channel import NotSent
        def denied(r):raise NotSent('CAD_BUSY','busy before SendCommand')
        result=await self.channel.dispatch('create-circle',{},denied,.3)
        self.assertEqual(result['code'],'CAD_BUSY')
        self.assertIsNone(self.channel.state()['recovery'])
        self.assertFalse(self.channel.pending.exists())
        journal=list((self.channel.ipc/'toolkit-journal').glob('*.json'))
        record=json.loads(journal[0].read_text())
        self.assertEqual(record['stage'],'not_sent')
        self.assertEqual(record['error_type'],'NotSent')
        self.assertIn('busy before',record['error'])

    async def test_unknown_send_error_preserves_original_error_and_barrier(self):
        def uncertain(r):raise OSError('SendCommand disconnected')
        with self.assertRaises(OSError):await self.channel.dispatch('create-circle',{},uncertain,.3)
        recovery=self.channel.state()['recovery']
        self.assertEqual(recovery['error_type'],'OSError')
        self.assertIn('disconnected',recovery['error'])

    async def test_legacy_read_barrier_archives_without_replaying(self):
        self.barrier('drawing-info')
        atomic(self.channel.pending,dict(request_id='old',command='drawing-info',params={}))
        atomic(self.channel.ipc/'autocad_mcp_cmd_old.json',dict(request_id='old',command='drawing-info',params={}))
        self.assertIsNone(self.channel.state()['recovery'])
        self.assertFalse(self.channel.pending.exists())
        self.assertFalse((self.channel.ipc/'autocad_mcp_cmd_old.json').exists())

    async def test_orphan_read_is_retired_before_next_read(self):
        atomic(self.channel.ipc/'autocad_mcp_read_dead.json',dict(request_id='dead',command='drawing-info'))
        def finish(r):
            self.assertEqual(len(list(self.channel.ipc.glob('autocad_mcp_read_*.json'))),1)
            atomic(self.channel.ipc/f"autocad_mcp_result_{r['request_id']}.json",dict(request_id=r['request_id'],ok=True))
        self.assertTrue((await self.channel.dispatch('entity-count',{},finish,.3))['ok'])

    async def test_read_failure_retains_existing_write_recovery(self):
        self.barrier()
        result=await self.channel.dispatch('drawing-info',{},lambda r:None,.01)
        self.assertEqual(result['code'],'READ_FAILED')
        self.assertEqual(self.channel.state()['recovery']['request_id'],'old')

    async def test_old_bridge_cannot_use_read_channel(self):
        self.context['guard_protocol']=2
        result=await self.channel.dispatch('entity-count',{},lambda r:self.fail('sent'),.01)
        self.assertEqual(result['code'],'BRIDGE_UPDATE_REQUIRED')

    def test_only_audited_operations_are_readonly(self):
        from autocad_access import readonly_tool,READ_COMMANDS
        self.assertTrue(readonly_tool('drawing',{'operation':'info'}))
        for name,args in [('system',{'operation':'execute_lisp','readOnlyHint':True}),('entity',{'operation':'erase'}),('drawing',{'operation':'save'}),('view',{'operation':'zoom_extents'})]:
            self.assertFalse(readonly_tool(name,args))
        self.assertNotIn('execute-lisp',READ_COMMANDS)


if __name__=='__main__':unittest.main()
