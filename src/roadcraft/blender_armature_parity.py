"""Pinned, read-only comparison of a source Blend armature with a repaired USF.

The Blender worker opens the historical Blend and USF in one background
process. It does not save, export, or modify an asset on disk. This is a
static armature diagnostic, not a native-Blend export approval.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_left_push_probe import (
    BLENDER_SHA256, BLEND_SHA256, INVENTORY_SHA256, SDK_PINS, USF_SHA256,
    LeftPushProbeError, _unlinked_path, require_hash, require_sdk_pins,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_armature_parity_worker.py")
WORKER_SHA256 = "899dad8810372c64de15bda3239a07311b19ce4231c5f34264796336cbace976"
RESULT_PREFIX = "ROADCRAFT_ARMATURE_PARITY "
PATH_PREFIX = "|@root|D11T_Rig.005|"
MATRIX_TOLERANCE = 1e-5
MAX_DIFF_ROWS = 128
PINNED_COUNTS = (384, 400, 396, 4)  # source, repaired, affix-classified, other
BLENDER_50_SHA256 = "f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c"
BLENDER_VERSION_PINS = {BLENDER_SHA256: "5.2.", BLENDER_50_SHA256: "5.0."}


class ArmatureParityError(RuntimeError):
    """The pinned diagnostic or its result cannot be trusted."""


def _paths(value: object, label: str) -> list[str]:
    if (not isinstance(value, list) or
            any(not isinstance(path, str) or not path.startswith(PATH_PREFIX)
                or not path[len(PATH_PREFIX):] or "||" in path for path in value) or
            value != sorted(set(value))):
        raise ArmatureParityError(f"{label} must contain unique sorted armature paths")
    return value


def _matrix_values(values: object, label: str) -> tuple[float, ...]:
    if (not isinstance(values, (list, tuple)) or len(values) != 16 or
            any(type(value) not in (float, int) or not math.isfinite(value)
                for value in values)):
        raise ArmatureParityError(f"{label} is not a finite 4x4 matrix")
    return tuple(float(value) for value in values)


def compare_static_armature(source: dict[str, list[float]],
                            repaired: dict[str, list[float]]) -> dict:
    """Compare all source bones with all meshless repaired structural nodes.

    Relocations are candidates inferred from unique leaf names only; they do
    not make two different hierarchy paths equivalent.
    """
    source_paths = _paths(sorted(source), "source")
    repaired_paths = _paths(sorted(repaired), "repaired")
    source_matrices = {path: _matrix_values(source[path], f"source {path}")
                       for path in source_paths}
    repaired_matrices = {path: _matrix_values(repaired[path], f"repaired {path}")
                         for path in repaired_paths}
    source_set = set(source_paths)
    repaired_set = set(repaired_paths)
    common = sorted(source_set & repaired_set)
    source_only = sorted(source_set - repaired_set)
    repaired_only = sorted(repaired_set - source_set)
    matrix_errors = []
    for path in common:
        left = source_matrices[path]
        right = repaired_matrices[path]
        matrix_errors.append({"path": path,
                              "maxElementError": max(abs(a - b) for a, b in zip(left, right))})
    source_leaves = Counter(path.rsplit("|", 1)[-1] for path in source_only)
    repaired_leaves = Counter(path.rsplit("|", 1)[-1] for path in repaired_only)
    repaired_by_leaf = {path.rsplit("|", 1)[-1]: path for path in repaired_only}
    relocations = []
    for path in source_only:
        name = path.rsplit("|", 1)[-1]
        if source_leaves[name] != 1 or repaired_leaves[name] != 1:
            continue
        target = repaired_by_leaf[name]
        error = max(abs(a - b) for a, b in zip(source_matrices[path],
                                               repaired_matrices[target]))
        relocations.append({"name": name, "sourcePath": path,
                            "repairedPath": target,
                            "maxElementError": error})
    changed = [entry for entry in matrix_errors
               if entry["maxElementError"] > MATRIX_TOLERANCE]
    return {
        "sourceBonePaths": source_paths,
        "repairedStructuralPaths": repaired_paths,
        "sourceOnlyPaths": source_only,
        "repairedOnlyPaths": repaired_only,
        "relocationCandidates": relocations,
        "sharedPathMatrixErrors": matrix_errors,
        "sharedPathCount": len(common),
        "changedMatrixCount": len(changed),
        "maxSharedMatrixError": max((entry["maxElementError"] for entry in matrix_errors),
                                    default=0.0),
        "changedRelocationMatrixCount": sum(
            row["maxElementError"] > MATRIX_TOLERANCE for row in relocations),
        "maxRelocationMatrixError": max(
            (row["maxElementError"] for row in relocations), default=0.0),
        "status": ("STATIC_ARMATURE_MATCH" if not source_only and not repaired_only
                   and not changed else "STATIC_ARMATURE_DIFFERENT"),
    }


def _validate_result(result: dict, expected_blender_sha256: str) -> None:
    if not isinstance(result, dict) or result.get("schemaVersion") != 1:
        raise ArmatureParityError("Blender result schema differs")
    expected = {
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": expected_blender_sha256,
        "classification": "all meshless nodes beneath USF armature; SDK bone affixes reported separately",
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(result.get(key)) is not type(value) or result.get(key) != value
           for key, value in expected.items()):
        raise ArmatureParityError("Blender result identity or no-write fields differ")
    if (expected_blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[expected_blender_sha256]) or
            type(result.get("sceneFrame")) is not int or
            result["sceneFrame"] != 1):
        raise ArmatureParityError("Blender version or frame differs")
    source_paths = _paths(result.get("sourceBonePaths"), "sourceBonePaths")
    repaired_paths = _paths(result.get("repairedStructuralPaths"),
                            "repairedStructuralPaths")
    affix_bones = _paths(result.get("affixClassifiedUsfPaths"),
                         "affixClassifiedUsfPaths")
    unclassified = _paths(result.get("unclassifiedMeshlessUsfPaths"),
                          "unclassifiedMeshlessUsfPaths")
    if (set(affix_bones) & set(unclassified) or
            set(affix_bones) | set(unclassified) != set(repaired_paths)):
        raise ArmatureParityError("USF structural classification is incomplete or overlapping")
    counts = (len(source_paths), len(repaired_paths), len(affix_bones),
              len(unclassified))
    if counts != PINNED_COUNTS:
        raise ArmatureParityError(
            f"Pinned armature coverage differs: {counts} != {PINNED_COUNTS}")
    errors = result.get("sharedPathMatrixErrors")
    if not isinstance(errors, list):
        raise ArmatureParityError("Blender omitted matrix measurements")
    expected_shared = sorted(set(source_paths) & set(repaired_paths))
    if ([entry.get("path") for entry in errors if isinstance(entry, dict)] !=
            expected_shared or len(errors) != len(expected_shared)):
        raise ArmatureParityError("Blender matrix measurements do not cover every shared path")
    for entry in errors:
        value = entry.get("maxElementError")
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ArmatureParityError("Blender matrix measurement is invalid")
    source_only = sorted(set(source_paths) - set(repaired_paths))
    repaired_only = sorted(set(repaired_paths) - set(source_paths))
    source_leaves = Counter(path.rsplit("|", 1)[-1] for path in source_only)
    repaired_leaves = Counter(path.rsplit("|", 1)[-1] for path in repaired_only)
    repaired_by_leaf = {path.rsplit("|", 1)[-1]: path for path in repaired_only}
    expected_relocations = [
        {"name": path.rsplit("|", 1)[-1], "sourcePath": path,
         "repairedPath": repaired_by_leaf[path.rsplit("|", 1)[-1]]}
        for path in source_only
        if source_leaves[path.rsplit("|", 1)[-1]] == 1 and
           repaired_leaves[path.rsplit("|", 1)[-1]] == 1
    ]
    relocations = result.get("relocationCandidates")
    if (not isinstance(relocations, list) or
            [{key: row.get(key) for key in ("name", "sourcePath", "repairedPath")}
             for row in relocations if isinstance(row, dict)] != expected_relocations or
            len(relocations) != len(expected_relocations)):
        raise ArmatureParityError("Blender relocation candidates contradict paths")
    for row in relocations:
        value = row.get("maxElementError")
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ArmatureParityError("Blender relocation matrix measurement is invalid")
    changed = sum(entry["maxElementError"] > MATRIX_TOLERANCE for entry in errors)
    largest = max((entry["maxElementError"] for entry in errors), default=0.0)
    status = ("STATIC_ARMATURE_MATCH" if not source_only and not repaired_only
              and not changed else "STATIC_ARMATURE_DIFFERENT")
    count_fields = {"sharedPathCount": len(expected_shared),
                    "changedMatrixCount": changed,
                    "maxSharedMatrixError": largest,
                    "changedRelocationMatrixCount": sum(
                        row["maxElementError"] > MATRIX_TOLERANCE
                        for row in relocations),
                    "maxRelocationMatrixError": max(
                        (row["maxElementError"] for row in relocations),
                        default=0.0),
                    "status": status,
                    "sourceOnlyPaths": source_only,
                    "repairedOnlyPaths": repaired_only,
                    }
    if any(result.get(key) != value for key, value in count_fields.items()):
        raise ArmatureParityError("Blender result contradicts paths or measurements")
    source_matrices = result.get("sourceWorldMatrices")
    repaired_matrices = result.get("repairedWorldMatrices")
    if not isinstance(source_matrices, dict) or not isinstance(repaired_matrices, dict):
        raise ArmatureParityError("Blender result omitted full static matrices")
    recomputed = compare_static_armature(source_matrices, repaired_matrices)
    if any(result.get(key) != value for key, value in recomputed.items()):
        raise ArmatureParityError("Blender result contradicts full static matrices")


def parse_result(stdout: str, expected_blender_sha256: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1:
        raise ArmatureParityError("Blender did not emit one armature result")
    try:
        result = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ArmatureParityError("Blender result is malformed") from exc
    _validate_result(result, expected_blender_sha256)
    return result


def compact_result(result: dict) -> dict:
    """Emit the complete, sorted *difference* list in a bounded JSON result."""
    differences = ([{"kind": "source_only", "path": path}
                    for path in result["sourceOnlyPaths"]] +
                   [{"kind": "repaired_only", "path": path}
                    for path in result["repairedOnlyPaths"]] +
                   [{"kind": "matrix_changed", **entry}
                    for entry in result["sharedPathMatrixErrors"]
                    if entry["maxElementError"] > MATRIX_TOLERANCE])
    differences.sort(key=lambda row: (row["path"], row["kind"]))
    if len(differences) > MAX_DIFF_ROWS:
        raise ArmatureParityError(
            f"{len(differences)} differences exceed the {MAX_DIFF_ROWS}-row diagnostic bound")
    structural_fields = {
        key: result[key] for key in (
            "sourceWorldMatrices", "repairedWorldMatrices",
            "affixClassifiedUsfPaths", "unclassifiedMeshlessUsfPaths")
    }
    structural_digest = hashlib.sha256(json.dumps(
        structural_fields, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    public_keys = ("schemaVersion", "status", "asset", "blendSha256",
                   "repairedUsfSha256", "blenderSha256", "blenderVersion",
                   "sceneFrame", "classification", "sharedPathCount",
                   "changedMatrixCount", "maxSharedMatrixError",
                   "changedRelocationMatrixCount", "maxRelocationMatrixError",
                   "relocationCandidates", "unclassifiedMeshlessUsfPaths",
                   "blendSaved", "usfExported", "nativeBlendExportApproved",
                   "sourceUnchanged", "sdkUnchanged", "workerSha256",
                   "inventorySha256")
    compact = {key: result[key] for key in public_keys}
    compact.update({"sourceBoneCount": len(result["sourceBonePaths"]),
                    "repairedStructuralCount": len(result["repairedStructuralPaths"]),
                    "affixClassifiedUsfCount": len(result["affixClassifiedUsfPaths"]),
                    "pathDiffRowCount": len(differences),
                    "pathDifferences": differences,
                    "structuralDigestSha256": structural_digest})
    return compact


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ArmatureParityError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise ArmatureParityError("accepted authoring inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise ArmatureParityError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, pinned_root, _, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if pinned_root != source_root:
        raise ArmatureParityError("authoring source root changed during validation")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise ArmatureParityError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "armature worker")
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(usf), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise ArmatureParityError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, blender_sha)
    require_hash(registry_path, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256, "inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise ArmatureParityError("authoring source root changed during diagnostic")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk_script_root)
    require_hash(blender_executable, blender_sha, "Blender executable after diagnostic")
    require_hash(WORKER, WORKER_SHA256, "armature worker after diagnostic")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256,
                   "blenderSha256": blender_sha})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry, blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (ArmatureParityError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc), "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    try:
        compact = compact_result(result)
    except ArmatureParityError as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc), "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    print(json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
