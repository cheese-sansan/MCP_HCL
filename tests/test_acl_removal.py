"""Necessary exact-removal, binding preservation and recovery contracts."""

import tempfile
import unittest
from pathlib import Path

import test_policy as fixtures
from contract_inventory import TOOLS
from pydantic import ValidationError
from test_mcp_contract import call, mcp_session
from test_project_build import configure_fixture, explicit_map, plan_fixture, snapshot

from mcp_hcl.acl_removal import AclRemoval, RemoveAcl, removal_intent, removal_verified
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.console import ConsoleError
from mcp_hcl.policy import scopes
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan

BASE = fixtures.BASE.replace(
    " mtu 1400",
    " mtu 1400\n packet-filter 3001 inbound\n packet-filter 3001 outbound\n packet-filter ipv6 3001 inbound",
)
BASE = BASE.replace("return\n", "#\nacl advanced 3001 name EDGE_WEB\n rule 5 deny tcp\n#\nreturn\n")
REQUEST = {
    "number": 3001,
    "binding_interface": "GigabitEthernet0/0",
    "binding_direction": "inbound",
}


class RemovalReadbackTests(unittest.TestCase):
    def test_identifier_bounds_and_named_type_resolution(self):
        named = AclRemoval(name="EDGE_WEB")
        self.assertIsNone(removal_intent(named)[0])
        commands, header = removal_intent(named, BASE)
        self.assertIn("undo acl advanced name edge_web", commands)
        self.assertEqual(header["number"], 3001)
        for parameters in (
            {"number": True},
            {"number": 1999},
            {"name": "all"},
            {"name": "bad\nreboot"},
            {"number": 3001, "name": "edge"},
            {"number": 3001, "acl_type": "basic"},
        ):
            with self.assertRaises(ValidationError):
                AclRemoval.model_validate(parameters)

    def test_only_requested_binding_and_definition_may_disappear(self):
        typed = AclRemoval.model_validate(REQUEST)
        commands, header = removal_intent(typed, BASE)
        self.assertIn("undo packet-filter 3001 inbound", commands)
        after = BASE.replace(" packet-filter 3001 inbound\n", "").replace(
            "acl advanced 3001 name EDGE_WEB\n rule 5 deny tcp\n", ""
        )
        self.assertTrue(removal_verified(BASE, after, typed, header))
        for changed in (
            after.replace(" packet-filter 3001 outbound\n", ""),
            after.replace("mtu 1400", "mtu 1500"),
            after.replace(" packet-filter ipv6 3001 inbound\n", ""),
        ):
            self.assertFalse(removal_verified(BASE, changed, typed, header))
        named = AclRemoval(name="edge_web")
        self.assertFalse(removal_verified(BASE, BASE.replace(" name EDGE_WEB", ""), named, header))


class RemovalGuest(fixtures.Guest):
    def __init__(self):
        super().__init__()
        self.current = BASE
        self.delete_fail = False

    def exchange(self, command):
        if command.startswith("undo acl "):
            self.commands.append(command)
            if self.delete_fail:
                raise ConsoleError("Delete rejected", code="command_rejected")
            views = scopes(self.current)
            tokens = command.split()
            number = tokens[-1] if tokens[-2] != "name" else None
            name = tokens[-1] if number is None else None
            for context, body in list(views.items()):
                if context and (
                    context[0] == "acl number " + number
                    if number is not None
                    else "@acl-name " + name in body or context[0].endswith(" name " + name)
                ):
                    views.pop(context)
            self.current = self.text(views)
            self.changed = True
            return ""
        return super().exchange(command)


class RemovalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PolicyTests("test_master_gate_and_dry_run_do_not_open_a_console")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.guest = RemovalGuest()

    def engine(self, writes=True):
        return RemoveAcl(self.fixture.engine(writes))

    def test_gated_preview_and_missing_named_type_do_not_open(self):
        self.assertEqual(
            self.engine(False).apply("missing", "lab", "r1", REQUEST)["errors"][0]["code"],
            "writes_disabled",
        )
        dry = self.engine().apply(self.fixture.project, "lab", "r1", REQUEST, True)
        self.assertIn("undo acl advanced 3001", dry["commands"])
        self.assertEqual(self.fixture.opens, 0)
        unresolved = self.engine().apply(
            self.fixture.project, "lab", "r1", {"name": "edge_web"}, True
        )
        self.assertEqual(unresolved["status"], "unverified")
        self.assertTrue(unresolved["requires_current_acl_type"])

    def test_exact_numbered_removal_persists_and_preserves_other_bindings(self):
        result = self.engine().apply(self.fixture.project, "lab", "r1", REQUEST)
        self.assertTrue(result["protocol_effect_verified"], result)
        self.assertTrue(result["protocol_persistence_verified"])
        self.assertFalse(result["configuration_verified"])
        current = self.fixture.guest.current
        self.assertNotIn("acl number 3001", current)
        self.assertIn("acl number 3002", current)
        self.assertIn("packet-filter 3001 outbound", current)
        self.assertIn("packet-filter ipv6 3001 inbound", current)
        self.assertEqual(snapshot(Path(self.fixture.project)), self.fixture.before)

    def test_named_number_alias_is_deleted_as_whole_definition(self):
        result = self.engine().apply(
            self.fixture.project,
            "lab",
            "r1",
            {"name": "EDGE_WEB", "binding_interface": "GigabitEthernet0/0"},
        )
        self.assertTrue(result["protocol_effect_verified"], result)
        self.assertNotIn("name edge_web", self.fixture.guest.current.casefold())
        self.assertNotIn("acl number 3001", self.fixture.guest.current)

    def test_delete_failure_restores_binding_without_replaying_removal(self):
        self.fixture.guest.delete_fail = True
        result = self.engine().apply(self.fixture.project, "lab", "r1", REQUEST)
        self.assertTrue(result["protocol_rollback_verified"], result)
        self.assertFalse(result["rollback_verified"])
        self.assertEqual(self.fixture.guest.current, BASE)
        self.assertEqual(self.fixture.guest.commands.count("undo acl advanced 3001"), 1)

    def test_recovery_identity_change_is_retained_as_unverified(self):
        self.fixture.guest.delete_fail = True
        self.fixture.identity_changed = True
        result = self.engine().apply(self.fixture.project, "lab", "r1", REQUEST)
        self.assertFalse(result["protocol_rollback_verified"])
        self.assertEqual(result["rollback"]["error"]["code"], "recovery_target_changed")


class RemovalStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_discovery_gate_and_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            store = ProjectStore([paths["root"]], paths["output"])
            catalog = HclCatalog(paths["install"])
            project = stage_plan(
                store, catalog, str(paths["project"]), "Removal", plan_fixture(), explicit_map()
            )["project_directory"]
            async with mcp_session(paths) as session:
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                self.assertEqual(set(tools), TOOLS)
                self.assertIn(
                    "binding_interface",
                    tools["hcl_remove_acl"].inputSchema["properties"]["parameters"]["properties"],
                )
                arguments = {
                    "project_path": project,
                    "topology": "lab",
                    "device": "r1",
                    "parameters": REQUEST,
                }
                response, body = await call(session, "hcl_remove_acl", arguments)
                self.assertFalse(response.isError)
                self.assertEqual(body["errors"][0]["code"], "writes_disabled")
                response, body = await call(
                    session, "hcl_remove_acl", arguments | {"dry_run": True}
                )
                self.assertEqual(body["status"], "verified")
                self.assertIn("undo acl advanced 3001", body["commands"])
