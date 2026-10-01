"""Bounded client for the observed HCL SimwareWrapper control protocol.

Two deliberately separate layers:

* :meth:`HclBackend._request` keeps the original narrow path: exactly two
  observed read-only commands, used by ``hcl_bridge_status``.  It is unchanged
  so that a running server can never grow new powers by accident.
* :meth:`HclBackend.invoke` drives the observed **verb registry** below.  Every
  verb carries an evidence level and a write flag; write verbs are refused
  unless the process was started with ``MCP_HCL_ALLOW_BACKEND_WRITE=1``.

Wire format (observed in HCL 5.10.3's own logs, see
``docs/hcl-backend-protocol.md``)::

    request : <id> <service> <verb> [args...]\\n
    response: <id>-<code>-<payload>\\r\\n/end

``code`` 100/101 mean success; 200/204/210/228 were observed as failures.

Nothing here is vendor-documented.  Arguments are rendered from observation,
not from a specification, so every builder validates shape strictly and refuses
tokens that could break the line-oriented framing.
"""

from __future__ import annotations

import ipaddress
import re
import secrets
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


class BackendError(RuntimeError):
    """A local backend response cannot be attributed to this probe."""


_READ_ONLY_COMMANDS = {"simwarewrapper version", "simwarewrapper system_memory"}
_END = b"\r\n/end"
_MAX_RESPONSE = 65536
_SUCCESS_CODES = frozenset({100, 101})
_OBSERVED_FAILURE_CODES = frozenset({200, 204, 210, 228})

