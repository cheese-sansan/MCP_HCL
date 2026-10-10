"""User-triggered lab preparation, evidence collection, audit and import."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import shutil
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

from packaging.requirements import Requirement
from pydantic import ValidationError

from mcp_hcl import __version__
from mcp_hcl.artifact_store import ArtifactRetries, linked, tree_hash
from mcp_hcl.console import ConsoleError
from mcp_hcl.environment import preflight
from mcp_hcl.evidence import audit_evidence, collect_evidence, digest, import_evidence, read_file

WIRED_REQUEST = {
    "schema_version": 1,
    "name": "ThreeRouterAcceptance",
    "template": "multi_lan",
    "routers": 3,
    "switches_per_router": 1,
    "pcs_per_lan": 2,
    "router_model": "MSR36-20",
    "switch_model": "S5820V2-54QS-GE",
    "host_model": "PC",
    "routing": "ospf",
    "ospf_process_id": 1,
    "dhcp": True,
    "lan_pool": "10.0.0.0/16",
    "transit_pool": "172.16.0.0/16",
}
WIRELESS_SPEC = {
    "kind": "experiment_requirements_not_an_executable_plan",
    "devices": {"AC": 1, "AP": 1, "S5820V2-54QS-GE": 1, "Phone": 2},
    "management_network": "10.50.0.0/24",
    "business_network": "10.50.10.0/24",
    "management_vlan": 1,
    "business_vlan": 10,
    "ac_gateways": {"management": "10.50.0.1", "business": "10.50.10.1"},
    "client_ipv4": "dhcp",
    "client_ipv6": "none",
    "security_required": "wpa2_psk",
    "open_wifi_is_diagnostic_only": True,
    "runtime_ready": False,
    "required_inputs": [
        "Actual AP hardware model and serial ID",
        "Verified CLI/scene/radio mappings",
        "WPA2-PSK Phone capability and native persistence evidence",
        "Locally supplied PSK",
        "Native terminal backup/restore capability",
    ],
    "acceptance": [
        "AP identity and online state",
        "Both Phone clients associated using WPA2-PSK",
        "Two unique leases in business subnet and correct gateway",
        "Bidirectional five-packet ping with zero loss",
    ],
    "full_live_gate_passed": False,
}
GUIDE = """# Independent HCL lab bundle

This package does not install HCL, start guests, modify Windows boot/security
settings or change shared VirtualBox. Use a separate, already working Windows
HCL environment. Vendor binaries, disks and complete manuals are not included.

1. Create a local venv with Python 3.11+ and install the tested dependencies:
   `python -m pip install -r requirements-tested.txt`
   `python -m pip install --no-deps wheels/mcp_hcl-0.5.0-py3-none-any.whl`
2. Run `mcp-hcl-lab preflight --installation ACTUAL_HCL_DIRECTORY`.
   This is observation only, not a pass for a real guest/console.
3. Manually prepare real model templates and start the isolated guests in HCL.
   Save complete native configs, display version/interface output and independent
   port mapping observations. For Phone save original before/after project files
   and native configuration pages; do not invent Comware interface commands.
4. Fill a capture spec from capture-spec.example.json, then run:
   `mcp-hcl-lab collect --spec PRIVATE_CAPTURE_SPEC --output NEW_PRIVATE_DIRECTORY`
   Manual file collection never sends commands. For native read-only collection,
   explicitly set native_readbacks=true, the observed topology and an exact-project
   verified GUI identity receipt; release PuTTY/MultiCC first. Only display
   current-configuration, display version and display interface are sent.
5. Copy that private directory to the analysis machine; run:
   `mcp-hcl-lab audit --directory COPIED_EVIDENCE_DIRECTORY`
   `mcp-hcl-lab import --directory COPIED_EVIDENCE_DIRECTORY --output-root PRIVATE_PROFILES --name NEW_NAME --idempotency-key UNIQUE_KEY`
   Set MCP_HCL_PROFILE_ROOT to PRIVATE_PROFILES. Integrity does not establish
   factory defaults, runtime acceptance or an independently verified port map.
6. Build the wired request through hcl_full_build(activate=false) with a real
   source project and explicit independently checked port map. Open its staged
   copy through hcl_open_project and preserve the GUI identity receipt. Start
   devices manually and release all other console clients. Only then explicitly
   enable MCP_HCL_ALLOW_LIVE_WRITE and run:
   `mcp-hcl-lab accept-wired --project-directory STAGED_PROJECT --topology OBSERVED_TOPOLOGY --gui-receipt GUI_JSON --installation HCL_ROOT --output-root STAGE_ROOT`
   The gate may exceed one minute. It preflights every native backup/restore,
   writes running config only, and recovers modified devices on configuration
   or network failure. Startup config is not implicitly saved. Failed recovery
   is reported per device with a manual recovery command, never as success.
