"""MCP stdio façade for evidence-backed HCL project staging."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_hcl import __version__
from mcp_hcl.project import ProjectError, ProjectStore


def create_store() -> ProjectStore:
    output_root = Path(os.environ.get("MCP_HCL_OUTPUT_ROOT", "work/staged"))
    configured = os.environ.get("MCP_HCL_PROJECT_ROOTS", "")
    project_roots = [Path(item) for item in configured.split(";") if item.strip()]
    if not project_roots:
        project_roots = [Path.home() / "HCL" / "Projects"]
    return ProjectStore(project_roots=project_roots, output_root=output_root)


def create_server(store: ProjectStore | None = None) -> FastMCP:
    store = store or create_store()
    mcp = FastMCP(
        name="mcp-hcl",
        instructions=(
            "HCL topology changes are staged as separate project files. "
            "After staging, the user must open the returned .net file in HCL. "
            "A staged result is not a live-canvas result."
        ),
    )

    @mcp.tool()
    def hcl_capabilities() -> dict[str, Any]:
        """Describe verified capabilities and the activation boundary."""
        return {
            "version": __version__,
            "project_inspection": "available",
            "stage_device_and_link": "available",
            "gui_activation": "requires opening the staged .net project in HCL",
            "live_canvas_api": "not verified and not exposed",
            "device_start_and_console": "not implemented",
            "output_root": str(store.output_root),
        }

    @mcp.tool()
    def hcl_list_projects() -> dict[str, Any]:
        """List HCL projects immediately under configured project roots."""
        return {"projects": store.list_projects()}

    @mcp.tool()
    def hcl_inspect_project(project_path: str) -> dict[str, Any]:
        """Read devices and links from one saved HCL project without changing it."""
        try:
            return {"status": "ok", **store.inspect(project_path)}
        except (ProjectError, OSError) as exc:
            return {"status": "rejected", "error": str(exc)}

    @mcp.tool()
    def hcl_stage_add_device(
        project_path: str,
        stage_name: str,
        template_device: str,
        new_name: str,
        x: float,
        y: float,
        connect_to: str | None = None,
        connect_to_port: str | None = None,
        new_port: str | None = None,
    ) -> dict[str, Any]:
        """Copy a project, add a device cloned from a known model, and optionally link it."""
        try:
            return store.stage_add_device(
                project_path, stage_name, template_device, new_name, x, y,
                connect_to, connect_to_port, new_port,
            )
        except (ProjectError, OSError) as exc:
            return {"status": "rejected", "error": str(exc)}

    @mcp.tool()
    def hcl_stage_link(
        project_path: str,
        stage_name: str,
        a: str,
        a_port: str,
        b: str,
        b_port: str,
    ) -> dict[str, Any]:
        """Copy a project and add a reciprocal link between two free ports."""
        try:
            return store.stage_link(project_path, stage_name, a, a_port, b, b_port)
        except (ProjectError, OSError) as exc:
            return {"status": "rejected", "error": str(exc)}

    return mcp


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
