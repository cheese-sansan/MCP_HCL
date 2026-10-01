from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_hcl.catalog import HclCatalog
from mcp_hcl.project import ProjectStore, ProjectError
from mcp_hcl.project_build import stage_plan
from test_mcp_contract import build_fixture, mcp_session, call


def configure_fixture(root):
    paths = build_fixture(root)
    (paths['install'] / 'deviceInfo.ini').write_text(
        '[PHY_PORT_VALUE]\n PHY_ETH_GE = 3\n PHY_SYNC = 56\n[MSR36]\n'
        ' [[0]]\n  GE = PHY_ETH_GE\n [[1]]\n  GE = PHY_ETH_GE\n [[2]]\n  GE = PHY_ETH_GE\n'
        ' [[3]]\n  Ser = PHY_SYNC\n', encoding='utf-8')
    net = next(paths['project'].glob('*.net'))
    text = net.read_bytes().decode('utf-8')
    text = text.replace('        slot0 = MSR36 384', '        slot0 = MSR36 384\r\n        vendor_unknown = keep this', 1)
    text += '    [[NOTE 7]]\r\n        text = "old topology"\r\n        font = "Arial,14,-1,5,75,0,0,0,0,0"\r\n'
    net.write_bytes(text.encode('utf-8'))
    return paths


def plan_fixture():
    return {'schema_version': 1, 'name': 'planned', 'devices': [
        {'id': 'r1', 'name': '计划路由器一', 'model': 'MSR36-20', 'x': 20.0, 'y': 40.0},
        {'id': 'r2', 'name': '计划路由器二', 'model': 'MSR36-20', 'x': 300.0, 'y': 40.0}],
        'links': [{'a': {'device': 'r1', 'interface': 'GigabitEthernet0/0'},
                   'b': {'device': 'r2', 'interface': 'GigabitEthernet0/1'}, 'medium': 'ethernet'}],
        'addresses': [{'device': 'r1', 'interface': 'GigabitEthernet0/0', 'cidr': '10.0.0.1/30'},
                      {'device': 'r2', 'interface': 'GigabitEthernet0/1', 'cidr': '10.0.0.2/30'}],
        'annotations': [{'text': '隔离拓扑\n第二行', 'x': 0.0, 'y': 100.0}]}


