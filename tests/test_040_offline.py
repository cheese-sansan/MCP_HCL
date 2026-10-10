import copy
import tempfile
import unittest
from pathlib import Path

from offline_fixtures import installation
from test_project_build import configure_fixture, explicit_map, plan_fixture, snapshot

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.generation import generate_configs
from mcp_hcl.planning import estimate_plan, plan_topology
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan
from mcp_hcl.project_edit import edit_project
from mcp_hcl.topology import validate_plan


class Planning040Tests(unittest.TestCase):
    def test_all_nine_templates_and_dhcp_clients(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            for template in (
                "single_lan",
                "multi_lan",
                "multi_lan_wan",
                "star",
                "hub_spoke",
                "branch_office",
                "router_on_a_stick",
                "three_router_triangle",
                "custom",
            ):
                request = {"template": template, "pcs_per_lan": 2, "dhcp": True}
                if template in {"multi_lan_wan", "branch_office"}:
                    request["wan_model"] = "MSR36-20"
                if template == "hub_spoke":
                    request["routers"] = 3
                if template == "star":
                    request["switches_per_router"] = 2
                if template == "custom":
                    request = {
                        "template": "custom",
                        "custom_plan": plan_topology({}, catalog)["plan"],
                    }
                with self.subTest(template=template):
                    result = plan_topology(request, catalog)
                    self.assertTrue(result["valid"], result.get("errors"))
                    self.assertEqual(
                        estimate_plan(request, catalog)["estimate"]["devices"],
                        len(result["plan"]["devices"]),
                    )
                    generated = generate_configs(result["plan"], catalog)
                    self.assertEqual(generated["status"], "verified", generated.get("errors"))
                    for setting in result["plan"]["host_settings"]:
                        if setting["ipv4"] == "dhcp":
                            self.assertFalse(
                                any(
                                    a["device"] == setting["device"] and ":" not in a["cidr"]
                                    for a in result["plan"]["addresses"]
                                )
                            )
                            self.assertIn(
                                "ip address dhcp-alloc", generated["configs"][setting["device"]]
                            )

    def test_dual_stack_subinterfaces_and_redundant_static_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            (catalog.installation / "devicecfgs/S5820V2-54QS-GE.cfg").write_text(
                "".join(f"interface GigabitEthernet0/{i}\n" for i in range(8)), encoding="utf-8"
            )
            result = plan_topology(
                {
                    "template": "router_on_a_stick",
                    "pcs_per_lan": 4,
                    "dual_stack": True,
                    "dhcp": True,
                },
                catalog,
            )
            self.assertTrue(result["valid"], result.get("errors"))
            self.assertEqual(len(result["plan"]["subinterfaces"]), 2)
            configs = generate_configs(result["plan"], catalog)["configs"]
            self.assertIn("vlan-type dot1q vid 10", configs["r1"])
            self.assertIn("undo ipv6 nd ra halt", configs["r1"])
            self.assertIn("ipv6 address auto", configs["h1_1_1"])
            triangle = plan_topology(
                {"template": "three_router_triangle", "floating_routes": True}, catalog
            )
            self.assertTrue(triangle["valid"], triangle.get("errors"))
            self.assertTrue(any(route["preference"] == 254 for route in triangle["plan"]["routes"]))
            self.assertIn(
                "preference 254", generate_configs(triangle["plan"], catalog)["configs"]["r1"]
            )

    def test_wireless_missing_evidence_is_a_hard_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            result = plan_topology(
                {
                    "access_points": 1,
                    "ap_model": "AP",
                    "ac_model": "AC",
                    "wireless_settings": {
                        "ssid": "Lab",
                        "psk": "test-only-123",
                        "hardware_model": "WA6320-HCL",
                        "serial_ids": ["TEST"],
                    },
                },
                catalog,
            )
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result["errors"][0]["code"], "wireless_evidence_missing")
            self.assertNotIn("plan", result)

    def test_static_dhcp_conflict_and_physical_link_to_logical_interface_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            plan = plan_topology({"dhcp": True}, catalog)["plan"]
            plan["addresses"].append(
                {"device": "r2", "interface": "GigabitEthernet0/2", "cidr": "10.0.0.50/24"}
            )
            self.assertIn(
                "static_address_in_dhcp_pool",
                {e["code"] for e in validate_plan(plan, catalog)["errors"]},
            )
            plan = plan_topology({"template": "router_on_a_stick"}, catalog)["plan"]
            plan["links"][0]["a"]["interface"] = plan["subinterfaces"][0]["parent"] + ".10"
            self.assertEqual(validate_plan(plan, catalog)["status"], "rejected")


class ProjectEdit040Tests(unittest.TestCase):
    def test_edit_chain_synchronizes_bound_plan_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            store = ProjectStore([paths["root"]], paths["output"])
            catalog = HclCatalog(paths["install"])
            before = snapshot(paths["project"])
            compiled = stage_plan(
                store, catalog, str(paths["project"]), "Build", plan_fixture(), explicit_map()
            )
            renamed = edit_project(
                store,
                catalog,
                compiled["project_directory"],
                "Rename",
                "rename",
                device="计划路由器一",
                new_name="NewR1",
            )
            self.assertEqual(store.inspect(renamed["project_directory"])["links"][0]["a"], "NewR1")
            moved = edit_project(
                store,
                catalog,
                renamed["project_directory"],
                "Move",
                "move",
                device="NewR1",
                x=88.0,
                y=99.0,
            )
            self.assertEqual(
                next(
                    d
                    for d in store.inspect(moved["project_directory"])["devices"]
                    if d["name"] == "NewR1"
                )["x"],
                88.0,
            )
            added = edit_project(
                store,
                catalog,
                moved["project_directory"],
                "Note",
                "note",
                text="新增\n注释",
                x=10.0,
                y=20.0,
            )
            self.assertIn("新增", Path(added["project_file"]).read_text(encoding="utf-8"))
            cleared = edit_project(
                store, catalog, added["project_directory"], "Clear", "clear_notes"
            )
            self.assertNotIn("[[NOTE ", Path(cleared["project_file"]).read_text(encoding="utf-8"))
            unlinked = edit_project(
                store,
                catalog,
                cleared["project_directory"],
                "Unlink",
                "unlink",
                a="NewR1",
                a_port="GE_0/0",
                b="计划路由器二",
                b_port="GE_0/1",
            )
            self.assertEqual(unlinked["link_count"], 0)
            deleted = edit_project(
                store,
                catalog,
                unlinked["project_directory"],
                "Delete",
                "delete",
                device="计划路由器二",
            )
            self.assertEqual(deleted["device_count"], 1)
            self.assertEqual(snapshot(paths["project"]), before)
