"""Offline MCP registrations; domain implementations remain outside the façade."""
import json
from mcp_hcl.artifacts import Artifacts
from mcp_hcl.planning import plan_topology, estimate_plan, explain_plan, fix_plan
from mcp_hcl.generation import generate_configs, generate_operations
from mcp_hcl.project_build import stage_plan


def register_offline(mcp, catalog, store, catalog_read):
    artifacts=Artifacts(store.output_root,catalog)

    @mcp.tool()
    def hcl_stage_plan(project_path: str, stage_name: str, plan: dict,
                       port_map: dict[str, dict[str, str]], idempotency_key: str | None = None) -> dict:
        """Compile a validated plan into a separate .net project using real source models.

        Replaces source devices/notes in the copy. Every linked CLI port needs
        an explicit model-to-scene map. Command transcripts stay outside startup
        configs. No GUI open, VM creation, power, CLI deployment or connectivity
        is claimed by a staged result.
        """
        return stage_plan(store, catalog, project_path, stage_name, plan, port_map)

    @mcp.tool()
    def hcl_list_modules(model: str | None = None) -> dict:
        """Read the documented native NIC mode and fixed profiles; model compatibility is unverified."""
        return catalog_read(lambda:catalog.modules(model))

    @mcp.tool()
    def hcl_list_templates() -> dict:
        """List deterministic HCL-native graph templates."""
        return catalog.templates()

    @mcp.tool()
    def hcl_plan_topology(request: dict) -> dict:
        """Build a deterministic plan from a strict TopologyRequest; never deploy."""
        return plan_topology(request,catalog)

    @mcp.tool()
    def hcl_estimate_plan(request: dict) -> dict:
        """Use the same planner to count devices, links, addresses and services."""
        return estimate_plan(request,catalog)

    @mcp.tool()
    def hcl_explain_plan(plan: dict) -> dict:
        """Explain a valid saved plan and its evidence boundaries without an LLM."""
        return explain_plan(plan,catalog)

    @mcp.tool()
    def hcl_fix_plan(plan: dict) -> dict:
        """Return a repaired copy; preserve manually supplied addresses and services."""
        return fix_plan(plan,catalog)

    @mcp.tool()
    def hcl_generate_configs(plan: dict) -> dict:
        """Generate documented Comware templates for ten typed services, offline only."""
        return generate_configs(plan,catalog)

    @mcp.tool()
    def hcl_generate_operations(plan: dict, include_configs: bool = True) -> dict:
        """Generate a declarative HCL operation manifest; executable=false until live adapters are accepted."""
        return generate_operations(plan,catalog,include_configs)

    @mcp.tool()
    def hcl_export_artifacts(plan: dict, artifact_name: str, idempotency_key: str | None = None) -> dict:
        """Atomically export an offline plan/config/operation bundle under the output root."""
        return artifacts.export(plan,artifact_name,idempotency_key)

    @mcp.tool()
    def hcl_load_plan(artifact_directory: str) -> dict:
        """Hash-check and reload an exported plan; never open the HCL GUI."""
        return artifacts.load(artifact_directory)

    @mcp.resource('hcl://catalog/aliases')
    def aliases_resource() -> str:
        return json.dumps(catalog_read(catalog.aliases),ensure_ascii=False)

    @mcp.resource('hcl://catalog/cables')
    def cables_resource() -> str:
        return json.dumps(catalog_read(catalog.cables),ensure_ascii=False)

    @mcp.resource('hcl://catalog/templates')
    def templates_resource() -> str:
        return json.dumps(catalog.templates(),ensure_ascii=False)
