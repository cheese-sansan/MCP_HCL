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
