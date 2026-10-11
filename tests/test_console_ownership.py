"""Real private Win32 pipes: process names do not establish endpoint ownership."""

import ctypes
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from test_console import NamedPipeServer

from mcp_hcl.cli_session import PersistentConsole
from mcp_hcl.console import ConsoleError, HclConsole, open_console_pipe


@unittest.skipUnless(os.name == "nt", "Win32 synthetic pipes required")
class OwnershipTests(unittest.TestCase):
    def test_background_multicc_does_not_block_an_exclusive_single_instance(self):
        pipe = rf"\\.\pipe\ownership{uuid4().hex}-device1"
        server = NamedPipeServer(pipe, max_instances=1, reply=b"display version\r\nBuild\r\n<R1>")
        server.start()
        connected = False
        try:
            with (
                tempfile.TemporaryDirectory() as temporary,
                patch("mcp_hcl.cli_session.Path.home", return_value=Path(temporary)),
                patch(
                    "subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout=b"true"),
                ),
            ):
                with PersistentConsole(pipe, Path(temporary), timeout=1) as channel:
                    connected = True
                    result = channel.exchange("display version")
                    self.assertTrue(result["complete"])
        finally:
            if not connected:
                # Cleanup connects only to this test's private server and sends nothing.
                try:
                    os.close(open_console_pipe(pipe, timeout=0.1))
                except ConsoleError:
                    pass
            server.close()

    def test_multiple_instance_pipe_is_refused_without_sending(self):
        pipe = rf"\\.\pipe\ownership{uuid4().hex}-device2"
        server = NamedPipeServer(pipe, max_instances=2, reply=b"display version\r\nBuild\r\n<R1>")
        server.start()
        try:
            with (
                tempfile.TemporaryDirectory() as temporary,
                patch("mcp_hcl.cli_session.Path.home", return_value=Path(temporary)),
                patch(
                    "subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout=b"false"),
                ),
            ):
                result = HclConsole(writes_enabled=True, lease_root=Path(temporary)).run(
                    pipe, "display version"
                )
                self.assertEqual(result["status"], "unverified", result)
                self.assertEqual(
                    result["errors"][0]["detail"]["reason"], "console_exclusivity_unverified"
                )
                self.assertEqual(result["command_outcome"], "not_sent")
                self.assertEqual(server.received, [])
        finally:
            server.close()

    def test_unknown_pipe_info_closes_handle_before_io(self):
        pipe = rf"\\.\pipe\ownership{uuid4().hex}-device3"
        server = NamedPipeServer(pipe, max_instances=1)
        server.start()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            with (
                patch("ctypes.WinDLL", return_value=kernel),
                patch.object(kernel, "GetNamedPipeInfo", return_value=False),
            ):
                with self.assertRaises(ConsoleError) as caught:
                    open_console_pipe(pipe, timeout=0.1)
                self.assertEqual(caught.exception.code, "console_exclusivity_unverified")
                self.assertEqual(caught.exception.detail["command_outcome"], "not_sent")
                self.assertEqual(server.received, [])
        finally:
            server.close()

    def test_raw_console_path_cannot_bypass_exclusivity(self):
        pipe = rf"\\.\pipe\ownership{uuid4().hex}-device4"
        server = NamedPipeServer(pipe, max_instances=255)
        server.start()
        try:
            result = HclConsole(writes_enabled=True).run(pipe, "display version")
            self.assertEqual(result["status"], "unverified", result)
            self.assertEqual(result["command_outcome"], "not_sent")
            self.assertEqual(result["errors"][0]["detail"]["maximum_instances"], 255)
            self.assertEqual(server.received, [])
        finally:
            server.close()
