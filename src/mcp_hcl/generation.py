"""Offline Comware command templates; no console, backend or GUI operations."""
from __future__ import annotations
from ipaddress import ip_interface, ip_network
from mcp_hcl.topology import validate_plan, TopologyPlan
from mcp_hcl.command_reference import feature_evidence


def view(name, commands):
    return [name, *commands, 'quit']


def address(cidr):
    ip=ip_interface(cidr)
    return f'ip address {ip.ip} {ip.netmask}' if ip.version==4 else f'ipv6 address {ip}'


def render_dhcp(p):
    lines=['dhcp enable']
    if p.mode=='relay':
        return lines+view(f'interface {p.interface}', ['dhcp select relay', *[f'dhcp relay server-address {s}' for s in p.servers]])
    n=ip_network(p.network)
    for r in p.excluded: lines.append(f'dhcp server forbidden-ip {r.start} {r.end}')
    commands=[f'network {n.network_address} mask {n.netmask}', f'gateway-list {p.gateway}']
    if p.dns: commands.append('dns-list '+' '.join(p.dns))
    lines+=view(f'dhcp server ip-pool {p.pool}', commands)
    return lines+view(f'interface {p.interface}', ['dhcp select server', f'dhcp server apply ip-pool {p.pool}'])


def render_ospf(p):
    commands=[]
    for area in sorted({a.area for a in p.networks}):
        statements=[]
        for item in p.networks:
            if item.area==area:
                n=ip_network(item.network);statements.append(f'network {n.network_address} {n.hostmask}')
        commands+=view(f'area {area}', statements)
    commands.extend(f'silent-interface {i}' for i in p.passive_interfaces)
    return view(f'ospf {p.process_id} router-id {p.router_id}',commands)


def render_rip(p):
    return view(f'rip {p.process_id}', [f'version {p.version}',
                *[f'network {ip_network(n).network_address}' for n in p.networks],
                *[f'silent-interface {i}' for i in p.passive_interfaces]])


def render_vlan(p):
    lines=[]
    for vlan in sorted(p.vlans): lines+=view(f'vlan {vlan}',[])
    for port in p.ports:
        commands=[f'port link-type {port.mode}']
        commands.append(f'port access vlan {port.vlan}' if port.mode=='access' else 'port trunk permit vlan '+' '.join(map(str,sorted(port.allowed_vlans))))
        lines+=view(f'interface {port.interface}',commands)
    for svi in p.svis: lines+=view(f'interface Vlan-interface{svi.vlan}',[address(svi.cidr)])
    return lines


def acl_match(prefix,cidr):
    if cidr is None: return f'{prefix} any'
    n=ip_network(cidr); return f'{prefix} {n.network_address} {n.hostmask}'


def render_acl(p):
    commands=[]
    for rule in sorted(p.rules,key=lambda r:r.id):
        fields=[f'rule {rule.id}',rule.action]
        if p.number>=3000: fields.append(rule.protocol)
        fields.append(acl_match('source',rule.source))
        if rule.source_port is not None: fields.append(f'source-port eq {rule.source_port}')
        if p.number>=3000: fields.append(acl_match('destination',rule.destination))
        if rule.destination_port is not None: fields.append(f'destination-port eq {rule.destination_port}')
        commands.append(' '.join(fields))
    lines=view(f'acl number {p.number}',commands)
    for b in p.bindings: lines+=view(f'interface {b.interface}',[f'packet-filter {p.number} {b.direction}'])
    return lines


def render_nat(p):
    lines=[]
    for b in p.outbound: lines+=view(f'interface {b.interface}',[f'nat outbound {b.acl}'])
    for s in p.static:
        if s.protocol:
            lines+=view(f'interface {s.interface}',[f'nat server protocol {s.protocol} global {s.global_address} {s.global_port} inside {s.local_address} {s.local_port}'])
        else:
            lines.append(f'nat static outbound {s.local_address} {s.global_address}')
            lines+=view(f'interface {s.interface}',['nat static enable'])
    return lines


def render_security(p):
    lines=['ssh server enable','undo telnet server enable']
    lines+=view(f'local-user {p.username} class manage', [f'password simple {p.password}',
                'service-type ssh',f'authorization-attribute user-role level-{p.privilege}'])
    commands=['authentication-mode scheme','protocol inbound ssh']
    if p.vty_acl is not None: commands.append(f'acl {p.vty_acl} inbound')
    return lines+view(f'line vty 0 {p.vty_last}',commands)


def render_wireless(p):
    lines=view(f'wlan service-template {p.template}', [f'ssid {p.ssid}',f'vlan {p.vlan}',
               'akm mode psk','security-ie rsn','cipher-suite ccmp',
               f'preshared-key pass-phrase simple {p.psk}','service-template enable'])
    if p.mode=='ac':
        lines+=view(f'wlan ap {p.ap_name} model {p.ap_model}',
                    [f'serial-id {p.serial_id}', *view(f'radio {p.radio}',[f'service-template {p.template}'])])
    else: lines+=view(f'interface {p.radio_interface}',[f'service-template {p.template}'])
    return lines


