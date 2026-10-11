"""Persistent, leased, bounded Comware console transactions."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import time
from pathlib import Path

from mcp_hcl.console import ConsoleError, ConsoleSession, _decode, describe, open_console_pipe

PROMPT = re.compile(r"(?:^|\n)(<[^<>\r\n]{1,128}>|\[[^\[\]\r\n]{1,160}\])\s*$")
PAGER = re.compile(r"(?:----\s*More\s*----|--More--)\s*$", re.I)
CLI_ERROR = re.compile(
    r"(?:^|\n)\s*(?:%\s*(?:Unrecognized|Incomplete|Wrong|Error|Too many)|Error:|Invalid command|Permission denied)",
    re.I,
)


def clean_text(raw: bytes) -> str:
    text = _decode(raw)[0].replace("\r", "")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    while "\b" in text:
        text = re.sub(r".?\x08", "", text)
    return text


class PipeLease:
    def __init__(self, root: Path, pipe: str):
        describe(pipe)
        if any(
            path.is_symlink() or getattr(path, "is_junction", lambda: False)()
            for path in (root, *root.parents)
        ):
            raise ConsoleError("Pipe lease root cannot contain links", code="invalid_lease_root")
        root.mkdir(parents=True, exist_ok=True)
        path = root / (hashlib.sha256(pipe.casefold().encode()).hexdigest() + ".lock")
        if path.is_symlink():
            raise ConsoleError("Pipe lease cannot be linked")
        self.fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(self.fd).st_size == 0:
                os.write(self.fd, b"0")
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            raise ConsoleError(
                "Console channel is busy; release the other client",
                code="console_lease_busy",
                detail={
                    "stage": "lease",
                    "errno": exc.errno,
                    "winerror": getattr(exc, "winerror", None),
                },
            ) from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class PersistentConsole:
    def __init__(
        self,
        pipe: str,
        lease_root: Path,
        *,
        session=None,
        timeout=12.0,
        max_bytes=1024 * 1024,
        open_timeout=2.0,
    ):
        self.pipe = pipe
        self.native_channel = session is None
        # Native consumers using different output directories still compete
        # for the same per-user endpoint lock. Synthetic sessions stay local.
        actual_lease_root = (
            Path.home() / ".mcp_hcl" / "console-leases" if self.native_channel else lease_root
        )
        self.lease = PipeLease(actual_lease_root, pipe)
        self.timeout = timeout
        self.max_bytes = max_bytes
        try:
            # Native open_console_pipe proves the connected instance is exclusive
            # before any drain or input. Process existence is not ownership:
            # an idle MultiCC (or an unrelated PuTTY) must not veto this endpoint.
            self.session = session or ConsoleSession(
                open_console_pipe(pipe, timeout=open_timeout), max_bytes=max_bytes
            )
        except Exception:
            self.lease.close()
            raise
        self.prompt = None
        self.history = []
        self.partial_output = b""
        self.failed = False

    def _receive(self, *, confirmation=False, initial=b""):
        answer = "Y" if confirmation is True else confirmation
        if confirmation is not False and (not isinstance(answer, str) or answer not in {"Y", "N"}):
            raise ConsoleError(
                "Only explicit Y/N confirmations are supported", code="invalid_confirmation"
            )
        output = bytearray(initial)
        deadline = time.monotonic() + self.timeout
        pager_count = 0
        last_pager_size = -1
        confirmed = False
        while time.monotonic() < deadline:
            if len(output) > self.max_bytes:
                raise ConsoleError(
                    "Console output exceeds the evidence limit; truncation is not accepted",
                    code="output_limit",
                    detail={"stage": "read", "observed_bytes": len(output)},
                )
            text = clean_text(bytes(output))
            if confirmation and not confirmed and re.search(r"\[(?:Y/N|y/n)\]:?\s*$", text):
                self.session.send(answer)
                confirmed = True
            if PAGER.search(text) and len(output) != last_pager_size:
                # Space is the documented pager continuation, not a command line.
                try:
                    sent = os.write(self.session._write_fd, b" ")
                except OSError as exc:
                    from mcp_hcl.console import _os_error

                    raise _os_error(exc, stage="pager", api="os.write") from exc
                if sent != 1:
                    raise ConsoleError(
                        "Pager continuation write failed",
                        code="pager_write_failed",
                        detail={"stage": "pager"},
                    )
                last_pager_size = len(output)
                pager_count += 1
                if pager_count > 256:
                    raise ConsoleError(
                        "Console pagination exceeded the page limit",
                        code="pager_limit",
                        detail={"stage": "read"},
                    )
            match = PROMPT.search(text)
            if match:
                self.prompt = match[1]
                return bytes(output)
            chunk = self.session._read_available()
            if chunk:
                output.extend(chunk)
                self.partial_output = bytes(output)
            else:
                time.sleep(0.02)
        raise ConsoleError(
            "No complete console prompt before deadline",
            code="prompt_timeout",
            detail={"stage": "read"},
        )

    def exchange(self, command: str, *, confirmation=False) -> dict:
        self.partial_output = b""
        stale = b""
        sent = False
        try:
            if self.failed:
                raise ConsoleError(
                    "Failed console transaction requires reconciliation and a new connection",
                    code="console_session_failed",
                    detail={"stage": "precondition"},
                )
            if (
                confirmation is not False
                and confirmation is not True
                and (not isinstance(confirmation, str) or confirmation not in {"Y", "N"})
            ):
                raise ConsoleError(
                    "Only explicit Y/N confirmations are supported",
                    code="invalid_confirmation",
                    detail={"stage": "precondition"},
                )
            stale = self.session.drain()
            if len(stale) >= self.max_bytes:
                raise ConsoleError(
                    "Stale stream cannot be drained safely",
                    code="stale_output_limit",
                    detail={"stage": "drain"},
                )
            self.session.send(command)
            sent = True
            raw = self._receive(confirmation=confirmation)
            text = clean_text(raw)
            lines = text.splitlines()
            echo = any(
                line.strip() == command
                or line.strip().endswith(">" + command)
                or line.strip().endswith("]" + command)
                for line in lines
            )
            if not echo:
                raise ConsoleError(
                    "Console command echo is missing; response attribution failed",
                    code="command_echo_missing",
                    detail={"stage": "attribution"},
                )
            if CLI_ERROR.search(text):
                raise ConsoleError(
                    "Device rejected the console command",
                    code="command_rejected",
                    detail={"stage": "response"},
                )
        except ConsoleError as exc:
            self.failed = True
            outcome = (
                "unknown" if sent or exc.detail.get("command_outcome") == "unknown" else "not_sent"
            )
            exc.detail["command_outcome"] = outcome
            self.history.append(
                {
                    "command": command,
                    "output": clean_text(self.partial_output),
                    "raw_output_b64": base64.b64encode(self.partial_output).decode("ascii"),
                    "output_sha256": hashlib.sha256(self.partial_output).hexdigest(),
                    "discarded_stale_bytes": len(stale),
                    "command_outcome": outcome,
                    "complete": False,
                    "error": str(exc),
                    "errors": [exc.as_error()],
                }
            )
            raise
        result = {
            "command": command,
            "output": text,
            "prompt": self.prompt,
            "raw_output_b64": base64.b64encode(raw).decode("ascii"),
            "output_sha256": hashlib.sha256(raw).hexdigest(),
            "request_sha256": hashlib.sha256(command.encode("ascii")).hexdigest(),
            "discarded_stale_bytes": len(stale),
            "complete": True,
        }
        self.history.append(result)
        return result

    def close(self):
        try:
            self.session.close()
        finally:
            self.lease.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
