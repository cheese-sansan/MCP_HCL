from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
                    await asyncio.wait_for(session.initialize(), timeout=10)
                    listed = await asyncio.wait_for(session.list_tools(), timeout=10)
                    self.assertEqual(
                        {tool.name for tool in listed.tools},
                        {
                            "hcl_capabilities", "hcl_list_projects", "hcl_inspect_project",
                            "hcl_stage_add_device", "hcl_stage_link",
                        },
                    )
                    result = await asyncio.wait_for(session.call_tool("hcl_capabilities", {}), timeout=10)
                    self.assertFalse(result.isError)
                    content = json.loads(result.content[0].text)
                    self.assertIn("opening the staged .net", content["gui_activation"])


if __name__ == "__main__":
    unittest.main()
