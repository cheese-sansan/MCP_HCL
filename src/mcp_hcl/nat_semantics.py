"""Compile bounded NAT deltas and compare their complete configuration scope."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from ipaddress import IPv4Address
from types import SimpleNamespace

from mcp_hcl.acl_semantics import (
    canonical_rule,
    catches_all,
    compile_acl_commands,
    ensure_acl_target,
)
from mcp_hcl.acl_values import address_pair
from mcp_hcl.generation import render_acl
from mcp_hcl.policy import scopes
from mcp_hcl.services import Acl, AclRule, NatAddressGroup


def acl_selector(parameters):
    return SimpleNamespace(
        number=parameters.acl_id, name=parameters.acl_name, kind=parameters.acl_kind
    )


def acl_entry(config, parameters):
    entries = ensure_acl_target(config, acl_selector(parameters))
    return entries[0] if entries else None


def reference_aliases(config, parameters):
    references = {parameters.acl_reference}
    entry = acl_entry(config, parameters)
    if entry is not None:
        header = entry["header"]
        if header["number"] is not None:
            references.add(str(header["number"]))
        if header["name"] is not None:
            references.add("name " + header["name"])
    return references


def outbound(line):
    match = re.fullmatch(r"nat outbound (\d+|name \S+)(?: address-group (\d+))?( no-pat)?", line)
    if match is None:
        return None
    reference, group, no_pat = match.groups()
    return {
        "reference": reference.casefold(),
        "group": int(group) if group is not None else None,
        "pat": no_pat is None,
    }


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if end < start:
            raise ValueError("Reversed NAT address member in readback")
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def group_ranges(commands):
    ranges = []
    for line in commands:
        if not line.startswith("address "):
            continue
        match = re.fullmatch(r"address (\S+)(?: (\S+))?", line)
        if match is None:
            raise ValueError("NAT address member options are not represented by this pool request")
        start = int(IPv4Address(match[1]))
        end = int(IPv4Address(match[2] or match[1]))
        ranges.append((start, end))
    return merge_ranges(ranges)


def acl_context(views, parameters):
    matches = []
    for context, commands in views.items():
        if len(context) != 1 or not context[0].startswith("acl "):
            continue
        if parameters.acl_name is not None:
            if "@acl-name " + parameters.acl_name in commands:
                matches.append(context)
        elif context == ("acl number " + str(parameters.acl_id),):
            matches.append(context)
    if len(matches) > 1:
        raise ValueError("Ambiguous ACL view in NAT configuration")
    return matches[0] if matches else None


def normalized(views, parameters, baseline_acl_number=None):
    """Native formatting aliases do not weaken preservation of other views."""
    result = {}
    aliases = {}
    target_name = parameters.acl_name if parameters.mode != "static" else None
    for context, lines in views.items():
        if len(context) == 1 and context[0].startswith("acl number "):
            names = [line[10:] for line in lines if line.startswith("@acl-name ")]
            if len(names) > 1:
                raise ValueError("Ambiguous ACL names in configuration")
            if names:
                aliases[context[0][11:]] = "name " + names[0]
    for context, commands in views.items():
        key = context
        lines = set(commands)
        if context and context[0].startswith("acl "):
            advanced = (
                int(context[0][11:]) >= 3000
                if context[0].startswith("acl number ")
                else context[0].startswith("acl advanced ")
            )
            if target_name is not None and "@acl-name " + target_name in lines:
                key = (f"acl {parameters.acl_kind} name {target_name}",)
                if baseline_acl_number is not None and context[0].startswith("acl number "):
                    lines.add("@acl-number " + context[0][11:])
            canonical = set()
            for line in lines:
                if line.startswith("rule ") and not re.fullmatch(r"rule \d+ comment .+", line):
                    try:
                        canonical.add(
                            "@acl-rule "
                            + json.dumps(canonical_rule(line, advanced), sort_keys=True)
                        )
                        continue
                    except (ValueError, KeyError, IndexError):
                        # Unrequested/unknown syntax remains an opaque protected line.
                        pass
                canonical.add(line)
            lines = canonical
        elif context and context[0].startswith("nat address-group "):
            known = {line for line in lines if line.startswith("address ")}
            try:
                ranges = group_ranges(known)
            except ValueError:
                ranges = None
            if ranges is not None:
                lines -= known
                lines.update(f"@nat-range {first} {last}" for first, last in ranges)
        if context and context[0].startswith("interface "):
            canonical = set()
            for line in lines:
                rule = outbound(line)
                if rule is None:
                    canonical.add(line)
                    continue
                reference = aliases.get(rule["reference"], rule["reference"])
                canonical.add(f"@nat-outbound {reference} group={rule['group']} pat={rule['pat']}")
            lines = canonical
        if key in result:
            raise ValueError("Configuration has duplicate logical views")
        result[key] = lines
    return result


def selected_outbound(views, parameters, references):
    context = ("interface " + parameters.outside_interface,)
    selected = []
    for line in views.get(context, set()):
        if not line.startswith("nat outbound "):
            continue
        rule = outbound(line)
        if rule is not None and rule["reference"] in references:
            selected.append((line, rule))
        elif rule is None and any(
            re.match(r"^nat outbound " + re.escape(ref) + r"(?:\s|$)", line, re.I)
            for ref in references
        ):
            raise ValueError("Existing selected NAT outbound options are unverified")
    if len(selected) > 1:
        raise ValueError("More than one selected outbound NAT binding")
    return selected


def inline_acl(config, parameters, *, origin_known=False):
    entry = acl_entry(config, parameters)
    if (
        entry is not None
        and parameters.acl_namespace == "ios"
        and parameters.acl_id is not None
        and not origin_known
    ):
        raise ValueError(
            "Existing native ACL has no recorded IOS identity; use an explicit Comware namespace"
        )
    existing = {}
    if entry is not None:
        for line in entry["commands"]:
            if line.startswith("rule ") and not re.fullmatch(r"rule \d+ comment .+", line):
                parsed = canonical_rule(line, parameters.acl_kind == "advanced")
                if parsed["id"] in existing:
                    raise ValueError("Duplicate ACL rule IDs in readback")
                existing[parsed["id"]] = parsed
    requested = []
    used = set(existing)
    for network in parameters.inside_networks:
        source = address_pair(network)
        matching = next(
            (
                rule["id"]
                for rule in existing.values()
                if rule["action"] == "permit"
                and rule["protocol"] == "ip"
                and rule["source"] == source
                and rule["destination"][1] == 0xFFFFFFFF
                and not any(
                    rule[k] for k in ("source_port", "destination_port", "icmp", "flags", "logging")
                )
            ),
            None,
        )
        if matching is not None:
            continue
        # Keep all existing sequence IDs; new permits precede the terminal deny.
        ordinary = [number for number in used if number != 65534]
        number = max(ordinary, default=-5) + 5
        if number >= 65534:
            raise ValueError("ACL has no free sequence before the terminal deny")
        used.add(number)
        requested.append(AclRule(id=number, action="permit", source=network))
    if not requested:
        if any(catches_all(rule) for rule in existing.values()):
            return [], None
        if 65534 in used:
            raise ValueError("ACL has no terminal deny slot")
        requested = [AclRule(id=65534, action="deny", remark="MCP_HCL implicit deny")]
    typed = Acl(
        number=parameters.acl_id,
        name=parameters.acl_name,
        acl_type=parameters.acl_kind,
        rules=requested,
        implicit_deny=True,
    )
    commands, effective = compile_acl_commands(render_acl(typed), config, typed)
    return commands, effective


def pool_assignment(views, parameters, pool_record):
    ids = {
        int(context[0][18:])
        for context in views
        if len(context) == 1 and re.fullmatch(r"nat address-group \d+", context[0])
    }
    if pool_record is not None:
        identifier = pool_record["address_group"]
        if (
            parameters.pool_address_group is not None
            and parameters.pool_address_group != identifier
        ):
            raise ValueError("A named pool cannot silently change its native group identity")
    elif parameters.pool_address_group is not None:
        identifier = parameters.pool_address_group
    else:
        identifier = next((number for number in range(65536) if number not in ids), None)
        if identifier is None:
            raise ValueError("No NAT address-group identity is available")
    context = (f"nat address-group {identifier}",)
    ranges = group_ranges(views.get(context, set()))
    desired = [(int(IPv4Address(parameters.pool_start)), int(IPv4Address(parameters.pool_end)))]
    if pool_record is not None and context in views and parameters.pool_address_group is None:
        recorded = [(int(IPv4Address(pool_record["start"])), int(IPv4Address(pool_record["end"])))]
        if ranges != recorded:
            raise ValueError(
                "Named pool metadata no longer matches its native range; pin the reviewed group explicitly"
            )
    if context in views and pool_record is None and ranges != desired:
        raise ValueError("Explicit native pool conflicts with an existing unrelated range")
    return identifier


@dataclass
class NatDelta:
    commands: list[str]
    expected: dict
    parameters: object
    pool_id: int | None = None
    baseline_acl_number: int | None = None

    def verified(self, config):
        return normalized(scopes(config), self.parameters, self.baseline_acl_number) == normalized(
            self.expected, self.parameters, self.baseline_acl_number
        )


def apply_delta(config, parameters, group_id=None):
    before = scopes(config)
    expected = copy.deepcopy(before)
    references = reference_aliases(config, parameters) if parameters.mode != "static" else set()
    old_rules = (
        selected_outbound(before, parameters, references) if parameters.mode != "static" else []
    )
    commands = []
    if parameters.mode == "static":
        for mapping in parameters.static_mappings:
            wanted = f"nat static outbound {mapping.inside_local} {mapping.inside_global}"
            for line in before.get((), set()):
                match = re.match(r"^nat static outbound (\S+) (\S+)(.*)$", line)
                if (
                    match
                    and (match[1] == mapping.inside_local or match[2] == mapping.inside_global)
                    and line != wanted
                ):
                    raise ValueError(
                        "Requested static NAT address conflicts with an existing mapping or options"
                    )
            expected[()].add(wanted)
            if wanted not in before.get((), set()):
                commands.append(wanted)
        context = ("interface " + parameters.outside_interface,)
        expected[context].add("nat static enable")
        if "nat static enable" not in before.get(context, set()):
            commands += [context[0], "nat static enable", "quit"]
    else:
        context = ("interface " + parameters.outside_interface,)
        if parameters.uses_pool:
            if group_id is None:
                raise ValueError("A resolved pool ID is required")
            group_context = (f"nat address-group {group_id}",)
            for candidate, lines in before.items():
                for line in lines:
                    rule = outbound(line)
                    if (
                        rule
                        and rule["group"] == group_id
                        and rule["pat"] != (parameters.mode == "pat")
                    ):
                        if not (candidate == context and rule["reference"] in references):
                            raise ValueError(
                                "Address group is already used in the opposite PAT/NO-PAT mode"
                            )
            old = before.get(group_context, set())
            ranges = group_ranges(old)
            old_members = sorted(line for line in old if line.startswith("address "))
            if old_members and ranges != [
                (int(IPv4Address(parameters.pool_start)), int(IPv4Address(parameters.pool_end)))
            ]:
                commands += [group_context[0], *["undo " + line for line in old_members], "quit"]
            group = NatAddressGroup(
                id=group_id, start=parameters.pool_start, end=parameters.pool_end
            )
            # Native display may merge or split address members; compare intervals.
            addresses = {
                f"address {IPv4Address(start)} {IPv4Address(min(start + 255, int(IPv4Address(group.end))))}"
                for start in range(
                    int(IPv4Address(group.start)), int(IPv4Address(group.end)) + 1, 256
                )
            }
            expected[group_context] = {
                line for line in old if not line.startswith("address ")
            } | addresses
            if group_context not in before or ranges != [
                (int(IPv4Address(group.start)), int(IPv4Address(group.end)))
            ]:
                commands += [
                    group_context[0],
                    *sorted(addresses, key=lambda line: int(IPv4Address(line.split()[1]))),
                    "quit",
                ]
        equivalent = (
            bool(old_rules)
            and old_rules[0][1]["group"] == group_id
            and old_rules[0][1]["pat"] == (parameters.mode == "pat")
        )
        if not equivalent:
            for line, _ in old_rules:
                expected[context].discard(line)
            if old_rules:
                commands += [
                    context[0],
                    *["undo nat outbound " + rule["reference"] for _, rule in old_rules],
                    "quit",
                ]
            reference = parameters.acl_reference
            target_line = "nat outbound " + reference
            if group_id is not None:
                target_line += " address-group " + str(group_id)
            if parameters.mode == "dynamic":
                target_line += " no-pat"
            commands += [context[0], target_line, "quit"]
            expected[context].add(target_line)
    entry = acl_entry(config, parameters) if parameters.mode != "static" else None
    number = entry["header"]["number"] if entry is not None else None
    return NatDelta(commands, expected, parameters, group_id, number)


def reference_in_line(line, references):
    for reference in references:
        if re.search(
            r"\b(?:acl|packet-filter|nat (?:inbound|outbound)) (?:ipv4 )?"
            + re.escape(reference)
            + r"(?:\s|$)",
            line,
            re.I,
        ):
            return True
    return False


def remove_delta(config, parameters, group_id=None):
    before = scopes(config)
    expected = copy.deepcopy(before)
    context = ("interface " + parameters.outside_interface,)
    references = reference_aliases(config, parameters) if parameters.mode != "static" else set()
    selected = (
        selected_outbound(before, parameters, references) if parameters.mode != "static" else []
    )
    commands = []
    if parameters.mode == "static":
        wanted = {
            f"nat static outbound {m.inside_local} {m.inside_global}"
            for m in parameters.static_mappings
        }
        for mapping in parameters.static_mappings:
            for line in before.get((), set()):
                match = re.match(r"^nat static outbound (\S+) (\S+)(.*)$", line)
                if (
                    match
                    and (match[1] == mapping.inside_local or match[2] == mapping.inside_global)
                    and line not in wanted
                ):
                    raise ValueError(
                        "Static removal identity conflicts with another mapping or unverified options"
                    )
        for line in sorted(wanted & before.get((), set())):
            commands.append("undo " + line)
            expected[()].discard(line)
        if parameters.disable_static_interface and "nat static enable" in before.get(
            context, set()
        ):
            if any(
                line.startswith(
                    ("nat static outbound ", "nat static inbound ", "nat static net-to-net ")
                )
                for line in expected.get((), set())
            ):
                raise ValueError(
                    "Static enable also serves remaining global mappings; preserve it explicitly"
                )
            commands += [context[0], "undo nat static enable", "quit"]
            expected[context].discard("nat static enable")
    else:
        expected_pat = parameters.mode == "pat"
        if selected:
            line, rule = selected[0]
            if rule["pat"] != expected_pat:
                raise ValueError("Removal mode differs from the actual NAT binding")
            if group_id is not None and rule["group"] != group_id:
                raise ValueError("Removal pool differs from the actual NAT binding")
            if group_id is None and rule["group"] is not None:
                raise ValueError("Pool identity must be explicit or recorded for removal")
            commands += [context[0], "undo nat outbound " + rule["reference"], "quit"]
            expected[context].discard(line)
        if group_id is not None and parameters.remove_pool:
            group_context = (f"nat address-group {group_id}",)
            for lines in expected.values():
                if any(
                    re.search(r"\baddress-group " + str(group_id) + r"(?:\s|$)", line)
                    for line in lines
                ):
                    raise ValueError(
                        "Requested NAT pool remains referenced by another configuration"
                    )
            if group_context in expected:
                commands.append("undo " + group_context[0])
                expected.pop(group_context)
        entry = acl_entry(config, parameters)
        if parameters.remove_acl and entry is not None:
            acl_key = (entry["header"]["key"],)
            for candidate, lines in expected.items():
                if candidate != acl_key and any(
                    reference_in_line(line, references) for line in lines
                ):
                    raise ValueError("Requested ACL remains referenced by another configuration")
            commands.append("undo acl " + entry["header"]["type"] + " " + parameters.acl_reference)
            expected.pop(acl_key)
    entry = acl_entry(config, parameters) if parameters.mode != "static" else None
    number = entry["header"]["number"] if entry is not None else None
    return NatDelta(commands, expected, parameters, group_id, number)
