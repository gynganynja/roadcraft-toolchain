"""Pinned, no-save D11 source/repaired/native animation readback.

This diagnostic inspects the historical Blend and two existing USFs.  It does
not construct or serialize a new USF, save a Blend, or approve native export.
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
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_animation_payload_worker.py")
WORKER_SHA256 = "d464ccf0656ed848bb49df1640fa54d31644c0bccf1f2f11ad17caff536769ab"
RESULT_PREFIX = "ROADCRAFT_ANIMATION_PAYLOAD "
MAX_JSON_BYTES = 128 * 1024
ACTION_NAMES = {"d11_wipers_backward", "d11_wipers_forward"}
WIPER_TARGET = '|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront'
SOURCE_PATH = 'pose.bones["BoneAnim_WiperFront"].rotation_euler'


class AnimationPayloadError(RuntimeError):
    """A pinned input, animation shape, or no-write result differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AnimationPayloadError(f"{label} must be finite")
    return float(value)


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise AnimationPayloadError(f"{label} has wrong dimension")
    return [_number(item, label) for item in value]


def _samples(value: object, length: int, dimension: int, label: str) -> list[dict]:
    if not isinstance(value, list) or len(value) != length:
        raise AnimationPayloadError(f"{label} sample count differs")
    output = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"frame", "value"}:
            raise AnimationPayloadError(f"{label} sample shape differs")
        output.append({"frame": _number(item["frame"], label),
                       "value": _vector(item["value"], dimension, label)})
    return output


def _check_source(actions: object) -> dict[str, dict]:
    if not isinstance(actions, list) or len(actions) != 2:
        raise AnimationPayloadError("source action coverage differs")
    by_name = {}
    for action in actions:
        if not isinstance(action, dict) or set(action) != {
                "name", "frameRange", "tracks", "samples"}:
            raise AnimationPayloadError("source action shape differs")
        name = action["name"]
        if name not in ACTION_NAMES or name in by_name:
            raise AnimationPayloadError("source action identity differs")
        bounds = action["frameRange"]
        if (not isinstance(bounds, list) or len(bounds) != 2 or
                any(type(v) is not int for v in bounds) or
                bounds[1] - bounds[0] != 17):
            raise AnimationPayloadError("source action frame range differs")
        tracks = action["tracks"]
        if not isinstance(tracks, list) or len(tracks) != 3:
            raise AnimationPayloadError("source Euler track coverage differs")
        indices = set()
        for track in tracks:
            if (not isinstance(track, dict) or set(track) != {
                    "dataPath", "arrayIndex", "keys"} or
                    track["dataPath"] != SOURCE_PATH or
                    type(track["arrayIndex"]) is not int or
                    track["arrayIndex"] not in (0, 1, 2) or
                    track["arrayIndex"] in indices or
                    not isinstance(track["keys"], list) or
                    len(track["keys"]) != 3):
                raise AnimationPayloadError("source Euler track differs")
            indices.add(track["arrayIndex"])
            frames = []
            for key in track["keys"]:
                if not isinstance(key, dict) or set(key) != {
                        "frame", "value", "interpolation", "handleLeft",
                        "handleRight"} or not isinstance(key["interpolation"], str):
                    raise AnimationPayloadError("source keyframe shape differs")
                frames.append(_number(key["frame"], "source keyframe"))
                _number(key["value"], "source keyframe")
                _vector(key["handleLeft"], 2, "source left handle")
                _vector(key["handleRight"], 2, "source right handle")
            if frames != sorted(set(frames)):
                raise AnimationPayloadError("source keyframes are not ordered")
        samples = action["samples"]
        if not isinstance(samples, list) or len(samples) != 18:
            raise AnimationPayloadError("source evaluated frame count differs")
        for offset, sample in enumerate(samples):
            if (not isinstance(sample, dict) or set(sample) != {
                    "frame", "translate", "rotation", "scale"} or
                    sample["frame"] != bounds[0] + offset):
                raise AnimationPayloadError("source evaluated frame differs")
            _vector(sample["translate"], 3, "source translation")
            _vector(sample["rotation"], 4, "source rotation")
            _vector(sample["scale"], 3, "source scale")
        by_name[name] = action
    if set(by_name) != ACTION_NAMES:
        raise AnimationPayloadError("source action set differs")
    return by_name


