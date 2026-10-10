"""Serialized, durable retries for offline artifacts; never replays live writes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


def linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def tree_hash(directory: Path) -> dict[str, str]:
    if not directory.is_dir() or linked(directory):
        raise ValueError("Artifact directory is missing or linked")
    result = {}
    for path in sorted(directory.rglob("*")):
        if linked(path):
            raise ValueError("Artifact trees must not contain links")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[path.relative_to(directory).as_posix()] = digest.hexdigest()
    return result


class ArtifactRetries:
    def __init__(self, root: Path, source_roots: list[Path] | None = None):
        self.root = root.resolve()
        self.source_roots = [p.resolve() for p in (source_roots or [root])]

    def run(
        self,
        operation: str,
        arguments: dict[str, Any],
        action: Callable[[], dict],
        *,
        source: str | None = None,
    ) -> dict:
        key = arguments.get("idempotency_key")
        if key is None:
            return action()
        if not key.strip() or len(key) > 128:
            raise ValueError("idempotency_key must be 1-128 non-blank characters")
        data = {"operation": operation, "arguments": arguments}
        if source:
            source_path = Path(source).resolve()
            if not any(source_path.is_relative_to(p) for p in self.source_roots):
                raise ValueError("Source is outside configured project roots")
            if self.root.is_relative_to(source_path):
                raise ValueError("Stage output root must not be inside the source project")
            data["source_directory"] = str(source_path)
            data["source"] = tree_hash(source_path)
        fingerprint = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        dbpath = self.root / ".operations.sqlite3"
        if linked(dbpath):
            raise ValueError("Retry journal cannot be a link")
        with closing(sqlite3.connect(dbpath, timeout=30)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations (key TEXT PRIMARY KEY, fingerprint TEXT, result TEXT, directory TEXT, hashes TEXT)"
            )
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT fingerprint,result,directory,hashes FROM operations WHERE key=?", (key,)
            ).fetchone()
            if row:
                if row[0] != fingerprint:
                    return self._reject(
                        "idempotency_conflict", "The key belongs to different input"
                    )
                try:
                    directory = Path(row[2]).resolve()
                    if not directory.is_relative_to(self.root) or tree_hash(
                        directory
                    ) != json.loads(row[3]):
                        raise ValueError("Artifact contents have changed")
                except (OSError, ValueError):
                    return self._reject(
                        "artifact_changed", "Original artifacts are missing or modified"
                    )
                return {**json.loads(row[1]), "replayed": True}
            result = action()
            if result.get("status") in {"staged", "verified"}:
                directory = Path(
                    result.get("artifact_directory", result.get("project_directory", ""))
                ).resolve()
                if not directory.is_relative_to(self.root):
                    raise ValueError("Artifacts escaped the output root")
                result.setdefault("operation_id", uuid4().hex)
                db.execute(
                    "INSERT INTO operations VALUES(?,?,?,?,?)",
                    (
                        key,
                        fingerprint,
                        json.dumps(result, ensure_ascii=False),
                        str(directory),
                        json.dumps(tree_hash(directory)),
                    ),
                )
            return result

    @staticmethod
    def _reject(code: str, message: str) -> dict:
        return {"status": "rejected", "errors": [{"code": code, "message": message}]}
