"""Pinned, no-save in-memory normal projection for 60 D11 blade meshes.

The accepted repaired USF remains the build input. This diagnostic tests one
normal-payload repair mechanism; it does not save a Blend or export a USF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_blade_payload import (
    BLADE_HOST, BLADE_HOST_SHA256, FIELD_NAMES, MESH_HOST,
    MESH_HOST_SHA256,
)
from .blender_blade_relocation import (
    BLEND_SHA256, BLENDER_VERSION_PINS, INVENTORY_SHA256, LEAVES,
    NATIVE_PARENT, REPAIRED_PARENT, USF_SHA256, WORKLIST, WORKLIST_SHA256,
    BladeRelocationError, _rows_and_native, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_left_push_probe import LeftPushProbeError
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_blade_normal_projection_worker.py")
WORKER_SHA256 = "5cbccc066898089906fe766a8ce2f6e040cd925257ae236674bdaeda3382b3b4"
SOURCE_WORKER = Path(__file__).with_name("blender_blade_payload_worker.py")
SOURCE_WORKER_SHA256 = "c6a4b4b0c0639a0b412c917e420d320ff5e0015edd915972ec393875b36d3be6"
RESULT_PREFIX = "ROADCRAFT_BLADE_NORMAL_PROJECTION "
EXPECTED_TRIANGLES = 2162
EXPECTED_CORNERS = 6486
MAX_JSON_BYTES = 256 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class NormalProjectionError(RuntimeError):
    """Pinned source, exact mapping, or no-write projection differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NormalProjectionError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(value: object, label: str) -> str:
    _require(isinstance(value, str) and HEX_SHA256.fullmatch(value) is not None,
             f"{label} is not SHA-256")
    return value


