import json
import shutil
import tempfile
import unittest
from pathlib import Path
from mcp_hcl.evidence import collect_evidence, audit_evidence, import_evidence
from mcp_hcl.catalog import HclCatalog, CatalogError
from test_project_build import configure_fixture


def captured(root):
    paths=configure_fixture(root)
    cfg=root/'saved.cfg';cfg.write_text('#\n version 7.1\ninterface GigabitEthernet0/0\n#\nreturn\n')
    spec={'project_directory':str(paths['project']),'installation':str(paths['install']), 'hcl_version':'5.10.3',
          'devices':[{'name':'device1','control_kind':'comware','configuration':str(cfg)}]}
    # Fixture names are derived from actual parser output rather than assumed.
    from mcp_hcl.project import ProjectStore
    spec['devices'][0]['name']=next(iter(ProjectStore([paths['project']],root/'out')._open(str(paths['project'])).sections))
    source=root/'captured';collect_evidence(spec,source)
    return paths,source


class Evidence050Tests(unittest.TestCase):
    def test_import_concurrency_restart_and_write_failure_preserve_sources(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        import subprocess,sys
        from mcp_hcl.artifact_store import tree_hash
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,source=captured(root);before=tree_hash(source);output=root/'output'
            with patch('mcp_hcl.evidence.shutil.copytree',side_effect=OSError('simulated disk failure')):
                with self.assertRaises(OSError):import_evidence(source,output,'Shared','same')
            with ThreadPoolExecutor(max_workers=3) as pool:
                results=list(pool.map(lambda _:import_evidence(source,output,'Shared','same'),range(3)))
            self.assertEqual(len({r['operation_id'] for r in results}),1)
            command=[sys.executable,'-B','-m','mcp_hcl.lab_bundle','import','--directory',str(source),'--output-root',str(output),'--name','Shared','--idempotency-key','same']
            result=subprocess.run(command,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['operation_id'],results[0]['operation_id'])
            self.assertEqual(tree_hash(source),before)

    def test_phone_differences_do_not_prove_field_semantics_or_psk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=configure_fixture(root)
            net=next(paths['project'].glob('*.net'));text=net.read_text()
            marker='[Non-vBox-DATA]'
            position=text.index(marker)
            phone='    [[Phone phone1]]\n        device_id = 3\n        slot0 = Phone 64\n        x = 0.0\n        y = 0.0\n        z = 5.0\n        observed_field = old\n'
            text=text[:position]+phone+text[position:];net.write_text(text)
            metadata=json.loads((paths['project']/'project.json').read_text())
            row=dict(metadata['deviceInfoList'][0]);row.update(resourceName='phone1',configPath='DeviceConfig\\phone1.cfg')
            metadata['deviceInfoList'].append(row);(paths['project']/'project.json').write_text(json.dumps(metadata))
            with (paths['install']/'deviceInfo.ini').open('a') as f:f.write('[Phone]\n [[1]]\n  WLAN-Radio = PHY_RADIO\n')
            before=root/'before.net';after=root/'after.net';page=root/'page.png'
            before.write_text(text);after.write_text(text.replace('observed_field = old','observed_field = new'));page.write_bytes(b'private-page-test-only')
            source=root/'phone-evidence'
            collect_evidence({'project_directory':str(paths['project']),'installation':str(paths['install']),'hcl_version':'5.10.3',
                'devices':[{'name':'phone1','control_kind':'native_gui','phone_before':str(before),'phone_after':str(after),'phone_page':str(page)}]},source)
            profile=audit_evidence(source)['profiles'][0]
            self.assertEqual(profile['default_interfaces'],[])
            self.assertEqual(profile['observed_changed_fields'],['observed_field'])
            self.assertFalse(profile['native_settings_supported'])
            self.assertNotIn('wpa2_psk',profile['capabilities']['wireless_security'])

    def test_native_readback_history_and_failed_receipts_are_preserved(self):
        from unittest.mock import patch
        from mcp_hcl.console import ConsoleError
        from mcp_hcl.evidence import digest
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths=configure_fixture(root)
            from mcp_hcl.project import ProjectStore
            doc=ProjectStore([paths['project']],root/'out')._open(str(paths['project']))
            gui=root/'gui.json';gui.write_text(json.dumps({'status':'verified','project_identity_verified':True,'target_project':str(doc.net_path)}))
            spec={'project_directory':str(paths['project']),'installation':str(paths['install']),'hcl_version':'5.10.3','native_readbacks':True,
                  'topology':'topo1','gui_receipt':str(gui),'devices':[{'name':next(iter(doc.sections)),'control_kind':'comware'}]}
            class Channel:
                def __init__(self,*args):self.history=[]
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def exchange(self,command):
                    body={'display current-configuration':'#\n version 7.1\ninterface GigabitEthernet0/0\n#\nreturn',
                          'display version':'Comware Software, Version 7.1','display interface':'GigabitEthernet0/0 current state: UP'}[command]
                    text=f'<device>{command}\n{body}\n<device>';raw=text.encode()
                    result={'command':command,'complete':True,'output':text,'raw_output_b64':base64.b64encode(raw).decode(),
                            'output_sha256':digest(raw),'request_sha256':digest(command.encode())}
                    self.history.append(result);return result
            with patch('mcp_hcl.cli_session.PersistentConsole',Channel):
                result=collect_evidence(spec,root/'native')
            self.assertFalse(result['runtime_verified'])
            self.assertEqual(result['origin']['capture_method'],'native_console')
            class Broken(Channel):
                def exchange(self,command):
                    self.history.append({'command':command,'complete':False,'raw_output_b64':'aW5jb21wbGV0ZQ=='})
                    raise ConsoleError('Continuous output timeout',code='prompt_timeout',detail={'stage':'read'})
            with patch('mcp_hcl.cli_session.PersistentConsole',Broken):
                result=collect_evidence(spec,root/'failed')
            self.assertEqual(result['status'],'partial')
            self.assertTrue((root/'failed/capture-failed.json').is_file())
            self.assertEqual(result['errors'][0]['code'],'prompt_timeout')
            self.assertIn('incomplete',base64.b64decode(json.loads((root/'failed/sources/0-failed-transcript.json').read_text())[0]['raw_output_b64']).decode())

    def test_hcl_and_firmware_version_mismatch_rejected(self):
        from mcp_hcl.evidence import digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,source=captured(root)
            original=json.loads((source/'manifest.json').read_text())
            original['origin']['hcl_version']='5.10.1';(source/'manifest.json').write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError,'HCL version'):audit_evidence(source)
            original['origin']['hcl_version']='5.10.3';path=source/'sources/version.txt';path.write_text('Comware Software, Version 8.0')
            original['models'][0]['version_readback']='sources/version.txt'
            original['files'].append({'path':'sources/version.txt','role':'version_readback','sha256':digest(path.read_bytes()),'original_source':'test'})
            (source/'manifest.json').write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError,'Firmware version'):audit_evidence(source)

    def test_move_import_retry_and_catalog_without_runtime_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths,source=captured(root)
            moved=root/'relocated';shutil.copytree(source,moved);shutil.rmtree(source)
            audited=audit_evidence(moved)
            self.assertFalse(audited['runtime_verified'])
            self.assertIn('MSR36-20: version_readback',audited['missing'])
            output=root/'profiles'
            first=import_evidence(moved,output,'Router','same');second=import_evidence(moved,output,'Router','same')
            self.assertEqual(first['operation_id'],second['operation_id']);self.assertTrue(second['replayed'])
            model=HclCatalog(paths['install'],output).device_details('MSR36-20')['device']
            self.assertEqual(model['default_firmware'],'7.1');self.assertFalse(model['mapping_verified'])
            self.assertFalse(model['runtime_verified'])
            (Path(first['artifact_directory'])/'import-report.json').write_text('tampered')
            self.assertEqual(import_evidence(moved,output,'Router','same')['errors'][0]['code'],'artifact_changed')

    def test_hash_unknown_flags_traversal_duplicates_and_test_origin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,source=captured(root)
            original=json.loads((source/'manifest.json').read_text())
            variations=[]
            import copy
            for change in ('flag','traversal','duplicate','identity'):
                manifest=copy.deepcopy(original)
                if change=='flag': manifest['runtime_verified']=True
                if change=='traversal': manifest['files'][0]['path']='../escape.net'
                if change=='duplicate': manifest['files'].append(manifest['files'][0])
                if change=='identity': manifest['models'][0]['device_id']=999
                variations.append(manifest)
            for manifest in variations:
                (source/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError): audit_evidence(source)
            manifest=original;manifest['origin']['capture_method']='test_fixture'
            (source/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Synthetic'): import_evidence(source,root/'out','Fake')
            (source/'manifest.json').write_text(json.dumps(original))
            (source/original['models'][0]['configuration']).write_text('changed')
            with self.assertRaises(ValueError): audit_evidence(source)

    def test_missing_sources_conflicting_profiles_and_input_key_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);paths,source=captured(root)
            import_evidence(source,root/'out','One','key')
            self.assertEqual(import_evidence(source,root/'out','Other','key')['errors'][0]['code'],'idempotency_conflict')
            import_evidence(source,root/'out','Two')
            with self.assertRaisesRegex(CatalogError,'Duplicate'): HclCatalog(paths['install'],root/'out').devices()
            manifest=json.loads((source/'manifest.json').read_text());(source/manifest['models'][0]['configuration']).unlink()
            with self.assertRaises(ValueError): audit_evidence(source)
