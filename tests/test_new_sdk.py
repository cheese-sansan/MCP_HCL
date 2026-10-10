import copy
import json
import tempfile
import unittest
from pathlib import Path

from contract_inventory import RESOURCES, TOOLS
from jsonschema import Draft202012Validator, ValidationError
from test_interface_tuning import REQUEST as TUNING
from test_mcp_contract import call, mcp_session
from test_nat_transactions import STATIC
from test_netstream_transactions import REQUEST as STREAM
from test_project_build import configure_fixture, explicit_map, plan_fixture
from test_switch_security import PORT, STP

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan

REQUESTS = {
    "hcl_apply_nat": STATIC,
    "hcl_remove_nat": STATIC,
    "hcl_apply_interface_tuning": TUNING,
    "hcl_apply_stp": STP,
    "hcl_apply_port_security": PORT,
    "hcl_apply_netstream": STREAM,
}


class NewSdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_nine_discovery_schema_default_gate_and_envelope(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            store = ProjectStore([paths["root"]], paths["output"])
            staged = stage_plan(
                store,
                HclCatalog(paths["install"]),
                str(paths["project"]),
                "SdkNew",
                plan_fixture(),
                explicit_map(),
            )
            plan = json.loads(
                (Path(staged["project_directory"]) / "MCPArtifacts/plan.json").read_text(
                    encoding="utf-8"
                )
            )
            async with mcp_session(paths) as session:
                listed = await session.list_tools()
                tools = {row.name: row for row in listed.tools}
                self.assertEqual(set(tools), TOOLS)
                self.assertIsNone(listed.nextCursor)
                self.assertEqual(
                    {str(row.uri) for row in (await session.list_resources()).resources}, RESOURCES
                )
                requests = {
                    tool: {
                        "project_path": staged["project_directory"],
                        "topology": "lab",
                        "parameters": params,
                    }
                    for tool, params in REQUESTS.items()
                }
                requests.update(
                    hcl_diff={
                        "project_path": staged["project_directory"],
                        "topology": "lab",
                        "plan": plan,
                    },
                    hcl_health_check={
                        "project_path": staged["project_directory"],
                        "topology": "lab",
                    },
                    hcl_audit_security={
                        "project_path": staged["project_directory"],
                        "topology": "lab",
                    },
                )
                for tool, args in requests.items():
                    with self.subTest(tool=tool):
                        schema = tools[tool].inputSchema
                        Draft202012Validator.check_schema(schema)
                        Draft202012Validator(schema).validate(args)
                        self.assertFalse(schema["additionalProperties"])
                        response, body = await call(session, tool, args)
                        self.assertFalse(response.isError)
                        self.assertEqual(body["errors"][0]["code"], "writes_disabled")
                        self.assertEqual(body["contract_version"], 2)
                        self.assertEqual(body["operation"], tool)
                        self.assertFalse(body["full_live_gate_passed"])
                        self.assertFalse(body["runtime_verified"])
                        self.assertEqual(response.structuredContent, body)
                        bad = args | {"unexpected": True}
                        response, body = await call(session, tool, bad)
                        self.assertTrue(response.isError)
                        self.assertEqual(body["errors"][0]["code"], "extra_forbidden")
                for tool, args in requests.items():
                    with self.subTest(tool=tool, outer="type"):
                        field = "dry_run" if tool in REQUESTS else "timeout_seconds"
                        response, body = await call(
                            session, tool, args | {field: 1 if field == "dry_run" else True}
                        )
                        self.assertTrue(response.isError)
                        self.assertEqual(body["status"], "rejected")
                        response, body = await call(
                            session, tool, {k: v for k, v in args.items() if k != "project_path"}
                        )
                        self.assertTrue(response.isError)

    async def test_write_tool_preview_and_nested_validation_without_native_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            store = ProjectStore([paths["root"]], paths["output"])
            staged = stage_plan(
                store,
                HclCatalog(paths["install"]),
                str(paths["project"]),
                "SdkPreview",
                plan_fixture(),
                explicit_map(),
            )
            async with mcp_session(paths) as session:
                tools = {row.name: row for row in (await session.list_tools()).tools}
                for tool, params in REQUESTS.items():
                    args = {
                        "project_path": staged["project_directory"],
                        "topology": "lab",
                        "parameters": params,
                        "dry_run": True,
                    }
                    with self.subTest(tool=tool):
                        response, body = await call(session, tool, args)
                        self.assertFalse(response.isError)
                        self.assertEqual(
                            body["status"],
                            "output_received" if tool == "hcl_apply_netstream" else "verified",
                            body,
                        )
                        self.assertFalse(body["configuration_verified"])
                        self.assertFalse(body["full_live_gate_passed"])
                        bad = args | {"parameters": params | {"unexpected": True}}
                        with self.assertRaises(ValidationError):
                            Draft202012Validator(tools[tool].inputSchema).validate(bad)
                        response, body = await call(session, tool, bad)
                        self.assertEqual(body["status"], "rejected")
                        self.assertEqual(body["errors"][0]["code"], "extra_forbidden")
                        response, body = await call(
                            session, tool, args | {"parameters": params | {"timeout_seconds": True}}
                        )
                        self.assertEqual(body["status"], "rejected")
