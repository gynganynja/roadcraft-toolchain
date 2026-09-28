"""Compact authoring-parity evidence with an exact, deterministic full archive."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping


_TOTAL_FIELDS = (
    "nodes", "meshNodes", "vertices", "faces", "normals", "materialSlots",
    "uvSets", "colorSets", "skinEntries", "skinBones", "animatedNodes",
    "animationSplines", "animationSplineKeys",
)
_MATERIAL_NAME = re.compile(r'material\s*=\s*\{\s*name\s*=\s*"([^"\r\n]+)"')


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True,
                       ensure_ascii=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _material_examples(diff: Mapping[str, Any]) -> list[dict[str, Any]]:
    def label(serialized: str) -> str:
        match = _MATERIAL_NAME.search(serialized)
        return match.group(1) if match else "sha256:" + hashlib.sha256(
            serialized.encode("utf-8")).hexdigest()[:16]

    examples = []
    matched = diff.get("matchedNodeDifferences", [])
    priority = sorted(matched, key=lambda row: (
        not any(name in row["path"] for name in
                ("Body_vis", "BoneBlade", "_cockpit_camera")),
        row["path"],
    ))
    for row in priority:
        changed = row["fields"].get("mesh")
        if not changed:
            continue
        baseline = changed.get("baseline") or {}
        candidate = changed.get("candidate") or {}
        old_names = Counter(baseline.get("materialNames", []))
        new_names = Counter(candidate.get("materialNames", []))
        if old_names == new_names and baseline.get("skinEntries") == candidate.get("skinEntries"):
            continue
        examples.append({
            "path": row["path"],
            "baselineMaterialSlots": sum(old_names.values()),
            "candidateMaterialSlots": sum(new_names.values()),
            "missingMaterialLabels": [label(value) for value in
                                      sorted((old_names - new_names).elements())[:12]],
            "extraMaterialLabels": [label(value) for value in
                                    sorted((new_names - old_names).elements())[:12]],
            "baselineSkinEntries": baseline.get("skinEntries"),
            "candidateSkinEntries": candidate.get("skinEntries"),
            "baselineFaces": baseline.get("faces"),
            "candidateFaces": candidate.get("faces"),
        })
        if len(examples) == 12:
            break
    return examples


def compact_summary(
    full: Mapping[str, Any], *, raw_sha256: str, raw_bytes: int,
    archive_sha256: str, archive_bytes: int,
    archive_path: Path, local_raw_path: Path,
) -> dict[str, Any]:
    """Summarize exact native export evidence without elevating its verdict."""
    diagnostic = full.get("diagnostic", {})
    baseline = diagnostic.get("baselineSemantic", {})
    candidate = diagnostic.get("candidateSemantic", {})
    diff = diagnostic.get("nodeDiff", {})
    return {
        "schemaVersion": 1,
        "asset": full["asset"],
        "status": full["status"],
        "nativeBlendExportApproved": False,
        "exportGate": full.get("exportGate"),
        "inventorySha256": full["inventorySha256"],
        "sourceAssetDigest": full["sourceAssetDigest"],
        "blendPath": full["blendPath"],
        "blendSha256": full["blendSha256"],
        "baselineUsfPath": full["baselineUsfPath"],
        "baselineUsfSha256": full["baselineUsfSha256"],
        "candidateUsfPath": full["candidateUsfPath"],
        "candidateUsfSha256": full.get("candidateUsfSha256Observed"),
        "candidateUsfBytes": full.get("candidateUsfBytesObserved"),
        "blenderPath": full["blenderPath"],
        "blenderSha256": full["blenderSha256"],
        "blenderVersion": full["blenderVersion"],
        "blenderThreads": full.get("blenderThreads"),
        "sdkFileHashes": full["sdkFileHashes"],
        "helperSha256": full["helperSha256"],
        "diffSha256": full["diffSha256"],
        "summarySha256": full["summarySha256"],
        "sourceUnchanged": full.get("sourceUnchanged"),
        "sdkUnchanged": full.get("sdkUnchanged"),
        "blenderExitCode": full.get("blenderExitCode"),
        "baselineTotals": {key: baseline.get(key) for key in _TOTAL_FIELDS},
        "candidateTotals": {key: candidate.get(key) for key in _TOTAL_FIELDS},
        "baselineStructuralDigest": baseline.get("structuralDigest"),
        "candidateStructuralDigest": candidate.get("structuralDigest"),
        "baselineRootName": diagnostic.get("baselineRootName"),
        "candidateRootName": diagnostic.get("candidateRootName"),
        "rootNameMatches": diagnostic.get("rootNameMatches"),
        "missingNodePaths": diff.get("missingNodePaths", []),
        "extraNodePaths": diff.get("extraNodePaths", []),
        "missingRigNodePaths": diff.get("missingRigNodePaths", []),
        "extraRigNodePaths": diff.get("extraRigNodePaths", []),
        "changedMatchedNodeCount": len(diff.get("matchedNodeDifferences", [])),
        "changedFieldCounts": diff.get("changedFieldCounts", {}),
        "materialAndSkinExamples": _material_examples(diff),
        "tangentCalculationWarnings": full.get("blenderLogTail", "").count(
            "calc_tangents failed"),
        "fullRawPath": str(local_raw_path),
        "fullRawSha256": raw_sha256,
        "fullRawBytes": raw_bytes,
        "archivePath": str(archive_path),
        "archiveSha256": archive_sha256,
        "archiveBytes": archive_bytes,
    }


def package_evidence(
    full: Mapping[str, Any], *, summary_path: Path,
    archive_path: Path, local_raw_path: Path,
) -> dict[str, Any]:
    """Write full ignored JSON, deterministic gzip and compact summary once."""
    if any(path.exists() for path in (summary_path, archive_path, local_raw_path)):
        raise FileExistsError("authoring evidence output already exists")
    raw = _json_bytes(full)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0,
                       compresslevel=9) as stream:
        stream.write(raw)
    archive = buffer.getvalue()
    _write_new(local_raw_path, raw)
    _write_new(archive_path, archive)
    summary = compact_summary(
        full, raw_sha256=_sha(raw), raw_bytes=len(raw),
        archive_sha256=_sha(archive), archive_bytes=len(archive),
        archive_path=archive_path, local_raw_path=local_raw_path)
    _write_new(summary_path, _json_bytes(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--local-raw", type=Path, required=True)
    args = parser.parse_args()
    full = json.loads(args.full_input.read_text(encoding="utf-8"))
    summary = package_evidence(
        full, summary_path=args.summary,
        archive_path=args.archive, local_raw_path=args.local_raw)
    print(json.dumps({"status": summary["status"],
                      "fullRawSha256": summary["fullRawSha256"],
                      "archiveSha256": summary["archiveSha256"],
                      "summary": str(args.summary)}, sort_keys=True))


if __name__ == "__main__":
    main()
