"""IPv4 ACL values shared by validation, generation and semantic readback."""
from ipaddress import IPv4Address,IPv4Network

PROTOCOLS={'ip':'ip','icmp':1,'igmp':2,'ipinip':4,'tcp':6,'udp':17,'gre':47,
           'esp':50,'ah':51,'ahp':51,'eigrp':88,'ospf':89}
ICMP_MESSAGES={
    'echo':(8,0),'echo-reply':(0,0),'fragmentneed-DFset':(3,4),
    'host-redirect':(5,1),'host-tos-redirect':(5,3),'host-unreachable':(3,1),
    'information-reply':(16,0),'information-request':(15,0),
    'net-redirect':(5,0),'net-tos-redirect':(5,2),'net-unreachable':(3,0),
    'parameter-problem':(12,0),'port-unreachable':(3,3),'protocol-unreachable':(3,2),
    'reassembly-timeout':(11,1),'source-quench':(4,0),'source-route-failed':(3,5),
    'timestamp-reply':(14,0),'timestamp-request':(13,0),'ttl-exceeded':(11,0),
}


def normalize_address(value):
    if value is None:return None
    if value=='any':return 'any'
    if '/' in value:return str(IPv4Network(value,strict=True))
    parts=value.split()
    if len(parts)==2 and parts[0]=='host':return 'host '+str(IPv4Address(parts[1]))
    if len(parts)==2:
        address=int(IPv4Address(parts[0]));wildcard=int(IPv4Address(parts[1]))
        return f'{IPv4Address(address&(~wildcard&0xffffffff))} {IPv4Address(wildcard)}'
    raise ValueError('ACL address needs CIDR, any, host IPv4 or IPv4 wildcard')


def address_pair(value):
    if value is None or value=='any':return (0,0xffffffff)
    if '/' in value:
        network=IPv4Network(value);return int(network.network_address),int(network.hostmask)
    parts=value.split()
    if parts[0]=='host':return int(IPv4Address(parts[1])),0
    wildcard=int(IPv4Address(parts[1]))
    return int(IPv4Address(parts[0]))&(~wildcard&0xffffffff),wildcard


def matches_every_ipv4(rule):
    return rule.protocol=='ip' and address_pair(rule.source)[1]==0xffffffff and address_pair(rule.destination)[1]==0xffffffff and not any(
        value is not None for value in (rule.source_port,rule.destination_port,rule.source_port_match,rule.destination_port_match,rule.icmp)) and not rule.tcp_flags


def acl_header(value):
    """Return stable identity/type metadata for known IPv4 ACL headers."""
    import re
    match=re.fullmatch(r'acl (number|basic|advanced) (?:(\d+)(?: name (\S+))?|name (\S+))(?: match-order (auto|config))?',value)
    if not match:return None
    form,number,label,named,order=match.groups()
    if number is not None:
        number=int(number)
        kind='basic' if 2000<=number<=2999 else 'advanced' if 3000<=number<=3999 else None
        if kind is None or form!='number' and form!=kind:return None
        return {'key':f'acl number {number}','number':number,'name':label.casefold() if label else None,
                'type':kind,'order':order or 'config'}
    if form=='number':return None
    return {'key':f'acl {form} name {named.casefold()}','number':None,'name':named.casefold(),
            'type':form,'order':order or 'config'}


def matches_acl(header,parameters):
    return header is not None and (header['number']==parameters.number if parameters.number is not None else
        header['name']==parameters.name and header['type']==parameters.kind)
