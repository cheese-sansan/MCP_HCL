"""NAT requests matching the pinned upstream's flat operation parameters."""
from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network
from typing import Literal
from pydantic import ConfigDict, Field, field_validator, model_validator
from mcp_hcl.models import StrictModel
from mcp_hcl.services import InterfaceName
from mcp_hcl.acl_values import normalize_address


def native_acl_number(value: str, namespace: str) -> int | None:
    if not value.isdigit():
        return None
    number = int(value)
    if namespace == 'comware':
        if 2000 <= number <= 3999:
            return number
    else:
        if 1 <= number <= 99:
            return 2000 + number
        if 1300 <= number <= 1999:
            return 2100 + number - 1300
        if 100 <= number <= 199:
            return 3000 + number - 100
        if 2000 <= number <= 2699:
            return 3100 + number - 2000
    raise ValueError('ACL number is outside its declared IOS or Comware namespace')


def application_schema(schema):
    pool_required = {'required': ['pool_start', 'pool_end', 'pool_netmask'],
                     'properties': {key: {'minLength': 1} for key in
                                    ('pool_name', 'pool_start', 'pool_end', 'pool_netmask')}}
    schema['allOf'] = [
        {'if': {'properties': {'mode': {'const': 'static'}}, 'required': ['mode']},
         'then': {'required': ['static_mappings'], 'properties': {'static_mappings': {'minItems': 1}}}},
        {'if': {'properties': {'mode': {'enum': ['dynamic', 'pat']}}, 'required': ['mode']},
         'then': {'required': ['inside_networks'], 'properties': {'inside_networks': {'minItems': 1}}}},
        {'if': {'anyOf': [
            {'properties': {'mode': {'const': 'dynamic'}}, 'required': ['mode']},
            {'allOf': [{'properties': {'mode': {'const': 'pat'}}, 'required': ['mode']},
                       {'not': {'properties': {'use_interface_overload': {'const': True}},
                                'required': ['use_interface_overload']}}]}]},
         'then': pool_required},
    ]


class NatMapping(StrictModel):
    inside_local: str
    inside_global: str

    @field_validator('inside_local', 'inside_global')
    @classmethod
    def ipv4(cls, value):
        return str(IPv4Address(value))


class NatOperation(StrictModel):
    router: str = Field(min_length=1, max_length=64)
    mode: Literal['static', 'dynamic', 'pat']
    inside_interface: InterfaceName
    outside_interface: InterfaceName
    acl_number: str = Field(default='1', pattern=r'^(?:[0-9]{1,4}|[A-Za-z][A-Za-z0-9_.-]{0,62})$')
    acl_namespace: Literal['ios', 'comware'] = 'ios'
    named_acl_type: Literal['basic', 'advanced'] | None = None
    pool_address_group: int | None = Field(default=None, ge=0, le=65535)
    static_mappings: list[NatMapping] = Field(default_factory=list, max_length=256)
    operation_key: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{8,64}$')
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator('router')
    @classmethod
    def printable_router(cls, value):
        if not value.strip() or any(not c.isprintable() for c in value):
            raise ValueError('Router selector must be printable')
        return value

    @field_validator('acl_number')
    @classmethod
    def canonical_numeric_acl(cls, value):
        return str(int(value)) if value.isdigit() else value

    @model_validator(mode='after')
    def common(self):
        if self.inside_interface == self.outside_interface:
            raise ValueError('Inside and outside interfaces must differ')
        if self.mode != 'static':
            native_acl_number(self.acl_number, self.acl_namespace)
        if self.acl_number.casefold() == 'all':
            raise ValueError('ACL name all is reserved')
        if self.mode != 'static' and self.acl_id is not None and self.named_acl_type is not None and self.named_acl_type != self.acl_kind:
            raise ValueError('ACL type conflicts with its numeric range')
        if len({m.inside_local for m in self.static_mappings}) != len(self.static_mappings):
            raise ValueError('Static mappings must have distinct inside-local addresses')
        if len({m.inside_global for m in self.static_mappings}) != len(self.static_mappings):
            raise ValueError('Static mappings must have distinct inside-global addresses')
        return self

    @property
    def acl_id(self):
        return native_acl_number(self.acl_number, self.acl_namespace)

    @property
    def acl_name(self):
        return None if self.acl_id is not None else self.acl_number.casefold()

    @property
    def acl_kind(self):
        return ('basic' if self.acl_id < 3000 else 'advanced') if self.acl_id is not None else self.named_acl_type or 'basic'

    @field_validator('pool_name', check_fields=False)
    @classmethod
    def pool_label(cls, value):
        if value and (not value.strip() or any(not character.isprintable() for character in value)):
            raise ValueError('Pool name must be printable')
        return value

    @property
    def acl_reference(self):
        return str(self.acl_id) if self.acl_id is not None else 'name ' + self.acl_name


class NatApplication(NatOperation):
    model_config = ConfigDict(json_schema_extra=application_schema)
    inside_networks: list[str] = Field(default_factory=list, max_length=4096)
    pool_name: str = Field(default='NAT-POOL', max_length=64)
    pool_start: str = ''
    pool_end: str = ''
    pool_netmask: str = ''
    use_interface_overload: bool = False

    @field_validator('inside_networks')
    @classmethod
    def networks(cls, values):
        # Upstream accepts any, host IPv4, and arbitrary IPv4 wildcard pairs.
        return [normalize_address(value.strip()) for value in values]

    @field_validator('pool_start', 'pool_end')
    @classmethod
    def pool_ip(cls, value):
        return str(IPv4Address(value)) if value else ''

    @field_validator('pool_netmask')
    @classmethod
    def netmask(cls, value):
        if not value:
            return value
        canonical = str(IPv4Address(value))
        network = IPv4Network('0.0.0.0/' + canonical)
        if str(network.netmask) != canonical:
            raise ValueError('Pool mask must be a contiguous netmask, not a wildcard')
        return canonical

    @model_validator(mode='after')
    def mode_fields(self):
        if self.mode == 'static':
            if not self.static_mappings:
                raise ValueError('Static NAT needs at least one mapping')
            return self
        if not self.inside_networks:
            raise ValueError('Dynamic NAT and PAT need inside_networks')
        if self.mode == 'dynamic' or not self.use_interface_overload:
            if not self.pool_name:
                raise ValueError('Pool NAT needs a pool name')
            if not all((self.pool_start, self.pool_end, self.pool_netmask)):
                raise ValueError('Pool NAT needs start, end and netmask')
            start, end = int(IPv4Address(self.pool_start)), int(IPv4Address(self.pool_end))
            if end < start:
                raise ValueError('NAT pool range is reversed')
            if end - start + 1 > 65536:
                raise ValueError('Pool exceeds the command bundle budget of 65536 addresses')
        return self

    @property
    def uses_pool(self):
        return self.mode == 'dynamic' or self.mode == 'pat' and not self.use_interface_overload


class NatRemoval(NatOperation):
    pool_name: str = Field(default='', max_length=64)
    remove_acl: bool = True
    remove_pool: bool = True
    disable_static_interface: bool = True
