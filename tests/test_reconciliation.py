import json
from pathlib import Path
from unittest.mock import patch

from software_fixtures import SoftwareCase
from test_address_observation import IPV4, IPV6, VPN

from mcp_hcl.reconciliation import Reconciliation


class ReconciliationTests(SoftwareCase):
    def engine(self):
        binder, channel = self.dependencies()
        return Reconciliation(
            self.store,
            self.catalog,
            writes_enabled=True,
            runtime_binding=binder,
            session_factory=channel,
        )

    def setUp(self):
        super().setUp()
        self.guest.responses.update(
            {
                "display interface": IPV4,
                "display ipv6 interface": IPV6,
                "display ip interface brief": VPN,
            }
        )

    def test_default_gate_strict_timeout_ipv6_and_unknown_health(self):
        self.assertEqual(
            Reconciliation(self.store, self.catalog).observe("health", "missing", "lab")["errors"][
                0
            ]["code"],
            "writes_disabled",
        )
        for change in (
            {"timeout_seconds": True},
            {"timeout_seconds": 0},
            {"timeout_seconds": 601},
            {"include_ipv6": 1},
        ):
            with self.subTest(change=change):
                self.assertEqual(
                    self.engine().observe("health", self.project, "lab", **change)["status"],
                    "rejected",
                )
        result = self.engine().observe("health", self.project, "lab")
        self.assertEqual(len(result["devices"]), 2, result)
        self.assert_synthetic(result)
        self.assertIsNone(result["healthy"])
        self.assertIsNone(result["down_links"])
        self.assertNotIn("display ipv6 interface", self.guest.commands)
        self.assertEqual(self.guest.commands.count("display ip interface brief"), 2)
        self.assertEqual(len(result["duplicate_ips_by_routing_domain"]), 1)

    def test_ipv6_on_request_and_plan_relevant_devices_only(self):
        result = self.engine().observe("health", self.project, "lab", include_ipv6=True)
        self.assertEqual(self.guest.commands.count("display ipv6 interface"), 2)
        self.assert_synthetic(result)
        self.guest.commands = []
        plan = json.loads(
            (Path(self.project) / "MCPArtifacts/plan.json").read_text(encoding="utf-8")
        )
        plan["addresses"] = [
            {"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "2001:db8::1/64"}
        ]
        result = self.engine().observe("diff", self.project, "lab", plan=plan)
        self.assertEqual(self.guest.commands.count("display ipv6 interface"), 1, result)
        self.assertIsNone(result["in_sync"])
        self.assertIsNone(result["missing_devices"])
        self.assertIsNone(result["live_device_count"])

    def test_binding_pipe_truncation_and_partial_ipv6_failures_preserve_unknown(self):
        for mode in ("binding", "pipe", "complete", "hash", "ipv6"):
            with self.subTest(mode=mode):
                self.binding_error = mode == "binding"
                self.pipe_error = mode == "pipe"
                self.reply_changes = (
                    {"complete": False}
                    if mode == "complete"
                    else {"output_sha256": "0" * 64}
                    if mode == "hash"
                    else {}
                )
                self.guest.fail = (
                    (lambda cmd: cmd == "display ipv6 interface") if mode == "ipv6" else None
                )
                result = self.engine().observe("health", self.project, "lab", include_ipv6=True)
                self.assertTrue(result["errors"], result)
                self.assert_synthetic(result)
                self.assertIsNone(result["healthy"])

    def test_stage_change_second_read_identity_and_deadline(self):
        def stage_change(cmd):
            if cmd == "display interface":
                p = Path(self.project) / "MCPArtifacts/stage-receipt.json"
                p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        self.guest.on_exchange = stage_change
        result = self.engine().observe("health", self.project, "lab")
        self.assertIn("staged_snapshot_changed", [e["code"] for e in result["errors"]])
        self.assertFalse(result["snapshot_complete_for_staged_bindings"])
        self.guest.on_exchange = lambda cmd: self.clock.advance(2)
        with patch("mcp_hcl.reconciliation.time.monotonic", self.clock):
            result = self.engine().observe("health", self.project, "lab", timeout_seconds=1)
        self.assertTrue(result["errors"])
        self.assert_synthetic(result)

    def test_receipt_and_close_failure_never_report_complete(self):
        self.guest.close_error = True
        result = self.engine().observe("health", self.project, "lab")
        self.assertTrue(result["errors"])
        self.assertFalse(result["snapshot_complete_for_staged_bindings"])
        self.guest.close_error = False
        original = Path.write_text

        def fail(path, *a, **k):
            if ".reconciliation-receipts" in path.parts:
                raise OSError("Scripted receipt failure")
            return original(path, *a, **k)

        with patch.object(Path, "write_text", fail):
            result = self.engine().observe("health", self.project, "lab")
        self.assertIn("receipt_write_failed", [e["code"] for e in result["errors"]])
        self.assert_synthetic(result)

    def test_vpn_second_read_rejects_identity_or_address_changes_and_old_columns(self):
        self.changed_identity = True
        result = self.engine().observe("health", self.project, "lab")
        self.assertTrue(result["errors"])
        self.assertNotIn("display ip interface brief", self.guest.commands)
        self.changed_identity = False
        self.guest.commands = []
        self.guest.responses["display ip interface brief"] = VPN.replace(
            "10.3.0.1/24", "10.3.0.2/24"
        )
        result = self.engine().observe("health", self.project, "lab")
        self.assertTrue(result["errors"])
        self.assertEqual(result["duplicate_ips_by_routing_domain"], [])
        self.guest.responses["display ip interface brief"] = VPN.replace(" VPN instance", "")
        result = self.engine().observe("health", self.project, "lab")
        self.assertTrue(result["warnings"])
        self.assertIsNone(result["healthy"])
        self.assert_synthetic(result)
