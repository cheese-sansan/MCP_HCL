import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from mcp_hcl.environment import preflight


class Environment050Tests(unittest.TestCase):
    def test_retired_boot_entry_never_invokes_bcd(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/hcl_lab_boot.ps1'
        text = script.read_text()
        self.assertNotIn('bcdedit', text.lower())
        for action in ('Create', 'Arm', 'Disarm', 'Remove'):
            result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script), '-Action', action], capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Retired', result.stderr)

    def test_unknown_observations_cannot_be_ready(self):
        def run(*args, **kwargs): return SimpleNamespace(returncode=1, stdout=b'')
        with patch('mcp_hcl.environment.os.name', 'nt'), patch('mcp_hcl.catalog.HclCatalog.devices', return_value={'devices':[]}):
            result = preflight(Path('.'), runner=run)
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['runtime_ready'])

    def test_processes_and_guest_lists_are_not_console_evidence(self):
        facts = dict(hypervisor_present=True, gui_running=True, wrapper_running=True,
                     external_console_present=False, virtualbox_directory='D:/VirtualBox', virtualbox_version='6.0.14')
        def run(args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=json.dumps(facts).encode() if args[0]=='powershell.exe' else b'"guest" {id}')
        with patch('mcp_hcl.environment.os.name', 'nt'), patch('mcp_hcl.catalog.HclCatalog.devices', return_value={'devices':[]}):
            result = preflight(Path('.'), runner=run)
        self.assertEqual(result['status'], 'observed')
        self.assertFalse(result['runtime_ready'])
        self.assertFalse(result['full_live_gate_passed'])
