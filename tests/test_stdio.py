from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_hcl import __version__


class StdioProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_can_discover_and_call_tools(self) -> None:
        with tempfile.TemporaryDirectory() as output_root:
            environment = dict(os.environ)
            environment["MCP_HCL_OUTPUT_ROOT"] = output_root
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_hcl.server"],
                env=environment,
            )
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    initialized = await asyncio.wait_for(session.initialize(), timeout=10)
                    self.assertEqual(initialized.serverInfo.version, __version__)
                    listed = await asyncio.wait_for(session.list_tools(), timeout=10)
                    self.assertEqual(
                        {tool.name for tool in listed.tools},
                        {
                            "hcl_capabilities", "hcl_list_projects", "hcl_inspect_project",
                            "hcl_stage_add_device", "hcl_stage_link",
                            "hcl_stage_copy", "hcl_parity_report", "hcl_bridge_status",
                            "hcl_list_devices", "hcl_get_device_details",
                            "hcl_validate_plan",
                            "hcl_backend_capabilities", "hcl_backend_topology",
                            "hcl_device_power", "hcl_console_exec",
                            "hcl_list_modules", "hcl_list_templates", "hcl_plan_topology", "hcl_estimate_plan",
                            "hcl_explain_plan", "hcl_fix_plan", "hcl_generate_configs", "hcl_generate_operations",
                            "hcl_export_artifacts", "hcl_load_plan",
                        },
                    )
                    result = await asyncio.wait_for(session.call_tool("hcl_capabilities", {}), timeout=10)
                    self.assertFalse(result.isError)
                    content = json.loads(result.content[0].text)
                    self.assertIn("opening the staged .net", content["gui_activation"])
                    self.assertFalse(content["live_gate"]["full_live_gate_passed"])
                    resources = await session.list_resources()
                    self.assertEqual({str(resource.uri) for resource in resources.resources},
                                     {"hcl://capabilities", "hcl://catalog/devices", "hcl://catalog/ports", "hcl://catalog/aliases", "hcl://catalog/cables", "hcl://catalog/templates"})
                    resource = await session.read_resource("hcl://capabilities")
                    self.assertEqual(json.loads(resource.contents[0].text), {key: content[key] for key in json.loads(resource.contents[0].text)})
                    report_result = await session.call_tool("hcl_parity_report", {})
                    report = json.loads(report_result.content[0].text)
                    self.assertEqual(len(report["tools"]), 61)
                    self.assertEqual(len(report["resources"]), 5)
                    self.assertEqual(set(report["registered_tools"]), {tool.name for tool in listed.tools})
                    self.assertEqual(report["completion"], "incomplete")
                    self.assertNotIn("hcl_live_deploy", {tool.name for tool in listed.tools})


if __name__ == "__main__":
    unittest.main()
