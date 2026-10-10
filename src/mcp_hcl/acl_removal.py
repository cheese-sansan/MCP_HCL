"""Scoped numbered/named ACL removal with verified persistence and recovery."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field,ValidationError,model_validator,field_validator
from mcp_hcl.models import StrictModel
from mcp_hcl.services import AclId,InterfaceName
from mcp_hcl.acl_semantics import configuration_acls,ipv4_binding
from mcp_hcl.deployment import config_text
from mcp_hcl.console import ConsoleError
from mcp_hcl.contracts import validation_errors
from mcp_hcl.gui_relay import rejected


class AclRemoval(StrictModel):
    number: AclId | None = None
    name: str | None = Field(default=None,pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,62}$')
    acl_type: Literal['basic','advanced'] | None = None
    binding_interface: InterfaceName | None = None
    binding_direction: Literal['inbound','outbound'] = 'inbound'
    @field_validator('binding_interface',mode='before')
    @classmethod
    def absent_interface(cls,value):return None if value=='' else value
    @model_validator(mode='after')
    def identity(self):
        if (self.number is None)==(self.name is None):raise ValueError('Supply exactly one ACL number or name')
        if self.name is not None:
            self.name=self.name.casefold()
            if self.name=='all':raise ValueError('ACL name all is reserved')
        if self.number is not None and self.acl_type is not None and self.acl_type!=self.kind:raise ValueError('ACL type conflicts with its numeric range')
        return self
    @property
    def kind(self):return ('basic' if self.number<3000 else 'advanced') if self.number is not None else self.acl_type
    @property
    def reference(self):return str(self.number) if self.number is not None else 'name '+self.name


def matches(header,parameters):
    return (header['number']==parameters.number if parameters.number is not None else header['name']==parameters.name) and (
        parameters.kind is None or parameters.kind==header['type'])


def removal_intent(parameters,baseline=None):
    from mcp_hcl.policy import scopes
    header=None;refs={parameters.reference};bindings=[]
    if baseline is not None:
        targets=[entry['header'] for entry in configuration_acls(baseline) if matches(entry['header'],parameters)]
        if len(targets)>1:raise ValueError('ACL identity is ambiguous in current configuration')
        header=targets[0] if targets else None
        if header is not None:
            if header['number'] is not None:refs.add(str(header['number']))
            if header['name'] is not None:refs.add('name '+header['name'])
        if parameters.binding_interface is not None:
            context=('interface '+parameters.binding_interface,);views=scopes(baseline)
            if context not in views:raise ValueError('Requested ACL binding interface is absent')
            for line in views[context]:
                binding=ipv4_binding(line)
                if binding is not None and binding[0] in refs and binding[1]==parameters.binding_direction:bindings.append(binding[0])
    elif parameters.binding_interface is not None:bindings=[parameters.reference]
    kind=header['type'] if header is not None else parameters.kind
    if kind is None and baseline is None:return None,None
    commands=['system-view']
    if bindings:
        commands+=['interface '+parameters.binding_interface,*[f'undo packet-filter {reference} {parameters.binding_direction}' for reference in sorted(set(bindings))],'quit']
    if baseline is None or header is not None:commands.append(f'undo acl {kind} {parameters.reference}')
    return [*commands,'return'],header


def removal_verified(before,after,parameters,header):
    from mcp_hcl.policy import scopes
    for entry in configuration_acls(after):
        candidate=entry['header']
        if matches(candidate,parameters) or header is not None and header['number'] is not None and candidate['number']==header['number']:return False
    old=scopes(before);new=scopes(after);target=(header['key'],) if header is not None else None
    refs={parameters.reference}
    if header is not None:
        if header['number'] is not None:refs.add(str(header['number']))
        if header['name'] is not None:refs.add('name '+header['name'])
    for context in old.keys()|new.keys():
        if context==target:
            if context in new:return False
            continue
        expected=old.get(context,set())
        if parameters.binding_interface is not None and context==('interface '+parameters.binding_interface,):
            expected={line for line in expected if not ((binding:=ipv4_binding(line)) is not None and binding[0] in refs and binding[1]==parameters.binding_direction)}
        if expected!=new.get(context,set()) or (context in old)!=(context in new):return False
    return True


class RemoveAcl:
    def __init__(self,policy):self.policy=policy
    def apply(self,project_path,topology,device,parameters,dry_run=False):
        if not dry_run and not self.policy.writes_enabled:return rejected('writes_disabled','Native ACL removal requires the live write switch')
        try:typed=AclRemoval.model_validate(parameters)
        except ValidationError as exc:return {'status':'rejected','errors':validation_errors(exc),'full_live_gate_passed':False}
        document,bindings=self.policy.deployment.bindings(project_path)
        selected=[identifier for identifier,binding in bindings.items() if identifier==device or binding['name']==device]
        if len(selected)!=1:raise ValueError('Select one exact staged ACL target')
        identifier=selected[0];binding=bindings[identifier]
        if dry_run:
            commands,_=removal_intent(typed)
            return {'status':'verified' if commands is not None else 'unverified','commands':commands,
                'requires_current_acl_type':commands is None,'verified_scope':'offline_acl_removal_intent_only',
                'configuration_verified':False,'persistence_verified':False,'full_live_gate_passed':False}
        operation=uuid4().hex;directory=self.policy.store.output_root/'.acl-removal-receipts'/operation;directory.mkdir(parents=True)
        result={'status':'unverified','operation_id':operation,'device':identifier,'receipt_directory':str(directory),'errors':[],
            'configuration_verified':False,'protocol_effect_verified':False,'persistence_verified':False,'protocol_persistence_verified':False,
            'rollback_verified':False,'protocol_rollback_verified':False,'full_live_gate_passed':False}
        channel=None;identity=None;backup=None;dirty=False;archived=[]
        try:
            channel,identity=self.policy.open(document,binding,topology);result['target_identity']=identity
            def captured(record):
                nonlocal backup,dirty
                backup=record;dirty=True
            backup=self.policy.deployment._backup(channel,identifier,directory,operation,on_saved=captured);dirty=False
            before=Path(backup['local_file']).read_text(encoding='utf-8')
            commands,header=removal_intent(typed,before);result['commands']=commands;result['matched_acl']=header;result['backup']=backup
            dirty=True
            for command in commands:channel.exchange(command)
            current=config_text(channel.exchange('display current-configuration')['output'])
            if not removal_verified(before,current,typed,header):raise ConsoleError('ACL removal or scope readback mismatch',code='acl_removal_unverified')
            native=self.policy.native_dependencies and getattr(channel,'native_channel',False)
            result['persistence']=self.policy.deployment.startup.persist(channel,backup['startup'],current,f'flash:/mcp_{operation}_{identifier}_after.cfg')
            result.update(status='verified' if native else 'output_received',configuration_verified=native,persistence_verified=native,
                protocol_effect_verified=True,protocol_persistence_verified=True,verified_scope='bound_native_acl_removal_and_saved_configuration_only' if native else 'synthetic_acl_removal_transaction_only')
        except (ConsoleError,OSError,ValueError) as exc:
            result['errors']=[exc.as_error() if isinstance(exc,ConsoleError) else {'code':'acl_removal_failed','message':str(exc)}]
            if dirty and backup is not None:
                try:
                    if channel is not None:archived=list(getattr(channel,'history',[]));channel.close();channel=None
                    channel,_=self.policy.open(document,binding,topology,identity['vm_uuid'])
                    result['rollback']=self.policy.deployment._restore(channel,backup)
                    result['protocol_rollback_verified']=True;result['rollback_verified']=self.policy.native_dependencies and getattr(channel,'native_channel',False)
                except (ConsoleError,OSError,ValueError) as recovery:result['rollback']={'status':'unverified','error':recovery.as_error() if isinstance(recovery,ConsoleError) else str(recovery),
                    'running_snapshot':backup['local_file'],'startup_snapshot':backup.get('startup')}
        finally:
            (directory/'transcript.json').write_text(json.dumps(archived+(getattr(channel,'history',[]) if channel is not None else []),indent=2),encoding='utf-8')
            if channel is not None:channel.close()
            (directory/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
