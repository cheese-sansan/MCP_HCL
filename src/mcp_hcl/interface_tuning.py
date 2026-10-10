"""Scoped Comware interface tuning; encrypted key values remain explicit limits."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator

from mcp_hcl.console import ConsoleError
from mcp_hcl.contracts import validation_errors
from mcp_hcl.deployment import config_text
from mcp_hcl.gui_relay import rejected
from mcp_hcl.models import StrictModel
from mcp_hcl.policy import scopes
from mcp_hcl.runtime_binding import unlinked
from mcp_hcl.services import InterfaceName
from mcp_hcl.transactions import (
    BudgetConsole,
    atomic_json,
    incomplete_operation,
    operation_json,
    unique_json,
)

SCALARS = {
    "bandwidth": "bandwidth",
    "ospf_cost": "ospf cost",
    "ospf_priority": "ospf dr-priority",
    "ospf_hello_interval": "ospf timer hello",
    "ospf_dead_interval": "ospf timer dead",
}


class InterfaceTuning(StrictModel):
    router: str = Field(min_length=1, max_length=64)
    interface: InterfaceName
    clock_rate: int | None = Field(default=None, ge=1)
    bandwidth: int | None = Field(default=None, ge=1, le=400000000)
    ospf_cost: int | None = Field(default=None, ge=0, le=65535)
    ospf_priority: int | None = Field(default=None, ge=0, le=255)
    ospf_hello_interval: int | None = Field(default=None, ge=1, le=65535)
    ospf_dead_interval: int | None = Field(default=None, ge=1, le=2147483647)
    delay: int | None = Field(default=None, ge=0)
    ospf_auth_key: SecretStr | None = None
    ospf_md5_key_id: int | None = Field(default=None, ge=1, le=255)
    ospf_md5_key: SecretStr | None = None
    operation_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("router")
    @classmethod
    def printable(cls, value):
        if not value.strip() or any(not c.isprintable() for c in value):
            raise ValueError("Router selector must be printable")
        return value

    @field_validator("ospf_auth_key", "ospf_md5_key")
    @classmethod
    def secret_token(cls, value):
        if value is None:
            return value
        text = value.get_secret_value()
        if not text or any(not c.isascii() or not c.isprintable() or c.isspace() for c in text):
            raise ValueError("OSPF key must be one printable ASCII token")
        return value

    @model_validator(mode="after")
    def related_fields(self):
        if self.clock_rate is not None and not self.interface.casefold().startswith("serial"):
            raise ValueError("clock_rate is only valid on a serial interface")
        if self.ospf_cost == 0 and not self.interface.casefold().startswith("loopback"):
            raise ValueError("Zero OSPF cost is only represented for loopback interfaces")
        if self.ospf_md5_key is not None and self.ospf_md5_key_id is None:
            raise ValueError("MD5 authentication needs its key ID")
        if self.ospf_md5_key_id is not None and self.ospf_md5_key is None:
            raise ValueError("Key ID without an MD5 key has no operation effect")
        if (
            self.ospf_auth_key is not None
            and self.ospf_md5_key is None
            and len(self.ospf_auth_key.get_secret_value()) > 8
        ):
            raise ValueError(
                "Installed Comware simple-authentication key limit is 8 ASCII characters"
            )
        if self.ospf_md5_key is not None and len(self.ospf_md5_key.get_secret_value()) > 16:
            raise ValueError("Installed Comware MD5 key limit is 16 ASCII characters")
        if self.ospf_hello_interval is not None and self.ospf_dead_interval is not None:
            if self.ospf_dead_interval <= self.ospf_hello_interval:
                raise ValueError("OSPF dead interval must exceed hello interval")
            if self.ospf_dead_interval < 4 * self.ospf_hello_interval:
                raise ValueError(
                    "Installed Comware documentation requires dead interval at least four times hello"
                )
        return self

    @property
    def secrets(self):
        return [
            value.get_secret_value()
            for value in (self.ospf_auth_key, self.ospf_md5_key)
            if value is not None
        ]

    @property
    def unsupported(self):
        # Do not turn IOS metric delay into physical link-delay or invent DCE syntax.
        return [field for field in ("clock_rate", "delay") if getattr(self, field) is not None]


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            value = re.sub(
                r"(?<![A-Za-z0-9])" + re.escape(secret) + r"(?![A-Za-z0-9])", "[REDACTED]", value
            )
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        if not secrets:
            return {key: redact(item, secrets) for key, item in value.items()}
        # Encoded raw text and secret-dependent hashes must not bypass redaction.
        omitted = {"raw_output_b64", "request_sha256", "output_sha256", "input_sha256"}
        result = {}
        for key, item in value.items():
            if key in omitted:
                continue
            # An error/console reply can concatenate a credential with other
            # text. Token boundaries are unsuitable for these free-text fields.
            # Keep enum/identity fields on the existing token-aware path.
            if key in {"message", "command", "output", "error"} and isinstance(item, str):
                for secret in secrets:
                    item = item.replace(secret, "[REDACTED]")
            result[key] = redact(item, secrets)
        return result | {"redacted": True}
    return value


def commands(parameters, *, reveal=False):
    result = [
        f"{prefix} {getattr(parameters, field)}"
        for field, prefix in SCALARS.items()
        if getattr(parameters, field) is not None
    ]
    if parameters.ospf_md5_key is not None:
        key = parameters.ospf_md5_key.get_secret_value() if reveal else "[REDACTED]"
        result.append(f"ospf authentication-mode md5 {parameters.ospf_md5_key_id} plain {key}")
    elif parameters.ospf_auth_key is not None:
        key = parameters.ospf_auth_key.get_secret_value() if reveal else "[REDACTED]"
        result.append("ospf authentication-mode simple plain " + key)
    return ["system-view", "interface " + parameters.interface, *result, "quit", "return"]


def target_expected(before, parameters):
    expected = copy.deepcopy(scopes(before))
    context = ("interface " + parameters.interface,)
    if context not in expected:
        raise ValueError("Requested tuning interface is absent from the current configuration")
    body = expected[context]
    for field, prefix in SCALARS.items():
        value = getattr(parameters, field)
        if value is not None:
            body.difference_update(line for line in list(body) if line.startswith(prefix + " "))
            body.add(prefix + " " + str(value))
    return expected


def readback_verified(before, after, parameters):
    """Protect every other view and all unrequested interface commands."""
    wanted = target_expected(before, parameters)
    actual = scopes(after)
    context = ("interface " + parameters.interface,)
    if context not in actual:
        return False
    protected = wanted[context]
    observed = set(actual[context])
    auth_requested = parameters.ospf_auth_key is not None or parameters.ospf_md5_key is not None
    if auth_requested:
        for line in list(protected):
            if not line.startswith("ospf authentication-mode "):
                continue
            if parameters.ospf_md5_key is None or not re.match(
                r"^ospf authentication-mode md5 \d+ ", line
            ):
                protected.discard(line)
            elif re.match(
                r"^ospf authentication-mode md5 " + str(parameters.ospf_md5_key_id) + r" ", line
            ):
                protected.discard(line)
        if parameters.ospf_md5_key is not None:
            selected = [
                line
                for line in observed
                if re.fullmatch(
                    r"ospf authentication-mode md5 "
                    + str(parameters.ospf_md5_key_id)
                    + r" cipher \S{33,53}",
                    line,
                )
            ]
        else:
            selected = [
                line
                for line in observed
                if re.fullmatch(r"ospf authentication-mode simple cipher \S{33,41}", line)
            ]
        if len(selected) != 1:
            return False
        observed.difference_update(selected)
    # DR priority 1 is a documented fixed default, unlike network-dependent timers.
    if parameters.ospf_priority == 1 and "ospf dr-priority 1" not in observed:
        protected.discard("ospf dr-priority 1")
    if (
        parameters.ospf_cost == 0
        and parameters.interface.casefold().startswith("loopback")
        and "ospf cost 0" not in observed
    ):
        protected.discard("ospf cost 0")
    actual[context] = observed
    return actual == wanted


class InterfaceTuningOperation:
    def __init__(self, policy):
        self.policy = policy

    def apply(self, project_path, topology, parameters, dry_run=False):
        if not dry_run and not self.policy.writes_enabled:
            return rejected("writes_disabled", "Interface tuning requires the live write switch")
        try:
            typed = InterfaceTuning.model_validate(parameters)
        except ValidationError as exc:
            return {
                "status": "rejected",
                "errors": validation_errors(exc),
                "full_live_gate_passed": False,
            }
        if typed.unsupported:
            return {
                "status": "unverified",
                "errors": [
                    {
                        "code": "interface_mapping_unverified",
                        "message": "No accepted Comware equivalent for the complete requested operation",
                    }
                ],
                "unsupported_fields": typed.unsupported,
                "commands": None,
                "full_live_gate_passed": False,
            }
        document, bindings = self.policy.deployment.bindings(project_path)
        matches = [
            (identifier, binding)
            for identifier, binding in bindings.items()
            if identifier == typed.router or binding["name"] == typed.router
        ]
        if len(matches) != 1:
            return rejected("invalid_tuning_target", "Select one exact staged router")
        identifier, binding = matches[0]
        preview = commands(typed)
        if dry_run:
            return {
                "status": "verified",
                "commands": preview,
                "verified_scope": "offline_interface_tuning_command_intent_only",
                "secret_values_redacted": bool(typed.secrets),
                "configuration_verified": False,
                "authentication_key_verified": False,
                "full_live_gate_passed": False,
            }
        operation = typed.operation_key or uuid4().hex
        directory = self.policy.store.output_root / ".interface-tuning-receipts" / operation
        unlinked(directory)
        request = {
            "project": str(document.net_path),
            "device": identifier,
            "topology": topology,
            "parameters": typed.model_dump(mode="json"),
        }
        fingerprint = hashlib.sha256(
            json.dumps(request, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if directory.exists():
            if typed.secrets:
                return {
                    "status": "unverified",
                    "operation_id": operation,
                    "errors": [
                        {
                            "code": "secret_operation_key_reuse",
                            "message": "Redacted credentials cannot be compared for replay; inspect the prior operation",
                        }
                    ],
                    "configuration_verified": False,
                    "full_live_gate_passed": False,
                }
            old = operation_json(directory / "request.json")
            if old is None:
                return incomplete_operation(operation, directory)
            if old.get("fingerprint") != fingerprint:
                return rejected("operation_key_conflict", "Tuning key belongs to another request")
            path = directory / "result.json"
            recorded = operation_json(path)
            if recorded is None:
                return incomplete_operation(operation, directory)
            return {
                "status": "output_received",
                "operation_id": operation,
                "previous_result": recorded,
                "current_state_rechecked": False,
                "configuration_verified": False,
                "full_live_gate_passed": False,
            }
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / "request.json", {"fingerprint": fingerprint, **request})
        result = {
            "status": "unverified",
            "operation_id": operation,
            "device": identifier,
            "receipt_directory": str(directory),
            "commands": preview,
            "errors": [],
            "configuration_verified": False,
            "protocol_effect_verified": False,
            "persistence_verified": False,
            "protocol_persistence_verified": False,
            "authentication_key_verified": False,
            "rollback_verified": False,
            "protocol_rollback_verified": False,
            "full_live_gate_passed": False,
        }
        channel = None
        identity = None
        backup = None
        dirty = False
        archived = []
        deadline = time.monotonic() + typed.timeout_seconds
        try:
            raw, identity = self.policy.open(document, binding, topology)
            channel = BudgetConsole(raw, deadline)
            result["target_identity"] = identity

            def saved(record):
                nonlocal backup, dirty
                backup, dirty = record, True

            backup = self.policy.deployment._backup(
                channel, identifier, directory, operation, on_saved=saved
            )
            dirty = False
            before = Path(backup["local_file"]).read_text(encoding="utf-8")
            target_expected(before, typed)
            result["backup"] = backup
            dirty = True
            for command in commands(typed, reveal=True):
                channel.exchange(command)
            after = config_text(channel.exchange("display current-configuration")["output"])
            if not readback_verified(before, after, typed):
                raise ConsoleError(
                    "Interface tuning readback or scope mismatch",
                    code="interface_tuning_unverified",
                )
            result["persistence"] = self.policy.deployment.startup.persist(
                channel, backup["startup"], after, f"flash:/mcp_{operation}_{identifier}_after.cfg"
            )
            native = self.policy.native_dependencies and getattr(channel, "native_channel", False)
            result.update(
                status="partial" if typed.secrets else "verified" if native else "output_received",
                configuration_verified=native and not typed.secrets,
                protocol_effect_verified=True,
                persistence_verified=native,
                protocol_persistence_verified=True,
                verified_scope="bound_interface_fields_and_cipher_shape_only"
                if typed.secrets
                else "bound_native_interface_tuning_configuration_only"
                if native
                else "synthetic_interface_tuning_only",
            )
            if typed.secrets:
                result["warnings"] = [
                    {
                        "code": "encrypted_key_value_unverified",
                        "message": "Cipher type and key ID read back; supplied plaintext equivalence and neighbour authentication remain unverified",
                    }
                ]
        except (ConsoleError, OSError, ValueError) as exc:
            result["errors"] = [
                exc.as_error()
                if isinstance(exc, ConsoleError)
                else {"code": "interface_tuning_failed", "message": str(exc)}
            ]
            if dirty and backup is not None and identity is not None:
                try:
                    if channel is not None:
                        archived = list(getattr(channel, "history", []))
                        channel.close()
                        channel = None
                    raw, recovered = self.policy.open(
                        document, binding, topology, identity["vm_uuid"]
                    )
                    channel = BudgetConsole(raw, time.monotonic() + typed.timeout_seconds)
                    result["recovery_identity"] = recovered
                    result["rollback"] = self.policy.deployment._restore(channel, backup)
                    result["protocol_rollback_verified"] = True
                    result["rollback_verified"] = self.policy.native_dependencies and getattr(
                        channel, "native_channel", False
                    )
                except (ConsoleError, OSError, ValueError) as recovery:
                    result["rollback"] = {
                        "status": "unverified",
                        "error": recovery.as_error()
                        if isinstance(recovery, ConsoleError)
                        else str(recovery),
                        "running_snapshot": backup["local_file"],
                        "startup_snapshot": backup.get("startup"),
                    }
        finally:
            result["finished_utc"] = datetime.now(timezone.utc).isoformat()
            history = archived + (getattr(channel, "history", []) if channel is not None else [])
            receipt_error = None
            try:
                atomic_json(directory / "transcript.json", redact(history, typed.secrets))
            except (ConsoleError, OSError, ValueError) as exc:
                receipt_error = exc
                result["status"] = "unverified"
                result["errors"].append(
                    {"code": "tuning_transcript_io_failed", "message": str(exc)}
                )
            if channel is not None:
                try:
                    channel.close()
                except (ConsoleError, OSError) as exc:
                    result["status"] = "unverified"
                    result["errors"].append(
                        {"code": "tuning_channel_close_failed", "message": str(exc)}
                    )
            try:
                atomic_json(directory / "result.json", redact(result, typed.secrets))
            except (ConsoleError, OSError, ValueError) as exc:
                receipt_error = exc
            if receipt_error is not None:
                raise ConsoleError(
                    "Interface tuning receipt is incomplete; do not replay",
                    code="tuning_receipt_io_failed",
                    detail={
                        "operation_id": operation,
                        "receipt_directory": str(directory),
                        "device_mutation_possible": dirty,
                    },
                ) from receipt_error
        return redact(result, typed.secrets)
