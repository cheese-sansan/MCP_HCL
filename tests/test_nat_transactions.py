import copy
import json
from pathlib import Path
from pydantic import ValidationError
from mcp_hcl.nat_models import NatApplication,NatRemoval,native_acl_number
from mcp_hcl.nat_policy import NatOperations
from mcp_hcl.nat_semantics import apply_delta,remove_delta,inline_acl,pool_assignment,group_ranges
from mcp_hcl.policy import scopes
from software_fixtures import SoftwareCase,Guest,BASE

STATIC={'router':'r1','mode':'static','inside_interface':'GigabitEthernet0/0','outside_interface':'GigabitEthernet0/1',
    'static_mappings':[{'inside_local':'10.0.0.1','inside_global':'203.0.113.1'}]}
STATIC_AFTER=BASE.replace('sysname preserved','sysname preserved\nnat static outbound 10.0.0.1 203.0.113.1').replace(' ip address',' nat static enable\n ip address')
DYNAMIC={**STATIC,'mode':'dynamic','static_mappings':[],'inside_networks':['10.0.0.0/24'],
    'pool_start':'203.0.113.1','pool_end':'203.0.113.8','pool_netmask':'255.255.255.0'}

class NatTests(SoftwareCase):
    def operation(self):return NatOperations(self.policy())
    def test_modes_strict_types_acl_mapping_and_network_forms(self):
        for mode,overload in [('static',False),('dynamic',False),('pat',False),('pat',True)]:
            request=STATIC if mode=='static' else DYNAMIC|{'mode':mode,'use_interface_overload':overload}
            model=NatApplication.model_validate(request);self.assertEqual(model.mode,mode)
        for network in ('any','host 192.0.2.1','10.0.0.0 0.255.0.255','10.0.0.0/24'):
            with self.subTest(network=network):self.assertTrue(NatApplication.model_validate(DYNAMIC|{'inside_networks':[network]}))
        for value,expected in [('1',2001),('99',2099),('1300',2100),('1999',2799),('100',3000),('199',3099),('2000',3100),('2699',3799)]:
            self.assertEqual(native_acl_number(value,'ios'),expected)
        for change in ({'timeout_seconds':True},{'use_interface_overload':'true'},{'pool_end':'202.0.0.1'},
                {'pool_netmask':'255.0.255.0'},{'inside_networks':[]},{'unknown':1}):
            with self.subTest(change=change):
                with self.assertRaises(ValidationError):NatApplication.model_validate(DYNAMIC|change)
    def test_static_transaction_persistence_idempotency_and_exact_removal(self):
        self.guest=Guest(after=STATIC_AFTER);request=STATIC|{'operation_key':'nat_static_1'}
        result=self.operation().run(self.project,'lab',request)
        self.assertTrue(result['protocol_effect_verified'],result);self.assert_synthetic(result)
        count=len(self.guest.commands);again=self.operation().run(self.project,'lab',request)
        self.assertTrue(again['reused_receipt']);self.assertFalse(again['current_state_rechecked']);self.assertEqual(len(self.guest.commands),count)
        conflict=self.operation().run(self.project,'lab',request|{'timeout_seconds':121})
        self.assertEqual(conflict['errors'][0]['code'],'operation_key_conflict')
        self.guest=Guest(STATIC_AFTER,BASE)
        removed=self.operation().run(self.project,'lab',STATIC,removal=True)
        self.assertTrue(removed['protocol_effect_verified'],removed);self.assertIn('undo nat static outbound 10.0.0.1 203.0.113.1',self.guest.commands)
    def test_pool_modes_ranges_equivalent_readback_and_preservation(self):
        for mode in ('dynamic','pat'):
            with self.subTest(mode=mode):
                model=NatApplication.model_validate(DYNAMIC|{'mode':mode,'pool_end':'203.0.114.1'})
                delta=apply_delta(BASE,model,0)
                self.assertIn('address 203.0.113.1 203.0.114.0',delta.commands)
                self.assertIn('address 203.0.114.1 203.0.114.1',delta.commands)
                desired=BASE.replace(' ip address',' nat outbound 2001 address-group 0'+(' no-pat' if mode=='dynamic' else '')+'\n ip address').replace('return','nat address-group 0\n address 203.0.113.1 203.0.114.1\n#\nreturn')
                self.assertTrue(delta.verified(desired));self.assertFalse(delta.verified(desired.replace('mtu 1400','mtu 1500')))
        pat=NatApplication.model_validate(DYNAMIC|{'mode':'pat','use_interface_overload':True})
        self.assertIn('nat outbound 2001',apply_delta(BASE,pat).commands)
    def test_acl_origin_named_type_and_preserved_existing_rules(self):
        config=BASE.replace('return','acl number 2001\n rule 5 permit source 192.0.2.0 0.0.0.255\n#\nreturn')
        with self.assertRaises(ValueError):inline_acl(config,NatApplication.model_validate(DYNAMIC))
        commands,model=inline_acl(config,NatApplication.model_validate(DYNAMIC|{'acl_namespace':'comware','acl_number':'2001'}))
        self.assertFalse(any(cmd.startswith('undo rule 5') for cmd in commands))
        named=NatApplication.model_validate(DYNAMIC|{'acl_number':'inside','named_acl_type':'advanced'})
        self.assertEqual(named.acl_reference,'name inside');self.assertEqual(named.acl_kind,'advanced')
    def test_pool_identity_drift_explicit_pin_and_unrelated_conflict(self):
        config=BASE.replace('return','nat address-group 7\n address 203.0.113.1 203.0.113.8\n#\nreturn')
        record={'address_group':7,'start':'203.0.113.2','end':'203.0.113.8'}
        with self.assertRaises(ValueError):pool_assignment(scopes(config),NatApplication.model_validate(DYNAMIC),record)
        self.assertEqual(pool_assignment(scopes(config),NatApplication.model_validate(DYNAMIC|{'pool_address_group':7}),record),7)
        with self.assertRaises(ValueError):pool_assignment(scopes(config),NatApplication.model_validate(DYNAMIC|{'pool_address_group':7,'pool_start':'203.0.113.2'}),None)
    def test_shared_acl_pool_and_static_enable_require_explicit_retention(self):
        config=BASE.replace(' ip address',' nat outbound 2001 address-group 0 no-pat\n ip address').replace(' mtu 1400',' mtu 1400\n packet-filter 2001 inbound').replace('return','nat address-group 0\n address 203.0.113.1 203.0.113.8\n#\nacl number 2001\n rule 5 permit source any\n#\nreturn')
        request=NatRemoval.model_validate({k:v for k,v in DYNAMIC.items() if k not in ('inside_networks','pool_start','pool_end','pool_netmask')}|{'acl_namespace':'comware','acl_number':'2001'})
        with self.assertRaises(ValueError):remove_delta(config,request,0)
        delta=remove_delta(config,request.model_copy(update={'remove_acl':False}),0)
        self.assertNotIn('undo acl basic 2001',delta.commands)
        more=STATIC_AFTER.replace('sysname preserved','sysname preserved\nnat static outbound 10.0.0.2 203.0.113.2')
        with self.assertRaises(ValueError):remove_delta(more,NatRemoval.model_validate(STATIC))
        self.assertNotIn('undo nat static enable',remove_delta(more,NatRemoval.model_validate(STATIC|{'disable_static_interface':False})).commands)
    def test_incomplete_receipt_and_same_vm_recovery(self):
        directory=self.paths['output']/'.nat-receipts'/'nat_partial_1';directory.mkdir(parents=True)
        result=self.operation().run(self.project,'lab',STATIC|{'operation_key':'nat_partial_1'})
        self.assertEqual(result['status'],'unverified');self.assertEqual(self.opens,[])
        self.guest=Guest(after=STATIC_AFTER);self.guest.fail=lambda cmd:cmd=='nat static enable'
        result=self.operation().run(self.project,'lab',STATIC)
        self.assertTrue(result['protocol_rollback_verified'],result);self.assertEqual(self.guest.current,BASE)
        self.assertEqual(self.guest.commands.count('nat static outbound 10.0.0.1 203.0.113.1'),1)

    def test_dynamic_and_both_pat_transactions_with_independent_acl_readback(self):
        acl_after=BASE.replace('return','acl number 2001\n rule 0 permit source 10.0.0.0 0.0.0.255\n rule 65534 deny\n rule 65534 comment MCP_HCL implicit deny\n#\nreturn')
        for mode,interface_overload in [('dynamic',False),('pat',False),('pat',True)]:
            with self.subTest(mode=mode,interface_overload=interface_overload):
                request=DYNAMIC|{'mode':mode,'use_interface_overload':interface_overload}
                line=' nat outbound 2001'+('' if interface_overload else ' address-group 0')+(' no-pat' if mode=='dynamic' else '')
                after=acl_after.replace(' ip address',line+'\n ip address')
                if not interface_overload:after=after.replace('return','nat address-group 0\n address 203.0.113.1 203.0.113.8\n#\nreturn')
                self.guest=Guest(after=acl_after)
                def transition(cmd):
                    if cmd.startswith(('nat outbound ','nat address-group ')):self.guest.after=after
                self.guest.on_exchange=transition
                # Each variant owns a distinct synthetic VM identity namespace.
                self.vm_identity=mode+'-'+str(interface_overload)
                result=self.operation().run(self.project,'lab',request)
                self.assertTrue(result.get('protocol_effect_verified'),result);self.assert_synthetic(result)
                self.assertEqual(self.guest.files[self.guest.startup['main']],after)

    def test_metadata_identity_and_native_namespace_are_not_simulation_authority(self):
        operation=self.operation();document=self.store._open(self.project)
        path,state=operation._state(document,'r1',{'vm_uuid':'same'})
        self.assertIn('.nat-protocol-state',path.parts)
        native=self.paths['output']/'.nat-state'/path.name;native.parent.mkdir(parents=True)
        native.write_text(json.dumps(state|{'native_verified':True}),encoding='utf-8')
        before=native.read_bytes();self.guest=Guest(after=STATIC_AFTER)
        result=operation.run(self.project,'lab',STATIC)
        self.assertTrue(result.get('protocol_effect_verified'),result);self.assert_synthetic(result);self.assertEqual(native.read_bytes(),before)
        path.write_text(json.dumps(state|{'target':{'project':'wrong','device':'r1','vm_uuid':'same'}}),encoding='utf-8')
        with self.assertRaises(ValueError):operation._state(document,'r1',{'vm_uuid':'same'})
