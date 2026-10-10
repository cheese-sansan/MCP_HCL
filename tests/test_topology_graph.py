"""Complete wired intent validation, separate from traffic or file generation."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from offline_fixtures import installation
from test_050_wireless import ProfileCatalog
from test_050_wireless import request as wireless_request
from test_mcp_contract import base_plan, build_fixture, call, mcp_session

from mcp_hcl.artifacts import Artifacts
from mcp_hcl.generation import generate_configs, generate_operations
from mcp_hcl.planning import plan_topology
from mcp_hcl.topology import validate_plan


class CompleteTopologyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = installation(self.root / "install")
        self.plan = base_plan()

    def codes(self, result):
        return {error["code"] for error in result["errors"]}

    def test_connected_graph_is_not_evidence_of_network_connectivity(self):
        result = validate_plan(self.plan, self.catalog)
        self.assertTrue(result["valid"])
        self.assertEqual(result["graph"]["components"], [["r1", "r2"]])
        self.assertEqual(result["graph"]["edge_count"], 1)
        self.assertTrue(result["graph"]["connected"])
        for key in (
            "runtime_verified",
            "guest_boot_verified",
            "configuration_verified",
            "connectivity_verified",
            "full_live_gate_passed",
        ):
            self.assertFalse(result[key])

    def test_isolated_device_and_two_wired_components_are_rejected_deterministically(self):
        self.plan["devices"] += [
            {"id": "r3", "name": "R3", "model": "MSR36-20"},
            {"id": "r4", "name": "R4", "model": "MSR36-20"},
        ]
        self.plan["links"].append(
            {
                "a": {"device": "r3", "interface": "GigabitEthernet0/0"},
                "b": {"device": "r4", "interface": "GigabitEthernet0/0"},
            }
        )
        before = copy.deepcopy(self.plan)
        result = validate_plan(self.plan, self.catalog)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["graph"]["components"], [["r1", "r2"], ["r3", "r4"]])
        error = next(
            error for error in result["errors"] if error["code"] == "topology_disconnected"
        )
        self.assertEqual(error["detail"]["unreachable_devices"], ["r3", "r4"])
        self.assertEqual(self.plan, before)
        self.plan["links"].append(
            {
                "a": {"device": "r2", "interface": "GigabitEthernet0/1"},
                "b": {"device": "r3", "interface": "GigabitEthernet0/1"},
            }
        )
        self.assertTrue(validate_plan(self.plan, self.catalog)["valid"])

    def test_invalid_ports_cannot_connect_two_components(self):
        self.plan["links"][0]["a"]["interface"] = "GigabitEthernet0/99"
        result = validate_plan(self.plan, self.catalog)
        self.assertEqual(result["graph"]["edge_count"], 0)
        self.assertIn("unknown_physical_interface", self.codes(result))
        self.assertIn("topology_disconnected", self.codes(result))

    def test_single_device_is_a_complete_declared_component(self):
        self.plan["devices"] = self.plan["devices"][:1]
        self.plan["links"] = []
        self.plan["addresses"] = []
        result = validate_plan(self.plan, self.catalog)
        self.assertTrue(result["valid"])
        self.assertEqual(result["graph"]["components"], [["r1"]])

    def test_partial_configuration_export_reload_and_operations_do_not_claim_full_graph(self):
        self.plan["links"] = []
        self.assertIn("topology_disconnected", self.codes(validate_plan(self.plan, self.catalog)))
        result = validate_plan(self.plan, self.catalog, validation_level="configuration")
        self.assertTrue(result["valid"])
        self.assertIsNone(result["graph"])
        self.assertIn(
            "wired_graph_not_checked", {warning["code"] for warning in result["warnings"]}
        )
        self.assertEqual(generate_configs(self.plan, self.catalog)["status"], "verified")
        self.assertFalse(generate_operations(self.plan, self.catalog, False)["executable"])
        artifacts = Artifacts(self.root / "exports", self.catalog)
        exported = artifacts.export(self.plan, "Partial")
        loaded = artifacts.load(exported["artifact_directory"])
        self.assertTrue(loaded["valid"])
        self.assertEqual(loaded["validation_level"], "configuration")
        self.assertIsNone(loaded["graph"])

    def test_radio_association_is_excluded_from_the_wired_graph_without_passing_wireless_gate(self):
        catalog = ProfileCatalog()
        result = plan_topology(wireless_request(), catalog)
        self.assertTrue(result["valid"], result["errors"])
        graph = result["graph"]
        phones = {
            device["id"] for device in result["plan"]["devices"] if device["model"] == "Phone"
        }
        self.assertEqual(set(graph["excluded_wireless_devices"]), phones)
        self.assertEqual(len(graph["components"]), 1)
        self.assertFalse(graph["connectivity_verified"])
        self.assertFalse(result["full_live_gate_passed"])
        self.assertEqual(generate_configs(result["plan"], catalog)["status"], "rejected")

    def test_wired_interface_cannot_hide_an_isolated_device_as_wireless(self):
        catalog = ProfileCatalog()
        plan = plan_topology(wireless_request(), catalog)["plan"]
        plan["devices"].append({"id": "isolated", "name": "isolated", "model": "MSR36-20"})
        plan["wireless_associations"].append(
            {
                "device": "isolated",
                "interface": "GigabitEthernet0/0",
                "ap": "ap1",
                "ssid": "diagnostic",
                "security": "open",
            }
        )
        result = validate_plan(plan, catalog)
        self.assertIn("wireless_interface_required", self.codes(result))
        self.assertIn("topology_disconnected", self.codes(result))
        self.assertNotIn("isolated", result["graph"]["excluded_wireless_devices"])

    def test_invalid_validation_level_is_a_business_rejection(self):
        for level in ("live", True, None, {}):
            result = validate_plan(self.plan, self.catalog, validation_level=level)
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result["errors"][0]["code"], "invalid_validation_level")

    def test_zero_router_id_and_empty_ospf_networks_never_generate_commands(self):
        self.plan["services"] = [
            {
                "device": "r1",
                "feature": "ospf",
                "parameters": {
                    "process_id": 1,
                    "router_id": "0.0.0.0",
                    "networks": [{"network": "10.0.0.0/30", "area": 0}],
                },
            }
        ]
        for level in ("topology", "configuration"):
            self.assertIn(
                "ospf_invalid_router_id",
                self.codes(validate_plan(self.plan, self.catalog, validation_level=level)),
            )
        self.assertNotIn("configs", generate_configs(self.plan, self.catalog))
        self.plan["services"][0]["parameters"].update(router_id="192.0.2.1", networks=[])
        result = validate_plan(self.plan, self.catalog)
        self.assertFalse(result["valid"])
        self.assertTrue(any("networks" in error.get("path", []) for error in result["errors"]))


class SviDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.catalog = installation(Path(self.temporary.name) / "install")
        self.plan = {
            "name": "SVI services",
            "devices": [{"id": "s1", "name": "Switch1", "model": "S5820V2-54QS-GE"}],
            "services": [
                {
                    "device": "s1",
                    "feature": "dhcp",
                    "parameters": {
                        "mode": "server",
                        "interface": "Vlan-interface10",
                        "pool": "LAN",
                        "network": "10.10.0.0/24",
                        "gateway": "10.10.0.1",
                        "excluded": [{"start": "10.10.0.1", "end": "10.10.0.1"}],
                    },
                },
                {
                    "device": "s1",
                    "feature": "ospf",
                    "parameters": {
                        "process_id": 1,
                        "router_id": "192.0.2.1",
                        "networks": [{"network": "10.10.0.0/24", "area": 0}],
                    },
                },
                {
                    "device": "s1",
                    "feature": "vlan",
                    "parameters": {"vlans": [10], "svis": [{"vlan": 10, "cidr": "10.10.0.1/24"}]},
                },
            ],
        }

    def test_dhcp_and_ospf_resolve_svi_addresses_independent_of_service_order(self):
        for services in (self.plan["services"], list(reversed(self.plan["services"]))):
            result = validate_plan({**self.plan, "services": services}, self.catalog)
            self.assertTrue(result["valid"], result["errors"])
            generated = generate_configs(result["plan"], self.catalog)
            self.assertEqual(generated["status"], "verified")
            self.assertIn(
                "interface Vlan-interface10\nip address 10.10.0.1 255.255.255.0",
                generated["configs"]["s1"],
            )
            self.assertIn("ospf 1 router-id 192.0.2.1", generated["configs"]["s1"])
            self.assertFalse(generated["configuration_verified"])

    def test_duplicate_svi_interface_and_reserved_svi_addresses_are_rejected(self):
        params = self.plan["services"][-1]["parameters"]
        # A second declaration in addresses is individually well-formed;
        # dependency resolution must still reject two IPv4 values on one SVI.
        self.plan["addresses"] = [
            {"device": "s1", "interface": "Vlan-interface10", "cidr": "10.10.0.2/24"}
        ]
        result = validate_plan(self.plan, self.catalog)
        self.assertIn("duplicate_svi_address", {error["code"] for error in result["errors"]})
        self.plan["addresses"] = []
        params["svis"][0]["cidr"] = "10.10.0.0/24"
        self.assertIn(
            "reserved_host_address",
            {error["code"] for error in validate_plan(self.plan, self.catalog)["errors"]},
        )


class TopologyGraphStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_graph_rejection_and_explicit_partial_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            plan = base_plan()
            plan["links"] = []
            async with mcp_session(paths) as session:
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                level = tools["hcl_validate_plan"].inputSchema["properties"]["validation_level"]
                self.assertEqual(level["default"], "topology")
                self.assertEqual(set(level["enum"]), {"topology", "configuration"})
                response, body = await call(session, "hcl_validate_plan", {"plan": plan})
                self.assertFalse(response.isError)
                self.assertEqual(body["status"], "rejected")
                self.assertIn("topology_disconnected", {error["code"] for error in body["errors"]})
                response, body = await call(
                    session,
                    "hcl_validate_plan",
                    {"plan": plan, "validation_level": "configuration"},
                )
                self.assertFalse(response.isError)
                self.assertTrue(body["valid"])
                self.assertIsNone(body["graph"])
                response, body = await call(
                    session, "hcl_validate_plan", {"plan": plan, "validation_level": True}
                )
                self.assertTrue(response.isError)
                self.assertEqual(body["status"], "rejected")
