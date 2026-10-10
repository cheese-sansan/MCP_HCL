"""NAT mode fidelity: pools, PAT/NO-PAT, classifiers and readback scope."""

import copy
import tempfile
import unittest
from pathlib import Path

from offline_fixtures import installation, service_plan
from pydantic import ValidationError

from mcp_hcl.deployment import verification_commands
from mcp_hcl.generation import generate_configs, render_nat
from mcp_hcl.services import Nat


class NatModeTests(unittest.TestCase):
    def test_easy_ip_pool_pat_and_dynamic_no_pat_are_distinct(self):
        group = {"id": 0, "start": "203.0.113.1", "end": "203.0.113.8"}
        easy = Nat.model_validate({"outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001}]})
        self.assertIn("nat outbound 2001", render_nat(easy))
        for pat, expected in (
            (True, "nat outbound 2001 address-group 0"),
            (False, "nat outbound 2001 address-group 0 no-pat"),
        ):
            model = Nat.model_validate(
                {
                    "address_groups": [group],
                    "outbound": [
                        {
                            "interface": "GigabitEthernet0/1",
                            "acl": 2001,
                            "address_group": 0,
                            "pat": pat,
                        }
                    ],
                }
            )
            commands = render_nat(model)
            self.assertIn("nat address-group 0", commands)
            self.assertIn("address 203.0.113.1 203.0.113.8", commands)
            self.assertIn(expected, commands)

    def test_pool_members_are_split_at_256_without_losing_range(self):
        model = Nat.model_validate(
            {
                "address_groups": [{"id": 1, "start": "198.18.0.1", "end": "198.18.2.1"}],
                "outbound": [
                    {
                        "interface": "GigabitEthernet0/1",
                        "acl": 2001,
                        "address_group": 1,
                        "pat": False,
                    }
                ],
            }
        )
        self.assertEqual(
            [command for command in render_nat(model) if command.startswith("address ")],
            [
                "address 198.18.0.1 198.18.1.0",
                "address 198.18.1.1 198.18.2.0",
                "address 198.18.2.1 198.18.2.1",
            ],
        )

    def test_invalid_pool_reference_mode_and_json_types_fail(self):
        cases = [
            {"outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001, "pat": False}]},
            {"outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001, "address_group": 1}]},
            {
                "address_groups": [{"id": True, "start": "203.0.113.1", "end": "203.0.113.2"}],
                "outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001}],
            },
            {
                "address_groups": [{"id": 1, "start": "203.0.113.9", "end": "203.0.113.1"}],
                "outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001}],
            },
            {"outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001, "pat": 1}]},
            {"outbound": [{"interface": "GigabitEthernet0/1", "acl": 2001, "acl_name": "both"}]},
        ]
        for value in cases:
            with self.assertRaises(ValidationError):
                Nat.model_validate(value)
        with self.assertRaises(ValidationError):
            Nat.model_validate(
                {
                    "address_groups": [{"id": 1, "start": "203.0.113.1", "end": "203.0.113.2"}],
                    "outbound": [
                        {
                            "interface": "GigabitEthernet0/0",
                            "acl": 2001,
                            "address_group": 1,
                            "pat": False,
                        },
                        {
                            "interface": "GigabitEthernet0/1",
                            "acl": 2001,
                            "address_group": 1,
                            "pat": True,
                        },
                    ],
                }
            )

    def test_named_acl_dependency_is_not_substituted_by_a_numeric_acl(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            plan = service_plan()
            nat = next(service for service in plan["services"] if service["feature"] == "nat")
            nat["parameters"] = {
                "outbound": [{"interface": "GigabitEthernet0/2", "acl_name": "inside_hosts"}]
            }
            result = generate_configs(plan, catalog)
            self.assertIn("missing_acl_dependency", [error["code"] for error in result["errors"]])
            plan["services"].append(
                {
                    "device": "r1",
                    "feature": "acl",
                    "parameters": {
                        "name": "Inside_Hosts",
                        "acl_type": "basic",
                        "rules": [{"id": 5, "action": "permit", "source": "10.0.0.0/24"}],
                    },
                }
            )
            result = generate_configs(plan, catalog)
            self.assertEqual(result["status"], "verified", result.get("errors"))
            self.assertIn("nat outbound name inside_hosts", result["configs"]["r1"])
            self.assertFalse(result["configuration_verified"])
            self.assertFalse(result["runtime_verified"])

    def test_address_group_readback_cannot_match_another_group(self):
        commands = [
            "system-view",
            "nat address-group 1",
            "address 203.0.113.1 203.0.113.8",
            "quit",
            "return",
        ]
        wrong = "#\nnat address-group 2\n address 203.0.113.1 203.0.113.8\n#\nreturn\n"
        self.assertFalse(verification_commands(commands, wrong))
        self.assertTrue(
            verification_commands(
                commands, wrong.replace("nat address-group 2", "nat address-group 1")
            )
        )
