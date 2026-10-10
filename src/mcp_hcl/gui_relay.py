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
import threading
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from uuid import uuid4
from mcp_hcl.console import ConsoleError
from mcp_hcl.gui_identity import GuiIdentityGuard, GuiIdentityError, GuiProfileLease, ps_literal, windows_powershell


def rejected(code, message):
    return {'status': 'rejected', 'errors': [{'code': code, 'message': message}],
            'runtime_verified': False, 'full_live_gate_passed': False}


class HclGuiRelay:
    def __init__(self, store, *, writes_enabled=False, runner=None, identity_guard=None, installation_root=None):
        self.store = store
        self.writes_enabled = writes_enabled
        self.runner = runner or self._run
        self.native_runner = runner is None
        self.native_dependencies = runner is None and identity_guard is None
        self.identity_guard = identity_guard or GuiIdentityGuard(
            installation_root or os.environ.get('MCP_HCL_INSTALL_ROOT', 'D:/HCL'),
            backend_port=int(os.environ.get('MCP_HCL_BACKEND_PORT', '16600')))
        self._lock = threading.Lock()

    @staticmethod
    def _run(command):
        return subprocess.run(command, capture_output=True, timeout=55, check=False)

    def execute(self, action: str, project_path: str, hcl_pid: int) -> dict:
        if not self.writes_enabled:
            return rejected('writes_disabled', 'Opening or saving the HCL GUI requires MCP_HCL_ALLOW_LIVE_WRITE=1')
        if not self._lock.acquire(blocking=False):
            return rejected('gui_operation_busy', 'Another GUI operation is active; no action was queued')
        try:
            with ExitStack() as scope:
                return self._execute(action, project_path, hcl_pid, scope)
        finally:
            self._lock.release()

    def _execute(self, action: str, project_path: str, hcl_pid: int, scope) -> dict:
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
        try:
            identity = self.identity_guard.prepare(action, document, marker['operation_id'], hcl_pid)
            if self.native_runner and identity.get('native_identity_verified') is not True:
                return rejected('native_gui_identity_required', 'Synthetic identity observations cannot authorize native GUI actions')
            if self.native_runner:
                scope.enter_context(GuiProfileLease(identity['profile_directory']))
                # Another controller could have changed the namespace before
                # the OS lock was acquired. Recheck while holding that lock.
                refreshed = self.identity_guard.prepare(action, document, marker['operation_id'], hcl_pid)
                if refreshed['identity_key'] != identity['identity_key']:
                    raise GuiIdentityError('gui_process_changed', 'GUI identity changed before obtaining the control lease')
                identity = refreshed
        except GuiIdentityError as exc:
            return rejected(exc.code, str(exc))
        except (OSError, ValueError, TypeError, KeyError, ConsoleError):
            return rejected('gui_preconditions_unknown', 'GUI identity or runtime namespace could not be established')
        run_directory = self.store.output_root / '.relay-receipts' / uuid4().hex
        before = hashlib.sha256(document.net_path.read_bytes()).hexdigest()
        resource = files('mcp_hcl').joinpath('data/hcl_open_gate.ps1')
        observer_resource = files('mcp_hcl').joinpath('data/hcl_process_identity.ps1')
        with ExitStack() as stack:
            script = stack.enter_context(as_file(resource))
            observer_script = stack.enter_context(as_file(observer_resource))
            arguments = {'WorkspaceWorkRoot': str(self.store.output_root), 'HclPid': hcl_pid,
                         'ProjectFile': str(document.net_path), 'OutputDirectory': str(run_directory),
                         'ExpectedOwnerSid': identity['owner_sid'], 'ExpectedCreationTime': identity['creation_time'],
                         'ExpectedProfileDirectory': identity['profile_directory'],
                         'ExpectedClientPath': identity['executable_path'],
                         'IdentityObserverFile': str(observer_script), 'IdentityObserverSha256': identity['observer_sha256']}
            arguments.update(ExpectedBackendPort=identity['broker']['port'], ExpectedBrokerPid=identity['broker']['pid'],
                             ExpectedBrokerCreationTime=identity['broker']['creation_time'],
                             ExpectedBrokerPath=identity['broker']['executable_path'])
            # Restricted file execution is not bypassed. The trusted packaged
            # body runs inline; paths are decoded constants, never code text.
            expression = '& {\n' + script.read_bytes().decode('utf-8-sig') + '\n} '
            expression += ' '.join('-' + key + ' ' + ps_literal(value) for key, value in arguments.items())
            expression += ' -OpenOnly' if action == 'open' else ' -ResumeLoadedProject'
            command = [str(windows_powershell()), '-NoProfile', '-NonInteractive', '-Command', expression]
            try:
                process = self.runner(command)
            except (OSError, subprocess.TimeoutExpired):
                return {'status': 'unverified', 'target_project': str(document.net_path),
                        'errors': [{'code': 'relay_unavailable_or_timed_out',
                                    'message': 'The GUI operation has no verified result; it is not automatically replayed'}],
                        'receipt_directory': str(run_directory), 'runtime_verified': False,
                        'full_live_gate_passed': False, 'process_identity_before': identity}
        try:
            identity_after = self.identity_guard.probe(hcl_pid)
            if identity_after['identity_key'] != identity['identity_key']:
                raise GuiIdentityError('gui_process_changed', 'HCL process identity changed during the GUI operation')
        except (GuiIdentityError, OSError, ValueError, KeyError, ConsoleError):
            return {'status': 'unverified', 'target_project': str(document.net_path),
                    'errors': [{'code': 'gui_process_changed_or_unknown', 'message': 'No stable HCL process identity after the GUI action'}],
                    'receipt_directory': str(run_directory), 'process_identity_before': identity,
                    'runtime_verified': False, 'full_live_gate_passed': False}
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
            required = ['project_preconditions', 'process_identity', 'project_opened', 'canvas_project_identity']
            if action == 'save': required += ['save_invoked', 'project_readback']
            verified = (process.returncode == 0 and bound and caption_matches and not receipt.get('validate_only') and
                        receipt.get('status') in {'verified', 'partial'} and
                        not receipt.get('error') and all(checks.get(key) is True for key in required))
            readback = self.store.inspect(str(document.directory))
        except (ValueError, KeyError, TypeError, OSError):
            return {'status': 'unverified', 'errors': [{'code': 'relay_receipt_invalid', 'message': 'Receipt or saved-project readback is invalid'}],
                    'runtime_verified': False, 'full_live_gate_passed': False}
        native = verified and self.native_dependencies and identity.get('native_identity_verified') is True and identity_after.get('native_identity_verified') is True
        return {'status': 'verified' if native else 'output_received' if verified else 'unverified', 'operation': 'gui_project_' + action,
                'operation_id': receipt.get('operation_id', uuid4().hex), 'target_project': str(document.net_path),
                'verified_scope': 'gui_project_identity_and_saved_file_readback_only' if native else 'synthetic_gui_receipt_protocol_only' if verified else 'none',
                'project_identity_verified': native, 'protocol_project_identity_verified': verified,
                'process_identity_before': identity, 'process_identity_after': identity_after,
                'runtime_isolation_verified': False, 'live_canvas_verified': False, 'runtime_verified': False,
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
