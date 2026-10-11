"""Independent examples and real SDK discovery for the complete API gap report."""

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_inventory import RESOURCES, TOOLS
from test_mcp_contract import build_fixture, call, mcp_session

from mcp_hcl.api_compatibility import api_compatibility_report, load_upstream_contracts
from mcp_hcl.parity import parity_report


class ApiCompatibilitySdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_upstream_rows_use_actual_sdk_inputs_without_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            async with mcp_session(paths) as session:
                schemas = {
                    tool.name: tool.inputSchema for tool in (await session.list_tools()).tools
                }
                self.assertEqual(set(schemas), TOOLS)
                uris = {
                    str(resource.uri) for resource in (await session.list_resources()).resources
                }
                self.assertEqual(uris, RESOURCES)
                result, report = await call(session, "hcl_parity_report", {})
                self.assertFalse(result.isError)
                api = report["api_compatibility"]
                self.assertEqual(len(api["tools"]), 62)
                self.assertEqual(len(api["resources"]), 5)
                self.assertEqual(api["discovered_hcl_tool_count"], 55)
                self.assertEqual(api["discovered_hcl_resource_count"], 6)
                for row in api["tools"]:
                    with self.subTest(tool=row["upstream_tool"]):
                        self.assertFalse(row["upstream_alias_registered"])
                        self.assertFalse(row["automatic_translation_available"])
                        self.assertEqual(row["output_equivalence"], "unverified")
                        self.assertEqual(row["error_equivalence"], "unverified")
                        self.assertEqual(row["behavior_equivalence"], "unverified")
                        for target in row["hcl_targets"]:
                            self.assertEqual(target["registered"], target["name"] in schemas)
                            if target["registered"]:
                                self.assertEqual(target["input_schema"], schemas[target["name"]])
                for row in api["resources"]:
                    with self.subTest(resource=row["upstream_uri"]):
                        self.assertEqual(row["registered"], row["hcl_uri"] in uris)
                        self.assertFalse(row["automatic_translation_available"])
                rows = {row["upstream_tool"]: row for row in api["tools"]}
                dhcp = rows["pt_configure_dhcp_server"]
                self.assertEqual(dhcp["availability"], "not_implemented")
                planning = rows["pt_plan_topology"]
                upstream = {p["name"]: p for p in planning["upstream_declaration"]["parameters"]}
                self.assertEqual(upstream["dhcp"]["default"], {"kind": "literal", "value": True})
                self.assertEqual(upstream["eigrp_as"]["default"]["value"], 100)
                target = planning["hcl_targets"][0]
                self.assertIn("request", target["input_differences"]["hcl_only_names"])
                request = target["input_schema"]["properties"]["request"]["properties"]
                self.assertIs(request["dhcp"]["default"], False)
                self.assertNotIn("eigrp", request["routing"]["enum"])
                wrapped = target["input_differences"]["wrapped_input_candidates"][0]
                self.assertEqual(wrapped["hcl_argument"], "request")
                self.assertIn("dhcp", wrapped["differences"]["defaults_changed"])
                self.assertIn("eigrp_as", wrapped["differences"]["upstream_only_names"])
                self.assertEqual(rows["pt_add_device"]["availability"], "not_implemented")
                self.assertEqual(
                    rows["pt_add_device"]["staged_alternatives"][0]["scope"], "saved_project_only"
                )
                self.assertFalse(report["full_live_gate_passed"])
                self.assertEqual(report["completion"], "incomplete")


