"""Named ACLs, arbitrary wildcard matching and exact directional replacement."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError
from mcp_hcl.services import Acl,AclRule
from mcp_hcl.generation import render_acl,generate_configs
from mcp_hcl.acl_semantics import verify_acl,prepare_acl_commands,ensure_acl_target
from mcp_hcl.policy import scopes,patch_preserves_unrequested
from mcp_hcl.project import ProjectStore
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.project_build import stage_plan
from test_mcp_contract import mcp_session,call
from test_project_build import configure_fixture,plan_fixture,explicit_map,snapshot
import test_policy as fixtures

NAMED={'name':'EDGE_WEB','acl_type':'advanced','rules':[{'id':5,'action':'permit','protocol':'tcp',
       'source':'10.1.2.3 0.255.0.255','destination':'host 192.0.2.20','destination_port':443}],
       'bindings':[{'interface':'GigabitEthernet0/0','direction':'inbound'}]}


class NamedValuesTests(unittest.TestCase):
    def test_named_identity_type_and_case_rules_keep_numeric_compatibility(self):
        model=Acl.model_validate(NAMED)
        self.assertEqual(model.name,'edge_web')
        self.assertEqual(render_acl(model)[0],'acl advanced name edge_web')
        self.assertIn('packet-filter name edge_web inbound',render_acl(model))
        self.assertEqual(Acl.model_validate(fixtures.ACL).view,'acl number 3001')
        for extra in ({'name':None},{'number':3001},{'acl_type':None},{'name':'ALL'},
                      {'name':'bad\nreboot'},{'name':'1name'},{'name':'x'*64},{'name':'x y'}):
            with self.assertRaises(ValidationError):Acl.model_validate(NAMED|extra)
        with self.assertRaises(ValidationError):Acl.model_validate(fixtures.ACL|{'acl_type':'basic'})
        with self.assertRaises(ValidationError):Acl.model_validate(NAMED|{'bindings':NAMED['bindings']*2})

    def test_host_any_and_noncontiguous_wildcard_are_semantically_exact(self):
        model=Acl.model_validate(NAMED|{'implicit_deny':False})
        self.assertEqual(model.rules[0].source,'10.0.2.0 0.255.0.255')
        config='#\nacl advanced name EDGE_WEB\n rule 5 permit tcp source 10.55.2.99 0.255.0.255 destination host 192.0.2.20 destination-port eq https\n#\ninterface GigabitEthernet0/0\n packet-filter name EDGE_WEB inbound\n#\nreturn\n'
        self.assertTrue(verify_acl(config,model))
        self.assertFalse(verify_acl(config.replace('10.55.2.99','10.55.3.99'),model))
        self.assertFalse(verify_acl(config.replace('0.255.0.255','0.255.1.255'),model))
        for source in ('10.1.2.3','10.0.0.1/24','host nope','10.0.0.0 255.256.0.0','::/0','any\nreboot'):
            with self.assertRaises(ValidationError):AclRule.model_validate({'id':1,'action':'permit','source':source})
        self.assertIn('source any',render_acl(Acl.model_validate({'name':'simple','acl_type':'basic',
            'rules':[{'id':1,'action':'permit','source':'any'}]}))[1])

    def test_upstream_protocol_and_documented_icmp_names_render_numeric_effect(self):
        for protocol,number in (('ahp',51),('ah',51),('esp',50),('eigrp',88)):
            model=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'permit','protocol':protocol}]})
            command=render_acl(model)[1]
            self.assertIn('permit '+str(number)+' ',command)
            self.assertTrue(verify_acl('#\nacl number 3001\n '+command+'\n#\nreturn\n',model))
        for name,kind,code in (('fragmentneed-DFset',3,4),('timestamp-request',13,0),('net-tos-redirect',5,2)):
            model=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'deny','protocol':'icmp','icmp':name}]})
            self.assertIn(f'icmp-type {kind} {code}',render_acl(model)[1])
            self.assertTrue(verify_acl('#\nacl number 3001\n rule 1 deny icmp icmp-type '+name+'\n#\nreturn\n',model))
        with self.assertRaises(ValidationError):AclRule.model_validate({'id':1,'action':'permit','protocol':'icmp','icmp':'unverified'})

    def test_named_number_alias_uses_only_the_verified_association(self):
        model=Acl.model_validate(NAMED|{'implicit_deny':False})
        config='#\nacl advanced 3001 name EDGE_WEB\n rule 5 permit tcp source 10.0.2.0 0.255.0.255 destination 192.0.2.20 0 destination-port eq 443\n#\ninterface GigabitEthernet0/0\n packet-filter 3001 inbound\n#\nreturn\n'
        self.assertTrue(verify_acl(config,model))
        for changed in (config.replace('name EDGE_WEB','name other'),config.replace('packet-filter 3001','packet-filter 3002'),
                        config.replace('packet-filter 3001 inbound','packet-filter 3001 inbound\n packet-filter name old inbound')):
            self.assertFalse(verify_acl(changed,model))

    def test_ambiguous_type_and_auto_order_targets_are_rejected(self):
        model=Acl.model_validate(NAMED)
        for config in ('#\nacl basic name edge_web\n rule 5 permit source any\nreturn\n',
                       '#\nacl advanced name edge_web match-order auto\n rule 5 permit ip\nreturn\n',
                       '#\nacl advanced name edge_web\n rule 5 permit ip\n#\nacl advanced 3001 name EDGE_WEB\n rule 5 permit ip\nreturn\n'):
            with self.assertRaises(ValueError):ensure_acl_target(config,model)
            self.assertFalse(verify_acl(config,model))

    def test_named_patch_cannot_change_other_ids_names_or_reverse_direction(self):
        model=Acl.model_validate(NAMED)
        before='#\nacl advanced name EDGE_WEB\n rule 5 deny tcp established\n rule 9 deny ip\n#\ninterface GigabitEthernet0/0\n packet-filter name old inbound\n packet-filter name reverse outbound\n packet-filter ipv6 3001 inbound\n#\nreturn\n'
        after=before.replace('rule 5 deny tcp established',render_acl(model)[1]).replace('packet-filter name old inbound','packet-filter name edge_web inbound')
        self.assertTrue(patch_preserves_unrequested(before,after,'acl',model))
        for changed in (after.replace('rule 9 deny ip','rule 9 permit ip'),after.replace('name reverse outbound','name reverse inbound'),
                        after.replace('packet-filter ipv6 3001 inbound','packet-filter ipv6 3002 inbound')):
            self.assertFalse(patch_preserves_unrequested(before,changed,'acl',model))
        numeric=Acl.model_validate(fixtures.ACL)
        named_number='#\nacl number 3001 name original\n rule 5 deny ip\n#\nreturn\n'
        self.assertFalse(patch_preserves_unrequested(named_number,named_number.replace('name original','name renamed'),'acl',numeric))

    def test_multiple_acl_preparation_does_not_repeat_rule_removal(self):
        first=Acl.model_validate(NAMED|{'bindings':[]})
        second=Acl.model_validate({'number':3002,'rules':[{'id':5,'action':'deny'}]})
        baseline='#\nacl advanced 3001 name EDGE_WEB\n rule 5 deny ip\n#\nacl number 3002\n rule 5 permit ip\n#\nreturn\n'
        commands=['system-view',*render_acl(first),*render_acl(second),'return']
        for parameters in (first,second):commands=prepare_acl_commands(commands,baseline,parameters)
        self.assertEqual(commands.count('undo rule 5'),2)
        self.assertLess(commands.index('undo rule 5'),commands.index(render_acl(first)[1]))


class NamedGuest(fixtures.Guest):
    def exchange(self,command):
        if command.startswith(('acl basic name ','acl advanced name ')):
            self.commands.append(command);views=scopes(self.current)
            name=command.split()[-1].casefold()
            aliases=[context for context,lines in views.items() if '@acl-name '+name in lines]
            self.view=aliases[0] if aliases else (command,)
            views.setdefault(self.view,set());self.current=self.text(views)
            return ''
        return super().exchange(command)


class NamedTransactionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PolicyTests('test_master_gate_and_dry_run_do_not_open_a_console')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.guest=NamedGuest()

    def test_new_named_acl_replaces_only_requested_ipv4_direction(self):
        guest=self.fixture.guest
        guest.current=fixtures.BASE.replace(' mtu 1400',' mtu 1400\n packet-filter name old inbound\n packet-filter 3002 inbound hardware-count\n packet-filter 3002 outbound\n packet-filter ipv6 3002 inbound')
        result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',NAMED)
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertFalse(result['configuration_verified'])
        self.assertIn('undo packet-filter name old inbound',guest.commands)
        self.assertIn('undo packet-filter 3002 inbound',guest.commands)
        self.assertIn('packet-filter 3002 outbound',guest.current)
        self.assertIn('packet-filter ipv6 3002 inbound',guest.current)
        self.assertNotIn('packet-filter name old inbound',guest.current)
        self.assertEqual(snapshot(Path(self.fixture.project)),self.fixture.before)

    def test_named_numeric_alias_clears_stale_rule_preserving_other_ids(self):
        guest=self.fixture.guest
        guest.current=fixtures.BASE.replace('return\n','#\nacl advanced 3001 name EDGE_WEB\n rule 5 deny tcp established logging\n rule 5 comment stale\n rule 9 deny ip\n#\nreturn\n')
        result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',NAMED)
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertIn('undo rule 5',guest.commands)
        self.assertNotIn('established',guest.current)
        self.assertNotIn('stale',guest.current)
        self.assertIn('rule 9 deny ip',guest.current)

    def test_failure_after_old_binding_removal_restores_exact_baseline(self):
        guest=self.fixture.guest
        guest.current=fixtures.BASE.replace(' mtu 1400',' mtu 1400\n packet-filter name old inbound')
        baseline=guest.current;guest.fail='packet-filter name edge_web'
        result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',NAMED)
        self.assertTrue(result['protocol_rollback_verified'],result)
        self.assertFalse(result['rollback_verified'])
        self.assertEqual(guest.current,baseline)
        self.assertEqual(guest.commands.count('acl advanced name edge_web'),1)

    def test_preflight_conflicts_stop_before_acl_or_binding_changes(self):
        for suffix in ('acl basic name EDGE_WEB\n rule 5 permit source any',
                       'acl advanced name EDGE_WEB match-order auto\n rule 5 permit ip'):
            with self.subTest(suffix=suffix):
                self.fixture.guest=NamedGuest();guest=self.fixture.guest
                guest.current=fixtures.BASE.replace('return\n','#\n'+suffix+'\n#\nreturn\n')
                baseline=guest.current
                result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',NAMED)
                self.assertFalse(result['protocol_effect_verified'])
                self.assertFalse(any(command.startswith(('acl ','rule ','packet-filter ','undo packet-filter')) for command in guest.commands))
                self.assertEqual(guest.current,baseline)

    def test_generation_preserves_multiple_named_identities_and_rejects_duplicate_binding(self):
        plan=plan_fixture()
        plan['services']=[{'device':'r1','feature':'acl','parameters':NAMED|{'bindings':[]}},
                          {'device':'r1','feature':'acl','parameters':NAMED|{'name':'another','bindings':[]}}]
        result=generate_configs(plan,self.fixture.catalog)
        self.assertEqual(result['status'],'verified',result)
        self.assertIn('acl advanced name another',result['configs']['r1'])
        plan['services'][1]['parameters']['name']='edge_web'
        self.assertIn('duplicate_service',[error['code'] for error in generate_configs(plan,self.fixture.catalog)['errors']])
        plan['services']=[{'device':'r1','feature':'acl','parameters':NAMED},
                          {'device':'r1','feature':'acl','parameters':NAMED|{'name':'another'}}]
        self.assertIn('duplicate_acl_binding',[error['code'] for error in generate_configs(plan,self.fixture.catalog)['errors']])


class NamedStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_named_schema_preview_rejections_and_source_immutability(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths=configure_fixture(Path(temporary));store=ProjectStore([paths['root']],paths['output'])
            catalog=HclCatalog(paths['install'])
            project=stage_plan(store,catalog,str(paths['project']),'Named',plan_fixture(),explicit_map())['project_directory']
            before=snapshot(Path(project))
            async with mcp_session(paths) as session:
                tools={tool.name:tool for tool in (await session.list_tools()).tools}
                properties=tools['hcl_apply_acl'].inputSchema['properties']['parameters']['properties']
                self.assertIn('name',properties);self.assertIn('acl_type',properties)
                arguments={'project_path':project,'topology':'lab','device':'r1','parameters':NAMED}
                response,body=await call(session,'hcl_apply_acl',arguments)
                self.assertEqual(body['errors'][0]['code'],'writes_disabled')
                response,body=await call(session,'hcl_apply_acl',arguments|{'dry_run':True})
                self.assertFalse(response.isError)
                self.assertEqual(body['status'],'verified',body)
                self.assertIn('acl advanced name edge_web',body['commands'])
                self.assertIn('source 10.0.2.0 0.255.0.255','\n'.join(body['commands']))
                response,body=await call(session,'hcl_apply_acl',arguments|{'parameters':NAMED|{'acl_type':None},'dry_run':True})
                self.assertEqual(body['status'],'rejected')
            self.assertEqual(snapshot(Path(project)),before)
