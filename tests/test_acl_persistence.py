"""Necessary contracts for implicit deny, saved configuration and recovery."""
import copy
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError
from mcp_hcl.acl_semantics import verify_acl,effective_acl_parameters
from mcp_hcl.services import Acl
from mcp_hcl.generation import render_acl
from mcp_hcl.startup import parse_startup
from mcp_hcl.console import ConsoleError
from mcp_hcl.cli_session import PersistentConsole
import test_policy as fixtures
from test_acl_named import NAMED,NamedGuest


class ImplicitDenyTests(unittest.TestCase):
    def test_default_deny_is_last_and_missing_fallback_cannot_pass(self):
        for identity in ({'number':2001},{'name':'web','acl_type':'advanced'}):
            rule={'id':5,'action':'permit','source':'10.0.0.0/24'}
            model=Acl.model_validate(identity|{'rules':[rule]})
            commands=render_acl(model)
            self.assertIn('rule 65534 deny',commands[-3])
            self.assertNotIn('packet-filter default deny',commands)
            config='#\n'+model.view+'\n '+commands[1]+'\n#\nreturn\n'
            self.assertFalse(verify_acl(config,model))
            config=config.replace('\n#\nreturn','\n '+commands[-3]+'\n#\nreturn')
            self.assertTrue(verify_acl(config,model))

    def test_explicit_catch_all_and_occupied_final_id_are_not_overwritten(self):
        permit_all=Acl.model_validate({'number':3001,'rules':[{'id':65534,'action':'permit'}]})
        self.assertFalse(any('MCP_HCL implicit deny' in command for command in render_acl(permit_all)))
        with self.assertRaises(ValidationError):Acl.model_validate({'number':3001,'rules':[{'id':65534,'action':'permit','protocol':'tcp'}]})
        model=Acl.model_validate(NAMED)
        occupied='#\nacl advanced name edge_web\n rule 65534 permit tcp\n#\nreturn\n'
        with self.assertRaises(ValueError):effective_acl_parameters(model,occupied)
        existing='#\nacl advanced name edge_web\n rule 7 permit ip\n#\nreturn\n'
        self.assertEqual([rule.id for rule in effective_acl_parameters(model,existing).rules],[5])


class StartupFormatTests(unittest.TestCase):
    def test_documented_roles_and_unknown_or_unsafe_layouts(self):
        text='Current startup saved-configuration file: flash:/old.cfg(*)\nNext main startup saved-configuration file: flash:/main.cfg\nNext backup startup saved-configuration file: NULL\n<R1>'
        self.assertEqual(parse_startup(text),{'current':'flash:/old.cfg','main':'flash:/main.cfg','backup':None})
        for changed in (text.replace('flash:/main.cfg','flash:/../main.cfg'),text.replace('flash:/main.cfg','flash:/main.cfg;reboot'),
                        text.replace('Next backup startup saved-configuration file: NULL\n',''),text+'\nNext main startup saved-configuration file: NULL',
                        'MainBoard:\n'+text):
            with self.assertRaises(ConsoleError):parse_startup(changed)


class PersistenceGuest(NamedGuest):
    def __init__(self,mode=None):super().__init__();self.mode=mode
    def exchange(self,command):
        if self.mode=='backup_unknown' and command.startswith('save ') and '_before.cfg' in command:
            self.commands.append(command);self.startup['main']=command[5:]
            raise ConsoleError('Save outcome unknown',code='pipe_broken')
        result=super().exchange(command)
        if command.startswith('save ') and '_after.cfg' in command and self.mode=='bad_saved':
            self.files[command[5:]]=fixtures.BASE
        if command.startswith('startup saved-configuration ') and '_after.cfg' in command:
            if self.mode=='pointer_unknown':raise ConsoleError('Pointer outcome unknown',code='pipe_broken')
            if self.mode=='old_file_changed':self.files['flash:/startup.cfg']='#\nsysname external\n#\nreturn\n'
        if command=='display saved-configuration' and self.mode in {'bad_selected','null_failure'}:return fixtures.BASE
        return result


class PersistenceTransactionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PolicyTests('test_master_gate_and_dry_run_do_not_open_a_console')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
    def apply(self,mode=None,empty=False):
        guest=PersistenceGuest(mode);self.fixture.guest=guest
        if empty:guest.startup={'current':None,'main':None,'backup':None};guest.files.clear()
        else:
            guest.startup['backup']='flash:/backup.cfg';guest.files['flash:/backup.cfg']='#\nsysname saved-backup\n#\nreturn\n'
        before=copy.deepcopy(guest.startup);originals={name:guest.files[name] for name in before.values() if name is not None}
        result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',NAMED)
        return guest,before,originals,result

    def test_saved_result_matches_running_and_old_files_remain(self):
        guest,before,originals,result=self.apply()
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertTrue(result['protocol_persistence_verified'])
        self.assertFalse(result['persistence_verified'])
        self.assertEqual(guest.files[guest.startup['main']],guest.current)
        self.assertNotEqual(guest.startup['main'],before['main'])
        self.assertEqual(guest.startup['backup'],before['backup'])
        self.assertEqual({name:guest.files[name] for name in originals},originals)
        self.assertIn('rule 65534 deny ip',guest.current)

    def test_bad_saved_content_stops_before_pointer_and_restores_running(self):
        guest,before,originals,result=self.apply('bad_saved')
        self.assertEqual(result['errors'][0]['code'],'persistence_content_unverified')
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertFalse(result['protocol_persistence_verified'])
        self.assertFalse(result['protocol_effect_verified'])
        self.assertEqual(guest.current,fixtures.BASE);self.assertEqual(guest.startup,before)
        self.assertFalse(any(command.startswith('startup saved-configuration ') for command in guest.commands))

    def test_unknown_pointer_outcome_reconnects_and_restores_original_roles(self):
        guest,before,originals,result=self.apply('pointer_unknown')
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertEqual(guest.startup,before);self.assertEqual(guest.current,fixtures.BASE)
        self.assertEqual(guest.commands.count('acl advanced name edge_web'),1)
        self.assertEqual(self.fixture.opens,2)
        self.assertEqual({name:guest.files[name] for name in originals},originals)

    def test_selected_saved_content_is_checked_even_after_correct_pointer(self):
        guest,before,originals,result=self.apply('bad_selected')
        self.assertEqual(result['errors'][0]['code'],'persistence_content_unverified')
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertEqual(guest.startup,before)

    def test_null_original_startup_is_restored_without_file_deletion(self):
        guest,before,originals,result=self.apply('null_failure',empty=True)
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertEqual(guest.startup,before)
        self.assertIn('undo startup saved-configuration',guest.commands)
        self.assertFalse(any(command.startswith(('delete ','reset saved-configuration')) for command in guest.commands))

    def test_original_startup_file_change_is_incomplete_recovery(self):
        guest,before,originals,result=self.apply('old_file_changed')
        self.assertEqual(result['errors'][0]['code'],'startup_content_changed')
        self.assertFalse(result['protocol_rollback_verified'])
        self.assertEqual(result['rollback']['error']['code'],'startup_content_changed')
        self.assertIn('startup_snapshot',result['rollback'])

    def test_unknown_backup_save_restores_pointer_without_using_unverified_file(self):
        guest,before,originals,result=self.apply('backup_unknown')
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertEqual(guest.startup,before)
        self.assertFalse(any(command.startswith('configuration replace file ') for command in guest.commands))
        self.assertFalse(any(command.startswith('acl ') for command in guest.commands))


class ConfirmationTests(unittest.TestCase):
    def test_replace_answers_no_and_invalid_confirmation_precedes_any_send(self):
        class Session:
            def __init__(self):self.sent=[];self.chunks=[]
            def drain(self):return b''
            def send(self,command):
                self.sent.append(command)
                self.chunks=[b'N\n<R1>'] if command=='N' else [command.encode()+b'\nCurrent configuration will be lost, save current configuration? [Y/N]:']
            def _read_available(self):return self.chunks.pop(0) if self.chunks else b''
            def close(self):pass
        with tempfile.TemporaryDirectory() as temporary:
            session=Session()
            with PersistentConsole(r'\\.\pipe\confirmation-device1',Path(temporary),session=session,timeout=.2) as channel:
                command='configuration replace file flash:/before.cfg'
                self.assertTrue(channel.exchange(command,confirmation='N')['complete'])
            self.assertEqual(session.sent,[command,'N'])
            invalid=Session()
            with PersistentConsole(r'\\.\pipe\confirmation-device1',Path(temporary),session=invalid,timeout=.2) as channel:
                with self.assertRaises(ConsoleError):channel.exchange(command,confirmation=1)
                self.assertEqual(invalid.sent,[])
