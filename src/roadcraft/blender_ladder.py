"""Source-pinned, no-save D11 access-ladder reconstruction diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from . import blender_armature_parity, blender_left_push_probe
from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_left_push_probe import (
    BLEND_SHA256, INVENTORY_SHA256, USF_SHA256,
    LeftPushProbeError, _unlinked_path, require_hash, require_sdk_pins,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_ladder_worker.py")
WORKER_SHA256 = "526768b392678b705c0d82687cbb76bd0bad1f1a41a9ad29ee0163cdb50ddf54"
PUSH_WORKER = Path(__file__).with_name("blender_push_branches_worker.py")
PUSH_WORKER_SHA256 = "974df2d86d1045a57acf392ad8367a2db19a0367a1a717fe3b04baf9e7ca63d0"
LEFT_PROBE_SHA256 = "003e0f6d38cf37976fc4c91eeba2df5dff6c9882d3cbbe29d53d8a516234da72"
ARMATURE_PARITY_SHA256 = "32d81c496295ed73706cd862bf4e1b47e013f246631c50f486d7cfe6c3c3b72c"
RESULT_PREFIX = "ROADCRAFT_LADDER "
CHASSIS_PREFIX = "|@root|D11T_Rig.005|BoneChassis_cdt"
LIFT_PREFIX = CHASSIS_PREFIX + "|BoneBladeLift_cdt"
NAMES = ("BoneAccess_LadderMount", "BoneAccess_Swivel",
         "BoneAccess_LadderHinge", "BoneAccess_Ladder")
TOLERANCE = 1e-5


class LadderError(RuntimeError):
    """The pinned ladder diagnostic or its result cannot be trusted."""


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _target_paths() -> list[str]:
    paths = []
    path = CHASSIS_PREFIX
    for name in NAMES:
        path += "|" + name
        paths.append(path)
    return paths


def _residual_paths(push_and_roll_present: bool = False) -> tuple[list[str], list[str]]:
    source = []
    repaired = [
        CHASSIS_PREFIX + "|IK_lift_left_base|d11t_light_inner_L",
        CHASSIS_PREFIX + "|IK_lift_right_base|d11t_light_inner_R",
        *(CHASSIS_PREFIX + "|ctrl_dash_v5_" + name for name in
          ("coolant", "fuel", "hyd_temp", "tach", "trans_temp")),
        CHASSIS_PREFIX + "|sfx",
    ]
    if not push_and_roll_present:
        source.append(LIFT_PREFIX + "|BoneBlade_cdt")
        roll = LIFT_PREFIX + "|BoneBladeRoll_cdt"
        repaired.extend((roll, roll + "|BoneBlade_cdt"))
        for side in ("left", "right"):
            tilt = LIFT_PREFIX + f"|IK_tilt_{side}_base"
            source.extend((tilt, tilt + f"|IK_tilt_{side}_tip"))
            push = LIFT_PREFIX + f"|IK_push_arm_{side}_base"
            repaired.extend((push, push + f"|IK_push_arm_{side}_tip",
                             push + f"|IK_tilt_{side}_base",
                             push + f"|IK_tilt_{side}_base|IK_tilt_{side}_tip"))
    return sorted(source), sorted(repaired)


def validate_result(value: object, blender_sha256: str, *,
                    push_and_roll_present: bool = False) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise LadderError("Blender result schema differs")
    if type(push_and_roll_present) is not bool:
        raise LadderError("combined repair option must be boolean")
    expected = {
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256, "sceneFrame": 1,
        "pushAndRollPresent": push_and_roll_present,
        "beforeSourceBoneCount": 389 if push_and_roll_present else 384,
        "afterSourceBoneCount": 392 if push_and_roll_present else 387,
        "repairedStructuralCount": 400,
        "beforeSharedPathCount": 388 if push_and_roll_present else 378,
        "afterSharedPathCount": 392 if push_and_roll_present else 382,
        "afterChangedMatrixCount": 0,
        "sourceLadderBoneParentedObjectCount": 0,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(value.get(key)) is not type(item) or value.get(key) != item
           for key, item in expected.items()):
        raise LadderError("Blender identity, coverage or no-write fields differ")
    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(value.get("blenderVersion"), str) or
            not value["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[blender_sha256])):
        raise LadderError("Blender version differs")
    source, repaired = _residual_paths(push_and_roll_present)
    if (value.get("afterSourceOnlyPaths") != source or
            value.get("afterRepairedOnlyPaths") != repaired):
        raise LadderError("Residual hierarchy paths differ")
    targets = value.get("targetMatrixErrors")
    if (not isinstance(targets, list) or len(targets) != 4 or
            [row.get("path") for row in targets if isinstance(row, dict)] !=
            _target_paths()):
        raise LadderError("Ladder target path roster differs")
    errors = [row.get("maxElementError") for row in targets]
    shared_max = value.get("afterMaxSharedMatrixError")
    if (any(not _finite_nonnegative(item) for item in [shared_max, *errors]) or
            shared_max < max(errors)):
        raise LadderError("Matrix measurements are invalid")
    matched = shared_max <= TOLERANCE and all(
        error <= TOLERANCE for error in errors)
    status = ("IN_MEMORY_LADDER_MATCH" if matched else
              "IN_MEMORY_LADDER_DIFFERENT")
    if value.get("status") != status:
        raise LadderError("Blender status contradicts matrix measurements")
    return value


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise LadderError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise LadderError("accepted inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise LadderError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, pinned_root, _, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if pinned_root != source_root:
        raise LadderError("authoring root changed during validation")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise LadderError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "ladder worker")
    dependencies = [
        (PUSH_WORKER, PUSH_WORKER_SHA256, "push-branch worker"),
        (Path(blender_left_push_probe.__file__), LEFT_PROBE_SHA256,
         "left-probe dependency"),
        (Path(blender_armature_parity.__file__), ARMATURE_PARITY_SHA256,
         "armature comparison dependency"),
    ]
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
        raise LadderError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise LadderError("Blender did not emit one ladder result")
    result = validate_result(json.loads(lines[0]), blender_sha)
    require_hash(registry, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise LadderError("authoring root changed during diagnostic")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after diagnostic")
    require_hash(worker, WORKER_SHA256, "ladder worker after diagnostic")
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
    except (LadderError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(error),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
