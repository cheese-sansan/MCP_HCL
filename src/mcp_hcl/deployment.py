"""Bounded staged-device deployment with tested native backups and rollback."""
from __future__ import annotations
import hashlib
import json
import re
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from mcp_hcl.cli_session import PersistentConsole, PROMPT
from mcp_hcl.console import ConsoleError, endpoint
from mcp_hcl.gui_relay import rejected


def config_text(reply: str) -> str:
    lines = reply.replace('\r','').splitlines()
    start = next((i for i,line in enumerate(lines) if line.strip() == '#'), None)
    end = next((i for i in range(len(lines)-1,-1,-1) if lines[i].strip() == 'return'), None)
    if start is None or end is None or end <= start:
        raise ConsoleError('Complete Comware configuration delimiters are missing')
    return '\n'.join(line.rstrip() for line in lines[start:end+1])+'\n'


def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verification_commands(commands: list[str], current: str) -> bool:
    """Check commands within their view, not merely anywhere in a config."""
    scopes={};context=()
    for line in current.splitlines():
        stripped=line.strip()
        if not stripped or stripped in {'#','return'}: continue
        if not line.startswith(' '):
            if stripped.startswith(('interface ','ospf ','rip ','vlan ','acl ','dhcp server ip-pool ','local-user ','traffic classifier ','traffic behavior ','qos policy ','wlan ')):
                context=(stripped.casefold(),);scopes.setdefault(context,set())
            else: context=();scopes.setdefault(context,set()).add(stripped.casefold())
        elif stripped.startswith(('area ','radio ')):
            context=context[:1]+(stripped.casefold(),);scopes.setdefault(context,set())
        else: scopes.setdefault(context,set()).add(stripped.casefold())
    context=()
    for command in commands:
        c=command.strip().casefold()
        if c in {'system-view','return'}: context=();continue
        if c=='quit': context=context[:-1];continue
        if c.startswith(('interface ','ospf ','rip ','vlan ','acl number ','dhcp server ip-pool ','local-user ','traffic classifier ','traffic behavior ','qos policy ','wlan ')):
            context=(c,)
            if context not in scopes: return False
        elif c.startswith(('area ','radio ')):
            context=context[:1]+(c,)
            if context not in scopes: return False
        elif c not in scopes.get(context,set()): return False
    return True


