import tempfile
import unittest
from pathlib import Path
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.console import ConsoleError
from mcp_hcl.deployment import Deployment,verification_commands
from mcp_hcl.project import ProjectStore
from mcp_hcl.project_build import stage_plan
from test_project_build import configure_fixture,plan_fixture,explicit_map


BASE='#\nsysname factory\n#\nreturn\n'


class FakeComware:
    def __init__(self,device,fail=False,rollback_fail=False,backup_bad=False):
        self.device=device;self.fail=fail;self.rollback_fail=rollback_fail;self.backup_bad=backup_bad
        self.current=BASE;self.files={};self.history=[];self.applied=False
        self.expected=f'#\nsysname {device}\ninterface GigabitEthernet0/{0 if device=="r1" else 1}\n ip address 10.0.0.{1 if device=="r1" else 2} 255.255.255.252\n#\nreturn\n'
    def exchange(self,command,**kwargs):
        self.history.append({'command':command})
        if command.startswith('save '): self.files[command[5:]]=self.current
        if command.startswith('more '): output='not a configuration' if self.backup_bad else self.files[command[5:]]
        elif command=='display current-configuration': output=self.current
        elif command.startswith('configuration replace file '):
            if self.rollback_fail and self.applied: raise ConsoleError('native rollback failed')
            self.current=self.files[command.split()[-1]];output='Configuration replaced'
        elif command.startswith('sysname '): self.applied=True;self.current='#\nsysname '+self.device+'\n#\nreturn\n';output=''
        elif command.startswith('ip address '):
            if self.fail: raise ConsoleError('command rejected')
            self.current=self.expected;output=''
        elif command.startswith('ping '): output='5 packet(s) transmitted, 5 packet(s) received, 0.0% packet loss'
        else: output=''
        return {'output':command+'\n'+output+'<R1>','complete':True}
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


class Deployment040Tests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        paths=configure_fixture(Path(self.temporary.name));self.store=ProjectStore([paths['root']],paths['output'])
        self.catalog=HclCatalog(paths['install']);self.project=stage_plan(self.store,self.catalog,str(paths['project']),'Deploy',plan_fixture(),explicit_map())['project_directory']

    def engine(self,channels):
        return Deployment(self.store,catalog=self.catalog,writes_enabled=True,session_factory=lambda pipe:channels['r1' if pipe.endswith('device3') else 'r2'])

    def test_all_backups_before_configuration_and_actual_readback(self):
        channels={'r1':FakeComware('r1'),'r2':FakeComware('r2')}
        result=self.engine(channels).run(self.project,'lab')
        self.assertEqual(result['status'],'verified',result.get('errors'))
        self.assertTrue(result['configuration_verified']);self.assertFalse(result['full_live_gate_passed'])
        self.assertEqual([step['stage'] for step in result['steps'][:2]],['backup_and_restore_preflight']*2)
        self.assertTrue(all(b['restore_test_verified'] for b in result['backups']))
        self.assertTrue(Path(result['receipt_directory'],'r1-transcript.json').is_file())

    def test_second_device_failure_restores_every_modified_device(self):
        channels={'r1':FakeComware('r1'),'r2':FakeComware('r2',fail=True)}
        result=self.engine(channels).run(self.project,'lab')
        self.assertEqual(result['status'],'partial');self.assertTrue(result['rollback_verified'])
        self.assertEqual(channels['r1'].current,BASE);self.assertEqual(channels['r2'].current,BASE)
        self.assertEqual([r['device'] for r in result['rollback']],['r2','r1'])

    def test_rollback_failure_is_not_reported_as_recovered(self):
        channels={'r1':FakeComware('r1'),'r2':FakeComware('r2',fail=True,rollback_fail=True)}
        result=self.engine(channels).run(self.project,'lab')
        self.assertFalse(result['rollback_verified'])
        self.assertIn('manual_restore_command',result['rollback'][0])

    def test_unusable_backup_stops_before_any_configuration(self):
        channels={'r1':FakeComware('r1',backup_bad=True),'r2':FakeComware('r2')}
        result=self.engine(channels).run(self.project,'lab')
        self.assertEqual(result['status'],'partial')
        self.assertFalse(any(c.applied for c in channels.values()))
        self.assertFalse(result['configuration_verified'])

    def test_ping_statistics_and_gate_not_exit_status(self):
        channels={'r1':FakeComware('r1'),'r2':FakeComware('r2')}
        result=self.engine(channels).connectivity(self.project,'lab','r1','10.0.0.2')
        self.assertTrue(result['connectivity_verified'])
        self.assertEqual(result['statistics']['received'],5)
        self.assertEqual(Deployment(self.store).run('missing','lab')['errors'][0]['code'],'writes_disabled')

    def test_readback_cannot_match_a_command_in_the_wrong_interface(self):
        self.assertFalse(verification_commands(['system-view','interface GigabitEthernet0/0','ip address 10.0.0.1 255.255.255.0','quit','return'],
                       '#\ninterface GigabitEthernet0/1\n ip address 10.0.0.1 255.255.255.0\nreturn\n'))
