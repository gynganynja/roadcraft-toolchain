"""Pinned, no-save three-way payload readback of 60 relocated D11 blade meshes.

This is diagnostic evidence only. Matching semantic arrays at two different
hierarchy paths does not establish collision behavior or allow native export.
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
from .blender_blade_relocation import (
    BLEND_SHA256, BLENDER_VERSION_PINS, INVENTORY_SHA256, LEAVES,
    NATIVE_PARENT, REPAIRED_PARENT, USF_SHA256, WORKLIST, WORKLIST_SHA256,
    BladeRelocationError, _rows_and_native, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_left_push_probe import LeftPushProbeError
from .blender_mesh_payload import FIELD_NAMES
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_blade_payload_worker.py")
WORKER_SHA256 = "c6a4b4b0c0639a0b412c917e420d320ff5e0015edd915972ec393875b36d3be6"
BLADE_HOST = Path(__file__).with_name("blender_blade_relocation.py")
BLADE_HOST_SHA256 = "87b272b4f2b52f29488a4188a7df5c2b5e83bdd03fe70527dc036082cc39a8a0"
MESH_HOST = Path(__file__).with_name("blender_mesh_payload.py")
MESH_HOST_SHA256 = "2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e"
RESULT_PREFIX = "ROADCRAFT_BLADE_PAYLOAD "
MAX_JSON_BYTES = 1024 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BladePayloadError(RuntimeError):
    """A pin, exact-path mapping, or complete bounded readback differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _summary(value: object, field: str, label: str) -> dict:
    required = {"elements", "sha256"}
    if field in ("uvCoordinates", "packedColors"):
        required.add("sets")
    if field == "uvCoordinates":
        required.add("names")
    if field == "skinIndicesWeights":
        required.add("bonesPerVertex")
    if not isinstance(value, dict) or set(value) != required:
        raise BladePayloadError(f"{label} {field} summary is incomplete")
    if (type(value["elements"]) is not int or value["elements"] < 0 or
            not isinstance(value["sha256"], str) or
            HEX_SHA256.fullmatch(value["sha256"]) is None):
        raise BladePayloadError(f"{label} {field} digest is invalid")
    for key in {"sets", "bonesPerVertex"} & required:
        if type(value[key]) is not int or value[key] < 0:
            raise BladePayloadError(f"{label} {field} {key} is invalid")
    if "names" in required and (
            not isinstance(value["names"], list) or
            len(value["names"]) != value["sets"] or
            any(not isinstance(name, str) or len(name) > 256
                for name in value["names"])):
        raise BladePayloadError(f"{label} UV names are invalid")
    return value


