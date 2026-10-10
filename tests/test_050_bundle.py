import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from mcp_hcl.lab_bundle import (
    WIRED_REQUEST,
    WIRELESS_SPEC,
    audit_bundle,
    prepare_bundle,
    tested_dependencies,
)


def wheel(path, version="0.5.0"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "mcp_hcl-" + version + ".dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: mcp-hcl\nVersion: {version}\n",
        )


class Bundle050Tests(unittest.TestCase):
    def test_prepare_audit_retry_and_artifact_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "mcp_hcl-0.5.0-py3-none-any.whl"
            wheel(archive)
            before = archive.read_bytes()
            first = prepare_bundle(archive, root / "out", "Acceptance", "key")
            second = prepare_bundle(archive, root / "out", "Acceptance", "key")
            self.assertEqual(first["operation_id"], second["operation_id"])
            self.assertTrue(second["replayed"])
            directory = Path(first["artifact_directory"])
            self.assertFalse(audit_bundle(directory)["runtime_ready"])
            self.assertEqual(
                json.loads((directory / "wireless-test.json").read_text())["devices"]["Phone"], 2
            )
            self.assertIn("cryptography", "\n".join(tested_dependencies()))
            self.assertEqual(before, archive.read_bytes())
            (directory / "wired-request.json").write_text("{}")
            with self.assertRaises(ValueError):
                audit_bundle(directory)
            self.assertEqual(
                prepare_bundle(archive, root / "out", "Acceptance", "key")["errors"][0]["code"],
                "artifact_changed",
            )

    def test_wrong_wheel_and_overwrite_fail_without_vendor_or_host_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "old.whl"
            wheel(archive, "0.4.0")
            with self.assertRaises(ValueError):
                prepare_bundle(archive, root / "out", "Wrong")
            wheel(archive)
            prepare_bundle(archive, root / "out", "Right")
            with self.assertRaises(ValueError):
                prepare_bundle(archive, root / "out", "Right")
            self.assertEqual(WIRED_REQUEST["pcs_per_lan"], 2)
            self.assertEqual(WIRELESS_SPEC["security_required"], "wpa2_psk")

    def test_wireless_gate_never_substitutes_open_for_secure(self):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "mcp_hcl.lab_bundle", "accept-wireless"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["errors"][0]["code"], "wireless_acceptance_not_ready"
        )

    def test_cli_validation_error_does_not_echo_private_unknown_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.json"
            spec.write_text(json.dumps({"psk": "private-unexpected-value"}))
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mcp_hcl.lab_bundle",
                    "collect",
                    "--spec",
                    str(spec),
                    "--output",
                    str(Path(tmp) / "out"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("private-unexpected-value", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
