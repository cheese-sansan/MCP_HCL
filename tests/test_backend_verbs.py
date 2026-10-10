"""Tests for the observed backend verb registry.

Everything runs against a real TCP peer that speaks HCL's captured framing, so
the tests exercise the same code path a running server would use - they simply
never need a running HCL.
"""

from __future__ import annotations

import socket
import threading
import unittest
from contextlib import contextmanager
from typing import Callable

from mcp_hcl.backend import OBSERVED_VERBS, BackendError, HclBackend


@contextmanager
def fake_wrapper(handler: Callable[[str], tuple[int, str]]):
    """A real TCP peer using HCL's observed request/reply framing.

    ``handler`` receives the command text and returns ``(code, payload)``.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.5)
    recorded: list[str] = []
    failures: list[Exception] = []
    stop = threading.Event()

    def serve() -> None:
        try:
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with connection:
                    connection.settimeout(2)
                    request = bytearray()
                    while b"\n" not in request:
                        chunk = connection.recv(1024)
                        if not chunk:
                            break
                        request.extend(chunk)
                    if not request:
                        continue
                    identifier, command = request.decode("ascii").strip().split(" ", 1)
                    recorded.append(command)
                    code, payload = handler(command)
                    connection.sendall(f"{identifier}-{code}-{payload}\r\n/end".encode("utf-8"))
        except Exception as exc:  # surfaced in the test thread's teardown
            failures.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], recorded
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=3)
        if failures:
            raise failures[0]


def ok(command: str) -> tuple[int, str]:
    return 101, "done"


class VerbRegistryTests(unittest.TestCase):
    def test_registry_exposes_evidence_and_gating(self) -> None:
        verbs = HclBackend().verbs()
        by_name = {row["verb"]: row for row in verbs}
        self.assertEqual(len(by_name), len(OBSERVED_VERBS))
        for row in verbs:
            self.assertIn(row["evidence"], {"verified", "observed", "inferred"})
            self.assertIn(
                row["kind"], {"read", "lifecycle", "topology", "console", "power", "device"}
            )
            self.assertIsInstance(row["writes"], bool)
        self.assertTrue(by_name["version"]["enabled"])
        self.assertTrue(by_name["system_memory"]["enabled"])
        # observed but deliberately refused: guessing its 14 fields could create broken VMs
        self.assertFalse(by_name["create"]["invocable"])
        self.assertFalse(by_name["create"]["enabled"])
        # power-on is observed, so it is invocable but gated
        self.assertTrue(by_name["start"]["invocable"])
        self.assertFalse(by_name["start"]["enabled"], "writes must be off by default")

    def test_write_verbs_are_refused_until_explicitly_enabled(self) -> None:
        backend = HclBackend()
        result = backend.invoke("start", {"device": 6})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["errors"][0]["code"], "writes_disabled")
        self.assertFalse(result["runtime_verified"])

    def test_not_invocable_and_unknown_verbs_are_refused(self) -> None:
        backend = HclBackend(allow_writes=True)
        unknown = backend.invoke("delete_everything", {})
        self.assertEqual(unknown["errors"][0]["code"], "unknown_verb")
        observed_only = backend.invoke("create", {"name": "R1"})
        self.assertEqual(observed_only["errors"][0]["code"], "verb_not_invocable")
        self.assertIn("semantics are not understood", observed_only["errors"][0]["message"])

    def test_arguments_cannot_break_the_line_framing(self) -> None:
        backend = HclBackend(allow_writes=True)
        for label, arguments in (
            (
                "newline_injection",
                {
                    "topology": "topo1",
                    "working_directory": "E:\\a\nsimware start 1 0",
                    "project_name": "p",
                    "udp_port": 10000,
                },
            ),
            (
                "space_in_name",
                {
                    "topology": "topo 1",
                    "working_directory": "E:\\a",
                    "project_name": "p",
                    "udp_port": 10000,
                },
            ),
            (
                "relative_path",
                {
                    "topology": "topo1",
                    "working_directory": "work\\a",
                    "project_name": "p",
                    "udp_port": 10000,
                },
            ),
            (
                "port_out_of_range",
                {
                    "topology": "topo1",
                    "working_directory": "E:\\a",
                    "project_name": "p",
                    "udp_port": 70000,
                },
            ),
            ("missing_arguments", {}),
        ):
            with self.subTest(case=label):
                result = backend.invoke("create_topology", arguments)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["errors"][0]["code"], "invalid_arguments")

    def test_rendered_lines_match_the_observed_shapes(self) -> None:
        seen: list[str] = []

        with fake_wrapper(lambda command: (101, "done")) as (port, recorded):
            backend = HclBackend(port=port, timeout=0.5, allow_writes=True)
            backend.invoke(
                "create_topology",
                {
                    "topology": "topo1",
                    "working_directory": "E:\\MCP_HCL\\work\\staged\\s1",
                    "project_name": "s1",
                    "udp_port": 10000,
                },
            )
            backend.invoke("start", {"device": 6})
            backend.invoke("delete_udp", {"device": 6})
            backend.invoke("normal_close", {"normal": True})
            backend.invoke("set_hcl_tcp", {"port": 18600})
            backend.invoke("set_hcl_normal_close", {"normal": False})
            backend.invoke("start_recover", {})
            seen.extend(recorded)

        self.assertEqual(
            seen,
            [
                "simware create_topology topo1 E:\\MCP_HCL\\work\\staged\\s1 s1 10000",
                "simware start 6 0",
                "simware delete_udp 6 0 0",
                "simware normal_close True",
                "simware set_hcl_tcp 18600",
                "simware set_hcl_normal_close False",
                "simware start_recover",
            ],
        )

    def test_backend_error_codes_are_reported_not_raised(self) -> None:
        with fake_wrapper(lambda command: (204, "")) as (port, _):
            backend = HclBackend(port=port, timeout=0.5, allow_writes=True)
            result = backend.invoke("start", {"device": 6})
        self.assertTrue(result["status"], "rejected")
        self.assertEqual(result["response_code"], 204)
        self.assertEqual(result["errors"][0]["code"], "backend_error_code")
        self.assertNotIn("verified_scope", result)

    def test_unreachable_backend_is_unverified_not_accepted(self) -> None:
        # port 1 on loopback: nothing listens, connection is refused
        backend = HclBackend(port=1, timeout=0.5, allow_writes=True)
        result = backend.invoke("start", {"device": 6})
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["errors"][0]["code"], "backend_unreachable")
        self.assertFalse(result["live_canvas_verified"])

    def test_original_read_only_path_is_still_narrow(self) -> None:
        backend = HclBackend()
        with self.assertRaises(ValueError):
            backend._request("simware start 6 0")
        with self.assertRaises(ValueError):
            backend._request("simware create_topology topo1 E:\\a a 10000")

    def test_status_never_claims_live_control(self) -> None:
        with fake_wrapper(
            lambda command: (101, "1.0.0&6.0.14" if command.endswith("version") else "14708")
        ) as (port, _):
            result = HclBackend(port=port, timeout=0.5).status()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["verified_scope"], "version_and_memory_protocol_readback")
        self.assertFalse(result["live_canvas_verified"])
        self.assertFalse(result["full_live_gate_passed"])


@contextmanager
def stateful_wrapper(handler):
    """A TCP peer whose handler sees per-connection state, like the real wrapper."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.5)
    recorded: list[str] = []
    failures: list[Exception] = []
    stop = threading.Event()

    def serve() -> None:
        try:
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                state: dict[str, bool] = {}
                with connection:
                    connection.settimeout(2)
                    buffer = bytearray()
                    try:
                        while not stop.is_set():
                            chunk = connection.recv(1024)
                            if not chunk:
                                break
                            buffer.extend(chunk)
                            while b"\n" in buffer:
                                line, _, rest = bytes(buffer).partition(b"\n")
                                buffer = bytearray(rest)
                                identifier, command = line.decode("ascii").strip().split(" ", 1)
                                recorded.append(command)
                                code, payload = handler(command, state)
                                frame = f"{identifier}-{code}"
                                if payload:
                                    frame += f"-{payload}"
                                connection.sendall((frame + "\r\n/end").encode("utf-8"))
                    except OSError:
                        pass
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], recorded
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=3)
        if failures:
            raise failures[0]