7. Wireless-test.json describes a separate five-device experiment, not a working
   plan. Open Wi-Fi cannot close its security gate. `accept-wireless` currently
   refuses deployment until Phone secure association serialization and recovery
   are independently established. Never substitute a wired host, AP client-mode
   CLI or open network for the intended secure Phone association.

All operations use new private receipt directories. Keep raw configurations,
PSKs, screenshots and transcripts private. Preserve failed receipts. Imports
retain the original execution host/method and do not claim local execution.
"""


def tested_dependencies() -> list[str]:
    pending = [("mcp", frozenset()), ("pydantic", frozenset()), ("packaging", frozenset())]
    seen = {}
    processed = set()
    while pending:
        name, extras = pending.pop()
        canonical = name.lower().replace("_", "-")
        if (canonical, extras) in processed:
            continue
        processed.add((canonical, extras))
        seen[canonical] = importlib.metadata.version(name)
        for item in importlib.metadata.requires(name) or []:
            requirement = Requirement(item)
            if not requirement.marker or any(
                requirement.marker.evaluate({"extra": extra}) for extra in extras | {""}
            ):
                pending.append((requirement.name, frozenset(requirement.extras)))
    return [f"{name}=={version}" for name, version in sorted(seen.items())]


def audit_bundle(directory: Path) -> dict:
    manifest = json.loads(read_file(directory / "bundle-manifest.json").decode("utf-8"))
    if (
        set(manifest)
        != {"schema_version", "kind", "package_version", "operation_id", "files", "runtime_ready"}
        or manifest["schema_version"] != 1
        or manifest["kind"] != "independent_lab_preparation"
        or manifest["runtime_ready"] is not False
    ):
        raise ValueError("Invalid lab bundle manifest")
    expected = manifest["files"]
    actual = tree_hash(directory)
    if (
        not isinstance(expected, dict)
        or {k: v for k, v in actual.items() if k != "bundle-manifest.json"} != expected
    ):
        raise ValueError("Lab bundle files are missing or modified")
    return {
        "status": "verified",
        "verified_scope": "lab_preparation_bundle_hashes_only",
        "package_version": manifest["package_version"],
        "operation_id": manifest["operation_id"],
        "runtime_ready": False,
        "full_live_gate_passed": False,
    }


def prepare_bundle(wheel: Path, output_root: Path, name: str, key: str | None = None) -> dict:
    from mcp_hcl.project_build import safe_filename

    safe_filename(name)
    if "/" in name or "\\" in name:
        raise ValueError("Single artifact name required")
    if any(linked(p) for p in [output_root, *output_root.parents]):
        raise ValueError("Output root cannot contain links")
    data = read_file(wheel)
    with zipfile.ZipFile(wheel) as archive:
        metadata = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("Invalid wheel")
        from email.parser import Parser

        info = Parser().parsestr(archive.read(metadata[0]).decode())
        if info["Name"] != "mcp-hcl" or info["Version"] != __version__:
            raise ValueError("Wheel package/version mismatch")
        if any(
            Path(n).suffix.lower() in {".vdi", ".vmdk", ".chm", ".net", ".cfg"}
            for n in archive.namelist()
        ):
            raise ValueError("Vendor/private files in wheel")
    dependencies = tested_dependencies()
    destination = output_root / name

    def action():
        if destination.exists():
            raise ValueError("Preparation bundle exists; never overwrite")
        output_root.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".lab-", dir=output_root))
        try:
            (temp / "wheels").mkdir()
            (temp / "wheels" / wheel.name).write_bytes(data)
            (temp / "requirements-tested.txt").write_text(
                "\n".join(dependencies) + "\n", encoding="utf-8"
            )
            (temp / "README.md").write_text(GUIDE, encoding="utf-8")
            (temp / "wired-request.json").write_text(json.dumps(WIRED_REQUEST, indent=2) + "\n")
            (temp / "wireless-test.json").write_text(json.dumps(WIRELESS_SPEC, indent=2) + "\n")
            example = {
                "project_directory": "ABSOLUTE_REAL_PROJECT",
                "installation": "ABSOLUTE_HCL_ROOT",
                "hcl_version": "5.10.3",
                "devices": [
                    {
                        "name": "ACTUAL_RESOURCE_NAME",
                        "control_kind": "comware",
                        "configuration": "ABSOLUTE_NATIVE_CFG",
                        "version_readback": "ABSOLUTE_VERSION_OUTPUT",
                        "interface_readback": "ABSOLUTE_INTERFACE_OUTPUT",
                    },
                    {
                        "name": "ACTUAL_PHONE_NAME",
                        "control_kind": "native_gui",
                        "phone_before": "ABSOLUTE_BEFORE_NET",
                        "phone_after": "ABSOLUTE_AFTER_NET",
                        "phone_page": "ABSOLUTE_CONFIGURATION_PAGE_PNG",
                    },
                ],
            }
            (temp / "capture-spec.example.json").write_text(json.dumps(example, indent=2) + "\n")
            (temp / "runtime-tested.json").write_text(
                json.dumps(
                    {
                        "python": platform.python_version(),
                        "system": platform.system(),
                        "dependencies": dependencies,
                        "runtime_acceptance": "not_run",
                        "wireless_gate_complete": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            operation = uuid4().hex
            (temp / "bundle-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "independent_lab_preparation",
                        "package_version": __version__,
                        "operation_id": operation,
                        "files": tree_hash(temp),
                        "runtime_ready": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            audit_bundle(temp)
            temp.rename(destination)
            return {
                "status": "verified",
                "artifact_directory": str(destination),
                "operation_id": operation,
                "verified_scope": "independent_lab_preparation_only",
                "runtime_ready": False,
                "full_live_gate_passed": False,
            }
        finally:
            if temp.exists():
                shutil.rmtree(temp)

    return ArtifactRetries(output_root).run(
        "prepare_lab_bundle",
        {
            "name": name,
            "wheel_sha256": digest(data),
            "dependencies": dependencies,
            "idempotency_key": key,
        },
        action,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--wheel", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--name", required=True)
    prepare.add_argument("--idempotency-key")
    collect = commands.add_parser("collect")
    collect.add_argument("--spec", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--directory", type=Path, required=True)
    audit.add_argument("--preparation-bundle", action="store_true")
    load = commands.add_parser("import")
    load.add_argument("--directory", type=Path, required=True)
    load.add_argument("--output-root", type=Path, required=True)
    load.add_argument("--name", required=True)
    load.add_argument("--idempotency-key")
    observe = commands.add_parser("preflight")
    observe.add_argument("--installation", type=Path, required=True)
    wired = commands.add_parser("accept-wired")
    for name in ("project-directory", "topology", "gui-receipt", "installation", "output-root"):
        wired.add_argument("--" + name, required=True)
    commands.add_parser("accept-wireless")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare_bundle(args.wheel, args.output_root, args.name, args.idempotency_key)
        elif args.action == "collect":
            result = collect_evidence(
                json.loads(read_file(args.spec).decode("utf-8-sig")), args.output
            )
        elif args.action == "import":
            result = import_evidence(
                args.directory, args.output_root, args.name, args.idempotency_key
            )
        elif args.action == "audit":
            result = (
                audit_bundle(args.directory)
                if args.preparation_bundle
                else audit_evidence(args.directory)
            )
            # No raw configuration, page contents or credentials on the CLI/MCP summary.
            result = {k: v for k, v in result.items() if k != "profiles"}
        elif args.action == "preflight":
            result = preflight(args.installation)
        elif args.action == "accept-wireless":
            result = {
                "status": "rejected",
                "errors": [
                    {
                        "code": "wireless_acceptance_not_ready",
                        "message": "Phone WPA2-PSK association, native settings persistence and backup/restore capability remain unverified",
                    }
                ],
                "wireless_gate_complete": False,
                "full_live_gate_passed": False,
            }
        else:
            import os

            from mcp_hcl.catalog import HclCatalog
            from mcp_hcl.console import writes_enabled_from_environment
            from mcp_hcl.deployment import Deployment
            from mcp_hcl.live_acceptance import accept_lab
            from mcp_hcl.project import ProjectStore

            store = ProjectStore([Path(args.project_directory)], Path(args.output_root))
            engine = Deployment(
                store,
                catalog=HclCatalog(Path(args.installation)),
                writes_enabled=writes_enabled_from_environment(os.environ),
            )
            result = accept_lab(engine, args.project_directory, args.topology, args.gui_receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") not in {"verified", "observed"}:
            raise SystemExit(2)
    except ValidationError as exc:
        from mcp_hcl.contracts import validation_errors

        print(
            json.dumps(
                {
                    "status": "rejected",
                    "errors": validation_errors(exc),
                    "full_live_gate_passed": False,
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ConsoleError) as exc:
        error = (
            exc.as_error()
            if isinstance(exc, ConsoleError)
            else {"code": "lab_input_rejected", "message": str(exc)}
        )
        print(
            json.dumps(
                {"status": "rejected", "errors": [error], "full_live_gate_passed": False},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
