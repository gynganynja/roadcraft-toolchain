"""Source-pinned, no-save D11 push-arm hierarchy reconstruction diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from . import blender_armature_parity, blender_left_push_probe
from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_left_push_probe import (
    BLEND_SHA256, INVENTORY_SHA256, USF_SHA256,
    LeftPushProbeError, _unlinked_path, require_hash, require_sdk_pins,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_push_branches_worker.py")
WORKER_SHA256 = "974df2d86d1045a57acf392ad8367a2db19a0367a1a717fe3b04baf9e7ca63d0"
LEFT_PROBE_SHA256 = "003e0f6d38cf37976fc4c91eeba2df5dff6c9882d3cbbe29d53d8a516234da72"
ARMATURE_PARITY_SHA256 = "32d81c496295ed73706cd862bf4e1b47e013f246631c50f486d7cfe6c3c3b72c"
RESULT_PREFIX = "ROADCRAFT_PUSH_BRANCHES "
CHASSIS_PREFIX = "|@root|D11T_Rig.005|BoneChassis_cdt"
ROOT_PREFIX = "|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt"
TOLERANCE = 1e-5


class PushBranchesError(RuntimeError):
    """The pinned in-memory probe or its result cannot be trusted."""


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _target_paths() -> list[str]:
    paths = []
    for side in ("left", "right"):
        base = ROOT_PREFIX + f"|IK_push_arm_{side}_base"
        paths.extend((base, base + f"|IK_push_arm_{side}_tip",
                      base + f"|IK_tilt_{side}_base",
                      base + f"|IK_tilt_{side}_base|IK_tilt_{side}_tip"))
    return sorted(paths)


def _residual_paths() -> tuple[list[str], list[str]]:
    source = [CHASSIS_PREFIX + "|BoneAccess_Ladder",
              ROOT_PREFIX + "|BoneBlade_cdt"]
    repaired = [
        CHASSIS_PREFIX + "|BoneAccess_LadderMount",
        CHASSIS_PREFIX + "|BoneAccess_LadderMount|BoneAccess_Swivel",
        CHASSIS_PREFIX + "|BoneAccess_LadderMount|BoneAccess_Swivel|BoneAccess_LadderHinge",
        CHASSIS_PREFIX + "|BoneAccess_LadderMount|BoneAccess_Swivel|BoneAccess_LadderHinge|BoneAccess_Ladder",
        ROOT_PREFIX + "|BoneBladeRoll_cdt",
        ROOT_PREFIX + "|BoneBladeRoll_cdt|BoneBlade_cdt",
        CHASSIS_PREFIX + "|IK_lift_left_base|d11t_light_inner_L",
        CHASSIS_PREFIX + "|IK_lift_right_base|d11t_light_inner_R",
        *(CHASSIS_PREFIX + "|ctrl_dash_v5_" + name for name in
          ("coolant", "fuel", "hyd_temp", "tach", "trans_temp")),
        CHASSIS_PREFIX + "|sfx",
    ]
    return sorted(source), sorted(repaired)


def validate_result(value: object, blender_sha256: str) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise PushBranchesError("Blender result schema differs")
    expected = {
        "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256, "sceneFrame": 1,
        "beforeSourceBoneCount": 384, "afterSourceBoneCount": 388,
        "repairedStructuralCount": 400,
        "beforeSharedPathCount": 378, "afterSharedPathCount": 386,
        "newBoneEditLength": 0.25, "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(value.get(key)) is not type(item) or value.get(key) != item
           for key, item in expected.items()):
        raise PushBranchesError("Blender identity, coverage or no-write fields differ")
    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(value.get("blenderVersion"), str) or
            not value["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[blender_sha256])):
        raise PushBranchesError("Blender version differs")
    source_only = value.get("afterSourceOnlyPaths")
    repaired_only = value.get("afterRepairedOnlyPaths")
    expected_source, expected_repaired = _residual_paths()
    if (not isinstance(source_only, list) or not isinstance(repaired_only, list) or
            source_only != expected_source or
            repaired_only != expected_repaired):
        raise PushBranchesError("Residual hierarchy paths differ")
    targets = value.get("targetMatrixErrors")
    if (not isinstance(targets, list) or len(targets) != 8 or
            [row.get("path") for row in targets if isinstance(row, dict)] !=
            _target_paths()):
        raise PushBranchesError("Push-arm target path roster differs")
    errors = [row.get("maxElementError") for row in targets]
    tilt = value.get("tiltPoseChanges")
    if (not isinstance(tilt, list) or len(tilt) != 2 or
            [row.get("side") for row in tilt if isinstance(row, dict)] !=
            ["left", "right"]):
        raise PushBranchesError("Tilt pose roster differs")
    changes = [row.get(key) for row in tilt
               for key in ("basePoseMatrixMaxChange", "tipPoseMatrixMaxChange")]
    shared_max = value.get("afterMaxSharedMatrixError")
    if (any(not _finite_nonnegative(item) for item in errors + changes) or
            not _finite_nonnegative(shared_max) or
            type(value.get("afterChangedMatrixCount")) is not int or
            value["afterChangedMatrixCount"] < 0 or
            shared_max < max(errors)):
        raise PushBranchesError("Matrix measurements are invalid")
    matched = (value["afterChangedMatrixCount"] == 0 and
               shared_max <= TOLERANCE and
               all(item <= TOLERANCE for item in errors + changes))
    status = ("IN_MEMORY_PUSH_BRANCH_MATCH" if matched else
              "IN_MEMORY_PUSH_BRANCH_DIFFERENT")
    if value.get("status") != status:
        raise PushBranchesError("Blender status contradicts matrix measurements")
    return value


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise PushBranchesError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise PushBranchesError("accepted inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise PushBranchesError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, pinned_root, _, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if pinned_root != source_root:
        raise PushBranchesError("authoring root changed during validation")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise PushBranchesError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "push-branch worker")
    require_hash(Path(blender_left_push_probe.__file__), LEFT_PROBE_SHA256,
                 "left-probe dependency")
    require_hash(Path(blender_armature_parity.__file__), ARMATURE_PARITY_SHA256,
                 "armature comparison dependency")
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
        raise PushBranchesError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise PushBranchesError("Blender did not emit one push-branch result")
    result = validate_result(json.loads(lines[0]), blender_sha)
    require_hash(registry, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise PushBranchesError("authoring root changed during diagnostic")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after diagnostic")
    require_hash(worker, WORKER_SHA256, "push-branch worker after diagnostic")
    require_hash(Path(blender_left_push_probe.__file__), LEFT_PROBE_SHA256,
                 "left-probe dependency after diagnostic")
    require_hash(Path(blender_armature_parity.__file__), ARMATURE_PARITY_SHA256,
                 "armature comparison dependency after diagnostic")
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
    except (PushBranchesError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(error),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
