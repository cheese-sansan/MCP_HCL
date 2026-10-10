import base64
import hashlib
import json
from unittest.mock import patch
from pydantic import ValidationError
from mcp_hcl.interface_tuning import InterfaceTuning, InterfaceTuningOperation, readback_verified, redact
from software_fixtures import SoftwareCase, Guest, BASE

REQUEST={'router':'r1','interface':'GigabitEthernet0/0','bandwidth':1000,'ospf_cost':10,'ospf_priority':0,'ospf_hello_interval':10,'ospf_dead_interval':40}
AFTER=BASE.replace(' mtu 1400',' mtu 1400\n bandwidth 1000\n ospf cost 10\n ospf dr-priority 0\n ospf timer hello 10\n ospf timer dead 40')
SECRET='TestKey7';CIPHER='Z'*36

class TuningTests(SoftwareCase):
    def operation(self):return InterfaceTuningOperation(self.policy())
    def test_scalar_strictness_boundaries_timers_and_secret_lengths(self):
        cases=[{'bandwidth':True},{'bandwidth':'1'},{'bandwidth':0},{'ospf_cost':0},
            {'ospf_priority':256},{'ospf_hello_interval':11,'ospf_dead_interval':40},
            {'ospf_auth_key':'123456789'},{'ospf_auth_key':'中文'},
            {'ospf_md5_key_id':1},{'ospf_md5_key':'12345678901234567','ospf_md5_key_id':1},{'unknown':1}]
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValidationError):InterfaceTuning.model_validate(REQUEST|change)
    def test_unsupported_operation_has_no_stage_or_console_io(self):
        for change in ({'delay':1},{'clock_rate':64000,'interface':'Serial0/0'}):
            with self.subTest(change=change):
                operation=self.operation()
                with patch.object(operation.policy.deployment,'bindings',side_effect=AssertionError('Unsupported operation read stage')):
                    result=operation.apply('missing','lab',REQUEST|change)
                self.assertEqual(result['status'],'unverified');self.assertEqual(self.opens,[])
    def test_scalars_persist_and_protect_unrequested_views(self):
        self.guest=Guest(after=AFTER);result=self.operation().apply(self.project,'lab',REQUEST)
        self.assertTrue(result['protocol_effect_verified'],result);self.assert_synthetic(result)
        self.assertEqual(self.guest.files[self.guest.startup['main']],AFTER)
        for changed in (AFTER.replace('sysname preserved','sysname changed'),AFTER.replace(' mtu 1400',' mtu 1500')):
            self.assertFalse(readback_verified(BASE,changed,InterfaceTuning.model_validate(REQUEST)))
    def test_fixed_defaults_and_network_dependent_timers(self):
        self.assertTrue(readback_verified(BASE,BASE,InterfaceTuning.model_validate({'router':'r1','interface':'GigabitEthernet0/0','ospf_priority':1})))
        loop=BASE+'interface LoopBack0\n#\n'
        self.assertTrue(readback_verified(loop,loop,InterfaceTuning.model_validate({'router':'r1','interface':'LoopBack0','ospf_cost':0})))
        self.assertFalse(readback_verified(BASE,BASE,InterfaceTuning.model_validate({'router':'r1','interface':'GigabitEthernet0/0','ospf_hello_interval':10})))
    def test_authentication_modes_preserve_other_keys_and_remain_partial(self):
        before=BASE.replace(' mtu 1400',' mtu 1400\n ospf authentication-mode md5 2 cipher '+CIPHER)
        after=before.replace(' mtu 1400',' mtu 1400\n ospf authentication-mode md5 1 cipher '+CIPHER)
        request={'router':'r1','interface':'GigabitEthernet0/0','ospf_md5_key_id':1,'ospf_md5_key':SECRET}
        self.assertTrue(readback_verified(before,after,InterfaceTuning.model_validate(request)))
        self.assertFalse(readback_verified(before,after.replace(' ospf authentication-mode md5 2 cipher '+CIPHER,''),InterfaceTuning.model_validate(request)))
        simple=BASE.replace(' mtu 1400',' mtu 1400\n ospf authentication-mode simple cipher '+CIPHER)
        self.assertTrue(readback_verified(before,simple,InterfaceTuning.model_validate({'router':'r1','interface':'GigabitEthernet0/0','ospf_auth_key':SECRET})))
        self.guest=Guest(before,after);result=self.operation().apply(self.project,'lab',request)
        self.assertEqual(result['status'],'partial',result);self.assertFalse(result['authentication_key_verified']);self.assert_synthetic(result)
        text=self.serialized(result)
        self.assertNotIn(SECRET,text);self.assertNotIn('raw_output_b64',text);self.assertNotIn('request_sha256',text)
    def test_failure_redaction_and_secret_operation_key_reuse(self):
        request={'router':'r1','interface':'GigabitEthernet0/0','ospf_auth_key':SECRET,'operation_key':'auth_test_1'}
        after=BASE.replace(' mtu 1400',' mtu 1400\n ospf authentication-mode simple cipher '+CIPHER)
        self.guest=Guest(after=after);result=self.operation().apply(self.project,'lab',request)
        count=len(self.guest.commands);again=self.operation().apply(self.project,'lab',request)
        self.assertEqual(again['status'],'unverified');self.assertEqual(again['errors'][0]['code'],'secret_operation_key_reuse');self.assertEqual(len(self.guest.commands),count)
        self.assertNotIn(SECRET,self.serialized(result))
        self.guest=Guest(after=AFTER);self.guest.fail=lambda cmd:cmd.startswith('ospf authentication-mode')
        result=self.operation().apply(self.project,'lab',request|{'operation_key':'auth_test_2'})
        self.assertTrue(result['protocol_rollback_verified'],result);self.assertNotIn(SECRET,self.serialized(result))
        redacted=redact({'raw_output_b64':base64.b64encode(SECRET.encode()).decode(),'output_sha256':hashlib.sha256(SECRET.encode()).hexdigest(),'command':SECRET},[SECRET])
        self.assertNotIn(SECRET,json.dumps(redacted));self.assertNotIn('raw_output_b64',redacted)

    def test_secret_adjacent_to_error_text_is_redacted_without_changing_status(self):
        from mcp_hcl.console import ConsoleError
        request={'router':'r1','interface':'GigabitEthernet0/0','ospf_auth_key':SECRET}
        original=self.guest.exchange
        def exchange(cmd):
            if cmd.startswith('ospf authentication-mode'):
                raise ConsoleError('credential:'+SECRET+'suffix',code='command_rejected')
            return original(cmd)
        self.guest.exchange=exchange
        result=self.operation().apply(self.project,'lab',request)
        self.assertNotIn(SECRET,self.serialized(result));self.assertEqual(result['status'],'unverified')
