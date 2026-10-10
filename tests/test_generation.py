from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from offline_fixtures import installation, service_plan

from mcp_hcl.generation import generate_configs


class ServiceGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = installation(self.root / "install")
        self.plan = service_plan()

    def test_ten_reference_examples_generate_and_are_not_runtime_claims(self):
        result = generate_configs(self.plan, self.catalog)
        self.assertEqual(result["status"], "verified", result.get("errors"))
        router = result["configs"]["r1"]
        controller = result["configs"]["ac1"]
        expected = {
            "dhcp": "dhcp server ip-pool LAN\nnetwork 10.0.0.0 mask 255.255.255.0\ngateway-list 10.0.0.1\ndns-list 192.0.2.53",
            "ospf": "ospf 1 router-id 192.0.2.1\narea 0\nnetwork 10.0.0.0 0.0.0.255\nquit\nquit",
            "rip": "rip 1\nversion 2\nnetwork 10.0.0.0\nsilent-interface GigabitEthernet0/1\nquit",
            "vlan": "port link-type trunk\nport trunk permit vlan 10 20",
            "acl": "rule 5 permit tcp source 10.0.0.0 0.0.0.255 destination 192.0.2.0 0.0.0.255 destination-port eq 443",
            "nat": "nat server protocol tcp global 192.0.2.10 8443 inside 10.0.0.10 443",
            "security": "local-user operator class manage\npassword simple test-only-123\nservice-type ssh\nauthorization-attribute user-role level-15",
            "qos": "qos policy edge\nclassifier web behavior mark\nquit",
            "netstream": "ip netstream export version 9\nip netstream export host 192.0.2.50 2055",
            "wireless": "wlan ap ap1 model WA4620i-AGN\nserial-id TEST123\nradio 1\nradio enable\nservice-template corp\nquit\nquit",
        }
        for feature, text in expected.items():
            with self.subTest(feature=feature):
                self.assertIn(text, controller if feature == "wireless" else router)
        self.assertIn("interface Vlan-interface20\nip address 10.20.0.1 255.255.255.0", router)
        self.assertFalse(result["configuration_verified"])
        self.assertFalse(result["runtime_verified"])
        self.assertEqual({s["feature"] for s in result["plan"]["services"]}, set(expected))
        self.assertTrue(all("sha256" in e for e in result["evidence"]))

    def test_all_services_reject_unknown_parameters_and_strict_types(self):
        for service in self.plan["services"]:
            plan = copy.deepcopy(self.plan)
            selected = next(s for s in plan["services"] if s["feature"] == service["feature"])
            selected["parameters"]["typo_parameter"] = 1
            with self.subTest(feature=service["feature"]):
                result = generate_configs(plan, self.catalog)
                self.assertEqual(result["status"], "rejected")
                self.assertTrue(any(e["code"] == "extra_forbidden" for e in result["errors"]))
                self.assertNotIn("configs", result)
        for feature, field, value in [
            ("ospf", "process_id", "1"),
            ("rip", "version", True),
            ("vlan", "vlans", ["10"]),
            ("netstream", "version", True),
            ("security", "disable_telnet", 1),
        ]:
            plan = copy.deepcopy(self.plan)
            next(s for s in plan["services"] if s["feature"] == feature)["parameters"][field] = (
                value
            )
            self.assertEqual(generate_configs(plan, self.catalog)["status"], "rejected")

    def test_missing_dependencies_and_unsafe_credentials_are_rejected(self):
        for feature in ("acl", "vlan"):
            plan = copy.deepcopy(self.plan)
            plan["services"] = [s for s in plan["services"] if s["feature"] != feature]
            result = generate_configs(plan, self.catalog)
            self.assertEqual(result["status"], "rejected")
            self.assertTrue(any("dependency" in e["code"] for e in result["errors"]))
        plan = copy.deepcopy(self.plan)
        next(s for s in plan["services"] if s["feature"] == "security")["parameters"][
            "password"
        ] = "password\nreboot"
        result = generate_configs(plan, self.catalog)
        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("password\nreboot", json.dumps(result))

    def test_relay_fat_ap_and_static_nat_variants(self):
        plan = copy.deepcopy(self.plan)
        plan["services"][0]["parameters"] = {
            "mode": "relay",
            "interface": "GigabitEthernet0/0",
            "servers": ["192.0.2.1"],
        }
        wireless = next(s for s in plan["services"] if s["feature"] == "wireless")
        wireless["device"] = "ap1"
        wireless["parameters"] = {
            "mode": "fat_ap",
            "template": "corp",
            "ssid": "Lab",
            "vlan": 10,
            "psk": "test-only-wifi",
            "radio_interface": "WLAN-Radio1/0/1",
        }
        plan["services"].append({"device": "ap1", "feature": "vlan", "parameters": {"vlans": [10]}})
        nat = next(s for s in plan["services"] if s["feature"] == "nat")
        nat["parameters"]["static"] = [
            {
                "interface": "GigabitEthernet0/2",
                "global_address": "192.0.2.10",
                "local_address": "10.0.0.10",
            }
        ]
        result = generate_configs(plan, self.catalog)
        self.assertEqual(result["status"], "verified", result.get("errors"))
        self.assertIn(
            "dhcp select relay\ndhcp relay server-address 192.0.2.1", result["configs"]["r1"]
        )
        self.assertIn("nat static outbound 10.0.0.10 192.0.2.10", result["configs"]["r1"])
        self.assertIn("interface WLAN-Radio1/0/1\nservice-template corp", result["configs"]["ap1"])
