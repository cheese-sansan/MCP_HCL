from __future__ import annotations

import copy
import unittest

from mcp_hcl.parity import parity_report, validate_inventory


class ParityInventoryTests(unittest.TestCase):
    def test_complete_pinned_inventory_and_platform_gaps(self) -> None:
        report = parity_report()
        validate_inventory(report)
        rows = {row["upstream_tool"]: row for row in report["tools"]}
        self.assertEqual(len(rows), 61)
        self.assertEqual(rows["pt_list_projects"]["state"], "implemented")
        self.assertEqual(rows["pt_simulation_step"]["state"], "unverified")
        self.assertEqual(rows["pt_simulation_step"]["hcl_targets"], [])
        self.assertFalse(report["full_live_gate_passed"])

    def test_missing_or_replaced_upstream_tool_is_rejected(self) -> None:
        report = parity_report()
        missing = copy.deepcopy(report)
        missing["tools"].pop()
        with self.assertRaises(ValueError):
            validate_inventory(missing)
        replaced = copy.deepcopy(report)
        replaced["tools"][0]["upstream_tool"] = "pt_invented_tool"
        with self.assertRaisesRegex(ValueError, "pinned upstream tool set"):
            validate_inventory(replaced)

    def test_live_claim_cannot_be_satisfied_by_stage_tool(self) -> None:
        report = parity_report()
        row = next(row for row in report["tools"] if row["upstream_tool"] == "pt_live_deploy")
        row["state"] = "implemented"
        row["hcl_targets"] = ["hcl_stage_copy"]
        with self.assertRaisesRegex(ValueError, "before the live gate"):
            validate_inventory(report)


if __name__ == "__main__":
    unittest.main()
