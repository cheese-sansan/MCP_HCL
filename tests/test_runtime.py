import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mcp_hcl.runtime import inspect_runtime


class RuntimeInventoryTests(unittest.TestCase):
    def test_denied_profile_or_registry_namespace_is_unknown_not_empty(self):
        import os
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);registry=home/'.VirtualBox';registry.mkdir()
            scandir=os.scandir
            for denied in (home,registry):
                def guarded(path):
                    if Path(path)==denied:raise PermissionError('Namespace denied')
                    return scandir(path)
                with patch('mcp_hcl.runtime.os.scandir',side_effect=guarded):
                    result=inspect_runtime(home)
                self.assertEqual(result['status'],'unknown')
                self.assertNotIn('file_count',result)
                self.assertFalse(result['activation_allowed'])
                self.assertEqual(result['errors'][0]['code'],'runtime_observation_unknown')

    def test_empty_profile_never_proves_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = inspect_runtime(Path(temporary))
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['file_count'],0)
        self.assertFalse(result['activation_allowed'])
        self.assertFalse(result['runtime_isolation_verified'])

    def test_registered_base_and_historical_disks_are_observed_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            runtime = home/'HCL VMs'/'topo1'/'device1'
            runtime.mkdir(parents=True)
            disk = runtime/'snapshot.vdi'
            disk.write_bytes(b'guest data')
            descriptor = runtime/'topo1-device1.vbox'
            descriptor.write_text('<VirtualBox/>')
            registry = home/'.VirtualBox'/'VirtualBox.xml'
            registry.parent.mkdir()
            registry.write_text('<VirtualBox xmlns="urn:virtualbox"><MachineRegistry><MachineEntry uuid="{base}" src="original/Simware_Base.vbox"/></MachineRegistry></VirtualBox>')
            before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (disk,descriptor,registry)}
            result = inspect_runtime(home)
            self.assertEqual(result['status'],'observed')
            self.assertEqual(result['file_count'],2)
            self.assertEqual(result['registered_machines'][0]['uuid'],'{base}')
            self.assertIn('existing_runtime_assets',[b['code'] for b in result['blockers']])
            self.assertNotIn('sha256',next(record for record in result['files'] if record['path'].endswith('.vdi')))
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
            self.assertFalse(result['disk_bytes_verified'])

    def test_malformed_registry_and_inventory_limits_are_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            registry = home/'.VirtualBox'/'VirtualBox.xml'
            registry.parent.mkdir()
            for text in ('bad xml','<!DOCTYPE x [<!ENTITY y "z">]><VirtualBox/>'):
                registry.write_text(text)
                result = inspect_runtime(home)
                self.assertEqual(result['status'],'unknown')
                self.assertFalse(result['activation_allowed'])
            registry.unlink()
            root = home/'HCL VMs'
            root.mkdir()
            for index in range(3): (root/f'{index}.vbox').write_text('<VirtualBox/>')
            self.assertEqual(inspect_runtime(home,max_entries=1)['status'],'unknown')

    def test_linked_runtime_and_unreadable_registry_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch('mcp_hcl.runtime._linked',return_value=True):
                self.assertEqual(inspect_runtime(home)['status'],'unknown')
            registry = home/'.VirtualBox'/'VirtualBox.xml'
            registry.parent.mkdir()
            registry.write_text('<VirtualBox/>')
            with patch.object(Path,'read_bytes',side_effect=PermissionError('denied')):
                result = inspect_runtime(home)
                self.assertEqual(result['status'],'unknown')
                self.assertEqual(result['errors'][0]['code'],'runtime_observation_unknown')
