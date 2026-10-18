"""Probe receipts survive every preflight failure without opening native channels."""

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BasicConsoleProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/hcl_lab_console_once.py"
        spec = importlib.util.spec_from_file_location("basic_console_probe", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = {
            "candidate": str(self.root / "candidate.whl"),
            "candidate_sha256": "a" * 64,
            "project_file": str(self.root / "project/lab.net"),
            "topology": "topo1",
            "device_id": 6,
            "owner_sid": "S-1-5-21-123-456-789-1011",
            "vm_uuid": "d9d57b86-2746-442c-9ab4-d93bbe00bc22",
        }

    def invoke(self, spec=None, *, failure=None, enabled=True, receipt_failure=False):
        path = self.root / "spec.json"
        path.write_text(json.dumps(self.spec if spec is None else spec), encoding="utf-8")
        calls = []
        target = {
            "owner_sid": self.spec["owner_sid"],
            "vm_uuid": self.spec["vm_uuid"],
            "pipe": r"\\.\pipe\topo1-device6",
        }
        stage = failure

        class Runtime:
            def resolve(self, document, binding, topology):
                calls.append(("resolve", document.directory, binding, topology))
                if stage == "resolve":
                    raise ValueError("No configuration disk binding")
                result = copy.deepcopy(target)
                if stage == "identity":
                    result["owner_sid"] = "S-1-5-21-999"
                return result

            def verify_pipe(self, channel, observed):
                calls.append(("verify_pipe", observed))
                if stage == "pipe_identity":
                    raise ValueError("Wrong pipe server")
                return observed

        class Console:
            def __init__(self, *args, **kwargs):
                calls.append(("open", args, kwargs))
                if stage == "open":
                    raise OSError("sensitive failure must not be echoed")

            def exchange(self, command):
                calls.append(("exchange", command))
                if stage == "exchange":
                    raise RuntimeError("sensitive failure must not be echoed")
                return {"complete": stage != "incomplete", "output": "Comware version fixture"}

            def close(self):
                calls.append(("close",))
                if stage == "close":
                    raise OSError("sensitive failure must not be echoed")

        def load(specification):
            calls.append(("load",))
            if stage == "candidate":
                raise ImportError("sensitive failure must not be echoed")
            return Runtime(), Console

        with patch.dict(os.environ, MCP_HCL_ALLOW_LIVE_WRITE="1" if enabled else "0"):
            if receipt_failure:
                with patch.object(Path, "write_text", side_effect=OSError("receipt write failed")):
                    return self.module.probe(path, self.root / "receipts", candidate_loader=load)
            receipt, result = self.module.probe(path, self.root / "receipts", candidate_loader=load)
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8")), result)
        self.assertFalse(result["full_live_gate_passed"])
        self.assertNotIn("sensitive failure", json.dumps(result))
        return result, calls

    def test_default_gate_prevents_candidate_loading_and_native_queries(self):
        result, calls = self.invoke(enabled=False)
        self.assertEqual(calls, [])
        self.assertEqual(result["command_outcome"], "not_sent")

    def test_all_validation_stages_keep_receipts_and_do_not_replay(self):
        expected = {
            "candidate": "candidate",
            "resolve": "runtime_binding",
            "identity": "runtime_binding",
            "open": "console_open",
            "pipe_identity": "pipe_identity",
            "exchange": "exchange",
            "incomplete": "exchange",
            "close": "complete",
        }
        for failure, stage in expected.items():
            with self.subTest(failure=failure):
                result, calls = self.invoke(failure=failure)
                self.assertEqual(result["status"], "unverified")
                self.assertEqual(result["stage"], stage)
                self.assertLessEqual(sum(row[0] == "exchange" for row in calls), 1)
                if failure not in {"exchange", "incomplete", "close"}:
                    self.assertEqual(result["command_outcome"], "not_sent")

    def test_production_binding_receives_exact_project_device_and_topology(self):
        result, calls = self.invoke()
        self.assertEqual(result["status"], "output_received")
        resolve = next(row for row in calls if row[0] == "resolve")
        self.assertEqual(resolve[1:], (self.root / "project", {"device_id": 6}, "topo1"))
        self.assertEqual([row[1] for row in calls if row[0] == "exchange"], ["display version"])
        self.assertEqual(calls[-1], ("close",))
        self.assertFalse(result["runtime_verified"])

    def test_unknown_fields_bool_device_and_bad_uuid_reject_before_loading(self):
        for field, value in (("command", "save"), ("device_id", True), ("vm_uuid", "wrong")):
            with self.subTest(field=field):
                spec = copy.deepcopy(self.spec)
                spec[field] = value
                result, calls = self.invoke(spec)
                self.assertEqual(calls, [])
                self.assertEqual(result["stage"], "input")

    def test_malformed_and_duplicate_json_are_recorded_before_io(self):
        for text in ("{", '{"device_id":6,"device_id":7}'):
            with self.subTest(text=text):
                path = self.root / "bad.json"
                path.write_text(text, encoding="utf-8")
                receipt, result = self.module.probe(
                    path,
                    self.root / "receipts",
                    candidate_loader=lambda _: self.fail("Unexpected loader"),
                )
                self.assertTrue(receipt.is_file())
                self.assertEqual(result["stage"], "input")
                self.assertEqual(result["command_outcome"], "not_sent")

    def test_receipt_failure_after_exchange_cannot_be_reported_as_not_sent(self):
        with self.assertRaises(self.module.ReceiptWriteError) as caught:
            self.invoke(receipt_failure=True)
        self.assertEqual(caught.exception.result["command_outcome"], "output_received")
        self.assertEqual(caught.exception.result["stage"], "complete")
