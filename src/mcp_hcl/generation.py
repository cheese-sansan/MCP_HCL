"""Offline Comware command templates; no console, backend or GUI operations."""
from __future__ import annotations
from ipaddress import ip_interface, ip_network
from ipaddress import IPv4Address
from mcp_hcl.acl_values import address_pair,ICMP_MESSAGES,PROTOCOLS
from mcp_hcl.vlan_semantics import permit_commands
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
    names={name.vlan:name.name for name in p.names}
    for vlan in sorted(p.vlans): lines+=view(f'vlan {vlan}',[] if vlan not in names else ['name '+names[vlan]])
    for port in p.ports:
        commands=[f'port link-type {port.mode}']
        commands.extend([f'port access vlan {port.vlan}'] if port.mode=='access' else permit_commands(port.allowed_vlans))
        if port.native_vlan is not None:commands.append(f'port trunk pvid vlan {port.native_vlan}')
        lines+=view(f'interface {port.interface}',commands)
    for svi in p.svis: lines+=view(f'interface Vlan-interface{svi.vlan}',[address(svi.cidr)])
    return lines


def acl_match(prefix,cidr):
    address,wildcard=address_pair(cidr)
    if wildcard==0xffffffff:return f'{prefix} any'
    return f'{prefix} {IPv4Address(address)} {IPv4Address(wildcard)}'


def render_acl(p,*,rules=None):
    if rules is None:
        from mcp_hcl.acl_semantics import effective_acl_parameters
        rules=effective_acl_parameters(p).rules
    commands=[]
    for rule in sorted(rules,key=lambda r:r.id):
        fields=[f'rule {rule.id}',rule.action]
        if p.kind=='advanced': fields.append(str(PROTOCOLS[rule.protocol] if rule.protocol in {'ah','ahp','eigrp','esp'} else rule.protocol))
        fields.append(acl_match('source',rule.source))
        if rule.source_port is not None: fields.append(f'source-port eq {rule.source_port}')
        if rule.source_port_match is not None:
            match=rule.source_port_match
            fields.append(f'source-port {match.operator} {match.port}'+(f' {match.end}' if match.end is not None else ''))
        if p.kind=='advanced': fields.append(acl_match('destination',rule.destination))
        if rule.destination_port is not None: fields.append(f'destination-port eq {rule.destination_port}')
        if rule.destination_port_match is not None:
            match=rule.destination_port_match
            fields.append(f'destination-port {match.operator} {match.port}'+(f' {match.end}' if match.end is not None else ''))
        if rule.icmp is not None:
            kind,code=ICMP_MESSAGES[rule.icmp] if isinstance(rule.icmp,str) else (rule.icmp.type,rule.icmp.code)
            fields.append(f'icmp-type {kind}'+(f' {code}' if code is not None else ''))
        fields.extend('established' if flag=='established' else f'{flag} 1' for flag in sorted(rule.tcp_flags))
        if rule.log:fields.append('logging')
        commands.append(' '.join(fields))
        if rule.remark is not None:commands.append(f'rule {rule.id} comment {rule.remark}')
    lines=view(p.view,commands)
    for b in p.bindings: lines+=view(f'interface {b.interface}',[f'packet-filter {p.reference} {b.direction}'])
    return lines


