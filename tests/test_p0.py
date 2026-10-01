from __future__ import annotations
import asyncio
import json
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp_hcl.artifact_store import ArtifactRetries
from mcp_hcl.server import create_server
from mcp_hcl.project import ProjectStore
from mcp_hcl.catalog import HclCatalog
from test_mcp_contract import build_fixture


class RetryTests(unittest.TestCase):
    def test_durable_conflict_tamper_and_concurrent_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            count = []
            def action():
                count.append(1)
                directory = root / 'export'
                directory.mkdir()
                (directory / 'plan.json').write_text('{}')
                return {'status': 'verified', 'artifact_directory': str(directory)}
            args = {'idempotency_key': 'request-1', 'name': 'one'}
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: ArtifactRetries(root).run('export', args, action), range(4)))
            self.assertEqual(len(count), 1)
            self.assertEqual(len({r['operation_id'] for r in results}), 1)
            replay = ArtifactRetries(root).run('export', args, action)
            self.assertTrue(replay['replayed'])
            conflict = ArtifactRetries(root).run('export', {**args, 'name': 'two'}, action)
            self.assertEqual(conflict['errors'][0]['code'], 'idempotency_conflict')
            (root / 'export' / 'plan.json').write_text('changed')
            self.assertEqual(ArtifactRetries(root).run('export', args, action)['errors'][0]['code'], 'artifact_changed')

    def test_failed_write_does_not_reserve_key(self):
        with tempfile.TemporaryDirectory() as directory:
            retries = ArtifactRetries(Path(directory))
            args = {'idempotency_key': 'failed'}
            def fail():
                raise OSError('disk failure')
            with self.assertRaises(OSError):
                retries.run('export', args, fail)
            result = retries.run('export', args, lambda: {'status': 'rejected', 'error': 'not created'})
            self.assertEqual(result['status'], 'rejected')


class EnvelopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_retry_and_argument_linkage(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            server = create_server(store=ProjectStore([paths['root']], paths['output']), catalog=HclCatalog(paths['install']))
            source = str(paths['root'] / 'Lab One')
            # Discover the fixture's actual directory rather than assuming its display name.
            source = str(next(p.parent for p in paths['root'].rglob('*.net')))
            args = {'project_path': source, 'stage_name': 'Retry', 'idempotency_key': 'stage-1'}
            first = await server.call_tool('hcl_stage_copy', args)
            second = await server.call_tool('hcl_stage_copy', args)
            self.assertEqual(first.structuredContent['status'], 'staged')
            self.assertEqual(first.structuredContent['operation_id'], second.structuredContent['operation_id'])
            self.assertTrue(second.structuredContent['replayed'])
            invalid = await server.call_tool('hcl_console_exec', {'command': 'display version', 'pipe': r'\\.\pipe\topo1-device1', 'device': 1})
            self.assertEqual(invalid.structuredContent['errors'][0]['code'], 'invalid_arguments')
            for key in ('status', 'operation_id', 'request_id', 'target', 'verified_scope', 'evidence', 'errors', 'warnings'):
                self.assertIn(key, first.structuredContent)
            for arguments in ({'action':'status','udp_port':10000}, {'action':'close','topology':None}):
                invalid = await server.call_tool('hcl_backend_topology', arguments)
                self.assertEqual(invalid.structuredContent['errors'][0]['code'],'invalid_arguments')


class LabVerdictTests(unittest.TestCase):
    def test_unknown_or_failed_readings_never_pass(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'hcl_lab_verdict.ps1'
        command = f". '{script}'; @((Get-HclLabVerdict $true $true $null),(Get-HclLabVerdict $false $true $false),(Get-HclLabVerdict $true $true $false),(Get-HclLabVerdict $true $true $true)) | ConvertTo-Json -Compress"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['unknown', 'unknown', 'lab_entry_active_and_no_hypervisor', 'lab_entry_active_but_hypervisor_still_present'])
        source = script.with_name('hcl_lab_environment.ps1').read_text(encoding='utf-8')
        self.assertNotIn('1031110f', source)
        self.assertIn('$creation.entry_id', source)