def _check_usf(side: object, *, native: bool) -> tuple[dict[str, dict], dict | None]:
    if not isinstance(side, dict) or set(side) != {
            "nodeCount", "actorName", "clips", "nodeAnimations"}:
        raise AnimationPayloadError("USF animation side shape differs")
    if (type(side["nodeCount"]) is not int or
            side["nodeCount"] != (597 if native else 654) or
            side["actorName"] != "cat_d11t"):
        raise AnimationPayloadError("USF node/actor identity differs")
    clips = side["clips"]
    if not isinstance(clips, list) or len(clips) != 2:
        raise AnimationPayloadError("USF clip coverage differs")
    by_name = {}
    for clip in clips:
        if not isinstance(clip, dict) or set(clip) != {
                "name", "begin", "end", "time", "frames"}:
            raise AnimationPayloadError("USF clip shape differs")
        name = clip["name"]
        if name not in ACTION_NAMES or name in by_name:
            raise AnimationPayloadError("USF clip identity differs")
        if (type(clip["begin"]) is not int or type(clip["end"]) is not int or
                clip["end"] - clip["begin"] != 17 or
                type(clip["frames"]) is not int or clip["frames"] != 0):
            raise AnimationPayloadError("USF clip frame shape differs")
        _number(clip["time"], "USF clip time")
        by_name[name] = clip
    if set(by_name) != ACTION_NAMES:
        raise AnimationPayloadError("USF clip set differs")
    if sorted((clip["begin"], clip["end"]) for clip in clips) != [
            (1, 18), (19, 36)]:
        raise AnimationPayloadError("USF clip windows differ")
    rows = side["nodeAnimations"]
    if not isinstance(rows, list) or len(rows) != (0 if native else 1):
        raise AnimationPayloadError("USF animated-node coverage differs")
    if native:
        return by_name, None
    row = rows[0]
    if not isinstance(row, dict) or set(row) != {
            "path", "initial", "splines"} or row["path"] != WIPER_TARGET:
        raise AnimationPayloadError("repaired wiper target differs")
    initial = row["initial"]
    if not isinstance(initial, dict) or set(initial) != {
            "translate", "rotation", "scale", "visibility"}:
        raise AnimationPayloadError("repaired initial transform differs")
    for key, length in (("translate", 3), ("rotation", 4), ("scale", 3)):
        _vector(initial[key], length, "repaired initial " + key)
    _number(initial["visibility"], "repaired initial visibility")
    splines = row["splines"]
    if (not isinstance(splines, dict) or set(splines) != {
            "translate", "rotation", "scale", "visibility"} or
            splines["visibility"] is not None):
        raise AnimationPayloadError("repaired spline set differs")
    for key, dimension in (("translate", 3), ("rotation", 4), ("scale", 3)):
        spline = splines[key]
        if not isinstance(spline, dict) or set(spline) != {
                "type", "state", "valuesDimension", "dataDimension",
                "keysCount", "dataSize", "samples"}:
            raise AnimationPayloadError("repaired spline shape differs")
        if (any(type(spline[field]) is not int for field in (
                "type", "state", "valuesDimension", "dataDimension",
                "keysCount", "dataSize")) or
                spline["valuesDimension"] != dimension or
                spline["dataDimension"] != dimension or
                spline["keysCount"] != 36 or
                spline["dataSize"] != 36 * (dimension + 1) * 4):
            raise AnimationPayloadError("repaired spline dimension differs")
        samples = _samples(spline["samples"], 36, dimension, key)
        if [sample["frame"] for sample in samples] != [float(i) for i in range(1, 37)]:
            raise AnimationPayloadError("repaired spline time index differs")
    return by_name, row


def _rotation_error(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if min(left_norm, right_norm) < 1e-12:
        raise AnimationPayloadError("zero-length rotation quaternion")
    dot = abs(sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm))
    return 2 * math.acos(min(1.0, dot))


