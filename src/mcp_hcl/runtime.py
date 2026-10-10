"""Bounded, read-only inventory of the HCL user runtime and VBox registry.

An engineering project copy or a clean inventory never proves the vendor's
cleanup boundary. This module does not start HCL, register media or change roots.
"""

from __future__ import annotations

import hashlib
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def _linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _present(path: Path) -> bool:
    try:
        path.stat()
        return True
    except FileNotFoundError:
        return False


def inspect_runtime(profile: Path, *, max_entries: int = 4096, timeout: float = 5.0) -> dict:
    root = profile / "HCL VMs"
    registry = profile / ".VirtualBox" / "VirtualBox.xml"
    result = {
        "status": "observed",
        "verified_scope": "runtime_asset_observations_only",
        "profile_directory": str(profile),
        "runtime_root": str(root),
        "registry_file": str(registry),
        "runtime_isolation_verified": False,
        "activation_allowed": False,
        "files": [],
        "registered_machines": [],
        "errors": [],
        "blockers": [
            {
                "code": "runtime_isolation_unverified",
                "message": "A project copy does not isolate HCL VM files or vendor cleanup",
            }
        ],
    }
    started = time.monotonic()
    try:
        if not profile.is_absolute() or not profile.is_dir():
            raise ValueError("Observed Windows profile must be an existing absolute directory")
        if any(
            _linked(path) for path in (profile, *profile.parents, root, registry.parent, registry)
        ):
            raise ValueError("Linked profile/runtime/registry paths cannot be inventoried safely")
        # Windows existence probes can return False below an unreadable
        # profile. Prove that its namespace can be enumerated first.
        with os.scandir(profile) as entries:
            next(entries, None)
        if _present(registry.parent):
            with os.scandir(registry.parent) as entries:
                next(entries, None)
        if _present(registry):
            if registry.stat().st_size > 1024 * 1024:
                raise ValueError("VirtualBox registry exceeds the observation limit")
            data = registry.read_bytes()
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                raise ValueError("External XML declarations are not accepted")
            document = ET.fromstring(data)
            for entry in document.iter():
                if entry.tag.rsplit("}", 1)[-1] == "MachineEntry":
                    if not entry.get("uuid") or not entry.get("src"):
                        raise ValueError("Incomplete VirtualBox machine registration")
                    result["registered_machines"].append(
                        {"uuid": entry.get("uuid"), "configuration": entry.get("src")}
                    )
            result["registry_sha256"] = hashlib.sha256(data).hexdigest()
        visited = 0
        if _present(root):
            if not root.is_dir():
                raise ValueError("HCL runtime root is not a directory")

            def walk_error(error):
                raise error

            for parent, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
                for name in [*directories, *names]:
                    visited += 1
                    if visited > max_entries or time.monotonic() - started > timeout:
                        raise ValueError(
                            "Runtime inventory exceeded its bounded observation budget"
                        )
                    item = Path(parent) / name
                    if _linked(item):
                        raise ValueError("Linked runtime entries cannot be inventoried safely")
                for name in names:
                    item = Path(parent) / name
                    info = item.stat()
                    record = {
                        "path": item.relative_to(root).as_posix(),
                        "size": info.st_size,
                        "mtime_ns": info.st_mtime_ns,
                    }
                    # Large guest disks are not opened or hashed here. Small
                    # VM descriptors identify disk references without OpenMedium.
                    if item.suffix.lower() in {".vbox", ".vbox-prev"}:
                        if info.st_size > 1024 * 1024:
                            raise ValueError("VM descriptor exceeds observation limit")
                        record["sha256"] = hashlib.sha256(item.read_bytes()).hexdigest()
                    result["files"].append(record)
        result["files"].sort(key=lambda record: record["path"])
        result["registered_machines"].sort(key=lambda record: record["uuid"])
        result["file_count"] = len(result["files"])
        if result["files"] or result["registered_machines"]:
            result["blockers"].append(
                {
                    "code": "existing_runtime_assets",
                    "message": "Existing VM files or registrations need protection before starting or switching HCL",
                }
            )
        result["disk_bytes_verified"] = False
        result["vendor_cleanup_boundary_verified"] = False
    except (OSError, ValueError, ET.ParseError) as exc:
        result["status"] = "unknown"
        result["errors"].append({"code": "runtime_observation_unknown", "message": str(exc)})
    return result
