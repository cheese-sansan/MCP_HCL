"""Atomic offline exports and hash-checked plan reloading."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from mcp_hcl.artifact_store import ArtifactRetries, linked, tree_hash
from mcp_hcl.generation import generate_configs, generate_operations


class Artifacts:
    def __init__(self, root: Path, catalog):
        self.root = root.resolve()
        self.catalog = catalog
        self.retries = ArtifactRetries(self.root)

    def export(self, plan: dict, artifact_name: str, idempotency_key: str | None = None) -> dict:
        return self.retries.run(
            "hcl_export_artifacts",
            {"plan": plan, "artifact_name": artifact_name, "idempotency_key": idempotency_key},
            lambda: self._export(plan, artifact_name),
        )

    def _export(self, plan, name):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,19}", name):
            raise ValueError("artifact_name must be 1-20 ASCII letters/digits/underscores")
        result = generate_configs(plan, self.catalog)
        if result["status"] != "verified":
            return result
        final = self.root / name
        if final.exists():
            raise ValueError("Artifact directory already exists")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".hcl-export-", dir=self.root))
        operation_id = uuid4().hex
        try:

            def write(filename, value):
                (temporary / filename).write_text(
                    json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )

            write("plan.json", result["plan"])
            operations = generate_operations(result["plan"], self.catalog)
            write(
                "operations.json",
                {
                    key: operations[key]
                    for key in ("schema_version", "operations", "executable", "requires")
                },
            )
            configdir = temporary / "configs"
            configdir.mkdir()
            for device, config in result["configs"].items():
                (configdir / (device + ".cfg")).write_text(config, encoding="utf-8")
            (temporary / "README.txt").write_text(
                "Offline artifacts only. Open/execute requires separate HCL acceptance.\nRuntime, firmware, CLI and connectivity are unverified.\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "operation_id": operation_id,
                "hashes": tree_hash(temporary),
                "evidence": result["evidence"],
                "runtime_verified": False,
            }
            write("manifest.json", manifest)
            os.rename(temporary, final)
            return {
                "status": "verified",
                "operation_id": operation_id,
                "verified_scope": "offline_export_and_hashes_only",
                "artifact_directory": str(final),
                "files": {name: str(final / name) for name in manifest["hashes"]},
                "manifest": str(final / "manifest.json"),
                "evidence": result["evidence"],
                "warnings": result["warnings"],
                "runtime_verified": False,
                "full_live_gate_passed": False,
            }
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def load(self, artifact_directory: str) -> dict:
        raw = Path(artifact_directory).absolute()
        directory = raw.resolve()
        if not directory.is_relative_to(self.root):
            raise ValueError("Artifact path is outside the output root")
        for parent in [raw, *raw.parents]:
            if linked(parent):
                raise ValueError("Artifact paths cannot contain links")
            if parent == self.root:
                break
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("hashes"), dict)
            or not re.fullmatch(r"[0-9a-f]{32}", str(manifest.get("operation_id", "")))
        ):
            raise ValueError("Invalid artifact manifest")
        hashes = tree_hash(directory)
        hashes.pop("manifest.json", None)
        if hashes != manifest["hashes"]:
            raise ValueError("Artifact hash mismatch or unexpected file")
        plan = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
        from mcp_hcl.topology import validate_plan

        # Reload the same configuration intent that export accepted. A hash-
        # checked artifact is not a claim of a complete connected topology.
        result = validate_plan(plan, self.catalog, validation_level="configuration")
        result.update(
            artifact_directory=str(directory), source_operation_id=manifest["operation_id"]
        )
        return result
