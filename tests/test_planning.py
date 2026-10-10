from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from test_mcp_contract import build_fixture

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.planning import estimate_plan, explain_plan, fix_plan, plan_topology


class PlanCoreTests(unittest.TestCase):
    def test_routing_variants_and_dhcp_match_shared_estimator(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            catalog = HclCatalog(paths["install"])
            for routing in ("static", "ospf", "rip", "none"):
                request = {"routing": routing, "dhcp": True}
                plan = plan_topology(request, catalog)
                self.assertTrue(plan["valid"], plan.get("errors"))
                self.assertEqual(
                    estimate_plan(request, catalog)["estimate"]["services"],
                    len(plan["plan"]["services"]),
                )
                self.assertEqual(explain_plan(plan["plan"], catalog)["status"], "verified")

    def test_request_capacities_and_strict_nested_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            catalog = HclCatalog(paths["install"])
            for request in (
                {"routers": "2"},
                {"schema_version": True},
                {"routers": 1, "template": "star", "switches_per_router": 2},
                {"routing": "eigrp"},
                {"unexpected": 1},
            ):
                # A 3-router hub uses all three router ports and remains valid.
                expected = (
                    "verified"
                    if request == {"routers": 1, "template": "star", "switches_per_router": 2}
                    else "rejected"
                )
                self.assertEqual(plan_topology(request, catalog)["status"], expected)
            self.assertEqual(
                plan_topology({"routers": 2, "template": "star"}, catalog)["status"], "rejected"
            )

    def test_port_repair_preserves_user_ip_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            catalog = HclCatalog(paths["install"])
            plan = plan_topology({}, catalog)["plan"]
            plan["links"].append(copy.deepcopy(plan["links"][0]))
            before = copy.deepcopy(plan)
            repaired = fix_plan(plan, catalog)
            self.assertEqual(plan, before)
            self.assertEqual(repaired["plan"]["addresses"], before["addresses"])
            self.assertTrue(repaired["fixes"])
