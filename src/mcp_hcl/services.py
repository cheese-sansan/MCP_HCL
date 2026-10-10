"""Typed, bounded Comware intents. Syntax verification is not firmware verification."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Annotated, Any, Literal, Union

from pydantic import Field, create_model, field_validator, model_validator

from mcp_hcl.acl_values import matches_every_ipv4, normalize_address
from mcp_hcl.models import StrictModel

Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.@:+/!=-]{0,62}$")]
InterfaceName = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9-]*\d+(?:/\d+)*(?:\.\d+)?$")]
VlanId = Annotated[int, Field(ge=1, le=4094)]
PortNumber = Annotated[int, Field(ge=1, le=65535)]
AclId = Annotated[int, Field(ge=2000, le=3999)]


class IPv4Fields(StrictModel):
    @field_validator("network", "source", "destination", check_fields=False)
    @classmethod
    def network_field(cls, value):
        return str(IPv4Network(value, strict=True)) if value is not None else None

    @field_validator(
        "router_id",
        "gateway",
        "collector",
        "global_address",
        "local_address",
        "start",
        "end",
        check_fields=False,
    )
    @classmethod
    def address_field(cls, value):
        return str(IPv4Address(value)) if value is not None else None

    @field_validator("cidr", check_fields=False)
    @classmethod
    def interface_field(cls, value):
        if "/" not in value:
            raise ValueError("An explicit prefix is required")
        return str(IPv4Interface(value))


class IPRange(IPv4Fields):
    start: str
    end: str

    @model_validator(mode="after")
    def ordered(self):
        if IPv4Address(self.start) > IPv4Address(self.end):
            raise ValueError("IP range is reversed")
        return self


class Dhcp(IPv4Fields):
    mode: Literal["server", "relay"]
    interface: InterfaceName
    pool: Token | None = None
    network: str | None = None
    gateway: str | None = None
    dns: list[str] = Field(default_factory=list, max_length=8)
    excluded: list[IPRange] = Field(default_factory=list, max_length=256)
    servers: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("dns", "servers")
    @classmethod
    def addresses(cls, value):
        return [str(IPv4Address(v)) for v in value]

    @model_validator(mode="after")
    def mode_fields(self):
        if self.mode == "server":
            if not self.pool or not self.network or not self.gateway or self.servers:
                raise ValueError("Server requires pool/network/gateway and forbids relay servers")
            network = IPv4Network(self.network)
            if network.prefixlen > 30:
                raise ValueError("DHCP server pools require at least a /30 subnet")
            if IPv4Address(self.gateway) not in network:
                raise ValueError("Gateway is outside the DHCP network")
            if any(
                IPv4Address(r.start) not in network or IPv4Address(r.end) not in network
                for r in self.excluded
            ):
                raise ValueError("Excluded addresses are outside the pool")
        elif not self.servers or any(
            (self.pool, self.network, self.gateway, self.dns, self.excluded)
        ):
            raise ValueError("Relay requires servers and forbids pool configuration")
        return self


class OspfNetwork(IPv4Fields):
    network: str
    area: int = Field(ge=0, le=4294967295)


class Ospf(IPv4Fields):
    process_id: int = Field(ge=1, le=65535)
    router_id: str
    networks: list[OspfNetwork] = Field(min_length=1, max_length=256)
    passive_interfaces: list[InterfaceName] = Field(default_factory=list, max_length=256)


class Rip(StrictModel):
    process_id: int = Field(default=1, ge=1, le=65535)
    version: Literal[1, 2] = 2
    networks: list[str] = Field(min_length=1, max_length=256)
    passive_interfaces: list[InterfaceName] = Field(default_factory=list, max_length=256)

    @field_validator("networks")
    @classmethod
    def classful_networks(cls, value):
        for item in value:
            n = IPv4Network(item, strict=True)
            first = int(str(n.network_address).split(".")[0])
            prefix = 8 if first < 128 else 16 if first < 192 else 24
            if first == 0 or first >= 224 or n.prefixlen != prefix:
                raise ValueError("RIP network statements require a unicast classful network")
        return [str(IPv4Network(v)) for v in value]


class VlanPort(StrictModel):
    interface: InterfaceName
    mode: Literal["access", "trunk"]
    vlan: VlanId | None = None
    allowed_vlans: list[VlanId] = Field(default_factory=list, max_length=4094)
    native_vlan: VlanId | None = None

    @model_validator(mode="after")
    def mode_fields(self):
        if self.mode == "access" and (
            self.vlan is None or self.allowed_vlans or self.native_vlan is not None
        ):
            raise ValueError("Access requires one VLAN and no trunk list")
        if self.mode == "trunk" and self.vlan is not None:
            raise ValueError("Trunk forbids an access VLAN; empty allowed_vlans means all")
        if len(set(self.allowed_vlans)) != len(self.allowed_vlans):
            raise ValueError("Duplicate trunk VLANs")
        return self


class Svi(IPv4Fields):
    vlan: VlanId
    cidr: str


class VlanName(StrictModel):
    vlan: VlanId
    name: str = Field(min_length=1, max_length=32, pattern=r"^[\x20-\x7e]+$")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if value != value.strip():
            raise ValueError("VLAN name cannot contain outer whitespace")
        return value


class VlanPatch(StrictModel):
    vlans: list[VlanId] = Field(default_factory=list, max_length=4094)
    names: list[VlanName] = Field(default_factory=list, max_length=4094)
    ports: list[VlanPort] = Field(default_factory=list, max_length=256)
    svis: list[Svi] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def unique_items(self):
        if len(set(self.vlans)) != len(self.vlans):
            raise ValueError("Duplicate VLANs")
        if len({name.vlan for name in self.names}) != len(self.names) or not {
            name.vlan for name in self.names
        } <= set(self.vlans):
            raise ValueError("VLAN names need unique declared IDs")
        if len({p.interface for p in self.ports}) != len(self.ports) or len(
            {s.vlan for s in self.svis}
        ) != len(self.svis):
            raise ValueError("Duplicate VLAN port or SVI")
        return self


class Vlan(VlanPatch):
    vlans: list[VlanId] = Field(min_length=1, max_length=4094)

    @model_validator(mode="after")
    def vlan_membership(self):
        used = (
            [p.vlan for p in self.ports if p.vlan]
            + [v for p in self.ports for v in p.allowed_vlans]
            + [s.vlan for s in self.svis]
        )
        if not set(used).issubset(set(self.vlans)):
            raise ValueError("Ports and SVIs must reference declared VLANs")
        return self


class AclPortMatch(StrictModel):
    operator: Literal["eq", "neq", "gt", "lt", "range"] = "eq"
    port: int = Field(ge=0, le=65535)
    end: int | None = Field(default=None, ge=0, le=65535)

    @model_validator(mode="after")
    def operands(self):
        if self.operator == "range":
            if self.end is None or self.end < self.port:
                raise ValueError("ACL range needs an ordered end port")
        elif self.end is not None:
            raise ValueError("Only range accepts an end port")
        return self


class AclIcmpMatch(StrictModel):
    type: int = Field(ge=0, le=255)
    code: int | None = Field(default=None, ge=0, le=255)


class AclRule(StrictModel):
    id: int = Field(ge=0, le=65534)
    action: Literal["permit", "deny"]
    protocol: (
        Literal[
            "ip", "icmp", "tcp", "udp", "gre", "ospf", "esp", "ah", "ahp", "eigrp", "igmp", "ipinip"
        ]
        | Annotated[int, Field(ge=0, le=255)]
    ) = "ip"
    source: str | None = None
    destination: str | None = None
    source_port: PortNumber | None = None
    destination_port: PortNumber | None = None
    source_port_match: AclPortMatch | None = None
    destination_port_match: AclPortMatch | None = None
    icmp: (
        AclIcmpMatch
        | Literal[
            "echo",
            "echo-reply",
            "fragmentneed-DFset",
            "host-redirect",
            "host-tos-redirect",
            "host-unreachable",
            "information-reply",
            "information-request",
            "net-redirect",
            "net-tos-redirect",
            "net-unreachable",
            "parameter-problem",
            "port-unreachable",
            "protocol-unreachable",
            "reassembly-timeout",
            "source-quench",
            "source-route-failed",
            "timestamp-reply",
            "timestamp-request",
            "ttl-exceeded",
        ]
        | None
    ) = None
    tcp_flags: list[Literal["ack", "fin", "psh", "rst", "syn", "urg", "established"]] = Field(
        default_factory=list, max_length=6
    )
    log: bool = False
    remark: str | None = Field(
        default=None, min_length=1, max_length=127, pattern=r"^[\x20-\x7e]+$"
    )

    @field_validator("source", "destination")
    @classmethod
    def acl_addresses(cls, value):
        return normalize_address(value)

    @model_validator(mode="after")
    def ports_need_transport(self):
        transport = self.protocol in ("tcp", "udp", 6, 17)
        if (
            any(
                value is not None
                for value in (
                    self.source_port,
                    self.destination_port,
                    self.source_port_match,
                    self.destination_port_match,
                )
            )
            and not transport
        ):
            raise ValueError("ACL ports require TCP or UDP")
        if (
            self.source_port is not None
            and self.source_port_match is not None
            or self.destination_port is not None
            and self.destination_port_match is not None
        ):
            raise ValueError("Use one ACL port representation per side")
        if self.icmp is not None and self.protocol not in ("icmp", 1):
            raise ValueError("ICMP matching requires ICMP protocol")
        if self.tcp_flags and self.protocol not in ("tcp", 6):
            raise ValueError("TCP flags require TCP protocol")
        if (
            len(set(self.tcp_flags)) != len(self.tcp_flags)
            or "established" in self.tcp_flags
            and len(self.tcp_flags) > 1
        ):
            raise ValueError(
                "TCP flags must be unique; established cannot combine with explicit flags"
            )
        if self.remark is not None and self.remark != self.remark.strip():
            raise ValueError("ACL remark cannot contain outer whitespace")
        return self


class Binding(StrictModel):
    interface: InterfaceName
    direction: Literal["inbound", "outbound"] = "inbound"


class Acl(StrictModel):
    number: AclId | None = None
    name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,62}$")] | None = None
    acl_type: Literal["basic", "advanced"] | None = None
    implicit_deny: bool = True
    rules: list[AclRule] = Field(min_length=1, max_length=4096)
    bindings: list[Binding] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def rules_valid(self):
        if (self.number is None) == (self.name is None):
            raise ValueError("Supply exactly one ACL number or name")
        if self.name is not None:
            self.name = self.name.casefold()
            if self.name == "all":
                raise ValueError("ACL name all is reserved")
            if self.acl_type is None:
                raise ValueError("Named ACL requires basic or advanced acl_type")
        elif self.acl_type is not None and self.acl_type != (
            "basic" if self.number < 3000 else "advanced"
        ):
            raise ValueError("ACL type conflicts with its numeric range")
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("Duplicate ACL rule IDs")
        if (
            self.implicit_deny
            and max(rule.id for rule in self.rules) == 65534
            and not any(matches_every_ipv4(rule) for rule in self.rules)
        ):
            raise ValueError("Implicit deny needs a free final rule ID or an explicit catch-all")
        if len({(binding.interface, binding.direction) for binding in self.bindings}) != len(
            self.bindings
        ):
            raise ValueError("Duplicate ACL interface/direction binding")
        if self.kind == "basic" and any(
            r.protocol != "ip"
            or r.destination
            or r.source_port is not None
            or r.destination_port is not None
            or r.source_port_match is not None
            or r.destination_port_match is not None
            or r.icmp is not None
            or r.tcp_flags
            for r in self.rules
        ):
            raise ValueError("Basic ACL permits only source-address rules")
        return self

    @property
    def kind(self):
        return (
            self.acl_type if self.number is None else "basic" if self.number < 3000 else "advanced"
        )

    @property
    def identity(self):
        return ("number", self.number) if self.number is not None else ("name", self.name)

    @property
    def view(self):
        return (
            f"acl number {self.number}"
            if self.number is not None
            else f"acl {self.kind} name {self.name}"
        )

    @property
    def reference(self):
        return str(self.number) if self.number is not None else "name " + self.name


class NatOutbound(StrictModel):
    interface: InterfaceName
    acl: AclId | None = None
    acl_name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,62}$")] | None = None
    address_group: int | None = Field(default=None, ge=0, le=65535)
    pat: bool = True

    @model_validator(mode="after")
    def classifier(self):
        if (self.acl is None) == (self.acl_name is None):
            raise ValueError("NAT outbound needs exactly one ACL number or name")
        if self.acl_name is not None:
            self.acl_name = self.acl_name.casefold()
            if self.acl_name == "all":
                raise ValueError("ACL name all is reserved")
        if not self.pat and self.address_group is None:
            raise ValueError("Dynamic NO-PAT requires an address group")
        return self


class NatAddressGroup(IPv4Fields):
    id: int = Field(ge=0, le=65535)
    start: str
    end: str

    @model_validator(mode="after")
    def range(self):
        start = int(IPv4Address(self.start))
        end = int(IPv4Address(self.end))
        if end < start:
            raise ValueError("NAT pool range is reversed")
        if end - start + 1 > 65536:
            raise ValueError("NAT pool exceeds this command bundle budget of 65536 addresses")
        return self


class NatStatic(IPv4Fields):
    interface: InterfaceName
    global_address: str
    local_address: str
    protocol: Literal["tcp", "udp"] | None = None
    global_port: PortNumber | None = None
    local_port: PortNumber | None = None

    @model_validator(mode="after")
    def mapping(self):
        if any(
            v is not None for v in (self.protocol, self.global_port, self.local_port)
        ) and not all(v is not None for v in (self.protocol, self.global_port, self.local_port)):
            raise ValueError("Protocol and both ports must be supplied together")
        return self


class Nat(StrictModel):
    address_groups: list[NatAddressGroup] = Field(default_factory=list, max_length=256)
    outbound: list[NatOutbound] = Field(default_factory=list, max_length=256)
    static: list[NatStatic] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.outbound and not self.static:
            raise ValueError("NAT requires an outbound or static mapping")
        ids = {group.id for group in self.address_groups}
        if len(ids) != len(self.address_groups):
            raise ValueError("Duplicate NAT address group IDs")
        if (
            not {rule.address_group for rule in self.outbound if rule.address_group is not None}
            <= ids
        ):
            raise ValueError("NAT outbound references an undeclared address group")
        modes = {}
        for rule in self.outbound:
            if rule.address_group is not None:
                if rule.address_group in modes and modes[rule.address_group] != rule.pat:
                    raise ValueError("One NAT address group cannot mix PAT and NO-PAT")
                modes[rule.address_group] = rule.pat
        if len({(rule.interface, rule.acl, rule.acl_name) for rule in self.outbound}) != len(
            self.outbound
        ):
            raise ValueError("Duplicate NAT outbound interface/classifier")
        return self


class Security(StrictModel):
    username: Token
    password: Token
    privilege: int = Field(default=15, ge=0, le=15)
    vty_acl: AclId | None = None
    vty_last: int = Field(default=4, ge=0, le=63)
    disable_telnet: Literal[True] = True


class Wireless(StrictModel):
    mode: Literal["ac", "fat_ap"]
    template: Token
    ssid: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,32}$")]
    vlan: VlanId
    security: Literal["open", "wpa2_psk"] = "wpa2_psk"
    psk: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.@:+/!=-]{8,63}$")] | None = None
    radio: int = Field(default=1, ge=1, le=4)
    ap_device: str | None = None
    ap_name: Token | None = None
    ap_model: Token | None = None
    serial_id: Token | None = None
    radio_interface: InterfaceName | None = None

    @model_validator(mode="after")
    def binding_required(self):
        if (self.security == "wpa2_psk") != (self.psk is not None):
            raise ValueError("WPA2-PSK requires a key; open security forbids a key")
        if self.mode == "ac" and (
            not all((self.ap_device, self.ap_name, self.ap_model, self.serial_id))
            or self.radio_interface
        ):
            raise ValueError(
                "AC mode requires AP device/name/model/serial-id and forbids radio_interface"
            )
        if self.mode == "fat_ap" and (
            not self.radio_interface
            or any((self.ap_device, self.ap_name, self.ap_model, self.serial_id))
        ):
            raise ValueError("FAT AP requires radio_interface and forbids AC bindings")
        return self


class Qos(StrictModel):
    classifier: Token
    behavior: Token
    policy: Token
    acl: AclId | None = None
    dscp: int | None = Field(default=None, ge=0, le=63)
    remark_dscp: int | None = Field(default=None, ge=0, le=63)
    cir: int | None = Field(default=None, ge=1, le=2147483647)
    bindings: list[Binding] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def classifier_behavior(self):
        if (self.acl is None and self.dscp is None) or (
            self.remark_dscp is None and self.cir is None
        ):
            raise ValueError("QoS needs a classifier match and at least one behavior")
        return self


class Netstream(IPv4Fields):
    collector: str
    port: PortNumber
    version: Literal[5, 9] = 9
    interfaces: list[Binding] = Field(min_length=1, max_length=256)


PARAMETERS = {
    "dhcp": Dhcp,
    "ospf": Ospf,
    "rip": Rip,
    "vlan": Vlan,
    "acl": Acl,
    "nat": Nat,
    "security": Security,
    "wireless": Wireless,
    "qos": Qos,
    "netstream": Netstream,
}
SERVICE_MODELS = [
    create_model(
        feature.title() + "Intent",
        __base__=StrictModel,
        device=(str, ...),
        feature=(Literal[feature], ...),
        parameters=(parameters, ...),
    )
    for feature, parameters in PARAMETERS.items()
]
ServiceIntent = Annotated[Union[tuple(SERVICE_MODELS)], Field(discriminator="feature")]


def service_errors(plan: Any, models: dict) -> list[dict]:
    errors = []
    devices = {d.id: d for d in plan.devices}
    acls = {
        (s.device, s.parameters.number)
        for s in plan.services
        if s.feature == "acl" and s.parameters.number is not None
    }
    acl_names = {
        (s.device, s.parameters.name)
        for s in plan.services
        if s.feature == "acl" and s.parameters.name is not None
    }
    vlans = {}
    identifiers = set()
    acl_bindings = set()

    def error(code, message):
        errors.append({"code": code, "message": message})

    for service in plan.services:
        if service.feature == "vlan":
            vlans.setdefault(service.device, set()).update(service.parameters.vlans)
    assigned = {
        (a.device, a.interface): IPv4Interface(a.cidr) for a in plan.addresses if ":" not in a.cidr
    }
    ips = {str(ip.ip) for ip in assigned.values()}
    # SVIs are address declarations too. Collect them before checking DHCP or
    # OSPF so service order cannot change dependency resolution.
    for service in plan.services:
        if service.feature != "vlan":
            continue
        for svi in service.parameters.svis:
            parsed = IPv4Interface(svi.cidr)
            key = (service.device, f"Vlan-interface{svi.vlan}")
            if str(parsed.ip) in ips or key in assigned:
                error(
                    "duplicate_svi_address",
                    "SVI address conflicts with another address declaration",
                )
            else:
                assigned[key] = parsed
            ips.add(str(parsed.ip))
            if parsed.network.prefixlen < 31 and parsed.ip in (
                parsed.network.network_address,
                parsed.network.broadcast_address,
            ):
                error("reserved_host_address", svi.cidr)
    for s in plan.services:
        if s.device not in devices:
            continue
        p = s.parameters
        if s.feature == "acl":
            for binding in p.bindings:
                key = (s.device, binding.interface, binding.direction)
                if key in acl_bindings:
                    error(
                        "duplicate_acl_binding",
                        "Only one IPv4 ACL may be selected per interface/direction",
                    )
                acl_bindings.add(key)
        interfaces = list(getattr(p, "passive_interfaces", []))
        if hasattr(p, "interface"):
            interfaces.append(p.interface)
        for collection in ("ports", "bindings", "interfaces", "outbound", "static"):
            interfaces.extend(v.interface for v in getattr(p, collection, []))
        model = models.get(devices[s.device].model, {})
        known = set(model.get("default_interfaces", [])) | {
            f"Vlan-interface{v}" for v in vlans.get(s.device, set())
        }
        known |= {sub.interface for sub in plan.subinterfaces if sub.device == s.device}
        for interface in interfaces:
            if interface not in known or interface == "NULL0":
                error("unknown_service_interface", f"{s.device}/{interface}")
        refs = []
        if s.feature == "nat":
            refs.extend(v.acl for v in p.outbound if v.acl is not None)
            for rule in p.outbound:
                if rule.acl_name is not None and (s.device, rule.acl_name) not in acl_names:
                    error("missing_acl_dependency", f"{s.device}/ACL name {rule.acl_name}")
        if s.feature == "security" and p.vty_acl is not None:
            refs.append(p.vty_acl)
        if s.feature == "qos" and p.acl is not None:
            refs.append(p.acl)
        for acl in refs:
            if (s.device, acl) not in acls:
                error("missing_acl_dependency", f"{s.device}/ACL {acl}")
        if s.feature == "wireless":
            if p.vlan not in vlans.get(s.device, set()):
                error("missing_vlan_dependency", f"{s.device}/VLAN {p.vlan}")
            if p.mode == "ac":
                ap = devices.get(p.ap_device)
                if devices[s.device].model != "AC" or not ap or ap.model != "AP":
                    error("wireless_model_mismatch", "AC binding needs an AC and a referenced AP")
            elif devices[s.device].model != "AP":
                error("wireless_model_mismatch", "FAT AP service requires an AP")
        if s.feature == "dhcp" and p.mode == "server":
            current = assigned.get((s.device, p.interface))
            if (
                current is None
                or current.network != IPv4Network(p.network)
                or str(current.ip) != p.gateway
            ):
                error(
                    "dhcp_interface_subnet_mismatch",
                    "DHCP pool/gateway must match the addressed serving interface",
                )
        if s.feature == "ospf":
            if p.router_id == "0.0.0.0":
                error(
                    "ospf_invalid_router_id",
                    f"{s.device}/OSPF {p.process_id}: router-id cannot be 0.0.0.0",
                )
            networks = {a.network for a in p.networks}
            present = [ip for (device, _), ip in assigned.items() if device == s.device]
            if any(not any(ip.ip in IPv4Network(n) for ip in present) for n in networks):
                error(
                    "ospf_network_unattached", "OSPF networks must include an addressed interface"
                )
        if s.feature == "nat" and len(
            {(v.interface, v.global_address, v.global_port, v.protocol) for v in p.static}
        ) != len(p.static):
            error("duplicate_nat_mapping", "Duplicate NAT outside mapping")
        identity = (
            s.device,
            s.feature,
            p.identity
            if s.feature == "acl"
            else getattr(
                p,
                "number",
                getattr(
                    p,
                    "pool",
                    getattr(
                        p, "policy", getattr(p, "template", getattr(p, "process_id", "singleton"))
                    ),
                ),
            ),
        )
        if identity in identifiers:
            error("duplicate_service", str(identity))
        identifiers.add(identity)
    return errors
