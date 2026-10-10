"""Plan → isolated project → optional gated GUI activation, never guest boot."""

from mcp_hcl.gui_relay import rejected
from mcp_hcl.planning import plan_topology
from mcp_hcl.project_build import stage_plan


def full_build(
    store,
    catalog,
    relay,
    project_path,
    stage_name,
    request,
    port_map,
    activate=False,
    hcl_pid=None,
    idempotency_key=None,
):
    if activate:
        if not relay.writes_enabled:
            return rejected("writes_disabled", "GUI activation requires the live write switch")
        if hcl_pid is None:
            return rejected("missing_argument", "activate=true requires hcl_pid")
        if idempotency_key is not None:
            return rejected(
                "live_replay_unsupported",
                "Key the offline build first, then invoke hcl_open_project explicitly",
            )
    elif hcl_pid is not None:
        return rejected("invalid_arguments", "hcl_pid belongs to activate=true")
    planned = plan_topology(request, catalog)
    if not planned.get("valid"):
        return planned
    staged = stage_plan(store, catalog, project_path, stage_name, planned["plan"], port_map)
    if staged["status"] != "staged":
        return staged
    staged["plan"] = planned["plan"]
    staged["steps"] = [
        {"operation": "plan_topology", "status": "verified"},
        {"operation": "stage_plan", "status": "staged", "operation_id": staged["operation_id"]},
    ]
    if activate:
        result = relay.execute("open", staged["project_directory"], hcl_pid)
        staged["activation_result"] = result
        staged["steps"].append(
            {
                "operation": "gui_open",
                "status": result["status"],
                "operation_id": result.get("operation_id"),
            }
        )
        staged["status"] = "partial"
        staged["warnings"].append(
            {
                "code": "full_live_build_unverified",
                "message": "GUI identity does not prove canvas topology, guest boot, configuration or connectivity",
            }
        )
    return staged


def register_build_tool(mcp, store, catalog, relay):
    @mcp.tool()
    def hcl_full_build(
        project_path: str,
        stage_name: str,
        request: dict,
        port_map: dict[str, dict[str, str]],
        activate: bool = False,
        hcl_pid: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Plan and compile an isolated HCL project, optionally open it in an existing GUI.

        activate defaults false. No VM power or CLI deployment occurs. Offline
        builds support durable idempotency; live activation is never replayed.
        """
        return full_build(
            store,
            catalog,
            relay,
            project_path,
            stage_name,
            request,
            port_map,
            activate,
            hcl_pid,
            idempotency_key,
        )
