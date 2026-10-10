import copy
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from software_fixtures import SoftwareCase

from mcp_hcl.gui_identity import GuiIdentityError, GuiIdentityGuard, GuiProfileLease, ps_literal


def gui_fixture(root):
    profile = root / "profile"
    (profile / "AppData/Local/Temp").mkdir(parents=True, exist_ok=True)
    install = root / "gui-install"
    install.mkdir(exist_ok=True)
    for name in ("SimwareClient.exe", "SimwareWrapper.exe"):
        (install / name).write_bytes(b"synthetic")
    sid = "S-1-5-21-123"
    created = "2026-10-11T00:00:00Z"
    facts = {
        "schema_version": 1,
        "actual_sid": sid,
        "cim_profile_directory": str(profile),
        "profile_directory": str(profile),
        "environment_profile": str(profile),
        "application_data": str(profile / "AppData/Roaming"),
        "environment_application_data": str(profile / "AppData/Roaming"),
        "local_application_data": str(profile / "AppData/Local"),
        "environment_local_application_data": str(profile / "AppData/Local"),
        "temporary_directory": str(profile / "AppData/Local/Temp"),
        "caller": {"session_id": 1, "elevated": False},
        "hcl": {
            "pid": 17,
            "name": "SimwareClient.exe",
            "owner_result": 0,
            "owner_sid": sid,
            "session_id": 1,
            "elevated": False,
            "creation_time": created,
            "executable_path": str(install / "SimwareClient.exe"),
        },
        "broker": {
            "pid": 18,
            "port": 16600,
            "name": "SimwareWrapper.exe",
            "owner_result": 0,
            "owner_sid": sid,
            "session_id": 1,
            "elevated": False,
            "creation_time": created,
            "executable_path": str(install / "SimwareWrapper.exe"),
        },
    }
    runtime = {
        "status": "observed",
        "errors": [],
        "profile_directory": str(profile),
        "runtime_root": str(profile / "HCL VMs"),
        "registry_file": str(profile / ".VirtualBox/VirtualBox.xml"),
        "files": [],
        "registered_machines": [],
    }

    def collector(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(facts).encode())

    guard = GuiIdentityGuard(
        install, runner=collector, runtime_observer=lambda _: copy.deepcopy(runtime)
    )
    return guard, facts, runtime


class IdentityTests(SoftwareCase):
    def setUp(self):
        super().setUp()
        self.guard, self.facts, self.runtime = gui_fixture(self.root)
        patch(
            "mcp_hcl.gui_identity.windows_powershell",
            return_value=self.root / "synthetic-powershell",
        ).start()

    def document(self):
        return self.store._open(self.project)

    def test_validate_principal_session_tokens_paths_and_listener(self):
        self.assertEqual(self.guard.validate(self.facts, 17)["owner_sid"], self.facts["actual_sid"])
        changes = [
            ("hcl", "owner_sid", "S-1-5-21-456"),
            ("hcl", "owner_result", None),
            ("hcl", "elevated", True),
            ("caller", "elevated", None),
            ("hcl", "session_id", 2),
            ("hcl", "pid", 18),
            ("hcl", "creation_time", "unknown"),
            ("hcl", "executable_path", str(self.root / "wrong.exe")),
            ("broker", "owner_sid", "S-1-5-21-456"),
            ("broker", "elevated", True),
            ("broker", "port", 16601),
            ("broker", "executable_path", str(self.root / "wrong.exe")),
        ]
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                facts = copy.deepcopy(self.facts)
                facts[section][key] = value
                with self.assertRaises(GuiIdentityError):
                    self.guard.validate(facts, 17)
        for key in ("environment_profile", "application_data", "temporary_directory"):
            with self.subTest(key=key):
                facts = copy.deepcopy(self.facts)
                facts[key] = str(self.root)
                with self.assertRaises(GuiIdentityError):
                    self.guard.validate(facts, 17)

    def test_identity_key_changes_with_process_listener_and_binary(self):
        before = self.guard.probe(17)["identity_key"]
        for section, key, value in [
            ("hcl", "creation_time", "2026-10-11T01:00:00Z"),
            ("broker", "pid", 19),
        ]:
            with self.subTest(section=section, key=key):
                original = self.facts[section][key]
                self.facts[section][key] = value
                self.assertNotEqual(before, self.guard.probe(17)["identity_key"])
                self.facts[section][key] = original
        Path(self.facts["hcl"]["executable_path"]).write_bytes(b"changed")
        self.assertNotEqual(before, self.guard.probe(17)["identity_key"])

    def test_collector_failure_missing_duplicate_listener_and_custom_port(self):
        for output in (b"{}", b"not json", b"x" * 65537):
            with self.subTest(size=len(output)):
                self.guard.runner = lambda *a, **k: SimpleNamespace(returncode=0, stdout=output)
                with self.assertRaises(GuiIdentityError):
                    self.guard.probe(17)
        self.guard.runner = lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"")
        with self.assertRaises(GuiIdentityError):
            self.guard.probe(17)
        self.guard.backend_port = 16666
        with self.assertRaisesRegex(GuiIdentityError, "16600"):
            self.guard.probe(17)

    def test_fresh_namespace_save_lease_and_restart(self):
        first = self.guard.prepare("open", self.document(), "a" * 32, 17)
        self.assertFalse(first["native_identity_verified"])
        self.assertFalse(first["lease_reused"])
        self.runtime["files"] = [{"path": "disk.vdi"}]
        self.assertTrue(self.guard.prepare("save", self.document(), "a" * 32, 17)["lease_reused"])
        for action, operation in [("open", "a" * 32), ("save", "b" * 32)]:
            with self.subTest(action=action):
                with self.assertRaises(GuiIdentityError):
                    self.guard.prepare(action, self.document(), operation, 17)
        self.guard.leases.clear()
        with self.assertRaises(GuiIdentityError):
            self.guard.prepare("save", self.document(), "a" * 32, 17)

    def test_existing_assets_empty_directory_registry_and_unknown_inventory(self):
        for change in (
            {"files": [{"path": "disk.vdi"}]},
            {"registered_machines": [{"uuid": "same"}]},
            {"status": "unknown"},
            {"files": None},
            {"errors": ["denied"]},
        ):
            with self.subTest(change=change):
                old = copy.deepcopy(self.runtime)
                self.runtime.update(change)
                with self.assertRaises(GuiIdentityError):
                    self.guard.prepare("open", self.document(), "a" * 32, 17)
                self.runtime.clear()
                self.runtime.update(old)
        self.runtime["files"] = [{"path": "lock.ini"}]
        self.assertIn("namespace_lease", self.guard.prepare("open", self.document(), "a" * 32, 17))
        (Path(self.runtime["runtime_root"]) / "empty").mkdir(parents=True)
        with self.assertRaises(GuiIdentityError):
            self.guard.prepare("open", self.document(), "b" * 32, 17)

    def test_shared_profile_lock_is_nonblocking_and_released(self):
        with GuiProfileLease(self.root / "lock-profile"):
            with self.assertRaises(GuiIdentityError):
                GuiProfileLease(self.root / "lock-profile")
        with GuiProfileLease(self.root / "lock-profile"):
            pass

    def test_constant_arguments_unicode_quotes_and_controls(self):
        for value in ("引号 ' ; & $()", "space path"):
            self.assertNotIn(value, ps_literal(value))
        for value in ("a\nb", "a\x00b", "a\tb"):
            with self.assertRaises(GuiIdentityError):
                ps_literal(value)
