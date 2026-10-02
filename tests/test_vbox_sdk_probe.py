import importlib.util
import unittest
import tempfile
import zipfile
import hashlib
from unittest.mock import patch
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'scripts/hcl_vbox_sdk_probe.py'
spec=importlib.util.spec_from_file_location('sdk_probe',path)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class SdkComparisonTests(unittest.TestCase):
    def test_coclass_reference_cannot_shadow_a_real_interface_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'sdk.zip'
            xml='<idl>'+''.join('<interface name="'+name+'" uuid="id"><method name="'+members[0]+'"/></interface>' for name,members in probe.MEMBERS.items())+'<coclass><interface name="IVirtualBox" default="yes"/></coclass></idl>'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('sdk/bindings/VirtualBox.xidl',xml)
                z.writestr('sdk/installer/vboxapi/__init__.py','pass')
                z.writestr('sdk/installer/vboxapi/VirtualBox_constants.py','pass')
            expected=hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.dict(probe.HASHES,{'6.0.14':expected}):
                result=probe.read_sdk(archive,'6.0.14')
            self.assertIn('findMachine',result['interfaces']['IVirtualBox']['members'])
            with self.assertRaisesRegex(ValueError,'SHA256'):probe.read_sdk(archive,'6.0.14')

    def fixture(self):
        return {'version':'test','interfaces':{i:{'uuid':'old','members':{m:{'kind':'method','params':[]} for m in names}}
                    for i,names in probe.MEMBERS.items()},'enums':{e:{'Known':'1'} for e in probe.ENUMS}}

    def test_same_selected_surface_is_not_runtime_success(self):
        result=probe.compare(self.fixture(),self.fixture())
        self.assertTrue(result['selected_declarations_compatible'])
        self.assertIsNone(result['hcl_runtime_compatible'])
        self.assertFalse(result['installer_executed'])
        self.assertFalse(result['full_live_gate_passed'])

    def test_signature_enum_and_missing_member_changes_are_distinct(self):
        before=self.fixture();after=self.fixture()
        after['interfaces']['IMachine']['members']['launchVMProcess']['params']=[{'safearray':'yes'}]
        del after['interfaces']['ISession']['members']['machine']
        after['enums']['MachineState']['Known']='2'
        result=probe.compare(before,after)
        self.assertFalse(result['selected_declarations_compatible'])
        self.assertEqual({r['state'] for r in result['members']},{'same','changed','missing'})
        self.assertFalse(next(r for r in result['enums'] if r['enum']=='MachineState')['existing_values_unchanged'])
