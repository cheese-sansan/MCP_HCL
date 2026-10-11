"""The current upstream and every agreed reproduction gap remain explicit."""

import copy
import unittest

from mcp_hcl.parity import parity_report, validate_inventory


class ReproductionGoalsTests(unittest.TestCase):
    def test_current_upstream_includes_dedicated_dhcp_server(self):
        report = parity_report()
        self.assertEqual(report["upstream"]["revision"], "3c7c7a46b9ea27c914f845d161f95f0fc3f53d5f")
        self.assertEqual(len(report["tools"]), 62)
        row = next(r for r in report["tools"] if r["upstream_tool"] == "pt_configure_dhcp_server")
        self.assertEqual(row["state"], "planned")
        self.assertTrue(row["live_required"])
        self.assertNotIn("hcl_configure_dhcp_server", report["registered_tools"])

    def test_all_gap_groups_have_dependencies_and_acceptance(self):
        report = parity_report()
        expected = {
            "exclusive_cli",
            "native_inventory",
            "live_editing",
            "wired_end_to_end",
            "configuration_semantics",
            "wireless",
            "live_observation",
            "simulation_workspace",
            "dhcp_server",
            "api_compatibility",
            "delivery_evidence",
        }
        goals = report.get("reproduction_targets", [])
        self.assertEqual({goal["id"] for goal in goals}, expected)
        for goal in goals:
            with self.subTest(goal=goal["id"]):
                self.assertIn(goal["state"], {"planned", "partial", "blocked"})
                self.assertTrue(goal["acceptance"])
                self.assertLessEqual(set(goal["depends_on"]), expected)
        self.assertFalse(report["full_live_gate_passed"])
        self.assertEqual(report["completion"], "incomplete")

    def test_goals_cannot_be_dropped_falsely_completed_or_cyclic(self):
        for mode in ("missing", "completed", "cycle", "acceptance", "unknown_dependency"):
            with self.subTest(mode=mode):
                report = copy.deepcopy(parity_report())
                goal = report["reproduction_targets"][0]
                if mode == "missing":
                    report["reproduction_targets"].pop()
                elif mode == "completed":
                    goal["state"] = "completed"
                elif mode == "cycle":
                    goal["depends_on"] = [goal["id"]]
                elif mode == "acceptance":
                    goal["acceptance"] = []
                else:
                    goal["depends_on"] = ["unknown"]
                with self.assertRaises(ValueError):
                    validate_inventory(report)
