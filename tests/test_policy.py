"""Scoped configuration effects/recovery using a stateful synthetic guest."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.console import ConsoleError
from mcp_hcl.policy import Policy,scopes,patch_preserves_unrequested
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan
from mcp_hcl.services import Acl,Vlan
from test_project_build import configure_fixture,plan_fixture,explicit_map,snapshot
from test_mcp_contract import mcp_session,call


BASE='''#
sysname preserved
#
interface GigabitEthernet0/0
 mtu 1400
 port link-type access
 port access vlan 1
#
interface GigabitEthernet0/1
 ip address 10.0.0.2 255.255.255.252
#
acl number 3002
 rule 0 deny ip source any destination any
#
return
'''
ACL={'number':3001,'rules':[{'id':5,'action':'permit','protocol':'tcp','source':'10.1.0.0/24',
     'destination':'192.0.2.0/24','destination_port':443}],
     'bindings':[{'interface':'GigabitEthernet0/0','direction':'inbound'}]}
VLAN={'vlans':[10,20],'ports':[{'interface':'GigabitEthernet0/0','mode':'trunk','allowed_vlans':[10,20]}]}


class Guest:
    def __init__(self):
        self.current=BASE;self.files={};self.commands=[];self.fail=None;self.unrequested=False
        self.view=None;self.backup_bad=False;self.restore_bad=False;self.changed=False
        self.startup={'current':None,'main':'flash:/startup.cfg','backup':None}
        self.files['flash:/startup.cfg']=BASE
    def text(self,views):
        lines=['#',*sorted(views.get((),set()))]
        for context,commands in views.items():
            if context:
                header=context[0]
                names=[line[10:] for line in commands if line.startswith('@acl-name ')]
                if header.startswith('acl number ') and names:header+=' name '+names[0]
                if '@acl-order auto' in commands:header+=' match-order auto'
                lines+=['#',header,*[' '+line for line in sorted(commands) if not line.startswith('@')]]
        return '\n'.join([*lines,'#','return',''])
    def exchange(self,command):
        self.commands.append(command)
        if command=='display current-configuration':return self.current
        if command=='display startup':
            return '\n'.join(f'{label} startup saved-configuration file: {self.startup[key] or "NULL"}' for label,key in
                (('Current','current'),('Next main','main'),('Next backup','backup')))+'\n'
        if command=='display saved-configuration':return self.files[self.startup['main'] or self.startup['backup']]
        if command=='undo startup saved-configuration':self.startup['main']=None;self.startup['backup']=None;return ''
        if command.startswith('startup saved-configuration '):self.startup[command.split()[-1]]=command.split()[2];return ''
        if command.startswith('save '):self.files[command[5:]]=self.current
        elif command.startswith('more '):return 'bad backup' if self.backup_bad and '_before.cfg' in command else self.files[command[5:]]
        elif command.startswith('configuration replace file '):
            if self.restore_bad and self.changed:raise ConsoleError('Recovery failed',code='pipe_broken')
            self.current=self.files[command.split()[-1]];self.view=None
        elif command in {'system-view','return','screen-length disable'}:self.view=None
        elif command=='quit':self.view=None
        elif command.startswith(('interface ','acl number ','vlan ')):
            self.view=(command,);views=scopes(self.current);views.setdefault(self.view,set());self.current=self.text(views)
        elif self.view is not None:
            self.changed=True
            if self.fail and command.startswith(self.fail):raise ConsoleError('Guest rejected command',code='command_rejected')
            views=scopes(self.current)
            lines=views[self.view]
            if command=='undo port trunk permit vlan all':
                lines.difference_update({line for line in lines if line.startswith('port trunk permit vlan ')})
            elif command=='undo shutdown':lines.discard('shutdown')
            elif command.startswith('undo packet-filter '):
                prefix=command[5:]
                lines.difference_update({line for line in lines if line==prefix or line.startswith(prefix+' ')})
            elif command.startswith('undo rule '):
                prefix='rule '+command.split()[-1]+' '
                lines.difference_update({line for line in lines if line.startswith(prefix)})
            else:
                key=' '.join(command.split()[:2])
                if command.startswith('rule ') and command.split()[2]=='comment':key=' '.join(command.split()[:3])
                elif command.startswith('rule '):
                    prefix=' '.join(command.split()[:2])+' '
                    lines.difference_update({line for line in lines if line.startswith(prefix) and not line.startswith(prefix+'comment ')})
                    key=command
                elif command.startswith('packet-filter '):key=command
                elif command.startswith('port trunk permit vlan '):key=command
                elif command.startswith('name '):key='name'
                elif command.startswith('port link-type '):key='port link-type'
                elif command.startswith('port '):key=' '.join(command.split()[:3])
                lines.difference_update({line for line in lines if line.startswith(key+' ') or line==key})
                lines.add(command)
            if self.unrequested:views[()].discard('sysname preserved');views[()].add('sysname unexpected')
            self.current=self.text(views)
        return ''


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);paths=configure_fixture(self.root)
        self.catalog=HclCatalog(paths['install']);self.store=ProjectStore([paths['root']],paths['output'])
        self.project=stage_plan(self.store,self.catalog,str(paths['project']),'Policy',plan_fixture(),explicit_map())['project_directory']
        self.before=snapshot(Path(self.project));self.guest=Guest();self.opens=0;self.identity_changed=False
    def engine(self,writes=True):
        test=self
        class Binder:
            def resolve(self,document,binding,topology):return {'vm_uuid':'changed' if test.identity_changed and test.opens else 'same'}
            def verify_pipe(self,channel,target):return target
        class Channel:
            native_channel=True
            def __init__(self,pipe):test.opens+=1;self.history=[]
            def exchange(self,command,**kwargs):
                self.history.append({'command':command})
                return {'output':command+'\n'+test.guest.exchange(command)+'<R1>','complete':True}
            def close(self):pass
        return Policy(self.store,self.catalog,writes_enabled=writes,runtime_binding=Binder(),session_factory=Channel)

    def test_master_gate_and_dry_run_do_not_open_a_console(self):
        engine=self.engine(False)
        self.assertEqual(engine.apply('acl','missing','lab','r1',ACL)['errors'][0]['code'],'writes_disabled')
        dry=engine.apply('vlan',self.project,'lab','r1',VLAN,True)
        self.assertEqual(dry['status'],'verified',dry)
        self.assertIn('undo port trunk permit vlan all',dry['commands'])
        self.assertFalse(dry['configuration_verified'])
        self.assertEqual(self.opens,0)

    def test_acl_effect_preserves_unrelated_acl_sysname_address_and_mtu(self):
        result=self.engine().apply('acl',self.project,'lab','r1',ACL)
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertFalse(result['configuration_verified'])
        self.assertEqual(result['status'],'output_received')
        current=scopes(self.guest.current)
        self.assertEqual(current[('acl number 3002',)],scopes(BASE)[('acl number 3002',)])
        self.assertIn('mtu 1400',current[('interface GigabitEthernet0/0',)])
        self.assertEqual(current[()],{'sysname preserved'})
        self.assertEqual(snapshot(Path(self.project)),self.before)

    def test_requested_acl_binding_slot_may_replace_another_acl_without_touching_opposite_direction(self):
        before=BASE.replace(' mtu 1400',' mtu 1400\n packet-filter 3002 inbound\n packet-filter 3002 outbound')
        desired=before.replace('packet-filter 3002 inbound','packet-filter 3001 inbound')
        self.assertTrue(patch_preserves_unrequested(before,desired,'acl',Acl.model_validate(ACL)))
        changed=desired.replace('packet-filter 3002 outbound','packet-filter 3001 outbound')
        self.assertFalse(patch_preserves_unrequested(before,changed,'acl',Acl.model_validate(ACL)))

    def test_vlan_trunk_membership_replaces_prior_members_without_other_configuration(self):
        result=self.engine().apply('vlan',self.project,'lab','r1',VLAN)
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertIn('port trunk permit vlan 10 20',self.guest.current)
        self.assertLess(self.guest.commands.index('undo port trunk permit vlan all'),self.guest.commands.index('port trunk permit vlan 10 20'))
        self.assertNotIn('sysname r1',self.guest.commands)
        self.assertEqual(snapshot(Path(self.project)),self.before)

    def test_invalid_parameters_and_unusable_backup_stop_before_policy_commands(self):
        bad=copy.deepcopy(ACL);bad['rules'][0]['destination_port']=True
        self.assertEqual(self.engine().apply('acl',self.project,'lab','r1',bad)['status'],'rejected')
        self.assertEqual(self.opens,0)
        self.guest.backup_bad=True
        result=self.engine().apply('acl',self.project,'lab','r1',ACL)
        self.assertFalse(result['protocol_effect_verified'])
        self.assertNotIn('acl number 3001',self.guest.commands)

    def test_midway_failure_reconnects_for_recovery_and_never_replays_policy(self):
        self.guest.fail='packet-filter '
        result=self.engine().apply('acl',self.project,'lab','r1',ACL)
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertFalse(result['rollback_verified'])
        self.assertEqual(self.guest.current,BASE)
        self.assertEqual(self.guest.commands.count('acl number 3001'),1)
        self.assertEqual(self.opens,2)
        transcript=json.loads((Path(result['receipt_directory'])/'transcript.json').read_text())
        self.assertIn('packet-filter 3001 inbound',[row['command'] for row in transcript])

    def test_unrequested_changes_restore_baseline_and_changed_recovery_identity_is_refused(self):
        self.guest.unrequested=True
        result=self.engine().apply('vlan',self.project,'lab','r1',VLAN)
        self.assertEqual(result['errors'][0]['code'],'policy_scope_changed')
        self.assertTrue(result['protocol_rollback_verified'])
        self.assertEqual(self.guest.current,BASE)
        self.guest=Guest();self.opens=0;self.identity_changed=True;self.guest.fail='packet-filter '
        result=self.engine().apply('acl',self.project,'lab','r1',ACL)
        self.assertFalse(result['protocol_rollback_verified'])
        self.assertEqual(result['rollback']['error']['code'],'recovery_target_changed')
        self.assertEqual(self.opens,1)

    def test_unverified_recovery_is_reported_with_the_native_backup_location(self):
        self.guest.fail='packet-filter ';self.guest.restore_bad=True
        result=self.engine().apply('acl',self.project,'lab','r1',ACL)
        self.assertFalse(result['rollback_verified'])
        self.assertFalse(result['protocol_rollback_verified'])
        self.assertIn('configuration replace file flash:/mcp_',result['rollback']['manual_restore_command'])


class PolicyStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_policy_schema_gate_and_offline_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths=configure_fixture(Path(temporary))
            store=ProjectStore([paths['root']],paths['output']);catalog=HclCatalog(paths['install'])
            project=stage_plan(store,catalog,str(paths['project']),'Policy',plan_fixture(),explicit_map())['project_directory']
            async with mcp_session(paths) as session:
                tools={tool.name:tool for tool in (await session.list_tools()).tools}
                self.assertEqual(tools['hcl_apply_acl'].inputSchema['properties']['parameters']['additionalProperties'],False)
                for tool,parameters in (('hcl_apply_acl',ACL),('hcl_apply_vlan',VLAN)):
                    response,body=await call(session,tool,{'project_path':project,'topology':'lab','device':'r1','parameters':parameters})
                    self.assertFalse(response.isError)
                    self.assertEqual(body['errors'][0]['code'],'writes_disabled')
                    response,body=await call(session,tool,{'project_path':project,'topology':'lab','device':'r1','parameters':parameters,'dry_run':True})
                    self.assertFalse(response.isError)
                    self.assertEqual(body['status'],'verified',body)
                    self.assertFalse(body['configuration_verified'])
