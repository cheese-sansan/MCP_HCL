"""Canonical ACL rule readback, including native formatter aliases."""

from __future__ import annotations

import re
from ipaddress import IPv4Address

from mcp_hcl.acl_values import ICMP_MESSAGES, PROTOCOLS, acl_header, address_pair, matches_acl

ICMP_NAMES = {name.casefold(): value for name, value in ICMP_MESSAGES.items()}
PORT_NAMES = {
    "ftp-data": 20,
    "ftp": 21,
    "ssh": 22,
    "telnet": 23,
    "smtp": 25,
    "domain": 53,
    "dns": 53,
    "www": 80,
    "http": 80,
    "https": 443,
    "bgp": 179,
}


def acl_view(value):
    header = acl_header(value)
    return (header["key"], header["name"]) if header else (value, None)


def configuration_acls(config):
    entries = []
    current = None
    for line in config.splitlines():
        value = line.strip()
        if not line.startswith(" "):
            current = None
            header = acl_header(value)
            if header is not None:
                current = {"header": header, "commands": []}
                entries.append(current)
        elif current is not None and value not in {"#", "return"}:
            current["commands"].append(value)
    return entries


def ensure_acl_target(config, parameters):
    """Refuse identity ambiguity and automatic rule order before a patch."""
    entries = configuration_acls(config)
    matches = [entry for entry in entries if matches_acl(entry["header"], parameters)]
    if len(matches) > 1:
        raise ValueError("ACL target has duplicate or ambiguous configuration headers")
    if parameters.name is not None and any(
        entry["header"]["name"] == parameters.name and entry["header"]["type"] != parameters.kind
        for entry in entries
    ):
        raise ValueError("Existing named ACL has another type")
    if any(entry["header"]["order"] != "config" for entry in matches):
        raise ValueError(
            "Existing ACL uses automatic order; requested sequence cannot be established"
        )
    return matches


def ipv4_binding(line):
    match = re.fullmatch(
        r"packet-filter (\d+|name \S+) (inbound|outbound)(?: extension)?(?: hardware-count)?",
        line.casefold(),
    )
    return match.groups() if match else None


def interface_bindings(config, interface, direction):
    selected = False
    result = []
    for line in config.splitlines():
        value = line.strip()
        if not line.startswith(" "):
            selected = value == "interface " + interface
        elif selected and value.startswith("packet-filter "):
            if value.split()[1] in {"ipv6", "mac", "user-defined"}:
                continue
            binding = ipv4_binding(value)
            if binding is None:
                raise ValueError("Existing IPv4 packet-filter syntax is unverified")
            if binding[1] == direction:
                result.append(binding[0])
    return result


def port_number(value):
    number = int(value) if value.isdigit() else PORT_NAMES[value]
    if not 0 <= number <= 65535:
        raise ValueError("Invalid ACL port")
    return number


