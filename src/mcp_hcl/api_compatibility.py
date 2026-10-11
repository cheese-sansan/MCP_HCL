"""Describe API differences using pinned declarations and current MCP discovery."""

import hashlib
import json
from copy import deepcopy
from importlib.resources import files

UPSTREAM_CONTRACTS_SHA256 = "f6eeabfb71a05f77bc6225059492154106cfdbfaf5edc0ad77331ef9eb4da92d"


def load_upstream_contracts(inventory: dict) -> dict:
    data = files("mcp_hcl").joinpath("data/upstream_contracts.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != UPSTREAM_CONTRACTS_SHA256:
        raise ValueError("API declarations do not match the verified snapshot bytes")
    snapshot = json.loads(data)
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("revision") != inventory["upstream"]["revision"]
    ):
        raise ValueError("API declarations have a different upstream revision")
    for kind in ("tool", "resource"):
        if (
            snapshot["sources"][kind + "_registry_sha256"]
            != inventory["upstream"][kind + "_registry_sha256"]
        ):
            raise ValueError("API declarations have different source identities")
    if set(snapshot["tools"]) != {r["upstream_tool"] for r in inventory["tools"]}:
        raise ValueError("API declarations must cover every upstream tool")
    if set(snapshot["resources"]) != {r["upstream_uri"] for r in inventory["resources"]}:
        raise ValueError("API declarations must cover every upstream resource")
    return snapshot


def _input_differences(parameters: list[dict], schema: dict) -> dict:
    upstream = {item["name"]: item for item in parameters}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    shared = sorted(set(upstream) & set(properties))
    differences = {
        "upstream_only_names": sorted(set(upstream) - set(properties)),
        "hcl_only_names": sorted(set(properties) - set(upstream)),
        "requiredness_changed": [
            name for name in shared if upstream[name]["required"] != (name in required)
        ],
        "defaults_changed": [
            name
            for name in shared
            if (
                ("default" in upstream[name]) != ("default" in properties[name])
                or (
                    "default" in upstream[name]
                    and (
                        upstream[name]["default"]["kind"] != "literal"
                        or type(upstream[name]["default"].get("value"))
                        is not type(properties[name].get("default"))
                        or upstream[name]["default"].get("value") != properties[name].get("default")
                    )
                )
            )
        ],
        "types_and_nested_semantics": "unverified; annotations are not complete upstream schemas",
    }
    differences["wrapped_input_candidates"] = [
        {
            "hcl_argument": name,
            "scope": "same_name_candidates_only; no executable translation or semantic equivalence",
            "differences": _input_differences(parameters, properties[name]),
        }
        for name in ("request", "parameters")
        if isinstance(properties.get(name), dict) and "properties" in properties[name]
    ]
    return differences


def api_compatibility_report(inventory: dict, tool_schemas: dict, resource_uris: set) -> dict:
    """Report discovery only; never dispatch a mapped or staged tool."""
    snapshot = load_upstream_contracts(inventory)
    tools = []
    for row in inventory["tools"]:
        declaration = snapshot["tools"][row["upstream_tool"]]
        targets = []
        for name in row["hcl_targets"]:
            target = {"name": name, "registered": name in tool_schemas}
            if name in tool_schemas:
                schema = tool_schemas[name]
                target["input_schema"] = deepcopy(schema)
                target["input_differences"] = _input_differences(declaration["parameters"], schema)
            targets.append(target)
        tools.append(
            {
                "upstream_tool": row["upstream_tool"],
                "upstream_declaration": deepcopy(declaration),
                "hcl_targets": targets,
                "availability": "mapped_entry_point"
                if any(t["registered"] for t in targets)
                else "not_implemented",
                "upstream_alias_registered": row["upstream_tool"] in tool_schemas,
                "automatic_translation_available": False,
                "output_equivalence": "unverified",
                "error_equivalence": "unverified",
                "behavior_equivalence": "unverified",
                "live_required": row["live_required"],
                "scope_note": row["note"],
                "staged_alternatives": [
                    {
                        "name": name,
                        "registered": name in tool_schemas,
                        "scope": "saved_project_only",
                    }
                    for name in row.get("staged_alternatives", [])
                ],
            }
        )
    resources = [
        {
            "upstream_uri": row["upstream_uri"],
            "hcl_uri": row["hcl_uri"],
            "registered": row["hcl_uri"] in resource_uris,
            "content_equivalence": "unverified; platform catalogs and capabilities differ",
            "automatic_translation_available": False,
        }
        for row in inventory["resources"]
    ]
    serialized = json.dumps(tool_schemas, sort_keys=True, separators=(",", ":"))
    return {
        "status": "partial",
        "verified_scope": "pinned_source_declarations_and_current_hcl_input_schemas_only",
        "upstream_revision": snapshot["revision"],
        "upstream_declarations_sha256": UPSTREAM_CONTRACTS_SHA256,
        "hcl_input_schemas_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "discovered_hcl_tool_count": len(tool_schemas),
        "discovered_hcl_resource_count": len(resource_uris),
        "tools": tools,
        "resources": resources,
        "automatic_translation_available": False,
        "full_live_gate_passed": False,
    }
