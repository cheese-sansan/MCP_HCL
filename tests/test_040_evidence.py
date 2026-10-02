import hashlib,json,tempfile,unittest
from pathlib import Path
from mcp_hcl.catalog import HclCatalog,CatalogError
from mcp_hcl.live_acceptance import ospf_peers,accept_lab
from mcp_hcl.project import ProjectStore
from mcp_hcl.deployment import Deployment
from test_project_build import configure_fixture


class Evidence040Tests(unittest.TestCase):
    def test_captured_profiles_require_matching_real_source_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths=configure_fixture(Path(temporary));profile=Path(temporary)/'profiles';profile.mkdir()
            net=next(paths['project'].glob('*.net'));cfg=paths['install']/'devicecfgs/MSR36-20.cfg'
            record={'schema_version':1,'model':'MSR36-20','interfaces':['GigabitEthernet0/0','GigabitEthernet0/1','GigabitEthernet0/2','Serial1/0','NULL0'],
                    'firmware':__import__('re').search(r'^\s*version\s+(.+)$', cfg.read_text(), __import__('re').M)[1].strip(),'evidence':[{'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (net,cfg)]}
            (profile/'model.json').write_text(json.dumps(record),encoding='utf-8')
            catalog=HclCatalog(paths['install'],profile)
            model=catalog.device_details('MSR36-20')['device']
            self.assertEqual(model['interface_evidence_scope'],'captured_configuration_only')
            self.assertFalse(model['factory_defaults_verified'])
            cfg.write_text('tampered')
            with self.assertRaises(CatalogError): catalog.devices()

    def test_neighbor_parser_does_not_count_the_local_router_id(self):
        text='OSPF Process 1 with Router ID 192.0.2.1\nRouter ID: 192.0.2.2\nState: Full\n'
        self.assertEqual(ospf_peers(text),{'192.0.2.2'})

    def test_live_gate_is_rejected_before_hardware_when_disabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            engine=Deployment(ProjectStore([root],root/'output'))
            with self.assertRaisesRegex(ValueError,'live write switch'):
                accept_lab(engine,'missing','lab','missing.json')
