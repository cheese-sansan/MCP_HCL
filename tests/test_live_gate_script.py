from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell required"
)
class GateScriptPreflightTests(unittest.TestCase):
    def test_utf8_metadata_and_failed_receipts_survive_retry(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        work = workspace / "work"
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gate-test-", dir=work) as temporary:
            root = Path(temporary)
            project = root / "project"
            configs = project / "DeviceConfig"
            configs.mkdir(parents=True)
            net = project / "test.net"
            net.write_text(
                f"version = 5.10.3\n[vbox 127.0.0.1:16600]\n    workingdir = {project}\n",
                encoding="utf-8",
            )
            original_net = net.read_bytes()
            (configs / "核心交换机.cfg").write_text("sysname 核心交换机\n", encoding="utf-8")
            metadata = project / "project.json"
            metadata.write_text("invalid JSON", encoding="utf-8")
            output = root / "receipts"
            command = [
                shutil.which("powershell.exe"),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(workspace / "scripts/hcl_open_gate.ps1"),
                "-HclPid",
                "0",
                "-ProjectFile",
                str(net),
                "-OutputDirectory",
                str(output),
                "-ValidateOnly",
            ]
            failed = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(failed.returncode, 0, failed.stderr)
            first = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(first["status"], "rejected")
            self.assertEqual(first["error"], "Project metadata is not valid UTF-8 JSON")
            first_path = Path(first["receipt_directory"]) / "result.json"
            failure_bytes = first_path.read_bytes()
            metadata.write_text(
                json.dumps(
                    {
                        "projectInfo": {"name": "中文隔离工程"},
                        "deviceInfoList": [
                            {
                                "resourceName": "核心交换机",
                                "configPath": "DeviceConfig\\核心交换机.cfg",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            passed = subprocess.run(command, capture_output=True, timeout=15)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            latest = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["status"], "verified")
            self.assertEqual(latest["verified_scope"], "isolated_project_preconditions_only")
            self.assertFalse(latest["full_live_gate_passed"])
            self.assertFalse(latest["checks"]["project_opened"])
            self.assertNotEqual(first["operation_id"], latest["operation_id"])
            self.assertEqual(first_path.read_bytes(), failure_bytes)
            self.assertEqual(net.read_bytes(), original_net)


if __name__ == "__main__":
    unittest.main()