def interpret_readback(result: dict, expected_rows: list[dict],
                       blender_sha: str, native_sha: str, summary_sha: str,
                       host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha,
        "blenderSha256": blender_sha, "hostSha256": host_sha,
        "bladeHostSha256": BLADE_HOST_SHA256,
        "meshHostSha256": MESH_HOST_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False, "sdkPackerGuarded": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise BladePayloadError("readback identity or no-write gate differs")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise BladePayloadError("Blender version differs")
    for key in ("cacheBeforeSourceMeshes", "cacheAfterSourceMeshes"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise BladePayloadError("SDK cache observation is invalid")
    rows = result.get("rows")
    if (not isinstance(rows, list) or len(rows) != len(expected_rows) or
            len(rows) != len(LEAVES)):
        raise BladePayloadError("blade payload row coverage differs")
    comparisons = {pair: {field: 0 for field in FIELD_NAMES}
                   for pair in ("sourceNative", "nativeRepaired", "sourceRepaired")}
    checked = []
    for row, evidence in zip(rows, expected_rows):
        leaf = evidence["leafName"]
        if (not isinstance(row, dict) or set(row) != {
                "leafName", "nativeExportPath", "repairedPath",
                "equivalenceVerified", "sourceObject", "sourcePredictedPath",
                "sourceParentBone", "fields"} or
                row["leafName"] != leaf or
                row["nativeExportPath"] != evidence["nativeExportPath"] or
                row["repairedPath"] != evidence["repairedPath"] or
                row["nativeExportPath"] != NATIVE_PARENT + "|" + leaf or
                row["repairedPath"] != REPAIRED_PARENT + "|" + leaf or
                row["equivalenceVerified"] is not False or
                row["sourceObject"] != leaf or
                row["sourcePredictedPath"] != row["nativeExportPath"] or
                row["sourceParentBone"] != "BoneBlade_cdt" or
                not isinstance(row["fields"], dict) or
                set(row["fields"]) != set(FIELD_NAMES)):
            raise BladePayloadError(f"blade path, source mapping or gate differs: {leaf}")
        matches = {}
        for field in FIELD_NAMES:
            value = row["fields"][field]
            if not isinstance(value, dict) or set(value) != {
                    "source", "native", "repaired"}:
                raise BladePayloadError(f"blade {leaf} {field} sides differ")
            sides = {side: _summary(value[side], field, f"{leaf} {side}")
                     for side in ("source", "native", "repaired")}
            matches[field] = {
                "sourceNative": sides["source"] == sides["native"],
                "nativeRepaired": sides["native"] == sides["repaired"],
                "sourceRepaired": sides["source"] == sides["repaired"],
            }
            for pair, matched in matches[field].items():
                comparisons[pair][field] += matched
        checked.append({**row, "matches": matches})
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_BLADE_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"],
        "cacheBeforeSourceMeshes": result["cacheBeforeSourceMeshes"],
        "cacheAfterSourceMeshes": result["cacheAfterSourceMeshes"],
        "relocationRows": len(checked), "fieldMatchRows": comparisons,
        "rowsDigestSha256": hashlib.sha256(_canonical(checked)).hexdigest(),
        "rows": checked,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise BladePayloadError("bounded blade payload result exceeded")
    return compact


def parse_result(stdout: str, rows: list[dict], blender_sha: str,
                 native_sha: str, summary_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise BladePayloadError("Blender did not emit one bounded payload readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise BladePayloadError("Blender payload readback is malformed") from exc
    return interpret_readback(raw, rows, blender_sha, native_sha, summary_sha,
                              host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 600) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise BladePayloadError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise BladePayloadError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise BladePayloadError("authoring inventory is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    rows, native, native_sha, summary_path, summary_sha = _rows_and_native(
        json.loads(worklist.read_text(encoding="utf-8")), asset["assetDigest"],
        blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise BladePayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    blade_host = require_hash(BLADE_HOST, BLADE_HOST_SHA256, "blade host")
    mesh_host = require_hash(MESH_HOST, MESH_HOST_SHA256, "mesh host")
    worker = require_hash(WORKER, WORKER_SHA256, "blade payload worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--host-sha256", host_sha,
               "--blade-host-sha256", BLADE_HOST_SHA256,
               "--mesh-host-sha256", MESH_HOST_SHA256,
               "--blender-sha256", blender_sha,
               "--native-usf-sha256", native_sha,
               "--summary-sha256", summary_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise BladePayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, rows, blender_sha, native_sha,
                          summary_sha, host_sha)
    for path, digest, label in (
            (registry, registry_sha, "registry"),
            (inventory_path, INVENTORY_SHA256, "authoring inventory"),
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary_path, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (blade_host, BLADE_HOST_SHA256, "blade host"),
            (mesh_host, MESH_HOST_SHA256, "mesh host"),
            (worker, WORKER_SHA256, "worker"),
            (Path(__file__), host_sha, "host")):
        require_hash(path, digest, label + " after readback")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "source root after readback") != source_root:
        raise BladePayloadError("source root changed during readback")
    _, verified_root, verified_asset, verified_blend, verified_repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if (verified_root != source_root or
            verified_asset["assetDigest"] != asset["assetDigest"] or
            verified_blend != blend or verified_repaired != repaired):
        raise BladePayloadError("accepted source inventory changed during readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (BladePayloadError, BladeRelocationError, LeftPushProbeError,
            BlenderAuthoringError, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR", "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
