"""Copy-only project editing with reciprocal links and bound-plan synchronization."""

import copy
import json
import math
import re
from pathlib import Path

from mcp_hcl.generation import generate_configs
from mcp_hcl.project import _FIELD, _PORT, ProjectError
from mcp_hcl.project_build import note_blocks, render_notes, safe_filename


def edit_project(store, catalog, project_path, stage_name, action, **parameters):
    doc = store._open(project_path)
    metadata = copy.deepcopy(doc.metadata)
    blocks = {name: list(doc.lines[s.start : s.end]) for name, s in doc.sections.items()}
    suffix = list(doc.lines[doc.vbox_end :])
    files = {}
    device = parameters.get("device")
    if action in {"rename", "move", "delete"} and device not in blocks:
        raise ProjectError("Unknown device")
    if action == "rename":
        new = parameters["new_name"]
        safe_filename(new)
        if any(n.casefold() == new.casefold() for n in blocks):
            raise ProjectError("Device name already exists")
        section = doc.sections[device]
        blocks[device][0] = f"    [[{section.model} {new}]]{doc.newline}"
        for name, block in blocks.items():
            for i, line in enumerate(block):
                match = _FIELD.match(line.rstrip("\r\n"))
                if (
                    match
                    and _PORT.fullmatch(match[1].strip())
                    and match[2].startswith(device + " ")
                ):
                    block[i] = (
                        f"        {match[1].strip()} = {new} {match[2][len(device) + 1 :]}{doc.newline}"
                    )
        for row in metadata["deviceInfoList"]:
            if row["resourceName"] == device:
                old = doc.directory / "DeviceConfig" / (device + ".cfg")
                if old.is_file() and not old.is_symlink():
                    files[f"DeviceConfig/{new}.cfg"] = old.read_bytes()
                row.update(resourceName=new, configPath=f"DeviceConfig\\{new}.cfg")
    elif action == "move":
        for axis in ("x", "y"):
            value = parameters[axis]
            if not math.isfinite(value) or abs(value) > 10000:
                raise ProjectError("Coordinate exceeds supported range")
            for i, line in enumerate(blocks[device]):
                if re.match(rf"^        {axis} = ", line):
                    blocks[device][i] = f"        {axis} = {value}{doc.newline}"
                    break
            else:
                blocks[device].append(f"        {axis} = {value}{doc.newline}")
    elif action == "delete":
        if len(blocks) == 1:
            raise ProjectError("Cannot remove the final source device")
        del blocks[device]
        for name, block in blocks.items():
            blocks[name] = [
                line
                for line in block
                if not (
                    (m := _FIELD.match(line.rstrip("\r\n")))
                    and _PORT.fullmatch(m[1].strip())
                    and m[2].startswith(device + " ")
                )
            ]
        metadata["deviceInfoList"] = [
            row for row in metadata["deviceInfoList"] if row["resourceName"] != device
        ]
    elif action == "unlink":
        a, b = parameters["a"], parameters["b"]
        pa, pb = parameters["a_port"], parameters["b_port"]
        if (
            a not in blocks
            or b not in blocks
            or doc.sections[a].fields.get(pa) != f"{b} {pb}"
            or doc.sections[b].fields.get(pb) != f"{a} {pa}"
        ):
            raise ProjectError("Requested reciprocal link does not exist")
        for name, port in ((a, pa), (b, pb)):
            blocks[name] = [
                line
                for line in blocks[name]
                if not ((m := _FIELD.match(line.rstrip("\r\n"))) and m[1].strip() == port)
            ]
    elif action == "note":
        # New note is appended; existing source notes remain byte-preserved.
        text = parameters["text"]
        if len(text) > 4096 or any(not c.isprintable() and c not in "\r\n" for c in text):
            raise ProjectError("Invalid note text")
        for axis in ("x", "y"):
            if not math.isfinite(parameters[axis]) or abs(parameters[axis]) > 10000:
                raise ProjectError("Invalid note coordinate")
        newlines = render_notes(
            [], [{"text": text, "x": parameters["x"], "y": parameters["y"]}], doc.newline
        )
        ids = [int(m[1]) for line in suffix if (m := re.search(r"\[\[NOTE (\d+)\]\]", line))]
        newlines = [
            line.replace("[[NOTE 1]]", f"[[NOTE {max(ids, default=0) + 1}]]")
            for line in newlines
            if not line.startswith("[Non-vBox-DATA]")
        ]
        if not any(line.startswith("[Non-vBox-DATA]") for line in suffix):
            suffix.append("[Non-vBox-DATA]" + doc.newline)
        suffix.extend(newlines)
    elif action == "clear_notes":
        for start, end in reversed(note_blocks(suffix)):
            del suffix[start:end]
    else:
        raise ProjectError("Unsupported edit action")
    plan_path = doc.directory / "MCPArtifacts/plan.json"
    if plan_path.is_file():
        if plan_path.is_symlink():
            raise ProjectError("Linked plan artifacts are not accepted")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        bindings_path = doc.directory / "MCPArtifacts/bindings.json"
        binding_data = json.loads(bindings_path.read_text(encoding="utf-8"))
        bound = {row["name"]: row for row in binding_data["devices"]}
        identifier = bound.get(device, {}).get("plan_id")
        if action in {"rename", "move", "delete"} and not identifier:
            raise ProjectError("Plan binding missing")
        if action == "rename":
            next(row for row in plan["devices"] if row["id"] == identifier)["name"] = parameters[
                "new_name"
            ]
            bound[device]["name"] = parameters["new_name"]
            # Stable plan IDs retain association references. AC AP names follow
            # a renamed source AP only when the previous name matched it.
            for service in plan["services"]:
                if (
                    service["feature"] == "wireless"
                    and service["parameters"].get("ap_device") == identifier
                    and service["parameters"].get("ap_name") == device
                ):
                    service["parameters"]["ap_name"] = parameters["new_name"]
        elif action == "move":
            next(row for row in plan["devices"] if row["id"] == identifier).update(
                x=parameters["x"], y=parameters["y"]
            )
        elif action == "delete":
            plan["devices"] = [row for row in plan["devices"] if row["id"] != identifier]
            plan["links"] = [
                row
                for row in plan["links"]
                if identifier not in {row["a"]["device"], row["b"]["device"]}
            ]
            for key in (
                "addresses",
                "routes",
                "services",
                "host_settings",
                "subinterfaces",
                "ipv6_ra",
            ):
                plan[key] = [row for row in plan.get(key, []) if row.get("device") != identifier]
            plan["services"] = [
                s
                for s in plan["services"]
                if s["feature"] != "wireless" or s["parameters"].get("ap_device") != identifier
            ]
            plan["wireless_associations"] = [
                row
                for row in plan.get("wireless_associations", [])
                if identifier not in {row["device"], row["ap"]}
            ]
            binding_data["devices"] = [
                row for row in binding_data["devices"] if row["plan_id"] != identifier
            ]
        elif action == "unlink":

            def endpoint_matches(endpoint, name, scene):
                binding = bound[name]
                mapped = (
                    binding_data["port_map"].get(binding["model"], {}).get(endpoint["interface"])
                )
                return endpoint["device"] == binding["plan_id"] and mapped == scene

            plan["links"] = [
                link
                for link in plan["links"]
                if not (
                    (
                        endpoint_matches(link["a"], parameters["a"], parameters["a_port"])
                        and endpoint_matches(link["b"], parameters["b"], parameters["b_port"])
                    )
                    or (
                        endpoint_matches(link["b"], parameters["a"], parameters["a_port"])
                        and endpoint_matches(link["a"], parameters["b"], parameters["b_port"])
                    )
                )
            ]
        elif action == "note":
            plan["annotations"].append({k: parameters[k] for k in ("text", "x", "y")})
        elif action == "clear_notes":
            plan["annotations"] = []
        generated = generate_configs(plan, catalog)
        if generated["status"] != "verified":
            raise ProjectError("Edit leaves an invalid bound plan; source is unchanged")
        files["MCPArtifacts/plan.json"] = (
            json.dumps(generated["plan"], ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        files["MCPArtifacts/bindings.json"] = (
            json.dumps(binding_data, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        for pid, commands in generated["configs"].items():
            files[f"MCPArtifacts/commands/{pid}.txt"] = commands.encode("utf-8")
    prefix_end = min(s.start for s in doc.sections.values())
    lines = (
        list(doc.lines[:prefix_end])
        + [line for block in blocks.values() for line in block]
        + suffix
    )
    result = store._commit(doc, stage_name, lines, metadata, additional_files=files)
    result.update(
        operation="stage_" + action,
        live_canvas_verified=False,
        configuration_verified=False,
        full_live_gate_passed=False,
    )
    return result


def register_edit_tools(mcp, store, catalog):
    @mcp.tool()
    def hcl_stage_rename_device(
        project_path: str,
        stage_name: str,
        device: str,
        new_name: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """Rename one device and both ends of its saved links in a new project copy."""
        return edit_project(
            store, catalog, project_path, stage_name, "rename", device=device, new_name=new_name
        )

    @mcp.tool()
    def hcl_stage_move_device(
        project_path: str,
        stage_name: str,
        device: str,
        x: float,
        y: float,
        idempotency_key: str | None = None,
    ) -> dict:
        """Move one saved device in an isolated project copy; no live canvas mutation."""
        return edit_project(
            store, catalog, project_path, stage_name, "move", device=device, x=x, y=y
        )

    @mcp.tool()
    def hcl_stage_delete_device(
        project_path: str, stage_name: str, device: str, idempotency_key: str | None = None
    ) -> dict:
        """Remove one saved device and reciprocal links from a separate project copy."""
        return edit_project(store, catalog, project_path, stage_name, "delete", device=device)

    @mcp.tool()
    def hcl_stage_unlink(
        project_path: str,
        stage_name: str,
        a: str,
        a_port: str,
        b: str,
        b_port: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """Remove exactly one reciprocal saved link from an isolated copy."""
        return edit_project(
            store,
            catalog,
            project_path,
            stage_name,
            "unlink",
            a=a,
            a_port=a_port,
            b=b,
            b_port=b_port,
        )

    @mcp.tool()
    def hcl_stage_add_note(
        project_path: str,
        stage_name: str,
        text: str,
        x: float,
        y: float,
        idempotency_key: str | None = None,
    ) -> dict:
        """Append a bounded note in the observed .net representation to a copy."""
        return edit_project(store, catalog, project_path, stage_name, "note", text=text, x=x, y=y)

    @mcp.tool()
    def hcl_stage_clear_annotations(
        project_path: str, stage_name: str, idempotency_key: str | None = None
    ) -> dict:
        """Remove observed NOTE blocks only; preserve unknown drawing/Non-vBox data."""
        return edit_project(store, catalog, project_path, stage_name, "clear_notes")
