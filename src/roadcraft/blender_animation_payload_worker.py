"""Blender-side, no-save D11 animation readback for three pinned assets."""

from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import struct
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_animation_payload import (  # noqa: E402
    ACTION_NAMES, BLEND_SHA256, BLENDER_VERSION_PINS, RESULT_PREFIX,
    SOURCE_PATH, USF_SHA256, WORKLIST_SHA256, AnimationPayloadError,
    require_hash, require_sdk_pins,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnimationPayloadError(message)


def _f32(value: object) -> float:
    number = float(value)
    _require(math.isfinite(number), "non-finite animation value")
    return struct.unpack("<f", struct.pack("<f", number))[0]


def _vector(values, dimension: int) -> list[float]:
    result = [_f32(value) for value in values]
    _require(len(result) == dimension, "animation vector dimension differs")
    return result


def _spline(spline) -> dict | None:
    if spline is None:
        return None
    count = int(spline.keys_count)
    dimension = int(spline.data_dimension)
    _require(0 <= count <= 10000 and 1 <= dimension <= 4 and
             int(spline.values_dimension) == dimension,
             "USF spline shape differs")
    data = bytes(spline.data)
    expected_size = count * (dimension + 1) * 4
    _require(int(spline.data_size) == len(data) == expected_size,
             "USF spline byte count differs")
    rows = []
    for values in struct.iter_unpack("<" + "f" * (dimension + 1), data):
        _require(all(math.isfinite(value) for value in values),
                 "USF spline contains non-finite float")
        rows.append({"frame": values[0], "value": list(values[1:])})
    _require(len(rows) == count, "USF spline sample count differs")
    return {"type": int(spline.type), "state": int(spline.state),
            "valuesDimension": int(spline.values_dimension),
            "dataDimension": dimension, "keysCount": count,
            "dataSize": int(spline.data_size), "samples": rows}


def _usf_record(path: Path) -> dict:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == "cat_d11t" and root.actor_info is not None,
             "USF root actor differs")
    clips = [{"name": clip.name, "begin": int(clip.begin),
              "end": int(clip.end), "time": _f32(clip.time),
              "frames": len(clip.frames)} for clip in root.actor_info.anims]
    rows = []
    stack = [(root, "|@root")]
    seen = set()
    node_count = 0
    while stack:
        node, node_path = stack.pop()
        _require(node_path not in seen, "USF node path duplicated")
        seen.add(node_path)
        node_count += 1
        if node is not root:
            _require(node.actor_info is None,
                     "unexpected nested USF actor metadata")
        if node.anim is not None:
            anim = node.anim
            rows.append({
                "path": node_path,
                "initial": {
                    "translate": _vector(anim.ini_translate, 3),
                    "rotation": _vector(anim.ini_rotation, 4),
                    "scale": _vector(anim.ini_scale, 3),
                    "visibility": _f32(anim.ini_visibility),
                },
                "splines": {
                    "translate": _spline(anim.spl_translate),
                    "rotation": _spline(anim.spl_rotation),
                    "scale": _spline(anim.spl_scale),
                    "visibility": _spline(anim.spl_visibility),
                },
            })
        for child in node.children:
            stack.append((child, node_path + "|" + child.name))
    result = {"nodeCount": node_count,
              "actorName": root.actor_info.actor_name,
              "clips": clips, "nodeAnimations": sorted(rows, key=lambda row: row["path"])}
    del scene
    gc.collect()
    return result


def _fcurves(action) -> list:
    if bpy.app.version < (5, 0, 0):
        return list(action.fcurves)
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                curves.extend(bag.fcurves)
    return curves


