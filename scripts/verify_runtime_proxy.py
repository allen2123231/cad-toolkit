"""Verify installed MCP stdio relays and durable receipts in an isolated folder."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from manager import plugin_files, mcp_command, mcp_env
from common import read_json, atomic_json
from probe import Client
import history

parser = argparse.ArgumentParser()
parser.add_argument('--version-dir', required=True)
parser.add_argument('--output', default=str(ROOT / 'test-results/proxy'))
args = parser.parse_args()
target = Path(args.version_dir).resolve()
output = Path(args.output).resolve()
plugin = output / 'plugin'
commands = {c: mcp_command(target, c) for c in ('autocad', 'inventor', 'rhino')}
plugin_files(plugin, ROOT / 'plugins/cad-toolkit', commands, 'test', mcp_env(output), history_root=output)
servers = read_json(plugin / 'mcp.json')['mcpServers']
results = {}
for component, spec in servers.items():
    env = {**os.environ, **spec['env'], 'AUTOCAD_MCP_BACKEND': 'ezdxf'}
    with Client([spec['command'], *spec['args']], env, timeout=20) as client:
        client.initialize()
        count = len(client.request('tools/list')['tools'])
        if component == 'rhino':
            client.call('get_modeling_guidance', {'topic': 'overview'})
        elif component == 'inventor':
            # No explicit connect, and never starts CAD. A healthy existing home screen is valid.
            status = client.call('status')
            assert 'Connected' in str(status), status
        else:
            client.call('system', {'operation': 'runtime'})
        results[component] = {'tool_count': count, 'round_trip': True}
receipts = history.recent(output)
assert all(any(r['component'] == c and r['outcome'] == 'succeeded' for r in receipts) for c in servers), receipts
atomic_json(output / 'report.json', {'passed': True, 'servers': results, 'receipt_count': len(receipts), 'cad_model_edits': 0})
print(json.dumps({'passed': True, 'servers': results, 'receipt_count': len(receipts)}))
