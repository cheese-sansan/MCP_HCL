import copy

from software_fixtures import SoftwareCase
from test_project_build import plan_fixture

from mcp_hcl.address_observation import interface_domains, ipv6_interfaces
from mcp_hcl.readback import ReadbackError
from mcp_hcl.reconciliation import diff_observations, health_observations, reconciliation_ports
from mcp_hcl.topology import TopologyPlan

IPV4 = "GigabitEthernet0/0 current state: UP\nLine protocol current state: UP\nInternet address: 10.3.0.1/24 (Primary)\n"
IPV6 = "GigabitEthernet0/0 current state: UP\nLine protocol current state: UP\nIPv6 is enabled, link-local address is FE80::1\nGlobal unicast address(es):\n 2001:db8::1, subnet is 2001:db8::/64\nJoined group address(es):\n FF02::1\n"
VPN = "Interface Physical Protocol IP address/Mask VPN instance\nGE0/0 up up 10.3.0.1/24 --\n"


class AddressTests(SoftwareCase):
    def test_ipv4_primary_secondary_absent_unknown_and_conflicts(self):
        ports = reconciliation_ports(IPV4 + "Internet address: 10.4.0.1/24 (Secondary)\n")
        self.assertEqual(len(ports[0]["ipv4_addresses"]), 2)
        self.assertEqual(ports[0]["ipv4"]["address"], "10.3.0.1")
        for value, status in [
            ("Internet address: none", "absent"),
            ("Internet protocol processing: disabled", "absent"),
            ("", "unknown"),
        ]:
            self.assertEqual(
                reconciliation_ports(IPV4.split("Internet")[0] + value)[0]["ipv4_observation"],
                status,
            )
        for extra in (
            "Internet address: none",
            "Internet address: 10.3.0.2/24 (Primary)",
            "Internet address: invalid",
            "Internet address: 10.3.0.1/24 (Secondary)",
        ):
            with self.subTest(extra=extra):
                with self.assertRaises((ValueError, ReadbackError)):
                    reconciliation_ports(IPV4 + extra + "\n")

    def test_ipv6_flags_lifetimes_link_local_and_disabled(self):
        for flag, usable, preferred in [
            ("TENTATIVE", False, True),
            ("DUPLICATE", False, True),
            ("DEPRECATED", True, False),
            ("ANYCAST", True, True),
        ]:
            with self.subTest(flag=flag):
                row = ipv6_interfaces(
                    IPV6.replace("2001:db8::/64", "2001:db8::/64 [" + flag + "]")
                )["GigabitEthernet0/0"]
                self.assertEqual(row["ipv6_addresses"][0]["usable"], usable)
                self.assertEqual(row["ipv6_addresses"][0]["preferred"], preferred)
                self.assertNotIn("prefix_length", row["ipv6_link_local"])
        zero = ipv6_interfaces(
            IPV6.replace("2001:db8::/64", "2001:db8::/64 [valid lifetime 0s/preferred lifetime 0s]")
        )
        self.assertFalse(zero["GigabitEthernet0/0"]["ipv6_addresses"][0]["usable"])
        disabled = ipv6_interfaces(IPV4.split("Internet")[0] + "IPv6 is disabled\n")
        self.assertEqual(disabled["GigabitEthernet0/0"]["ipv6_observation"], "absent")

    def test_ipv6_incomplete_unknown_duplicate_and_conflicting_records_reject(self):
        bad = [
            IPV6.replace("Joined group address(es):", "unknown:"),
            IPV6.replace("2001:db8::/64", "2001:db8::/64 [UNKNOWN]"),
            IPV6.replace("2001:db8::/64", "2001:db8::/64 [DUPLICATE] [DUPLICATE]"),
            IPV6.replace("2001:db8::/64", "2001:db9::/64"),
            IPV6.replace("IPv6 is enabled", "IPv6 is disabled"),
            IPV6.replace("Joined group", " 2001:db8::1, subnet is 2001:db8::/64\nJoined group"),
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises((ValueError, ReadbackError)):
                    ipv6_interfaces(text)

    def test_vpn_columns_exact_aliases_domains_and_changed_addresses(self):
        ports = reconciliation_ports(IPV4)
        for value, kind in [("--", "public"), ("vpnA", "vpn")]:
            result = interface_domains(VPN.replace("--", value), ports)
            self.assertEqual(
                result["interfaces"]["GigabitEthernet0/0"]["routing_domain"]["kind"], kind
            )
        self.assertEqual(
            interface_domains(VPN.replace(" VPN instance", ""), ports)["status"], "unavailable"
        )
        for text in (
            VPN.replace("10.3.0.1/24", "10.3.0.2/24"),
            VPN + "GigabitEthernet0/0 up up 10.3.0.1/24 --\n",
        ):
            with self.assertRaises(ReadbackError):
                interface_domains(text, ports)

    def test_duplicate_domains_anycast_and_unusable_addresses_do_not_prove_health(self):
        ports = reconciliation_ports(IPV4)
        ports[0].update(ipv6_interfaces(IPV6)["GigabitEthernet0/0"])
        other = copy.deepcopy(ports)
        ports[0].update(routing_domain_observation="known", routing_domain={"kind": "public"})
        other[0].update(
            routing_domain_observation="known", routing_domain={"kind": "vpn", "name": "vpnA"}
        )
        devices = [{"name": "one", "ports": ports}, {"name": "two", "ports": other}]
        result = health_observations(devices)
        self.assertIn("10.3.0.1", result["duplicate_ips"])
        self.assertEqual(result["duplicate_ips_by_routing_domain"], [])
        self.assertIn("2001:db8::1", result["ipv6_duplicate_addresses"])
        self.assertIsNone(result["down_links"])
        other[0]["ipv6_addresses"][0]["flags"] = ["ANYCAST"]
        self.assertEqual(health_observations(devices)["ipv6_duplicate_addresses"], {})
        other[0]["ipv6_addresses"][0]["usable"] = False
        self.assertEqual(len(health_observations(devices)["ipv6_unusable_addresses"]), 1)

    def test_diff_primary_prefix_missing_global_and_link_local_usability(self):
        data = plan_fixture()
        data["addresses"] = [
            {"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "10.3.0.2/25"}
        ]
        plan = TopologyPlan.model_validate(data)
        name = plan.devices[0].name
        ports = reconciliation_ports(IPV4)
        devices = [{"name": name, "ports": ports}]
        result = diff_observations(plan, devices)
        self.assertEqual(len(result["ip_mismatches"]), 1)
        self.assertEqual(len(result["prefix_mismatches"]), 1)
        self.assertEqual(
            diff_observations(plan, [])["unavailable_addresses"][0]["reason"],
            "device_or_interface_not_observed",
        )
        ports[0].update(ipv6_interfaces(IPV6)["GigabitEthernet0/0"])
        for address, reason in [
            ("fe80::1/64", "link_local_prefix_not_observed"),
            ("2001:db8::1/64", "ipv6_address_not_usable"),
        ]:
            with self.subTest(address=address):
                ports[0]["ipv6_addresses"][0]["usable"] = False
                ports[0]["ipv6_addresses"][0]["flags"] = ["TENTATIVE"]
                data["addresses"][0]["cidr"] = address
                result = diff_observations(TopologyPlan.model_validate(data), devices)
                self.assertEqual(result["unavailable_addresses"][0]["reason"], reason)
