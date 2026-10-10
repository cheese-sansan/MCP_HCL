from pathlib import Path

from mcp_hcl.catalog import HclCatalog


def installation(root):
    (root / "devicecfgs").mkdir(parents=True)
    cfg = " version 7.1.064\ninterface GigabitEthernet0/0\ninterface GigabitEthernet0/1\ninterface GigabitEthernet0/2\ninterface Serial1/0\ninterface NULL0\n"
    for model in ("MSR36-20", "S5820V2-54QS-GE", "PC"):
        (root / "devicecfgs" / (model + ".cfg")).write_text(cfg, encoding="utf-8")
    (root / "version").mkdir()
    for image in ("ac", "ap"):
        (root / "version" / (image + ".vmdk")).write_bytes(b"synthetic image marker")
    (root / "deviceInfo.ini").write_text(
        "[PHY_PORT_VALUE]\n PHY_ETH_GE = 3\n PHY_SYNC = 56\n PHY_RADIO = 114\n"
        + "".join(
            f"[{name}]\n [[0]]\n  GE = PHY_ETH_GE\n [[1]]\n  GE = PHY_ETH_GE\n [[2]]\n  GE = PHY_ETH_GE\n"
            for name in ("MSR36", "S5800", "PC", "AC", "AP")
        ),
        encoding="utf-8",
    )
    return HclCatalog(root)


def service_plan():
    return {
        "schema_version": 1,
        "name": "All services",
        "devices": [
            {"id": "r1", "name": "r1", "model": "MSR36-20"},
            {"id": "ac1", "name": "ac1", "model": "AC"},
            {"id": "ap1", "name": "ap1", "model": "AP"},
        ],
        "addresses": [{"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.1/24"}],
        "services": [
            {
                "device": "r1",
                "feature": "dhcp",
                "parameters": {
                    "mode": "server",
                    "interface": "GigabitEthernet0/0",
                    "pool": "LAN",
                    "network": "10.0.0.0/24",
                    "gateway": "10.0.0.1",
                    "dns": ["192.0.2.53"],
                    "excluded": [{"start": "10.0.0.1", "end": "10.0.0.9"}],
                },
            },
            {
                "device": "r1",
                "feature": "ospf",
                "parameters": {
                    "process_id": 1,
                    "router_id": "192.0.2.1",
                    "networks": [{"network": "10.0.0.0/24", "area": 0}],
                },
            },
            {
                "device": "r1",
                "feature": "rip",
                "parameters": {
                    "version": 2,
                    "networks": ["10.0.0.0/8"],
                    "passive_interfaces": ["GigabitEthernet0/1"],
                },
            },
            {
                "device": "r1",
                "feature": "vlan",
                "parameters": {
                    "vlans": [10, 20],
                    "ports": [
                        {"interface": "GigabitEthernet0/1", "mode": "access", "vlan": 10},
                        {
                            "interface": "GigabitEthernet0/2",
                            "mode": "trunk",
                            "allowed_vlans": [10, 20],
                        },
                    ],
                    "svis": [{"vlan": 20, "cidr": "10.20.0.1/24"}],
                },
            },
            {
                "device": "r1",
                "feature": "acl",
                "parameters": {
                    "number": 2001,
                    "rules": [{"id": 0, "action": "permit", "source": "10.0.0.0/24"}],
                },
            },
            {
                "device": "r1",
                "feature": "acl",
                "parameters": {
                    "number": 3001,
                    "rules": [
                        {
                            "id": 5,
                            "action": "permit",
                            "protocol": "tcp",
                            "source": "10.0.0.0/24",
                            "destination": "192.0.2.0/24",
                            "destination_port": 443,
                        }
                    ],
                    "bindings": [{"interface": "GigabitEthernet0/1", "direction": "inbound"}],
                },
            },
            {
                "device": "r1",
                "feature": "nat",
                "parameters": {
                    "outbound": [{"interface": "GigabitEthernet0/2", "acl": 2001}],
                    "static": [
                        {
                            "interface": "GigabitEthernet0/2",
                            "global_address": "192.0.2.10",
                            "local_address": "10.0.0.10",
                            "protocol": "tcp",
                            "global_port": 8443,
                            "local_port": 443,
                        }
                    ],
                },
            },
            {
                "device": "r1",
                "feature": "security",
                "parameters": {
                    "username": "operator",
                    "password": "test-only-123",
                    "vty_acl": 2001,
                },
            },
            {"device": "ac1", "feature": "vlan", "parameters": {"vlans": [10]}},
            {
                "device": "ac1",
                "feature": "wireless",
                "parameters": {
                    "mode": "ac",
                    "template": "corp",
                    "ssid": "LabSSID",
                    "vlan": 10,
                    "psk": "test-only-wifi",
                    "ap_device": "ap1",
                    "ap_name": "ap1",
                    "ap_model": "WA4620i-AGN",
                    "serial_id": "TEST123",
                    "radio": 1,
                },
            },
            {
                "device": "r1",
                "feature": "qos",
                "parameters": {
                    "classifier": "web",
                    "behavior": "mark",
                    "policy": "edge",
                    "acl": 3001,
                    "remark_dscp": 46,
                    "cir": 1000,
                    "bindings": [{"interface": "GigabitEthernet0/1", "direction": "outbound"}],
                },
            },
            {
                "device": "r1",
                "feature": "netstream",
                "parameters": {
                    "collector": "192.0.2.50",
                    "port": 2055,
                    "version": 9,
                    "interfaces": [{"interface": "GigabitEthernet0/2", "direction": "inbound"}],
                },
            },
        ],
    }
