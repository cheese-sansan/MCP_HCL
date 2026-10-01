"""Request-correlated console access to one HCL device.

HCL serves each device console on a **Windows named pipe**:

* the name comes from the backend's ``create_udp`` reply and is
  ``\\\\.\\pipe\\<topology>-device<N>`` (observed: ``\\\\.\\pipe\\topo1-device6``);
* HCL's own console window is PuTTY in **serial** mode pointed at that pipe
  (``D:\\HCL\\sessions\\default_conf``: ``Protocol=serial``, ``PortNumber\\115200``).

So the CLI channel is a byte stream over a named pipe: no window automation and
no keystroke synthesis are involved.

Design rules enforced here:

* only pipe names matching the observed HCL pattern are accepted, so this can
  never be pointed at an arbitrary host pipe;
* the descriptors are opened non-blocking and polled, so there is no reader
  thread whose ``close`` could deadlock (verified on Windows 11 / Python 3.12:
  ``os.set_blocking`` works on both anonymous and named pipes);
* output that arrived *before* the command is drained and reported, so stale
  console text can never be mistaken for this request's answer;
* writes are refused unless the process opted in with ``MCP_HCL_ALLOW_LIVE_WRITE=1``;
* a successful read proves the **console channel** works, never that the guest
  booted, that a command was accepted, or that the network is reachable.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

#: ``\\.\pipe\<topology>-device<N>`` exactly as observed in HCL 5.10.3.
PIPE_PATTERN = re.compile(
    r"^\\\\\.\\pipe\\(?P<topology>[A-Za-z0-9_.-]{1,64})-device(?P<device>[0-9]{1,4})$"
)

MAX_OUTPUT_BYTES = 256 * 1024
_POLL_SECONDS = 0.02


class ConsoleError(RuntimeError):
    """The console channel cannot be used safely."""


def endpoint(topology: str, device: int) -> str:
    """Build the observed pipe name for one device, validating both parts."""
    if not isinstance(topology, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", topology):
        raise ConsoleError("topology must match [A-Za-z0-9_.-]{1,64}")
    if isinstance(device, bool) or not isinstance(device, int) or not 1 <= device <= 1024:
        raise ConsoleError("device must be an integer between 1 and 1024")
    return f"\\\\.\\pipe\\{topology}-device{device}"


def describe(pipe_name: str) -> dict[str, Any]:
    """Split a pipe name into its topology and device, or refuse it."""
    match = PIPE_PATTERN.fullmatch(pipe_name or "")
    if match is None:
        raise ConsoleError(
            "Only HCL console pipes of the form \\\\.\\pipe\\<topology>-device<N> are accepted"
        )
    return {"pipe": pipe_name, "topology": match.group("topology"),
            "device": int(match.group("device"))}


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ConsoleError("command must be a non-empty string")
    if any(character in command for character in "\r\n\x00"):
        raise ConsoleError("command must not contain CR, LF or NUL")
    if len(command) > 512:
        raise ConsoleError("command is longer than 512 characters")
    if not command.isascii():
        raise ConsoleError('Console commands require verified ASCII encoding')
    return command.strip()


class ConsoleSession:
    """Non-blocking, line-oriented session over pipe file descriptors.

    Descriptors are injected so the protocol logic can be tested with anonymous
    pipes; :func:`open_console_pipe` is the only OS-specific part.
    """

    def __init__(self, read_fd: int, write_fd: int | None = None, *,
                 max_bytes: int = MAX_OUTPUT_BYTES) -> None:
        self._read_fd = read_fd
        self._write_fd = read_fd if write_fd is None else write_fd
        self._max_bytes = max_bytes
        self._closed = False

    # ------------------------------------------------------------------ io
    def _read_available(self) -> bytes:
        try:
            return os.read(self._read_fd, 65536)
        except BlockingIOError:
            return b""
        except OSError as exc:
            raise ConsoleError(f"Console read failed: {exc.__class__.__name__}") from exc

    def drain(self) -> bytes:
        """Discard and return everything already buffered (the 'stale output')."""
        collected = bytearray()
        while len(collected) < self._max_bytes:
            chunk = self._read_available()
            if not chunk:
                break
            collected.extend(chunk)
        return bytes(collected)

    def read_until_idle(self, *, idle_gap: float, timeout: float) -> bytes:
        """Collect output until it stops arriving for ``idle_gap`` seconds."""
        collected = bytearray()
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while True:
            if time.monotonic() >= deadline:
                break
            chunk = self._read_available()
            if chunk:
                collected.extend(chunk)
                if len(collected) > self._max_bytes:
                    del collected[: len(collected) - self._max_bytes]
                last_data = time.monotonic()
                continue
            now = time.monotonic()
            if now >= deadline:
                break
            if collected and (now - last_data) >= idle_gap:
                break
            time.sleep(min(_POLL_SECONDS, max(deadline - now, 0.001)))
        return bytes(collected)

    def send(self, command: str) -> None:
        payload = (_validate_command(command) + "\r\n").encode("ascii", errors="strict")
        deadline = time.monotonic() + 4.0
        offset = 0
        while offset < len(payload):
            if time.monotonic() >= deadline:
                raise ConsoleError('Console partial write timed out')
            try:
                sent = os.write(self._write_fd, payload[offset:])
                if sent == 0: raise ConsoleError('Console channel closed during write')
                offset += sent
            except BlockingIOError:
                time.sleep(_POLL_SECONDS)
            except OSError as exc:
                raise ConsoleError(f"Console write failed: {exc.__class__.__name__}") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for descriptor in {self._read_fd, self._write_fd}:
            try:
                os.close(descriptor)
            except OSError:
                pass


def open_console_pipe(pipe_name: str, *, timeout: float = 2.0) -> int:
    """Open one HCL console pipe non-blocking, retrying until ``timeout``."""
    describe(pipe_name)  # refuse anything that is not an HCL console pipe
    deadline = time.monotonic() + timeout
    while True:
        try:
            descriptor = os.open(pipe_name, os.O_RDWR | os.O_BINARY)
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise ConsoleError(
                    f"Console pipe is not available: {exc.__class__.__name__}"
                ) from exc
            time.sleep(0.05)
            continue
        try:
            os.set_blocking(descriptor, False)
        except (OSError, ValueError) as exc:
            os.close(descriptor)
            raise ConsoleError(
                f"Cannot make the console pipe non-blocking: {exc.__class__.__name__}"
            ) from exc
        return descriptor


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8/replace"


@dataclass(frozen=True)
class HclConsole:
    """Bounded, request-correlated console client."""

    open_timeout: float = 2.0
    idle_gap: float = 0.4
    read_timeout: float = 8.0
    settle_seconds: float = 0.25
    writes_enabled: bool = False

    def run(self, pipe_name: str, command: str, *, expect: str | None = None) -> dict[str, Any]:
        """Send one command and return only the output that followed it."""
        operation_id = uuid4().hex
        result: dict[str, Any] = {
            "status": "rejected", "operation": "console_exec", "operation_id": operation_id,
            "endpoint": pipe_name, "command": command, "target_project": None, "evidence": [],
            # A console read proves the channel, never the guest's state.
            "runtime_verified": False, "guest_boot_verified": False,
            "configuration_verified": False, "connectivity_verified": False,
            "full_live_gate_passed": False,
        }
        if not self.writes_enabled:
            result["errors"] = [{
                "code": "writes_disabled",
                "message": "Sending console input changes device state. Start the server with "
                           "MCP_HCL_ALLOW_LIVE_WRITE=1 after an explicit decision.",
            }]
            return result
        try:
            location = describe(pipe_name)
            command = _validate_command(command)
        except ConsoleError as exc:
            result["errors"] = [{"code": "invalid_request", "message": str(exc)}]
            return result

        started = time.monotonic()
        session: ConsoleSession | None = None
        try:
            descriptor = open_console_pipe(pipe_name, timeout=self.open_timeout)
            session = ConsoleSession(descriptor)
            # Let anything the device already emitted arrive, then throw it away:
            # it belongs to an earlier request, not to this one.
            time.sleep(min(self.settle_seconds, self.idle_gap))
            stale = session.drain()
            session.send(command)
            raw = session.read_until_idle(idle_gap=self.idle_gap, timeout=self.read_timeout)
        except ConsoleError as exc:
            result["status"] = "unverified"
            result["errors"] = [{"code": "console_unavailable", "message": str(exc)}]
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            return result
        finally:
            if session is not None:
                session.close()

        text, encoding = _decode(raw)
        result.update({
            "status": "output_received" if raw else "no_output",
            "topology": location["topology"],
            "device": location["device"],
            "discarded_stale_bytes": len(stale),
            "output_bytes": len(raw),
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "output_encoding": encoding,
            "output": text[-MAX_OUTPUT_BYTES:],
            "expect": expect,
            "expect_found": None if expect is None else (expect in text),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "verified_scope": "console_channel_text_readback_only",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "evidence": [{
                "source": pipe_name, "layer": "console_pipe",
                "request_sha256": hashlib.sha256(command.encode("ascii", "replace")).hexdigest(),
                "output_sha256": hashlib.sha256(raw).hexdigest(),
            }],
        })
        if expect is not None and result["expect_found"] is False:
            result["errors"] = [{
                "code": "expected_text_missing",
                "message": f"Console output did not contain the expected marker: {expect}",
            }]
        return result


def writes_enabled_from_environment(environment: dict[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return source.get("MCP_HCL_ALLOW_LIVE_WRITE", "").strip().lower() in {"1", "true", "yes", "on"}
