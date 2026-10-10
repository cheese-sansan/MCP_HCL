import copy
from unittest.mock import patch

from pydantic import ValidationError
from software_fixtures import BASE, Guest, SoftwareCase

from mcp_hcl.switch_security import (
    PortSecurityRequest,
    StpRequest,
    SwitchSecurityOperation,
    port_security_delta,
    stp_delta,
)

STP = {
    "switch": "r1",
    "mode": "rapid-pvst",
    "priority": {"10": 4096},
    "portfast_ports": ["GigabitEthernet0/0"],
    "bpduguard_ports": ["GigabitEthernet0/0"],
}
PORT = {"switch": "r1", "port": "GigabitEthernet0/0", "static_macs": ["0011-2233-4455"]}
STP_AFTER = BASE.replace(
    "sysname preserved",
    "sysname preserved\nstp mode pvst\nstp global enable\nstp bpdu-protection\nstp vlan 10 priority 4096",
).replace(" mtu 1400", " mtu 1400\n stp edged-port")
PORT_AFTER = BASE.replace("sysname preserved", "sysname preserved\nport-security enable").replace(
    " mtu 1400",
    " mtu 1400\n port-security max-mac-count 1\n port-security port-mode autolearn\n port-security intrusion-mode disableport\n port-security mac-address security 0011-2233-4455 vlan 1",
)


class SwitchTests(SoftwareCase):
    def operation(self):
        return SwitchSecurityOperation(self.policy())

    def test_strict_json_priority_mac_capacity_and_duplicates(self):
        for model, request, changes in [
            (
                StpRequest,
                STP,
                (
                    {"priority": {"10": True}},
                    {"priority": {"10": 1}},
                    {"priority": {"4095": 4096}},
                    {"mode": "mstp"},
                    {"timeout_seconds": "120"},
                ),
            ),
            (
                PortSecurityRequest,
                PORT,
                (
                    {"sticky": 1},
                    {"max_mac": True},
                    {"static_macs": ["0000-0000-0000"]},
                    {"static_macs": ["0100-0000-0001"]},
                    {"static_macs": ["xx"]},
                    {"static_macs": ["001122334455", "0011-2233-4455"]},
                ),
            ),
        ]:
            for change in changes:
                with self.subTest(model=model.__name__, change=change):
                    with self.assertRaises(ValidationError):
                        model.model_validate(request | change)
        self.assertEqual(
            PortSecurityRequest.model_validate(
                PORT | {"static_macs": ["00:11:22:33:44:55"]}
            ).static_macs,
            ["0011-2233-4455"],
        )

    def test_unsupported_modes_stop_before_stage_read_console_and_backup(self):
        for feature, request in [
            ("stp", STP | {"mode": "pvst"}),
            ("port_security", PORT | {"violation": "protect"}),
            ("port_security", PORT | {"violation": "restrict"}),
            ("port_security", PORT | {"max_mac": 1025}),
        ]:
            with self.subTest(feature=feature, request=request):
                operation = self.operation()
                with patch.object(
                    operation.policy.deployment,
                    "bindings",
                    side_effect=AssertionError("Unsupported request read stage"),
                ):
                    result = operation.apply(feature, "missing", "lab", request)
                self.assertEqual(result["status"], "unverified")
                self.assertEqual(self.opens, [])

    def test_positive_transactions_persist_and_preserve_scope(self):
        for feature, request, after in [
            ("stp", STP, STP_AFTER),
            ("port_security", PORT, PORT_AFTER),
        ]:
            with self.subTest(feature=feature):
                self.guest = Guest(after=after)
                result = self.operation().apply(feature, self.project, "lab", request)
                self.assertTrue(result["protocol_effect_verified"], result)
                self.assert_synthetic(result)
                self.assertEqual(self.guest.files[self.guest.startup["main"]], after)
                self.assertEqual(self.guest.files["flash:/startup.cfg"], BASE)

    def test_vlan_ranges_and_explicit_priority_override_root(self):
        before = BASE.replace(
            "sysname preserved", "sysname preserved\nstp vlan 10 to 12 priority 8192"
        )
        request = StpRequest.model_validate(
            STP | {"root_primary_vlans": [10], "bpduguard_ports": []}
        )
        commands, expected = stp_delta(before, request)
        self.assertIn("stp vlan 10 priority 4096", commands)
        self.assertNotIn("stp vlan 10 root primary", commands)
        self.assertIn("stp vlan 11 priority 8192", expected[()])
        self.assertIn("stp vlan 12 priority 8192", expected[()])

    def test_global_bpdu_edge_conflicts_refuse(self):
        for before, request in [
            (BASE, STP | {"portfast_ports": []}),
            (BASE.replace(" ip address", " stp edged-port\n ip address"), STP),
            (BASE.replace(" mtu 1400", " mtu 1400\n stp loop-protection"), STP),
        ]:
            with self.subTest(before=before):
                with self.assertRaises(ValueError):
                    stp_delta(before, StpRequest.model_validate(request))

    def test_port_modes_authentication_learning_and_mac_conflicts_refuse(self):
        additions = [
            "port link-type trunk",
            "port link-type hybrid",
            "port link-mode route",
            "dot1x",
            "mac-authentication",
            "port-security mac-address dynamic",
            "port-security port-mode secure",
            "port-security mac-address security 0011-2233-4455 vlan 2",
        ]
        for addition in additions:
            with self.subTest(addition=addition):
                before = BASE.replace(" port link-type access", " " + addition)
                with self.assertRaises(ValueError):
                    port_security_delta(before, PortSecurityRequest.model_validate(PORT))
        sticky = BASE.replace(
            " mtu 1400",
            " mtu 1400\n port-security mac-address security sticky 0011-2233-4455 vlan 1",
        )
        with self.assertRaises(ValueError):
            port_security_delta(
                sticky, PortSecurityRequest.model_validate(PORT | {"sticky": False})
            )

    def test_failure_recovers_original_uuid_without_replay(self):
        self.guest = Guest(after=STP_AFTER)
        self.guest.fail = lambda cmd: cmd == "stp bpdu-protection"
        result = self.operation().apply("stp", self.project, "lab", STP)
        self.assertTrue(result["protocol_rollback_verified"], result)
        self.assertEqual(self.guest.current, BASE)
        self.assertEqual(self.guest.commands.count("stp mode pvst"), 1)
        self.assertEqual(len(self.opens), 2)
        self.assert_synthetic(result)