def interpret_readback(raw: dict, expected_rows: list[dict], *,
                       blender_sha: str, native_sha: str,
                       host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "status": "IN_MEMORY_NORMAL_PROJECTION",
        "blendSha256": BLEND_SHA256,
        "nativeUsfSha256": native_sha,
        "repairedUsfSha256": USF_SHA256,
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "workerSha256": WORKER_SHA256,
        "hostSha256": host_sha,
        "sourceWorkerSha256": SOURCE_WORKER_SHA256,
        "bladeHostSha256": BLADE_HOST_SHA256,
        "meshHostSha256": MESH_HOST_SHA256,
        "sceneFrame": 1,
        "sourceSceneMeshCount": 210,
        "normalInputSpace": "saber",
        "leaves": len(LEAVES),
        "triangles": EXPECTED_TRIANGLES,
        "corners": EXPECTED_CORNERS,
        "sourceUnchanged": True,
        "sdkUnchanged": True,
        "nativeUsfUnchanged": True,
        "repairedUsfUnchanged": True,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
        "equivalenceVerified": False,
    }
    _require(isinstance(raw, dict) and all(
        type(raw.get(key)) is type(value) and raw.get(key) == value
        for key, value in expected.items()),
        "projection identity or no-write gate differs")
    _require(blender_sha in BLENDER_VERSION_PINS and
             isinstance(raw.get("blenderVersion"), str) and
             raw["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha]),
             "Blender version differs")
    rows = raw.get("rows")
    _require(isinstance(rows, list) and len(rows) == len(expected_rows) ==
             len(LEAVES), "blade projection row coverage differs")
    other_fields = set(FIELD_NAMES) - {"normals"}
    triangle_total = corner_total = 0
    for row, evidence in zip(rows, expected_rows):
        leaf = evidence["leafName"]
        _require(isinstance(row, dict) and set(row) == {
            "leafName", "nativePath", "repairedPath",
            "triangleCount", "cornerCount", "sourceHadCustomNormals",
            "projectedNormalsExactRepaired", "baselineFieldsExactNative",
            "projectedOtherFieldsUnchanged", "baselineNormalSha256",
            "repairedNormalSha256", "projectedNormalSha256",
            "baselineOtherFieldsSha256", "projectedOtherFieldsSha256",
        } and row["leafName"] == leaf and
            row["nativePath"] == evidence["nativeExportPath"] ==
            NATIVE_PARENT + "|" + leaf and
            row["repairedPath"] == evidence["repairedPath"] ==
            REPAIRED_PARENT + "|" + leaf,
            f"blade projection path differs: {leaf}")
        triangles, corners = row["triangleCount"], row["cornerCount"]
        _require(type(triangles) is int and type(corners) is int and
                 0 < triangles <= 5000 and corners == triangles * 3 and
                 row["sourceHadCustomNormals"] is False and
                 row["projectedNormalsExactRepaired"] is True,
                 f"blade projection coverage or normals differ: {leaf}")
        _require(isinstance(row["baselineFieldsExactNative"], dict) and
                 set(row["baselineFieldsExactNative"]) == set(FIELD_NAMES) and
                 all(value is True for value in
                     row["baselineFieldsExactNative"].values()),
                 f"source/native field evidence differs: {leaf}")
        _require(isinstance(row["projectedOtherFieldsUnchanged"], dict) and
                 set(row["projectedOtherFieldsUnchanged"]) == other_fields and
                 all(value is True for value in
                     row["projectedOtherFieldsUnchanged"].values()),
                 f"non-normal field evidence differs: {leaf}")
        for key in ("baselineNormalSha256", "repairedNormalSha256",
                    "projectedNormalSha256", "baselineOtherFieldsSha256",
                    "projectedOtherFieldsSha256"):
            _hash(row[key], f"{leaf} {key}")
        _require(row["projectedNormalSha256"] ==
                 row["repairedNormalSha256"] and
                 row["projectedOtherFieldsSha256"] ==
                 row["baselineOtherFieldsSha256"],
                 f"projected payload digest differs: {leaf}")
        triangle_total += triangles
        corner_total += corners
    _require(triangle_total == EXPECTED_TRIANGLES and
             corner_total == EXPECTED_CORNERS,
             "blade projection total coverage differs")
    result = {**raw, "rowsDigestSha256": hashlib.sha256(
        _canonical(rows)).hexdigest()}
    _require(len(_canonical(result)) <= MAX_JSON_BYTES,
             "bounded blade projection result exceeded")
    return result


def parse_result(stdout: str, expected_rows: list[dict], *,
                 blender_sha: str, native_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    _require(len(matches) == 1 and len(matches[0]) <= MAX_JSON_BYTES,
             "one bounded projection result required")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise NormalProjectionError("projection JSON is malformed") from exc
    return interpret_readback(raw, expected_rows, blender_sha=blender_sha,
                              native_sha=native_sha, host_sha=host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 600) -> dict:
    _require(type(timeout_seconds) is int and timeout_seconds > 0,
             "timeout must be positive")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    _require(inventory_ref["sha256"] == INVENTORY_SHA256,
             "accepted inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    _require(inventory_path.is_relative_to(registry.parent),
             "authoring inventory outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "accepted repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    expected_rows, native, native_sha, summary, summary_sha = _rows_and_native(
        json.loads(worklist.read_text(encoding="utf-8")),
        asset["assetDigest"], blend, repaired)
    _require(len(expected_rows) == len(LEAVES),
             "blade worklist coverage differs")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    _require(blender_sha in BLENDER_VERSION_PINS,
             "Blender executable differs from reviewed pins")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "projection worker")
    source_worker = require_hash(
        SOURCE_WORKER, SOURCE_WORKER_SHA256, "source mapping worker")
    blade_host = require_hash(BLADE_HOST, BLADE_HOST_SHA256, "blade mapping host")
    mesh_host = require_hash(MESH_HOST, MESH_HOST_SHA256, "mesh digest host")
    host_sha = file_sha256(Path(__file__))
    command = [
        str(blender), "--background", "--factory-startup",
        "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
        "--python", str(worker), "--",
        "--blend", str(blend), "--native-usf", str(native),
        "--repaired-usf", str(repaired), "--worklist", str(worklist),
        "--sdk-script-root", str(sdk), "--blender-sha256", blender_sha,
        "--worker-sha256", WORKER_SHA256, "--host-sha256", host_sha,
        "--native-usf-sha256", native_sha,
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=timeout_seconds, env=environment, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise NormalProjectionError(
            f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, expected_rows,
                          blender_sha=blender_sha, native_sha=native_sha,
                          host_sha=host_sha)
    for path, digest, label in (
            (registry, registry_sha, "registry"),
            (inventory_path, INVENTORY_SHA256, "authoring inventory"),
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "accepted repaired USF"),
            (native, native_sha, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (worker, WORKER_SHA256, "projection worker"),
            (source_worker, SOURCE_WORKER_SHA256, "source mapping worker"),
            (blade_host, BLADE_HOST_SHA256, "blade mapping host"),
            (mesh_host, MESH_HOST_SHA256, "mesh digest host"),
            (Path(__file__), host_sha, "projection host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    _require(_unlinked_path(Path(inventory["sourceRoot"]),
                            "source root after readback") == source_root,
             "source root changed during readback")
    _, checked_root, checked_asset, checked_blend, checked_repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    _require(checked_root == source_root and
             checked_asset["assetDigest"] == asset["assetDigest"] and
             checked_blend == blend and checked_repaired == repaired,
             "accepted source inventory changed during readback")
    result.update({
        "inventorySha256": INVENTORY_SHA256,
        "paritySummarySha256": summary_sha,
        "registrySha256": registry_sha,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_probe(
            registry_path=args.registry, blender_executable=args.blender,
            sdk_script_root=args.sdk_script_root,
            timeout_seconds=args.timeout_seconds)
    except (NormalProjectionError, BladeRelocationError, LeftPushProbeError,
            BlenderAuthoringError, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
