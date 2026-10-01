"""Deterministic offline planning, estimation, explanation and conservative repair."""
from __future__ import annotations
from collections import deque
from copy import deepcopy
from ipaddress import IPv4Network
from typing import Literal
from pydantic import Field, ValidationError, field_validator
from mcp_hcl.models import StrictModel
from mcp_hcl.templates import TEMPLATES
from mcp_hcl.topology import TopologyPlan, validate_plan
from mcp_hcl.contracts import validation_errors


class TopologyRequest(StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(default='HCL Lab', min_length=1, max_length=64)
    template: Literal['single_lan','multi_lan','star','hub_spoke','three_router_triangle'] = 'multi_lan'
    routers: int = Field(default=2, ge=1, le=20)
    switches_per_router: int = Field(default=1, ge=0, le=4)
    pcs_per_lan: int = Field(default=0, ge=0, le=64)
    router_model: str = 'MSR36-20'
    switch_model: str = 'S5820V2-54QS-GE'
    host_model: str = 'PC'
    lan_pool: str = '10.0.0.0/16'
    transit_pool: str = '172.16.0.0/16'
    routing: Literal['static','ospf','rip','none'] = 'static'
    dhcp: bool = False
    @field_validator('lan_pool','transit_pool')
    @classmethod
    def network(cls,value):
        return str(IPv4Network(value,strict=True))


def rejection(code, message):
    return {'status':'rejected','valid':False,'errors':[{'code':code,'message':message}],
            'runtime_verified':False,'full_live_gate_passed':False}


def plan_topology(data, catalog):
    try:
        request=TopologyRequest.model_validate(data)
    except ValidationError as exc:
        return {'status':'rejected','valid':False,'errors':validation_errors(exc)}
    template=next(t for t in TEMPLATES if t['key']==request.template)
    if not template['min_routers']<=request.routers<=template['max_routers']:
        return rejection('template_router_count','Router count is incompatible with this template')
    lan=IPv4Network(request.lan_pool); transit=IPv4Network(request.transit_pool)
    if lan.overlaps(transit) or lan.prefixlen>24 or transit.prefixlen>30:
        return rejection('invalid_address_pools','Pools overlap or cannot allocate /24 LAN and /30 transit networks')
    models={m['model']:m for m in catalog.devices()['devices']}
    count=request.routers*(1+request.switches_per_router*(1+request.pcs_per_lan))
    if count>256:
        return rejection('device_limit','The request exceeds the 256 device plan limit')
    if request.pcs_per_lan and not request.switches_per_router:
        return rejection('missing_access_switch','pcs_per_lan requires an access switch')
    devices=[]; links=[]; addresses=[]; routes=[]; services=[]; ports={}
    def add(identifier,model,x,y):
        if model not in models: raise ValueError(f'Unknown installed model: {model}')
        interfaces=[i for i in models[model]['default_interfaces'] if i.startswith('GigabitEthernet')]
        if not interfaces: raise ValueError(f'No evidence-backed Ethernet interfaces for {model}')
        devices.append({'id':identifier,'name':identifier,'model':model,'x':float(x),'y':float(y)})
        ports[identifier]=deque(interfaces)
    def link(a,b):
        if not ports[a] or not ports[b]: raise ValueError(f'Insufficient free ports: {a}/{b}')
        pa,pb=ports[a].popleft(),ports[b].popleft()
        links.append({'a':{'device':a,'interface':pa},'b':{'device':b,'interface':pb},'medium':'ethernet'})
        return pa,pb
    lan_networks=iter(lan.subnets(new_prefix=24)); transit_networks=iter(transit.subnets(new_prefix=30))
    graph={f'r{i+1}':{} for i in range(request.routers)}; lans=[]
    try:
        for i in range(request.routers): add(f'r{i+1}',request.router_model,i*350,0)
        if request.template in {'star','hub_spoke'}: edges=[(0,i) for i in range(1,request.routers)]
        elif request.template=='three_router_triangle': edges=[(0,1),(1,2),(2,0)]
        else: edges=[(i,i+1) for i in range(request.routers-1)]
        for a,b in edges:
            a,b=f'r{a+1}',f'r{b+1}'; pa,pb=link(a,b); network=next(transit_networks)
            ia,ib=str(network.network_address+1),str(network.network_address+2)
            addresses.extend([{'device':a,'interface':pa,'cidr':ia+'/30'}, {'device':b,'interface':pb,'cidr':ib+'/30'}])
            graph[a][b]=ib;graph[b][a]=ia
        for i in range(request.routers):
            router=f'r{i+1}'
            for j in range(request.switches_per_router):
                switch=f's{i+1}_{j+1}';add(switch,request.switch_model,i*350+j*80,180)
                interface,_=link(router,switch); network=next(lan_networks);gateway=str(network.network_address+1)
                addresses.append({'device':router,'interface':interface,'cidr':gateway+'/24'})
                lans.append((router,str(network)))
                if request.dhcp:
                    services.append({'device':router,'feature':'dhcp','parameters':{'mode':'server','interface':interface,
                                     'pool':switch,'network':str(network),'gateway':gateway,'excluded':[{'start':gateway,'end':gateway}]}})
                for k in range(request.pcs_per_lan):
                    host=f'h{i+1}_{j+1}_{k+1}'; add(host,request.host_model,i*350+k*55,350+j*120)
                    _,port=link(switch,host)
                    addresses.append({'device':host,'interface':port,'cidr':str(network.network_address+k+2)+'/24'})
                    routes.append({'device':host,'network':'0.0.0.0/0','next_hop':gateway})
        if request.routing=='static':
            for origin in graph:
                for target,network in lans:
                    if origin==target: continue
                    queue=deque([(origin,None)]);visited={origin};hop=None
                    while queue:
                        node,first=queue.popleft()
                        if node==target: hop=first;break
                        for neighbor in graph[node]:
                            if neighbor not in visited:
                                visited.add(neighbor);queue.append((neighbor,first or neighbor))
                    if hop: routes.append({'device':origin,'network':network,'next_hop':graph[origin][hop]})
        elif request.routing in {'ospf','rip'}:
            for router in graph:
                if request.routing=='ospf':
                    networks=sorted({str(IPv4Network(a['cidr'],strict=False)) for a in addresses if a['device']==router})
                    parameters={'process_id':1,'router_id':f'192.0.2.{int(router[1:])}', 'networks':[{'network':n,'area':0} for n in networks]}
                else:
                    networks=sorted({str(IPv4Network(a['cidr'].split('/')[0]+'/'+
                              str(8 if int(a['cidr'].split('.')[0])<128 else 16 if int(a['cidr'].split('.')[0])<192 else 24),strict=False))
                                     for a in addresses if a['device']==router})
                    parameters={'version':2,'networks':networks}
                services.append({'device':router,'feature':request.routing,'parameters':parameters})
    except (ValueError,StopIteration) as exc:
        return rejection('planning_failed',str(exc) or 'Address pool exhausted')
    plan={'schema_version':1,'name':request.name,'devices':devices,'links':links,'addresses':addresses,
          'routes':routes,'services':services,'annotations':[]}
    result=validate_plan(plan,catalog)
    result['request']=request.model_dump(mode='json')
    return result


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