def canonical_rule(line, advanced):
    tokens = line.lower().split()
    if len(tokens) < 3 or tokens[0] != "rule" or tokens[2] not in {"permit", "deny"}:
        raise ValueError("Unsupported ACL rule")
    result = {
        "id": int(tokens[1]),
        "action": tokens[2],
        "protocol": "ip",
        "source": (0, 0xFFFFFFFF),
        "destination": (0, 0xFFFFFFFF),
        "source_port": None,
        "destination_port": None,
        "icmp": None,
        "flags": {},
        "logging": False,
    }
    index = 3
    if advanced:
        result["protocol"] = (
            int(tokens[index]) if tokens[index].isdigit() else PROTOCOLS[tokens[index]]
        )
        index += 1
    used = set()
    while index < len(tokens):
        key = tokens[index]
        index += 1
        if key in used:
            raise ValueError("Duplicate ACL qualifier")
        used.add(key)
        if key in {"source", "destination"}:
            address = tokens[index]
            index += 1
            if address == "any":
                continue
            if address == "host":
                address = tokens[index]
                index += 1
                wildcard = 0
            else:
                wildcard = 0 if tokens[index] == "0" else int(IPv4Address(tokens[index]))
                index += 1
            result[key] = (int(IPv4Address(address)) & (~wildcard & 0xFFFFFFFF), wildcard)
        elif key in {"source-port", "destination-port"}:
            operator = tokens[index]
            number = port_number(tokens[index + 1])
            index += 2
            end = port_number(tokens[index]) if operator == "range" else None
            if operator == "range":
                index += 1
            if (
                operator not in {"eq", "neq", "gt", "lt", "range"}
                or end is not None
                and end < number
            ):
                raise ValueError("Invalid ACL operand")
            result[key.replace("-", "_")] = (operator, number, end)
        elif key == "icmp-type":
            value = tokens[index]
            index += 1
            if value.isdigit():
                code = (
                    int(tokens[index]) if index < len(tokens) and tokens[index].isdigit() else None
                )
                if code is not None:
                    index += 1
                result["icmp"] = (int(value), code)
            else:
                result["icmp"] = ICMP_NAMES[value]
        elif key in {"ack", "fin", "psh", "rst", "syn", "urg"}:
            value = int(tokens[index]) if index < len(tokens) and tokens[index] in {"0", "1"} else 1
            if index < len(tokens) and tokens[index] in {"0", "1"}:
                index += 1
            result["flags"][key] = value
        elif key == "established":
            result["flags"][key] = 1
        elif key == "logging":
            result["logging"] = True
        else:
            raise ValueError("Unverified ACL qualifier")
    return result


def expected_rule(rule):
    def port(simple, match):
        return (
            ("eq", simple, None)
            if simple is not None
            else (match.operator, match.port, match.end)
            if match
            else None
        )

    return {
        "id": rule.id,
        "action": rule.action,
        "protocol": rule.protocol if isinstance(rule.protocol, int) else PROTOCOLS[rule.protocol],
        "source": address_pair(rule.source),
        "destination": address_pair(rule.destination),
        "source_port": port(rule.source_port, rule.source_port_match),
        "destination_port": port(rule.destination_port, rule.destination_port_match),
        "icmp": ICMP_MESSAGES[rule.icmp]
        if isinstance(rule.icmp, str)
        else (rule.icmp.type, rule.icmp.code)
        if rule.icmp
        else None,
        "flags": {flag: 1 for flag in rule.tcp_flags},
        "logging": rule.log,
    }


def catches_all(rule):
    return (
        rule["protocol"] == "ip"
        and rule["source"][1] == 0xFFFFFFFF
        and rule["destination"][1] == 0xFFFFFFFF
        and not any(rule[key] for key in ("source_port", "destination_port", "icmp", "flags"))
    )


def effective_acl_parameters(parameters, baseline=None):
    if not parameters.implicit_deny:
        return parameters
    rules = {}
    if baseline is not None:
        selected = ensure_acl_target(baseline, parameters)
        for entry in selected:
            for line in entry["commands"]:
                if line.startswith("rule ") and not re.fullmatch(r"rule \d+ comment .+", line):
                    parsed = canonical_rule(line, parameters.kind == "advanced")
                    rules[parsed["id"]] = parsed
    rules.update({rule.id: expected_rule(rule) for rule in parameters.rules})
    if any(catches_all(rule) for rule in rules.values()):
        return parameters
    if max(rules) >= 65534:
        raise ValueError("Existing ACL leaves no final rule slot for implicit deny")
    from mcp_hcl.services import AclRule

    terminal = AclRule(id=65534, action="deny", remark="MCP_HCL implicit deny")
    return parameters.model_copy(update={"rules": [*parameters.rules, terminal]})


