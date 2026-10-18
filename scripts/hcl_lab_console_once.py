"""One explicitly enabled display-version probe; all stages retain a new receipt."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4


class ReceiptWriteError(OSError):
    def __init__(self, result):
        super().__init__("Probe receipt could not be persisted")
        self.result = result


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate specification fields are forbidden")
        result[key] = value
    return result


def load_candidate(spec):
    wheel = Path(spec["candidate"]).resolve(strict=True)
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != spec["candidate_sha256"]:
        raise ValueError("Candidate bytes do not match the reviewed SHA")
    if any(name == "mcp_hcl" or name.startswith("mcp_hcl.") for name in sys.modules):
        raise ValueError("A candidate is already imported; use a fresh interpreter")
    sys.path.insert(0, str(wheel))
    from mcp_hcl.cli_session import PersistentConsole
    from mcp_hcl.runtime_binding import RuntimeBinding

    for name in ("mcp_hcl.cli_session", "mcp_hcl.runtime_binding"):
        if not str(sys.modules[name].__file__).startswith(str(wheel) + os.sep):
            raise ValueError("Actual import does not belong to the reviewed wheel")
    return RuntimeBinding(), PersistentConsole


def probe(spec_path, output_root, *, candidate_loader=load_candidate):
    directory = Path(output_root).resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    result = {
        "operation_id": directory.name,
        "status": "unverified",
        "stage": "input",
        "command": "display version",
        "command_outcome": "not_sent",
        "runtime_verified": False,
        "configuration_verified": False,
        "connectivity_verified": False,
        "full_live_gate_passed": False,
        "errors": [],
    }
    channel = None
    try:
        with Path(spec_path).open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("Probe specification exceeds its size limit")
        spec = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_fields)
        fields = {
            "candidate",
            "candidate_sha256",
            "project_file",
            "topology",
            "device_id",
            "owner_sid",
            "vm_uuid",
        }
        if not isinstance(spec, dict) or set(spec) != fields:
            raise ValueError("Exact probe specification fields are required")
        if (
            any(not isinstance(spec[k], str) for k in fields - {"device_id"})
            or type(spec["device_id"]) is not int
            or not 1 <= spec["device_id"] <= 1024
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", spec["topology"])
            or not re.fullmatch(r"S-\d+(?:-\d+)+", spec["owner_sid"])
            or not re.fullmatch(r"[0-9a-f]{64}", spec["candidate_sha256"])
        ):
            raise ValueError("Invalid probe identity or scalar types")
        expected_uuid = str(UUID(spec["vm_uuid"]))
        project = Path(spec["project_file"])
        candidate = Path(spec["candidate"])
        if not candidate.is_absolute() or candidate.suffix.lower() != ".whl":
            raise ValueError("An explicit absolute candidate wheel is required")
        if not project.is_absolute() or project.suffix.lower() != ".net":
            raise ValueError("An explicit absolute project .net file is required")
        result["specification_sha256"] = hashlib.sha256(raw).hexdigest()
        result["candidate_sha256"] = spec["candidate_sha256"]
        if os.environ.get("MCP_HCL_ALLOW_LIVE_WRITE") != "1":
            raise ValueError("Explicit console write permission is required")
        result["stage"] = "candidate"
        runtime, console = candidate_loader(spec)
        result["stage"] = "runtime_binding"
        target = runtime.resolve(
            SimpleNamespace(directory=project.parent, net_path=project),
            {"device_id": spec["device_id"]},
            spec["topology"],
        )
        if target["owner_sid"] != spec["owner_sid"] or target["vm_uuid"] != expected_uuid:
            raise ValueError("Observed current-user VM differs from the reviewed identity")
        result["target"] = target
        result["stage"] = "console_open"
        channel = console(
            target["pipe"], project.parent / ".console-lease", timeout=12, open_timeout=2
        )
        result["stage"] = "pipe_identity"
        result["identity"] = runtime.verify_pipe(channel, target)
        result["stage"] = "exchange"
        result["command_outcome"] = "unknown"
        reply = channel.exchange("display version")
        if reply.get("complete") is not True:
            raise ValueError("The console did not return a complete attributed response")
        result.update(status="output_received", command_outcome="output_received", reply=reply)
        result["verified_scope"] = "single_display_version_reply_only"
        result["stage"] = "complete"
    except Exception as exc:
        detail = getattr(exc, "detail", {})
        if isinstance(detail, dict) and detail.get("command_outcome") in {"not_sent", "unknown"}:
            result["command_outcome"] = detail["command_outcome"]
        error = {
            "code": getattr(exc, "code", "basic_probe_failed"),
            "type": type(exc).__name__,
            "stage": result["stage"],
        }
        if type(exc) is ValueError or type(exc).__module__ == "mcp_hcl.console":
            error["message"] = str(exc)
        result["errors"].append(error)
    finally:
        if channel is not None:
            try:
                channel.close()
            except Exception as exc:
                result["status"] = "unverified"
                result["errors"].append(
                    {"code": "console_close_failed", "type": type(exc).__name__, "stage": "close"}
                )
        try:
            (directory / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise ReceiptWriteError(result) from exc
    return directory / "result.json", result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        path, result = probe(args.spec, args.output_root)
    except ReceiptWriteError as exc:
        print(
            json.dumps(
                {
                    "status": "unverified",
                    "stage": "receipt_write",
                    "command_outcome": exc.result["command_outcome"],
                    "error": "Receipt persistence failed; do not replay the command",
                }
            )
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "stage": "receipt_setup",
                    "command_outcome": "not_sent",
                    "error": "Receipt directory unavailable",
                }
            )
        )
        return 2
    print(
        json.dumps(
            {
                "receipt": str(path),
                "status": result["status"],
                "stage": result["stage"],
                "command_outcome": result["command_outcome"],
            }
        )
    )
    return 0 if result["status"] == "output_received" else 2


if __name__ == "__main__":
    raise SystemExit(main())
