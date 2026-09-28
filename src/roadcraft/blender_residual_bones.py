"""Source-pinned, no-save D11 seven-bone structural diagnostic."""

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
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_residual_bones_worker.py")
WORKER_SHA256 = "9c402c74245a18081e559a13f7cf4d3a425e13a7fc046cdd0f27d301b1a8c594"
DEPENDENCIES = (
    ("blender_push_branches.py", "f0a684c03983cd9d89b739bc7f5aa48b503cd2831b9de6f5a5f1d06d34a523f7"),
    ("blender_push_branches_worker.py", "974df2d86d1045a57acf392ad8367a2db19a0367a1a717fe3b04baf9e7ca63d0"),
    ("blender_blade_roll.py", "24d4b9513617d0638af52dac95238199a2bfd880c6926d68f7a230adf1bc4d89"),
    ("blender_blade_roll_worker.py", "ced27a3f52a0a80764eecbd07edce6e9c6b32d6f5f6b77a5f35e57be1b2399be"),
    ("blender_ladder.py", "fc6a993e647593c39afc8fdc37dbec4ef4c2dc7023bf1592b309f8d673c51a10"),
    ("blender_ladder_worker.py", "526768b392678b705c0d82687cbb76bd0bad1f1a41a9ad29ee0163cdb50ddf54"),
    ("blender_armature_parity.py", "32d81c496295ed73706cd862bf4e1b47e013f246631c50f486d7cfe6c3c3b72c"),
    ("blender_left_push_probe.py", "003e0f6d38cf37976fc4c91eeba2df5dff6c9882d3cbbe29d53d8a516234da72"),
)
RESULT_PREFIX = "ROADCRAFT_RESIDUAL_BONES "
CHASSIS_PREFIX = "|@root|D11T_Rig.005|BoneChassis_cdt"
TOLERANCE = 1e-5


class ResidualBonesError(RuntimeError):
    """The pinned structural diagnostic or its result cannot be trusted."""


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _target_paths() -> list[str]:
    return [
        CHASSIS_PREFIX + "|IK_lift_left_base|d11t_light_inner_L",
        CHASSIS_PREFIX + "|IK_lift_right_base|d11t_light_inner_R",
        *(CHASSIS_PREFIX + "|ctrl_dash_v5_" + name for name in
          ("coolant", "fuel", "hyd_temp", "tach", "trans_temp")),
    ]


def validate_result(value: object, blender_sha256: str) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ResidualBonesError("Blender result schema differs")
    expected = {
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256, "sceneFrame": 1,
        "priorRepairStatuses": [
            "IN_MEMORY_PUSH_BRANCH_MATCH", "IN_MEMORY_BLADE_ROLL_MATCH",
            "IN_MEMORY_LADDER_MATCH"],
        "beforeSourceBoneCount": 392,
        "afterSourceBoneCount": 399,
        "sourceEmptyNodeCount": 1,
        "repairedStructuralCount": 400,
        "afterSharedPathCount": 400,
        "afterSourceOnlyPaths": [],
        "afterRepairedOnlyPaths": [],
        "afterChangedMatrixCount": 0,
        "sfxSourceKind": "bone-parented EMPTY",
        "sourceMeshCount": 210,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(value.get(key)) is not type(item) or value.get(key) != item
           for key, item in expected.items()):
        raise ResidualBonesError("Blender identity, coverage or no-write fields differ")
    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(value.get("blenderVersion"), str) or
            not value["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[blender_sha256])):
        raise ResidualBonesError("Blender version differs")
    targets = value.get("targetMatrixErrors")
    if (not isinstance(targets, list) or len(targets) != 7 or
            [row.get("path") for row in targets if isinstance(row, dict)] !=
            _target_paths()):
        raise ResidualBonesError("Seven target path roster differs")
    errors = [row.get("maxElementError") for row in targets]
    shared_max = value.get("afterMaxSharedMatrixError")
    sfx_error = value.get("sfxSourceMatrixError")
    mesh_error = value.get("meshWorldError")
    if (any(not _finite_nonnegative(item) for item in
            [shared_max, sfx_error, mesh_error, *errors]) or
            shared_max < max([sfx_error, *errors])):
        raise ResidualBonesError("Matrix measurements are invalid")
    matched = all(value <= TOLERANCE for value in
                  [shared_max, sfx_error, mesh_error, *errors])
    status = ("IN_MEMORY_STRUCTURAL_MATCH" if matched else
              "IN_MEMORY_STRUCTURAL_DIFFERENT")
    if value.get("status") != status:
        raise ResidualBonesError("Blender status contradicts matrix measurements")
    return value


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ResidualBonesError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise ResidualBonesError("accepted inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise ResidualBonesError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, pinned_root, _, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if pinned_root != source_root:
        raise ResidualBonesError("authoring root changed during validation")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise ResidualBonesError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "residual-bones worker")
    dependencies = [(Path(__file__).with_name(name), sha, name)
                    for name, sha in DEPENDENCIES]
    for path, sha, label in dependencies:
        require_hash(path, sha, label)
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(usf), "--sdk-script-root", str(sdk),
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
        raise ResidualBonesError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise ResidualBonesError("Blender did not emit one structural result")
    result = validate_result(json.loads(lines[0]), blender_sha)
    require_hash(registry, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise ResidualBonesError("authoring root changed during diagnostic")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after diagnostic")
    require_hash(worker, WORKER_SHA256,
                 "residual-bones worker after diagnostic")
    for path, sha, label in dependencies:
        require_hash(path, sha, label + " after diagnostic")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (ResidualBonesError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(error),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
