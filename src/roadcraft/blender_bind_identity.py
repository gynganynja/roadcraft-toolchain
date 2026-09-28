"""Pinned, no-save D11 source/native/repaired skin-bone readback.

The SDK's skin b_read leaves UIDs and inverse binds unresolved. This probe
reconstructs only that resolution in memory; it never serializes a USF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_blade_relocation import BladeRelocationError, _rows_and_native
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import (
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256, WORKLIST,
    WORKLIST_SHA256, MeshInventoryError, _worklist_rows,
)
from .blender_mesh_inventory import WORKER as MAPPER_WORKER
from .blender_mesh_inventory import WORKER_SHA256 as MAPPER_WORKER_SHA256
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_bind_identity_worker.py")
WORKER_SHA256 = "b8444c389bfbae5efd0c74ca68623e96db82c144511c65a9584fbe1169f31181"
RESULT_PREFIX = "ROADCRAFT_BIND_IDENTITY "
EXPECTED_ROWS = 126
MAX_JSON_BYTES = 1024 * 1024
TOLERANCE = 1e-5


class BindIdentityError(RuntimeError):
    """Pinned data, mapping, or complete skin readback differs."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _finite_matrix(values: object, label: str) -> list[float]:
    if (not isinstance(values, list) or len(values) != 16 or
            any(type(v) not in (float, int) or not math.isfinite(v)
                for v in values)):
        raise BindIdentityError(f"{label} is not a finite 4x4 matrix")
    return [float(v) for v in values]


def compare_binds(source: list[dict], usf: list[dict]) -> dict:
    """Compare ordered source IDs and inverse matrices, retaining gap names."""
    for side, rows in (("source", source), ("USF", usf)):
        if not isinstance(rows, list) or len(rows) > 500:
            raise BindIdentityError(f"{side} skin-bone coverage is invalid")
        ids = []
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"sourceId", "inverse"} or
                    not isinstance(row["sourceId"], str) or
                    not row["sourceId"].startswith("|") or
                    len(row["sourceId"]) > 512):
                raise BindIdentityError(f"{side} bone identity is invalid")
            _finite_matrix(row["inverse"], f"{side} inverse")
            ids.append(row["sourceId"])
        if len(ids) != len(set(ids)):
            raise BindIdentityError(f"{side} skin-bone identities are duplicated")
    src = {row["sourceId"]: row["inverse"] for row in source}
    dst = {row["sourceId"]: row["inverse"] for row in usf}
    shared = sorted(src.keys() & dst.keys())
    max_error = max((abs(a - b) for identity in shared
                     for a, b in zip(src[identity], dst[identity])), default=0.0)
    return {
        "sourceCount": len(source), "usfCount": len(usf),
        "orderedIdentityMatch": [x["sourceId"] for x in source] ==
                                [x["sourceId"] for x in usf],
        "sharedIdentityCount": len(shared),
        "missingFromUsf": sorted(src.keys() - dst.keys()),
        "extraInUsf": sorted(dst.keys() - src.keys()),
        "maxSharedInverseElementError": max_error,
        "sharedInverseWithinTolerance": bool(shared) and max_error <= TOLERANCE,
    }


