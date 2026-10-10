"""Behavioral offline tests, with expectations taken from HCL command reference examples."""

from __future__ import annotations

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_inventory import TOOLS
from offline_fixtures import installation, service_plan
from test_mcp_contract import build_fixture, call, mcp_session

from mcp_hcl.artifacts import Artifacts
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.generation import generate_configs, generate_operations
from mcp_hcl.planning import estimate_plan, fix_plan, plan_topology
from mcp_hcl.project import ProjectStore
from mcp_hcl.server import create_server


class ArtifactBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = installation(self.root / "install")
        self.plan = service_plan()

    def test_atomic_export_restart_reload_and_tamper(self):
        artifacts = Artifacts(self.root / "output", self.catalog)
        first = artifacts.export(self.plan, "Export1", "export-key")
        replay = Artifacts(self.root / "output", self.catalog).export(
            self.plan, "Export1", "export-key"
        )
        self.assertEqual(first["operation_id"], replay["operation_id"])
        self.assertTrue(replay["replayed"])
        loaded = artifacts.load(first["artifact_directory"])
        self.assertEqual(loaded["status"], "verified")
        self.assertEqual(loaded["plan"], generate_configs(self.plan, self.catalog)["plan"])
        operations = json.loads((Path(first["artifact_directory"]) / "operations.json").read_text())
        self.assertFalse(operations["executable"])
        (Path(first["artifact_directory"]) / "configs/r1.cfg").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            artifacts.load(first["artifact_directory"])
        self.assertEqual(
            artifacts.export(self.plan, "Export1", "export-key")["errors"][0]["code"],
            "artifact_changed",
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            artifacts.load(str(self.root / "outside"))

    def test_failed_rename_cleans_temporary_files_and_key_can_retry(self):
        artifacts = Artifacts(self.root / "output", self.catalog)
        with patch("mcp_hcl.artifacts.os.rename", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                artifacts.export(self.plan, "FailWrite", "retry-write")
        self.assertFalse((self.root / "output/FailWrite").exists())
        self.assertEqual(list((self.root / "output").glob(".hcl-export-*")), [])
        self.assertEqual(
            artifacts.export(self.plan, "FailWrite", "retry-write")["status"], "verified"
        )

    def test_manifest_corruption_and_same_key_different_input_are_rejected(self):
        artifacts = Artifacts(self.root / "output", self.catalog)
        exported = artifacts.export(self.plan, "Conflict", "key")
        changed = copy.deepcopy(self.plan)
        changed["name"] = "changed"
        self.assertEqual(
            artifacts.export(changed, "Conflict", "key")["errors"][0]["code"],
            "idempotency_conflict",
        )
        directory = Path(exported["artifact_directory"])
        (directory / "manifest.json").write_text('{"schema_version":1,"hashes":{}}')
        with self.assertRaisesRegex(ValueError, "Invalid artifact manifest"):
            artifacts.load(str(directory))

    def test_native_nic_mode_is_not_the_fixed_interface_list(self):
        result = self.catalog.modules()
        self.assertEqual(result["modules"][0]["category"], "virtual_nic_mode")
        self.assertEqual(result["modules"][0]["enhanced_max_connections"], 35)
        self.assertIsNone(result["modules"][0]["ports_added"])
        self.assertFalse(result["expansion_modules_verified"])
        models = {m["model"]: m for m in self.catalog.devices()["devices"]}
        self.assertEqual(models["AC"]["default_interfaces"], [])
        self.assertFalse(models["AC"]["default_configuration_available"])
        self.assertTrue(models["MSR36-20"]["scene_ports"])
        self.assertFalse(any(p["mapping_verified"] for p in models["MSR36-20"]["scene_ports"]))

    def test_operation_manifest_preserves_annotations_and_omits_configs_when_requested(self):
        plan = copy.deepcopy(self.plan)
        plan["annotations"] = [{"text": "隔离实验\n保留说明", "x": 12.0, "y": 34.0}]
        result = generate_operations(plan, self.catalog, include_configs=False)
        self.assertEqual(result["status"], "verified")
        notes = [v for v in result["operations"] if v["action"] == "add_annotation"]
        self.assertEqual(notes, [{"action": "add_annotation", **plan["annotations"][0]}])
        self.assertFalse(any(v["action"] == "configure_device" for v in result["operations"]))
        self.assertFalse(result["executable"])


class PlanningTests(unittest.TestCase):
    def test_planning_estimates_and_export_roundtrip_for_all_templates(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            for template, routers in [
                ("single_lan", 1),
                ("multi_lan", 2),
                ("star", 1),
                ("hub_spoke", 3),
                ("three_router_triangle", 3),
            ]:
                request = {"template": template, "routers": routers, "pcs_per_lan": 1}
                result = plan_topology(request, catalog)
                self.assertTrue(result["valid"], result.get("errors"))
                expected = estimate_plan(request, catalog)["estimate"]
                self.assertEqual(expected["devices"], len(result["plan"]["devices"]))
                self.assertEqual(expected["links"], len(result["plan"]["links"]))
                self.assertEqual(result["plan"], plan_topology(request, catalog)["plan"])
                artifacts = Artifacts(Path(temporary) / "output", catalog)
                exported = artifacts.export(result["plan"], template[:20])
                self.assertEqual(
                    artifacts.load(exported["artifact_directory"])["plan"], result["plan"]
                )
            self.assertEqual(
                plan_topology({"template": "single_lan", "routers": 2}, catalog)["status"],
                "rejected",
            )
            self.assertEqual(
                plan_topology({"lan_pool": "172.16.0.0/16"}, catalog)["status"], "rejected"
            )
            self.assertEqual(plan_topology({"routers": True}, catalog)["status"], "rejected")

    def test_fix_is_conservative_and_does_not_mutate_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = installation(Path(temporary) / "install")
            plan = plan_topology({}, catalog)["plan"]
            plan["devices"][0]["model"] = "msr36-20"
            plan["links"][0]["medium"] = "serial"
            original = copy.deepcopy(plan)
            result = fix_plan(plan, catalog)
            self.assertTrue(result["valid"], result.get("errors"))
            self.assertEqual(plan, original)
            self.assertEqual(result["plan"]["addresses"], original["addresses"])
            self.assertEqual({f["kind"] for f in result["fixes"]}, {"model_alias", "medium"})


class OfflineStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_planning_export_reload_and_schemas(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            async with mcp_session(paths) as session:
                tools = {t.name: t for t in (await session.list_tools()).tools}
                self.assertEqual(set(tools), TOOLS)
                schema = tools["hcl_generate_configs"].inputSchema
                self.assertFalse(schema["additionalProperties"])
                self.assertIn(
                    "discriminator", schema["properties"]["plan"]["properties"]["services"]["items"]
                )
                request_schema = tools["hcl_plan_topology"].inputSchema["properties"]["request"]
                self.assertIn("wireless_clients_per_lan", request_schema["properties"])
                self.assertIn("wireless_client_model", request_schema["properties"])
                invalid = await session.call_tool(
                    "hcl_plan_topology", {"request": {"wireless_clients_per_lan": True}}
                )
                self.assertFalse(invalid.isError)
                self.assertEqual(invalid.structuredContent["status"], "rejected")
                self.assertEqual(invalid.structuredContent["errors"][0]["code"], "int_type")
                from jsonschema import Draft202012Validator
                from test_050_wireless import request as phone_request

                Draft202012Validator(tools["hcl_plan_topology"].inputSchema).validate(
                    {"request": phone_request()}
                )
                _, planned = await call(session, "hcl_plan_topology", {"request": {}})
                self.assertTrue(planned["valid"], planned["errors"])
                _, exported = await call(
                    session,
                    "hcl_export_artifacts",
                    {
                        "plan": planned["plan"],
                        "artifact_name": "stdio",
                        "idempotency_key": "stdio-key",
                    },
                )
                self.assertEqual(exported["status"], "verified", exported["errors"])
                _, loaded = await call(
                    session, "hcl_load_plan", {"artifact_directory": exported["artifact_directory"]}
                )
                self.assertEqual(loaded["plan"], planned["plan"])
                self.assertFalse(loaded["runtime_verified"])
                self.assertNotEqual(exported["request_id"], loaded["request_id"])
                self.assertEqual(len((await session.list_resources()).resources), 6)
