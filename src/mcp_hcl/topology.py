"""Versioned intent and semantic validation, independent of HCL power state."""

from __future__ import annotations

from ipaddress import ip_address, ip_interface, ip_network
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mcp_hcl.catalog import CatalogError, HclCatalog
from mcp_hcl.contracts import validation_errors


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)


class Device(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
    name: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    x: float = 0
    y: float = 0

    @field_validator('name')
    @classmethod
    def printable_name(cls, value: str) -> str:
        if not value.strip() or any(not char.isprintable() for char in value) or any(c in value for c in '[]'):
            raise ValueError('Device name must be printable and cannot contain section delimiters')
        return value


class Endpoint(StrictModel):
    device: str
    interface: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9-]*\d+(?:/\d+)*$')


class Link(StrictModel):
    a: Endpoint
    b: Endpoint
    medium: Literal['ethernet', 'serial'] = 'ethernet'


class Address(StrictModel):
    device: str
    interface: str
    cidr: str

    @field_validator('cidr')
    @classmethod
    def valid_cidr(cls, value: str) -> str:
        if '/' not in value:
            raise ValueError('Address needs an explicit prefix length')
        return str(ip_interface(value))


class StaticRoute(StrictModel):
    device: str
    network: str
    next_hop: str

    @field_validator('network')
    @classmethod
    def valid_network(cls, value: str) -> str:
        return str(ip_network(value, strict=True))

    @field_validator('next_hop')
    @classmethod
    def valid_next_hop(cls, value: str) -> str:
        return str(ip_address(value))


class ServiceIntent(StrictModel):
    device: str
    feature: Literal['dhcp', 'ospf', 'rip', 'vlan', 'acl', 'nat', 'security', 'wireless', 'qos', 'netstream']
    # Intent is preserved for planning. A generator must reject fields it does
    # not implement rather than silently turn these parameters into commands.
    parameters: dict[str, Any] = Field(default_factory=dict)


class Annotation(StrictModel):
    text: str = Field(max_length=4096)
    x: float = 0
    y: float = 0


class TopologyPlan(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=64)
    devices: list[Device] = Field(min_length=1, max_length=256)
    links: list[Link] = Field(default_factory=list, max_length=4096)
    addresses: list[Address] = Field(default_factory=list, max_length=4096)
    routes: list[StaticRoute] = Field(default_factory=list, max_length=4096)
    services: list[ServiceIntent] = Field(default_factory=list, max_length=4096)
    annotations: list[Annotation] = Field(default_factory=list, max_length=1024)


def validate_plan(data: dict[str, Any], catalog: HclCatalog) -> dict[str, Any]:
    result: dict[str, Any] = {
        'status': 'unverified', 'target_project': None, 'operation_id': uuid4().hex,
        'operation': 'validate_topology_plan', 'evidence': [], 'errors': [], 'warnings': [],
        'runtime_verified': False, 'full_live_gate_passed': False,
    }
    try:
        plan = TopologyPlan.model_validate(data)
    except ValidationError as exc:
        result.update(status='rejected', valid=False, errors=validation_errors(exc))
        return result
    try:
        installed = catalog.devices()
    except (CatalogError, OSError, UnicodeError) as exc:
        result.update(status='partial', valid=None, errors=[{'code': 'catalog_unavailable', 'message': str(exc)}])
        return result
    models = {row['model']: row for row in installed['devices']}
    devices: dict[str, Device] = {}
    names: set[str] = set()

    def error(code: str, message: str):
        result['errors'].append({'code': code, 'message': message})

    for device in plan.devices:
        if device.id in devices:
            error('duplicate_device_id', device.id)
        if device.name in names:
            error('duplicate_device_name', device.name)
        devices[device.id] = device
        names.add(device.name)
        if device.model not in models:
            error('unknown_model', device.model)
    result['evidence'] = [models[model]['evidence'] for model in sorted({d.model for d in plan.devices}) if model in models]

    def check_endpoint(device_id: str, interface: str) -> bool:
        device = devices.get(device_id)
        if device is None:
            error('unknown_device', device_id)
            return False
        model = models.get(device.model)
        if model is None:
            return False
        if interface not in model['default_interfaces'] or interface == 'NULL0':
            error('unknown_physical_interface', f'{device_id}/{interface}')
            return False
        return True

    used: set[tuple[str, str]] = set()
    for link in plan.links:
        if link.a.device == link.b.device:
            error('self_link', link.a.device)
        for endpoint in (link.a, link.b):
            check_endpoint(endpoint.device, endpoint.interface)
            key = (endpoint.device, endpoint.interface)
            if key in used:
                error('duplicate_port', '/'.join(key))
            used.add(key)
            is_serial = endpoint.interface.startswith('Serial')
            if is_serial != (link.medium == 'serial'):
                error('medium_mismatch', '/'.join(key))
    assigned: set[tuple[str, str, int]] = set()
    addresses: set[str] = set()
    for address in plan.addresses:
        check_endpoint(address.device, address.interface)
        parsed = ip_interface(address.cidr)
        key = (address.device, address.interface, parsed.version)
        if key in assigned:
            error('duplicate_interface_address_family', f'{address.device}/{address.interface}')
        assigned.add(key)
        if str(parsed.ip) in addresses:
            error('duplicate_ip', str(parsed.ip))
        addresses.add(str(parsed.ip))
        if parsed.version == 4 and parsed.network.prefixlen < 31 and parsed.ip in (
            parsed.network.network_address, parsed.network.broadcast_address
        ):
            error('reserved_host_address', address.cidr)
    for route in plan.routes:
        if route.device not in devices:
            error('unknown_device', route.device)
        if ip_network(route.network).version != ip_address(route.next_hop).version:
            error('route_address_family_mismatch', route.network)
    for service in plan.services:
        if service.device not in devices:
            error('unknown_device', service.device)
        result['warnings'].append({'code': 'feature_runtime_unverified', 'device': service.device,
                                   'feature': service.feature})
    result.update(status='verified' if not result['errors'] else 'rejected', valid=not result['errors'],
                  verified_scope='plan_structure_and_installed_default_interfaces_only',
                  plan=plan.model_dump(mode='json'))
    return result