def interpret_readback(result: dict, gap_rows: list[dict], *,
                       blender_sha: str, native_sha: str, summary_sha: str,
                       host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha,
        "blenderSha256": blender_sha, "hostSha256": host_sha,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise BindIdentityError("readback identity, coverage, or no-write flags differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise BindIdentityError("Blender version differs")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != len(gap_rows) or len(rows) != EXPECTED_ROWS:
        raise BindIdentityError("readback omitted mapped mesh rows")
    seen = set()
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or
                set(row) != {"path", "sourceObject", "sourceNative", "sourceRepaired",
                             "nativeSelfMaxElementError", "repairedSelfMaxElementError"} or
                row["path"] != gap["path"] or
                not isinstance(row["sourceObject"], str) or
                row["sourceObject"] in seen):
            raise BindIdentityError("mesh path or source mapping differs")
        seen.add(row["sourceObject"])
        for name in ("sourceNative", "sourceRepaired"):
            comparison = row[name]
            if not isinstance(comparison, dict) or set(comparison) != {
                    "sourceCount", "usfCount", "orderedIdentityMatch",
                    "sharedIdentityCount", "missingFromUsf", "extraInUsf",
                    "maxSharedInverseElementError", "sharedInverseWithinTolerance"}:
                raise BindIdentityError(f"incomplete {name} comparison")
            for count in ("sourceCount", "usfCount", "sharedIdentityCount"):
                if type(comparison[count]) is not int or not 0 <= comparison[count] <= 500:
                    raise BindIdentityError(f"invalid {name} count")
            if (type(comparison["orderedIdentityMatch"]) is not bool or
                    type(comparison["sharedInverseWithinTolerance"]) is not bool):
                raise BindIdentityError(f"invalid {name} verdict")
            for field in ("missingFromUsf", "extraInUsf"):
                ids = comparison[field]
                if (not isinstance(ids, list) or len(ids) != len(set(ids)) or
                        ids != sorted(ids) or
                        any(not isinstance(x, str) or not x.startswith("|") or
                            len(x) > 512 for x in ids)):
                    raise BindIdentityError(f"invalid {name} identity gaps")
            if (comparison["sourceCount"] != comparison["sharedIdentityCount"] +
                    len(comparison["missingFromUsf"]) or
                    comparison["usfCount"] != comparison["sharedIdentityCount"] +
                    len(comparison["extraInUsf"]) or
                    comparison["orderedIdentityMatch"] and
                    (comparison["missingFromUsf"] or comparison["extraInUsf"])):
                raise BindIdentityError(f"contradictory {name} identity counts")
            error = comparison["maxSharedInverseElementError"]
            if (type(error) not in (float, int) or not math.isfinite(error) or error < 0 or
                    comparison["sharedInverseWithinTolerance"] !=
                    (comparison["sharedIdentityCount"] > 0 and error <= TOLERANCE)):
                raise BindIdentityError(f"contradictory {name} inverse verdict")
        if (row["sourceNative"]["sourceCount"] != row["sourceRepaired"]["sourceCount"] or
                row["sourceNative"]["usfCount"] != gap["nativeExportSkinBoneUidCount"] or
                row["sourceRepaired"]["usfCount"] != gap["repairedSkinBoneUidCount"]):
            raise BindIdentityError("skin coverage contradicts pinned worklist")
        for key in ("nativeSelfMaxElementError", "repairedSelfMaxElementError"):
            value = row[key]
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise BindIdentityError("invalid USF inverse self-check")
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_USF_BIND_IDENTITY_READBACK",
        "blenderVersion": result["blenderVersion"],
        "mappedRows": len(rows),
        "sourceNativeOrderedIdentityMatches": sum(
            row["sourceNative"]["orderedIdentityMatch"] for row in rows),
        "sourceRepairedOrderedIdentityMatches": sum(
            row["sourceRepaired"]["orderedIdentityMatch"] for row in rows),
        "sourceNativeInverseWithinTolerance": sum(
            row["sourceNative"]["sharedInverseWithinTolerance"] for row in rows),
        "sourceRepairedInverseWithinTolerance": sum(
            row["sourceRepaired"]["sharedInverseWithinTolerance"] for row in rows),
        "maxNativeInverseSelfError": max(row["nativeSelfMaxElementError"] for row in rows),
        "maxRepairedInverseSelfError": max(row["repairedSelfMaxElementError"] for row in rows),
        "rowsDigestSha256": hashlib.sha256(canonical(rows)).hexdigest(),
        "rows": rows,
    })
    if len(canonical(compact)) > MAX_JSON_BYTES:
        raise BindIdentityError("bounded bind result exceeded")
    return compact


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise BindIdentityError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    ref = config["accepted"]["authoringInventory"]
    if ref["sha256"] != INVENTORY_SHA256:
        raise BindIdentityError("accepted inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / ref["path"], "inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise BindIdentityError("inventory outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "worklist")
    parsed = json.loads(worklist.read_text(encoding="utf-8"))
    gaps = _worklist_rows(parsed, asset["assetDigest"])
    _, native, native_sha, summary, summary_sha = _rows_and_native(
        parsed, asset["assetDigest"], blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise BindIdentityError("Blender executable differs from reviewed pins")
    sdk = require_sdk_pins(sdk_script_root)
    mapper = require_hash(MAPPER_WORKER, MAPPER_WORKER_SHA256, "path mapper")
    worker = require_hash(WORKER, WORKER_SHA256, "bind worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--mapper-sha256",
               MAPPER_WORKER_SHA256, "--host-sha256", host_sha,
               "--blender-sha256", blender_sha, "--native-usf-sha256",
               native_sha, "--summary-sha256", summary_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-16:])
        raise BindIdentityError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1 or len(lines[0]) > MAX_JSON_BYTES:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-8:])
        raise BindIdentityError(
            f"Blender emitted {len(lines)} bind readbacks (max length "
            f"{max(map(len, lines), default=0)}): {tail[:1200]}")
    result = interpret_readback(json.loads(lines[0]), gaps,
                                blender_sha=blender_sha, native_sha=native_sha,
                                summary_sha=summary_sha, host_sha=host_sha)
    require_hash(registry, registry_sha, "registry after")
    require_hash(inventory_path, INVENTORY_SHA256, "inventory after")
    if _unlinked_path(Path(inventory["sourceRoot"]), "source root after") != source_root:
        raise BindIdentityError("source root changed")
    for path, digest, label in (
            (blend, BLEND_SHA256, "Blend"), (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "native USF"), (worklist, WORKLIST_SHA256, "worklist"),
            (summary, summary_sha, "summary"), (blender, blender_sha, "Blender"),
            (mapper, MAPPER_WORKER_SHA256, "mapper"),
            (worker, WORKER_SHA256, "worker"), (Path(__file__), host_sha, "host")):
        require_hash(path, digest, label + " after")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256,
                   "workerSha256": WORKER_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (BindIdentityError, MeshInventoryError, BladeRelocationError,
            LeftPushProbeError, BlenderAuthoringError, OSError, ValueError,
            KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc), "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
