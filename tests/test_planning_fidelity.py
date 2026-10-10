"""Observable planning semantics checked against the pinned upstream intent."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_hcl.planning import plan_topology, estimate_plan
from mcp_hcl.generation import generate_configs
from offline_fixtures import installation
from test_mcp_contract import build_fixture, mcp_session, call
from test_project_build import configure_fixture, explicit_map, snapshot


class PlanningFidelityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.catalog = installation(Path(self.temporary.name)/'install')
        for model in ('MSR36-20','S5820V2-54QS-GE','PC'):
            capacity = 80 if model=='S5820V2-54QS-GE' else 8
            (self.catalog.installation/'devicecfgs'/(model+'.cfg')).write_text(
                ' version 7.1.064\n'+''.join(f'interface GigabitEthernet0/{i}\n' for i in range(capacity)),encoding='utf-8')

    def planned(self, request):
        before = copy.deepcopy(request)
        result = plan_topology(request,self.catalog)
        self.assertTrue(result.get('valid'),result.get('errors'))
        self.assertEqual(request,before)
        self.assertFalse(result['runtime_verified'])
        self.assertFalse(result['full_live_gate_passed'])
        return result

    def population(self, result, prefix):
        return {device['id'] for device in result['plan']['devices'] if device['id'].startswith(prefix)}

    def test_scalar_and_uniform_arrays_produce_the_same_network(self):
        base = {'routers':3,'pcs_per_lan':2,'laptops_per_lan':1,'laptop_model':'PC'}
        scalar = self.planned(base)
        arrays = self.planned({**base,'pcs_per_lan':[2,2,2],'laptops_per_lan':[1,1,1]})
        self.assertEqual(scalar['plan'],arrays['plan'])
        self.assertEqual(scalar['allocation'],arrays['allocation'])
        self.assertEqual(estimate_plan(base,self.catalog)['estimate']['devices'],15)
        self.assertEqual(estimate_plan(base,self.catalog)['estimate']['links'],14)

    def test_nonuniform_counts_bind_to_the_correct_router_lan(self):
        result = self.planned({'routers':3,'pcs_per_lan':[1,2,0],
                               'laptops_per_lan':[0,1,2],'laptop_model':'PC','dhcp':True})
        self.assertEqual(self.population(result,'h'),{'h1_1_1','h2_1_1','h2_1_2'})
        self.assertEqual(self.population(result,'l'),{'l2_1_1','l3_1_1','l3_1_2'})
        links = result['plan']['links']
        for prefix, switch in (('h1_','s1_1'),('h2_','s2_1'),('l2_','s2_1'),('l3_','s3_1')):
            attached = [link['a']['device'] for link in links if link['b']['device'].startswith(prefix)]
            self.assertTrue(attached)
            self.assertEqual(set(attached),{switch})
        self.assertTrue(all(host['ipv4']=='dhcp' for host in result['plan']['host_settings']))

    def test_short_empty_and_trailing_arrays_follow_upstream_normalization(self):
        short = self.planned({'routers':3,'pcs_per_lan':[1,2]})
        self.assertEqual(short['allocation']['pcs_per_router'],[1,2,2])
        empty = self.planned({'routers':2,'pcs_per_lan':[],'laptops_per_lan':[]})
        self.assertEqual(empty['allocation']['pcs_per_router'],[3,3])
        self.assertEqual(len(self.population(empty,'h')),6)
        trailing = self.planned({'routers':2,'pcs_per_lan':[1,0,9]})
        self.assertEqual(len(self.population(trailing,'h')),1)
        self.assertEqual(len(trailing['plan']['devices']),5)

    def test_secondary_switches_do_not_duplicate_pc_or_laptop_population(self):
        request = {'routers':2,'switches_per_router':2,'pcs_per_lan':[1,2],
                   'laptops_per_lan':[1,0],'laptop_model':'PC','dhcp':True}
        result = self.planned(request)
        self.assertEqual(len(result['plan']['devices']),10)
        self.assertEqual(len(self.population(result,'h')),3)
        self.assertEqual(len(self.population(result,'l')),1)
        for link in result['plan']['links']:
            if link['b']['device'].startswith(('h','l')):
                self.assertTrue(link['a']['device'].endswith('_1'))
        self.assertEqual(estimate_plan(request,self.catalog)['estimate']['devices'],10)

    def test_zero_vlan_uses_ten_twenty_and_excess_groups_are_clamped_to_pcs(self):
        result = self.planned({'template':'router_on_a_stick','pcs_per_lan':4,'vlans':0,'dhcp':True})
        self.assertEqual(result['allocation']['effective_vlan_count'],2)
        self.assertEqual({sub['vlan'] for sub in result['plan']['subinterfaces']},{10,20})
        config = generate_configs(result['plan'],self.catalog)['configs']['r1']
        self.assertIn('vlan-type dot1q vid 20',config)
        self.assertNotIn('vlan-type dot1q vid 11',config)
        clamped = self.planned({'template':'router_on_a_stick','pcs_per_lan':2,'vlans':5})
        self.assertEqual(clamped['allocation']['effective_vlan_count'],2)
        self.assertEqual(len(clamped['plan']['subinterfaces']),2)

    def test_zero_populations_do_not_require_a_laptop_model_or_access_switch(self):
        result = self.planned({'routers':2,'switches_per_router':0,'pcs_per_lan':[0,0],'laptops_per_lan':[0,0]})
        self.assertEqual(len(result['plan']['devices']),2)
        self.assertEqual(len(result['plan']['links']),1)

    def test_invalid_array_values_fail_before_catalog_reads(self):
        invalid = [[True],['2'],[-1],[65],[2.0],[[2]],[0]*21]
        with patch.object(self.catalog,'devices',side_effect=AssertionError('invalid request reached catalog')):
            for field in ('pcs_per_lan','laptops_per_lan'):
                for value in invalid:
                    with self.subTest(field=field,value=value):
                        self.assertEqual(plan_topology({field:value},self.catalog)['status'],'rejected')

    def test_missing_host_model_is_a_business_rejection(self):
        (self.catalog.installation/'devicecfgs'/'PC.cfg').unlink()
        result = plan_topology({'pcs_per_lan':[1,0]},self.catalog)
        self.assertEqual(result['status'],'rejected')
        self.assertEqual(result['errors'][0]['code'],'planning_failed')
        self.assertIn('Unknown installed model: PC',result['errors'][0]['message'])

    def test_coordinate_rows_and_columns_do_not_overlap_host_categories(self):
        result = self.planned({'routers':2,'pcs_per_lan':[10,1],'laptops_per_lan':[2,1],'laptop_model':'PC'})
        devices = {device['id']:device for device in result['plan']['devices']}
        self.assertGreater(devices['r2']['x'],devices['h1_1_10']['x'])
        self.assertNotEqual(devices['h1_1_1']['y'],devices['l1_1_1']['y'])
        positions = [(device['x'],device['y']) for device in devices.values()]
        self.assertEqual(len(positions),len(set(positions)))

    def test_large_asymmetric_population_stays_inside_staging_coordinate_limits(self):
        result = self.planned({'routers':15,'pcs_per_lan':[64,0]})
        for device in result['plan']['devices']:
            self.assertTrue(0<=device['x']<=10000)
            self.assertTrue(0<=device['y']<=10000)
        self.assertEqual(len(self.population(result,'h')),64)


class PlanningFidelityStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_calls_accept_arrays_without_integer_coercion(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = build_fixture(Path(temporary))
            (paths['install']/'devicecfgs'/'PC.cfg').write_text('interface GigabitEthernet0/0\n',encoding='utf-8')
            async with mcp_session(paths) as session:
                tools = {tool.name:tool for tool in (await session.list_tools()).tools}
                for name in ('hcl_plan_topology','hcl_estimate_plan'):
                    branches = tools[name].inputSchema['properties']['request']['properties']['pcs_per_lan']['anyOf']
                    self.assertEqual({branch['type'] for branch in branches},{'integer','array'})
                    result, body = await call(session,name,{'request':{'pcs_per_lan':[1,0]}})
                    self.assertFalse(result.isError)
                    self.assertEqual(body['status'],'verified',body.get('errors'))
                    result, body = await call(session,name,{'request':{'pcs_per_lan':[True]}})
                    self.assertFalse(result.isError)
                    self.assertEqual(body['status'],'rejected')

    async def test_asymmetric_full_build_preserves_source_and_reloads_bound_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            (paths['install']/'devicecfgs'/'PC.cfg').write_text('interface GigabitEthernet0/0\n',encoding='utf-8')
            ini = paths['install']/'deviceInfo.ini'
            ini.write_text(ini.read_text()+
                '[S5800]\n [[0]]\n  GE = PHY_ETH_GE\n [[1]]\n  GE = PHY_ETH_GE\n'+
                '[PC]\n [[0]]\n  GE = PHY_ETH_GE\n',encoding='utf-8')
            net = next(paths['project'].glob('*.net'))
            templates = ('    [[S5820V2-54QS-GE TemplateSwitch]]\n        device_id = 3\n        slot0 = S5800 384\n        x = 0.0\n        y = 0.0\n'+
                         '    [[PC TemplateHost]]\n        device_id = 4\n        slot0 = PC 384\n        x = 0.0\n        y = 0.0\n')
            net.write_text(net.read_text().replace('[Non-vBox-DATA]',templates+'[Non-vBox-DATA]'),encoding='utf-8')
            import json
            metadata_path = paths['project']/'project.json'
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            for name,model,category in (('TemplateSwitch','S5820V2-54QS-GE','switch'),('TemplateHost','PC','pc')):
                metadata['deviceInfoList'].append({'resourceName':name,'resourceCategory':category,
                    'resourceModel':model,'resourceVersion':'test','configPath':f'DeviceConfig\\{name}.cfg'})
                (paths['project']/'DeviceConfig'/(name+'.cfg')).write_text('',encoding='utf-8')
            metadata_path.write_text(json.dumps(metadata),encoding='utf-8')
            before = snapshot(paths['project'])
            mapping = {**explicit_map(),
                       'S5820V2-54QS-GE':{'GigabitEthernet0/0':'GE_0/0','GigabitEthernet0/1':'GE_0/1'},
                       'PC':{'GigabitEthernet0/0':'GE_0/0'}}
            async with mcp_session(paths) as session:
                result, body = await call(session,'hcl_full_build',{
                    'project_path':str(paths['project']),'stage_name':'Asymmetric',
                    'request':{'pcs_per_lan':[1,0],'dhcp':True},'port_map':mapping})
                self.assertFalse(result.isError)
                self.assertEqual(body['status'],'staged',body)
                self.assertEqual((body['device_count'],body['link_count']),(5,4))
                self.assertFalse(body['configuration_verified'])
                self.assertFalse(body['full_live_gate_passed'])
                plan = json.loads((Path(body['project_directory'])/'MCPArtifacts/plan.json').read_text(encoding='utf-8'))
                self.assertEqual({host['device'] for host in plan['host_settings']},{'h1_1_1'})
                commands = (Path(body['commands_directory'])/'h1_1_1.txt').read_text()
                self.assertIn('ip address dhcp-alloc',commands)
            self.assertEqual(snapshot(paths['project']),before)
