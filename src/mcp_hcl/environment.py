"""Read-only environment observations; no boot, security or guest mutations."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path


def preflight(installation: Path, *, runner=subprocess.run) -> dict:
    result = {'scope': 'read_only_environment_observations', 'changes_applied': False,
              'runtime_ready': False, 'full_live_gate_passed': False, 'observations': {}, 'errors': []}
    observations = result['observations']
    if os.name != 'nt':
        result['errors'].append({'code': 'windows_required', 'message': 'Native HCL observations require Windows'})
        result['status'] = 'unknown'
        return result
    query = """$ErrorActionPreference='Stop';
$v=Get-ItemProperty 'HKLM:\\SOFTWARE\\Oracle\\VirtualBox';
$p=@(Get-CimInstance Win32_Process | Select-Object -ExpandProperty Name);
@{hypervisor_present=(Get-CimInstance Win32_ComputerSystem).HypervisorPresent;
virtualbox_version=$v.Version;virtualbox_directory=$v.InstallDir;
gui_running=($p -contains 'SimwareClient.exe');wrapper_running=($p -contains 'SimwareWrapper.exe');
external_console_present=([bool](@($p | Where-Object {$_ -in @('putty.exe','SimwareMultiCC.exe')}).Count))} | ConvertTo-Json -Compress"""
    try:
        checked = runner(['powershell.exe', '-NoProfile', '-Command', query], capture_output=True, timeout=15)
        if checked.returncode: raise ValueError('Windows observation query failed')
        facts = json.loads(checked.stdout.decode('utf-8-sig'))
        for key in ('hypervisor_present', 'gui_running', 'wrapper_running', 'external_console_present'):
            if type(facts.get(key)) is not bool: raise ValueError(f'Unknown observation: {key}')
        observations.update(facts)
        executable = Path(facts['virtualbox_directory']) / 'VBoxManage.exe'
        running = runner([str(executable), 'list', 'runningvms'], capture_output=True, timeout=12)
        if running.returncode: raise ValueError('Running guest observation failed')
        observations['running_guests'] = running.stdout.decode('utf-8-sig').splitlines()
        observations['guest_observation_complete'] = True
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        result['errors'].append({'code': 'environment_unknown', 'message': str(exc)})
    from mcp_hcl.catalog import HclCatalog
    try:
        models = HclCatalog(installation).devices()['devices']
        observations['installation'] = {'path': str(installation), 'models': [m['model'] for m in models],
                                       'missing_cli_defaults': [m['model'] for m in models if not m['default_interfaces']]}
        client=installation/'SimwareClient.exe'
        observations['installation']['hcl_version']={'value':None,'status':'unknown'}
        try:
            import win32api
            info=win32api.GetFileVersionInfo(str(client),'\\')
            high,low=info['FileVersionMS'],info['FileVersionLS']
            observations['installation']['hcl_version']={'value':f'{high>>16}.{high&65535}.{low>>16}.{low&65535}','status':'observed_file_version'}
        except Exception:
            # Many HCL binaries carry no version resource. Never guess from a
            # user-supplied version label or a bundled guide's older version.
            pass
    except (OSError, ValueError) as exc:
        result['errors'].append({'code': 'catalog_unavailable', 'message': str(exc)})
    result['status'] = 'unknown' if result['errors'] else 'observed'
    result['remaining'] = ['Exact staged-project GUI identity', 'Expected guest identities',
                           'Exclusive complete native console readbacks', 'Model and mapping evidence']
    return result
