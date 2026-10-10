"""Comware VLAN readback, including ranges, defaults and routed subinterfaces."""
import re
from ipaddress import IPv4Interface
from mcp_hcl.console import ConsoleError


def configuration_views(config):
    result={};context=None
    for line in config.splitlines():
        value=line.strip()
        if not value or value in {'#','return'}:continue
        if not line.startswith(' '):context=value;result.setdefault(context,[])
        elif context is not None:result[context].append(value)
    return result


def vlan_set(value):
    tokens=value.split();result=set();index=0
    if tokens==['all']:return set(range(1,4095))
    while index<len(tokens):
        start=int(tokens[index]);index+=1;end=start
        if index<len(tokens) and tokens[index]=='to':
            end=int(tokens[index+1]);index+=2
        if not 1<=start<=end<=4094:raise ValueError('Invalid VLAN range')
        result.update(range(start,end+1))
    return result


def permit_commands(vlans):
    if not vlans:return ['port trunk permit vlan all']
    ordered=sorted(set(vlans));items=[];start=end=ordered[0]
    for value in ordered[1:]:
        if value==end+1:end=value
        else:items.append(str(start) if start==end else f'{start} to {end}');start=end=value
    items.append(str(start) if start==end else f'{start} to {end}')
    # The bundled command help includes devices limited to ten VLAN items.
    return ['port trunk permit vlan '+' '.join(items[index:index+10]) for index in range(0,len(items),10)]


def exact_vlan_commands(commands):
    result=[];interface=None;cleared=set()
    for command in commands:
        if command.startswith('interface '):interface=command[10:]
        elif command=='quit':interface=None
        if command.startswith('port trunk permit vlan ') and interface not in cleared:
            result.append('undo port trunk permit vlan all');cleared.add(interface)
        result.append(command)
    return result


def verify_vlan(config,parameters):
    views=configuration_views(config)
    try:
        for number in parameters.vlans:
            if f'vlan {number}' not in views and number!=1:return False
        for name in parameters.names:
            values=[line[5:] for line in views.get(f'vlan {name.vlan}',[]) if line.startswith('name ')]
            if (values[0] if len(values)==1 else f'VLAN {name.vlan:04d}' if not values else None)!=name.name:return False
        for port in parameters.ports:
            body=views.get('interface '+port.interface)
            if body is None or 'port link-mode route' in body:return False
            modes=[line[15:] for line in body if line.startswith('port link-type ')]
            if (modes[0] if len(modes)==1 else 'access' if not modes else None)!=port.mode:return False
            if port.mode=='access':
                values=[int(line[17:]) for line in body if line.startswith('port access vlan ')]
                if (values[0] if len(values)==1 else 1 if not values else None)!=port.vlan:return False
            else:
                allowed=set();lines=[line[23:] for line in body if line.startswith('port trunk permit vlan ')]
                for line in lines:allowed.update(vlan_set(line))
                if not lines:allowed={1}
                if allowed!=(set(port.allowed_vlans) if port.allowed_vlans else set(range(1,4095))):return False
                if port.native_vlan is not None:
                    values=[int(line[21:]) for line in body if line.startswith('port trunk pvid vlan ')]
                    if (values[0] if len(values)==1 else 1 if not values else None)!=port.native_vlan:return False
        for svi in parameters.svis:
            if not addressed(views.get(f'interface Vlan-interface{svi.vlan}',[]),svi.cidr):return False
    except (ValueError,IndexError):return False
    return True


def addressed(body,cidr):
    expected=IPv4Interface(cidr)
    actual=[]
    for line in body:
        match=re.fullmatch(r'ip address (\S+) (\S+)',line)
        if match:actual.append(IPv4Interface(match[1]+'/'+match[2]))
    return actual==[expected]


def verify_subinterfaces(config,subinterfaces):
    views=configuration_views(config)
    try:
        for sub in subinterfaces:
            parent=views.get('interface '+sub.parent_port);body=views.get(f'interface {sub.parent_port}.{sub.vlan_id}')
            if parent is None or 'shutdown' in parent or body is None:return False
            if f'vlan-type dot1q vid {sub.vlan_id}' not in body:return False
            if sub.ip_cidr is not None and not addressed(body,sub.ip_cidr):return False
    except ValueError:return False
    return True


def check_existing_vlans(config,parameters):
    views=configuration_views(config);known={1,*parameters.vlans}
    for view in views:
        match=re.fullmatch(r'vlan (\d+)',view)
        if match:known.add(int(match[1]))
    refs={port.vlan for port in parameters.ports if port.vlan is not None}
    refs.update(vlan for port in parameters.ports for vlan in port.allowed_vlans)
    if not refs<=known:
        raise ConsoleError('Referenced VLANs are neither requested nor observed',code='vlan_reference_unverified')
