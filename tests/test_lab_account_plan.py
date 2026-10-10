"""Account plan parsing and read-only preview; mutating cmdlets are blocked."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class AccountPlanTests(unittest.TestCase):
    script = Path(__file__).resolve().parents[1]/'scripts/hcl_lab_account.ps1'

    def run_preview(self, directory, account='MCPHCLLab'):
        # Dynamic guards ensure Preview cannot accidentally call a real
        # account mutation even if future edits change its dispatch.
        script = str(self.script).replace("'","''")
        directory = str(directory).replace("'","''")
        command = "$ErrorActionPreference='Stop'; "
        for name in ('New-LocalUser','Add-LocalGroupMember','Disable-LocalUser','Remove-LocalUser'):
            command += "function " + name + " { throw 'Account mutation forbidden in Preview test' }; "
        command += f"& '{script}' -Action Preview -AccountName '{account}' -OutputRoot '{directory}'"
        return subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,timeout=10)

    def test_script_parses_with_windows_powershell(self):
        script = str(self.script).replace("'","''")
        command = f"$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}"
        result = subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_preview_writes_new_receipt_without_account_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_preview(Path(temporary))
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            paths = list(Path(temporary).rglob('result.json'))
            self.assertEqual(len(paths),1)
            receipt = json.loads(paths[0].read_text(encoding='utf-8-sig'))
            self.assertEqual(receipt['kind'],'lab_account_plan')
            self.assertEqual(receipt['proposed_group_sid'],'S-1-5-32-545')
            self.assertFalse(receipt['changes_applied'])
            self.assertFalse(receipt['runtime_isolation_verified'])

    def test_reserved_builtin_account_is_rejected_without_mutations(self):
        result = subprocess.run(['powershell.exe','-NoProfile','-Command',
            "(Get-LocalUser | Where-Object {$_.SID.Value -match '-500$'} | Select-Object -First 1).Name"],capture_output=True,timeout=10)
        # The local administrator name can be localized; use only an ASCII
        # valid name supported by this conservative plan interface.
        name = result.stdout.decode('utf-8',errors='replace').strip()
        import re
        if result.returncode or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,19}',name):
            self.skipTest('Built-in administrator name is outside the supported plan naming grammar')
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_preview(Path(temporary),name)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            receipt = json.loads(next(Path(temporary).rglob('result.json')).read_text(encoding='utf-8-sig'))
            self.assertEqual(receipt['status'],'rejected')
            self.assertTrue(receipt['account_exists'])
            self.assertFalse(receipt['changes_applied'])
