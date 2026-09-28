"""Bounded, machine-readable differences between two SDK-parsed USF trees.

This is diagnostic evidence. Equal rows do not prove native Blender parity:
compilation and native views still require separate review.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


def compare_node_rows(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return complete path and field differences in stable lexical order."""
    old_paths, new_paths = set(baseline), set(candidate)
    missing = sorted(old_paths - new_paths)
    extra = sorted(new_paths - old_paths)
    changed: list[dict[str, Any]] = []
    for path in sorted(old_paths & new_paths):
        old, new = baseline[path], candidate[path]
        fields = sorted(set(old) | set(new))
        changes = {field: {"baseline": old.get(field), "candidate": new.get(field)}
                   for field in fields if old.get(field) != new.get(field)}
        if changes:
            changed.append({"path": path, "fields": changes})

    def is_rig_path(path: str) -> bool:
        return any(part.startswith("Bone") or part.startswith("_")
                   for part in path.split("|") if part)

    changed_field_counts = Counter(field for row in changed
                                   for field in row["fields"])
    return {
        "baselineNodeCount": len(baseline),
        "candidateNodeCount": len(candidate),
        "missingNodePaths": missing,
        "extraNodePaths": extra,
        "missingRigNodePaths": [path for path in missing if is_rig_path(path)],
        "extraRigNodePaths": [path for path in extra if is_rig_path(path)],
        "matchedNodeDifferences": changed,
        "changedFieldCounts": dict(sorted(changed_field_counts.items())),
        "matchesIndexedFields": not (missing or extra or changed),
    }
