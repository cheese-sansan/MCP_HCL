"""Current-principal GUI binding and process-local fresh-namespace leases."""
from __future__ import annotations

import ctypes
import base64
import ctypes.wintypes as wt
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from mcp_hcl.console import ConsoleError
from mcp_hcl.runtime import inspect_runtime
from mcp_hcl.runtime_binding import unlinked


class GuiIdentityError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class GuiProfileLease:
    """Nonblocking OS file lock shared by GUI controllers in one user profile."""
    def __init__(self, profile):
        self.fd = None
        root = Path(profile) / '.mcp_hcl'
        path = root / 'gui-control.lock'
        unlinked(path)
        root.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            if os.fstat(self.fd).st_size == 0:
                os.write(self.fd, b'0')
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                raise GuiIdentityError('native_windows_required', 'GUI control leases require Windows')
        except (OSError, GuiIdentityError) as exc:
            self.close()
            raise GuiIdentityError('gui_control_busy_or_unavailable', 'The shared GUI control lease is busy or unavailable; no action was queued') from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def windows_powershell():
    if os.name != 'nt':
        raise GuiIdentityError('native_windows_required', 'Native GUI identity requires Windows')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [wt.LPWSTR, wt.UINT]
    kernel.GetSystemDirectoryW.restype = wt.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise GuiIdentityError('windows_directory_unknown', 'Windows system directory could not be observed')
    executable = Path(buffer.value) / 'WindowsPowerShell/v1.0/powershell.exe'
    unlinked(executable)
    if not executable.is_file():
        raise GuiIdentityError('windows_powershell_missing', 'Windows PowerShell is unavailable')
    return executable


def ps_literal(value):
    """Constant UTF-8 argument expression; user text is never parsed as code."""
    value = str(value)
    if any(ord(char) < 32 for char in value):
        raise GuiIdentityError('invalid_script_argument', 'Control characters are forbidden in GUI arguments')
    encoded = base64.b64encode(value.encode('utf-8')).decode('ascii')
    return "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')))"


