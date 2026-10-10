from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

from contract_inventory import TOOLS
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_hcl import __version__


class StdioProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_can_discover_and_call_tools(self) -> None:
        with tempfile.TemporaryDirectory() as output_root:
            environment = dict(os.environ)
            environment["MCP_HCL_OUTPUT_ROOT"] = output_root
            environment["MCP_HCL_ALLOW_LIVE_WRITE"] = "0"
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
                    self.assertEqual({tool.name for tool in listed.tools}, TOOLS)
                    result = await asyncio.wait_for(
                        session.call_tool("hcl_capabilities", {}), timeout=10
                    )
                    self.assertFalse(result.isError)
                    content = json.loads(result.content[0].text)
                    self.assertIn("opening the staged .net", content["gui_activation"])
                    self.assertFalse(content["live_gate"]["full_live_gate_passed"])
                    resources = await session.list_resources()
                    self.assertEqual(
                        {str(resource.uri) for resource in resources.resources},
                        {
                            "hcl://capabilities",
                            "hcl://catalog/devices",
                            "hcl://catalog/ports",
                            "hcl://catalog/aliases",
                            "hcl://catalog/cables",
                            "hcl://catalog/templates",
                        },
                    )
                    resource = await session.read_resource("hcl://capabilities")
                    self.assertEqual(
                        json.loads(resource.contents[0].text),
                        {key: content[key] for key in json.loads(resource.contents[0].text)},
                    )
                    report_result = await session.call_tool("hcl_parity_report", {})
                    report = json.loads(report_result.content[0].text)
                    self.assertEqual(len(report["tools"]), 61)
                    self.assertEqual(len(report["resources"]), 5)
                    self.assertEqual(
                        set(report["registered_tools"]), {tool.name for tool in listed.tools}
                    )
                    self.assertEqual(report["completion"], "incomplete")
                    self.assertIn("hcl_live_deploy", {tool.name for tool in listed.tools})


if __name__ == "__main__":
    unittest.main()
