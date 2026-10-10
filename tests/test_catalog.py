from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mcp_hcl.catalog import CatalogError, HclCatalog


class CatalogTests(unittest.TestCase):
    def test_model_and_port_evidence_do_not_claim_guest_support(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "devicecfgs").mkdir()
            (directory / "devicecfgs" / "MSR36-20.cfg").write_text(
                " version 7.1.064, Release 0427P22\ninterface GigabitEthernet0/0\ninterface NULL0\n",
                encoding="utf-8",
            )
            (directory / "deviceInfo.ini").write_text(
                "[PHY_PORT_VALUE]\n PHY_ETH_GE = 3\n[MSR36]\n [[0]]\n  GE = PHY_ETH_GE\n",
                encoding="utf-8",
            )
            catalog = HclCatalog(directory)
            model = catalog.device_details("MSR36-20")
            self.assertFalse(model["runtime_verified"])
            self.assertEqual(model["device"]["default_interfaces"], ["GigabitEthernet0/0", "NULL0"])
            self.assertEqual(len(model["device"]["evidence"]["sha256"]), 64)
            self.assertEqual(catalog.ports()["families"]["MSR36"][0]["index"], 0)
            with self.assertRaises(CatalogError):
                catalog.device_details("../MSR36-20")

    def test_missing_and_malformed_installations_are_not_verified(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = HclCatalog(Path(root))
            with self.assertRaises(CatalogError):
                catalog.devices()
            (Path(root) / "deviceInfo.ini").write_text("[MSR36]\n", encoding="utf-8")
            with self.assertRaises(CatalogError):
                catalog.ports()
