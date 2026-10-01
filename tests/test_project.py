from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mcp_hcl.project import ProjectError, ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.projects = root / "projects"
        self.project = self.projects / "lab1"
        self.project.mkdir(parents=True)
        (self.project / "ConfigDisk").mkdir()
        (self.project / "DeviceConfig").mkdir()
        (self.project / "ConfigDisk" / "device1.vdi").write_bytes(b"synthetic disk marker")
        (self.project / "DeviceConfig" / "R1.cfg").write_text("sysname R1\n", encoding="utf-8")
        (self.project / "deviceversion.txt").write_text("MSR36:b75\n", encoding="utf-8")
        metadata = {
            "projectInfo": {"name": "Lab One", "path": "lab1"},
            "deviceInfoList": [
                {
                    "resourceName": name,
                    "resourceCategory": "router",
                    "resourceModel": "MSR36-20",
                    "resourceVersion": "test",
                    "configPath": f"DeviceConfig\\{name}.cfg",
                }
                for name in ("R1", "R2")
            ],
        }
        (self.project / "project.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
        net = """version = 5.10.3
[vbox 127.0.0.1:16600]
    workingdir = C:\\old\\lab1
    udp = 10000
    [[MSR36-20 R1]]
        device_id = 1
        bridge_mac = 64-52-00-00-01-00
        slot0 = MSR36 384
        GE_0/0 = R2 GE_0/0
        x = 0.0
        y = 0.0
        z = 5.0
    [[MSR36-20 R2]]
        device_id = 2
        bridge_mac = 64-52-00-00-02-00
        slot0 = MSR36 384
        GE_0/0 = R1 GE_0/0
        x = 100.0
        y = 0.0
        z = 5.0
[Non-vBox-DATA]
    m11 = 1.0
"""
        (self.project / "lab1.net").write_bytes(net.replace("\n", "\r\n").encode("utf-8"))
        self.source_bytes = (self.project / "lab1.net").read_bytes()
        self.output = root / "staged"
        self.store = ProjectStore([self.projects], self.output)

    def test_inspect_and_stage_device_with_link(self) -> None:
        before = self.store.inspect(str(self.project))
        self.assertEqual(len(before["devices"]), 2)
        self.assertEqual(len(before["links"]), 1)
        result = self.store.stage_add_device(
            str(self.project), "MCP_Test_1", "R1", "MCP_R3", 200, 50,
            "R2", "GE_0/1", "GE_0/0",
        )
        self.assertEqual(result["status"], "staged")
        staged_dir = Path(result["project_directory"])
        staged = self.store.inspect(str(staged_dir))
        self.assertEqual(len(staged["devices"]), 3)
        self.assertEqual(len(staged["links"]), 2)
        self.assertIn("GE_0/1 = MCP_R3 GE_0/0", Path(result["project_file"]).read_text())
        self.assertIn(f"workingdir = {staged_dir}", Path(result["project_file"]).read_text())
        self.assertTrue((staged_dir / "ConfigDisk" / "device1.vdi").is_file())
        self.assertEqual((staged_dir / "DeviceConfig" / "MCP_R3.cfg").read_bytes(), b"")
        self.assertEqual((self.project / "lab1.net").read_bytes(), self.source_bytes)
        self.assertFalse((self.project / "DeviceConfig" / "MCP_R3.cfg").exists())

    def test_stage_link_requires_unused_ports(self) -> None:
        result = self.store.stage_link(str(self.project), "MCP_Test_2", "R1", "GE_0/1", "R2", "GE_0/1")
        self.assertEqual(result["link_count"], 2)
        with self.assertRaises(ProjectError):
            self.store.stage_link(str(self.project), "MCP_Test_3", "R1", "GE_0/0", "R2", "GE_0/1")

    def test_copy_preserves_configs_notes_and_source(self) -> None:
        net_path = self.project / "lab1.net"
        net_path.write_bytes(net_path.read_bytes() + b'    [[NOTE 1]]\r\n        text = "keep me"\r\n')
        serial = self.project / "SerialFile"
        serial.mkdir()
        (serial / "R1.log").write_bytes(b"existing console record")
        before = {
            str(path.relative_to(self.project)): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }
        result = self.store.stage_copy(str(self.project), "Gate_Copy")
        copy_path = Path(result["project_directory"])
        self.assertEqual(result["status"], "staged")
        self.assertEqual((result["device_count"], result["link_count"]), (2, 1))
        self.assertIn('text = "keep me"', Path(result["project_file"]).read_text())
        self.assertEqual((copy_path / "DeviceConfig/R1.cfg").read_bytes(), before[str(Path("DeviceConfig") / "R1.cfg")])
        self.assertEqual((copy_path / "SerialFile/R1.log").read_bytes(), b"existing console record")
        after = {
            str(path.relative_to(self.project)): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)

    def test_rejects_duplicate_stage_and_outside_source(self) -> None:
        self.store.stage_link(str(self.project), "MCP_Test_4", "R1", "GE_0/1", "R2", "GE_0/1")
        with self.assertRaises(ProjectError):
            self.store.stage_link(str(self.project), "MCP_Test_4", "R1", "GE_0/2", "R2", "GE_0/2")
        with self.assertRaises(ProjectError):
            self.store.inspect(str(Path(self.temp.name) / "outside"))


if __name__ == "__main__":
    unittest.main()
