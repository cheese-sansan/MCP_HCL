from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp_hcl.gui_relay import HclGuiRelay
from mcp_hcl.project import ProjectStore
from test_mcp_contract import build_fixture, mcp_session, call


class GuiRelayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = build_fixture(Path(self.temporary.name))
        self.store = ProjectStore([self.paths['root']], self.paths['output'])
        self.staged = self.store.stage_copy(str(self.paths['project']), 'GuiCopy')
        self.commands = []

    def runner(self, *, failure=None, wrong_project=False, validate_only=False, wrong_caption=False):
        def run(command):
            self.commands.append(command)
            if failure: raise failure
            output = Path(command[command.index('-OutputDirectory') + 1])
            output.mkdir(parents=True)
            receipt = {'operation_id': 'a' * 32, 'status': 'partial', 'hcl_pid': 17,
                       'project_file': 'C:/wrong/project.net' if wrong_project else self.staged['project_file'],
                       'operation': 'isolated_project_open' if '-OpenOnly' in command else 'isolated_project_save',
                       'validate_only': validate_only,
                       'active_project_caption': f"HCL - {'GuiCopyExtra' if wrong_caption else 'GuiCopy'} [{self.staged['project_directory']}]",
                       'checks': {key: True for key in ('project_preconditions', 'project_opened', 'canvas_project_identity', 'save_invoked', 'project_readback')}}
            (output / 'result.json').write_text(json.dumps(receipt), encoding='utf-8')
            return SimpleNamespace(returncode=0)
        return run

    def test_disabled_relay_does_not_read_or_invoke_anything(self):
        relay = HclGuiRelay(self.store, runner=self.runner())
        result = relay.execute('open', 'does-not-exist', 17)
        self.assertEqual(result['errors'][0]['code'], 'writes_disabled')
        self.assertEqual(self.commands, [])

    def test_original_project_and_missing_or_forged_stage_marker_are_rejected(self):
        relay = HclGuiRelay(self.store, writes_enabled=True, runner=self.runner())
        result = relay.execute('open', str(self.paths['project']), 17)
        self.assertEqual(result['errors'][0]['code'], 'original_project_protected')
        marker = Path(self.staged['project_directory']) / 'MCPArtifacts/stage-receipt.json'
        marker.write_text('[]')
        self.assertEqual(relay.execute('open', self.staged['project_directory'], 17)['errors'][0]['code'], 'invalid_stage_receipt')
        marker.unlink()
        self.assertEqual(relay.execute('open', self.staged['project_directory'], 17)['errors'][0]['code'], 'stage_receipt_required')
        self.assertEqual(self.commands, [])

    def test_open_and_save_have_distinct_no_boot_actions_and_limited_evidence(self):
        relay = HclGuiRelay(self.store, writes_enabled=True, runner=self.runner())
        for action in ('open', 'save'):
            result = relay.execute(action, self.staged['project_directory'], 17)
            self.assertEqual(result['status'], 'verified')
            self.assertTrue(result['project_identity_verified'])
            self.assertFalse(result['live_canvas_verified'])
            self.assertFalse(result['guest_boot_verified'])
            self.assertFalse(result['configuration_verified'])
            self.assertFalse(result['full_live_gate_passed'])
            self.assertEqual(result['source_stage_operation_id'], self.staged['operation_id'])
            self.assertTrue(Path(result['evidence'][0]['source']).is_file())
        self.assertIn('-OpenOnly', self.commands[0])
        self.assertIn('-ResumeLoadedProject', self.commands[1])
        self.assertNotEqual(self.commands[0][self.commands[0].index('-OutputDirectory') + 1],
                            self.commands[1][self.commands[1].index('-OutputDirectory') + 1])

    def test_wrong_project_or_preflight_only_receipts_cannot_prove_gui_success(self):
        for kwargs in ({'wrong_project': True}, {'validate_only': True}, {'wrong_caption': True}):
            relay = HclGuiRelay(self.store, writes_enabled=True, runner=self.runner(**kwargs))
            self.assertEqual(relay.execute('open', self.staged['project_directory'], 17)['status'], 'unverified')

    def test_timeout_is_not_replayed_and_prior_receipt_cannot_be_reused(self):
        relay = HclGuiRelay(self.store, writes_enabled=True, runner=self.runner(failure=subprocess.TimeoutExpired('powershell', 55)))
        result = relay.execute('open', self.staged['project_directory'], 17)
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(len(self.commands), 1)
        # A successful previous operation is in a different UUID directory.
        successful = HclGuiRelay(self.store, writes_enabled=True, runner=self.runner()).execute('open', self.staged['project_directory'], 17)
        missing = HclGuiRelay(self.store, writes_enabled=True, runner=lambda command: SimpleNamespace(returncode=0))
        result = missing.execute('open', self.staged['project_directory'], 17)
        self.assertEqual(result['errors'][0]['code'], 'relay_receipt_missing')
        self.assertTrue(Path(successful['evidence'][0]['source']).is_file())


class GuiStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_project_tools_are_visible_but_default_to_write_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            async with mcp_session(paths) as session:
                for tool in ('hcl_open_project', 'hcl_save_project'):
                    result, body = await call(session, tool, {'project_path': str(paths['project']), 'hcl_pid': 17})
                    self.assertFalse(result.isError)
                    self.assertEqual(body['errors'][0]['code'], 'writes_disabled')
                    self.assertFalse(body['full_live_gate_passed'])
