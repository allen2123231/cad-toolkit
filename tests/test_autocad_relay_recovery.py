"""End-to-end NDJSON checks: recovery must not stall the MCP front door."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ENGINE=Path(__file__).resolve().parents[1]/'engine'
sys.path.insert(0,str(ENGINE))
from autocad_channel import atomic
from probe import Client


class RelayRecoveryTests(unittest.TestCase):
    def test_application_start_wait_does_not_block_recovery_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            child=root/'child.py';child.write_text('''import sys,json
for line in sys.stdin:
 m=json.loads(line)
 if "id" in m:print(json.dumps({"jsonrpc":"2.0","id":m["id"],"result":{"protocolVersion":"2025-03-26","capabilities":{},"serverInfo":{"name":"fixture","version":"1"}}}),flush=True)
''')
            wrapper=root/'wrapper.py';wrapper.write_text('''import sys,time
sys.path.insert(0,sys.argv[1])
import cad_launch
def delayed(*args):
 time.sleep(1)
 return {"state":"starting","message":"fixture waiting"}
cad_launch.wait_for_application=delayed
import relay
sys.exit(relay.run(sys.argv[2],"autocad",[sys._base_executable,sys.argv[3]]))
''')
            atomic(root/'ipc/toolkit-recovery.json',dict(request_id='interrupted',command='create-circle',frame=None,closed_observed=True,stage='unknown'))
            with Client([sys._base_executable,str(wrapper),str(ENGINE),str(root),str(child)],timeout=5) as client:
                client.initialize()
                client.send({'jsonrpc':'2.0','id':900,'method':'tools/call','params':{'name':'get_application_state','arguments':{'wait_seconds':42}}})
                client.send({'jsonrpc':'2.0','id':901,'method':'tools/call','params':{'name':'get_recovery_state','arguments':{}}})
                first=client.messages.get(timeout=3)
                self.assertEqual(first['id'],901,'A slow readiness poll must not monopolize the front door')
                self.assertIn('interrupted',first['result']['content'][0]['text'])
                self.assertEqual(client.messages.get(timeout=3)['id'],900)

    def test_recovery_accepts_status_and_new_requests_without_forwarding_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);child=root/'child.py';marker=root/'executed.txt'
            child.write_text('''import json,sys
from pathlib import Path
for line in sys.stdin:
 m=json.loads(line)
 if "id" not in m:continue
 method=m.get("method")
 if method=="initialize":result={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fixture","version":"1"}}
 elif method=="tools/list":result={"tools":[{"name":"entity","inputSchema":{"type":"object"}}]}
 else:
  Path(sys.argv[1]).write_text("unexpected execution")
  result={"content":[{"type":"text","text":"executed"}]}
 print(json.dumps({"jsonrpc":"2.0","id":m["id"],"result":result}),flush=True)
''',encoding='utf-8')
            atomic(root/'ipc/toolkit-recovery.json',dict(request_id='interrupted',command='create-circle',frame=None,closed_observed=True,stage='unknown'))
            command=[sys.executable,str(ENGINE/'relay.py'),'--root',str(root),'--component','autocad','--',sys._base_executable,str(child),str(marker)]
            with Client(command,env={**os.environ,'PYTHONUTF8':'1'},timeout=10) as client:
                init=client.initialize()
                self.assertIn('Never automatically repeat',init['instructions'])
                names={tool['name'] for tool in client.request('tools/list')['tools']}
                self.assertTrue({'entity','get_recovery_state','open_application','get_application_state'}<=names)
                for i in range(3):
                    response=client.request('tools/call',{'name':'entity','arguments':{'operation':'create_circle'}})
                    self.assertTrue(response['isError'])
                    self.assertIn('RECOVERY_REQUIRED',response['content'][0]['text'])
                    state=client.call('get_recovery_state')
                    self.assertEqual(state['recovery']['request_id'],'interrupted')
                # Read-only application inspection bypasses the occupied mailbox.
                value=client.call('get_application_state',{'wait_seconds':0})
                self.assertIn('state',value)
                self.assertFalse(marker.exists(),'blocked batches must not reach the CAD service')
            self.assertTrue((root/'ipc/toolkit-recovery.json').exists(),'relay restart must preserve evidence')
            import history
            self.assertEqual(sum(r['outcome']=='blocked' for r in history.recent(root)),3)


if __name__=='__main__':unittest.main()
