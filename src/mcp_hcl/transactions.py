"""Shared bounded console exchanges and durable operation receipt helpers.

Legacy NAT error codes/messages are preserved for existing callers.
"""

from __future__ import annotations

import json
import os
import time
from uuid import uuid4

from mcp_hcl.console import ConsoleError
from mcp_hcl.runtime_binding import unlinked


class BudgetConsole:
    """Limit each native exchange to the remaining operation time; never replay."""

    def __init__(self, channel, deadline):
        self.channel = channel
        self.deadline = deadline

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def exchange(self, command, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ConsoleError("NAT operation deadline reached", code="nat_deadline_exceeded")
        previous = getattr(self.channel, "timeout", None)
        if previous is not None:
            self.channel.timeout = min(previous, remaining)
        try:
            result = self.channel.exchange(command, **kwargs)
        finally:
            if previous is not None:
                self.channel.timeout = previous
        if time.monotonic() >= self.deadline:
            raise ConsoleError(
                "NAT exchange completed after its deadline", code="nat_deadline_exceeded"
            )
        return result


def atomic_json(path, data):
    unlinked(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".new")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def unique_json(path):
    unlinked(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("NAT identity metadata exceeds its read budget")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate NAT identity metadata key")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def operation_json(path):
    """Unreadable history is an incomplete record, never replay authority."""
    try:
        record = unique_json(path)
    except (OSError, ValueError, ConsoleError):
        return None
    return record if isinstance(record, dict) else None


def incomplete_operation(operation, directory):
    return {
        "status": "unverified",
        "operation_id": operation,
        "receipt_directory": str(directory),
        "current_state_rechecked": False,
        "configuration_verified": False,
        "persistence_verified": False,
        "full_live_gate_passed": False,
        "errors": [
            {
                "code": "operation_record_incomplete",
                "message": "Prior operation history is missing or invalid; no commands were replayed",
            }
        ],
    }
