"""Extended ACL intent and semantic readback, including exact replacement."""
import copy
import unittest
from pydantic import ValidationError
from mcp_hcl.services import Acl,AclRule,AclPortMatch,AclIcmpMatch
from mcp_hcl.generation import render_acl
from mcp_hcl.acl_semantics import canonical_rule,verify_acl
from test_policy import ACL,BASE
import test_policy as fixtures
from unittest.mock import Mock
from mcp_hcl.deployment import Deployment
from mcp_hcl.console import ConsoleError


class AclExtendedTests(unittest.TestCase):
    def test_every_port_operator_and_zero_boundary_render(self):
        for operator in ('eq','neq','gt','lt','range'):
            fields={'operator':operator,'port':0}
            if operator=='range':fields['end']=65535
            model=Acl.model_validate({'number':3001,'rules':[{'id':1,'action':'permit','protocol':'tcp','destination_port_match':fields}]})
            command=render_acl(model)[1]
            self.assertIn('destination-port '+operator+' 0',command)
            self.assertEqual(canonical_rule(command,True)['destination_port'],(operator,0,65535 if operator=='range' else None))

    def test_strict_operands_and_protocol_relationships(self):
        for value in ({'port':True},{'port':-1},{'port':65536},{'port':1.0},
                      {'operator':'range','port':10},{'operator':'range','port':10,'end':9},
                      {'operator':'eq','port':10,'end':20}):
            with self.assertRaises(ValidationError):AclPortMatch.model_validate(value)
        for extra in ({'protocol':'icmp','source_port_match':{'port':1}},
                      {'protocol':'udp','tcp_flags':['syn']},{'protocol':'tcp','icmp':{'type':8}},
                      {'protocol':'tcp','tcp_flags':['syn','syn']},
                      {'protocol':'tcp','tcp_flags':['established','ack']},
                      {'protocol':'tcp','source_port':1,'source_port_match':{'port':2}},
                      {'protocol':True},{'log':1},{'remark':'x\nreboot'},{'remark':'中文'}):
            with self.assertRaises(ValidationError):AclRule.model_validate({'id':1,'action':'permit'}|extra)
        with self.assertRaises(ValidationError):AclIcmpMatch.model_validate({'type':True})
        with self.assertRaises(ValidationError):Acl.model_validate({'number':2001,'rules':[{'id':1,'action':'permit','protocol':'tcp'}]})

    def test_icmp_flags_logging_and_comments_are_generated_in_rule_context(self):
        model=Acl.model_validate({'number':3001,'rules':[
            {'id':3,'action':'deny','protocol':'icmp','icmp':{'type':8,'code':0},'log':True,'remark':'Block echo only'},
            {'id':4,'action':'permit','protocol':'tcp','tcp_flags':['ack','syn']}]})
        commands=render_acl(model)
        self.assertIn('icmp-type 8 0 logging',commands[1])
        self.assertEqual(commands[2],'rule 3 comment Block echo only')
        self.assertIn('ack 1 syn 1',commands[3])
        basic=Acl.model_validate({'number':2001,'rules':[{'id':0,'action':'deny','log':True,'remark':'Basic log'}]})
        self.assertIn('logging',render_acl(basic)[1])

    def test_native_aliases_qualifier_order_and_omitted_any_match_requested_effect(self):
        model=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[
            {'id':3,'action':'deny','protocol':'icmp','icmp':{'type':8,'code':0},'log':True,'remark':'Echo'},
            {'id':5,'action':'permit','protocol':6,'source':'10.1.0.0/24','destination_port':443}]})
        config='#\nacl advanced 3001\n rule 3 deny icmp logging icmp-type echo\n rule 3 comment Echo\n rule 5 permit tcp destination-port eq https source 10.1.0.0 0.0.0.255\n#\nreturn\n'
        self.assertTrue(verify_acl(config,model))
        for changed in (config.replace('logging ','') ,config.replace('https','www'),
                        config.replace('source 10.1.0.0','source 10.2.0.0'),
                        config.replace('comment Echo','comment Other'),config.replace('icmp-type echo','icmp-type echo time-range test')):
            self.assertFalse(verify_acl(changed,model))

    def test_explicit_false_tcp_flag_and_icmp_code_difference_do_not_pass(self):
        model=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'permit','protocol':'tcp','tcp_flags':['syn']}]})
        self.assertFalse(verify_acl('#\nacl number 3001\n rule 1 permit tcp syn 0\n#\nreturn\n',model))
        icmp=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'permit','protocol':'icmp','icmp':{'type':8}}]})
        self.assertFalse(verify_acl('#\nacl number 3001\n rule 1 permit icmp icmp-type echo\n#\nreturn\n',icmp))

    def test_numeric_protocol_zero_is_distinct_from_all_ip_protocols(self):
        numeric=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'permit','protocol':0}]})
        any_ip=Acl.model_validate({'number':3001,'implicit_deny':False,'rules':[{'id':1,'action':'permit','protocol':'ip'}]})
        config='#\nacl advanced 3001\n rule 1 permit 0\n#\nreturn\n'
        self.assertTrue(verify_acl(config,numeric))
        self.assertFalse(verify_acl(config,any_ip))
        alias=config.replace('permit 0','permit ip')
        self.assertTrue(verify_acl(alias,any_ip))
        self.assertFalse(verify_acl(alias,numeric))


class AclReplacementTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PolicyTests('test_master_gate_and_dry_run_do_not_open_a_console')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
    def test_rule_replacement_removes_stale_flags_comment_and_preserves_other_ids(self):
        old='''#
acl number 3001
 rule 5 deny tcp source any destination any established logging
 rule 5 comment Old rule
 rule 6 deny ip source any destination any
#
'''
        guest=self.fixture.guest
        guest.current=BASE.replace('return\n',old+'return\n')
        result=self.fixture.engine().apply('acl',self.fixture.project,'lab','r1',ACL)
        self.assertTrue(result['protocol_effect_verified'],result)
        self.assertLess(guest.commands.index('undo rule 5'),guest.commands.index('rule 5 permit tcp source 10.1.0.0 0.0.0.255 destination 192.0.2.0 0.0.0.255 destination-port eq 443'))
        self.assertNotIn('established',guest.current)
        self.assertNotIn('Old rule',guest.current)
        self.assertIn('rule 6 deny ip source any destination any',guest.current)
        self.assertFalse(result['configuration_verified'])

    def test_native_deployment_rejects_identity_before_console_and_backup(self):
        native=Deployment(self.fixture.store,catalog=self.fixture.catalog,writes_enabled=True)
        native.runtime=Mock()
        native.runtime.resolve.side_effect=ConsoleError('Wrong running target',code='runtime_binding_unverified')
        native.session_factory=Mock()
        result=native.run(self.fixture.project,'lab')
        self.assertEqual(result['status'],'partial')
        self.assertFalse(result['configuration_verified'])
        self.assertEqual(result['backups'],[])
        native.session_factory.assert_not_called()

    def test_native_recovery_uuid_change_is_refused_before_opening(self):
        native=Deployment(self.fixture.store,catalog=self.fixture.catalog,writes_enabled=True)
        native.runtime=Mock();native.runtime.resolve.return_value={'vm_uuid':'new'}
        native.session_factory=Mock()
        document,bindings=native.bindings(self.fixture.project)
        with self.assertRaises(ConsoleError) as caught:native.open_channel(document,bindings['r1'],'lab','old')
        self.assertEqual(caught.exception.code,'recovery_target_changed')
        native.session_factory.assert_not_called()