def render_nat(p):
    lines=[]
    for group in p.address_groups:
        first=int(IPv4Address(group.start));last=int(IPv4Address(group.end));members=[]
        for start in range(first,last+1,256):members.append(f'address {IPv4Address(start)} {IPv4Address(min(start+255,last))}')
        lines+=view(f'nat address-group {group.id}',members)
    for b in p.outbound:
        reference=str(b.acl) if b.acl is not None else 'name '+b.acl_name
        command='nat outbound '+reference
        if b.address_group is not None:command+=f' address-group {b.address_group}'
        if not b.pat:command+=' no-pat'
        lines+=view(f'interface {b.interface}',[command])
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
    security=['akm mode psk','security-ie rsn','cipher-suite ccmp',f'preshared-key pass-phrase simple {p.psk}'] if p.security=='wpa2_psk' else []
    lines=view(f'wlan service-template {p.template}', [f'ssid {p.ssid}',f'vlan {p.vlan}',*security,'service-template enable'])
    if p.mode=='ac':
        lines+=view(f'wlan ap {p.ap_name} model {p.ap_model}',
                    [f'serial-id {p.serial_id}', *view(f'radio {p.radio}',['radio enable',f'service-template {p.template}'])])
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
    # A per-device configuration bundle may intentionally describe isolated
    # devices; complete graph validation belongs to hcl_validate_plan/planning.
    validated=validate_plan(data,catalog,validation_level='configuration')
    if not validated.get('valid'): return validated
    if validated['plan']['wireless_associations']:
        return {'status': 'rejected', 'errors': [{'code': 'wireless_client_commands_unverified',
                'message': 'Native terminal association serialization has no independently accepted profile; CLI substitution and security downgrade are forbidden'}],
                'runtime_verified': False, 'full_live_gate_passed': False}
    models={row['model']:row for row in catalog.devices()['devices']}
    if any(models[d['model']].get('control_kind')=='native_gui' for d in validated['plan']['devices']):
        return {'status':'rejected','errors':[{'code':'native_terminal_settings_unverified','message':'Native GUI terminal serialization is unverified; no Comware commands will be generated'}], 'runtime_verified':False}
    plan=TopologyPlan.model_validate(validated['plan']);configs={};evidence=feature_evidence('base')
    for feature in sorted({s.feature for s in plan.services}): evidence+=feature_evidence(feature)
    for device in plan.devices:
        lines=['system-view',f'sysname {device.id}']
        for sub in plan.subinterfaces:
            if sub.device == device.id:
                lines += view(f'interface {sub.interface}', [f'vlan-type dot1q vid {sub.vlan}'])
        for service in (s for s in plan.services if s.device==device.id and s.feature=='vlan'):
            lines+=render_vlan(service.parameters)
        for item in plan.addresses:
            if item.device==device.id: lines+=view(f'interface {item.interface}',[address(item.cidr)])
        for host in plan.host_settings:
            if host.device == device.id:
                commands = []
                if host.ipv4 == 'dhcp': commands.append('ip address dhcp-alloc')
                if host.ipv6 == 'slaac': commands.append('ipv6 address auto')
                if commands: lines += view(f'interface {host.interface}', commands)
        for ra in plan.ipv6_ra:
            if ra.device == device.id:
                lines += view(f'interface {ra.interface}', ['undo ipv6 nd ra halt'])
        for route in plan.routes:
            if route.device==device.id:
                network=ip_network(route.network)
                command = (f'ip route-static {network.network_address} {network.netmask} {route.next_hop}' if network.version==4 else
                           f'ipv6 route-static {network} {route.next_hop}')
                if route.preference != 60: command += f' preference {route.preference}'
                lines.append(command)
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
    validated=generate_configs(data,catalog) if include_configs else validate_plan(data,catalog,validation_level='configuration')
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
    operations.extend({'action':'add_annotation', **annotation} for annotation in plan['annotations'])
    operations.extend({'action':'associate_wireless_terminal', **association, 'executable':False,
                       'serialization_verified':False} for association in plan['wireless_associations'])
    if include_configs:
        operations.extend({'action':'configure_device','device':d,'commands':commands.splitlines()} for d,commands in validated['configs'].items())
    return {'status':'verified','verified_scope':'offline_hcl_operation_manifest_only','schema_version':1,
            'operations':operations,'plan':plan,'executable':False,'file_executor':'hcl_stage_plan',
            'requires':'Source project and explicit port map for file staging; P2/P3 adapters and GUI acceptance for live execution',
            'evidence':validated['evidence'],'warnings':validated.get('warnings',[]),'runtime_verified':False,'full_live_gate_passed':False}