def _source_actions() -> list[dict]:
    from saber.blender.lib.usf.transform import get_anim_transform

    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    _require(len(arms) == 1 and arms[0].name == "D11T_Rig.005",
             "source armature differs")
    arm = arms[0]
    created_animation_data = arm.animation_data is None
    if created_animation_data:
        arm.animation_data_create()  # In-memory evaluation only; Blend is never saved.
    bone = arm.pose.bones.get("BoneAnim_WiperFront")
    _require(bone is not None and bone.parent is not None,
             "source wiper bone/parent differs")
    actions = list(bpy.data.actions)
    _require(len(actions) == 2 and {action.name for action in actions} == ACTION_NAMES,
             "source action set differs")
    old_action = arm.animation_data.action
    old_slot = arm.animation_data.action_slot
    old_frame = bpy.context.scene.frame_current
    records = []
    try:
        for action in actions:
            bounds = [int(action.frame_range[0]), int(action.frame_range[1])]
            tracks = []
            for curve in _fcurves(action):
                _require(curve.data_path == SOURCE_PATH,
                         "source action targets another property")
                keys = [{
                    "frame": _f32(key.co[0]),
                    "value": _f32(key.co[1]),
                    "interpolation": str(key.interpolation),
                    "handleLeft": _vector(key.handle_left, 2),
                    "handleRight": _vector(key.handle_right, 2),
                } for key in curve.keyframe_points]
                tracks.append({"dataPath": curve.data_path,
                               "arrayIndex": int(curve.array_index),
                               "keys": keys})
            tracks.sort(key=lambda track: track["arrayIndex"])
            arm.animation_data.action = action
            slots = list(action.slots)
            _require(len(slots) == 1, "source action slot coverage differs")
            arm.animation_data.action_slot = slots[0]
            samples = []
            for frame in range(bounds[0], bounds[1] + 1):
                bpy.context.scene.frame_set(frame)
                matrix = bone.parent.matrix.inverted() @ bone.matrix
                converter = get_anim_transform()
                if converter:
                    matrix = converter(matrix)
                translate, rotation, scale = matrix.to_4x4().decompose()
                rotation.invert()
                samples.append({"frame": frame,
                                "translate": _vector(translate, 3),
                                "rotation": _vector(rotation, 4),
                                "scale": _vector(scale, 3)})
            records.append({"name": action.name, "frameRange": bounds,
                            "tracks": tracks, "samples": samples})
    finally:
        arm.animation_data.action = old_action
        if old_action is not None and old_slot is not None:
            arm.animation_data.action_slot = old_slot
        bpy.context.scene.frame_set(old_frame)
        if created_animation_data:
            arm.animation_data_clear()
    return records


def run_readback(*, blend: Path, repaired: Path, native: Path,
                 worklist: Path, sdk_root: Path, worker_sha256: str,
                 host_sha256: str, blender_sha256: str,
                 native_usf_sha256: str, summary_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS,
             "Blender executable pin differs")
    blender = require_hash(Path(bpy.app.binary_path), blender_sha256,
                           "Blender executable")
    worker = require_hash(Path(__file__), worker_sha256, "animation worker")
    host = require_hash(Path(__file__).with_name("blender_animation_payload.py"),
                        host_sha256, "animation host")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    require_hash(native, native_usf_sha256, "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [row for row in evidence["assets"] if row.get("asset") == "cat_d11t"]
    _require(len(assets) == 1, "worklist base asset differs")
    asset = assets[0]
    _require(asset.get("blendSha256") == BLEND_SHA256 and
             asset.get("repairedUsfSha256") == USF_SHA256 and
             asset.get("scratchNativeUsfSha256") == native_usf_sha256 and
             asset.get("summarySha256") == summary_sha256 and
             asset.get("nativeBlendExportApproved") is False,
             "worklist animation asset identity differs")
    summary = require_hash(Path(asset["summaryPath"]), summary_sha256,
                           "base parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(Path(summary_data["candidateUsfPath"]) == native and
             summary_data["candidateUsfSha256"] == native_usf_sha256 and
             summary_data["nativeBlendExportApproved"] is False,
             "retained native summary differs")
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        repaired_record = _usf_record(repaired)
        native_record = _usf_record(native)
    finally:
        BinaryIO.read_bytearray = original_reader
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1,
             "source scene initial frame differs")
    source_actions = _source_actions()
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_usf_sha256, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, summary_sha256, "summary"),
            (blender, blender_sha256, "Blender executable"),
            (host, host_sha256, "animation host"),
            (worker, worker_sha256, "animation worker")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_usf_sha256,
        "worklistSha256": WORKLIST_SHA256,
        "summarySha256": summary_sha256,
        "blenderSha256": blender_sha256,
        "hostSha256": host_sha256,
        "workerSha256": worker_sha256,
        "blenderVersion": bpy.app.version_string,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceActions": source_actions,
        "repaired": repaired_record,
        "native": native_record,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    parser.add_argument("--summary-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        blend=args.blend, repaired=args.repaired_usf,
        native=args.native_usf, worklist=args.worklist,
        sdk_root=args.sdk_script_root, worker_sha256=args.worker_sha256,
        host_sha256=args.host_sha256, blender_sha256=args.blender_sha256,
        native_usf_sha256=args.native_usf_sha256,
        summary_sha256=args.summary_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
