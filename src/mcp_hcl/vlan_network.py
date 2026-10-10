"""Scoped multi-device VLAN transactions with all backups before changes."""
from __future__ import annotations
import json,re
from ipaddress import IPv4Interface
from pathlib import Path
from uuid import uuid4
from pydantic import Field,ValidationError,field_validator,model_validator
from mcp_hcl.models import StrictModel
from mcp_hcl.services import VlanId,InterfaceName,VlanPatch,VlanName,VlanPort
from mcp_hcl.console import ConsoleError
from mcp_hcl.contracts import validation_errors
from mcp_hcl.deployment import config_text
from mcp_hcl.generation import render_vlan,address,view
from mcp_hcl.gui_relay import rejected
from mcp_hcl.vlan_semantics import configuration_views,exact_vlan_commands,verify_vlan,verify_subinterfaces,check_existing_vlans


class NetworkVlan(StrictModel):
    vlan_id: VlanId
    name: str | None = Field(default=None,max_length=32,pattern=r'^[\x20-\x7e]*$')
    @model_validator(mode='after')
    def name_valid(self):
        if self.name=='':self.name=None
        if self.name is not None:VlanName(vlan=self.vlan_id,name=self.name)
        return self


class AccessPort(StrictModel):
    switch: str = Field(default='',max_length=128)
    port: InterfaceName
    vlan_id: VlanId


class Trunk(StrictModel):
    switch: str = Field(default='',max_length=128)
    port: InterfaceName
    allowed_vlans: list[VlanId] = Field(default_factory=list,max_length=4094)
    native_vlan: VlanId = 1
    encapsulation: str = 'dot1q'
    @field_validator('encapsulation')
    @classmethod
    def dot1q(cls,value):
        if value.casefold()!='dot1q':raise ValueError('Only 802.1Q is represented by this Comware transaction')
        return 'dot1q'
    @model_validator(mode='after')
    def unique_vlans(self):
        if len(set(self.allowed_vlans))!=len(self.allowed_vlans):raise ValueError('Duplicate allowed VLANs')
        return self


class RoutedVlan(StrictModel):
    router: str = Field(default='',max_length=128)
    parent_port: InterfaceName
    vlan_id: VlanId
    ip_cidr: str | None = None
    encapsulation: str = 'dot1Q'
    @field_validator('encapsulation')
    @classmethod
    def dot1q(cls,value):return Trunk.dot1q(value)
    @field_validator('ip_cidr')
    @classmethod
    def ipv4(cls,value):
        if value is None or value=='':return None
        if '/' not in value or IPv4Interface(value).version!=4:raise ValueError('Explicit IPv4 prefix required')
        parsed=IPv4Interface(value)
        if parsed.network.prefixlen<31 and parsed.ip in (parsed.network.network_address,parsed.network.broadcast_address):
            raise ValueError('Routed VLAN address is a reserved subnet endpoint')
        return str(parsed)
    @field_validator('parent_port')
    @classmethod
    def physical_parent(cls,value):
        if '.' in value or value.startswith(('Serial','NULL')):raise ValueError('A physical Ethernet parent is required')
        return value


class VlanNetworkRequest(StrictModel):
    switch: str = Field(default='',max_length=128)
    router: str = Field(default='',max_length=128)
    vlans: list[NetworkVlan] = Field(default_factory=list,max_length=4094)
    access_ports: list[AccessPort] = Field(default_factory=list,max_length=256)
    trunks: list[Trunk] = Field(default_factory=list,max_length=256)
    subinterfaces: list[RoutedVlan] = Field(default_factory=list,max_length=256)
    @model_validator(mode='after')
    def selection(self):
        if len({v.vlan_id for v in self.vlans})!=len(self.vlans):raise ValueError('Duplicate VLAN IDs')
        switches={row.switch or self.switch for row in [*self.access_ports,*self.trunks]}
        if self.switch:switches.add(self.switch)
        if self.vlans and not switches or '' in switches:raise ValueError('Each switch operation needs a target')
        if any(not (row.router or self.router) for row in self.subinterfaces):raise ValueError('Each subinterface needs a router')
        if not any((self.vlans,self.access_ports,self.trunks,self.subinterfaces)):raise ValueError('No VLAN changes requested')
        return self


def scoped_subinterfaces(before,after,subinterfaces):
    from mcp_hcl.policy import scopes
    old=scopes(before);new=scopes(after);allowed={};parents={sub.parent_port for sub in subinterfaces}
    for sub in subinterfaces:
        prefixes=['vlan-type dot1q vid ']
        if sub.ip_cidr is not None:prefixes.append('ip address ')
        allowed[f'interface {sub.parent_port}.{sub.vlan_id}']=prefixes
    for context in old.keys()|new.keys():
        changed=old.get(context,set())^new.get(context,set())
        if context and context[0] in allowed:
            if any(not line.startswith(tuple(allowed[context[0]])) or line.endswith((' sub',' secondary')) for line in changed):return False
        elif context and context[0] in {'interface '+parent for parent in parents}:
            if not changed<= {'shutdown'} or context not in new:return False
        elif changed or (context in old)!=(context in new):return False
    return True


