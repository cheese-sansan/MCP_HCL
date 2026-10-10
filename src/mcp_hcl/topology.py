"""Versioned intent and semantic validation, independent of HCL power state."""

from __future__ import annotations

from ipaddress import ip_address, ip_interface, ip_network
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mcp_hcl.catalog import CatalogError, HclCatalog
from mcp_hcl.contracts import validation_errors
from mcp_hcl.models import StrictModel
from mcp_hcl.services import ServiceIntent, service_errors


class Device(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    x: float = 0
    y: float = 0

    @field_validator("name")
    @classmethod
    def printable_name(cls, value: str) -> str:
        if (
            not value.strip()
            or any(not char.isprintable() for char in value)
            or any(c in value for c in "[]")
        ):
            raise ValueError("Device name must be printable and cannot contain section delimiters")
        return value


class Endpoint(StrictModel):
    device: str
    interface: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9-]*\d+(?:/\d+)*$")


class Link(StrictModel):
    a: Endpoint
    b: Endpoint
    medium: Literal["ethernet", "serial"] = "ethernet"


class Address(StrictModel):
    device: str
    interface: str
    cidr: str

    @field_validator("cidr")
    @classmethod
    def valid_cidr(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("Address needs an explicit prefix length")
        return str(ip_interface(value))


class StaticRoute(StrictModel):
    device: str
    network: str
    next_hop: str
    preference: int = Field(default=60, ge=1, le=255)

    @field_validator("network")
    @classmethod
    def valid_network(cls, value: str) -> str:
        return str(ip_network(value, strict=True))

    @field_validator("next_hop")
    @classmethod
    def valid_next_hop(cls, value: str) -> str:
        return str(ip_address(value))


class Annotation(StrictModel):
    text: str = Field(max_length=4096)
    x: float = 0
    y: float = 0


class HostSetting(StrictModel):
    device: str
    interface: str
    ipv4: Literal["static", "dhcp", "none"] = "none"
    ipv6: Literal["static", "slaac", "none"] = "none"


class InterfaceRef(StrictModel):
    device: str
    interface: str


class Subinterface(StrictModel):
    device: str
    parent: str
    vlan: int = Field(ge=1, le=4094)

    @property
    def interface(self):
        return f"{self.parent}.{self.vlan}"


class WirelessAssociation(StrictModel):
    device: str
    interface: str
    ap: str
    ssid: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,32}$")
    security: Literal["open", "wpa2_psk"] = "wpa2_psk"


class TopologyPlan(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=64)
    devices: list[Device] = Field(min_length=1, max_length=256)
    links: list[Link] = Field(default_factory=list, max_length=4096)
    addresses: list[Address] = Field(default_factory=list, max_length=4096)
    routes: list[StaticRoute] = Field(default_factory=list, max_length=4096)
    services: list[ServiceIntent] = Field(default_factory=list, max_length=4096)
    annotations: list[Annotation] = Field(default_factory=list, max_length=1024)
    host_settings: list[HostSetting] = Field(default_factory=list, max_length=256)
    subinterfaces: list[Subinterface] = Field(default_factory=list, max_length=256)
    ipv6_ra: list[InterfaceRef] = Field(default_factory=list, max_length=256)
    wireless_associations: list[WirelessAssociation] = Field(default_factory=list, max_length=256)


def wired_graph(
    plan: TopologyPlan, links: list[Link], wireless_devices: set[str]
) -> dict[str, Any]:
    """Connected components of valid declared wired links; no traffic simulation."""
    identifiers = list(
        dict.fromkeys(device.id for device in plan.devices if device.id not in wireless_devices)
    )
    adjacency = {identifier: set() for identifier in identifiers}
    edge_count = 0
    for link in links:
        if link.a.device in adjacency and link.b.device in adjacency:
            adjacency[link.a.device].add(link.b.device)
            adjacency[link.b.device].add(link.a.device)
            edge_count += 1
    unseen = set(identifiers)
    components = []
    for origin in identifiers:
        if origin not in unseen:
            continue
        members = {origin}
        queue = [origin]
        unseen.remove(origin)
        while queue:
            for neighbor in adjacency[queue.pop()]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    members.add(neighbor)
                    queue.append(neighbor)
        components.append([identifier for identifier in identifiers if identifier in members])
    return {
        "verified_scope": "declared_wired_links_only",
        "connected": len(components) <= 1,
        "components": components,
        "wired_devices": identifiers,
        "excluded_wireless_devices": sorted(wireless_devices),
        "edge_count": edge_count,
        "connectivity_verified": False,
    }


