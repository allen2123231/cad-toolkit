"""Opt-in, read-only stdio integration against the installed server package.

An empty temporary IPC directory deliberately has no native context, so this
must refuse drawing commands without notifying or changing any existing CAD.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'engine'))
from probe import Client

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    env={**os.environ,'AUTOCAD_MCP_BACKEND':'file_ipc','AUTOCAD_MCP_IPC_DIR':str(root/'ipc'),'PYTHONUTF8':'1'}
    command=[sys.executable,'-X','utf8',str(REPO/'engine/autocad_session.py')]
    with Client(command,env,timeout=10) as client:
        client.initialize()
        status=client.call('system',{'operation':'status'})
        value=status.get('payload',status)
        assert value['backend']=='file_ipc' and value['ready'] is False,status
        try:client.call('drawing',{'operation':'info'})
        except RuntimeError as exc:
            assert any(code in str(exc) for code in ('BRIDGE_UPDATE_REQUIRED','CAD_CLOSED','SELECT_TARGET')),str(exc)
        else:raise AssertionError('Missing context must block drawing info')
    assert not list((root/'ipc').glob('autocad_mcp_cmd_*.json'))
    assert not (root/'ipc/pcad-pending.json').exists()
    print(json.dumps({'passed':True,'checks':3,'backend':'file_ipc','cad_not_notified':True}))