class VlanNetwork:
    def __init__(self,policy):self.policy=policy

    def prepare(self,project_path,request):
        document,bindings=self.policy.deployment.bindings(project_path)
        plan=json.loads((document.directory/'MCPArtifacts/plan.json').read_text(encoding='utf-8'))
        devices={device['id']:device for device in plan['devices']}
        models={model['model']:model for model in self.policy.catalog.devices()['devices']}
        def target(selector):
            matches=[identifier for identifier,binding in bindings.items() if identifier==selector or binding['name']==selector]
            if len(matches)!=1:raise ValueError('Unknown or ambiguous staged VLAN target: '+selector)
            identifier=matches[0]
            if models[devices[identifier]['model']].get('control_kind','comware')!='comware':raise ValueError('VLAN target has no Comware control contract')
            return identifier
        patches={};routers={}
        switch_selectors={row.switch or request.switch for row in [*request.access_ports,*request.trunks]}
        if request.switch:switch_selectors.add(request.switch)
        for selector in switch_selectors:
            identifier=target(selector)
            if identifier in patches:continue
            patches[identifier]=VlanPatch(vlans=[v.vlan_id for v in request.vlans],
                names=[VlanName(vlan=v.vlan_id,name=v.name) for v in request.vlans if v.name is not None])
        used=set()
        for row in [*request.access_ports,*request.trunks]:
            identifier=target(row.switch or request.switch);key=(identifier,row.port)
            if key in used:raise ValueError('Duplicate access/trunk port after resolving device identity')
            used.add(key)
            patches[identifier].ports.append(VlanPort(interface=row.port,mode='trunk' if isinstance(row,Trunk) else 'access',
                vlan=None if isinstance(row,Trunk) else row.vlan_id,allowed_vlans=row.allowed_vlans if isinstance(row,Trunk) else [],
                native_vlan=row.native_vlan if isinstance(row,Trunk) else None))
        subkeys=set()
        for sub in request.subinterfaces:
            identifier=target(sub.router or request.router);key=(identifier,sub.parent_port,sub.vlan_id)
            if key in subkeys:raise ValueError('Duplicate routed VLAN after resolving device identity')
            subkeys.add(key);routers.setdefault(identifier,[]).append(sub)
        commands={}
        for identifier in patches.keys()|routers.keys():
            known=set(models[devices[identifier]['model']]['default_interfaces'])
            required={port.interface for port in patches.get(identifier,VlanPatch()).ports}|{sub.parent_port for sub in routers.get(identifier,[])}
            if not required<=known or 'NULL0' in required:raise ValueError('Requested VLAN physical interface is absent from its model')
            body=exact_vlan_commands(render_vlan(patches.get(identifier,VlanPatch())))
            for parent in sorted({sub.parent_port for sub in routers.get(identifier,[])}):body+=view('interface '+parent,['undo shutdown'])
            for sub in routers.get(identifier,[]):body+=view(f'interface {sub.parent_port}.{sub.vlan_id}',
                [f'vlan-type dot1q vid {sub.vlan_id}',*([address(sub.ip_cidr)] if sub.ip_cidr is not None else [])])
            commands[identifier]=['system-view',*body,'return']
        return document,bindings,patches,routers,commands

    def apply(self,project_path,topology,parameters,dry_run=False):
        if not dry_run and not self.policy.writes_enabled:return rejected('writes_disabled','Native VLAN changes require the live write switch')
        try:request=VlanNetworkRequest.model_validate(parameters)
        except ValidationError as exc:return {'status':'rejected','errors':validation_errors(exc),'full_live_gate_passed':False}
        document,bindings,patches,routers,commands=self.prepare(project_path,request)
        if dry_run:return {'status':'verified','verified_scope':'offline_multi_device_vlan_intent_only','commands':commands,
            'configuration_verified':False,'persistence_verified':False,'full_live_gate_passed':False}
        from mcp_hcl.policy import patch_preserves_unrequested
        operation=uuid4().hex;directory=self.policy.store.output_root/'.vlan-network-receipts'/operation;directory.mkdir(parents=True)
        result={'status':'unverified','operation_id':operation,'receipt_directory':str(directory),'devices':sorted(commands),'steps':[],
            'errors':[],'configuration_verified':False,'protocol_effect_verified':False,'persistence_verified':False,
            'protocol_persistence_verified':False,'rollback_verified':False,'protocol_rollback_verified':False,'full_live_gate_passed':False}
        channels={};identities={};backups={};dirty=[];archived={};currents={};persisted={}
        try:
            for identifier in sorted(commands):channels[identifier],identities[identifier]=self.policy.open(document,bindings[identifier],topology)
            for identifier in sorted(commands):
                def captured(record):backups[identifier]=record;dirty.append(identifier)
                backups[identifier]=self.policy.deployment._backup(channels[identifier],identifier,directory,operation,on_saved=captured)
                dirty.remove(identifier)
                result['steps'].append({'device':identifier,'stage':'backup_restore_preflight','status':'verified'})
            for identifier in sorted(commands):
                before=Path(backups[identifier]['local_file']).read_text(encoding='utf-8');views=configuration_views(before)
                patch=patches.get(identifier,VlanPatch());check_existing_vlans(before,patch)
                physical={port.interface for port in patch.ports}|{sub.parent_port for sub in routers.get(identifier,[])}
                if not physical<={name[10:] for name in views if name.startswith('interface ')}:raise ConsoleError('Physical interfaces absent from current config',code='vlan_interface_unverified')
            for identifier in sorted(commands):
                before=Path(backups[identifier]['local_file']).read_text(encoding='utf-8');dirty.append(identifier)
                for command in commands[identifier]:channels[identifier].exchange(command)
                current=config_text(channels[identifier].exchange('display current-configuration')['output'])
                patch=patches.get(identifier,VlanPatch());subs=routers.get(identifier,[])
                if not verify_vlan(current,patch) or not verify_subinterfaces(current,subs):raise ConsoleError('VLAN readback mismatch',code='vlan_effect_unverified')
                # Each set of changed contexts must belong to either the L2
                # patch or requested routed children/parent shutdown state.
                intermediate=self._without_router_changes(before,current,subs)
                if not patch_preserves_unrequested(before,intermediate,'vlan',patch) or not scoped_subinterfaces(intermediate,current,subs):
                    raise ConsoleError('VLAN operation changed unrequested configuration',code='vlan_scope_changed')
                currents[identifier]=current;result['steps'].append({'device':identifier,'stage':'configuration_readback','status':'verified'})
            for identifier in sorted(commands):persisted[identifier]=self.policy.deployment.startup.persist(channels[identifier],backups[identifier]['startup'],currents[identifier],f'flash:/mcp_{operation}_{identifier}_after.cfg')
            native=self.policy.native_dependencies and all(getattr(channel,'native_channel',False) for channel in channels.values())
            result.update(status='verified' if native else 'output_received',configuration_verified=native,persistence_verified=native,
                protocol_effect_verified=True,protocol_persistence_verified=True,persistence=persisted,
                verified_scope='bound_native_multi_device_vlan_configuration_only' if native else 'synthetic_multi_device_vlan_transaction_only')
        except (ConsoleError,OSError,ValueError) as exc:
            result['errors']=[exc.as_error() if isinstance(exc,ConsoleError) else {'code':'vlan_transaction_failed','message':str(exc)}]
            rollback=[]
            for identifier in reversed(dirty):
                try:
                    archived[identifier]=list(getattr(channels[identifier],'history',[]));channels[identifier].close()
                    channels[identifier],_=self.policy.open(document,bindings[identifier],topology,identities[identifier]['vm_uuid'])
                    rollback.append(self.policy.deployment._restore(channels[identifier],backups[identifier]))
                except (ConsoleError,OSError,ValueError) as recovery:rollback.append({'device':identifier,'status':'unverified','error':recovery.as_error() if isinstance(recovery,ConsoleError) else str(recovery),
                    'running_snapshot':backups[identifier]['local_file'],'startup_snapshot':backups[identifier].get('startup')})
            restored=bool(dirty) and len(rollback)==len(dirty) and all(row.get('protocol_rollback_verified') for row in rollback)
            result.update(rollback=rollback,protocol_rollback_verified=restored,rollback_verified=restored and self.policy.native_dependencies)
        finally:
            result['backups']=list(backups.values())
            for identifier,channel in channels.items():
                (directory/f'{identifier}-transcript.json').write_text(json.dumps(archived.get(identifier,[])+getattr(channel,'history',[]),indent=2),encoding='utf-8');channel.close()
            (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result

    @staticmethod
    def _without_router_changes(before,after,subinterfaces):
        old=configuration_views(before);new=configuration_views(after)
        for sub in subinterfaces:
            child=f'interface {sub.parent_port}.{sub.vlan_id}'
            if child in old:new[child]=old[child]
            else:new.pop(child,None)
        for parent in {sub.parent_port for sub in subinterfaces}:
            key='interface '+parent
            if key in new:
                new[key]=[line for line in new[key] if line!='shutdown']+(['shutdown'] if 'shutdown' in old.get(key,[]) else [])
        return '\n'.join(['#',*[line for name,body in new.items() for line in [name,*[' '+line for line in body],'#']],'return',''])
