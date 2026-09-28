"""Exact-template cleanup, gated by a reviewed manifest hash.

The Git temporary pack and every path not listed as a verified template copy
are outside this operation. Dry-run is the default; applying it needs an exact
manifest SHA-256 that the reviewer has approved separately.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
from typing import Any

from . import cleanup, core


class CleanupBlocked(RuntimeError):
    """A reviewed cleanup candidate changed or is unsafe to remove."""


def _safe_within(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise CleanupBlocked(f"Missing or unreadable candidate component: {current}") from exc
        if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise CleanupBlocked(f"Candidate crosses a link or reparse point: {current}")
    return True


def _check(manifest_path: Path, approved_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(approved_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in approved_sha256):
        raise CleanupBlocked("A 64-character approved manifest SHA-256 is required")
    manifest_file = manifest_path.resolve(strict=True)
    actual_sha = core.sha256_file(manifest_file)
    if actual_sha != approved_sha256.lower():
        raise CleanupBlocked(f"Review manifest differs from approved hash: {actual_sha}")
    review = core.load_json(manifest_file)
    roots = [Path(value).absolute() for value in review.get("runRoots", [])]
    templates = Path(review.get("sdkTemplates", "")).absolute()
    rows = review.get("templateCopies")
    if (review.get("schemaVersion") != 1 or not roots or not templates.is_dir() or
            not isinstance(rows, list) or not rows or
            review.get("templateCopyCount") != len(rows)):
        raise CleanupBlocked("Review manifest has missing or inconsistent template fields")
    checked = []
    original_hashes: dict[Path, str] = {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") != "sdk-template-copy":
            raise CleanupBlocked("Only explicit SDK template copies are eligible")
        candidate = Path(row["path"]).absolute()
        if (candidate.name not in cleanup.TEMPLATE_NAMES or
                candidate.parent.name.casefold() != "templates" or
                candidate.parent.parent.name.casefold() != "editor_data" or
                not any(_safe_within(candidate, root) for root in roots)):
            raise CleanupBlocked(f"Candidate is outside reviewed old-run templates: {candidate}")
        if str(candidate).casefold() in seen:
            raise CleanupBlocked(f"Duplicate candidate path: {candidate}")
        seen.add(str(candidate).casefold())
        original = (templates / candidate.name).resolve(strict=True)
        if row.get("retainedOriginal") != str(original):
            raise CleanupBlocked(f"Retained original path differs: {candidate}")
        current = cleanup._file_record(candidate)
        for key in ("path", "sizeBytes", "allocatedBytes", "sha256", "fileId",
                    "hardLinks", "modifiedUtc"):
            if current.get(key) != row.get(key):
                raise CleanupBlocked(f"Candidate changed ({key}): {candidate}")
        if original not in original_hashes:
            original_hashes[original] = cleanup.sha256_file(original)
        if current["hardLinks"] != 1 or original_hashes[original] != current["sha256"]:
            raise CleanupBlocked(f"Candidate lacks a retained identical original: {candidate}")
        checked.append(current)
    if sum(row["allocatedBytes"] for row in checked) != review.get("templateAllocatedBytes"):
        raise CleanupBlocked("Reviewed allocation total differs")
    return review, checked


def commit_template_cleanup(manifest_path: str | Path, approved_sha256: str,
                            journal_root: str | Path, *, apply: bool = False) -> dict[str, Any]:
    """Review exact files, optionally unlink them with an append-only receipt."""
    manifest_file = Path(manifest_path)
    review, checked = _check(manifest_file, approved_sha256)
    result = {"operation": "remove-reviewed-template-copies", "dryRun": not apply,
              "manifest": str(manifest_file.resolve()),
              "manifestSha256": approved_sha256.lower(),
              "candidateCount": len(checked),
              "allocatedBytes": sum(item["allocatedBytes"] for item in checked),
              "gitTemporaryPackIncluded": False,
              "deletedCount": 0}
    if not apply:
        return result
    processes, error = core._editor_processes()
    roadcraft_processes = [row for row in processes if any(
        token in str(row.get("name", "")).casefold()
        for token in ("roadcraft", "modeditor", "integrationstudio", "furnace", "mod_pak_builder")
    )]
    if error or roadcraft_processes:
        raise CleanupBlocked(f"RoadCraft process state blocks cleanup: {error or roadcraft_processes}")
    journal = Path(journal_root).absolute()
    journal.mkdir(parents=True, exist_ok=True)
    run_dir = journal / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") +
                         uuid.uuid4().hex[:12])
    run_dir.mkdir(exist_ok=False)
    receipt_path = run_dir / "receipt.json"
    receipt = {**result, "dryRun": False, "startedUtc": datetime.now(timezone.utc).isoformat(),
               "state": "IN_PROGRESS", "deleted": [], "receiptPath": str(receipt_path)}
    def persist() -> None:
        temporary = receipt_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, receipt_path)
    persist()
    try:
        for expected in checked:
            candidate = Path(expected["path"])
            current = cleanup._file_record(candidate)
            if any(current[key] != expected[key]
                   for key in ("sizeBytes", "allocatedBytes", "sha256", "fileId",
                               "hardLinks", "modifiedUtc")):
                raise CleanupBlocked(f"Candidate changed during deletion: {candidate}")
            candidate.unlink()
            receipt["deleted"].append(expected)
            receipt["deletedCount"] = len(receipt["deleted"])
            persist()
        receipt["state"] = "COMPLETE"
    except Exception as exc:
        receipt["state"] = "PARTIAL_REVIEW_REQUIRED"
        receipt["error"] = str(exc)
        raise
    finally:
        receipt["finishedUtc"] = datetime.now(timezone.utc).isoformat()
        persist()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = commit_template_cleanup(args.manifest, args.approved_manifest_sha256,
                                         args.journal_root, apply=args.apply)
    except (CleanupBlocked, core.RoadcraftError, OSError, KeyError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
