"""Account plan parsing and read-only preview; mutating cmdlets are blocked."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class AccountPlanTests(unittest.TestCase):
    script = Path(__file__).resolve().parents[1] / "scripts/hcl_lab_account.ps1"

    def run_preview(self, directory, account="MCPHCLLab"):
        # Dynamic guards ensure Preview cannot accidentally call a real
        # account mutation even if future edits change its dispatch.
        script = str(self.script).replace("'", "''")
        directory = str(directory).replace("'", "''")
        command = "$ErrorActionPreference='Stop'; "
        for name in (
            "New-LocalUser",
            "Add-LocalGroupMember",
            "Disable-LocalUser",
            "Remove-LocalUser",
        ):
            command += (
                "function " + name + " { throw 'Account mutation forbidden in Preview test' }; "
            )
        command += (
            f"& '{script}' -Action Preview -AccountName '{account}' -OutputRoot '{directory}'"
        )
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, timeout=10
        )

    def test_script_parses_with_windows_powershell(self):
        script = str(self.script).replace("'", "''")
        command = f"$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}"
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_preview_writes_new_receipt_without_account_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_preview(Path(temporary))
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            paths = list(Path(temporary).rglob("result.json"))
            self.assertEqual(len(paths), 1)
            receipt = json.loads(paths[0].read_text(encoding="utf-8-sig"))
            self.assertEqual(receipt["kind"], "lab_account_plan")
            self.assertEqual(receipt["proposed_group_sid"], "S-1-5-32-545")
            self.assertFalse(receipt["changes_applied"])
            self.assertFalse(receipt["runtime_isolation_verified"])

    def test_reserved_builtin_account_is_rejected_without_mutations(self):
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-LocalUser | Where-Object {$_.SID.Value -match '-500$'} | Select-Object -First 1).Name",
            ],
            capture_output=True,
            timeout=10,
        )
        # The local administrator name can be localized; use only an ASCII
        # valid name supported by this conservative plan interface.
        name = result.stdout.decode("utf-8", errors="replace").strip()
        import re

        if result.returncode or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,19}", name):
            self.skipTest(
                "Built-in administrator name is outside the supported plan naming grammar"
            )
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_preview(Path(temporary), name)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            receipt = json.loads(
                next(Path(temporary).rglob("result.json")).read_text(encoding="utf-8-sig")
            )
            self.assertEqual(receipt["status"], "rejected")
            self.assertTrue(receipt["account_exists"])
            self.assertFalse(receipt["changes_applied"])


class LabEnvironmentDiagnosticsTests(unittest.TestCase):
    script = Path(__file__).resolve().parents[1] / "scripts/hcl_lab_environment_identity.ps1"

    def fixture(self):
        profile = "C:\\Users\\FreshLab"
        return {
            "sid": "S-1-5-21-111-222-333-1234",
            "standard_account": True,
            "cim_profile": profile,
            "profile": profile,
            "application_data": profile + "\\AppData\\Roaming",
            "local_application_data": profile + "\\AppData\\Local",
            "paths": {
                "USERPROFILE": profile,
                "HOME": None,
                "HOMEDRIVE": "C:",
                "HOMEPATH": "\\Users\\FreshLab",
                "APPDATA": profile + "\\AppData\\Roaming",
                "LOCALAPPDATA": profile + "\\AppData\\Local",
                "TEMP": profile + "\\AppData\\Local\\Temp",
                "TMP": profile + "\\AppData\\Local\\Temp\\session",
                "VBOX_USER_HOME": None,
                "SECRET_TOKEN": "must-never-be-exported",
            },
        }

    def assess(self, observations, expected_profile="C:\\Users\\FreshLab"):
        import base64

        encoded = base64.b64encode(json.dumps(observations).encode()).decode()
        script = str(self.script).replace("'", "''")
        expected_profile = expected_profile.replace("'", "''")
        command = (
            "$ErrorActionPreference='Stop';$t=$null;$e=$null;"
            f"$ast=[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e);"
            "if($e.Count){throw 'Script parse failed'};"
            "function Get-CimInstance {throw 'Native call forbidden'};"
            "function Start-Process {throw 'Native call forbidden'};"
            "function New-LocalUser {throw 'Native call forbidden'};"
            "$functions=$ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$true);"
            "foreach($f in $functions){if($f.Name -in @('Normalize-LabPath','Test-LabEnvironmentObservation')){"
            ". ([ScriptBlock]::Create($f.Extent.Text))}};"
            f"$facts=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json;"
            "Test-LabEnvironmentObservation -Observation $facts "
            f"-ExpectedSid 'S-1-5-21-111-222-333-1234' -ExpectedProfile '{expected_profile}'|ConvertTo-Json -Depth 8"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return json.loads(result.stdout.decode("utf-8-sig"))

    def test_complete_observation_reports_fields_without_authorizing_activation(self):
        result = self.assess(self.fixture())
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["environment_paths_match"])
        self.assertFalse(result["activation_allowed"])
        self.assertFalse(result["runtime_isolation_verified"])
        self.assertFalse(result["full_live_gate_passed"])
        self.assertEqual(len(result["checks"]), 14)
        self.assertNotIn("must-never-be-exported", json.dumps(result))

    def test_each_environment_mismatch_is_named_and_all_failures_are_preserved(self):
        facts = self.fixture()
        fields = ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "HOME", "VBOX_USER_HOME")
        for field in fields:
            facts["paths"][field] = "C:\\Users\\Other\\wrong"
        facts["paths"]["HOMEPATH"] = "\\Users\\Other"
        result = self.assess(facts)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(set(result["blockers"]), {*fields, "HOMEDRIVE+HOMEPATH"})
        self.assertTrue(
            all(row["observed"] for row in result["checks"] if row["status"] == "failed")
        )

    def test_missing_fields_are_unknown_instead_of_passing(self):
        facts = self.fixture()
        del facts["paths"]["TMP"]
        facts["cim_profile"] = None
        result = self.assess(facts)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["environment_paths_match"])
        self.assertEqual(set(result["unknown_fields"]), {"profile.cim", "TMP"})

    def test_sid_and_standard_token_are_bound_to_current_receipt(self):
        facts = self.fixture()
        facts["sid"] = "S-1-5-21-111-222-333-1006"
        facts["standard_account"] = False
        result = self.assess(facts)
        self.assertEqual(set(result["blockers"]), {"identity.sid", "identity.standard_account"})
        self.assertEqual(result["status"], "rejected")

    def test_temp_prefix_and_relative_paths_cannot_masquerade_as_private_paths(self):
        facts = self.fixture()
        facts["paths"]["TEMP"] += "-shared"
        facts["paths"]["TMP"] = "relative\\Temp"
        result = self.assess(facts)
        self.assertIn("TEMP", result["blockers"])
        self.assertIn("TMP", result["unknown_fields"])
        self.assertFalse(result["environment_paths_match"])

    def test_optional_home_and_temp_subdirectory_accept_case_and_separator_variation(self):
        facts = self.fixture()
        facts["paths"]["HOME"] = "c:/users/freshlab/"
        facts["paths"]["TEMP"] = "c:/users/freshlab/AppData/Local/Temp/session/"
        self.assertEqual(self.assess(facts)["status"], "verified")

    def test_real_short_temp_alias_refers_to_the_same_profile(self):
        import ctypes

        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "Long Lab Profile"
            temp = profile / "AppData/Local/Temp"
            temp.mkdir(parents=True)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            kernel.GetShortPathNameW.restype = ctypes.c_uint
            buffer = ctypes.create_unicode_buffer(32768)
            self.assertGreater(kernel.GetShortPathNameW(str(temp), buffer, len(buffer)), 0)
            if buffer.value.casefold() == str(temp).casefold():
                self.skipTest("This filesystem did not provide a distinct 8.3 alias")
            facts = json.loads(
                json.dumps(self.fixture()).replace(
                    "C:\\\\Users\\\\FreshLab", str(profile).replace("\\", "\\\\")
                )
            )
            facts["paths"]["HOMEDRIVE"] = profile.drive
            facts["paths"]["HOMEPATH"] = str(profile)[len(profile.drive) :]
            facts["paths"]["TEMP"] = buffer.value
            facts["paths"]["TMP"] = buffer.value
            result = self.assess(facts, expected_profile=str(profile))
            self.assertEqual(result["status"], "verified")
            self.assertFalse(result["activation_allowed"])

    def test_non_string_paths_and_non_boolean_token_are_unknown(self):
        facts = self.fixture()
        facts["standard_account"] = "true"
        facts["paths"]["TMP"] = {"secret": "must-never-be-exported"}
        result = self.assess(facts)
        self.assertEqual(set(result["unknown_fields"]), {"identity.standard_account", "TMP"})
        self.assertNotIn("must-never-be-exported", json.dumps(result))

    def test_collector_emits_structured_failure_and_nonzero_exit_without_native_writes(self):
        import os

        script = str(self.script).replace("'", "''")
        command = "$ErrorActionPreference='Stop';"
        for name in ("Start-Process", "New-LocalUser", "Remove-LocalUser", "Set-Content"):
            command += f"function {name} {{throw 'Native write forbidden'}};"
        command += (
            "function Get-CimInstance {param($ClassName,$Filter,$ErrorAction) "
            "[pscustomobject]@{LocalPath='C:\\Users\\FreshLab'}};"
            f"& '{script}' -ExpectedSid 'S-1-5-21-111-222-333-1234' "
            "-ExpectedProfile 'C:\\Users\\FreshLab';exit $LASTEXITCODE"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            timeout=10,
            env=dict(os.environ, MCP_TEST_SECRET="must-never-be-exported"),
        )
        self.assertEqual(result.returncode, 2, result.stderr.decode(errors="replace"))
        receipt = json.loads(result.stdout.decode("utf-8-sig"))
        self.assertEqual(receipt["status"], "rejected")
        self.assertIn("identity.sid", receipt["blockers"])
        self.assertEqual(len(receipt["checks"]), 14)
        self.assertFalse(receipt["activation_allowed"])
        self.assertNotIn("must-never-be-exported", result.stdout.decode(errors="replace"))


class LabObservationLauncherTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def run_command(self, command):
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            timeout=10,
        )
        return result

    def builder(self):
        script = str(self.root / "scripts/hcl_lab_observation_launch.ps1").replace("'", "''")
        return (
            "$ErrorActionPreference='Stop';"
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);$t=$null;$e=$null;"
            f"$ast=[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e);"
            "if($e.Count){throw 'Launcher parse failed'};"
            "$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] "
            "-and $n.Name -eq 'New-LabObservationCommand'},$true);"
            ". ([ScriptBlock]::Create($f.Extent.Text));"
        )

    def test_hash_checked_command_preserves_unicode_and_quoted_constants(self):
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            observer = Path(temporary) / "observer's copy.ps1"
            observer.write_text(
                "param($ExpectedSid,$ExpectedProfile) "
                "@{sid=$ExpectedSid;profile=$ExpectedProfile}|ConvertTo-Json",
                encoding="utf-8-sig",
            )
            path = str(observer).replace("'", "''")
            digest = hashlib.sha256(observer.read_bytes()).hexdigest()
            command = self.builder() + (
                f"$c=New-LabObservationCommand -Reader '{path}' -Sha256 '{digest}' "
                "-Sid 'S-1-5-21-1-2-3-1009' -Profile 'C:\\Users\\测试'';$(invalid)';"
                "& ([ScriptBlock]::Create($c))"
            )
            result = self.run_command(command)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(
                json.loads(result.stdout.decode("utf-8-sig")),
                {"sid": "S-1-5-21-1-2-3-1009", "profile": "C:\\Users\\测试';$(invalid)"},
            )

    def test_changed_observer_never_executes(self):
        with tempfile.TemporaryDirectory() as temporary:
            observer = Path(temporary) / "observer.ps1"
            observer.write_text("throw 'observer unexpectedly executed'", encoding="utf-8")
            path = str(observer).replace("'", "''")
            command = self.builder() + (
                f"$c=New-LabObservationCommand -Reader '{path}' -Sha256 '{'0' * 64}' "
                "-Sid 'S-1-5-21-1-2-3-1009' -Profile 'C:\\Users\\Lab';"
                "& ([ScriptBlock]::Create($c))"
            )
            result = self.run_command(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Observer hash changed", result.stderr)
            self.assertNotIn(b"observer unexpectedly executed", result.stderr)

    def test_plan_only_binds_fresh_receipt_without_password_or_process_launch(self):
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            directory = str(Path(temporary)).replace("'", "''")
            observer = self.root / "scripts/hcl_lab_environment_identity.ps1"
            digest = hashlib.sha256(observer.read_bytes()).hexdigest()
            launcher = str(self.root / "scripts/hcl_lab_observation_launch.ps1").replace("'", "''")
            command = (
                "$ErrorActionPreference='Stop';"
                "function Start-Process {throw 'Process launch forbidden'};"
                "function Read-Host {throw 'Credential input forbidden'};"
                "function Get-LocalUser {param($SID) [pscustomobject]@{Name='FreshLab';Enabled=$true;"
                "SID=[pscustomobject]@{Value='S-1-5-21-1-2-3-1009'};Description='MCP_HCL lab "
                + "a"
                * 32
                + "'}};"
                "function Get-LocalGroupMember {param($SID) @()};"
                "function Get-CimInstance {param($ClassName,$Filter) @()};"
                "$r=@{schema_version=1;kind='lab_account_creation';status='created_standard_account';"
                "owner_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
                "account_name='FreshLab';account_sid='S-1-5-21-1-2-3-1009';description='MCP_HCL lab "
                + "a"
                * 32
                + f"'}};$r|ConvertTo-Json|Set-Content '{directory}/creation.json' -Encoding UTF8;"
                f"& '{launcher}' -CreationRecord '{directory}/creation.json' "
                f"-ExpectedProfile 'C:\\Users\\FreshLab' -ObserverSha256 '{digest}' "
                f"-OutputRoot '{directory}/receipts' -PlanOnly"
            )
            result = self.run_command(command)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            receipt = json.loads(result.stdout.decode("utf-8-sig"))
            self.assertEqual(receipt["phase"], "prepared_not_executed")
            self.assertEqual(receipt["account_sid"], "S-1-5-21-1-2-3-1009")
            self.assertFalse(receipt["activation_allowed"])
            self.assertFalse(receipt["hcl_or_guest_started"])
            self.assertFalse(receipt["profile_ready"])
            self.assertFalse(receipt["profile_loaded_for_child"])
            self.assertEqual(receipt["working_directory"], "C:\\Users\\FreshLab")

    def guarded_launch(self, *, initialized, stale_marker=False):
        import hashlib

        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            profile.mkdir()
            literal_profile = str(profile).replace("'", "''")
            directory = str(Path(temporary)).replace("'", "''")
            launcher = str(self.root / "scripts/hcl_lab_observation_launch.ps1").replace("'", "''")
            digest = hashlib.sha256(
                (self.root / "scripts/hcl_lab_environment_identity.ps1").read_bytes()
            ).hexdigest()
            marker = "MCP_HCL lab " + "a" * 32
            command = (
                "$ErrorActionPreference='Stop';function Read-Host {throw 'Credential prompt forbidden'};"
                "function Get-LocalUser {param($SID) [pscustomobject]@{Name='FreshLab';Enabled=$true;"
                "SID=[pscustomobject]@{Value='S-1-5-21-1-2-3-1009'};Description='"
                + ("wrong marker" if stale_marker else marker)
                + "'}};function Get-LocalGroupMember {param($SID) @()};"
            )
            command += (
                "function Get-CimInstance {param($ClassName,$Filter) "
                + (f"[pscustomobject]@{{LocalPath='{literal_profile}'}}" if initialized else "@()")
                + "};"
            )
            command += (
                "function Start-Process {param($WorkingDirectory) "
                f"if($WorkingDirectory -ne '{literal_profile}'){{throw 'Wrong working directory'}};"
                "$p=[pscustomobject]@{Id=888;Handle=[IntPtr]1};$p|Add-Member ScriptMethod WaitForExit {param($ms) $false};$p};"
                "$r=@{schema_version=1;kind='lab_account_creation';status='created_standard_account';"
                "owner_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
                f"account_name='FreshLab';account_sid='S-1-5-21-1-2-3-1009';description='{marker}'}};"
                f"$r|ConvertTo-Json|Set-Content '{directory}/creation.json' -Encoding UTF8;"
                "$s=New-Object Security.SecureString;$s.AppendChar([char]65);"
                f"& '{launcher}' -CreationRecord '{directory}/creation.json' "
                f"-ExpectedProfile '{literal_profile}' -ObserverSha256 '{digest}' "
                f"-OutputRoot '{directory}/receipts' -Password $s;exit $LASTEXITCODE"
            )
            return self.run_command(command)

    def test_timeout_reports_same_child_and_never_claims_profile_or_runtime_success(self):
        result = self.guarded_launch(initialized=True)
        self.assertEqual(result.returncode, 3, result.stderr.decode(errors="replace"))
        receipt = json.loads(result.stdout.decode("utf-8-sig"))
        self.assertEqual(receipt["phase"], "running_after_observation_timeout")
        self.assertEqual(receipt["pid"], 888)
        self.assertTrue(receipt["profile_load_requested"])
        self.assertFalse(receipt["profile_loaded_for_child"])
        self.assertFalse(receipt["full_live_gate_passed"])

    def test_uninitialized_profile_rejects_before_credentials_or_launch(self):
        result = self.guarded_launch(initialized=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Initialize the recorded account profile", result.stderr)
        self.assertNotIn(b"Credential prompt forbidden", result.stderr)

    def test_same_sid_with_wrong_creation_marker_is_rejected(self):
        result = self.guarded_launch(initialized=True, stale_marker=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Lab account creation identity changed", result.stderr)

    def test_exit_code_is_observed_from_exact_retained_handle(self):
        script = str(self.root / "scripts/hcl_lab_observation_launch.ps1").replace("'", "''")
        command = (
            "$ErrorActionPreference='Stop';$t=$null;$e=$null;"
            f"$ast=[Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e);"
            "$f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] "
            "-and $n.Name -eq 'Get-LabChildExitCode'},$true);"
            ". ([ScriptBlock]::Create($f.Extent.Text));"
            "$p=Start-Process (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile','-Command','exit 7') -WindowStyle Hidden -PassThru;"
            "$handle=$p.Handle;$p.WaitForExit();try{@{code=(Get-LabChildExitCode $handle)}|ConvertTo-Json}finally{$p.Dispose()}"
        )
        result = self.run_command(command)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(json.loads(result.stdout.decode("utf-8-sig"))["code"], 7)
