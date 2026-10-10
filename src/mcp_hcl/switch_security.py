"""Typed switch-security deltas with explicit IOS/Comware limitations."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, ValidationError, field_validator, model_validator

from mcp_hcl.console import ConsoleError
from mcp_hcl.contracts import validation_errors
from mcp_hcl.deployment import config_text
from mcp_hcl.gui_relay import rejected
from mcp_hcl.models import StrictModel
from mcp_hcl.nat_policy import (
    BudgetConsole,
    atomic_json,
    incomplete_operation,
    operation_json,
    unique_json,
)
from mcp_hcl.policy import scopes
from mcp_hcl.runtime_binding import unlinked
from mcp_hcl.services import InterfaceName, VlanId


class SwitchRequest(StrictModel):
    switch: str = Field(min_length=1, max_length=64)
    operation_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("switch")
    @classmethod
    def printable(cls, value):
        if not value.strip() or any(not c.isprintable() for c in value):
            raise ValueError("Switch selector must be printable")
        return value


class StpRequest(SwitchRequest):
    mode: Literal["pvst", "rapid-pvst"] = "rapid-pvst"
    root_primary_vlans: list[VlanId] = Field(default_factory=list, max_length=4094)
    priority: dict[str, Annotated[int, Field(ge=0, le=61440)]] = Field(default_factory=dict)
    portfast_ports: list[InterfaceName] = Field(default_factory=list, max_length=256)
    bpduguard_ports: list[InterfaceName] = Field(default_factory=list, max_length=256)

    @field_validator("priority")
    @classmethod
    def priorities(cls, value):
        if len(value) > 4094:
            raise ValueError("Too many VLAN priorities")
        for vlan, priority in value.items():
            if not re.fullmatch(r"[1-9][0-9]{0,3}", vlan) or not 1 <= int(vlan) <= 4094:
                raise ValueError("Priority object keys must be canonical VLAN IDs")
            if priority % 4096:
                raise ValueError("STP priority must be a multiple of 4096")
        return value

    @model_validator(mode="after")
    def no_duplicates(self):
        for values in (self.root_primary_vlans, self.portfast_ports, self.bpduguard_ports):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate STP target")
        return self


class PortSecurityRequest(SwitchRequest):
    port: InterfaceName
    max_mac: int = Field(default=1, ge=1, le=8192)
    violation: Literal["protect", "restrict", "shutdown"] = "shutdown"
    sticky: bool = True
    static_macs: list[str] = Field(default_factory=list, max_length=8192)

    @field_validator("static_macs")
    @classmethod
    def addresses(cls, value):
        result = []
        for mac in value:
            if not re.fullmatch(
                r"(?:[0-9a-fA-F]{4}[.-]){2}[0-9a-fA-F]{4}|(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}|[0-9a-fA-F]{12}",
                mac,
            ):
                raise ValueError("Static MAC needs six valid hexadecimal octets")
            compact = re.sub("[.:-]", "", mac).lower()
            if int(compact[:2], 16) & 1 or compact in {"000000000000", "ffffffffffff"}:
                raise ValueError("Secure MAC must be a nonzero unicast address")
            result.append("-".join(compact[i : i + 4] for i in (0, 4, 8)))
        if len(set(result)) != len(result):
            raise ValueError("Duplicate secure MAC address")
        return result

    @model_validator(mode="after")
    def capacity(self):
        if len(self.static_macs) > self.max_mac:
            raise ValueError("Static secure MACs exceed the requested maximum")
        return self


def set_scalar(views, context, prefix, line):
    views.setdefault(context, set())
    old = sorted(
        value for value in views[context] if value == prefix or value.startswith(prefix + " ")
    )
    if old == [line]:
        return []
    views[context].difference_update(old)
    views[context].add(line)
    return [line]


def stp_views(text):
    """Expand only known VLAN lists so compression cannot hide other VLAN changes."""
    result = scopes(text)
    expanded = set()
    for line in result.get((), set()):
        match = re.fullmatch(
            r"stp vlan ([0-9 to]+) (priority \d+|root primary|root secondary|enable)", line
        )
        if match is None:
            expanded.add(line)
            continue
        tokens = match[1].split()
        index = 0
        while index < len(tokens):
            first = int(tokens[index])
            index += 1
            last = first
            if index < len(tokens) and tokens[index] == "to":
                if index + 1 >= len(tokens):
                    raise ValueError("Incomplete STP VLAN range")
                last = int(tokens[index + 1])
                index += 2
            if not 1 <= first <= last <= 4094:
                raise ValueError("Invalid STP VLAN range")
            expanded.update(f"stp vlan {vlan} {match[2]}" for vlan in range(first, last + 1))
    result[()] = expanded
    return result


def stp_delta(before, parameters):
    if parameters.mode != "rapid-pvst":
        raise ValueError("Legacy IOS PVST algorithm has no accepted per-VLAN Comware mapping")
    views = stp_views(before)
    expected = copy.deepcopy(views)
    interfaces = {
        context[0][10:]: lines
        for context, lines in views.items()
        if len(context) == 1 and context[0].startswith("interface ")
    }
    wanted_ports = set(parameters.portfast_ports) | set(parameters.bpduguard_ports)
    if not wanted_ports <= interfaces.keys():
        raise ValueError("STP target interface is absent")
    for port in wanted_ports:
        lines = interfaces[port]
        if "port link-mode route" in lines or "stp loop-protection" in lines:
            raise ValueError("STP edge/guard target is routed or has conflicting loop protection")
    edges = {port for port, lines in interfaces.items() if "stp edged-port" in lines}
    if not set(parameters.bpduguard_ports) <= edges | set(parameters.portfast_ports):
        raise ValueError(
            "Global Comware BPDU protection requires each requested guard port to be explicitly edge"
        )
    if parameters.bpduguard_ports and "stp bpdu-protection" not in views.get((), set()):
        if (edges | set(parameters.portfast_ports)) - set(parameters.bpduguard_ports):
            raise ValueError("Global BPDU protection would newly affect an unrequested edge port")
    commands = set_scalar(expected, (), "stp mode", "stp mode pvst")
    # Global protocol enable is part of applying the requested mode.
    expected[()].discard("undo stp global enable")
    expected[()].add("stp global enable")
    if "stp global enable" not in views.get((), set()):
        commands.append("stp global enable")
    if parameters.bpduguard_ports and "stp bpdu-protection" not in views.get((), set()):
        expected[()].add("stp bpdu-protection")
        commands.append("stp bpdu-protection")
    for vlan in sorted(
        set(parameters.root_primary_vlans) | {int(value) for value in parameters.priority}
    ):
        prefix = f"stp vlan {vlan}"
        previous = [
            line
            for line in views.get((), set())
            if re.fullmatch(
                re.escape(prefix) + r" (?:priority \d+|root (?:primary|secondary))", line
            )
        ]
        expected[()].difference_update(previous)
        if str(vlan) in parameters.priority:
            line = prefix + " priority " + str(parameters.priority[str(vlan)])
            commands += ["undo " + prefix + " root" for value in previous if " root " in value]
        else:
            line = prefix + " root primary"
            commands += [
                "undo " + prefix + " priority" for value in previous if " priority " in value
            ]
        expected[()].add(line)
        if previous != [line]:
            commands.append(line)
    for port in sorted(set(parameters.portfast_ports)):
        context = ("interface " + port,)
        expected[context].add("stp edged-port")
        if "stp edged-port" not in views[context]:
            commands += [context[0], "stp edged-port", "quit"]
    return commands, expected


def port_security_delta(before, parameters):
    if parameters.violation != "shutdown":
        raise ValueError(
            "Native blockmac/trap behavior does not prove IOS protect/restrict semantics"
        )
    if parameters.max_mac > 1024:
        raise ValueError(
            "Requested maximum exceeds the installed command-reference range; model-specific proof is required"
        )
    views = scopes(before)
    expected = copy.deepcopy(views)
    context = ("interface " + parameters.port,)
    if context not in views:
        raise ValueError("Port-security target is absent")
    body = views[context]
    if (
        "port link-mode route" in body
        or "port link-type trunk" in body
        or "port link-type hybrid" in body
    ):
        raise ValueError(
            "Port security requires an existing layer-two access port; VLAN conversion is not inferred"
        )
    modes = [line for line in body if line.startswith("port-security port-mode ")]
    if modes and modes != ["port-security port-mode autolearn"]:
        raise ValueError("Changing existing port-security mode could remove unrelated secure MACs")
    counts = [line for line in body if line.startswith("port-security max-mac-count ")]
    if modes and counts != [f"port-security max-mac-count {parameters.max_mac}"]:
        raise ValueError(
            "Changing maximum in autoLearn can erase learned state; independent migration is required"
        )
    if "port-security enable" not in views.get((), set()):
        if any(
            line.startswith(("dot1x", "mac-authentication"))
            for lines in views.values()
            for line in lines
        ):
            raise ValueError(
                "Global port-security enable would reset existing authentication settings"
            )
    vlan_lines = [line for line in body if line.startswith("port access vlan ")]
    if len(vlan_lines) > 1:
        raise ValueError("Access VLAN is ambiguous")
    vlan = int(vlan_lines[0].split()[-1]) if vlan_lines else 1
    if not 1 <= vlan <= 4094:
        raise ValueError("Access VLAN is invalid")
    target = expected[context]
    commands = []
    if "port-security enable" not in views.get((), set()):
        expected[()].add("port-security enable")
        commands.append("port-security enable")
    interface_commands = []
    interface_commands += set_scalar(expected, context, "port link-type", "port link-type access")
    interface_commands += set_scalar(
        expected,
        context,
        "port-security max-mac-count",
        f"port-security max-mac-count {parameters.max_mac}",
    )
    interface_commands += set_scalar(
        expected, context, "port-security port-mode", "port-security port-mode autolearn"
    )
    interface_commands += set_scalar(
        expected,
        context,
        "port-security intrusion-mode",
        "port-security intrusion-mode disableport",
    )
    dynamic = "port-security mac-address dynamic"
    if parameters.sticky and dynamic in body:
        raise ValueError(
            "Switching dynamic secure MACs to sticky would affect unrequested learned state"
        )
    if not parameters.sticky and dynamic not in body:
        if any(line.startswith("port-security mac-address security sticky ") for line in body):
            raise ValueError("Disabling sticky would convert existing unrequested sticky entries")
        target.add(dynamic)
        interface_commands.append(dynamic)
    existing_macs = [
        line for line in body if line.startswith("port-security mac-address security ")
    ]
    new_macs = [
        mac
        for mac in parameters.static_macs
        if not any(mac in entry.split() for entry in existing_macs)
    ]
    if len(existing_macs) + len(new_macs) > parameters.max_mac:
        raise ValueError("Existing and requested static secure MACs exceed the new maximum")
    for mac in parameters.static_macs:
        line = f"port-security mac-address security {mac} vlan {vlan}"
        conflicting = [entry for entry in existing_macs if mac in entry.split() and entry != line]
        if conflicting:
            raise ValueError(
                "Requested static MAC conflicts with an existing secure MAC type or VLAN"
            )
        if line not in body:
            target.add(line)
            interface_commands.append(line)
    if interface_commands:
        commands += [context[0], *interface_commands, "quit"]
    return commands, expected


def configuration_matches(after, expected, feature, parameters):
    current = stp_views(after) if feature == "stp" else scopes(after)
    desired = copy.deepcopy(expected)
    if feature == "stp":
        # Documented defaults can be omitted; no unknown timer/topology defaults.
        for line in list(desired.get((), set())):
            if line == "stp global enable" and "undo stp global enable" not in current.get(
                (), set()
            ):
                if line not in current.get((), set()):
                    desired[()].discard(line)
            if (
                (match := re.fullmatch(r"stp vlan (\d+) priority 32768", line))
                and match[1] in parameters.priority
                and line not in current.get((), set())
            ):
                desired[()].discard(line)
    if feature == "port_security":
        for context in desired:
            if (
                context == ("interface " + parameters.port,)
                and "port link-type access" in desired[context]
                and "port link-type access" not in current.get(context, set())
            ):
                if not any(
                    line.startswith("port link-type ") for line in current.get(context, set())
                ):
                    desired[context].discard("port link-type access")
    return desired == current


class SwitchSecurityOperation:
    def __init__(self, policy):
        self.policy = policy

    def apply(self, feature, project_path, topology, parameters, dry_run=False):
        if not dry_run and not self.policy.writes_enabled:
            return rejected("writes_disabled", "Switch security requires the live write switch")
        model = StpRequest if feature == "stp" else PortSecurityRequest
        compiler = stp_delta if feature == "stp" else port_security_delta
        try:
            typed = model.model_validate(parameters)
        except ValidationError as exc:
            return {
                "status": "rejected",
                "errors": validation_errors(exc),
                "full_live_gate_passed": False,
            }
        # Capability limits depend only on the request. Reject the entire
        # intent before reading a stage, opening a pipe or saving a backup.
        unsupported = (feature == "stp" and typed.mode != "rapid-pvst") or (
            feature != "stp" and (typed.violation != "shutdown" or typed.max_mac > 1024)
        )
        if unsupported:
            return {
                "status": "unverified",
                "errors": [
                    {
                        "code": "switch_security_mapping_unverified",
                        "message": "The complete requested operation has no accepted Comware mapping",
                    }
                ],
                "configuration_verified": False,
                "upstream_behavior_equivalent": False,
                "full_live_gate_passed": False,
            }
        document, bindings = self.policy.deployment.bindings(project_path)
        matches = [
            (identifier, binding)
            for identifier, binding in bindings.items()
            if identifier == typed.switch or binding["name"] == typed.switch
        ]
        if len(matches) != 1:
            return rejected("invalid_switch_target", "Select one exact staged switch")
        identifier, binding = matches[0]
        if dry_run:
            if feature == "stp":
                fake = "".join(
                    "interface " + port + "\n#\n"
                    for port in sorted(set(typed.portfast_ports) | set(typed.bpduguard_ports))
                )
            else:
                fake = "interface " + typed.port + "\n#\n"
            try:
                commands, _ = compiler(fake, typed)
            except ValueError as exc:
                return {
                    "status": "unverified",
                    "errors": [{"code": "switch_security_mapping_unverified", "message": str(exc)}],
                    "full_live_gate_passed": False,
                }
            return {
                "status": "verified",
                "commands": ["system-view", *commands, "return"],
                "verified_scope": "offline_switch_security_intent_only",
                "runtime_preflight_required": True,
                "configuration_verified": False,
                "upstream_behavior_equivalent": False,
                "full_live_gate_passed": False,
            }
        operation = typed.operation_key or uuid4().hex
        directory = self.policy.store.output_root / ".switch-security-receipts" / operation
        unlinked(directory)
        request = {
            "feature": feature,
            "project": str(document.net_path),
            "device": identifier,
            "topology": topology,
            "parameters": typed.model_dump(mode="json"),
        }
        fingerprint = hashlib.sha256(
            json.dumps(request, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if directory.exists():
            path = directory / "request.json"
            if not path.is_file():
                return {
                    "status": "unverified",
                    "errors": [
                        {
                            "code": "operation_record_incomplete",
                            "message": "Prior state needs reconciliation; no replay",
                        }
                    ],
                    "full_live_gate_passed": False,
                }
            old = operation_json(path)
            if old is None:
                return incomplete_operation(operation, directory)
            if old.get("fingerprint") != fingerprint:
                return rejected(
                    "operation_key_conflict", "Switch security key belongs to another request"
                )
            path = directory / "result.json"
            recorded = operation_json(path)
            if recorded is None:
                return incomplete_operation(operation, directory)
            return {
                "status": "output_received",
                "operation_id": operation,
                "previous_result": recorded,
                "current_state_rechecked": False,
                "configuration_verified": False,
                "full_live_gate_passed": False,
            }
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "request.json", {"fingerprint": fingerprint, **request})
        result = {
            "status": "unverified",
            "operation_id": operation,
            "device": identifier,
            "receipt_directory": str(directory),
            "errors": [],
            "configuration_verified": False,
            "protocol_effect_verified": False,
            "persistence_verified": False,
            "protocol_persistence_verified": False,
            "rollback_verified": False,
            "protocol_rollback_verified": False,
            "upstream_behavior_equivalent": False,
            "full_live_gate_passed": False,
        }
        channel = None
        identity = None
        backup = None
        dirty = False
        archived = []
        deadline = time.monotonic() + typed.timeout_seconds
        try:
            raw, identity = self.policy.open(document, binding, topology)
            channel = BudgetConsole(raw, deadline)
            result["target_identity"] = identity

            def saved(record):
                nonlocal backup, dirty
                backup, dirty = record, True

            backup = self.policy.deployment._backup(
                channel, identifier, directory, operation, on_saved=saved
            )
            dirty = False
            before = Path(backup["local_file"]).read_text(encoding="utf-8")
            commands, expected = compiler(before, typed)
            result["backup"] = backup
            result["commands"] = ["system-view", *commands, "return"]
            dirty = True
            for command in result["commands"]:
                channel.exchange(command)
            after = config_text(channel.exchange("display current-configuration")["output"])
            if not configuration_matches(after, expected, feature, typed):
                raise ConsoleError(
                    "Switch security configuration or scope readback differs",
                    code="switch_security_unverified",
                )
            result["persistence"] = self.policy.deployment.startup.persist(
                channel, backup["startup"], after, f"flash:/mcp_{operation}_{identifier}_after.cfg"
            )
            native = self.policy.native_dependencies and getattr(channel, "native_channel", False)
            result.update(
                status="verified" if native else "output_received",
                configuration_verified=native,
                protocol_effect_verified=True,
                persistence_verified=native,
                protocol_persistence_verified=True,
                verified_scope="bound_native_switch_security_config_only"
                if native
                else "synthetic_switch_security_only",
            )
            result["warnings"] = [
                {
                    "code": "switch_security_behaviour_unverified",
                    "message": "Configuration readback does not prove root election, BPDU effects, learning, violation or IOS behaviour",
                }
            ]
        except (ConsoleError, OSError, ValueError) as exc:
            result["errors"] = [
                exc.as_error()
                if isinstance(exc, ConsoleError)
                else {"code": "switch_security_failed", "message": str(exc)}
            ]
            if dirty and backup is not None and identity is not None:
                try:
                    if channel is not None:
                        archived = list(getattr(channel, "history", []))
                        channel.close()
                        channel = None
                    raw, recovered = self.policy.open(
                        document, binding, topology, identity["vm_uuid"]
                    )
                    channel = BudgetConsole(raw, time.monotonic() + typed.timeout_seconds)
                    result["recovery_identity"] = recovered
                    result["rollback"] = self.policy.deployment._restore(channel, backup)
                    result["protocol_rollback_verified"] = True
                    result["rollback_verified"] = self.policy.native_dependencies and getattr(
                        channel, "native_channel", False
                    )
                except (ConsoleError, OSError, ValueError) as recovery:
                    result["rollback"] = {
                        "status": "unverified",
                        "error": recovery.as_error()
                        if isinstance(recovery, ConsoleError)
                        else str(recovery),
                        "running_snapshot": backup["local_file"],
                        "startup_snapshot": backup.get("startup"),
                    }
        finally:
            result["finished_utc"] = datetime.now(timezone.utc).isoformat()
            history = archived + (getattr(channel, "history", []) if channel is not None else [])
            error = None
            try:
                atomic_json(directory / "transcript.json", history)
            except (ConsoleError, OSError, ValueError) as exc:
                error = exc
                result["status"] = "unverified"
                result["errors"].append(
                    {"code": "switch_security_transcript_io_failed", "message": str(exc)}
                )
            if channel is not None:
                try:
                    channel.close()
                except (ConsoleError, OSError) as exc:
                    result["status"] = "unverified"
                    result["errors"].append(
                        {"code": "switch_security_close_failed", "message": str(exc)}
                    )
            try:
                atomic_json(directory / "result.json", result)
            except (ConsoleError, OSError, ValueError) as exc:
                error = exc
            if error is not None:
                raise ConsoleError(
                    "Switch security receipt incomplete; no replay",
                    code="switch_security_receipt_io_failed",
                    detail={"operation_id": operation, "device_mutation_possible": dirty},
                ) from error
        return result
