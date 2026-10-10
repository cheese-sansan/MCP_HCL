"""Bound readback, native PID rejection and formatter conformance; no HCL guests."""
import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from mcp_hcl.console import ConsoleError,ConsoleSession,open_console_pipe
from mcp_hcl.inspection import Inspection,reply_body,QUERIES
from mcp_hcl.readback import ReadbackError,interface_states,vlan_database,qos_definitions
from mcp_hcl.runtime_binding import RuntimeBinding
from mcp_hcl.project import ProjectStore
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.project_build import stage_plan
from test_project_build import configure_fixture,plan_fixture,explicit_map
from test_console import NamedPipeServer
from test_mcp_contract import mcp_session,call


PORTS='''GigabitEthernet0/0
Current state: UP
Line protocol state: UP
IP packet frame type: Ethernet II, hardware address: 0011-2233-4455
Internet address: 10.3.0.1/24 (Primary)
The Maximum Transmit Unit is 1500
1000Mbps-speed mode, full-duplex mode
GigabitEthernet0/1 current state: DOWN (Administratively)
Line protocol current state: DOWN
'''
VLANS='''VLAN ID: 1
VLAN type: Static
Route interface: Not configured
Description: Management
Name: VLAN 0001
Tagged ports: None
Untagged ports:
 GigabitEthernet0/1
VLAN ID: 10
VLAN type: Static
Name: Application
Tagged ports: GigabitEthernet0/0
Untagged ports: None
'''
CLASSIFIERS='''User-defined classifier information:
Classifier: web (ID 17)
 Operator: AND
 Rule(s) :
  If-match acl 3001
'''
BEHAVIORS='''User-defined behavior information:
Behavior: mark (ID 18)
 Marking:
  Remark dscp 46
'''
POLICIES='''User-defined QoS policy information:
Policy: edge (ID 19)
 Classifier: web (ID 17)
  Behavior: mark
   Marking:
    Remark dscp 46
'''


def reply(command,body):
    raw=(command+'\r\n'+body+'\r\n<R1>').encode()
    return {'command':command,'complete':True,'raw_output_b64':base64.b64encode(raw).decode(),
            'output_sha256':hashlib.sha256(raw).hexdigest(),'request_sha256':hashlib.sha256(command.encode()).hexdigest()}


