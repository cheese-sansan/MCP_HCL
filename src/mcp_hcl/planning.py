"""Deterministic HCL planner aligned with the pinned upstream template intent."""
from __future__ import annotations
from collections import deque
from copy import deepcopy
from ipaddress import IPv4Network, IPv6Network
from typing import Literal
from pydantic import Field, ValidationError, field_validator, model_validator
from mcp_hcl.models import StrictModel
from mcp_hcl.templates import TEMPLATES
from mcp_hcl.topology import TopologyPlan, validate_plan
from mcp_hcl.contracts import validation_errors


class WirelessSettings(StrictModel):
    ssid: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,32}$')
    security: Literal['open','wpa2_psk'] = 'wpa2_psk'
    psk: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.@:+/!=-]{8,63}$')
    hardware_model: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,63}$')
    serial_ids: list[str] = Field(min_length=1, max_length=20)
    vlan: int = Field(default=10, ge=1, le=4094)

    @model_validator(mode='after')
    def security_parameters(self):
        if (self.security=='wpa2_psk') != (self.psk is not None):
            raise ValueError('WPA2-PSK requires a key; open security forbids a key')
        return self


class TopologyRequest(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(default='HCL Lab', min_length=1, max_length=64)
    template: Literal['single_lan','multi_lan','multi_lan_wan','star','hub_spoke','branch_office','router_on_a_stick','three_router_triangle','custom'] = 'multi_lan'
    routers: int | None = Field(default=None, ge=1, le=20)
    switches_per_router: int | None = Field(default=None, ge=0, le=4)
    pcs_per_lan: int = Field(default=0, ge=0, le=64)
    laptops_per_lan: int = Field(default=0, ge=0, le=64)
    servers: int = Field(default=0, ge=0, le=32)
    access_points: int = Field(default=0, ge=0, le=20)
    has_wan: bool = False
    router_model: str = 'MSR36-20'
    switch_model: str = 'S5820V2-54QS-GE'
    host_model: str = 'PC'
    laptop_model: str | None = None
    server_model: str | None = None
    wan_model: str | None = None
    ap_model: str | None = None
    ac_model: str | None = None
    wireless_laptops: bool = False
    wireless_clients_per_lan: int = Field(default=0, ge=0, le=64)
    wireless_client_model: str | None = None
    wireless_settings: WirelessSettings | None = None
    lan_pool: str = '10.0.0.0/16'
    transit_pool: str = '172.16.0.0/16'
    routing: Literal['static','ospf','rip','none'] = 'static'
    ospf_process_id: int = Field(default=1, ge=1, le=65535)
    floating_routes: bool = False
    dhcp: bool = False
    dual_stack: bool = False
    ipv6_base: str = '2001:db8::/32'
    vlans: int = Field(default=2, ge=1, le=64)
    custom_plan: dict | None = None

    @field_validator('lan_pool','transit_pool')
    @classmethod
    def network(cls,value): return str(IPv4Network(value,strict=True))

    @field_validator('ipv6_base')
    @classmethod
    def ipv6_network(cls,value):
        network = IPv6Network(value, strict=True)
        if network.prefixlen > 64: raise ValueError('IPv6 base must allocate /64 subnets')
        return str(network)

    @model_validator(mode='after')
    def relationships(self):
        if self.template == 'custom':
            if self.custom_plan is None: raise ValueError('custom requires custom_plan')
            if self.model_fields_set - {'schema_version','name','template','custom_plan'}:
                raise ValueError('custom accepts only its explicit plan, not automatic planning parameters')
        elif self.custom_plan is not None: raise ValueError('custom_plan belongs to the custom template')
        if self.floating_routes and (self.routing != 'static' or self.template != 'three_router_triangle'):
            raise ValueError('Floating routes require static routing and the redundant triangle template')
        if self.wireless_laptops and (not self.laptops_per_lan or not self.access_points):
            raise ValueError('Wireless laptops require laptops and access points')
        if self.wireless_clients_per_lan:
            if self.wireless_laptops: raise ValueError('Wireless client and laptop groups cannot overlap')
            if not self.wireless_client_model or not self.access_points or not self.dhcp:
                raise ValueError('Native wireless clients require explicit model, APs and DHCP')
            if self.dual_stack: raise ValueError('Native wireless client IPv6 capability is unverified')
        elif self.wireless_client_model is not None:
            raise ValueError('wireless_client_model requires a nonzero client group')
        if self.access_points and (not self.ap_model or not self.ac_model or not self.wireless_settings):
            raise ValueError('Wireless requires explicit AC/AP models, SSID/PSK and observed AP serial IDs')
        if self.wireless_settings and len(self.wireless_settings.serial_ids) != self.access_points:
            raise ValueError('Each AP needs its own serial ID')
        return self


def rejection(code,message):
    return {'status':'rejected','valid':False,'errors':[{'code':code,'message':message}],
            'runtime_verified':False,'full_live_gate_passed':False}


def plan_topology(data,catalog):
    try: request=TopologyRequest.model_validate(data)
    except ValidationError as exc: return {'status':'rejected','valid':False,'errors':validation_errors(exc)}
    if request.template == 'custom': return validate_plan(deepcopy(request.custom_plan),catalog)
    defaults={'single_lan':1,'star':1,'router_on_a_stick':1,'three_router_triangle':3,'hub_spoke':4,'branch_office':3,'multi_lan_wan':3}
    nrouters=request.routers if request.routers is not None else defaults.get(request.template,2)
    nswitches=request.switches_per_router if request.switches_per_router is not None else (3 if request.template=='star' else 1)
    spec=next(t for t in TEMPLATES if t['key']==request.template)
    if not spec['min_routers']<=nrouters<=spec['max_routers']: return rejection('template_router_count','Router count is incompatible with template')
    if request.template=='router_on_a_stick' and nswitches!=1: return rejection('template_switch_count','Single-arm routing requires exactly one switch')
    wan=request.has_wan or request.template in {'branch_office','multi_lan_wan'}
    for required,model,category in [(wan,request.wan_model,'WAN provider'),(request.servers,request.server_model,'server'),
                                    (request.laptops_per_lan,request.laptop_model,'laptop')]:
        if required and not model: return rejection('explicit_model_required',f'{category} requires a documented HCL model; no substitution is made')
    if (request.pcs_per_lan or request.laptops_per_lan or request.servers or request.access_points or request.wireless_clients_per_lan) and not nswitches:
        return rejection('missing_access_switch','Endpoints require an access switch')
    models={m['model']:m for m in catalog.devices()['devices']}
    if request.wireless_clients_per_lan:
        model=models.get(request.wireless_client_model,{})
        if model.get('control_kind')!='native_gui' or not model.get('native_interfaces'):
            return rejection('wireless_evidence_missing','Explicit native terminal model/radio evidence is missing')
        if request.wireless_settings.security not in model.get('capabilities',{}).get('wireless_security',[]):
            return rejection('wireless_security_unverified','Native terminal security association is unverified; no downgrade is made')
        if request.access_points != nrouters*nswitches or request.template=='router_on_a_stick' or request.wireless_settings.vlan==1:
            return rejection('wireless_layout_unverified','Native clients require one AP per LAN and separate management/business VLANs')
    if request.access_points:
        for model in (request.ap_model,request.ac_model,request.laptop_model if request.wireless_laptops else request.ap_model):
            if model not in models or not models[model]['default_interfaces']:
                return rejection('wireless_evidence_missing','Wireless model CLI defaults are missing; collect real model profiles before accepting this plan')
    count=nrouters*(1+nswitches*(1+request.pcs_per_lan+request.laptops_per_lan+request.wireless_clients_per_lan))+request.servers+request.access_points+(1 if request.access_points else 0)+(1 if wan else 0)
    if count>256: return rejection('device_limit','Plan exceeds 256 devices')
    if request.access_points>nrouters*nswitches: return rejection('ap_count','At most one AP is allocated per LAN')
    lan=IPv4Network(request.lan_pool);transit=IPv4Network(request.transit_pool)
    if lan.overlaps(transit) or lan.prefixlen>24 or transit.prefixlen>30: return rejection('invalid_address_pools','Pools overlap or cannot allocate LAN/transit subnets')
    plan={'schema_version':1,'name':request.name,'devices':[],'links':[],'addresses':[],'routes':[],'services':[],
          'annotations':[],'host_settings':[],'subinterfaces':[],'ipv6_ra':[]}
    ports={};graph={};lans=[];lan_ranges=iter(lan.subnets(new_prefix=24));transit_ranges=iter(transit.subnets(new_prefix=30))
    ipv6_ranges=iter(IPv6Network(request.ipv6_base).subnets(new_prefix=64))
    wireless_index=0

    def add(identifier,model,x,y):
        if model not in models: raise ValueError(f'Unknown installed model: {model}')
        interfaces=[i for i in models[model]['default_interfaces'] if i.startswith(('GigabitEthernet','Ten-GigabitEthernet'))]
        if not interfaces: raise ValueError(f'No evidence-backed Ethernet interfaces for {model}')
        plan['devices'].append({'id':identifier,'name':identifier,'model':model,'x':float(x),'y':float(y)})
        ports[identifier]=deque(interfaces)

    def connect(a,b):
        if not ports[a] or not ports[b]: raise ValueError(f'Insufficient free ports: {a}/{b}')
        pa,pb=ports[a].popleft(),ports[b].popleft()
        plan['links'].append({'a':{'device':a,'interface':pa},'b':{'device':b,'interface':pb},'medium':'ethernet'})
        return pa,pb

    def assign(device,interface,ip,prefix): plan['addresses'].append({'device':device,'interface':interface,'cidr':f'{ip}/{prefix}'})

    def transit_link(a,b):
        pa,pb=connect(a,b);network=next(transit_ranges);ia,ib=str(network.network_address+1),str(network.network_address+2)
        assign(a,pa,ia,30);assign(b,pb,ib,30);graph.setdefault(a,{})[b]=ib;graph.setdefault(b,{})[a]=ia
        if request.dual_stack:
            v6=next(ipv6_ranges);assign(a,pa,v6.network_address+1,64);assign(b,pb,v6.network_address+2,64)

    def client(identifier,model,switch,network,gateway,v6,index,x,y,wireless=False):
        native=models[model].get('control_kind')=='native_gui'
        if native:
            plan['devices'].append({'id':identifier,'name':identifier,'model':model,'x':float(x),'y':float(y)})
        else: add(identifier,model,x,y)
        if wireless:
            radio=models[model].get('native_interfaces',[]) if native else [i for i in models[model]['default_interfaces'] if i.startswith(('WLAN','Wireless'))]
            if not radio: raise ValueError('Wireless client has no observed radio interface')
            interface=radio[0]
            plan.setdefault('wireless_associations',[]).append({'device':identifier,'interface':interface,'ssid':request.wireless_settings.ssid,'ap':f'ap{wireless_index}', 'security':request.wireless_settings.security})
        else: _,interface=connect(switch,identifier)
        setting={'device':identifier,'interface':interface,'ipv4':'dhcp' if request.dhcp else 'static','ipv6':'slaac' if v6 else 'none'}
        if not request.dhcp:
            assign(identifier,interface,network.network_address+index,24)
            plan['routes'].append({'device':identifier,'network':'0.0.0.0/0','next_hop':gateway})
        plan['host_settings'].append(setting)

    try:
        for i in range(nrouters): add(f'r{i+1}',request.router_model,i*350,0);graph[f'r{i+1}']={}
        if request.template in {'hub_spoke','branch_office'}: edges=[(0,i) for i in range(1,nrouters)]
        elif request.template=='three_router_triangle': edges=[(0,1),(1,2),(2,0)]
        else: edges=[(i,i+1) for i in range(nrouters-1)]
        if request.template!='branch_office':
            for a,b in edges: transit_link(f'r{a+1}',f'r{b+1}')
        if wan:
            add('wan',request.wan_model,0,-180);graph['wan']={}
            for router in (list(graph)[:-1] if request.template=='branch_office' else ['r1']): transit_link(router,'wan')
        if request.access_points: add('ac1',request.ac_model,0,500)
        for i in range(nrouters):
            router=f'r{i+1}'
            for j in range(nswitches):
                switch=f's{i+1}_{j+1}';add(switch,request.switch_model,i*350+j*80,180)
                physical,switch_uplink=connect(router,switch)
                groups=request.vlans if request.template=='router_on_a_stick' else 1
                vlan_ids=list(range(10,10+groups))
                if request.template=='router_on_a_stick':
                    plan['services'].append({'device':switch,'feature':'vlan','parameters':{'vlans':vlan_ids,'ports':[{'interface':switch_uplink,'mode':'trunk','allowed_vlans':vlan_ids}]}})
                for group in range(groups):
                    network=next(lan_ranges);gateway=str(network.network_address+1);interface=physical
                    native_wireless=bool(request.wireless_clients_per_lan)
                    if native_wireless:
                        plan['subinterfaces'].append({'device':router,'parent':physical,'vlan':1});interface=f'{physical}.1'
                    if groups>1 or request.template=='router_on_a_stick':
                        plan['subinterfaces'].append({'device':router,'parent':physical,'vlan':vlan_ids[group]});interface=f'{physical}.{vlan_ids[group]}'
                    assign(router,interface,gateway,24);lans.append((router,str(network)))
                    v6=next(ipv6_ranges) if request.dual_stack else None
                    if v6: assign(router,interface,v6.network_address+1,64);plan['ipv6_ra'].append({'device':router,'interface':interface})
                    if request.dhcp: plan['services'].append({'device':router,'feature':'dhcp','parameters':{'mode':'server','interface':interface,'pool':f'{switch}_{group}','network':str(network),'gateway':gateway,'excluded':[{'start':gateway,'end':gateway}]}})
                    members=[('h',request.host_model,k) for k in range(request.pcs_per_lan) if k%groups==group]
                    members += [('l',request.laptop_model,k) for k in range(request.laptops_per_lan) if k%groups==group]
                    if i==0 and j==0: members += [('srv',request.server_model,k) for k in range(request.servers) if k%groups==group]
                    if request.access_points and wireless_index<request.access_points and group==0:
                        wireless_index+=1;ap=f'ap{wireless_index}';add(ap,request.ap_model,i*350,450);ap_switch_port,_=connect(switch,ap)
                        ac_switch_port=None
                        if wireless_index==1: ac_switch_port,_=connect(switch,'ac1')
                        settings=request.wireless_settings
                        plan['services'].append({'device':'ac1','feature':'wireless','parameters':{'mode':'ac','template':f'wifi{wireless_index}','ssid':settings.ssid,'vlan':settings.vlan,'security':settings.security,'psk':settings.psk,'ap_device':ap,'ap_name':ap,'ap_model':settings.hardware_model,'serial_id':settings.serial_ids[wireless_index-1],'radio':1}})
                        if native_wireless:
                            business=next(lan_ranges);business_gateway=str(business.network_address+1)
                            plan['subinterfaces'].append({'device':router,'parent':physical,'vlan':settings.vlan})
                            business_interface=f'{physical}.{settings.vlan}'
                            assign(router,business_interface,business_gateway,24);lans.append((router,str(business)))
                            plan['services'].append({'device':router,'feature':'dhcp','parameters':{'mode':'server','interface':business_interface,'pool':f'{switch}_wifi','network':str(business),'gateway':business_gateway,'excluded':[{'start':business_gateway,'end':business_gateway}]}})
                            trunk_ports=[switch_uplink,ap_switch_port]+([ac_switch_port] if ac_switch_port else [])
                            plan['services'].append({'device':switch,'feature':'vlan','parameters':{'vlans':[1,settings.vlan],'ports':[{'interface':p,'mode':'trunk','allowed_vlans':[1,settings.vlan]} for p in trunk_ports]}})
                            plan['services'].append({'device':ap,'feature':'vlan','parameters':{'vlans':[1],'svis':[{'vlan':1,'cidr':f'{network.network_address+200}/24'}]}})
                            if wireless_index==1:
                                plan['services'].append({'device':'ac1','feature':'vlan','parameters':{'vlans':[1,settings.vlan],'svis':[{'vlan':1,'cidr':f'{network.network_address+201}/24'}]}})
                            for k in range(request.wireless_clients_per_lan):
                                client(f'w{i+1}_{j+1}_{k+1}',request.wireless_client_model,switch,business,business_gateway,None,k+2,i*350+k*55,580,True)
                    for index,(kind,model,k) in enumerate(members,2):
                        identifier=f'{kind}{i+1}_{j+1}_{k+1}';client(identifier,model,switch,network,gateway,v6,index,i*350+k*55,350+j*120,kind=='l' and request.wireless_laptops)
                        if request.template=='router_on_a_stick':
                            port=plan['links'][-1]['a']['interface']
                            next(s for s in plan['services'] if s['device']==switch and s['feature']=='vlan')['parameters']['ports'].append({'interface':port,'mode':'access','vlan':vlan_ids[group]})
        if request.access_points and not request.wireless_clients_per_lan: plan['services'].append({'device':'ac1','feature':'vlan','parameters':{'vlans':[request.wireless_settings.vlan]}})
        if request.wireless_clients_per_lan:
            # Exclude all explicitly assigned management addresses, including SVI intent.
            for service in plan['services']:
                if service['feature']=='dhcp':
                    pool=IPv4Network(service['parameters']['network'])
                    for vlan in (s for s in plan['services'] if s['feature']=='vlan'):
                        for svi in vlan['parameters'].get('svis',[]):
                            ip=__import__('ipaddress').ip_interface(svi['cidr']).ip
                            if ip in pool: service['parameters']['excluded'].append({'start':str(ip),'end':str(ip)})
        for origin in graph:
            if request.routing=='static':
                for target,network in lans:
                    if origin==target: continue
                    for banned,preference in [(None,60)]+([(None,254)] if request.floating_routes else []):
                        queue=deque([(origin,None)]);visited={origin};hop=None
                        if preference==254:
                            first=next((r for r in plan['routes'] if r['device']==origin and r['network']==network and r.get('preference',60)==60),None)
                            blocked=next((n for n,ip in graph[origin].items() if first and ip==first['next_hop']),None)
                        else: blocked=None
                        while queue:
                            node,first_hop=queue.popleft()
                            if node==target: hop=first_hop;break
                            for neighbor in graph[node]:
                                if node==origin and neighbor==blocked: continue
                                if neighbor not in visited: visited.add(neighbor);queue.append((neighbor,first_hop or neighbor))
                        if hop: plan['routes'].append({'device':origin,'network':network,'next_hop':graph[origin][hop],'preference':preference})
            elif request.routing in {'ospf','rip'}:
                addresses=[a for a in plan['addresses'] if a['device']==origin and ':' not in a['cidr']]
                if not addresses: continue
                if request.routing=='ospf': parameters={'process_id':request.ospf_process_id,'router_id':f'192.0.2.{list(graph).index(origin)+1}','networks':[{'network':n,'area':0} for n in sorted({str(IPv4Network(a['cidr'],strict=False)) for a in addresses})]}
                else: parameters={'version':2,'networks':sorted({str(IPv4Network(a['cidr'].split('/')[0]+'/'+str(8 if int(a['cidr'].split('.')[0])<128 else 16 if int(a['cidr'].split('.')[0])<192 else 24),strict=False)) for a in addresses})}
                plan['services'].append({'device':origin,'feature':request.routing,'parameters':parameters})
    except (ValueError,StopIteration) as exc: return rejection('planning_failed',str(exc) or 'Address pool exhausted')
    result=validate_plan(plan,catalog);result['request']=request.model_dump(mode='json');return result

def estimate_plan(request,catalog):
    result=plan_topology(request,catalog)
    if not result.get('valid'): return result
    plan=result['plan']
    return {'status':'verified','verified_scope':'offline_plan_counts_only',
            'estimate':{'devices':len(plan['devices']),'links':len(plan['links']),
                        'addresses':len(plan['addresses']),'routes':len(plan['routes']), 'services':len(plan['services'])},
            'evidence':result['evidence'],'warnings':result['warnings'],'runtime_verified':False}


def explain_plan(data,catalog):
    result=validate_plan(data,catalog)
    if not result.get('valid'): return result
    p=result['plan']
    return {'status':'verified','verified_scope':'offline_plan_explanation_only','evidence':result['evidence'],
            'explanations':[f"{len(p['devices'])} devices use locally discovered model defaults.",
                            f"{len(p['links'])} links reserve one unique physical interface at each end.",
                            f"{len(p['routes'])} static routes and {len(p['services'])} service intents are offline intent.",
                            'Guest firmware, canvas activation and network reachability are unverified.']}


def fix_plan(data,catalog):
    plan=deepcopy(data);fixes=[]
    aliases=catalog.aliases()['aliases'];models={m['model']:m for m in catalog.devices()['devices']}
    try:
        for device in plan.get('devices',[]):
            old=device.get('model');new=aliases.get(str(old).lower(),old)
            if old!=new: device['model']=new;fixes.append({'kind':'model_alias','device':device.get('id'),'before':old,'after':new})
        typed=TopologyPlan.model_validate(plan)
    except ValidationError as exc:
        return {'status':'rejected','errors':validation_errors(exc),'fixes':fixes}
    devices={d.id:d for d in typed.devices};used=set()
    for link in plan.get('links',[]):
        for side in ('a','b'):
            endpoint=link[side];device=devices.get(endpoint['device'])
            if not device or device.model not in models: continue
            choices=[i for i in models[device.model]['default_interfaces'] if i!='NULL0']
            old=endpoint['interface'];serial=old.startswith('Serial')
            if old not in choices or (device.id,old) in used:
                free=[i for i in choices if i.startswith('Serial')==serial and (device.id,i) not in used]
                if free: endpoint['interface']=free[0];fixes.append({'kind':'port','device':device.id,'before':old,'after':free[0]})
            used.add((device.id,endpoint['interface']))
        a_serial=link['a']['interface'].startswith('Serial');b_serial=link['b']['interface'].startswith('Serial')
        if a_serial==b_serial:
            medium='serial' if a_serial else 'ethernet'
            if link.get('medium','ethernet')!=medium:
                fixes.append({'kind':'medium','before':link.get('medium'),'after':medium});link['medium']=medium
    result=validate_plan(plan,catalog);result['fixes']=fixes
    return result