#: A single protocol token: no whitespace, no control characters.  The protocol
#: is line- and space-delimited, so anything else would be command injection.
_TOKEN = re.compile(r"^[^\s\x00-\x1f\x7f]+$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


def _token(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise BackendError(
            f"{field_name} must be a single non-empty token without whitespace or control characters"
        )
    return value


def _name(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise BackendError(f"{field_name} must match [A-Za-z][A-Za-z0-9_-]{{0,31}}")
    return value


def _integer(value: Any, field_name: str, *, low: int, high: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BackendError(f"{field_name} must be an integer")
    if not low <= value <= high:
        raise BackendError(f"{field_name} must be between {low} and {high}")
    return str(value)


def _bool(value: Any, field_name: str) -> str:
    if not isinstance(value, bool):
        raise BackendError(f"{field_name} must be a boolean")
    # HCL renders Python booleans: 'True' / 'False' were both observed.
    return "True" if value else "False"


def _absolute_directory(value: Any, field_name: str) -> str:
    text = _token(value, field_name)
    if not re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", text):
        raise BackendError(f"{field_name} must be an absolute Windows path")
    return text


def _build_create_topology(arguments: dict[str, Any]) -> str:
    return " ".join((
        _name(arguments.get("topology"), "topology"),
        _absolute_directory(arguments.get("working_directory"), "working_directory"),
        _name(arguments.get("project_name"), "project_name"),
        _integer(arguments.get("udp_port"), "udp_port", low=1024, high=65535),
    ))


def _build_delete_udp(arguments: dict[str, Any]) -> str:
    return " ".join((
        _integer(arguments.get("device"), "device", low=1, high=1024),
        "0",
        "0",
    ))


def _build_start(arguments: dict[str, Any]) -> str:
    return " ".join((
        _integer(arguments.get("device"), "device", low=1, high=1024),
        "0",
    ))


def _build_normal_close(arguments: dict[str, Any]) -> str:
    return _bool(arguments.get("normal"), "normal")


def _build_set_hcl_tcp(arguments: dict[str, Any]) -> str:
    return _integer(arguments.get("port"), "port", low=1024, high=65535)


def _build_set_hcl_normal_close(arguments: dict[str, Any]) -> str:
    return _bool(arguments.get("normal"), "normal")


@dataclass(frozen=True)
class VerbSpec:
    """One observed backend verb and how far we trust it."""

    verb: str
    service: str
    kind: str
    evidence: str
    writes: bool
    invocable: bool
    summary: str
    build: Callable[[dict[str, Any]], str] | None = None
    note: str = ""

    def describe(self, *, writes_enabled: bool) -> dict[str, Any]:
        return {
            "verb": self.verb,
            "service": self.service,
            "kind": self.kind,
            "evidence": self.evidence,
            "writes": self.writes,
            "invocable": self.invocable,
            "enabled": self.invocable and (writes_enabled or not self.writes),
            "summary": self.summary,
            "note": self.note,
        }


def _verb(verb: str, service: str, kind: str, evidence: str, writes: bool, invocable: bool,
          summary: str, build: Callable[[dict[str, Any]], str] | None = None,
          note: str = "") -> VerbSpec:
    return VerbSpec(verb, service, kind, evidence, writes, invocable, summary, build, note)


#: The verb registry.  ``invocable=False`` means the verb was observed in HCL's
#: logs but its field semantics are not understood well enough to reproduce it
#: safely; it is listed for introspection only.
OBSERVED_VERBS: dict[str, VerbSpec] = {
    spec.verb: spec for spec in (
        _verb("version", "simwarewrapper", "read", "verified", False, True,
              "Backend version string.", None,
              "Used by hcl_bridge_status."),
        _verb("system_memory", "simwarewrapper", "read", "verified", False, True,
              "Reported system memory in MB.", None,
              "Used by hcl_bridge_status."),
        _verb("create_topology", "simware", "topology", "observed", True, True,
              "Bind a backend topology context to a project directory.",
              _build_create_topology,
              "Argument order confirmed from HCL's own request line; field meanings beyond "
              "the directory are still inferred."),
        _verb("start", "simware", "power", "observed", True, True,
              "Power on one device (device index).", _build_start,
              "Observed exactly once, as the command HCL sent when 启动 was invoked. That "
              "attempt failed for a hypervisor reason (VERR_NEM_VM_CREATE_FAILED), so the "
              "verb itself is not disproven but is NOT verified to boot a guest."),
        _verb("start_recover", "simware", "power", "observed", True, True,
              "Recover/start the topology's devices.", None,
              "No arguments observed."),
        _verb("delete_udp", "simware", "console", "observed", True, True,
              "Tear down one device's console/UDP channel.", _build_delete_udp,
              "Trailing flags reproduced from observation."),
        _verb("normal_close", "simware", "lifecycle", "observed", True, True,
              "Ask the backend wrapper to close normally.", _build_normal_close),
        _verb("set_hcl_tcp", "simware", "lifecycle", "observed", True, True,
              "Tell the backend which TCP port HCL listens on.", _build_set_hcl_tcp,
              "18600 was the only observed value."),
        _verb("set_hcl_normal_close", "simware", "lifecycle", "observed", True, True,
              "Set the normal-close policy.", _build_set_hcl_normal_close),
        _verb("create_udp", "simware", "console", "inferred", True, False,
              "Allocate a device console; the reply carries the pipe name.", None,
              "Reply shape is known (a pipe path plus a boolean) but the UDP port arguments "
              "are only partly understood. Not needed: the pipe name is deterministic once "
              "HCL has loaded the topology."),
        _verb("create", "simware", "device", "inferred", True, False,
              "Create one device VM. 14 positional fields, six of them unexplained.", None,
              "Refused on purpose: guessing memory/slot/flag fields could create broken VMs."),
        _verb("delete", "simware", "device", "inferred", True, False,
              "Delete one device VM.", None, "Argument shape not fully sampled."),
        _verb("set_memory", "simware", "device", "inferred", True, False,
              "Adjust a device's memory.", None, "Not sampled."),
        _verb("set_version_path", "simware", "device", "inferred", True, False,
              "Point a device at a firmware image.", None, "Not sampled."),
        _verb("save", "simware", "lifecycle", "inferred", True, False,
              "Persist backend state.", None, "Not sampled."),
    )
}


def _frames(payload: bytes) -> list[dict[str, Any]]:
    """Parse every complete ``<id>-<code>-<payload>`` frame in a byte buffer.

    HCL's wrapper emits a **spurious trailing frame** when it reads an empty
    request after the client has closed (observed: ``send_reply(done=1,
    errorCode=200, parameters=None)`` with no request id).  Parsing therefore
    collects all *terminated* frames and the caller matches on the request id,
    instead of assuming exactly one frame per connection.

    The trailing chunk after the last ``/end`` is deliberately discarded: it is
    a partially received frame, and treating it as complete would silently
    truncate a value that TCP happened to split across two reads.

    A frame whose reply carries no parameters omits the payload segment
    entirely - observed raw: ``b'222222222-100\\r\\n/end'`` - so the payload is
    optional rather than ``-None``.
    """
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise BackendError("Backend response is not valid UTF-8") from exc
    frames: list[dict[str, Any]] = []
    for chunk in text.split("/end")[:-1]:
        chunk = chunk.strip("\r\n")
        if not chunk:
            continue
        match = re.fullmatch(r"([0-9]+)-([0-9]{3})(?:-(.*))?", chunk, re.DOTALL)
        if match is None:
            continue
        frames.append({"id": int(match[1]), "code": int(match[2]), "value": match[3] or ""})
    return frames


class _Wire:
    """Request/reply framing over one TCP connection to SimwareWrapper."""

    def __init__(self, connection: socket.socket, timeout: float) -> None:
        self._connection = connection
        self._timeout = timeout
        self._connection.settimeout(timeout)

    def exchange(self, command: str, *,
                 accepted_codes: frozenset[int] | None = _SUCCESS_CODES) -> dict[str, Any]:
        request_id = secrets.randbelow(900_000_000) + 100_000_000
        self._connection.sendall(f"{request_id} {command}\n".encode("ascii"))
        response = bytearray()
        deadline = time.monotonic() + self._timeout
        match: dict[str, Any] | None = None
        while True:
            match = next((frame for frame in _frames(bytes(response))
                          if frame["id"] == request_id), None)
            if match is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._connection.settimeout(remaining)
            try:
                chunk = self._connection.recv(min(4096, _MAX_RESPONSE + 1 - len(response)))
            except (TimeoutError, socket.timeout):
                break
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > _MAX_RESPONSE:
                raise BackendError("Backend response exceeds the size limit")
        frames = _frames(bytes(response))
        if match is None:
            if frames:
                raise BackendError("Backend returned a different request ID")
            if not response:
                raise BackendError("Backend sent no response before the deadline")
            raise BackendError("Backend response has an unknown wire format")
        code = match["code"]
        if accepted_codes is not None and code not in accepted_codes:
            raise BackendError(f"Backend rejected the read-only probe with code {code}")
        return {
            "request_id": request_id, "command": command,
            "response_code": code, "value": match["value"],
            "extra_frames": max(len(frames) - 1, 0),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "layer": "backend_protocol",
        }


def _invoke(exchange: Callable[[str], dict[str, Any]], verb: str,
            arguments: dict[str, Any] | None, *, writes_enabled: bool) -> dict[str, Any]:
    """Shared body for one registry verb over any exchange callable."""
    arguments = dict(arguments or {})
    operation_id = uuid4().hex
    result: dict[str, Any] = {
        "status": "rejected", "operation": "backend_invoke", "operation_id": operation_id,
        "verb": verb, "target_project": None, "evidence": [],
        "runtime_verified": False, "full_live_gate_passed": False,
        "live_canvas_verified": False,
    }
    spec = OBSERVED_VERBS.get(verb)
    if spec is None:
        result["errors"] = [{"code": "unknown_verb", "message": f"Verb is not observed: {verb}"}]
        return result
    if not spec.invocable:
        result["errors"] = [{
            "code": "verb_not_invocable",
            "message": f"{verb} was observed but its field semantics are not understood; "
                       f"it is introspection-only.",
        }]
        return result
    if spec.writes and not writes_enabled:
        result["errors"] = [{
            "code": "writes_disabled",
            "message": "This verb changes HCL state. Start the server with "
                       "MCP_HCL_ALLOW_LIVE_WRITE=1 after an explicit decision.",
        }]
        return result
    try:
        payload = spec.build(arguments) if spec.build else ""
    except BackendError as exc:
        result["errors"] = [{"code": "invalid_arguments", "message": str(exc)}]
        return result
    command = f"{spec.service} {verb}" + (f" {payload}" if payload else "")
    try:
        reply = exchange(command)
    except BackendError as exc:
        result["status"] = "unverified"
        result["errors"] = [{"code": "backend_unreachable", "message": str(exc)}]
        return result
    result["response_code"] = reply["response_code"]
    result["value"] = reply["value"]
    result["request_id"] = reply["request_id"]
    result["evidence"] = [reply]
    if reply["response_code"] in _SUCCESS_CODES:
        result["status"] = "accepted"
        result["verified_scope"] = "backend_accepted_the_command_only"
    else:
        result["errors"] = [{
            "code": "backend_error_code",
            "message": f"Backend answered with code {reply['response_code']}",
        }]
    return result


@dataclass
class BackendSession:
    """One persistent connection, which is how HCL itself drives the backend.

    **Observed 2026-10-01**: the wrapper keys its topology context to the
    *connection*.  ``create_topology`` on a connection makes the handler adopt
    that topology (``SimwareTopo __init__, TopoName is mcphcl1``), and a later
    request on a *different* connection is handled with topology ``None`` and
    answers ``errorCode=228`` for verbs that need one (observed for ``start``).
    A one-shot connection per request therefore cannot power anything on.
    """

    wire: _Wire
    writes_enabled: bool = False
    topology: str | None = None
    project_directory: str | None = None
    commands_sent: list[str] = field(default_factory=list)

    def invoke(self, verb: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = _invoke(lambda command: self.wire.exchange(command, accepted_codes=None),
                         verb, arguments, writes_enabled=self.writes_enabled)
        spec = OBSERVED_VERBS.get(verb)
        if spec is not None:
            self.commands_sent.append(f"{spec.service} {verb}")
        return result

    def open_topology(self, topology: str, working_directory: str,
                      project_name: str | None = None, udp_port: int = 10000) -> dict[str, Any]:
        result = self.invoke("create_topology", {
            "topology": topology, "working_directory": working_directory,
            "project_name": project_name, "udp_port": udp_port,
        })
        if result.get("status") == "accepted":
            self.topology = topology
            self.project_directory = working_directory
        return result

    def close_topology(self) -> dict[str, Any]:
        result = self.invoke("normal_close", {"normal": True})
        self.topology = None
        self.project_directory = None
        return result

    def close(self) -> None:
        try:
            self.wire._connection.close()  # noqa: SLF001 - the session owns the socket
        except OSError:
            pass


@dataclass(frozen=True)
class HclBackend:
    host: str = "127.0.0.1"
    port: int = 16600
    timeout: float = 2.0
    allow_writes: bool = False

    def __post_init__(self) -> None:
        if not ipaddress.ip_address(self.host).is_loopback:
            raise ValueError("Backend probes require a loopback IP address")
        if not 1 <= self.port <= 65535 or not 0.1 <= self.timeout <= 5:
            raise ValueError("Invalid backend port or timeout")

    # ------------------------------------------------------------------ wire
    def _exchange(self, command: str, *,
                  accepted_codes: frozenset[int] | None = _SUCCESS_CODES) -> dict[str, Any]:
        """Open one connection, send one command, parse the framed reply."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
                return _Wire(connection, self.timeout).exchange(command, accepted_codes=accepted_codes)
        except OSError as exc:
            raise BackendError(f"Backend connection failed: {exc.__class__.__name__}") from exc

    def _request(self, command: str) -> dict[str, Any]:
        """The original narrow path: two observed read-only commands, nothing else."""
        if command not in _READ_ONLY_COMMANDS:
            raise ValueError("Only observed read-only backend commands are allowed")
        return self._exchange(command)

    # ------------------------------------------------------------- verb API
    def verbs(self) -> list[dict[str, Any]]:
        """Introspection for ``hcl_backend_capabilities``; never touches the network."""
        return [spec.describe(writes_enabled=self.allow_writes)
                for spec in sorted(OBSERVED_VERBS.values(), key=lambda item: (item.service, item.verb))]

    def invoke(self, verb: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call one registry verb on a **one-shot** connection.

        Only safe for verbs that do not need a topology context (reads,
        lifecycle).  Anything that operates on a topology - ``start`` above all -
        needs :meth:`connect`, because the wrapper keys the topology to the
        connection.
        """
        return _invoke(lambda command: self._exchange(command, accepted_codes=None),
                       verb, arguments, writes_enabled=self.allow_writes)

    def connect(self) -> BackendSession:
        """Open a persistent connection for topology-scoped verbs."""
        try:
            connection = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise BackendError(f"Backend connection failed: {exc.__class__.__name__}") from exc
        return BackendSession(_Wire(connection, self.timeout), writes_enabled=self.allow_writes)

    # --------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        """Read version and memory, with explicit limits on what was verified."""
        evidence: list[dict[str, Any]] = []
        result: dict[str, Any] = {
            "status": "unverified",
            "operation": "read_only_backend_probe",
            "operation_id": uuid4().hex,
            "target_project": None,
            "endpoint": {"host": self.host, "port": self.port},
            "live_canvas_verified": False,
            "full_live_gate_passed": False,
            "evidence": evidence,
        }
        try:
            version = self._request("simwarewrapper version")
            evidence.append(version)
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+&[0-9]+\.[0-9]+\.[0-9]+", version["value"]):
                raise BackendError("Backend version does not match the observed HCL format")
            result["backend_version"] = version["value"]
            memory = self._request("simwarewrapper system_memory")
            evidence.append(memory)
            if not re.fullmatch(r"[0-9]{1,10}", memory["value"]) or int(memory["value"]) <= 0:
                raise BackendError("Backend memory response is invalid")
            result["reported_system_memory_mb"] = int(memory["value"])
            result["status"] = "verified"
            result["verified_scope"] = "version_and_memory_protocol_readback"
        except BackendError as exc:
            result["status"] = "partial" if "backend_version" in result else "unverified"
            result["error"] = str(exc)
        return result
