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

import errno
import hashlib
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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

    def __init__(
        self,
        message: str,
        *,
        code: str = "console_unavailable",
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail = {"reason": code, **(detail or {})}

    def as_error(self, *, code: str | None = None) -> dict[str, Any]:
        return {"code": code or self.code, "message": str(self), "detail": dict(self.detail)}


def _os_error(exc: OSError, *, stage: str, api: str) -> ConsoleError:
    """Keep the native error, rather than interpreting a CRT exception name."""
    native = getattr(exc, "winerror", None)
    reasons = {
        2: "pipe_not_found",
        3: "pipe_not_found",
        5: "pipe_access_denied",
        32: "pipe_sharing_violation",
        109: "pipe_broken",
        231: "pipe_busy",
        232: "pipe_closing",
        233: "pipe_not_connected",
        121: "pipe_timeout",
    }
    reason = reasons.get(native, "console_io_failed")
    if native is None:
        if exc.errno == errno.ENOENT:
            reason = "pipe_not_found"
        elif exc.errno in {errno.EACCES, errno.EPERM}:
            reason = "pipe_access_denied"
        elif exc.errno == errno.EPIPE:
            reason = "pipe_broken"
    return ConsoleError(
        f"Console {stage} failed: {exc.__class__.__name__}",
        code=reason,
        detail={
            "stage": stage,
            "api": api,
            "winerror": native,
            "errno": exc.errno,
            "access_mode": "read_write",
        },
    )


def _require_single_pipe_instance(kernel, handle) -> None:
    """Prove endpoint exclusivity on the connected client handle, before I/O.

    CreateFile uses share mode zero. A maximum of one byte-mode instance
    additionally rules out another client connected to a different instance
    of the same name. This does not establish the VM or server principal;
    staged transactions still require RuntimeBinding.verify_pipe.
    """
    import ctypes
    import ctypes.wintypes as wt

    flags, maximum = wt.DWORD(), wt.DWORD()
    try:
        query = kernel.GetNamedPipeInfo
        query.argtypes = [
            wt.HANDLE,
            ctypes.POINTER(wt.DWORD),
            ctypes.POINTER(wt.DWORD),
            ctypes.POINTER(wt.DWORD),
            ctypes.POINTER(wt.DWORD),
        ]
        query.restype = wt.BOOL
        if not query(handle, ctypes.byref(flags), None, None, ctypes.byref(maximum)):
            raise ConsoleError(
                "Connected pipe exclusivity could not be observed",
                code="console_exclusivity_unverified",
                detail={
                    "stage": "ownership",
                    "api": "GetNamedPipeInfo",
                    "winerror": ctypes.get_last_error(),
                    "command_outcome": "not_sent",
                },
            )
    except (AttributeError, OSError, TypeError) as exc:
        raise ConsoleError(
            "Connected pipe exclusivity observation is unavailable",
            code="console_exclusivity_unverified",
            detail={"stage": "ownership", "api": "GetNamedPipeInfo", "command_outcome": "not_sent"},
        ) from exc
    if flags.value != 0 or maximum.value != 1:
        raise ConsoleError(
            "A single byte-mode client instance is required before console input",
            code="console_exclusivity_unverified",
            detail={
                "stage": "ownership",
                "api": "GetNamedPipeInfo",
                "pipe_flags": flags.value,
                "maximum_instances": maximum.value,
                "command_outcome": "not_sent",
            },
        )


def _open_pipe_descriptor(pipe_name: str) -> int:
    if os.name != "nt":
        return os.open(pipe_name, os.O_RDWR | os.O_BINARY)
    # CRT os.open can collapse PIPE_BUSY into PermissionError. Capture the
    # Win32 result before transferring ownership to a Python descriptor.
    import ctypes
    import ctypes.wintypes as wt
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wt.LPCWSTR,
        wt.DWORD,
        wt.DWORD,
        ctypes.c_void_p,
        wt.DWORD,
        wt.DWORD,
        wt.HANDLE,
    ]
    kernel.CreateFileW.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.CloseHandle.restype = wt.BOOL
    handle = kernel.CreateFileW(pipe_name, 0xC0000000, 0, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        native_error = ctypes.get_last_error()
        raise ctypes.WinError(native_error)
    try:
        _require_single_pipe_instance(kernel, handle)
        return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    except ConsoleError:
        kernel.CloseHandle(handle)
        raise
    except OSError as exc:
        kernel.CloseHandle(handle)
        raise _os_error(exc, stage="descriptor", api="open_osfhandle") from exc


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
    return {
        "pipe": pipe_name,
        "topology": match.group("topology"),
        "device": int(match.group("device")),
    }


def _validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ConsoleError("command must be a non-empty string")
    if any(character in command for character in "\r\n\x00"):
        raise ConsoleError("command must not contain CR, LF or NUL")
    if len(command) > 512:
        raise ConsoleError("command is longer than 512 characters")
    if not command.isascii():
        raise ConsoleError("Console commands require verified ASCII encoding")
    return command.strip()


class ConsoleSession:
    """Non-blocking, line-oriented session over pipe file descriptors.

    Descriptors are injected so the protocol logic can be tested with anonymous
    pipes; :func:`open_console_pipe` is the only OS-specific part.
    """

    def __init__(
        self,
        read_fd: int,
        write_fd: int | None = None,
        *,
        max_bytes: int = MAX_OUTPUT_BYTES,
        write_timeout: float = 4.0,
    ) -> None:
        self._read_fd = read_fd
        self._write_fd = read_fd if write_fd is None else write_fd
        self._max_bytes = max_bytes
        self._closed = False
        self.write_timeout = write_timeout
        self.partial_output = b""
        self.read_termination: str | None = None
        self.last_write_bytes = 0

    # ------------------------------------------------------------------ io
    def _read_available(self) -> bytes:
        try:
            return os.read(self._read_fd, 65536)
        except BlockingIOError:
            return b""
        except OSError as exc:
            raise _os_error(exc, stage="read", api="os.read") from exc

    def drain(self) -> bytes:
        """Discard and return everything already buffered (the 'stale output')."""
        collected = bytearray()
        while len(collected) < self._max_bytes:
            chunk = self._read_available()
            if not chunk:
                break
            collected.extend(chunk)
        if len(collected) >= self._max_bytes:
            raise ConsoleError(
                "Stale stream reached the evidence limit; no command was sent",
                code="stale_output_limit",
                detail={"stage": "drain", "bytes": len(collected)},
            )
        return bytes(collected)

    def read_until_idle(self, *, idle_gap: float, timeout: float) -> bytes:
        """Collect output until it stops arriving for ``idle_gap`` seconds."""
        collected = bytearray()
        self.partial_output = b""
        self.read_termination = None
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while True:
            if time.monotonic() >= deadline:
                self.read_termination = "timeout"
                break
            chunk = self._read_available()
            if chunk:
                collected.extend(chunk)
                if len(collected) > self._max_bytes:
                    self.partial_output = bytes(collected[: self._max_bytes])
                    raise ConsoleError(
                        "Console output exceeds the evidence limit",
                        code="output_limit",
                        detail={
                            "stage": "read",
                            "truncated": True,
                            "observed_bytes": len(collected),
                        },
                    )
                self.partial_output = bytes(collected)
                last_data = time.monotonic()
                continue
            now = time.monotonic()
            if now >= deadline:
                self.read_termination = "timeout"
                break
            if collected and (now - last_data) >= idle_gap:
                self.read_termination = "idle"
                break
            time.sleep(min(_POLL_SECONDS, max(deadline - now, 0.001)))
        return bytes(collected)

    def send(self, command: str) -> None:
        payload = (_validate_command(command) + "\r\n").encode("ascii", errors="strict")
        deadline = time.monotonic() + self.write_timeout
        offset = 0
        self.last_write_bytes = 0
        while offset < len(payload):
            if time.monotonic() >= deadline:
                raise ConsoleError(
                    "Console partial write timed out",
                    code="write_timeout",
                    detail={
                        "stage": "write",
                        "bytes_written": offset,
                        "command_outcome": "unknown" if offset else "not_sent",
                    },
                )
            try:
                sent = os.write(self._write_fd, payload[offset:])
                if sent == 0:
                    raise ConsoleError(
                        "Console channel closed during write",
                        code="pipe_broken",
                        detail={
                            "stage": "write",
                            "bytes_written": offset,
                            "command_outcome": "unknown" if offset else "not_sent",
                        },
                    )
                offset += sent
                self.last_write_bytes = offset
            except BlockingIOError:
                time.sleep(_POLL_SECONDS)
            except OSError as exc:
                failure = _os_error(exc, stage="write", api="os.write")
                failure.detail.update(
                    bytes_written=offset, command_outcome="unknown" if offset else "not_sent"
                )
                raise failure from exc

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
    """Open one HCL pipe; wait only for absent/busy endpoints within a deadline."""
    describe(pipe_name)  # refuse anything that is not an HCL console pipe
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout < 0:
        raise ConsoleError("Open timeout must be finite and nonnegative", code="invalid_timeout")
    deadline = time.monotonic() + timeout
    attempts = 0
    while True:
        attempts += 1
        try:
            descriptor = _open_pipe_descriptor(pipe_name)
        except OSError as exc:
            failure = _os_error(
                exc, stage="open", api="CreateFileW" if os.name == "nt" else "os.open"
            )
            failure.detail.update(attempts=attempts)
            remaining = deadline - time.monotonic()
            if failure.code not in {"pipe_not_found", "pipe_busy"} or remaining <= 0:
                failure.detail["wait_expired"] = remaining <= 0
                raise failure from exc
            time.sleep(min(0.05, remaining))
            continue
        try:
            os.set_blocking(descriptor, False)
        except (OSError, ValueError) as exc:
            os.close(descriptor)
            raise ConsoleError(
                f"Cannot make the console pipe non-blocking: {exc.__class__.__name__}",
                code="nonblocking_failed",
                detail={
                    "stage": "configure",
                    "winerror": getattr(exc, "winerror", None),
                    "errno": getattr(exc, "errno", None),
                },
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
    lease_root: Path | None = None

    def run(self, pipe_name: str, command: str, *, expect: str | None = None) -> dict[str, Any]:
        """Send one command and return only the output that followed it."""
        operation_id = uuid4().hex
        result: dict[str, Any] = {
            "status": "rejected",
            "operation": "console_exec",
            "operation_id": operation_id,
            "endpoint": pipe_name,
            "command": command,
            "target_project": None,
            "evidence": [],
            # A console read proves the channel, never the guest's state.
            "runtime_verified": False,
            "guest_boot_verified": False,
            "configuration_verified": False,
            "connectivity_verified": False,
            "full_live_gate_passed": False,
        }
        if not self.writes_enabled:
            result["errors"] = [
                {
                    "code": "writes_disabled",
                    "message": "Sending console input changes device state. Start the server with "
                    "MCP_HCL_ALLOW_LIVE_WRITE=1 after an explicit decision.",
                }
            ]
            return result
        try:
            location = describe(pipe_name)
            command = _validate_command(command)
        except ConsoleError as exc:
            result["errors"] = [{"code": "invalid_request", "message": str(exc)}]
            return result

        started = time.monotonic()
        session: ConsoleSession | None = None
        channel = None
        sent = False
        try:
            if self.lease_root is not None:
                import base64

                from mcp_hcl.cli_session import PersistentConsole

                with PersistentConsole(
                    pipe_name,
                    self.lease_root,
                    timeout=self.read_timeout,
                    max_bytes=MAX_OUTPUT_BYTES,
                    open_timeout=self.open_timeout,
                ) as channel:
                    reply = channel.exchange(command)
                    sent = True
                    raw = base64.b64decode(reply["raw_output_b64"])
                    stale = b"0" * reply["discarded_stale_bytes"]
            else:
                descriptor = open_console_pipe(pipe_name, timeout=self.open_timeout)
                session = ConsoleSession(descriptor)
                time.sleep(min(self.settle_seconds, self.idle_gap))
                stale = session.drain()
                session.send(command)
                sent = True
                raw = session.read_until_idle(idle_gap=self.idle_gap, timeout=self.read_timeout)
        except ConsoleError as exc:
            result["status"] = "unverified"
            result["errors"] = [exc.as_error(code="console_unavailable")]
            result["complete"] = False
            result["command_outcome"] = (
                "unknown" if sent or exc.detail.get("command_outcome") == "unknown" else "not_sent"
            )
            failed_raw = (
                session.partial_output
                if session is not None
                else getattr(channel, "partial_output", b"")
            )
            result.update(
                output=_decode(failed_raw)[0],
                output_bytes=len(failed_raw),
                output_sha256=hashlib.sha256(failed_raw).hexdigest(),
            )
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            return result
        finally:
            if session is not None:
                session.close()

        text, encoding = _decode(raw)
        result.update(
            {
                "status": "output_received" if raw else "no_output",
                "topology": location["topology"],
                "device": location["device"],
                "discarded_stale_bytes": len(stale),
                "output_bytes": len(raw),
                "output_sha256": hashlib.sha256(raw).hexdigest(),
                "output_encoding": encoding,
                "output": text[-MAX_OUTPUT_BYTES:],
                "complete": bool(channel is not None and reply["complete"]),
                "read_termination": "prompt" if channel is not None else session.read_termination,
                "command_outcome": "response_received" if raw else "unknown",
                "expect": expect,
                "expect_found": None if expect is None else (expect in text),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "verified_scope": "console_channel_text_readback_only",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "evidence": [
                    {
                        "source": pipe_name,
                        "layer": "console_pipe",
                        "request_sha256": hashlib.sha256(
                            command.encode("ascii", "replace")
                        ).hexdigest(),
                        "output_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                ],
            }
        )
        if session is not None and raw and session.read_termination == "timeout":
            result["status"] = "unverified"
            result["errors"] = [
                {
                    "code": "console_read_timeout",
                    "message": "Output did not become idle before the deadline",
                }
            ]
        if expect is not None and result["expect_found"] is False:
            result["errors"] = [
                {
                    "code": "expected_text_missing",
                    "message": f"Console output did not contain the expected marker: {expect}",
                }
            ]
        return result


def writes_enabled_from_environment(environment: dict[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return source.get("MCP_HCL_ALLOW_LIVE_WRITE", "").strip().lower() in {"1", "true", "yes", "on"}
