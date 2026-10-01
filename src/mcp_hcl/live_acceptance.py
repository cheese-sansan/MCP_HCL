"""User-triggered three-router gate. No process/VM startup or boot changes."""
import json
import re
from ipaddress import ip_address,ip_interface
from mcp_hcl.console import ConsoleError
from pathlib import Path
from uuid import uuid4
from mcp_hcl.console import endpoint


def ospf_peers(text):
    peers=set();pending=None
    for line in text.splitlines():
        if 'Router ID' in line and ('Process' in line or 'with' in line): continue
        match=re.search(r'Router ID\s*[: ]\s*(\d+\.\d+\.\d+\.\d+)',line,re.I)
        if match: pending=match[1]
        if re.search(r'\bFull\b',line,re.I):
            addresses=re.findall(r'\b\d+\.\d+\.\d+\.\d+\b',line)
            if addresses: peers.add(addresses[0])
            elif pending: peers.add(pending)
    return peers


def accept_lab(deployment,project_path,topology,gui_receipt):
    if not deployment.writes_enabled: raise ValueError('Enable the live write switch explicitly after preparing the isolated lab')
    doc,bindings=deployment.bindings(project_path)
    gui=json.loads(Path(gui_receipt).read_text(encoding='utf-8-sig'))
    if (gui.get('status')!='verified' or not gui.get('project_identity_verified') or
            Path(gui.get('target_project','')).resolve()!=doc.net_path):
        raise ValueError('A verified GUI identity receipt for this exact staged project is required')
    plan=json.loads((doc.directory/'MCPArtifacts/plan.json').read_text(encoding='utf-8'))
    routers=['r1','r2','r3'];clients=[d['id'] for d in plan['devices'] if d['id'].startswith('h')]
    if set(clients)!={f'h{i}_1_{j}' for i in range(1,4) for j in (1,2)} or any(r not in bindings for r in routers): raise ValueError('Gate requires the fixed three-router/six-client plan')
    dynamic={h['device'] for h in plan['host_settings'] if h['ipv4']=='dhcp'}
    if set(clients)!=dynamic: raise ValueError('All six clients must request real DHCP addresses')
    lan={}
    for router in routers:
        candidates=[ip_interface(a['cidr']) for a in plan['addresses'] if a['device']==router and a['cidr'].startswith('10.')]
        if len(candidates)!=1 or candidates[0].network.prefixlen!=24: raise ValueError('Each router requires exactly one /24 LAN')
        lan[router]=candidates[0]
    operation=uuid4().hex;directory=deployment._directory(operation)
    configuration=deployment.run(project_path,topology)
    result={'operation_id':operation,'gui_identity_result':gui,'configuration_result':configuration,'neighbor_checks':[],
            'route_checks':[],'lease_checks':[],'ping_checks':[],'full_live_gate_passed':False,'status':'partial'}
    if not configuration.get('configuration_verified'):
        (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
    observation_error=None
    unique=False
    try:
        expected={'r1':{'192.0.2.2'},'r2':{'192.0.2.1','192.0.2.3'},'r3':{'192.0.2.2'}}
        leases=[];client_addresses={};client_gateways={}
        for router in routers:
            with deployment.session_factory(endpoint(topology,bindings[router]['device_id'])) as channel:
                neighbor=channel.exchange('display ospf peer')['output']
                routing=channel.exchange('display ip routing-table')['output']
                lease=channel.exchange('display dhcp server ip-in-use')['output']
                (directory/(router+'-observations.json')).write_text(json.dumps({'neighbors':neighbor,'routes':routing,'leases':lease},indent=2),encoding='utf-8')
                result['neighbor_checks'].append({'device':router,'passed':ospf_peers(neighbor)==expected[router]})
                remote=[a['cidr'].split('/')[0].rsplit('.',1)[0]+'.0' for a in plan['addresses'] if a['device'] in routers and a['device']!=router and a['cidr'].startswith('10.')]
                result['route_checks'].append({'device':router,'passed':all(any(n in line and re.search(r'\bOSPF\b',line,re.I) for line in routing.splitlines()) for n in remote)})
                leases+=re.findall(r'(?m)^\s*(10\.\d+\.\d+\.\d+)\s+',lease)
        for client in clients:
            with deployment.session_factory(endpoint(topology,bindings[client]['device_id'])) as channel:
                output=channel.exchange('display ip interface brief')['output']
                route=channel.exchange('display ip routing-table')['output']
                ips=set(re.findall(r'\b10\.\d+\.\d+\.\d+\b',output))
                gateways=set(re.findall(r'\b10\.\d+\.\d+\.1\b',route))
                expected_lan=lan['r'+client[1]]
                passed=(len(ips)==1 and gateways=={str(expected_lan.ip)} and next(iter(ips),None) in leases and ip_address(next(iter(ips))) in expected_lan.network)
                client_addresses[client]=next(iter(ips),None);client_gateways[client]=next(iter(gateways),None)
                result['lease_checks'].append({'device':client,'passed':passed})
        unique=len(set(client_addresses.values()))==6 and None not in client_addresses.values()
        representatives=[f'h{i}_1_1' for i in range(1,4)]
        for source in representatives:
            for destination in representatives:
                if source!=destination and client_addresses.get(destination):
                    result['ping_checks'].append(deployment.connectivity(project_path,topology,source,client_addresses[destination],5))
    except (ConsoleError,OSError,ValueError) as exc:
        observation_error=str(exc)
    result['network_gate_passed']=observation_error is None and unique and all(c['passed'] for key in ('neighbor_checks','route_checks','lease_checks') for c in result[key]) and len(result['ping_checks'])==6 and all(p['connectivity_verified'] for p in result['ping_checks'])
    if not result['network_gate_passed']:
        result['observation_error']=observation_error
        result['rollback']=[]
        for backup in reversed(configuration['backups']):
            try:
                with deployment.session_factory(endpoint(topology,bindings[backup['device']]['device_id'])) as channel:
                    result['rollback'].append(deployment._restore(channel,backup))
            except (ConsoleError,OSError,ValueError) as exc:
                result['rollback'].append({'device':backup['device'],'status':'unverified','error':str(exc),'manual_restore_command':f"configuration replace file {backup['guest_file']}"})
        result['rollback_verified']=len(result['rollback'])==len(configuration['backups']) and all(r['status']=='verified' for r in result['rollback'])
    # GUI identity is an independent prerequisite, never inferred from console output.
    result['status']='verified' if result['network_gate_passed'] else 'partial'
    result['full_live_gate_passed']=bool(result['network_gate_passed'] and configuration.get('native_channels') and gui.get('project_identity_verified'))
    result['verified_scope']='three_router_console_and_network_gate_only'
    (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
