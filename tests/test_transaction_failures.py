import json
from pathlib import Path
from unittest.mock import patch

from software_fixtures import BASE, Guest, SoftwareCase
from test_interface_tuning import AFTER as TUNING_AFTER
from test_interface_tuning import REQUEST as TUNING
from test_nat_transactions import STATIC, STATIC_AFTER
from test_netstream_transactions import AFTER as STREAM_AFTER
from test_netstream_transactions import REQUEST as STREAM
from test_switch_security import PORT, PORT_AFTER, STP, STP_AFTER

from mcp_hcl.console import ConsoleError
from mcp_hcl.interface_tuning import InterfaceTuningOperation
from mcp_hcl.nat_policy import NatOperations
from mcp_hcl.netstream_policy import NetstreamOperation
from mcp_hcl.switch_security import SwitchSecurityOperation

FEATURES = [
    ("nat", STATIC, STATIC_AFTER),
    ("tuning", TUNING, TUNING_AFTER),
    ("stp", STP, STP_AFTER),
    ("port", PORT, PORT_AFTER),
    ("stream", STREAM, STREAM_AFTER),
]


class TransactionFailures(SoftwareCase):
    def invoke(self, feature, request):
        policy = self.policy()
        if feature == "nat":
            return NatOperations(policy).run(self.project, "lab", request)
        if feature == "tuning":
            return InterfaceTuningOperation(policy).apply(self.project, "lab", request)
        if feature == "stream":
            return NetstreamOperation(policy).apply(self.project, "lab", request)
        return SwitchSecurityOperation(policy).apply(
            "stp" if feature == "stp" else "port_security", self.project, "lab", request
        )

    def test_binding_pipe_and_occupied_channel_stop_before_commands(self):
        for feature, request, after in FEATURES:
            for mode in ("binding", "pipe", "busy"):
                with self.subTest(feature=feature, mode=mode):
                    self.guest = Guest(after=after)
                    self.opens = []
                    self.binding_error = mode == "binding"
                    self.pipe_error = mode == "pipe"
                    if mode == "busy":
                        with patch.object(
                            self,
                            "dependencies",
                            return_value=(
                                self.dependencies()[0],
                                lambda _: (_ for _ in ()).throw(
                                    ConsoleError("Occupied", code="pipe_busy")
                                ),
                            ),
                        ):
                            result = self.invoke(feature, request)
                    else:
                        result = self.invoke(feature, request)
                    self.assertTrue(result["errors"], result)
                    self.assertEqual(self.guest.commands, [])
                    self.assert_synthetic(result)
        self.binding_error = self.pipe_error = False

    def test_saved_content_failure_restores_running_and_startup(self):
        for feature, request, after in FEATURES:
            with self.subTest(feature=feature):
                self.guest = Guest(after=after)
                self.guest.bad_saved = True
                self.opens = []
                result = self.invoke(feature, request)
                self.assertTrue(result["errors"], result)
                self.assertEqual(self.guest.current, BASE, result)
                self.assertEqual(self.guest.startup["main"], "flash:/startup.cfg")
                self.assertEqual(len(self.opens), 2)
                self.assert_synthetic(result)

    def test_unrequested_scope_change_and_changed_uuid_recovery_refusal(self):
        for feature, request, after in FEATURES:
            with self.subTest(feature=feature):
                self.guest = Guest(after=after.replace("sysname preserved", "sysname unauthorized"))
                self.opens = []
                self.changed_identity = True
                result = self.invoke(feature, request)
                self.assertTrue(result["errors"], result)
                self.assertEqual(len(self.opens), 1, result)
                self.assertEqual(result["rollback"]["error"]["code"], "recovery_target_changed")
                self.assert_synthetic(result)
        self.changed_identity = False

    def test_budget_expiry_recovery_has_new_connection_without_delta_replay(self):
        for feature, request, after in FEATURES:
            with self.subTest(feature=feature):
                self.guest = Guest(after=after)
                self.opens = []
                self.clock.value = 0

                def advance(cmd):
                    if cmd not in (
                        "display startup",
                        "display current-configuration",
                        "screen-length disable",
                    ) and not cmd.startswith(
                        ("save ", "more ", "configuration replace", "startup ", "undo startup")
                    ):
                        self.clock.advance(2)

                self.guest.on_exchange = advance
                with patch("mcp_hcl.nat_policy.time.monotonic", self.clock):
                    result = self.invoke(feature, request | {"timeout_seconds": 1})
                self.assertTrue(result["errors"], result)
                self.assert_synthetic(result)

    def test_close_and_receipt_failures_are_not_complete_success(self):
        for feature, request, after in FEATURES:
            with self.subTest(feature=feature, mode="close"):
                self.guest = Guest(after=after)
                self.guest.close_error = True
                result = self.invoke(feature, request)
                self.assertEqual(result["status"], "unverified", result)
                self.assertTrue(result["errors"])
                self.assert_synthetic(result)
            with self.subTest(feature=feature, mode="receipt"):
                self.guest = Guest(after=after)
                module = {
                    "nat": "nat_policy",
                    "tuning": "interface_tuning",
                    "stp": "switch_security",
                    "port": "switch_security",
                    "stream": "netstream_policy",
                }[feature]
                mod = __import__("mcp_hcl." + module, fromlist=["atomic_json"])
                original = mod.atomic_json

                def fail(path, data):
                    if path.name == "result.json":
                        raise OSError("Scripted final receipt failure")
                    return original(path, data)

                with patch("mcp_hcl." + module + ".atomic_json", fail):
                    with self.assertRaises(ConsoleError) as raised:
                        self.invoke(feature, request)
                self.assertIn("receipt", raised.exception.code)

    def test_unusable_backup_and_uncertain_startup_pointer_recover_before_replay(self):
        for feature, request, after in FEATURES:
            for mode in ("backup", "pointer"):
                with self.subTest(feature=feature, mode=mode):
                    self.guest = Guest(after=after)
                    self.opens = []
                    original = self.guest.exchange

                    def exchange(cmd):
                        result = original(cmd)
                        if mode == "backup" and cmd.startswith("more ") and "_before.cfg" in cmd:
                            return "#\nsysname wrong\n#\nreturn\n"
                        if (
                            mode == "pointer"
                            and cmd.startswith("startup saved-configuration ")
                            and "_after.cfg" in cmd
                        ):
                            raise ConsoleError("Pointer outcome unknown", code="pipe_broken")
                        return result

                    self.guest.exchange = exchange
                    result = self.invoke(feature, request)
                    self.assertTrue(result["errors"], result)
                    self.assertEqual(self.guest.current, BASE)
                    self.assertEqual(self.guest.startup["main"], "flash:/startup.cfg")
                    self.assert_synthetic(result)

    def test_same_key_conflict_missing_and_malformed_history_never_replay(self):
        folders = {
            "nat": ".nat-receipts",
            "tuning": ".interface-tuning-receipts",
            "stp": ".switch-security-receipts",
            "port": ".switch-security-receipts",
            "stream": ".netstream-receipts",
        }
        for feature, request, after in FEATURES:
            with self.subTest(feature=feature, mode="reuse"):
                self.guest = Guest(after=after)
                key = "reuse_" + feature + "_1"
                first = self.invoke(feature, request | {"operation_key": key})
                self.assertTrue(first.get("protocol_effect_verified"), first)
                count = len(self.guest.commands)
                again = self.invoke(feature, request | {"operation_key": key})
                self.assertEqual(len(self.guest.commands), count)
                self.assert_synthetic(again)
                conflict = self.invoke(
                    feature, request | {"operation_key": key, "timeout_seconds": 121}
                )
                self.assertEqual(conflict["status"], "rejected")
                self.assertEqual(len(self.guest.commands), count)
                result_path = self.paths["output"] / folders[feature] / key / "result.json"
                for invalid in ("[]", '{"ok":true,"ok":false}', "not-json"):
                    with self.subTest(feature=feature, result=invalid):
                        result_path.write_text(invalid, encoding="utf-8")
                        damaged = self.invoke(feature, request | {"operation_key": key})
                        self.assertEqual(damaged["status"], "unverified")
                        self.assertEqual(damaged["operation_id"], key)
                        self.assertEqual(len(self.guest.commands), count)
                        self.assert_synthetic(damaged)
            for mode in ("missing", "malformed"):
                with self.subTest(feature=feature, mode=mode):
                    key = "incomplete_" + feature + "_" + mode
                    directory = self.paths["output"] / folders[feature] / key
                    directory.mkdir(parents=True)
                    if mode == "malformed":
                        (directory / "request.json").write_text(
                            '{"fingerprint":1,"fingerprint":2}', encoding="utf-8"
                        )
                    count = len(self.guest.commands)
                    result = self.invoke(feature, request | {"operation_key": key})
                    self.assertIn(result["status"], ("rejected", "unverified"))
                    self.assertEqual(len(self.guest.commands), count)
                    self.assert_synthetic(result)