def explicit_map():
    return {'MSR36-20': {'GigabitEthernet0/0': 'GE_0/0', 'GigabitEthernet0/1': 'GE_0/1'}}


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class ProjectCompilationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = configure_fixture(Path(self.temporary.name))
        self.store = ProjectStore([self.paths['root']], self.paths['output'])
        self.catalog = HclCatalog(self.paths['install'])
        self.before = snapshot(self.paths['project'])

    def build(self, plan=None, mapping=None, name='Build'):
        return stage_plan(self.store, self.catalog, str(self.paths['project']), name,
                          plan or plan_fixture(), explicit_map() if mapping is None else mapping)

    def test_atomic_project_compilation_preserves_source_and_real_template_fields(self):
        result = self.build()
        self.assertEqual(result['status'], 'staged')
        self.assertEqual((result['device_count'], result['link_count']), (2, 1))
        directory = Path(result['project_directory'])
        inspected = self.store.inspect(str(directory))
        self.assertEqual({d['name'] for d in inspected['devices']}, {'计划路由器一', '计划路由器二'})
        self.assertEqual({d['device_id'] for d in inspected['devices']}, {3, 4})
        self.assertEqual(inspected['links'], [{'a': '计划路由器一', 'a_port': 'GE_0/0',
                                              'b': '计划路由器二', 'b_port': 'GE_0/1'}])
        net = Path(result['project_file']).read_bytes()
        self.assertIn(b'vendor_unknown = keep this', net)
        self.assertIn(b'slot0 = MSR36 384', net)
        self.assertNotIn(b'old topology', net)
        self.assertIn('text = "隔离拓扑\\n第二行"'.encode('utf-8'), net)
        self.assertFalse(net.startswith(b'\xef\xbb\xbf'))
        self.assertIn(f'workingdir = {directory}'.encode('utf-8'), net)
        self.assertEqual((directory / 'DeviceConfig/计划路由器一.cfg').read_bytes(), b'')
        commands = (directory / 'MCPArtifacts/commands/r1.txt').read_text(encoding='utf-8')
        self.assertIn('ip address 10.0.0.1 255.255.255.252', commands)
        self.assertEqual(json.loads((directory / 'MCPArtifacts/plan.json').read_text(encoding='utf-8'))['name'], 'planned')
        self.assertFalse(result['configuration_verified'])
        self.assertFalse(result['port_mapping_verified'])
        self.assertEqual(snapshot(self.paths['project']), self.before)
        copied = self.store.stage_copy(str(directory), 'CopyCompiled')
        self.assertEqual((Path(copied['project_directory']) / 'MCPArtifacts/commands/r1.txt').read_text(encoding='utf-8'), commands)

    def test_missing_or_ambiguous_maps_and_wrong_physical_types_do_not_write_project(self):
        for mapping in ({}, {'MSR36-20': {'GigabitEthernet0/0': 'GE_0/99'}},
                        {'MSR36-20': {'GigabitEthernet0/0': 'GE_0/0', 'GigabitEthernet0/1': 'GE_0/0'}},
                        {'MSR36-20': {'GigabitEthernet0/0': 'Ser_0/3', 'GigabitEthernet0/1': 'GE_0/1'}}):
            with self.subTest(mapping=mapping), self.assertRaises(ProjectError):
                self.build(mapping=mapping)
            self.assertFalse((self.paths['output'] / 'Build').exists())
        self.assertEqual(snapshot(self.paths['project']), self.before)

    def test_template_is_required_and_names_cannot_escape_config_directory(self):
        plan = plan_fixture()
        plan['devices'][0]['model'] = 'S5820V2-54QS-GE'
        with self.assertRaisesRegex(ProjectError, 'no real template'):
            self.build(plan=plan)
        for name in ('../escape', 'NUL', 'unsafe:device', 'trailing.'):
            plan = plan_fixture()
            plan['devices'][0]['name'] = name
            with self.subTest(name=name), self.assertRaises(ProjectError):
                self.build(plan=plan)
        self.assertFalse((self.paths['output'] / 'Build').exists())

    def test_unsupported_note_escaping_and_coordinate_range_are_rejected(self):
        for text in ('quote"', 'back\\slash', '\x00'):
            plan = plan_fixture()
            plan['annotations'][0]['text'] = text
            with self.assertRaises(ProjectError): self.build(plan=plan)
        plan = plan_fixture()
        plan['devices'][0]['x'] = 10001.0
        with self.assertRaises(ProjectError): self.build(plan=plan)
        self.assertEqual(snapshot(self.paths['project']), self.before)

    def test_rename_failure_cleans_temporary_stage_and_keeps_original(self):
        with patch('mcp_hcl.project.os.rename', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError): self.build()
        self.assertFalse((self.paths['output'] / 'Build').exists())
        self.assertEqual(list(self.paths['output'].glob('.hcl-stage-*')), [])
        self.assertEqual(snapshot(self.paths['project']), self.before)


class ProjectCompilationStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mcp_stage_plan_is_durable_and_does_not_claim_live_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = configure_fixture(Path(temporary))
            arguments = {'project_path': str(paths['project']), 'stage_name': 'ViaMCP',
                         'plan': plan_fixture(), 'port_map': explicit_map(), 'idempotency_key': 'build-request'}
            before = snapshot(paths['project'])
            async with mcp_session(paths) as session:
                result, body = await call(session, 'hcl_stage_plan', arguments)
                self.assertFalse(result.isError)
                self.assertEqual(body['status'], 'staged', body)
                self.assertEqual(body['verified_scope'], 'isolated_project_files_and_caller_mapping_only')
                self.assertTrue(any(e.get('source') == body['project_file'] for e in body['evidence']))
                self.assertFalse(body['live_canvas_verified'])
                self.assertFalse(body['configuration_verified'])
                first_id = body['operation_id']
            async with mcp_session(paths) as session:
                _, replay = await call(session, 'hcl_stage_plan', arguments)
                self.assertTrue(replay['replayed'])
                self.assertEqual(replay['operation_id'], first_id)
                for field in ('x', 'foo'):
                    invalid = copy.deepcopy(arguments)
                    invalid[field] = 1
                    result, body = await call(session, 'hcl_stage_plan', invalid)
                    self.assertTrue(result.isError)
            self.assertEqual(snapshot(paths['project']), before)
