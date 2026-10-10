from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.topology import validate_plan


class TopologyValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        (root / "devicecfgs").mkdir()
        (root / "devicecfgs" / "MSR36-20.cfg").write_text(
            "interface GigabitEthernet0/0\ninterface GigabitEthernet0/1\ninterface Serial1/0\n",
            encoding="utf-8",
        )
        self.catalog = HclCatalog(root)
        self.plan = {
            "schema_version": 1,
            "name": "中文实验",
            "devices": [
                {"id": "r1", "name": "路由器一", "model": "MSR36-20"},
                {"id": "r2", "name": "路由器二", "model": "MSR36-20"},
            ],
            "links": [
                {
                    "a": {"device": "r1", "interface": "GigabitEthernet0/0"},
                    "b": {"device": "r2", "interface": "GigabitEthernet0/0"},
                }
            ],
            "addresses": [
                {"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.1/30"},
                {"device": "r2", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.2/30"},
            ],
            "annotations": [{"text": "保留注释\n第二行"}],
        }

    def test_validated_intent_preserves_unicode_and_has_limited_scope(self):
        result = validate_plan(self.plan, self.catalog)
        self.assertTrue(result["valid"])
        self.assertFalse(result["runtime_verified"])
        self.assertEqual(result["plan"]["annotations"][0]["text"], "保留注释\n第二行")
        self.assertEqual(self.plan["name"], "中文实验")

    def test_conflicts_and_unknown_hardware_do_not_pass(self):
        plan = copy.deepcopy(self.plan)
        plan["links"].append(copy.deepcopy(plan["links"][0]))
        plan["addresses"][1]["cidr"] = "10.0.0.1/30"
        plan["routes"] = [{"device": "r2", "network": "::/0", "next_hop": "10.0.0.1"}]
        result = validate_plan(plan, self.catalog)
        codes = {row["code"] for row in result["errors"]}
        self.assertFalse(result["valid"])
        self.assertTrue(
            {"duplicate_port", "duplicate_ip", "route_address_family_mismatch"} <= codes
        )
        plan["devices"][0]["model"] = "invented"
        self.assertIn(
            "unknown_model", {row["code"] for row in validate_plan(plan, self.catalog)["errors"]}
        )

    def test_invalid_version_nonfinite_and_service_support_remain_explicit(self):
        plan = copy.deepcopy(self.plan)
        plan["schema_version"] = 2
        self.assertEqual(validate_plan(plan, self.catalog)["status"], "rejected")
        plan["schema_version"] = 1
        plan["devices"][0]["x"] = float("nan")
        self.assertEqual(validate_plan(plan, self.catalog)["status"], "rejected")
        plan["devices"][0]["x"] = 0
        plan["services"] = [{"device": "r1", "feature": "netstream"}]
        result = validate_plan(plan, self.catalog)
        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "rejected")
