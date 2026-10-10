"""Named NetFlow intents over scoped Comware NetStream configuration."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal
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
from mcp_hcl.services import Binding, InterfaceName


class NetstreamRequest(StrictModel):
    device: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    destination_ip: str = ""
    udp_port: int = Field(default=2055, ge=1, le=65535)
    version: Literal[5, 9] = 9
    source_port: str = ""
    monitors: list[str] = Field(default_factory=list, max_length=256)
    remove: bool = False
    interfaces: list[Binding] = Field(default_factory=list, max_length=256)
    operation_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("device", "name")
    @classmethod
    def printable(cls, value):
        if not value.strip() or any(not char.isprintable() for char in value):
            raise ValueError("Selectors/names must be nonempty printable strings")
        return value

    @field_validator("destination_ip")
    @classmethod
    def ipv4(cls, value):
        return str(IPv4Address(value)) if value else value

    @field_validator("source_port")
    @classmethod
    def interface(cls, value):
        if value and not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*\d+(?:/\d+)*(?:\.\d+)?", value):
            raise ValueError("Use one exact native source interface")
        return value

    @field_validator("monitors")
    @classmethod
    def monitor_names(cls, values):
        if any(
            not value.strip() or any(not char.isprintable() for char in value) for value in values
        ):
            raise ValueError("Monitor names must be printable and nonempty")
        return values

    @model_validator(mode="after")
    def unique_bindings(self):
        keys = [(item.interface, item.direction) for item in self.interfaces]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate collection interface/direction")
        if self.remove and self.interfaces:
            raise ValueError("Exporter removal does not remove shared collection interfaces")
        return self


def source_interface(value):
    match = re.fullmatch(r"([A-Za-z][A-Za-z-]*)(\d+(?:/\d+)*(?:\.\d+)?)", value)
    if match is None:
        raise ValueError("Unsupported native source-interface spelling")
    return match[1].lower() + " " + match[2]


def stream_snapshot(text):
    if re.search(r"^\s*ip netstream aggregation\b", text, re.M):
        raise ValueError("Aggregation views/inheritance need a separate supported scope mapping")
    views = scopes(text)
    global_lines = views.get((), set())
    hosts = {}
    version, options, source = 9, (), ""
    version_seen = source_seen = False
    for line in global_lines:
        if line.startswith("ip netstream export host "):
            match = re.fullmatch(
                r"ip netstream export host (\S+) (\d+)(?: vpn-instance (\S+))?", line
            )
            if match is None:
                raise ValueError("Unsupported NetStream destination shape")
            address = str(IPv4Address(match[1]))
            port = int(match[2])
            if not 0 <= port <= 65535:
                raise ValueError("Invalid NetStream UDP port")
            key = (address, match[3] or "")
            if key in hosts:
                raise ValueError("Duplicate NetStream destination identity")
            hosts[key] = port
        elif line.startswith("ip netstream export version "):
            match = re.fullmatch(
                r"ip netstream export version (5|9)(?: (origin-as|peer-as))?(?: (bgp-nexthop))?",
                line,
            )
            if match is None or version_seen or match[1] == "5" and match[3]:
                raise ValueError("Unsupported/conflicting NetStream version options")
            version_seen = True
            version = int(match[1])
            options = tuple(token for token in (match[2], match[3]) if token)
        elif line.startswith("ip netstream export source "):
            match = re.fullmatch(
                r"ip netstream export source interface ([A-Za-z][A-Za-z-]*)\s*(\d+(?:/\d+)*(?:\.\d+)?)",
                line,
            )
            if match is None or source_seen:
                raise ValueError("Unsupported/conflicting NetStream source interface")
            source_seen = True
            source = match[1].lower() + " " + match[2]
    return views, hosts, version, options, source


def normalized_views(text):
    views, _, _, _, _ = stream_snapshot(text)
    return normalized_scope_sets(views)


def normalized_scope_sets(views):
    result = copy.deepcopy(views)
    for line in list(result.get((), set())):
        if re.fullmatch(r"ip netstream export version 9(?: peer-as)?", line):
            result[()].discard(line)
        elif line.startswith("ip netstream export source interface "):
            match = re.fullmatch(
                r"ip netstream export source interface ([A-Za-z][A-Za-z-]*)\s*(\d+(?:/\d+)*(?:\.\d+)?)",
                line,
            )
            result[()].discard(line)
            result[()].add(
                "ip netstream export source interface " + match[1].lower() + " " + match[2]
            )
    return result


def netstream_delta(before, request, names):
    views, hosts, version, options, source = stream_snapshot(before)
    old = names.get(request.name)
    for item in names.values():
        if (
            not isinstance(item, dict)
            or not {"destination_ip", "udp_port", "version", "source_native"} <= item.keys()
            or hosts.get((item["destination_ip"], "")) != item["udp_port"]
            or version != item["version"]
            or source != item["source_native"]
        ):
            raise ValueError(
                "A recorded name no longer matches its native destination/global settings"
            )
    if old is not None and (
        hosts.get((old["destination_ip"], "")) != old["udp_port"]
        or version != old["version"]
        or source != old["source_native"]
    ):
        raise ValueError("Recorded exporter no longer matches current native settings")
    commands = []
    expected = copy.deepcopy(views)
    registry = copy.deepcopy(names)
    global_lines = expected.setdefault((), set())
    if request.remove:
        if old is None:
            raise ValueError("Removal requires a recorded name bound to this actual VM")
        address = old["destination_ip"]
        if any(
            name != request.name and item["destination_ip"] == address
            for name, item in names.items()
        ):
            raise ValueError("Another named intent shares this native destination")
        commands.append("undo ip netstream export host " + address)
        global_lines.discard(f"ip netstream export host {address} {old['udp_port']}")
        del registry[request.name]
        return commands, expected, registry
    destination = request.destination_ip or (old["destination_ip"] if old else "")
    if not destination:
        raise ValueError("A new inert named exporter has no accepted native object mapping")
    wanted_source = (
        source_interface(request.source_port)
        if request.source_port
        else (old["source_native"] if old else source)
    )
    if request.source_port and ("interface " + request.source_port,) not in views:
        raise ValueError("Requested native source interface was not observed")
    other_hosts = {
        key: port for key, port in hosts.items() if not old or key != (old["destination_ip"], "")
    }
    other_names = {name: item for name, item in names.items() if name != request.name}
    if any(item["destination_ip"] == destination for item in other_names.values()):
        raise ValueError("A different name already owns this destination")
    if (destination, "") in other_hosts:
        raise ValueError("Destination already exists without this name identity")
    if len(other_hosts) >= 4:
        raise ValueError("The documented per-view destination limit would be exceeded")
    if (other_hosts or other_names) and (request.version != version or wanted_source != source):
        raise ValueError("Global version/source changes would affect other destinations")
    if request.version == 5 and "bgp-nexthop" in options:
        raise ValueError("Version 5 cannot preserve the unrequested BGP next-hop option")
    if old and old["destination_ip"] != destination:
        commands.append("undo ip netstream export host " + old["destination_ip"])
        global_lines.discard(f"ip netstream export host {old['destination_ip']} {old['udp_port']}")
    if request.version != version:
        commands.append(
            "ip netstream export version "
            + str(request.version)
            + (" " + " ".join(options) if options else "")
        )
        global_lines.difference_update(
            line for line in list(global_lines) if line.startswith("ip netstream export version ")
        )
        global_lines.add(commands[-1])
    if wanted_source != source:
        command = "ip netstream export source interface " + wanted_source
        commands.append(command)
        global_lines.difference_update(
            line for line in list(global_lines) if line.startswith("ip netstream export source ")
        )
        global_lines.add(command)
    if hosts.get((destination, "")) != request.udp_port:
        command = f"ip netstream export host {destination} {request.udp_port}"
        commands.append(command)
        global_lines.difference_update(
            line
            for line in list(global_lines)
            if re.fullmatch(r"ip netstream export host " + re.escape(destination) + r" \d+", line)
        )
        global_lines.add(command)
    for binding in request.interfaces:
        context = ("interface " + binding.interface,)
        if context not in views:
            raise ValueError("Collection interface was not observed")
        command = "ip netstream " + binding.direction
        if command not in expected[context]:
            commands += ["interface " + binding.interface, command, "quit"]
            expected[context].add(command)
    registry[request.name] = {
        "destination_ip": destination,
        "udp_port": request.udp_port,
        "version": request.version,
        "source_native": wanted_source,
    }
    return commands, expected, registry


class NetstreamOperation:
    def __init__(self, policy):
        self.policy = policy

    def apply(self, project_path, topology, parameters, dry_run=False):
        if not dry_run and not self.policy.writes_enabled:
            return rejected(
                "writes_disabled", "NetStream mutations require the explicit live write switch"
            )
        try:
            request = NetstreamRequest.model_validate(parameters)
        except ValidationError as exc:
            return {
                "status": "rejected",
                "errors": validation_errors(exc),
                "full_live_gate_passed": False,
            }
        if request.monitors:
            return {
                "status": "unverified",
                "errors": [
                    {
                        "code": "named_monitor_mapping_unverified",
                        "message": "Named NetFlow monitors have no accepted NetStream mapping; no subset will be applied.",
                    }
                ],
                "full_live_gate_passed": False,
            }
        document, bindings = self.policy.deployment.bindings(project_path)
        selected = [
            (identifier, binding)
            for identifier, binding in bindings.items()
            if identifier == request.device or binding["name"] == request.device
        ]
        if len(selected) != 1:
            return rejected("unknown_or_ambiguous_device", "Select one exact staged device")
        identifier, binding = selected[0]
        if dry_run:
            return {
                "status": "output_received",
                "intent": request.model_dump(mode="json"),
                "verified_scope": "offline_netstream_intent_only",
                "runtime_preflight_required": True,
                "named_exporter_equivalent": False,
                "configuration_verified": False,
                "full_live_gate_passed": False,
            }
        operation = request.operation_key or uuid4().hex
        directory = self.policy.store.output_root / ".netstream-receipts" / operation
        unlinked(directory)
        payload = {
            "project": str(document.net_path),
            "device": identifier,
            "topology": topology,
            "parameters": request.model_dump(mode="json"),
        }
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if directory.exists():
            previous = directory / "request.json"
            old_request = operation_json(previous)
            if old_request is None:
                return incomplete_operation(operation, directory)
            if old_request.get("fingerprint") != fingerprint:
                return rejected(
                    "operation_key_conflict_or_incomplete",
                    "Prior request requires reconciliation; no replay",
                )
            result_file = directory / "result.json"
            recorded = operation_json(result_file)
            if recorded is None:
                return incomplete_operation(operation, directory)
            return {
                "status": "output_received",
                "operation_id": operation,
                "previous_result": recorded,
                "replayed": False,
                "configuration_verified": False,
                "full_live_gate_passed": False,
            }
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "request.json", {"fingerprint": fingerprint, **payload})
        result = {
            "status": "unverified",
            "operation": "apply_netstream",
            "operation_id": operation,
            "target_project": str(document.net_path),
            "device": identifier,
            "errors": [],
            "configuration_verified": False,
            "persistence_verified": False,
            "rollback_verified": False,
            "named_exporter_equivalent": False,
            "named_monitors_equivalent": False,
            "collector_delivery_verified": False,
            "upstream_behavior_equivalent": False,
            "full_live_gate_passed": False,
        }
        channel = None
        identity = backup = None
        dirty = False
        histories = []
        registry_path = registry = None
        registry_existed = False
        registry_write_started = False
        deadline = time.monotonic() + request.timeout_seconds
        try:
            raw, identity = self.policy.open(document, binding, topology)
            channel = BudgetConsole(raw, deadline)
            result["target_identity"] = identity
            namespace = (
                ".netstream-names"
                if self.policy.native_dependencies and getattr(channel, "native_channel", False)
                else ".netstream-protocol-names"
            )
            registry_path = (
                self.policy.store.output_root
                / namespace
                / identifier
                / (identity["vm_uuid"] + ".json")
            )
            unlinked(registry_path)
            registry_existed = registry_path.is_file()
            registry = (
                unique_json(registry_path)
                if registry_path.is_file()
                else {
                    "schema_version": 1,
                    "project": str(document.net_path),
                    "vm_uuid": identity["vm_uuid"],
                    "names": {},
                }
            )
            if (
                not isinstance(registry, dict)
                or registry.get("schema_version") != 1
                or registry.get("project") != str(document.net_path)
                or registry.get("vm_uuid") != identity["vm_uuid"]
                or not isinstance(registry.get("names"), dict)
            ):
                raise ValueError("Exporter name registry identity is stale or invalid")
            if (
                registry_path.is_file()
                and namespace == ".netstream-names"
                and registry.get("native_configuration_origin") is not True
            ):
                raise ValueError("Unverified name metadata cannot authorize native object reuse")

            def saved(record):
                nonlocal backup, dirty
                backup, dirty = record, True

            backup = self.policy.deployment._backup(
                channel, identifier, directory, operation, on_saved=saved
            )
            dirty = False
            before = Path(backup["local_file"]).read_text(encoding="utf-8")
            commands, expected, names = netstream_delta(before, request, registry["names"])
            result.update(commands=["system-view", *commands, "return"], backup=backup)
            dirty = True
            for command in result["commands"]:
                channel.exchange(command)
            after = config_text(channel.exchange("display current-configuration")["output"])
            if normalized_views(after) != normalized_scope_sets(expected):
                raise ConsoleError(
                    "NetStream scope/configuration differs after application",
                    code="netstream_readback_unverified",
                )
            result["persistence"] = self.policy.deployment.startup.persist(
                channel, backup["startup"], after, f"flash:/mcp_{operation}_{identifier}_after.cfg"
            )
            registry_write_started = True
            atomic_json(
                registry_path,
                {
                    **registry,
                    "names": names,
                    "native_configuration_origin": namespace == ".netstream-names",
                },
            )
            native = self.policy.native_dependencies and getattr(channel, "native_channel", False)
            result.update(
                status="verified" if native else "output_received",
                configuration_verified=native,
                protocol_effect_verified=True,
                persistence_verified=native,
                verified_scope="bound_native_netstream_configuration_only"
                if native
                else "synthetic_netstream_only",
                exporter_name_registry=str(registry_path),
            )
            result["warnings"] = [
                "The name is local identity metadata, not a native named exporter; no monitor-object or flow delivery proof."
            ]
        except (ConsoleError, OSError, ValueError, KeyError, TypeError) as exc:
            result["errors"].append(
                exc.as_error()
                if isinstance(exc, ConsoleError)
                else {"code": "netstream_unverified", "message": str(exc)}
            )
            if dirty and backup is not None and identity is not None:
                try:
                    if channel is not None:
                        histories = list(getattr(channel, "history", []))
                        channel.close()
                    raw, restored = self.policy.open(
                        document, binding, topology, identity["vm_uuid"]
                    )
                    channel = BudgetConsole(raw, time.monotonic() + request.timeout_seconds)
                    result["recovery_identity"] = restored
                    result["rollback"] = self.policy.deployment._restore(channel, backup)
                    result["rollback_verified"] = self.policy.native_dependencies and getattr(
                        channel, "native_channel", False
                    )
                    if registry_write_started and registry_path is not None:
                        if registry_existed:
                            atomic_json(registry_path, registry)
                        else:
                            # Only this call's newly created identity file is
                            # removed; no directory/profile/assets are deleted.
                            unlinked(registry_path)
                            registry_path.unlink(missing_ok=True)
                        result["name_registry_restored"] = True
                except (ConsoleError, OSError, ValueError) as recovery:
                    result["rollback"] = {
                        "status": "unverified",
                        "running_snapshot": backup["local_file"],
                        "error": recovery.as_error()
                        if isinstance(recovery, ConsoleError)
                        else str(recovery),
                    }
        finally:
            if channel is not None:
                histories += list(getattr(channel, "history", []))
                try:
                    channel.close()
                except (OSError, ConsoleError):
                    result["status"] = "unverified"
                    result["configuration_verified"] = False
                    result["persistence_verified"] = False
                    result["errors"].append(
                        {
                            "code": "netstream_channel_close_failed",
                            "message": "Channel close failed",
                        }
                    )
            try:
                atomic_json(directory / "transcript.json", histories)
                atomic_json(directory / "result.json", result)
            except (OSError, ValueError, ConsoleError) as exc:
                raise ConsoleError(
                    "NetStream receipt incomplete; no replay",
                    code="netstream_receipt_io_failed",
                    detail={"operation_id": operation, "device_mutation_possible": dirty},
                ) from exc
        return result