class ApiComparisonTests(unittest.TestCase):
    def test_current_discovery_replaces_catalog_claims_and_does_not_mutate_inputs(self):
        inventory = parity_report()
        schemas = {
            "hcl_list_projects": {
                "type": "object",
                "properties": {"output_dir": {"type": "string", "default": "other"}},
                "required": ["output_dir"],
            }
        }
        original = copy.deepcopy(schemas)
        report = api_compatibility_report(inventory, schemas, set())
        rows = {row["upstream_tool"]: row for row in report["tools"]}
        diff = rows["pt_list_projects"]["hcl_targets"][0]["input_differences"]
        self.assertEqual(diff["defaults_changed"], ["output_dir"])
        self.assertEqual(diff["requiredness_changed"], ["output_dir"])
        self.assertEqual(rows["pt_list_devices"]["availability"], "not_implemented")
        self.assertTrue(all(not row["registered"] for row in report["resources"]))
        rows["pt_list_projects"]["hcl_targets"][0]["input_schema"]["properties"].clear()
        self.assertEqual(schemas, original)
        again = api_compatibility_report(inventory, original, set())
        self.assertEqual(report["hcl_input_schemas_sha256"], again["hcl_input_schemas_sha256"])

    def test_null_default_differs_from_no_default_and_bool_differs_from_int(self):
        inventory = parity_report()
        snapshot = load_upstream_contracts(inventory)
        snapshot["tools"]["pt_list_projects"]["parameters"] = [
            {
                "name": "a",
                "required": False,
                "annotation": "bool",
                "default": {"kind": "literal", "value": True},
            },
            {
                "name": "b",
                "required": False,
                "annotation": "str | None",
                "default": {"kind": "literal", "value": None},
            },
        ]
        schema = {"properties": {"a": {"default": 1}, "b": {}}}
        with patch("mcp_hcl.api_compatibility.load_upstream_contracts", return_value=snapshot):
            report = api_compatibility_report(inventory, {"hcl_list_projects": schema}, set())
        row = next(r for r in report["tools"] if r["upstream_tool"] == "pt_list_projects")
        self.assertEqual(row["hcl_targets"][0]["input_differences"]["defaults_changed"], ["a", "b"])

    def test_revision_source_and_completeness_mismatches_are_rejected(self):
        for mode in ("revision", "source", "tool", "resource"):
            with self.subTest(mode=mode):
                inventory = parity_report()
                if mode == "revision":
                    inventory["upstream"]["revision"] = "wrong"
                elif mode == "source":
                    inventory["upstream"]["tool_registry_sha256"] = "wrong"
                elif mode == "tool":
                    inventory["tools"].pop()
                else:
                    inventory["resources"].pop()
                with self.assertRaises(ValueError):
                    load_upstream_contracts(inventory)

    def test_changed_snapshot_bytes_are_rejected(self):
        with patch("mcp_hcl.api_compatibility.UPSTREAM_CONTRACTS_SHA256", "invalid"):
            with self.assertRaisesRegex(ValueError, "snapshot bytes"):
                load_upstream_contracts(parity_report())


class CaptureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/capture_upstream_contracts.py"
        spec = importlib.util.spec_from_file_location("capture_contracts", path)
        cls.capture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.capture)

    def test_source_is_never_imported_and_expression_default_is_never_executed(self):
        source = b"""raise RuntimeError("must not run")
@mcp.tool()
def pt_example(required: str, nullable: str | None = None, lazy: str = danger()) -> str:
    raise RuntimeError("must not run")
"""
        params = self.capture.declarations(source, "tool")["pt_example"]["parameters"]
        self.assertTrue(params[0]["required"])
        self.assertEqual(params[1]["default"], {"kind": "literal", "value": None})
        self.assertEqual(params[2]["default"], {"kind": "expression", "source": "danger()"})

    def test_source_hash_and_duplicate_declarations_are_rejected(self):
        tool = b"@mcp.tool()\ndef pt_example() -> str: pass\n"
        resource = b'@mcp.resource("pt://example")\ndef r() -> str: pass\n'
        inventory = {
            "upstream": {
                "revision": "test",
                "tool_registry_sha256": hashlib.sha256(tool).hexdigest(),
                "resource_registry_sha256": hashlib.sha256(resource).hexdigest(),
            },
            "tools": [{"upstream_tool": "pt_example"}],
            "resources": [{"upstream_uri": "pt://example"}],
        }
        self.assertEqual(len(self.capture.capture(tool, resource, inventory)["tools"]), 1)
        with self.assertRaisesRegex(ValueError, "pinned source bytes"):
            self.capture.capture(tool + b"\n", resource, inventory)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.capture.declarations(tool + tool, "tool")

    def test_packaged_snapshot_has_independently_known_parameters(self):
        snapshot = load_upstream_contracts(parity_report())
        self.assertEqual(
            snapshot["tools"]["pt_get_device_details"]["parameters"],
            [{"name": "model_name", "annotation": "str", "required": True}],
        )
        self.assertEqual(
            snapshot["tools"]["pt_list_projects"]["parameters"],
            [
                {
                    "name": "output_dir",
                    "annotation": "str",
                    "required": False,
                    "default": {"kind": "literal", "value": "projects"},
                }
            ],
        )
        self.assertEqual(
            set(snapshot["resources"]),
            {
                "pt://capabilities",
                "pt://catalog/devices",
                "pt://catalog/cables",
                "pt://catalog/aliases",
                "pt://catalog/templates",
            },
        )


if __name__ == "__main__":
    unittest.main()
