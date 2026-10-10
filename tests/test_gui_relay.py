from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from software_fixtures import inline_arguments
from test_gui_identity import gui_fixture
from test_mcp_contract import build_fixture, call, mcp_session

from mcp_hcl.gui_relay import HclGuiRelay
from mcp_hcl.project import ProjectStore


class GuiRelayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = build_fixture(Path(self.temporary.name))
        self.store = ProjectStore([self.paths["root"]], self.paths["output"])
        self.staged = self.store.stage_copy(str(self.paths["project"]), "GuiCopy")
        self.commands = []
        self.guard, self.facts, self.runtime = gui_fixture(Path(self.temporary.name))
        self.power = patch(
            "mcp_hcl.gui_identity.windows_powershell",
            return_value=Path(self.temporary.name) / "fake-powershell",
        )
        self.power.start()
        self.addCleanup(self.power.stop)
        self.native = patch(
            "subprocess.run", side_effect=AssertionError("Unexpected native GUI subprocess")
        )
        self.native.start()
        self.addCleanup(self.native.stop)

    def runner(
        self, *, failure=None, wrong_project=False, validate_only=False, wrong_caption=False
    ):
        def run(command):
            self.commands.append(command)
            if failure:
                raise failure
            arguments = inline_arguments(command)
            output = Path(arguments["OutputDirectory"])
            output.mkdir(parents=True)
            receipt = {
                "operation_id": "a" * 32,
                "status": "partial",
                "hcl_pid": 17,
                "project_file": "C:/wrong/project.net"
                if wrong_project
                else self.staged["project_file"],
                "operation": "isolated_project_open"
                if arguments["action"] == "open"
                else "isolated_project_save",
                "validate_only": validate_only,
                "active_project_caption": f"HCL - {'GuiCopyExtra' if wrong_caption else 'GuiCopy'} [{self.staged['project_directory']}]",
                "checks": {
                    key: True
                    for key in (
                        "project_preconditions",
                        "process_identity",
                        "project_opened",
                        "canvas_project_identity",
                        "save_invoked",
                        "project_readback",
                    )
                },
            }
            (output / "result.json").write_text(json.dumps(receipt), encoding="utf-8")
            return SimpleNamespace(returncode=0)

        return run

    def test_disabled_relay_does_not_read_or_invoke_anything(self):
        relay = HclGuiRelay(self.store, runner=self.runner(), identity_guard=self.guard)
        result = relay.execute("open", "does-not-exist", 17)
        self.assertEqual(result["errors"][0]["code"], "writes_disabled")
        self.assertEqual(self.commands, [])

    def test_original_project_and_missing_or_forged_stage_marker_are_rejected(self):
        relay = HclGuiRelay(
            self.store, writes_enabled=True, runner=self.runner(), identity_guard=self.guard
        )
        result = relay.execute("open", str(self.paths["project"]), 17)
        self.assertEqual(result["errors"][0]["code"], "original_project_protected")
        marker = Path(self.staged["project_directory"]) / "MCPArtifacts/stage-receipt.json"
        marker.write_text("[]")
        self.assertEqual(
            relay.execute("open", self.staged["project_directory"], 17)["errors"][0]["code"],
            "invalid_stage_receipt",
        )
        marker.unlink()
        self.assertEqual(
            relay.execute("open", self.staged["project_directory"], 17)["errors"][0]["code"],
            "stage_receipt_required",
        )
        self.assertEqual(self.commands, [])

    def test_open_and_save_have_distinct_no_boot_actions_and_limited_evidence(self):
        relay = HclGuiRelay(
            self.store, writes_enabled=True, runner=self.runner(), identity_guard=self.guard
        )
        for action in ("open", "save"):
            result = relay.execute(action, self.staged["project_directory"], 17)
            self.assertEqual(result["status"], "output_received")
            self.assertFalse(result["project_identity_verified"])
            self.assertTrue(result["protocol_project_identity_verified"])
            self.assertFalse(result["live_canvas_verified"])
            self.assertFalse(result["guest_boot_verified"])
            self.assertFalse(result["configuration_verified"])
            self.assertFalse(result["full_live_gate_passed"])
            self.assertEqual(result["source_stage_operation_id"], self.staged["operation_id"])
            self.assertTrue(Path(result["evidence"][0]["source"]).is_file())
        self.assertEqual(inline_arguments(self.commands[0])["action"], "open")
        self.assertEqual(inline_arguments(self.commands[1])["action"], "save")
        self.assertNotEqual(
            inline_arguments(self.commands[0])["OutputDirectory"],
            inline_arguments(self.commands[1])["OutputDirectory"],
        )

    def test_wrong_project_or_preflight_only_receipts_cannot_prove_gui_success(self):
        for kwargs in ({"wrong_project": True}, {"validate_only": True}, {"wrong_caption": True}):
            relay = HclGuiRelay(
                self.store,
                writes_enabled=True,
                runner=self.runner(**kwargs),
                identity_guard=self.guard,
            )
            self.assertEqual(
                relay.execute("open", self.staged["project_directory"], 17)["status"], "unverified"
            )

    def test_timeout_is_not_replayed_and_prior_receipt_cannot_be_reused(self):
        relay = HclGuiRelay(
            self.store,
            writes_enabled=True,
            runner=self.runner(failure=subprocess.TimeoutExpired("powershell", 55)),
            identity_guard=self.guard,
        )
        result = relay.execute("open", self.staged["project_directory"], 17)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(len(self.commands), 1)
        # A successful previous operation is in a different UUID directory.
        successful = HclGuiRelay(
            self.store, writes_enabled=True, runner=self.runner(), identity_guard=self.guard
        ).execute("open", self.staged["project_directory"], 17)
        missing = HclGuiRelay(
            self.store,
            writes_enabled=True,
            runner=lambda command: SimpleNamespace(returncode=0),
            identity_guard=self.guard,
        )
        result = missing.execute("open", self.staged["project_directory"], 17)
        self.assertEqual(result["errors"][0]["code"], "relay_receipt_missing")
        self.assertTrue(Path(successful["evidence"][0]["source"]).is_file())

    def test_actor_arguments_bind_identity_and_observer_hash(self):
        import hashlib
        from importlib.resources import files

        relay = HclGuiRelay(
            self.store, writes_enabled=True, runner=self.runner(), identity_guard=self.guard
        )
        result = relay.execute("open", self.staged["project_directory"], 17)
        arguments = inline_arguments(self.commands[0])
        self.assertEqual(arguments["ExpectedOwnerSid"], self.facts["actual_sid"])
        self.assertEqual(arguments["ExpectedBrokerPid"], "18")
        self.assertEqual(
            arguments["IdentityObserverSha256"],
            hashlib.sha256(
                files("mcp_hcl").joinpath("data/hcl_process_identity.ps1").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(result["verified_scope"], "synthetic_gui_receipt_protocol_only")

    def test_failed_identity_busy_and_changed_after_action_do_not_elevate(self):
        relay = HclGuiRelay(
            self.store, writes_enabled=True, runner=self.runner(), identity_guard=self.guard
        )
        self.facts["hcl"]["elevated"] = True
        result = relay.execute("open", self.staged["project_directory"], 17)
        self.assertEqual(result["errors"][0]["code"], "elevated_gui_unsupported")
        self.assertEqual(self.commands, [])
        self.facts["hcl"]["elevated"] = False
        relay._lock.acquire()
        try:
            self.assertEqual(
                relay.execute("open", self.staged["project_directory"], 17)["errors"][0]["code"],
                "gui_operation_busy",
            )
        finally:
            relay._lock.release()
        original = self.runner()

        def run(command):
            result = original(command)
            self.facts["hcl"]["creation_time"] = "2026-10-11T01:00:00Z"
            return result

        relay.runner = run
        result = relay.execute("open", self.staged["project_directory"], 17)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["errors"][0]["code"], "gui_process_changed_or_unknown")

    def test_actor_identity_check_missing_or_invalid_receipt_and_nonzero_exit(self):
        for mode in ("identity", "structure", "exit"):
            with self.subTest(mode=mode):
                original = self.runner()

                def run(command):
                    process = original(command)
                    path = Path(inline_arguments(command)["OutputDirectory"]) / "result.json"
                    receipt = json.loads(path.read_text())
                    if mode == "identity":
                        receipt["checks"].pop("process_identity")
                    if mode == "structure":
                        receipt = []
                    path.write_text(json.dumps(receipt))
                    return SimpleNamespace(returncode=1) if mode == "exit" else process

                relay = HclGuiRelay(
                    self.store, writes_enabled=True, runner=run, identity_guard=self.guard
                )
                self.assertEqual(
                    relay.execute("open", self.staged["project_directory"], 17)["status"],
                    "unverified",
                )


class GuiStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_project_tools_are_visible_but_default_to_write_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            async with mcp_session(paths) as session:
                for tool in ("hcl_open_project", "hcl_save_project"):
                    result, body = await call(
                        session, tool, {"project_path": str(paths["project"]), "hcl_pid": 17}
                    )
                    self.assertFalse(result.isError)
                    self.assertEqual(body["errors"][0]["code"], "writes_disabled")
                    self.assertFalse(body["full_live_gate_passed"])
