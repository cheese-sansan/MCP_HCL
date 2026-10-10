import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_hcl.cli_session import PersistentConsole, PipeLease
from mcp_hcl.console import ConsoleError, ConsoleSession


class ScriptedSession:
    def __init__(self, reply):
        self.reply = reply
        self.chunks = []
        self._write_fd = 123

    def drain(self):
        return b"stale output"

    def send(self, command):
        self.chunks = list(self.reply(command))

    def _read_available(self):
        return self.chunks.pop(0) if self.chunks else b""

    def close(self):
        pass


class Console040Tests(unittest.TestCase):
    def test_partial_writes_send_every_byte(self):
        data = []

        def write(fd, payload):
            data.append(payload[:2])
            return min(2, len(payload))

        with patch("os.write", side_effect=write):
            ConsoleSession(1).send("display version")
        self.assertEqual(b"".join(data), b"display version\r\n")

    def test_persistent_echo_prompt_and_stale_drain(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = ScriptedSession(
                lambda command: [command.encode() + b"\r\noutput\r\n", b"<R1>"]
            )
            with PersistentConsole(
                r"\\.\pipe\lab-device1", Path(temporary), session=session, timeout=0.1
            ) as channel:
                result = channel.exchange("display version")
                self.assertTrue(result["complete"])
                self.assertEqual(result["discarded_stale_bytes"], 12)

    def test_lease_busy_and_missing_echo_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = PipeLease(Path(temporary), r"\\.\pipe\lab-device1")
            try:
                with self.assertRaises(ConsoleError):
                    PipeLease(Path(temporary), r"\\.\pipe\lab-device1")
            finally:
                first.close()
            with PersistentConsole(
                r"\\.\pipe\lab-device1",
                Path(temporary),
                session=ScriptedSession(lambda c: [b"old\n<R1>"]),
                timeout=0.1,
            ) as channel:
                with self.assertRaises(ConsoleError):
                    channel.exchange("display version")

    def test_continuous_output_obeys_deadline_and_overflow_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = ScriptedSession(lambda c: [])
            session._read_available = lambda: b"flood"
            with PersistentConsole(
                r"\\.\pipe\lab-device1",
                Path(temporary),
                session=session,
                timeout=0.02,
                max_bytes=100,
            ) as channel:
                with self.assertRaises(ConsoleError):
                    channel.exchange("display version")
                self.assertFalse(channel.history[-1]["complete"])

    def test_pagination_continues_once_and_confirmation_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = ScriptedSession(lambda c: [c.encode() + b"\n---- More ----", b"\nlast\n<R1>"])
            with patch("os.write", return_value=1) as write:
                with PersistentConsole(
                    r"\\.\pipe\lab-device1", Path(temporary), session=session, timeout=0.1
                ) as channel:
                    self.assertTrue(channel.exchange("display version")["complete"])
                self.assertEqual(
                    [c for c in write.call_args_list if c.args[0] == 123],
                    [unittest.mock.call(123, b" ")],
                )
