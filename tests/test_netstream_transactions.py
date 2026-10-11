import copy
import json
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from software_fixtures import BASE, Guest, SoftwareCase

from mcp_hcl.netstream_policy import (
    NetstreamOperation,
    NetstreamRequest,
    netstream_delta,
    normalized_scope_sets,
    normalized_views,
)

REQUEST = {
    "device": "r1",
    "name": "collector",
    "destination_ip": "192.0.2.10",
    "udp_port": 2055,
    "version": 9,
    "interfaces": [{"interface": "GigabitEthernet0/0", "direction": "inbound"}],
}
AFTER = BASE.replace(
    "sysname preserved", "sysname preserved\nip netstream export host 192.0.2.10 2055"
).replace(" mtu 1400", " mtu 1400\n ip netstream inbound")
NAME = {"destination_ip": "192.0.2.10", "udp_port": 2055, "version": 9, "source_native": ""}


class NetstreamTests(SoftwareCase):
    def operation(self):
        return NetstreamOperation(self.policy())

    def test_strict_addresses_ports_versions_directions_and_unknown_fields(self):
        for change in (
            {"udp_port": True},
            {"udp_port": 0},
            {"udp_port": 65536},
            {"version": "9"},
            {"version": 10},
            {"destination_ip": "::1"},
            {"remove": 1},
            {"vpn_instance": "vpnA"},
            {"interfaces": REQUEST["interfaces"] * 2},
            {"interfaces": [{"interface": "GigabitEthernet0/0", "direction": "both"}]},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValidationError):
                    NetstreamRequest.model_validate(REQUEST | change)

    def test_monitor_objects_are_rejected_before_stage_io(self):
        operation = self.operation()
        with patch.object(
            operation.policy.deployment,
            "bindings",
            side_effect=AssertionError("Monitor request read stage"),
        ):
            result = operation.apply(
                "missing", "lab", REQUEST | {"monitors": ["unsupported-monitor"]}
            )
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(self.opens, [])

    def test_transaction_name_identity_persistence_and_exact_remove(self):
        self.guest = Guest(after=AFTER)
        result = self.operation().apply(self.project, "lab", REQUEST)
        self.assertTrue(result["protocol_effect_verified"], result)
        self.assert_synthetic(result)
        registry = Path(result["exporter_name_registry"])
        self.assertIn(".netstream-protocol-names", registry.parts)
        self.assertFalse(
            json.loads(registry.read_text(encoding="utf-8"))["native_configuration_origin"]
        )
        count = len(self.guest.commands)
        self.guest.after = AFTER
        again = self.operation().apply(
            self.project, "lab", REQUEST | {"operation_key": "stream_reuse_1"}
        )
        count = len(self.guest.commands)
        reused = self.operation().apply(
            self.project, "lab", REQUEST | {"operation_key": "stream_reuse_1"}
        )
        self.assertEqual(len(self.guest.commands), count)
        self.assertFalse(reused["replayed"])
        self.assert_synthetic(reused)
        retained = BASE.replace(" mtu 1400", " mtu 1400\n ip netstream inbound")
        self.guest.after = retained
        removed = self.operation().apply(
            self.project, "lab", REQUEST | {"remove": True, "interfaces": []}
        )
        self.assertTrue(removed["protocol_effect_verified"], removed)
        self.assertIn("undo ip netstream export host 192.0.2.10", self.guest.commands)
        self.assertNotIn("undo ip netstream export host", self.guest.commands)
        self.assertIn(" ip netstream inbound", self.guest.current)

    def test_empty_destination_reuse_new_inert_name_rejection_and_port_override(self):
        with self.assertRaises(ValueError):
            netstream_delta(
                BASE, NetstreamRequest.model_validate(REQUEST | {"destination_ip": ""}), {}
            )
        commands, expected, names = netstream_delta(
            AFTER,
            NetstreamRequest.model_validate(REQUEST | {"destination_ip": "", "udp_port": 9999}),
            {"collector": NAME},
        )
        self.assertIn("ip netstream export host 192.0.2.10 9999", commands)
        self.assertEqual(names["collector"]["destination_ip"], "192.0.2.10")
        self.assertNotIn("undo ip netstream export host", commands)

    def test_shared_globals_drift_aggregation_capacity_bgp_and_name_conflicts(self):
        other = BASE.replace(
            "sysname preserved", "sysname preserved\nip netstream export host 192.0.2.11 2055"
        )
        cases = [
            (other, REQUEST | {"version": 5}, {}),
            (other, REQUEST | {"source_port": "GigabitEthernet0/0"}, {}),
            (AFTER, REQUEST, {"collector": NAME | {"udp_port": 9999}}),
            (
                BASE.replace(
                    "sysname preserved", "sysname preserved\nip netstream aggregation protocol"
                ),
                REQUEST,
                {},
            ),
            (
                BASE.replace(
                    "sysname preserved",
                    "sysname preserved\nip netstream export version 9 peer-as bgp-nexthop",
                ),
                REQUEST | {"version": 5},
                {},
            ),
            (AFTER, REQUEST, {"other": NAME}),
            (
                BASE.replace(
                    "sysname preserved",
                    "sysname preserved"
                    + "".join(
                        "\nip netstream export host 192.0.2." + str(i) + " 2055"
                        for i in range(11, 15)
                    ),
                ),
                REQUEST,
                {},
            ),
        ]
        for before, request, names in cases:
            with self.subTest(before=before, request=request, names=names):
                with self.assertRaises(ValueError):
                    netstream_delta(before, NetstreamRequest.model_validate(request), names)
        with self.assertRaises(ValueError):
            netstream_delta(
                AFTER,
                NetstreamRequest.model_validate(REQUEST | {"remove": True, "interfaces": []}),
                {"collector": NAME, "shared": NAME},
            )

    def test_unrequested_nested_views_and_as_options_are_protected(self):
        before = BASE.replace(
            "return", "ospf 1\n area 0\n  network 10.0.0.0 0.0.0.255\n#\nreturn"
        ).replace("sysname preserved", "sysname preserved\nip netstream export version 9 origin-as")
        commands, expected, names = netstream_delta(
            before, NetstreamRequest.model_validate(REQUEST), {}
        )
        after = before.replace(
            "sysname preserved", "sysname preserved\nip netstream export host 192.0.2.10 2055"
        ).replace(" mtu 1400", " mtu 1400\n ip netstream inbound")
        self.assertEqual(normalized_views(after), normalized_scope_sets(expected))
        self.assertNotEqual(
            normalized_views(after.replace("network 10.0.0.0", "network 10.1.0.0")),
            normalized_scope_sets(expected),
        )
        self.assertNotIn("ip netstream export version 9", commands)

    def test_registry_write_failure_restores_guest_and_old_or_new_name_file(self):
        original = __import__("mcp_hcl.netstream_policy", fromlist=["atomic_json"]).atomic_json
        for existing in (False, True):
            with self.subTest(existing=existing):
                registry = self.store.output_root / ".netstream-protocol-names" / "r1" / "same.json"
                if existing:
                    registry.parent.mkdir(parents=True, exist_ok=True)
                    registry.write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "project": str(self.store._open(self.project).net_path),
                                "vm_uuid": "same",
                                "names": {},
                            }
                        ),
                        encoding="utf-8",
                    )
                before_bytes = registry.read_bytes() if registry.exists() else None
                self.guest = Guest(after=AFTER)
                failed = [False]

                def write(path, data):
                    if path == registry and not failed[0]:
                        failed[0] = True
                        original(path, data)  # Simulate an uncertain outcome after rename.
                        raise OSError("Scripted metadata write failure")
                    return original(path, data)

                with patch("mcp_hcl.netstream_policy.atomic_json", write):
                    result = self.operation().apply(self.project, "lab", REQUEST)
                self.assertTrue(failed[0], "The canonical registry write must receive the fault")
                self.assertEqual(self.guest.current, BASE, result)
                self.assertTrue(result["name_registry_restored"], result)
                self.assertEqual(
                    json.loads(registry.read_text(encoding="utf-8")), json.loads(before_bytes)
                ) if before_bytes else self.assertFalse(registry.exists())
                self.assert_synthetic(result)

    def test_native_namespace_cannot_be_reused_by_a_synthetic_channel(self):
        path = self.paths["output"] / ".netstream-names" / "r1" / "same.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"native_configuration_origin": True, "names": {"fake": NAME}}),
            encoding="utf-8",
        )
        before = path.read_bytes()
        self.guest = Guest(after=AFTER)
        result = self.operation().apply(self.project, "lab", REQUEST)
        self.assertTrue(result.get("protocol_effect_verified"), result)
        self.assert_synthetic(result)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn(".netstream-protocol-names", Path(result["exporter_name_registry"]).parts)