def validate_plan(
    data: dict[str, Any],
    catalog: HclCatalog,
    *,
    validation_level: Literal["topology", "configuration"] = "topology",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unverified",
        "target_project": None,
        "operation_id": uuid4().hex,
        "operation": "validate_topology_plan",
        "evidence": [],
        "errors": [],
        "warnings": [],
        "runtime_verified": False,
        "full_live_gate_passed": False,
        "guest_boot_verified": False,
        "configuration_verified": False,
        "connectivity_verified": False,
        "validation_level": validation_level,
        "graph": None,
    }
    if validation_level not in ("topology", "configuration"):
        result.update(
            status="rejected",
            valid=False,
            validation_level=None,
            errors=[
                {
                    "code": "invalid_validation_level",
                    "message": "Use topology or configuration validation",
                }
            ],
        )
        return result
    try:
        plan = TopologyPlan.model_validate(data)
    except ValidationError as exc:
        result.update(status="rejected", valid=False, errors=validation_errors(exc))
        return result
    try:
        installed = catalog.devices()
    except (CatalogError, OSError, UnicodeError) as exc:
        result.update(
            status="partial",
            valid=None,
            errors=[{"code": "catalog_unavailable", "message": str(exc)}],
        )
        return result
    models = {row["model"]: row for row in installed["devices"]}
    devices: dict[str, Device] = {}
    names: set[str] = set()

    def error(code: str, message: str):
        result["errors"].append({"code": code, "message": message})

    for device in plan.devices:
        if device.id in devices:
            error("duplicate_device_id", device.id)
        if device.name in names:
            error("duplicate_device_name", device.name)
        devices[device.id] = device
        names.add(device.name)
        if device.model not in models:
            error("unknown_model", device.model)
    result["evidence"] = [
        models[model]["evidence"]
        for model in sorted({d.model for d in plan.devices})
        if model in models
    ]

    def check_endpoint(device_id: str, interface: str, *, physical_only=False) -> bool:
        device = devices.get(device_id)
        if device is None:
            error("unknown_device", device_id)
            return False
        model = models.get(device.model)
        if model is None:
            return False
        logical = {
            f"Vlan-interface{vlan}"
            for service in plan.services
            if service.device == device_id and service.feature == "vlan"
            for vlan in service.parameters.vlans
        }
        logical |= {s.interface for s in plan.subinterfaces if s.device == device_id}
        if physical_only:
            logical = set()
        if (
            interface
            not in set(model["default_interfaces"])
            | set(model.get("native_interfaces", []))
            | logical
            or interface == "NULL0"
        ):
            error("unknown_physical_interface", f"{device_id}/{interface}")
            return False
        return True

    used: set[tuple[str, str]] = set()
    valid_links: list[Link] = []
    for link in plan.links:
        valid_link = True
        if link.a.device == link.b.device:
            error("self_link", link.a.device)
            valid_link = False
        for endpoint in (link.a, link.b):
            if not check_endpoint(endpoint.device, endpoint.interface, physical_only=True):
                valid_link = False
            key = (endpoint.device, endpoint.interface)
            if key in used:
                error("duplicate_port", "/".join(key))
                valid_link = False
            used.add(key)
            is_serial = endpoint.interface.startswith("Serial")
            if is_serial != (link.medium == "serial"):
                error("medium_mismatch", "/".join(key))
                valid_link = False
        if valid_link:
            valid_links.append(link)
    assigned: set[tuple[str, str, int]] = set()
    addresses: set[str] = set()
    for address in plan.addresses:
        check_endpoint(address.device, address.interface)
        if (
            address.device in devices
            and models.get(devices[address.device].model, {}).get("control_kind") == "native_gui"
        ):
            error("native_terminal_static_address_unverified", address.device)
        parsed = ip_interface(address.cidr)
        key = (address.device, address.interface, parsed.version)
        if key in assigned:
            error("duplicate_interface_address_family", f"{address.device}/{address.interface}")
        assigned.add(key)
        if str(parsed.ip) in addresses:
            error("duplicate_ip", str(parsed.ip))
        addresses.add(str(parsed.ip))
        if (
            parsed.version == 4
            and parsed.network.prefixlen < 31
            and parsed.ip in (parsed.network.network_address, parsed.network.broadcast_address)
        ):
            error("reserved_host_address", address.cidr)
    for route in plan.routes:
        if route.device not in devices:
            error("unknown_device", route.device)
        if ip_network(route.network).version != ip_address(route.next_hop).version:
            error("route_address_family_mismatch", route.network)
        if (
            route.device in devices
            and models.get(devices[route.device].model, {}).get("control_kind") == "native_gui"
        ):
            error("native_terminal_route_unverified", route.device)
    subkeys = set()
    for sub in plan.subinterfaces:
        check_endpoint(sub.device, sub.parent, physical_only=True)
        if (
            sub.device in devices
            and models.get(devices[sub.device].model, {}).get("control_kind") == "native_gui"
        ):
            error("native_terminal_subinterface_forbidden", sub.device)
        key = (sub.device, sub.interface)
        if key in subkeys:
            error("duplicate_subinterface", str(key))
        subkeys.add(key)
        if sub.parent.startswith("Serial") or "." in sub.parent:
            error("invalid_subinterface_parent", sub.parent)
    hostkeys = set()
    for host in plan.host_settings:
        check_endpoint(host.device, host.interface, physical_only=True)
        model = models.get(devices[host.device].model, {}) if host.device in devices else {}
        if model.get("control_kind") == "native_gui":
            capabilities = model.get("capabilities", {})
            if host.ipv4 not in capabilities.get(
                "ipv4_modes", []
            ) or host.ipv6 not in capabilities.get("ipv6_modes", []):
                error("native_terminal_address_mode_unverified", host.device)
        key = (host.device, host.interface)
        if key in hostkeys:
            error("duplicate_host_setting", str(key))
        hostkeys.add(key)
        for family, mode in ((4, host.ipv4), (6, host.ipv6)):
            present = (host.device, host.interface, family) in assigned
            if (mode in {"dhcp", "slaac", "none"} and present) or (
                mode == "static" and not present
            ):
                error("host_address_mode_conflict", f"{host.device}/{host.interface}/IPv{family}")
    for ra in plan.ipv6_ra:
        check_endpoint(ra.device, ra.interface)
        if (ra.device, ra.interface, 6) not in assigned:
            error("ra_without_ipv6_address", f"{ra.device}/{ra.interface}")
    wireless_devices: set[str] = set()
    for association in plan.wireless_associations:
        known_radio = check_endpoint(association.device, association.interface, physical_only=True)
        if not association.interface.startswith(("WLAN", "Wireless")):
            error("wireless_interface_required", f"{association.device}/{association.interface}")
        elif known_radio:
            wireless_devices.add(association.device)
        device = devices.get(association.device)
        model = models.get(device.model, {}) if device else {}
        if model.get("control_kind") == "native_gui":
            if association.security not in model.get("capabilities", {}).get(
                "wireless_security", []
            ):
                error("wireless_security_unverified", association.device)
            if not any(
                h.device == association.device
                and h.interface == association.interface
                and h.ipv4 == "dhcp"
                for h in plan.host_settings
            ):
                error("wireless_dhcp_client_missing", association.device)
        if association.ap not in devices:
            error("unknown_wireless_ap", association.ap)
        elif not any(
            service.feature == "wireless"
            and service.parameters.ap_device == association.ap
            and service.parameters.ssid == association.ssid
            and service.parameters.security == association.security
            for service in plan.services
            if service.feature == "wireless" and service.parameters.mode == "ac"
        ):
            error("wireless_ssid_dependency", association.ssid)
    for service in plan.services:
        if service.feature == "dhcp" and service.parameters.mode == "server":
            pool = ip_network(service.parameters.network)
            excluded = [
                (ip_address(r.start), ip_address(r.end)) for r in service.parameters.excluded
            ]
            for address in plan.addresses:
                ip = ip_interface(address.cidr).ip
                if (
                    ip.version == 4
                    and ip in pool
                    and not any(start <= ip <= end for start, end in excluded)
                ):
                    error("static_address_in_dhcp_pool", f"{address.device}/{ip}")
            for vlan in (s for s in plan.services if s.feature == "vlan"):
                for svi in vlan.parameters.svis:
                    ip = ip_interface(svi.cidr).ip
                    if ip in pool and not any(start <= ip <= end for start, end in excluded):
                        error("static_address_in_dhcp_pool", f"{vlan.device}/{ip}")
    for service in plan.services:
        if service.device not in devices:
            error("unknown_device", service.device)
        elif models.get(devices[service.device].model, {}).get("control_kind") == "native_gui":
            error("native_terminal_cli_service_forbidden", service.device)
        result["warnings"].append(
            {
                "code": "feature_runtime_unverified",
                "device": service.device,
                "feature": service.feature,
            }
        )
    result["errors"].extend(service_errors(plan, models))
    if validation_level == "topology":
        graph = wired_graph(plan, valid_links, wireless_devices)
        result["graph"] = graph
        if not graph["connected"]:
            unreachable = [
                identifier for component in graph["components"][1:] for identifier in component
            ]
            result["errors"].append(
                {
                    "code": "topology_disconnected",
                    "message": "Separate wired components contain: " + ", ".join(unreachable),
                    "detail": {
                        "components": graph["components"],
                        "unreachable_devices": unreachable,
                    },
                    "suggestion": "Connect the separate wired components using available installed-model interfaces.",
                }
            )
    else:
        result["warnings"].append(
            {
                "code": "wired_graph_not_checked",
                "message": "Configuration validation does not require one connected wired topology.",
            }
        )
    result.update(
        status="verified" if not result["errors"] else "rejected",
        valid=not result["errors"],
        verified_scope=(
            "offline_plan_wired_graph_and_configuration_semantics_only"
            if validation_level == "topology"
            else "plan_structure_and_installed_default_interfaces_only"
        ),
        plan=plan.model_dump(mode="json"),
    )
    return result
