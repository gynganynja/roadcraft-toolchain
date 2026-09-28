"""Blender-side, no-save readback of pinned D11 v2/v3 animations."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_animation_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST_SHA256,
    AnimationPayloadError, require_hash, require_sdk_pins,
)
from roadcraft.blender_animation_payload_worker import (  # noqa: E402
    _f32, _source_actions, _spline, _vector,
)
from roadcraft.blender_animation_variants import (  # noqa: E402
    BASE_HOST, BASE_HOST_SHA256, BASE_WORKER, BASE_WORKER_SHA256,
    RESULT_PREFIX, VARIANTS,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnimationPayloadError(message)


def _usf_record(path: Path, expected_root: str) -> dict:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == expected_root and root.actor_info is not None and
             root.actor_info.actor_name == expected_root,
             "variant USF root/actor differs")
    clips = [{"name": clip.name, "begin": int(clip.begin),
              "end": int(clip.end), "time": _f32(clip.time),
              "frames": len(clip.frames)} for clip in root.actor_info.anims]
    rows = []
    stack = [(root, "|@root")]
    seen = set()
    node_count = 0
    while stack:
        node, node_path = stack.pop()
        _require(node_path not in seen, "variant USF node path duplicated")
        seen.add(node_path)
        node_count += 1
        if node is not root:
            _require(node.actor_info is None,
                     "unexpected nested variant actor metadata")
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
              "clips": clips,
              "nodeAnimations": sorted(rows, key=lambda row: row["path"])}
    del scene
    gc.collect()
    return result


def run_readback(*, asset: str, blend: Path, repaired: Path, native: Path,
                 worklist: Path, summary: Path, sdk_root: Path,
                 worker_sha256: str, host_sha256: str,
                 blender_sha256: str) -> dict:
    _require(asset in VARIANTS and blender_sha256 in BLENDER_VERSION_PINS,
             "unreviewed variant or Blender executable")
    pins = VARIANTS[asset]
    blender = require_hash(Path(bpy.app.binary_path), blender_sha256,
                           "Blender executable")
    worker = require_hash(Path(__file__), worker_sha256,
                          "variant animation worker")
    host = require_hash(Path(__file__).with_name("blender_animation_variants.py"),
                        host_sha256, "variant animation host")
    require_hash(BASE_HOST, BASE_HOST_SHA256, "base animation host")
    require_hash(BASE_WORKER, BASE_WORKER_SHA256, "base animation worker")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, pins["repairedSha256"], "repaired USF")
    require_hash(native, pins["nativeSha256"], "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    require_hash(summary, pins["summarySha256"], "variant parity summary")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    matches = [row for row in evidence["assets"] if row.get("asset") == asset]
    _require(len(matches) == 1, "variant worklist row differs")
    row = matches[0]
    _require(row.get("blendSha256") == BLEND_SHA256 and
             row.get("repairedUsfSha256") == pins["repairedSha256"] and
             row.get("scratchNativeUsfSha256") == pins["nativeSha256"] and
             row.get("summarySha256") == pins["summarySha256"] and
             Path(row["summaryPath"]) == summary and
             row.get("nativeBlendExportApproved") is False,
             "variant worklist pins differ")
    receipt = json.loads(summary.read_text(encoding="utf-8"))
    _require(receipt.get("asset") == asset and
             Path(receipt["blendPath"]) == blend and
             Path(receipt["baselineUsfPath"]) == repaired and
             Path(receipt["candidateUsfPath"]) == native and
             receipt.get("baselineUsfSha256") == pins["repairedSha256"] and
             receipt.get("candidateUsfSha256") == pins["nativeSha256"] and
             receipt.get("nativeBlendExportApproved") is False,
             "variant parity summary pins differ")
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        repaired_record = _usf_record(repaired, "cat_d11t")
        native_record = _usf_record(native, asset)
    finally:
        BinaryIO.read_bytearray = original_reader
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1,
             "source scene initial frame differs")
    source_actions = _source_actions()
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, pins["repairedSha256"], "repaired USF"),
            (native, pins["nativeSha256"], "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, pins["summarySha256"], "summary"),
            (blender, blender_sha256, "Blender executable"),
            (host, host_sha256, "variant animation host"),
            (worker, worker_sha256, "variant animation worker"),
            (BASE_HOST, BASE_HOST_SHA256, "base animation host"),
            (BASE_WORKER, BASE_WORKER_SHA256, "base animation worker")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": asset,
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": pins["repairedSha256"],
        "nativeExportUsfSha256": pins["nativeSha256"],
        "summarySha256": pins["summarySha256"],
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha256,
        "hostSha256": host_sha256,
        "workerSha256": worker_sha256,
        "baseHostSha256": BASE_HOST_SHA256,
        "baseWorkerSha256": BASE_WORKER_SHA256,
        "repairedRootName": "cat_d11t",
        "nativeRootName": asset,
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
    parser.add_argument("--asset", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        asset=args.asset, blend=args.blend, repaired=args.repaired_usf,
        native=args.native_usf, worklist=args.worklist, summary=args.summary,
        sdk_root=args.sdk_script_root, worker_sha256=args.worker_sha256,
        host_sha256=args.host_sha256, blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