class Deployment:
    def __init__(self, store, *, catalog=None, writes_enabled=False, session_factory=None):
        self.store=store;self.writes_enabled=writes_enabled
        self.catalog=catalog
        self.session_factory=session_factory or (lambda pipe:PersistentConsole(pipe,store.output_root/'.console-leases'))

    def bindings(self, project_path):
        doc=self.store._open(project_path)
        if not doc.directory.is_relative_to(self.store.output_root): raise ValueError('Only staged projects may be deployed')
        path=doc.directory/'MCPArtifacts/bindings.json'
        stage=doc.directory/'MCPArtifacts/stage-receipt.json'
        for p in (path,stage):
            if not p.is_file() or p.is_symlink(): raise ValueError('Fresh stage/bindings receipts are required')
        metadata=json.loads(stage.read_text(encoding='utf-8'))
        if Path(metadata['project_file']).resolve()!=doc.net_path: raise ValueError('Stage identity mismatch')
        data=json.loads(path.read_text(encoding='utf-8'))['devices']
        actual={d['name']:d for d in doc.summary()['devices']}
        if len({d['plan_id'] for d in data})!=len(data): raise ValueError('Duplicate staged device binding')
        for binding in data:
            if actual.get(binding['name'],{}).get('device_id')!=binding['device_id']:
                raise ValueError('Device binding does not match the staged .net')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',binding['plan_id']): raise ValueError('Invalid plan ID')
        return doc,{d['plan_id']:d for d in data}

    def _directory(self, operation):
        directory=self.store.output_root/'.deployment-receipts'/operation
        directory.mkdir(parents=True,exist_ok=False)
        return directory

    def _backup(self, channel, device, directory, operation, on_saved=None):
        channel.exchange('return');channel.exchange('screen-length disable')
        before=config_text(channel.exchange('display current-configuration')['output'])
        guest=f'flash:/mcp_{operation}_{device}_before.cfg'
        channel.exchange(f'save {guest}',confirmation=True)
        # Native save output alone is not proof that a usable complete file exists.
        saved=config_text(channel.exchange(f'more {guest}')['output'])
        if digest(before)!=digest(saved): raise ConsoleError('Guest backup differs from the complete running configuration')
        local=directory/(device+'.cfg');local.write_text(before,encoding='utf-8')
        record={'device':device,'guest_file':guest,'local_file':str(local),'sha256':digest(before),'restore_test_verified':False}
        if on_saved: on_saved(record)
        channel.exchange('system-view')
        channel.exchange(f'configuration replace file {guest}',confirmation=True)
        channel.exchange('return')
        restored=config_text(channel.exchange('display current-configuration')['output'])
        if digest(before)!=digest(restored): raise ConsoleError('Native restore preflight failed to reproduce the baseline')
        record['restore_test_verified']=True
        return record

    def _restore(self, channel, backup):
        channel.exchange('return');channel.exchange('system-view')
        channel.exchange(f"configuration replace file {backup['guest_file']}",confirmation=True)
        channel.exchange('return')
        current=config_text(channel.exchange('display current-configuration')['output'])
        if digest(current)!=backup['sha256']: raise ConsoleError('Restored running configuration does not match the baseline')
        return {'device':backup['device'],'status':'verified','sha256':digest(current)}

    def run(self, project_path, topology, selected=None):
        if not self.writes_enabled: return rejected('writes_disabled','CLI deployment requires the live write switch')
        doc,bindings=self.bindings(project_path)
        selected=selected or list(bindings)
        if len(set(selected))!=len(selected) or not set(selected)<=set(bindings): raise ValueError('Deployment device selection is invalid')
        commands={}
        from mcp_hcl.generation import generate_configs
        if self.catalog is None: raise ValueError('A catalog is required to validate the staged command artifacts')
        plan=json.loads((doc.directory/'MCPArtifacts/plan.json').read_text(encoding='utf-8'))
        generated=generate_configs(plan,self.catalog)
        if generated['status']!='verified': raise ValueError('Staged plan cannot produce verified offline command templates')
        for device in selected:
            p=doc.directory/'MCPArtifacts/commands'/(device+'.txt')
            if p.is_symlink() or not p.is_file(): raise ValueError('Command artifacts are missing or linked')
            commands[device]=p.read_text(encoding='utf-8').splitlines()
            if commands[device] != generated['configs'][device].splitlines(): raise ValueError('Staged commands differ from the validated plan')
            if any(line.lower().startswith(('save','reboot','reset','configuration replace')) for line in commands[device]):
                raise ValueError('Command artifacts cannot contain lifecycle/persistence/restore operations')
        operation=uuid4().hex;directory=self._directory(operation)
        backups={};modified=[];rollback=[];steps=[];channels={};error=None;complete=False
        with ExitStack() as stack:
            try:
                for device in selected:
                    pipe=endpoint(topology,bindings[device]['device_id'])
                    channel=self.session_factory(pipe);channels[device]=channel;stack.callback(channel.close)
                for device in selected:
                    def saved(record):
                        backups[device]=record
                        modified.append(device)
                    backups[device]=self._backup(channels[device],device,directory,operation,on_saved=saved)
                    modified.remove(device)
                    steps.append({'device':device,'stage':'backup_and_restore_preflight','status':'verified'})
                for device in selected:
                    modified.append(device)
                    for index,command in enumerate(commands[device]):
                        channels[device].exchange(command)
                        steps.append({'device':device,'stage':'command','index':index,'status':'accepted'})
                    current=config_text(channels[device].exchange('display current-configuration')['output'])
                    if not verification_commands(commands[device],current): raise ConsoleError('Configuration readback does not match generated intent')
                    steps.append({'device':device,'stage':'configuration_readback','status':'verified'})
                complete=True
            except (ConsoleError,OSError,ValueError) as exc:
                error=str(exc)
                for device in reversed(modified):
                    try: rollback.append(self._restore(channels[device],backups[device]))
                    except (ConsoleError,OSError,ValueError) as restore_error:
                        # Reconnect once for recovery only. Never replay the
                        # original configuration commands after a disconnect.
                        try:
                            channels[device].close()
                            fresh=self.session_factory(endpoint(topology,bindings[device]['device_id']))
                            channels[device]=fresh;stack.callback(fresh.close)
                            rollback.append(self._restore(fresh,backups[device]))
                        except (ConsoleError,OSError,ValueError) as retry_error:
                            rollback.append({'device':device,'status':'unverified','error':str(retry_error),
                                             'initial_error':str(restore_error),
                                             'manual_restore_command':f"configuration replace file {backups[device]['guest_file']}"})
            finally:
                for device,channel in channels.items():
                    (directory/(device+'-transcript.json')).write_text(json.dumps(getattr(channel,'history',[]),ensure_ascii=False,indent=2),encoding='utf-8')
        result={'status':'verified' if complete else 'partial','operation_id':operation,'target_project':str(doc.net_path),
                'native_channels': bool(channels) and all(getattr(c,'native_channel',False) for c in channels.values()),
                'verified_scope':'running_configuration_readback_only' if complete else 'deployment_and_recovery_receipts_only',
                'configuration_verified':complete,'connectivity_verified':False,'guest_boot_verified':False,'full_live_gate_passed':False,
                'steps':steps,'backups':list(backups.values()),'rollback':rollback,'receipt_directory':str(directory),
                'rollback_verified': bool(modified) and all(r['status']=='verified' for r in rollback),
                'errors':[] if complete else [{'code':'deployment_failed','message':error or 'No verified deployment'}]}
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result

    def backup(self, project_path, topology, device):
        if not self.writes_enabled: return rejected('writes_disabled','Native configuration backup requires the live write switch')
        doc,bindings=self.bindings(project_path)
        if device not in bindings: raise ValueError('Unknown staged device')
        operation=uuid4().hex;directory=self._directory(operation)
        with self.session_factory(endpoint(topology,bindings[device]['device_id'])) as channel:
            result=self._backup(channel,device,directory,operation)
            result.update(project_file=str(doc.net_path),topology=topology,device_id=bindings[device]['device_id'])
            (directory/'backup.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return {'status':'verified','backup_id':operation,'backup':result,'verified_scope':'native_backup_and_restore_preflight_only','full_live_gate_passed':False}

    def restore(self, project_path, topology, backup_id):
        if not self.writes_enabled: return rejected('writes_disabled','Native restore requires the live write switch')
        if not re.fullmatch(r'[0-9a-f]{32}',backup_id): raise ValueError('Invalid backup ID')
        doc,bindings=self.bindings(project_path)
        path=self.store.output_root/'.deployment-receipts'/backup_id/'backup.json'
        record=json.loads(path.read_text(encoding='utf-8'));device=record['device']
        if device not in bindings or not record.get('restore_test_verified'): raise ValueError('Backup has no verified restore preflight')
        local=Path(record['local_file']).resolve()
        if (Path(record['project_file']).resolve()!=doc.net_path or record['topology']!=topology or
                record['device_id']!=bindings[device]['device_id'] or not local.is_relative_to(path.parent.resolve()) or local.is_symlink()):
            raise ValueError('Backup is not bound to this staged device and topology')
        if digest(local.read_text(encoding='utf-8'))!=record['sha256']: raise ValueError('Backup content was modified')
        with self.session_factory(endpoint(topology,bindings[device]['device_id'])) as channel:
            result=self._restore(channel,record)
        return {'status':'verified','restore':result,'verified_scope':'running_configuration_restored_only','full_live_gate_passed':False}

    def connectivity(self, project_path, topology, device, destination, count=5):
        if not self.writes_enabled: return rejected('writes_disabled','Sending ping requires the live write switch')
        from ipaddress import ip_address
        destination=str(ip_address(destination))
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=10: raise ValueError('Ping count must be 1-10')
        doc,bindings=self.bindings(project_path)
        if device not in bindings: raise ValueError('Unknown staged device')
        operation=uuid4().hex;directory=self._directory(operation)
        with self.session_factory(endpoint(topology,bindings[device]['device_id'])) as channel:
            response=channel.exchange(f'ping -c {count} {destination}')
            (directory/'ping.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
        match=re.search(r'(\d+)\s+packet(?:\(s\)|s)?\s+transmitted,?\s*(\d+)\s+packet(?:\(s\)|s)?\s+received,?\s*([\d.]+)%\s+packet loss',response['output'],re.I)
        verified=bool(match and int(match[1])==count and int(match[2])==count and float(match[3])==0)
        return {'status':'verified' if verified else 'unverified','operation_id':operation,
                'verified_scope':'measured_ping_statistics_only','connectivity_verified':verified,
                'statistics':None if not match else {'transmitted':int(match[1]),'received':int(match[2]),'loss_percent':float(match[3])},
                'receipt_directory':str(directory),'full_live_gate_passed':False}


def register_deployment_tools(mcp, deployment):
    @mcp.tool()
    def hcl_backup_config(project_path: str, topology: str, device: str) -> dict:
        """Create and test a native running-config backup for a bound staged device (gated)."""
        return deployment.backup(project_path,topology,device)

    @mcp.tool()
    def hcl_restore_config(project_path: str, topology: str, backup_id: str) -> dict:
        """Restore a tested native backup and compare the complete running configuration (gated)."""
        return deployment.restore(project_path,topology,backup_id)

    @mcp.tool()
    def hcl_live_deploy(project_path: str, topology: str, devices: list[str] | None = None) -> dict:
        """Back up all staged devices before deployment; restore modified devices on failure (gated)."""
        return deployment.run(project_path,topology,devices)

    @mcp.tool()
    def hcl_verify_connectivity(project_path: str, topology: str, device: str, destination: str, count: int = 5) -> dict:
        """Parse bounded actual ping statistics from a bound staged console; never infer success from exit status."""
        return deployment.connectivity(project_path,topology,device,destination,count)
