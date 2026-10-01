"""Gated deterministic HCL open/save relay, with request-local file receipts.

The packaged PowerShell adapter verifies the active project caption. It does
not boot guests, deploy CLI, validate pixels, or claim a live topology snapshot.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from importlib.resources import as_file, files
from pathlib import Path
from uuid import uuid4


def rejected(code, message):
    return {'status': 'rejected', 'errors': [{'code': code, 'message': message}],
            'runtime_verified': False, 'full_live_gate_passed': False}


class HclGuiRelay:
    def __init__(self, store, *, writes_enabled=False, runner=None):
        self.store = store
        self.writes_enabled = writes_enabled
        self.runner = runner or self._run

    @staticmethod
    def _run(command):
        return subprocess.run(command, capture_output=True, timeout=55, check=False)

    def execute(self, action: str, project_path: str, hcl_pid: int) -> dict:
        if not self.writes_enabled:
            return rejected('writes_disabled', 'Opening or saving the HCL GUI requires MCP_HCL_ALLOW_LIVE_WRITE=1')
        if action not in {'open', 'save'}:
            return rejected('invalid_action', 'Only open/save relay actions are supported')
        if isinstance(hcl_pid, bool) or not isinstance(hcl_pid, int) or hcl_pid < 1:
            return rejected('invalid_pid', 'hcl_pid must be a positive SimwareClient PID')
        document = self.store._open(project_path)
        if not document.directory.is_relative_to(self.store.output_root):
            return rejected('original_project_protected', 'GUI relay accepts only projects under the isolated output root')
        marker_path = document.directory / 'MCPArtifacts' / 'stage-receipt.json'
        if not marker_path.is_file() or marker_path.is_symlink():
            return rejected('stage_receipt_required', 'Create a fresh copy with an hcl_stage_* tool before GUI activation')
        try:
            marker = json.loads(marker_path.read_text(encoding='utf-8'))
            if (not isinstance(marker, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(marker.get('operation_id', ''))) or
                    marker.get('schema_version') != 1 or Path(marker['project_file']).resolve() != document.net_path or
                    Path(marker['source_directory']).resolve() == document.directory):
                raise ValueError('Stage receipt identity mismatch')
        except (ValueError, KeyError, TypeError) as exc:
            return rejected('invalid_stage_receipt', str(exc))
        run_directory = self.store.output_root / '.relay-receipts' / uuid4().hex
        before = hashlib.sha256(document.net_path.read_bytes()).hexdigest()
        resource = files('mcp_hcl').joinpath('data/hcl_open_gate.ps1')
        with as_file(resource) as script:
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                       '-WorkspaceWorkRoot', str(self.store.output_root), '-HclPid', str(hcl_pid),
                       '-ProjectFile', str(document.net_path), '-OutputDirectory', str(run_directory)]
            command.append('-OpenOnly' if action == 'open' else '-ResumeLoadedProject')
            try:
                process = self.runner(command)
            except (OSError, subprocess.TimeoutExpired):
                return {'status': 'unverified', 'target_project': str(document.net_path),
                        'errors': [{'code': 'relay_unavailable_or_timed_out',
                                    'message': 'The GUI operation has no verified result; it is not automatically replayed'}],
                        'receipt_directory': str(run_directory), 'runtime_verified': False,
                        'full_live_gate_passed': False}
        receipt_path = run_directory / 'result.json'
        if not receipt_path.is_file() or receipt_path.is_symlink():
            return {'status': 'unverified', 'target_project': str(document.net_path),
                    'errors': [{'code': 'relay_receipt_missing', 'message': 'No request-local relay receipt was produced'}],
                    'runtime_verified': False, 'full_live_gate_passed': False}
        try:
            receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
            if not isinstance(receipt, dict) or not isinstance(receipt.get('checks'), dict):
                raise ValueError('Invalid GUI receipt structure')
            checks = receipt['checks']
            caption = re.fullmatch(r'HCL - (.+) \[(.+)\]', receipt.get('active_project_caption', ''))
            caption_matches = bool(caption and caption[1] == document.metadata['projectInfo']['name'] and
                                   Path(caption[2]).resolve() == document.directory)
            bound = (receipt['hcl_pid'] == hcl_pid and
                     Path(receipt['project_file']).resolve() == document.net_path and
                     receipt['operation'] == ('isolated_project_open' if action == 'open' else 'isolated_project_save'))
            required = ['project_preconditions', 'project_opened', 'canvas_project_identity']
            if action == 'save': required += ['save_invoked', 'project_readback']
            verified = (process.returncode == 0 and bound and caption_matches and not receipt.get('validate_only') and
                        receipt.get('status') in {'verified', 'partial'} and
                        not receipt.get('error') and all(checks.get(key) is True for key in required))
            readback = self.store.inspect(str(document.directory))
        except (ValueError, KeyError, TypeError, OSError):
            return {'status': 'unverified', 'errors': [{'code': 'relay_receipt_invalid', 'message': 'Receipt or saved-project readback is invalid'}],
                    'runtime_verified': False, 'full_live_gate_passed': False}
        return {'status': 'verified' if verified else 'unverified', 'operation': 'gui_project_' + action,
                'operation_id': receipt.get('operation_id', uuid4().hex), 'target_project': str(document.net_path),
                'verified_scope': 'gui_project_identity_and_saved_file_readback_only' if verified else 'none',
                'project_identity_verified': verified, 'live_canvas_verified': False, 'runtime_verified': False,
                'guest_boot_verified': False, 'configuration_verified': False, 'connectivity_verified': False,
                'full_live_gate_passed': False, 'project': readback, 'checks': checks,
                'receipt_directory': str(run_directory), 'source_stage_operation_id': marker['operation_id'],
                'errors': [] if verified else [{'code': 'gui_effect_unverified', 'message': 'Active project identity or required readback checks did not pass'}],
                'evidence': [{'source': str(receipt_path), 'sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(), 'layer': 'gui_relay_receipt'},
                             {'source': str(document.net_path), 'sha256_before': before,
                              'sha256': hashlib.sha256(document.net_path.read_bytes()).hexdigest(), 'layer': 'saved_project'}]}


def register_gui_tools(mcp, relay):
    @mcp.tool()
    def hcl_open_project(project_path: str, hcl_pid: int) -> dict:
        """Open a staged .net in an existing SimwareClient (write-gated); no guest boot or CLI deployment."""
        return relay.execute('open', project_path, hcl_pid)

    @mcp.tool()
    def hcl_save_project(project_path: str, hcl_pid: int) -> dict:
        """Verify the active staged project identity, save it and parse the saved files (write-gated)."""
        return relay.execute('save', project_path, hcl_pid)
