import tempfile
import unittest
from pathlib import Path

from test_mcp_contract import call, mcp_session
from test_project_build import configure_fixture, explicit_map, snapshot

from mcp_hcl.build_pipeline import full_build
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.gui_relay import HclGuiRelay
from mcp_hcl.project import ProjectStore


class BuildPipelineTests(unittest.TestCase):
    def test_failed_activation_prerequisites_do_not_create_a_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            store = ProjectStore([paths["root"]], paths["output"])
            catalog = HclCatalog(paths["install"])
            relay = HclGuiRelay(store)
            result = full_build(
                store, catalog, relay, "nonexistent", "Denied", {}, {}, activate=True, hcl_pid=1
            )
            self.assertEqual(result["errors"][0]["code"], "writes_disabled")
            self.assertFalse(paths["output"].exists())
            relay.writes_enabled = True
            result = full_build(
                store,
                catalog,
                relay,
                "nonexistent",
                "Denied",
                {},
                {},
                activate=True,
                hcl_pid=1,
                idempotency_key="no-live-key",
            )
            self.assertEqual(result["errors"][0]["code"], "live_replay_unsupported")
            self.assertFalse(paths["output"].exists())


class BuildPipelineStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_build_plans_compiles_and_replays_only_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            before = snapshot(paths["project"])
            arguments = {
                "project_path": str(paths["project"]),
                "stage_name": "FullBuild",
                "request": {"switches_per_router": 0, "routing": "ospf"},
                "port_map": explicit_map(),
                "idempotency_key": "full-build-key",
            }
            async with mcp_session(paths) as session:
                result, body = await call(session, "hcl_full_build", arguments)
                self.assertFalse(result.isError)
                self.assertEqual(body["status"], "staged", body)
                self.assertEqual((body["device_count"], body["link_count"]), (2, 1))
                self.assertEqual(
                    [s["operation"] for s in body["steps"]], ["plan_topology", "stage_plan"]
                )
                self.assertNotIn("activation_result", body)
                self.assertFalse(body["full_live_gate_passed"])
                self.assertIn("ospf 1", (Path(body["commands_directory"]) / "r1.txt").read_text())
                _, replay = await call(session, "hcl_full_build", arguments)
                self.assertTrue(replay["replayed"])
                self.assertEqual(replay["operation_id"], body["operation_id"])
            self.assertEqual(snapshot(paths["project"]), before)