class FormatterTests(unittest.TestCase):
    def test_interface_formats_preserve_reported_values_without_cable_guessing(self):
        parsed=interface_states(PORTS)
        self.assertEqual(len(parsed),2)
        self.assertEqual(parsed[0]['mac'],'00:11:22:33:44:55')
        self.assertEqual(parsed[0]['ipv4']['netmask'],'255.255.255.0')
        self.assertEqual((parsed[0]['mtu'],parsed[0]['speed_bps'],parsed[0]['duplex']),(1500,1000000000,'full'))
        self.assertTrue(parsed[1]['administratively_down'])
        self.assertTrue(all(row['linked'] is None for row in parsed))
        self.assertFalse(any(row['live_cable_inventory_verified'] for row in parsed))

    def test_detailed_vlan_rows_and_wrapped_ports_are_strict(self):
        parsed=vlan_database(VLANS)
        self.assertEqual([row['number'] for row in parsed],[1,10])
        self.assertEqual(parsed[0]['untagged_ports'],['GigabitEthernet0/1'])
        self.assertIsNone(parsed[0]['is_default'])
        for text in ('nothing',VLANS.replace('VLAN ID: 10','VLAN ID: 1'),VLANS.replace('VLAN ID: 10','VLAN ID: 4095')):
            with self.assertRaises(ReadbackError):vlan_database(text)

    def test_qos_id_annotations_and_binding_names(self):
        self.assertEqual(qos_definitions(CLASSIFIERS,'classifiers')[0]['rules'],['If-match acl 3001'])
        self.assertEqual(qos_definitions(BEHAVIORS,'behaviors')[0]['name'],'mark')
        self.assertEqual(qos_definitions(POLICIES,'policies')[0]['classes'],[{'classifier':'web','behavior':'mark'}])
        for text,kind in (('User-defined classifier information:','classifiers'),
                          (POLICIES.replace('Behavior: mark','Something: mark'),'policies'),
                          ('unrecognized','behaviors')):
            with self.assertRaises(ReadbackError):qos_definitions(text,kind)

    def test_partial_states_and_tampered_transcript_are_not_empty_success(self):
        with self.assertRaises(ReadbackError):interface_states(PORTS.replace('Line protocol state: UP',''))
        response=reply('display interface',PORTS)
        self.assertIn('GigabitEthernet0/0',reply_body(response,'display interface'))
        for changed in ({'complete':False},{'output_sha256':'0'*64},{'request_sha256':'0'*64}):
            with self.assertRaises(ReadbackError):reply_body(response|changed,'display interface')


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);paths=configure_fixture(self.root)
        self.store=ProjectStore([paths['root']],paths['output'])
        self.project=stage_plan(self.store,HclCatalog(paths['install']),str(paths['project']),'Inspect',plan_fixture(),explicit_map())['project_directory']
        self.commands=[]

    def engine(self,*,binding_error=False,response_override=None):
        commands=self.commands
        class Binder:
            def resolve(self,doc,binding,topology):
                if binding_error:raise ConsoleError('Wrong VM identity',code='runtime_binding_unverified')
                return {'vm_uuid':'synthetic','device_id':binding['device_id']}
            def verify_pipe(self,channel,target):return {**target,'verified_scope':'synthetic_binding_only'}
        class Channel:
            native_channel=True  # Even this injected claim must not elevate a mock.
            def __init__(self,pipe):self.history=[]
            def exchange(self,command):
                commands.append(command)
                body={'display interface':PORTS,'display vlan all':VLANS,
                      QUERIES['qos'][0]:CLASSIFIERS,QUERIES['qos'][1]:BEHAVIORS,QUERIES['qos'][2]:POLICIES}[command]
                response=reply(command,response_override if response_override is not None else body)
                self.history.append(response);return response
            def __enter__(self):return self
            def __exit__(self,*args):pass
        return Inspection(self.store,writes_enabled=True,runtime_binding=Binder(),session_factory=Channel)

    def test_default_gate_and_failed_identity_send_no_commands(self):
        self.assertEqual(Inspection(self.store).read('ports','missing','lab')['errors'][0]['code'],'writes_disabled')
        result=self.engine(binding_error=True).read('ports',self.project,'lab','r1')
        self.assertEqual(result['status'],'unverified')
        self.assertEqual(self.commands,[])

    def test_vlans_and_qos_report_typed_facts_but_injected_channels_are_not_native(self):
        engine=self.engine()
        result=engine.read('vlans',self.project,'lab','计划路由器一')
        self.assertEqual(result['status'],'output_received')
        self.assertEqual(len(result['devices'][0]['vlans']),2)
        self.assertFalse(result['native_readback_verified'])
        qos=engine.read('qos',self.project,'lab','r1')
        self.assertEqual(qos['devices'][0]['policies'][0]['classes'][0]['behavior'],'mark')
        self.assertEqual(self.commands,['display vlan all',*QUERIES['qos']])
        self.assertTrue(all(command.startswith('display ') for command in self.commands))
        self.assertFalse(qos['full_live_gate_passed'])

    def test_unrecognized_output_retains_failure_transcript_and_link_filter_never_guesses(self):
        engine=self.engine(response_override='unsupported output')
        result=engine.read('ports',self.project,'lab','r1')
        self.assertEqual(result['status'],'unverified')
        transcript=Path(result['evidence'][0]['source'])
        self.assertIn('unsupported output',base64.b64decode(json.loads(transcript.read_text())[0]['raw_output_b64']).decode())
        self.commands.clear()
        filtered=engine.read('ports',self.project,'lab','r1',True)
        self.assertEqual(filtered['errors'][0]['code'],'live_cable_inventory_unverified')
        self.assertEqual(self.commands,[])


class RuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.home=Path(self.temporary.name)
        self.project=self.home/'staged';(self.project/'ConfigDisk').mkdir(parents=True)
        self.net=self.project/'project.net';self.net.write_text('synthetic net')
        self.disk=self.project/'ConfigDisk/device3.vdi';self.disk.write_bytes(b'synthetic disk')
        self.cfg=self.home/'HCL VMs/lab/device3/lab-device3.vbox';self.cfg.parent.mkdir(parents=True)
        self.vm_uuid=str(uuid4());self.disk_uuid=str(uuid4())
        self.cfg.write_text(f'<VirtualBox><Machine name="lab-device3" uuid="{{{self.vm_uuid}}}"><MediaRegistry><HardDisks><HardDisk uuid="{{{self.disk_uuid}}}" location="{self.disk.as_posix()}"/></HardDisks></MediaRegistry><Hardware><UART><Port hostMode="HostPipe" server="true" path="\\\\.\\pipe\\lab-device3"/></UART></Hardware><StorageControllers><StorageController><AttachedDevice type="HardDisk"><Image uuid="{{{self.disk_uuid}}}"/></AttachedDevice></StorageController></StorageControllers></Machine></VirtualBox>')
        self.values={'name':'lab-device3','UUID':self.vm_uuid,'VMState':'running','CfgFile':str(self.cfg),'IDE-0-0':str(self.disk)}
        self.document=SimpleNamespace(directory=self.project,net_path=self.net)
    def binder(self):
        def run(args,**kwargs):
            data=json.dumps({'profile':str(self.home),'sid':'S-1-5-21-1','vbox':'D:/VBox'}).encode() if args[0]=='powershell.exe' else '\n'.join(key+'='+json.dumps(value) for key,value in self.values.items()).encode()
            return SimpleNamespace(returncode=0,stdout=data)
        return RuntimeBinding(runner=run)
    def test_running_descriptor_registered_storage_and_project_disk_are_all_required(self):
        target=self.binder().resolve(self.document,{'device_id':3},'lab')
        self.assertEqual(target['vm_uuid'],self.vm_uuid)
        self.assertFalse(target['runtime_isolation_verified'])
        for field,value in (('UUID',str(uuid4())),('VMState','poweroff'),('CfgFile',str(self.home/'other.vbox')),('IDE-0-0',str(self.home/'other.vdi'))):
            before=self.values[field];self.values[field]=value
            with self.subTest(field=field),self.assertRaises(ConsoleError):self.binder().resolve(self.document,{'device_id':3},'lab')
            self.values[field]=before
    def test_declaring_but_not_attaching_a_project_disk_fails(self):
        self.cfg.write_text(self.cfg.read_text().replace('<Image uuid="{'+self.disk_uuid+'}"/>',''))
        with self.assertRaises(ConsoleError):self.binder().resolve(self.document,{'device_id':3},'lab')
    def test_real_pipe_server_that_is_not_a_virtualbox_process_is_rejected(self):
        pipe=rf'\\.\pipe\identity{uuid4().hex}-device1'
        server=NamedPipeServer(pipe);server.start()
        fd=open_console_pipe(pipe,timeout=1)
        channel=SimpleNamespace(session=ConsoleSession(fd))
        binder=RuntimeBinding(runner=lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout=json.dumps({
            'name':'python.exe','sid':'S-1-5-21-1','owner_result':0,'command':'--startvm '+self.vm_uuid}).encode()))
        try:
            with self.assertRaises(ConsoleError):binder.verify_pipe(channel,{'owner_sid':'S-1-5-21-1','vm_uuid':self.vm_uuid})
            self.assertEqual(server.received,[])
        finally:channel.session.close();server.close()


class InspectionStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspection_surface_is_visible_and_all_queries_are_off_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths=configure_fixture(Path(temporary))
            async with mcp_session(paths) as session:
                names={tool.name for tool in (await session.list_tools()).tools}
                self.assertTrue({'hcl_inspect_ports','hcl_read_vlans','hcl_read_qos'}<=names)
                for tool in ('hcl_inspect_ports','hcl_read_vlans','hcl_read_qos'):
                    response,body=await call(session,tool,{'project_path':'missing','topology':'lab','device':'r1'})
                    self.assertFalse(response.isError)
                    self.assertEqual(body['errors'][0]['code'],'writes_disabled')
                    self.assertFalse(body['full_live_gate_passed'])
