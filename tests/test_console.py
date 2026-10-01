"""Tests for the named-pipe device console client.

Two layers are covered:

* protocol logic (drain stale output, correlate a reply, refuse unsafe input)
  over anonymous pipes, which needs nothing Windows-specific;
* a **real Windows named pipe** created with ``CreateNamedPipeW``, so the
  open/read/write path used against HCL is genuinely exercised, not mocked.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import msvcrt
import os
import sys
import threading
import time
import unittest

from mcp_hcl.console import (
    ConsoleError,
    ConsoleSession,
    HclConsole,
    describe,
    endpoint,
    writes_enabled_from_environment,
)

WINDOWS_ONLY = unittest.skipUnless(sys.platform == "win32", "Windows named pipes are required")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
ERROR_PIPE_CONNECTED = 535
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32.CreateNamedPipeW.restype = wt.HANDLE
kernel32.CreateNamedPipeW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD,
                                      wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]
kernel32.ConnectNamedPipe.restype = wt.BOOL
kernel32.ConnectNamedPipe.argtypes = [wt.HANDLE, ctypes.c_void_p]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def _make_nonblocking(fd: int) -> int:
    os.set_blocking(fd, False)
    return fd


def _read_nonblocking(fd: int, size: int = 65536) -> bytes:
    try:
        return os.read(fd, size)
    except BlockingIOError:
        return b""


def _pump(fd: int, size: int, timeout: float = 3.0) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + timeout
    while len(data) < size and time.monotonic() < deadline:
        chunk = _read_nonblocking(fd, size - len(data))
        if chunk:
            data.extend(chunk)
        else:
            time.sleep(0.02)
    return bytes(data)


class NamedPipeServer:
    """A real byte-mode Windows named pipe that answers each line with a reply."""

    def __init__(self, name: str, *, banner: bytes = b"", reply: bytes = b"") -> None:
        self.name = name
        self.banner = banner
        self.reply = reply
        self.received: list[str] = []
        self.errors: list[Exception] = []
        self._handle = None
        self._owns_handle = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handle = kernel32.CreateNamedPipeW(
            self.name, PIPE_ACCESS_DUPLEX, PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES, 4096, 4096, 0, None,
        )
        if not handle or handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            connected = kernel32.ConnectNamedPipe(self._handle, None)
            if not connected and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
                raise ctypes.WinError(ctypes.get_last_error())
            descriptor = msvcrt.open_osfhandle(self._handle, os.O_RDWR | os.O_BINARY)
            self._owns_handle = False
            try:
                os.set_blocking(descriptor, False)
                if self.banner:
                    os.write(descriptor, self.banner)
                buffer = b""
                while not self._stop.is_set():
                    try:
                        chunk = os.read(descriptor, 4096)
                    except BlockingIOError:
                        time.sleep(0.02)
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\r\n" in buffer:
                        line, buffer = buffer.split(b"\r\n", 1)
                        self.received.append(line.decode("ascii", "replace"))
                        os.write(descriptor, self.reply)
            finally:
                os.close(descriptor)
        except Exception as exc:  # surfaced by close()
            self.errors.append(exc)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        if self._owns_handle and self._handle:
            kernel32.CloseHandle(self._handle)
        if self.errors:
            raise self.errors[0]


class PipeNameTests(unittest.TestCase):
    def test_endpoint_builds_the_observed_shape(self) -> None:
        self.assertEqual(endpoint("topo1", 6), "\\\\.\\pipe\\topo1-device6")
        self.assertEqual(describe("\\\\.\\pipe\\topo77-device12"),
                         {"pipe": "\\\\.\\pipe\\topo77-device12", "topology": "topo77", "device": 12})

    def test_only_hcl_console_pipes_are_accepted(self) -> None:
        for bad in ("\\\\.\\pipe\\evil", "\\\\.\\pipe\\x", "\\\\server\\pipe\\topo1-device1",
                    "topo1-device1", "/dev/ttyS0", "", None, "\\\\.\\pipe\\topo1-device",
                    "\\\\.\\pipe\\topo1-device1x"):
            with self.subTest(pipe=bad):
                with self.assertRaises(ConsoleError):
                    describe(bad)

    def test_endpoint_argument_validation(self) -> None:
        for topology, device in (("topo 1", 1), ("", 1), ("topo1", 0), ("topo1", 2000),
                                 ("topo1", True), ("topo1", "1")):
            with self.subTest(topology=topology, device=device):
                with self.assertRaises(ConsoleError):
                    endpoint(topology, device)


class ConsoleGatingTests(unittest.TestCase):
    def test_input_is_refused_without_the_master_switch(self) -> None:
        # no pipe exists at this name: a pass proves the gate fires before any I/O
        result = HclConsole().run("\\\\.\\pipe\\topo1-device1", "display version")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["errors"][0]["code"], "writes_disabled")
        self.assertFalse(result["guest_boot_verified"])

    def test_unsafe_commands_are_refused(self) -> None:
        console = HclConsole(writes_enabled=True)
        for command in ("", "   ", "display version\nreboot", "display\r\nversion", "a\x00b"):
            with self.subTest(command=command):
                result = console.run("\\\\.\\pipe\\topo1-device1", command)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["errors"][0]["code"], "invalid_request")

    def test_environment_master_switch(self) -> None:
        for value, expected in (("1", True), ("true", True), ("YES", True), ("on", True),
                                ("", False), ("0", False), ("no", False)):
            with self.subTest(value=value):
                self.assertIs(writes_enabled_from_environment({"MCP_HCL_ALLOW_LIVE_WRITE": value}),
                              expected)


class ConsoleSessionTests(unittest.TestCase):
    def test_drained_output_cannot_be_mistaken_for_the_answer(self) -> None:
        client_read, peer_write = os.pipe()
        peer_read, client_write = os.pipe()
        for descriptor in (client_read, peer_write, peer_read, client_write):
            _make_nonblocking(descriptor)
        session = ConsoleSession(client_read, client_write)
        try:
            os.write(peer_write, b"<HCL> stale banner\r\n")
            time.sleep(0.2)
            stale = session.drain()
            self.assertIn(b"stale banner", stale)

            session.send("display version")
            sent = _pump(peer_read, len(b"display version\r\n"))
            self.assertEqual(sent, b"display version\r\n")

            os.write(peer_write, b"Version 7.1.064\r\n")
            output = session.read_until_idle(idle_gap=0.15, timeout=2.0)
        finally:
            session.close()
            for descriptor in (peer_write, peer_read):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        self.assertIn(b"Version 7.1.064", output)
        self.assertNotIn(b"stale banner", output)

    def test_read_until_idle_returns_empty_when_nothing_arrives(self) -> None:
        client_read, peer_write = os.pipe()
        _make_nonblocking(client_read)
        session = ConsoleSession(client_read)
        try:
            started = time.monotonic()
            output = session.read_until_idle(idle_gap=0.1, timeout=0.4)
            elapsed = time.monotonic() - started
        finally:
            session.close()
            os.close(peer_write)
        self.assertEqual(output, b"")
        self.assertGreaterEqual(elapsed, 0.35)


@WINDOWS_ONLY
class RealNamedPipeTests(unittest.TestCase):
    def test_round_trip_over_a_real_named_pipe(self) -> None:
        name = "\\\\.\\pipe\\mcphcltest-device1"
        server = NamedPipeServer(name, banner=b"<HCL> booting\r\n",
                                 reply=b"Version 7.1.064, Release 0427P22\r\n<HCL>")
        server.start()
        try:
            console = HclConsole(open_timeout=3.0, idle_gap=0.3, read_timeout=6.0,
                                 writes_enabled=True)
            result = console.run(name, "display version", expect="Version")
        finally:
            server.close()

        self.assertEqual(result["status"], "output_received")
        self.assertEqual(result["topology"], "mcphcltest")
        self.assertEqual(result["device"], 1)
        self.assertIn("Version 7.1.064", result["output"])
        self.assertTrue(result["expect_found"])
        self.assertGreaterEqual(result["discarded_stale_bytes"], 1,
                                "the banner written before the command must be drained")
        self.assertNotIn("booting", result["output"])
        self.assertEqual(result["verified_scope"], "console_channel_text_readback_only")
        self.assertFalse(result["guest_boot_verified"])
        self.assertFalse(result["configuration_verified"])
        self.assertFalse(result["connectivity_verified"])
        self.assertFalse(result["full_live_gate_passed"])
        self.assertEqual(len(result["output_sha256"]), 64)
        self.assertEqual(server.received, ["display version"])

    def test_missing_expected_marker_is_reported(self) -> None:
        name = "\\\\.\\pipe\\mcphcltest-device2"
        server = NamedPipeServer(name, reply=b"Unknown command\r\n<HCL>")
        server.start()
        try:
            console = HclConsole(open_timeout=3.0, idle_gap=0.3, read_timeout=6.0,
                                 writes_enabled=True)
            result = console.run(name, "display nosuchthing", expect="Version")
        finally:
            server.close()

        self.assertFalse(result["expect_found"])
        self.assertEqual(result["errors"][0]["code"], "expected_text_missing")
        self.assertIn("Unknown command", result["output"])

    def test_absent_pipe_is_unverified_not_an_exception(self) -> None:
        console = HclConsole(open_timeout=0.4, writes_enabled=True)
        result = console.run("\\\\.\\pipe\\mcphcltest-absent-device9", "display version")
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["errors"][0]["code"], "console_unavailable")


if __name__ == "__main__":
    unittest.main()
