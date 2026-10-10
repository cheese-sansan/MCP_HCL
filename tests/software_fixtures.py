"""Scripted configuration/readback fixtures, isolated from native HCL services."""
import base64
import copy
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.console import ConsoleError
from mcp_hcl.policy import Policy
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan
from test_project_build import configure_fixture, plan_fixture, explicit_map

BASE = '#\nversion 7.1.064\nsysname preserved\n#\ninterface GigabitEthernet0/0\n mtu 1400\n port link-type access\n port access vlan 1\n#\ninterface GigabitEthernet0/1\n ip address 10.0.0.2 255.255.255.252\n#\nreturn\n'

def reply(command, text, **changes):
    raw = (command+'\r\n'+text+'\r\n<R1>').encode()
    return {'command':command,'complete':True,'output':raw.decode(),
            'raw_output_b64':base64.b64encode(raw).decode(),
            'output_sha256':hashlib.sha256(raw).hexdigest(),
            'request_sha256':hashlib.sha256(command.encode()).hexdigest(), **changes}

class Clock:
    def __init__(self): self.value = 0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds

class Guest:
    """Apply one fixed expected readback on first mutation; do not compile intent."""
    def __init__(self, before=BASE, after=None):
        self.current=before; self.after=after or before; self.commands=[]
        self.files={'flash:/startup.cfg':before}
        self.startup={'current':None,'main':'flash:/startup.cfg','backup':None}
        self.fail=None; self.bad_saved=False; self.close_error=False
        self.responses={}; self.on_exchange=None; self.mutated=False
    def exchange(self, command):
        self.commands.append(command)
        if self.on_exchange: self.on_exchange(command)
        if self.fail and self.fail(command): raise ConsoleError('Scripted failure',code='command_rejected')
        if command in self.responses: return self.responses[command]
        if command=='display current-configuration': return self.current
        if command=='display startup':
            return '\n'.join(f'{label} startup saved-configuration file: {self.startup[key] or "NULL"}'
                for label,key in (('Current','current'),('Next main','main'),('Next backup','backup')))+'\n'
        if command=='display saved-configuration': return self.files[self.startup['main'] or self.startup['backup']]
        if command.startswith('more '): return self.files[command[5:]]
        if command.startswith('save '):
            self.files[command[5:]]=BASE if self.bad_saved and '_after.cfg' in command else self.current
        elif command=='undo startup saved-configuration': self.startup.update(main=None,backup=None)
        elif command.startswith('startup saved-configuration '): self.startup[command.split()[-1]]=command.split()[2]
        elif command.startswith('configuration replace file '): self.current=self.files[command.split()[-1]]
        elif command not in {'system-view','return','quit','screen-length disable'}:
            self.current=self.after; self.mutated=True
        return ''

class SoftwareCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.paths=configure_fixture(self.root)
        self.store=ProjectStore([self.paths['root']],self.paths['output'])
        self.catalog=HclCatalog(self.paths['install'])
        self.project=stage_plan(self.store,self.catalog,str(self.paths['project']),'Verify',plan_fixture(),explicit_map())['project_directory']
        self.guest=Guest(); self.opens=[]; self.targets=[]; self.changed_identity=False
        self.binding_error=False; self.pipe_error=False; self.reply_changes={}
        self.channels=[]; self.clock=Clock()
        self.addCleanup(patch.stopall)
        patch('subprocess.run',side_effect=AssertionError('Unexpected native subprocess')).start()
        patch('mcp_hcl.cli_session.PersistentConsole.__init__',side_effect=AssertionError('Unexpected native pipe')).start()
        patch('ctypes.WinDLL',side_effect=AssertionError('Unexpected native identity/pipe API')).start()
    def dependencies(self):
        case=self
        class Binder:
            def resolve(self,doc,binding,topology):
                case.targets.append(binding['device_id'])
                if case.binding_error: raise ConsoleError('Binding mismatch',code='runtime_binding_unverified')
                return {'vm_uuid':'changed' if case.changed_identity and case.opens else getattr(case,'vm_identity','same'),
                        'configuration_disk':'fixture-disk','device_id':binding['device_id'],
                        'project_sha256':hashlib.sha256(doc.net_path.read_bytes()).hexdigest()}
            def verify_pipe(self,channel,target):
                if case.pipe_error: raise ConsoleError('Pipe mismatch',code='pipe_identity_unverified')
                return target
        class Channel:
            native_channel=True  # Spoofing this alone must never elevate synthetic evidence.
            def __init__(self,pipe):
                case.opens.append(pipe);case.channels.append(self);self.history=[];self.partial_output=b''
            def exchange(self,command,**kwargs):
                row=reply(command,case.guest.exchange(command),**case.reply_changes)
                self.history.append(row);return row
            def close(self):
                if case.guest.close_error: raise ConsoleError('Close failed',code='pipe_broken')
        return Binder(),Channel
    def policy(self,writes=True):
        binder,channel=self.dependencies()
        return Policy(self.store,self.catalog,writes_enabled=writes,runtime_binding=binder,session_factory=channel)
    def assert_synthetic(self,result):
        self.assertFalse(result.get('configuration_verified',False),result)
        self.assertFalse(result.get('persistence_verified',False),result)
        self.assertFalse(result.get('rollback_verified',False),result)
        self.assertFalse(result.get('native_readback_verified',False),result)
        self.assertFalse(result['full_live_gate_passed'])
    def serialized(self,result):
        texts=[json.dumps(result,ensure_ascii=False)]
        texts += [p.read_text(encoding='utf-8') for p in self.paths['output'].rglob('*.json')
                  if '.console-leases' not in p.parts]
        return '\n'.join(texts)

def inline_arguments(command):
    """Decode only the generated constant expressions, without eval or PowerShell."""
    assert command[:4][1:] == ['-NoProfile','-NonInteractive','-Command']
    expression=command[4]
    pattern=r"-([A-Za-z][A-Za-z0-9]+) \(\[Text.Encoding\]::UTF8.GetString\(\[Convert\]::FromBase64String\('([A-Za-z0-9+/=]+)'\)\)\)"
    args={k:base64.b64decode(v,validate=True).decode() for k,v in re.findall(pattern,expression)}
    args['action']='open' if expression.endswith(' -OpenOnly') else 'save'
    return args
