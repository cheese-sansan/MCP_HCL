"""Strict IPv6 and optional VPN-instance readback, without default guesses."""

from __future__ import annotations

import re
from ipaddress import ip_address, ip_network

from mcp_hcl.readback import INTERFACE, ReadbackError, interface_states

ADDRESS_FLAGS = {"TENTATIVE", "DUPLICATE", "DEPRECATED", "AUTOCFG", "EUI-64", "ANYCAST", "DHCP"}


def address_flags(text):
    flags = []
    lifetimes = None
    for token in re.findall(r"\[([^\]]+)\]", text):
        token = " ".join(token.split())
        if token in ADDRESS_FLAGS:
            if token in flags:
                raise ReadbackError("Repeated IPv6 address flag")
            flags.append(token)
            continue
        lifetime = re.fullmatch(
            r"valid lifetime (\d+s|infinite)/preferred lifetime (\d+s|infinite)", token
        )
        if lifetime is None or lifetimes is not None:
            raise ReadbackError("Unsupported IPv6 address annotation")
        lifetimes = {"valid": lifetime[1], "preferred": lifetime[2]}
    return {
        "flags": sorted(flags),
        "lifetimes": lifetimes,
        "usable": not {"TENTATIVE", "DUPLICATE"} & set(flags)
        and (lifetimes is None or lifetimes["valid"] != "0s"),
        "preferred": "DEPRECATED" not in flags
        and (lifetimes is None or lifetimes["preferred"] != "0s"),
    }


def ipv6_interfaces(text):
    states = interface_states(text)
    headers = list(
        re.finditer(
            r"^(" + INTERFACE + r")(?:\s+current state\s*:\s*([^\n]+))?\s*$", text, re.M | re.I
        )
    )
    result = {}
    for index, state in enumerate(states):
        block = text[
            headers[index].end() : headers[index + 1].start()
            if index + 1 < len(headers)
            else len(text)
        ]
        statuses = re.findall(r"^\s*IPv6 is (enabled|disabled)\b", block, re.M | re.I)
        if len(statuses) != 1:
            raise ReadbackError("Missing or conflicting IPv6 interface status")
        if statuses[0].lower() == "disabled":
            if re.search(r"Global unicast address|link-local address", block, re.I):
                raise ReadbackError("Disabled IPv6 interface reports addresses")
            result[state["interface"]] = {
                "ipv6_observation": "absent",
                "ipv6_addresses": [],
                "ipv6_link_local": None,
            }
            continue
        start = list(re.finditer(r"^\s*Global unicast address\(es\)\s*:\s*$", block, re.M | re.I))
        end = list(re.finditer(r"^\s*Joined group address\(es\)\s*:\s*$", block, re.M | re.I))
        if len(start) != 1 or len(end) != 1 or end[0].start() < start[0].end():
            raise ReadbackError("Incomplete IPv6 address section")
        link = re.search(
            r"IPv6 is enabled,\s*link-local address\s+is\s+([0-9a-f:]+)"
            r"((?:\s*\[[^\]]+\])*)\s*\Z",
            block[: start[0].start()].strip(),
            re.I,
        )
        if link is None:
            raise ReadbackError("Unsupported IPv6 link-local observation")
        link_address = ip_address(link[1])
        if link_address.version != 6 or not link_address.is_link_local:
            raise ReadbackError("Invalid reported IPv6 link-local address")
        link_local = {"address": str(link_address), **address_flags(link[2])}
        content = block[start[0].end() : end[0].start()].strip()
        addresses = []
        if content and content.lower() != "none":
            pattern = re.compile(
                r"([0-9a-f:]+),\s*subnet is\s+([0-9a-f:]+/\d+)"
                r"((?:\s*\[[^\]]+\])*)",
                re.I,
            )
            position = 0
            for match in pattern.finditer(content):
                if content[position : match.start()].strip():
                    raise ReadbackError("Unrecognized text in IPv6 address list")
                address = ip_address(match[1])
                subnet = ip_network(match[2], strict=True)
                if (
                    address.version != 6
                    or subnet.version != 6
                    or address not in subnet
                    or address.is_unspecified
                    or address.is_multicast
                    or address.is_link_local
                ):
                    raise ReadbackError("Invalid reported IPv6 global address/subnet")
                addresses.append(
                    {
                        "address": str(address),
                        "prefix_length": subnet.prefixlen,
                        **address_flags(match[3]),
                    }
                )
                position = match.end()
            if content[position:].strip() or not addresses:
                raise ReadbackError("Incomplete IPv6 address list")
        if len({row["address"] for row in addresses}) != len(addresses):
            raise ReadbackError("Repeated IPv6 address in one interface")
        result[state["interface"]] = {
            "ipv6_observation": "present" if addresses else "absent",
            "ipv6_addresses": addresses,
            "ipv6_link_local": link_local,
        }
    return result


def interface_domains(text, ports):
    """Read the VPN column when present; old layouts remain unknown.

    Only exact interface names and documented GE abbreviations are joined.
    A complete address/prefix match is required before attaching a domain.
    """
    headings = [
        line
        for line in text.splitlines()
        if re.match(r"^\s*Interface\s+Physical\s+Protocol\b", line, re.I)
    ]
    if len(headings) != 1:
        raise ReadbackError("Missing or ambiguous IP interface table header")
    if not re.search(r"IP address/Mask\s+VPN instance\b", headings[0], re.I):
        return {"status": "unavailable", "interfaces": {}}
    known = {row["interface"]: row for row in ports}
    aliases = {name: name for name in known}
    for name in known:
        if name.startswith("GigabitEthernet"):
            alias = "GE" + name[len("GigabitEthernet") :]
            if alias in aliases and aliases[alias] != name:
                raise ReadbackError("Ambiguous GE interface abbreviation")
            aliases[alias] = name
    lines = text.splitlines()
    first = lines.index(headings[0]) + 1
    records = {}
    seen = set()
    for line in lines[first:]:
        if not line.strip():
            continue
        match = re.fullmatch(
            r"\s*(\S+)\s+(?:\*?down|up)(?:\(s\))?\s+(?:down|up)(?:\(s\))?"
            r"\s+(\S+)\s+(\S+)(?:\s+.*)?",
            line,
            re.I,
        )
        if match is None or match[1] in seen:
            raise ReadbackError("Unsupported or duplicate IP interface table row")
        seen.add(match[1])
        name = aliases.get(match[1])
        if name is None:
            continue
        if name in records:
            raise ReadbackError("Multiple table rows resolve to the same interface")
        reported = match[2]
        before = known[name]["ipv4"]
        if reported.lower() == "unassigned":
            if known[name]["ipv4_observation"] != "absent":
                raise ReadbackError(
                    "IP interface table disagrees with the prior address observation"
                )
        else:
            from ipaddress import ip_interface

            address = ip_interface(reported)
            if (
                address.version != 4
                or before is None
                or before["address"] != str(address.ip)
                or before["prefix_length"] != address.network.prefixlen
            ):
                raise ReadbackError(
                    "IP interface table disagrees with the prior address/prefix observation"
                )
        domain = match[3]
        if not re.fullmatch(r"[^\s\x00-\x1f\x7f]{1,31}", domain):
            raise ReadbackError("Unsupported VPN instance name")
        records[name] = {
            "routing_domain_observation": "known",
            "routing_domain": {"kind": "public"}
            if domain == "--"
            else {"kind": "vpn", "name": domain},
        }
    if not seen:
        raise ReadbackError("IP interface table has no rows")
    return {"status": "observed", "interfaces": records}
