import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from mcp_hcl.security_audit import SecurityAudit,comware_posture,credential_storage,audit_findings
from mcp_hcl.readback import ReadbackError
from software_fixtures import SoftwareCase

SECRET='SyntheticSecret17';CIPHER='SyntheticCipher17'
CONFIG='#\nversion 7.1.064\nheader motd ^\ntelnet server enable\nlocal-user bannerfake\n password simple fake\n^\n#\nlocal-user alice class manage\n password simple '+SECRET+'\n service-type ssh\n authorization-attribute user-role network-admin\n#\nline vty 0 4\n authentication-mode scheme\n protocol inbound ssh\n#\nreturn\n'

class AuditTests(SoftwareCase):
    def engine(self):
        binder,channel=self.dependencies()
        return SecurityAudit(self.store,writes_enabled=True,runtime_binding=binder,session_factory=channel)
    def setUp(self):super().setUp();self.guest.responses['display current-configuration']=CONFIG
    def assert_private(self,result):
        text=self.serialized(result)
        for value in (SECRET,CIPHER,base64.b64encode(CONFIG.encode()).decode(),hashlib.sha256(CONFIG.encode()).hexdigest(),'raw_output_b64','output_sha256','request_sha256'):
            self.assertNotIn(value,text)
        self.assert_synthetic(result);self.assertIsNone(result['secure'])
        for channel in self.channels:self.assertEqual(channel.history,[])
    def test_banner_fake_commands_storage_and_unknown_algorithms(self):
        posture=comware_posture(CONFIG)
        self.assertEqual([u['name'] for u in posture['local_users']],['alice']);self.assertIsNone(posture['telnet_server_explicit'])
        self.assertTrue(posture['banner_motd_set'])
        for command,expected in [('password simple hash','plaintext'),('password simple cipher','plaintext'),
            ('password hash '+CIPHER,'hash_algorithm_unknown'),('password cipher '+CIPHER,'cipher_algorithm_unknown'),('password '+SECRET,'unknown')]:
            self.assertEqual(credential_storage(command),expected)
        self.assertEqual(audit_findings('r1',posture)[0]['code'],'USER_CREDENTIAL_REVERSIBLE')
    def test_footer_version_duplicate_users_and_banner_conflicts(self):
        for text in (CONFIG.replace('return',''),CONFIG.replace('version 7.1.064','version 7.1.064\nversion 7.1.065'),
            CONFIG.replace('^\n#\nlocal-user','not-closed\n#\nlocal-user'),CONFIG.replace('line vty','local-user alice\n#\nline vty')):
            with self.subTest(text=text):
                with self.assertRaises(ReadbackError):comware_posture(text)
    def test_success_is_private_synthetic_and_sorted_with_unknown_rules(self):
        result=self.engine().read(self.project,'lab')
        self.assertEqual(result['devices_audited'],2,result);self.assert_private(result)
        self.assertEqual(result['rule_mapping']['USER_CREDENTIAL_WEAK_ALGO'],'unverified_algorithm')
        self.assertTrue(all(row['severity']=='high' for row in result['findings']))
    def test_old_user_interface_plaintext_roles_and_remote_aaa_unknown(self):
        text='#\nversion 5.20\nsuper password simple '+SECRET+'\nlocal-user old\n password cipher '+CIPHER+'\n#\nuser-interface vty 0 4\n authentication-mode none\n set authentication password simple '+SECRET+'\n#\nreturn\n'
        posture=comware_posture(text)
        self.assertEqual(posture['local_users'][0]['credential_storage'],'cipher_algorithm_unknown')
        self.assertEqual(posture['access_lines'][0]['authentication'],'none')
        self.assertEqual(posture['access_lines'][0]['credential_storage'],'plaintext')
        without=comware_posture('#\nversion 7.1\n#\nreturn\n')
        self.assertEqual(audit_findings('r1',without)[0]['severity'],'low')
    def test_gate_strict_timeout_bad_target_and_pc_exclusion(self):
        self.assertEqual(SecurityAudit(self.store).read('missing','lab')['errors'][0]['code'],'writes_disabled')
        for timeout in (True,0,601,'120'):
            self.assertEqual(self.engine().read(self.project,'lab',timeout_seconds=timeout)['status'],'rejected')
        self.assertEqual(self.engine().read(self.project,'lab',device='missing')['status'],'rejected')
        binder,channel=self.dependencies();engine=SecurityAudit(self.store,writes_enabled=True,runtime_binding=binder,session_factory=channel)
        original=engine.staged.bindings
        def bindings(path):
            doc,rows=original(path);rows['r2']['model']='PC';return doc,rows
        engine.staged.bindings=bindings
        result=engine.read(self.project,'lab');self.assertEqual(result['skipped_hosts'],['r2']);self.assertEqual(result['devices_audited'],1)
    def test_failures_truncation_timeout_close_and_receipt_never_leak(self):
        for mode in ('truncated','hash','reject','close','timeout','receipt'):
            with self.subTest(mode=mode):
                self.reply_changes={'complete':False} if mode=='truncated' else {'output_sha256':'0'*64} if mode=='hash' else {}
                self.guest.fail=(lambda cmd:True) if mode=='reject' else None;self.guest.close_error=mode=='close'
                self.guest.on_exchange=(lambda cmd:self.clock.advance(2)) if mode=='timeout' else None
                original=Path.write_text
                def write(path,*a,**k):
                    if mode=='receipt' and '.security-audit-receipts' in path.parts:raise OSError(SECRET)
                    return original(path,*a,**k)
                with patch.object(Path,'write_text',write),patch('mcp_hcl.reconciliation.time.monotonic',self.clock):
                    result=self.engine().read(self.project,'lab',timeout_seconds=1)
                self.assertTrue(result['errors'],result);self.assert_private(result)

    def test_partial_device_and_stage_change_revoke_attribution(self):
        self.guest.fail=lambda cmd:len(self.guest.commands)>1
        result=self.engine().read(self.project,'lab')
        self.assertEqual(result['devices_audited'],1);self.assertTrue(result['errors']);self.assert_private(result)
        self.guest.fail=None
        def change(cmd):
            p=Path(self.project)/'MCPArtifacts/stage-receipt.json'
            p.write_text(p.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        self.guest.on_exchange=change
        result=self.engine().read(self.project,'lab')
        self.assertIn('audit_stage_changed',[e['code'] for e in result['errors']]);self.assert_private(result)