class GuiIdentityGuard:
    def __init__(self, installation_root, *, runner=None, runtime_observer=None, backend_port=16600):
        self.installation_root = Path(installation_root)
        self.runner = runner or subprocess.run
        self.runtime_observer = runtime_observer or inspect_runtime
        self.native_dependencies = runner is None and runtime_observer is None
        self.leases = {}
        if type(backend_port) is not int or not 1024 <= backend_port <= 65535:
            raise GuiIdentityError('invalid_backend_port', 'Backend port must be an integer from 1024 to 65535')
        self.backend_port = backend_port

    def probe(self, hcl_pid):
        if type(hcl_pid) is not int or not 1 <= hcl_pid <= 2147483647:
            raise GuiIdentityError('invalid_pid', 'HCL PID must be a positive Windows process integer')
        if self.backend_port != 16600:
            raise GuiIdentityError('gui_backend_port_unverified',
                                   'GUI ownership checks currently cover the observed HCL backend port 16600 only')
        resource = files('mcp_hcl').joinpath('data/hcl_process_identity.ps1')
        script_bytes = resource.read_bytes()
        script = script_bytes.decode('utf-8-sig')
        command = [str(windows_powershell()), '-NoProfile', '-NonInteractive', '-Command',
                   '& {\n' + script + '\n} -HclPid ' + str(hcl_pid) + ' -BackendPort ' + str(self.backend_port)]
        try:
            process = self.runner(command, capture_output=True, timeout=12, check=False)
            if process.returncode != 0:
                raise GuiIdentityError('gui_process_identity_unknown', 'HCL process observation failed')
            if len(process.stdout) > 65536:
                raise GuiIdentityError('gui_process_identity_unknown', 'HCL process observation exceeded its limit')
            facts = json.loads(process.stdout.decode('utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            raise GuiIdentityError('gui_process_identity_unknown', 'HCL process observation is unavailable') from exc
        identity = self.validate(facts, hcl_pid)
        identity['native_identity_verified'] = self.native_dependencies
        identity['observer_sha256'] = hashlib.sha256(script_bytes).hexdigest()
        return identity

    def validate(self, facts, hcl_pid):
        try:
            if not isinstance(facts, dict) or type(facts.get('schema_version')) is not int or facts['schema_version'] != 1:
                raise ValueError('Invalid process observation schema')
            sid = facts['actual_sid']
            hcl = facts['hcl']
            caller = facts['caller']
            broker = facts['broker']
            if not isinstance(sid, str) or not re.fullmatch(r'S-\d+(?:-\d+)+', sid):
                raise ValueError('Current principal SID is unknown')
            if (not isinstance(hcl, dict) or type(hcl.get('pid')) is not int or hcl['pid'] != hcl_pid
                    or hcl.get('name') != 'SimwareClient.exe' or type(hcl.get('owner_result')) is not int
                    or hcl['owner_result'] != 0 or hcl.get('owner_sid') != sid):
                raise GuiIdentityError('hcl_principal_mismatch', 'HCL must belong to the observed current Windows SID')
            if (not isinstance(caller, dict) or type(caller.get('session_id')) is not int
                    or type(hcl.get('session_id')) is not int or caller['session_id'] != hcl['session_id']):
                raise GuiIdentityError('hcl_session_mismatch', 'HCL and the caller must belong to the same Windows session')
            if hcl.get('elevated') is not False or caller.get('elevated') is not False:
                raise GuiIdentityError('elevated_gui_unsupported', 'Both the caller and HCL must use non-elevated tokens')
            if (not isinstance(broker, dict) or type(broker.get('pid')) is not int or broker['pid'] < 1
                    or broker.get('name') != 'SimwareWrapper.exe' or type(broker.get('owner_result')) is not int
                    or broker['owner_result'] != 0 or broker.get('owner_sid') != sid
                    or type(broker.get('session_id')) is not int or broker['session_id'] != caller['session_id']
                    or broker.get('elevated') is not False
                    or type(broker.get('port')) is not int or broker['port'] != self.backend_port):
                raise GuiIdentityError('backend_principal_mismatch', 'The configured backend listener must use the same non-elevated Windows principal/session')
            profile = Path(facts['cim_profile_directory'])
            if not profile.is_absolute() or not profile.is_dir():
                raise ValueError('Current-SID profile path is not absolute')
            unlinked(profile)
            profile = profile.resolve()
            expected = {'profile_directory': profile, 'environment_profile': profile,
                        'application_data': profile / 'AppData/Roaming',
                        'environment_application_data': profile / 'AppData/Roaming',
                        'local_application_data': profile / 'AppData/Local',
                        'environment_local_application_data': profile / 'AppData/Local'}
            if any(not isinstance(facts.get(key), str) or not Path(facts[key]).is_absolute()
                   or Path(facts[key]).resolve() != path for key, path in expected.items()):
                raise GuiIdentityError('hcl_profile_paths_mismatch', 'Actual profile and environment paths disagree with the current SID')
            temporary = Path(facts['temporary_directory'])
            if not temporary.is_absolute() or not temporary.resolve().is_relative_to(profile / 'AppData/Local/Temp'):
                raise GuiIdentityError('hcl_profile_paths_mismatch', 'Temporary files must remain in the current-SID private Temp namespace')
            unlinked(temporary)
            executable = Path(hcl['executable_path'])
            expected_executable = self.installation_root / 'SimwareClient.exe'
            unlinked(executable)
            unlinked(expected_executable)
            if not executable.is_absolute() or executable.resolve() != expected_executable.resolve() or not executable.is_file():
                raise GuiIdentityError('hcl_executable_mismatch', 'HCL does not match the configured SimwareClient executable')
            created = hcl['creation_time']
            if not isinstance(created, str) or datetime.fromisoformat(created.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('HCL process creation time is unknown')
            broker_executable = Path(broker['executable_path'])
            unlinked(broker_executable)
            if (not broker_executable.is_absolute() or not broker_executable.is_file()
                    or broker_executable.resolve() != (self.installation_root / 'SimwareWrapper.exe').resolve()):
                raise GuiIdentityError('backend_executable_mismatch', 'Backend listener does not match the configured SimwareWrapper')
            broker_created = broker['creation_time']
            if not isinstance(broker_created, str) or datetime.fromisoformat(broker_created.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('Backend process creation time is unknown')
            identity = {'owner_sid': sid, 'profile_directory': str(profile), 'hcl_pid': hcl_pid,
                        'creation_time': created, 'session_id': hcl['session_id'],
                        'executable_path': str(executable.resolve()),
                        'executable_file_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                        'caller_elevated': False, 'hcl_elevated': False,
                        'hcl_environment_verified': False, 'gui_backend_connection_verified': False,
                        'broker': {'pid': broker['pid'], 'creation_time': broker_created, 'port': self.backend_port,
                                   'owner_sid': sid, 'elevated': False, 'executable_path': str(broker_executable.resolve()),
                                   'executable_file_sha256': hashlib.sha256(broker_executable.read_bytes()).hexdigest()}}
            identity['identity_key'] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            return identity
        except GuiIdentityError:
            raise
        except (KeyError, OSError, ValueError, TypeError, ConsoleError) as exc:
            raise GuiIdentityError('gui_process_identity_unknown', 'HCL principal, profile or process identity is unknown') from exc

    def prepare(self, action, document, stage_operation_id, hcl_pid):
        identity = self.probe(hcl_pid)
        key = (identity['identity_key'], str(document.net_path), stage_operation_id)
        if action == 'save' and key in self.leases:
            return {**identity, 'namespace_lease': self.leases[key], 'lease_reused': True}
        runtime = self.runtime_observer(Path(identity['profile_directory']))
        profile = Path(identity['profile_directory'])
        if (not isinstance(runtime, dict) or runtime.get('status') != 'observed' or runtime.get('errors')
                or not isinstance(runtime.get('files'), list) or not isinstance(runtime.get('registered_machines'), list)
                or Path(runtime.get('profile_directory', '')).resolve() != profile
                or Path(runtime.get('runtime_root', '')).resolve() != profile / 'HCL VMs'
                or Path(runtime.get('registry_file', '')).resolve() != profile / '.VirtualBox/VirtualBox.xml'):
            raise GuiIdentityError('runtime_namespace_unknown', 'Current-user runtime assets could not be inventoried')
        # The root bootstrap lock is permitted; every other file or registry
        # entry could be an original asset affected by HCL cleanup.
        foreign_files = [row for row in runtime.get('files', []) if row.get('path', '').casefold() != 'lock.ini']
        root = profile / 'HCL VMs'
        existing_directories = root.is_dir() and any(path.is_dir() for path in root.iterdir())
        if foreign_files or existing_directories or runtime.get('registered_machines'):
            raise GuiIdentityError('existing_runtime_assets_protected',
                                   'GUI activation requires a fresh runtime namespace; existing VM files/registrations are protected')
        if len(self.leases) >= 64:
            raise GuiIdentityError('gui_lease_capacity', 'The process-local GUI lease limit was reached')
        lease = {'origin': 'fresh_current_sid_namespace_before_gui_action',
                 'stage_operation_id': stage_operation_id, 'project_file': str(document.net_path),
                 'runtime_root': runtime['runtime_root'], 'registry_file': runtime['registry_file'],
                 'identity_key': identity['identity_key'], 'native_origin_verified': self.native_dependencies,
                 'runtime_isolation_verified': False}
        self.leases[key] = lease
        return {**identity, 'namespace_lease': lease, 'lease_reused': False}
