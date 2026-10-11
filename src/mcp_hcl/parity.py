"""A pinned upstream inventory, independent of unverified live capabilities."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any
from uuid import uuid4

UPSTREAM_REVISION = "3c7c7a46b9ea27c914f845d161f95f0fc3f53d5f"
UPSTREAM_TOOL_NAMES_SHA256 = "42a0fd202034cf2a6016ec3fe67f9c8f67eb894f3cb902d4653c7b55ecdc0d69"
REGISTERED_TOOLS = frozenset(
    {
        "hcl_capabilities",
        "hcl_list_projects",
        "hcl_inspect_project",
        "hcl_stage_add_device",
        "hcl_stage_link",
        "hcl_stage_copy",
        "hcl_parity_report",
        "hcl_bridge_status",
        "hcl_list_devices",
        "hcl_get_device_details",
        "hcl_validate_plan",
        # HCL-native control-plane primitives.  They are NOT upstream parity
        # claims: no upstream row is marked implemented by their existence.
        "hcl_backend_capabilities",
        "hcl_backend_topology",
        "hcl_device_power",
        "hcl_console_exec",
        "hcl_list_modules",
        "hcl_list_templates",
        "hcl_plan_topology",
        "hcl_estimate_plan",
        "hcl_explain_plan",
        "hcl_fix_plan",
        "hcl_generate_configs",
        "hcl_generate_operations",
        "hcl_export_artifacts",
        "hcl_load_plan",
        "hcl_stage_plan",
        "hcl_open_project",
        "hcl_save_project",
        "hcl_full_build",
        "hcl_stage_rename_device",
        "hcl_stage_move_device",
        "hcl_stage_delete_device",
        "hcl_stage_unlink",
        "hcl_stage_add_note",
        "hcl_stage_clear_annotations",
        "hcl_backup_config",
        "hcl_restore_config",
        "hcl_live_deploy",
        "hcl_verify_connectivity",
        "hcl_inspect_ports",
        "hcl_read_vlans",
        "hcl_read_qos",
        "hcl_apply_acl",
        "hcl_apply_vlan",
        "hcl_apply_vlan_network",
        "hcl_remove_acl",
        "hcl_apply_nat",
        "hcl_remove_nat",
        "hcl_apply_interface_tuning",
        "hcl_apply_stp",
        "hcl_apply_port_security",
        "hcl_diff",
        "hcl_health_check",
        "hcl_audit_security",
        "hcl_apply_netstream",
    }
)
REGISTERED_RESOURCES = frozenset(
    {
        "hcl://capabilities",
        "hcl://catalog/devices",
        "hcl://catalog/ports",
        "hcl://catalog/aliases",
        "hcl://catalog/cables",
        "hcl://catalog/templates",
    }
)
REPRODUCTION_TARGET_IDS = frozenset(
    {
        "exclusive_cli",
        "native_inventory",
        "live_editing",
        "wired_end_to_end",
        "configuration_semantics",
        "wireless",
        "live_observation",
        "simulation_workspace",
        "dhcp_server",
        "api_compatibility",
        "delivery_evidence",
    }
)


def validate_inventory(inventory: dict[str, Any]) -> None:
    """Reject incomplete inventories and unsupported implementation claims."""
    if inventory.get("schema_version") != 1:
        raise ValueError("Unsupported parity inventory schema")
    if inventory.get("upstream", {}).get("revision") != UPSTREAM_REVISION:
        raise ValueError("Parity inventory has a different upstream revision")
    tools = inventory.get("tools", [])
    resources = inventory.get("resources", [])
    tool_names = [row["upstream_tool"] for row in tools]
    resource_names = [row["upstream_uri"] for row in resources]
    if len(tools) != 62 or len(set(tool_names)) != 62:
        raise ValueError("Parity inventory must contain 62 unique upstream tools")
    if inventory.get("expected_tool_count") != 62 or inventory.get("expected_resource_count") != 5:
        raise ValueError("Declared upstream counts do not match the pinned inventory")
    if len(resources) != 5 or len(set(resource_names)) != 5:
        raise ValueError("Parity inventory must contain 5 unique upstream resources")
    fingerprint = hashlib.sha256("\n".join(sorted(tool_names)).encode("utf-8")).hexdigest()
    if fingerprint != UPSTREAM_TOOL_NAMES_SHA256:
        raise ValueError("Parity inventory differs from the pinned upstream tool set")
    for row in tools:
        if row["state"] not in {"implemented", "planned", "unverified"}:
            raise ValueError("Unknown tool implementation state")
        targets = row["hcl_targets"]
        if row["state"] == "implemented" and (
            not targets or not set(targets).issubset(REGISTERED_TOOLS)
        ):
            raise ValueError(f"Unregistered implementation claim: {row['upstream_tool']}")
        if row["state"] == "implemented" and row["live_required"]:
            raise ValueError("Live equivalence cannot be claimed before the live gate passes")
    for row in resources:
        if row["state"] not in {"implemented", "planned", "unverified"}:
            raise ValueError("Unknown resource implementation state")
        if row["state"] == "implemented" and row["hcl_uri"] not in REGISTERED_RESOURCES:
            raise ValueError(f"Unregistered resource claim: {row['upstream_uri']}")
    goals = inventory.get("reproduction_targets", [])
    if not isinstance(goals, list) or len(goals) != len(REPRODUCTION_TARGET_IDS):
        raise ValueError("The complete reproduction goal set is required")
    if any(not isinstance(goal, dict) or not isinstance(goal.get("id"), str) for goal in goals):
        raise ValueError("Invalid reproduction goal structure")
    if {goal["id"] for goal in goals} != REPRODUCTION_TARGET_IDS:
        raise ValueError("The reproduction goal set differs from the accepted scope")
    graph = {}
    for goal in goals:
        dependencies = goal.get("depends_on")
        acceptance = goal.get("acceptance")
        if goal.get("state") not in {"planned", "partial", "blocked"}:
            raise ValueError("Reproduction goals cannot claim unsupported completion")
        if (
            not isinstance(dependencies, list)
            or any(not isinstance(d, str) for d in dependencies)
            or not set(dependencies).issubset(REPRODUCTION_TARGET_IDS)
        ):
            raise ValueError("Unknown reproduction goal dependency")
        if (
            not isinstance(acceptance, list)
            or not acceptance
            or any(not isinstance(item, str) or not item.strip() for item in acceptance)
        ):
            raise ValueError("Each reproduction goal needs explicit acceptance criteria")
        graph[goal["id"]] = dependencies
    visited, active = set(), set()

    def visit(identifier):
        if identifier in active:
            raise ValueError("Reproduction goal dependencies contain a cycle")
        if identifier in visited:
            return
        active.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        active.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)


def parity_report() -> dict[str, Any]:
    """Return the real mapping and registered surface; planned names are data."""
    inventory = json.loads(
        files("mcp_hcl").joinpath("data/upstream_parity.json").read_text(encoding="utf-8")
    )
    validate_inventory(inventory)
    counts = {
        state: sum(row["state"] == state for row in inventory["tools"])
        for state in ("implemented", "planned", "unverified")
    }
    return {
        "status": "verified",
        "operation_id": uuid4().hex,
        "target_project": None,
        "verified_scope": "pinned_upstream_inventory_only",
        "evidence": [
            {
                "source": "packaged data/upstream_parity.json",
                "revision": UPSTREAM_REVISION,
                "tool_names_sha256": UPSTREAM_TOOL_NAMES_SHA256,
            }
        ],
        **inventory,
        "tool_state_counts": counts,
        "registered_tools": sorted(REGISTERED_TOOLS),
        "registered_resources": sorted(REGISTERED_RESOURCES),
        "full_live_gate_passed": False,
        "completion": "incomplete",
    }