@contextmanager
def raw_wrapper(builder):
    """A TCP peer that sends exactly the bytes ``builder`` returns, per connection."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(3)
    failures: list[Exception] = []
    commands: list[str] = []

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2)
                request = bytearray()
                while b"\n" not in request:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    request.extend(chunk)
                identifier, command = request.decode("ascii").strip().split(" ", 1)
                commands.append(command)
                for piece in builder(command, identifier):
                    connection.sendall(piece)
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], commands
    finally:
        thread.join(timeout=4)
        listener.close()
        if failures:
            raise failures[0]


def hcl_like(command: str, state: dict) -> tuple[int, str]:
    """Mirror the wrapper's per-connection topology rule, observed 2026-10-01.

    Payload-free replies reproduce the raw captured frames
    ``b'<id>-100\\r\\n/end'`` and ``b'<id>-228\\r\\n/end'``.
    """
    if command.startswith("simware create_topology"):
        state["topology"] = True
        return 100, ""
    if command.startswith("simware start"):
        return (100, "") if state.get("topology") else (228, "")
    return 200, ""


class WireFramingTests(unittest.TestCase):
    def test_split_frame_is_not_accepted_before_its_terminator(self) -> None:
        def builder(command: str, identifier: str):
            frame = f"{identifier}-100-1.0.0&6.0.14\r\n/end".encode()
            # deliberately split so the first read holds an unterminated frame
            return [frame[:-1], frame[-1:]]

        with raw_wrapper(builder) as (port, _):
            result = HclBackend(port=port, timeout=0.5)._exchange("simwarewrapper version")
        self.assertEqual(result["response_code"], 100)
        self.assertEqual(result["value"], "1.0.0&6.0.14")

    def test_frames_parser_drops_unterminated_chunks_and_keeps_terminated_ones(self) -> None:
        # Private import on purpose: this pins the framing rule itself, which is
        # what makes both the split-read and spurious-frame cases safe.
        from mcp_hcl.backend import _frames

        payload = b"7-100-ok\r\n/end999-200-bogus\r\n/end7-101-partial"
        self.assertEqual(
            [(frame["id"], frame["code"], frame["value"]) for frame in _frames(payload)],
            [(7, 100, "ok"), (999, 200, "bogus")],
        )
        self.assertEqual(_frames(b"7-100-unterminated\r\n/en"), [])
        self.assertEqual(_frames(b""), [])

    def test_frames_without_a_payload_segment_are_parsed(self) -> None:
        # Raw capture from the live wrapper:
        #   b'222222222-100\r\n/end'   (create_topology, parameters=None)
        #   b'333333333-228\r\n/end'   (start on a connection with no topology)
        from mcp_hcl.backend import _frames

        self.assertEqual(
            [
                (frame["id"], frame["code"], frame["value"])
                for frame in _frames(b"222222222-100\r\n/end333333333-228\r\n/end")
            ],
            [(222222222, 100, ""), (333333333, 228, "")],
        )

    def test_exchange_accepts_a_reply_without_parameters(self) -> None:
        def builder(command: str, identifier: str):
            return [f"{identifier}-100\r\n/end".encode()]

        with raw_wrapper(builder) as (port, _):
            result = HclBackend(port=port, timeout=0.5)._exchange("simwarewrapper version")
        self.assertEqual(result["response_code"], 100)
        self.assertEqual(result["value"], "")

    def test_trailing_spurious_frame_does_not_break_parsing(self) -> None:
        def builder(command: str, identifier: str):
            real = f"{identifier}-100-1.0.0&6.0.14\r\n/end".encode()
            bogus = b"999999999-200-None\r\n/end"
            # one write, so the two frames most likely share a single read
            return [real + bogus]

        with raw_wrapper(builder) as (port, _):
            result = HclBackend(port=port, timeout=0.5)._exchange("simwarewrapper version")
        self.assertEqual(
            result["value"],
            "1.0.0&6.0.14",
            "the reply must be matched by request id, not by position",
        )
        self.assertEqual(result["response_code"], 100)
        self.assertIn(result["extra_frames"], (0, 1))  # coalescing dependent


class BackendSessionTests(unittest.TestCase):
    def test_topology_context_is_per_connection(self) -> None:
        with stateful_wrapper(hcl_like) as (port, recorded):
            backend = HclBackend(port=port, timeout=0.5, allow_writes=True)
            one_shot = backend.invoke("start", {"device": 1})
            self.assertEqual(
                one_shot["response_code"], 228, "a one-shot connection has no topology context"
            )
            self.assertEqual(one_shot["errors"][0]["code"], "backend_error_code")

            session = backend.connect()
            try:
                opened = session.open_topology("mcphcl1", r"E:\MCP_HCL\work\staged\s1", "s1", 10000)
                self.assertEqual(opened["status"], "accepted")
                self.assertEqual(session.topology, "mcphcl1")
                started = session.invoke("start", {"device": 1})
                self.assertEqual(started["status"], "accepted")
                self.assertEqual(started["response_code"], 100)
                self.assertEqual(
                    session.commands_sent, ["simware create_topology", "simware start"]
                )
            finally:
                session.close()

        self.assertEqual(
            recorded,
            [
                "simware start 1 0",
                "simware create_topology mcphcl1 E:\\MCP_HCL\\work\\staged\\s1 s1 10000",
                "simware start 1 0",
            ],
        )

    def test_gated_session_sends_nothing(self) -> None:
        with stateful_wrapper(hcl_like) as (port, recorded):
            backend = HclBackend(port=port, timeout=0.5, allow_writes=False)
            session = backend.connect()
            try:
                result = session.open_topology("mcphcl1", r"E:\MCP_HCL\work\staged\s1", "s1", 10000)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["errors"][0]["code"], "writes_disabled")
            finally:
                session.close()
        self.assertEqual(recorded, [], "a write-disabled session must not reach the backend")

    def test_failed_open_leaves_the_session_named_after_nothing(self) -> None:
        def refuse(command: str, state: dict) -> tuple[int, str]:
            return 204, "None"

        with stateful_wrapper(refuse) as (port, _):
            backend = HclBackend(port=port, timeout=0.5, allow_writes=True)
            session = backend.connect()
            try:
                result = session.open_topology("mcphcl1", r"E:\MCP_HCL\work\staged\s1", "s1", 10000)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["response_code"], 204)
                self.assertIsNone(session.topology)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