def verify_acl(config, parameters):
    lines = config.splitlines()
    views = {}
    context = None
    for line in lines:
        value = line.strip()
        if not line.startswith(" ") and value not in {"#", "return"}:
            normalized, _ = acl_view(value)
            context = normalized
            views.setdefault(context, [])
        elif context is not None and value not in {"#", "return"}:
            views[context].append(value)
    actual = {}
    remarks = {}
    try:
        selected = ensure_acl_target(config, parameters)
        if len(selected) != 1:
            return False
        body = selected[0]["commands"]
        header = selected[0]["header"]
        for line in body:
            comment = re.fullmatch(r"rule (\d+) comment (.+)", line)
            if comment:
                remarks[int(comment[1])] = comment[2]
                continue
            if line.startswith("rule "):
                value = canonical_rule(line, parameters.kind == "advanced")
                if value["id"] in actual:
                    return False
                actual[value["id"]] = value
        for rule in parameters.rules:
            if actual.get(rule.id) != expected_rule(rule) or remarks.get(rule.id) != rule.remark:
                return False
        if parameters.implicit_deny and not any(catches_all(rule) for rule in actual.values()):
            return False
        for binding in parameters.bindings:
            references = {parameters.reference}
            if header["number"] is not None:
                references.add(str(header["number"]))
            actual_bindings = interface_bindings(config, binding.interface, binding.direction)
            if len(actual_bindings) != 1 or actual_bindings[0] not in references:
                return False
    except (ValueError, KeyError, IndexError):
        return False
    return True


def without_acl_definitions(commands):
    """Keep other views/bindings; ACL effects are checked by verify_acl."""
    result = []
    inside = False
    for command in commands:
        if acl_header(command) is not None:
            inside = True
            continue
        if inside:
            if command == "quit":
                inside = False
            continue
        if ipv4_binding(command) is not None:
            continue
        result.append(command)
    return result


def replace_existing_acl_rules(commands, baseline, parameters=None):
    existing = {}
    for entry in configuration_acls(baseline):
        header = entry["header"]
        aliases = {header["key"]}
        if header["name"]:
            aliases.add(f"acl {header['type']} name {header['name']}")
        rules = {
            int(match[1])
            for line in entry["commands"]
            if (match := re.match(r"^rule (\d+)\b", line))
        }
        for alias in aliases:
            existing.setdefault(alias, set()).update(rules)
    result = []
    context = None
    selected = False
    for command in commands:
        header = acl_header(command)
        if header is not None:
            context = header["key"]
            selected = parameters is None or matches_acl(header, parameters)
        elif command in {"quit", "return", "system-view"} or command.startswith("interface "):
            context = None
            selected = False
        match = re.match(r"^rule (\d+) (?:permit|deny)\b", command)
        if selected and context and match and int(match[1]) in existing.get(context, set()):
            result.append("undo rule " + match[1])
        result.append(command)
    return result


def compile_acl_commands(commands, baseline, parameters):
    ensure_acl_target(baseline, parameters)
    effective = effective_acl_parameters(parameters, baseline)
    from mcp_hcl.generation import render_acl

    definition = render_acl(effective, rules=effective.rules)
    definition = definition[: definition.index("quit") + 1]
    replaced = []
    inside = False
    for command in commands:
        header = acl_header(command)
        if header is not None and matches_acl(header, parameters):
            replaced.extend(definition)
            inside = True
            continue
        if inside:
            if command == "quit":
                inside = False
            continue
        replaced.append(command)
    old = {
        (binding.interface, binding.direction): interface_bindings(
            baseline, binding.interface, binding.direction
        )
        for binding in parameters.bindings
    }
    result = []
    interface = None
    for command in replace_existing_acl_rules(replaced, baseline, effective):
        if command.startswith("interface "):
            interface = command[10:]
        elif command in {"quit", "return", "system-view"}:
            interface = None
        requested = ipv4_binding(command)
        if requested is not None:
            for reference in old.get((interface, requested[1]), []):
                result.append(f"undo packet-filter {reference} {requested[1]}")
        result.append(command)
    return result, effective


def prepare_acl_commands(commands, baseline, parameters):
    return compile_acl_commands(commands, baseline, parameters)[0]