def render_qos(p):
    match=[]
    if p.acl is not None: match.append(f'if-match acl {p.acl}')
    if p.dscp is not None: match.append(f'if-match dscp {p.dscp}')
    behavior=[]
    if p.remark_dscp is not None: behavior.append(f'remark dscp {p.remark_dscp}')
    if p.cir is not None: behavior.append(f'car cir {p.cir}')
    lines=view(f'traffic classifier {p.classifier} operator and',match)
    lines+=view(f'traffic behavior {p.behavior}',behavior)
    lines+=view(f'qos policy {p.policy}',[f'classifier {p.classifier} behavior {p.behavior}'])
    for b in p.bindings: lines+=view(f'interface {b.interface}',[f'qos apply policy {p.policy} {b.direction}'])
    return lines


def render_netstream(p):
    lines=[f'ip netstream export version {p.version}', f'ip netstream export host {p.collector} {p.port}']
    for b in p.interfaces: lines+=view(f'interface {b.interface}',[f'ip netstream {b.direction}'])
    return lines


RENDERERS={name:globals()['render_'+name] for name in ('dhcp','ospf','rip','vlan','acl','nat','security','wireless','qos','netstream')}
SERVICE_ORDER={'vlan':0,'acl':1,'dhcp':2,'ospf':3,'rip':4,'nat':5,'security':6,'wireless':7,'qos':8,'netstream':9}


def generate_configs(data,catalog):
    validated=validate_plan(data,catalog)
    if not validated.get('valid'): return validated
    plan=TopologyPlan.model_validate(validated['plan']);configs={};evidence=feature_evidence('base')
    for feature in sorted({s.feature for s in plan.services}): evidence+=feature_evidence(feature)
    for device in plan.devices:
        lines=['system-view',f'sysname {device.id}']
        for service in (s for s in plan.services if s.device==device.id and s.feature=='vlan'):
            lines+=render_vlan(service.parameters)
        for item in plan.addresses:
            if item.device==device.id: lines+=view(f'interface {item.interface}',[address(item.cidr)])
        for route in plan.routes:
            if route.device==device.id:
                network=ip_network(route.network)
                lines.append(f'ip route-static {network.network_address} {network.netmask} {route.next_hop}' if network.version==4 else
                             f'ipv6 route-static {network} {route.next_hop}')
        for service in sorted((s for s in plan.services if s.device==device.id and s.feature!='vlan'),key=lambda s:SERVICE_ORDER[s.feature]):
            lines+=RENDERERS[service.feature](service.parameters)
        lines.append('return');configs[device.id]='\n'.join(lines)+'\n'
    warnings=list(validated['warnings'])
    if any(s.feature=='security' for s in plan.services):
        warnings.append({'code':'ssh_host_key_precondition','message':'SSH requires an existing local host key; key creation is not performed by this generator.'})
    return {'status':'verified','verified_scope':'offline_documented_comware_templates_only',
            'configs':configs,'plan':plan.model_dump(mode='json'),'evidence':evidence+validated['evidence'],
            'warnings':warnings,'runtime_verified':False,'configuration_verified':False,
            'guest_boot_verified':False,'connectivity_verified':False,'full_live_gate_passed':False}


def generate_operations(data,catalog,include_configs=True):
    validated=generate_configs(data,catalog) if include_configs else validate_plan(data,catalog)
    if validated['status']!='verified': return validated
    plan=validated['plan']; operations=[]
    models={m['model']:m for m in catalog.devices()['devices']}
    devices={d['id']:d for d in plan['devices']}
    for d in plan['devices']: operations.append({'action':'create_device',**d,'power_on':False})
    for link in plan['links']:
        translated={}
        for side in ('a','b'):
            endpoint=link[side];model=models[devices[endpoint['device']]['model']]
            matches=[p for p in model.get('scene_ports',[]) if p['cli_interface']==endpoint['interface']]
            translated[side]={**endpoint,'scene_port_candidate':matches[0]['scene_port'] if len(matches)==1 else None,
                              'mapping_verified':False}
        operations.append({'action':'create_link','medium':link['medium'],**translated})
    if include_configs:
        operations.extend({'action':'configure_device','device':d,'commands':commands.splitlines()} for d,commands in validated['configs'].items())
    return {'status':'verified','verified_scope':'offline_hcl_operation_manifest_only','schema_version':1,
            'operations':operations,'plan':plan,'executable':False,'requires':'P2/P3 adapters and mapping/GUI acceptance',
            'evidence':validated['evidence'],'warnings':validated.get('warnings',[]),'runtime_verified':False,'full_live_gate_passed':False}
