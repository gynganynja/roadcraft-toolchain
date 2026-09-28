"""Source-pinned, no-save D11 v2/v3 in-memory structural reconstruction."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_left_push_probe import (
    BLEND_SHA256, INVENTORY_SHA256, USF_SHA256,
    LeftPushProbeError, _unlinked_path, require_hash, require_sdk_pins,
)
from .blender_residual_bones import (
    DEPENDENCIES, WORKER_SHA256 as RESIDUAL_SHA,
)
from .blender_variant_structural_targets import ASSET_USF_SHA256
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_variant_reconstruction_worker.py")
WORKER_SHA256 = "86e003a80db00ca4fb36e154db314cd122db1a19258480be4b96c2d7a133146f"
RESULT_PREFIX = "ROADCRAFT_VARIANT_RECONSTRUCTION "
TOLERANCE = 1e-5


class VariantReconstructionError(RuntimeError):
    """The variant reconstruction or its evidence cannot be trusted."""


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_result(value: object, *, asset: str, blend: Path,
                    blender_sha256: str) -> dict:
    if asset not in ("cat_d11t_v2", "cat_d11t_v3"):
        raise VariantReconstructionError("variant name differs")
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise VariantReconstructionError("Blender result schema differs")
    expected = {
        "asset": asset,
        "variantBlendPath": str(blend),
        "variantBlendSha256": BLEND_SHA256,
        "baseRepairedUsfSha256": USF_SHA256,
        "variantRepairedUsfSha256": ASSET_USF_SHA256[asset],
        "blenderSha256": blender_sha256,
        "sourcePoseBoneCount": 399,
        "repairedStructuralCount": 400,
        "sharedPathCount": 400,
        "sourceOnlyPaths": [],
        "repairedOnlyPaths": [],
        "changedMatrixCount": 0,
        "baseReconstructionStatus": "IN_MEMORY_STRUCTURAL_MATCH",
        "sfxSourceKind": "bone-parented EMPTY",
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(value.get(key)) is not type(item) or value.get(key) != item
           for key, item in expected.items()):
        raise VariantReconstructionError("Blender identity, coverage or no-write fields differ")
    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(value.get("blenderVersion"), str) or
            not value["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[blender_sha256])):
        raise VariantReconstructionError("Blender version differs")
    error = value.get("maxSharedMatrixError")
    mesh_error = value.get("baseMeshWorldError")
    if not _finite_nonnegative(error) or not _finite_nonnegative(mesh_error):
        raise VariantReconstructionError("matrix measurement is invalid")
    matched = error <= TOLERANCE and mesh_error <= TOLERANCE
    status = ("IN_MEMORY_VARIANT_STRUCTURAL_MATCH" if matched else
              "IN_MEMORY_VARIANT_STRUCTURAL_DIFFERENT")
    if value.get("status") != status:
        raise VariantReconstructionError("Blender status contradicts matrix measurements")
    return value


def run_probe(*, asset: str, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if asset not in ("cat_d11t_v2", "cat_d11t_v3"):
        raise VariantReconstructionError("variant name differs")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise VariantReconstructionError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise VariantReconstructionError("accepted inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise VariantReconstructionError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, base_root, _, base_blend, base_usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    _, variant_root, _, blend, variant_usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, asset)
    if base_root != source_root or variant_root != source_root or blend == base_blend:
        raise VariantReconstructionError("authoring root or variant path differs")
    require_hash(base_blend, BLEND_SHA256, "base source Blend")
    require_hash(base_usf, USF_SHA256, "base repaired USF")
    require_hash(blend, BLEND_SHA256, "variant source Blend")
    require_hash(variant_usf, ASSET_USF_SHA256[asset],
                 "variant repaired USF")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise VariantReconstructionError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "variant worker")
    module_root = Path(__file__).resolve().parent
    require_hash(module_root / "blender_residual_bones_worker.py",
                 RESIDUAL_SHA, "residual reconstruction worker")
    for name, sha in DEPENDENCIES:
        require_hash(module_root / name, sha, name)
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--asset", asset,
               "--blend", str(blend), "--base-blend", str(base_blend),
               "--base-usf", str(base_usf),
               "--variant-usf", str(variant_usf),
               "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=timeout_seconds, env=environment, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise VariantReconstructionError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise VariantReconstructionError("Blender did not emit one variant result")
    result = validate_result(json.loads(lines[0]), asset=asset,
                             blend=blend, blender_sha256=blender_sha)
    require_hash(registry, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise VariantReconstructionError("authoring root changed during diagnostic")
    require_hash(base_blend, BLEND_SHA256, "base source Blend after diagnostic")
    require_hash(base_usf, USF_SHA256, "base repaired USF after diagnostic")
    require_hash(blend, BLEND_SHA256, "variant source Blend after diagnostic")
    require_hash(variant_usf, ASSET_USF_SHA256[asset],
                 "variant repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after diagnostic")
    require_hash(worker, WORKER_SHA256, "variant worker after diagnostic")
    require_hash(module_root / "blender_residual_bones_worker.py",
                 RESIDUAL_SHA, "residual reconstruction worker after diagnostic")
    for name, sha in DEPENDENCIES:
        require_hash(module_root / name, sha, name + " after diagnostic")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=("cat_d11t_v2", "cat_d11t_v3"),
                        required=True)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(asset=args.asset, registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (VariantReconstructionError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(error),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "IN_MEMORY_VARIANT_STRUCTURAL_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