def compare_records(actions: object, repaired: object, native: object) -> dict:
    """Compare metadata and aligned evaluated transforms without export."""
    source = _check_source(actions)
    repaired_clips, repaired_wiper = _check_usf(repaired, native=False)
    native_clips, _ = _check_usf(native, native=True)
    windows_equal = all(repaired_clips[name] == native_clips[name]
                        for name in ACTION_NAMES)
    if not windows_equal:
        raise AnimationPayloadError("native/repaired clip metadata differs")
    maxima = {"translate": 0.0, "rotationRadians": 0.0, "scale": 0.0}
    for name in sorted(ACTION_NAMES):
        clip = repaired_clips[name]
        for index, source_sample in enumerate(source[name]["samples"]):
            sample_index = clip["begin"] - 1 + index
            if sample_index >= clip["end"]:
                raise AnimationPayloadError("source/USF clip sample alignment differs")
            for component in ("translate", "scale"):
                right = repaired_wiper["splines"][component]["samples"][sample_index]["value"]
                maxima[component] = max(maxima[component], *(
                    abs(a - b) for a, b in zip(source_sample[component], right)))
            right_rotation = repaired_wiper["splines"]["rotation"]["samples"][sample_index]["value"]
            maxima["rotationRadians"] = max(
                maxima["rotationRadians"],
                _rotation_error(source_sample["rotation"], right_rotation))
    return {
        "sourceActionNamesMatchUsfClips": True,
        "repairedNativeClipMetadataEqual": windows_equal,
        "sourceTarget": SOURCE_PATH,
        "repairedTarget": WIPER_TARGET,
        "nativeAnimatedNodeCount": 0,
        "sourceTrackCount": 6,
        "sourceKeyframePointCount": 18,
        "sourceEvaluatedFramesComparedToRepaired": 36,
        "repairedWiperSamplesByTransform": {
            "translate": 36, "rotation": 36, "scale": 36},
        "sourceRepairedMaximumErrors": maxima,
        "sourceRepairedWithinTolerance": (
            maxima["translate"] <= 1e-5 and maxima["scale"] <= 1e-5 and
            maxima["rotationRadians"] <= 1e-5),
        "nativeWiperTransformTrackPresent": False,
        "nativeBlendExportApproved": False,
    }


def interpret_readback(result: object, blender_sha: str, native_sha: str,
                       summary_sha: str, host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha,
        "blenderSha256": blender_sha, "hostSha256": host_sha,
        "workerSha256": WORKER_SHA256,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if (not isinstance(result, dict) or set(result) != set(expected) | {
            "blenderVersion", "sourceActions", "repaired", "native"} or
            any(type(result.get(key)) is not type(value) or
                result.get(key) != value for key, value in expected.items()) or
            blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise AnimationPayloadError("animation readback identity or no-write fields differ")
    comparison = compare_records(result["sourceActions"], result["repaired"],
                                 result["native"])
    payload = {key: result[key] for key in expected}
    payload.update({
        "status": "SOURCE_REPAIRED_NATIVE_ANIMATION_READBACK",
        "blenderVersion": result["blenderVersion"],
        "comparison": comparison,
        "recordsDigestSha256": hashlib.sha256(_canonical([
            result["sourceActions"], result["repaired"],
            result["native"]])).hexdigest(),
        "sourceActions": result["sourceActions"],
        "repaired": result["repaired"], "native": result["native"],
    })
    if len(_canonical(payload)) > MAX_JSON_BYTES:
        raise AnimationPayloadError("animation result exceeded bound")
    return payload


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise AnimationPayloadError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise AnimationPayloadError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise AnimationPayloadError("authoring inventory is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    parsed = json.loads(worklist.read_text(encoding="utf-8"))
    _worklist_rows(parsed, asset["assetDigest"])
    _, native, native_sha, summary_path, summary_sha = _rows_and_native(
        parsed, asset["assetDigest"], blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise AnimationPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "animation worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--host-sha256", host_sha,
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
        raise AnimationPayloadError(f"Blender exited {completed.returncode}: {tail}")
    matches = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise AnimationPayloadError("Blender did not emit one bounded animation readback")
    result = interpret_readback(json.loads(matches[0]), blender_sha, native_sha,
                                summary_sha, host_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256, "inventory after readback")
    if _unlinked_path(Path(inventory["sourceRoot"]), "source root after") != source_root:
        raise AnimationPayloadError("source root changed during readback")
    for path, digest, label in ((blend, BLEND_SHA256, "source Blend"),
                                (repaired, USF_SHA256, "repaired USF"),
                                (native, native_sha, "retained native USF"),
                                (worklist, WORKLIST_SHA256, "worklist"),
                                (summary_path, summary_sha, "parity summary"),
                                (blender, blender_sha, "Blender executable"),
                                (Path(__file__), host_sha, "animation host"),
                                (worker, WORKER_SHA256, "animation worker")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise AnimationPayloadError("final animation result exceeded bound")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (AnimationPayloadError, BlenderAuthoringError, BladeRelocationError,
            LeftPushProbeError, MeshInventoryError, OSError, ValueError,
            KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
