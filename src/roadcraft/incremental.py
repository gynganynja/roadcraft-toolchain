"""Reuse declared, isolated build steps only while their output bytes still match.

This is an execution cache, not an acceptance record or an artifact downloader.
Entries point to sealed successful job receipts; failed runs never seed it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from . import core


INDEX = ".roadcraft-step-cache.json"


def capture_trees(roots: list[str]) -> list[dict[str, Any]]:
    result = []
    for value in roots:
        root = core._require_local_path(value).resolve()
        if not root.is_dir():
            raise core.RoadcraftError(f"Declared output tree is missing: {root}")
        files = []
        for path in sorted(root.rglob("*")):
            core._require_local_path(path)
            if path.is_file():
                identity = core.file_identity(path)
                if not identity.get("unchangedDuringRead"):
                    raise core.RoadcraftError(f"Output changed during cache snapshot: {path}")
                files.append({"path": path.relative_to(root).as_posix(), "sha256": identity["sha256"]})
        result.append({"path": str(root), "files": files})
    return result


def fingerprint(step: dict[str, Any], completed: list[dict[str, Any]]) -> str:
    dependencies = []
    wanted = set(step["dependsOn"])
    for row in completed:
        if row["id"] in wanted:
            dependencies.append({"id": row["id"], "outputs": [
                {"path": item["path"], "sha256": item["sha256"]}
                for item in row["outputChecks"]], "outputTrees": row.get("outputTreeChecks", [])})
    if len(dependencies) != len(wanted):
        raise core.RoadcraftError("Cache dependency has not completed")
    # Values are hashed in memory; environment contents are never saved in a cache entry.
    content = {"version": 1, "step": step, "dependencies": dependencies,
               "executableSha256": core.sha256_file(step["command"][0]),
               "environment": {**os.environ, **step["env"]},
               "runner": {name: core.sha256_file(Path(__file__).with_name(name))
                          for name in ("jobs.py", "incremental.py", "core.py")}}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_index(root: Path) -> dict[str, Any]:
    path = root / INDEX
    if not path.exists():
        return {}
    try:
        data = core.load_json(path)
        return data.get("entries", {}) if data.get("schemaVersion") == 1 and isinstance(data.get("entries"), dict) else {}
    except (core.RoadcraftError, OSError):
        return {}  # Cache corruption means a rebuild, never a passed step.


def lookup(root: Path, entries: dict[str, Any], key: str, step: dict[str, Any]) -> dict[str, Any] | None:
    ref = entries.get(key)
    if not isinstance(ref, dict):
        return None
    run_id = ref.get("runId")
    if not isinstance(run_id, str) or not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in run_id) or run_id in (".", ".."):
        return None
    try:
        receipt_path = core.resolve_path(f"{run_id}/receipt.json", root / INDEX)
        if not receipt_path.is_relative_to(root):
            return None
        identity = core.file_identity(receipt_path, ref.get("receiptSha256"))
        if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
            return None
        receipt = core.load_json(receipt_path)
        if receipt.get("status") != "passed" or receipt.get("recoveryRequired"):
            return None
        row = next((r for r in receipt["steps"] if r["id"] == step["id"] and r.get("cacheKey") == key), None)
        if row is None or row.get("status") not in ("passed", "cached"):
            return None
        outputs = row.get("outputChecks", [])
        if [r["path"] for r in outputs] != [p["path"] for p in step["outputs"]]:
            return None
        for pin in outputs:
            current = core.file_identity(pin["path"], pin.get("sha256"))
            if not current.get("matchesExpected") or not current.get("unchangedDuringRead"):
                return None
        trees = capture_trees(step["outputTrees"])
        if trees != row.get("outputTreeChecks", []):
            return None
        return {"receiptPath": str(receipt_path), "receiptSha256": identity["sha256"],
                "runId": run_id, "outputChecks": outputs,
                "outputTreeChecks": trees,
                "executionSeconds": row.get("executionSeconds", 0)}
    except (core.RoadcraftError, OSError, KeyError, TypeError):
        return None


def add_receipt(entries: dict[str, Any], receipt: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    updated = dict(entries)
    digest = core.sha256_file(receipt_path)
    for row in receipt["steps"]:
        if row.get("cacheKey") and row["status"] in ("passed", "cached"):
            updated[row["cacheKey"]] = {"runId": receipt["runId"], "receiptSha256": digest}
    return {"schemaVersion": 1, "entries": updated}
