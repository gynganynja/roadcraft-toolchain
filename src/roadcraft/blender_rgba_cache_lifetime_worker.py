"""Blender-side, no-save reproduction of SDK RGBA cache-key lifetime reuse.

Only two disposable in-memory meshes are created. No source Blend or USF is
opened, and no Blender file or asset is saved or exported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_rgba_cache_lifetime import (  # noqa: E402
    BLENDER_VERSION_PINS, MAX_ATTEMPTS, RESULT_PREFIX,
    CacheLifetimeError, require_hash, require_sdk_pins,
)


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise CacheLifetimeError(message)


def _scratch_object(name: str, rgba: tuple[float, float, float, float]):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    colors = mesh.color_attributes.new(name="C", type="FLOAT_COLOR",
                                       domain="POINT")
    colors.data[0].color = rgba
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def run_probe(*, sdk_root: Path, worker_sha256: str, host_sha256: str,
              blender_sha256: str) -> dict:
    _need(blender_sha256 in BLENDER_VERSION_PINS,
          "Blender executable pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256,
                 "Blender executable")
    require_hash(Path(__file__), worker_sha256, "cache lifetime worker")
    host = Path(__file__).with_name("blender_rgba_cache_lifetime.py")
    require_hash(host, host_sha256, "cache lifetime host")
    sdk = require_sdk_pins(sdk_root)
    _need(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
          "Blender version differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMeshColorSet

    _need(len(RGBA_CACHE) == 0, "SDK RGBA cache was not empty at startup")
    white_obj = gray_obj = None
    white_eval = gray_eval = None
    collision = None
    try:
        white_obj = _scratch_object("scratch_white", (1.0, 1.0, 1.0, 1.0))
        gray_obj = _scratch_object("scratch_gray", (0.2, 0.3, 0.4, 1.0))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        white_eval = white_obj.evaluated_get(depsgraph)
        white_mesh = white_eval.to_mesh()
        white_key = white_mesh.color_attributes["C"].data[0].color
        white_type = type(white_key).__name__
        white_hash = hash(white_key)
        white_packed = UsfMeshColorSet.rgba_to_saber(white_key)
        _need(white_type == "bpy_prop_array" and white_packed == 0xFFFFFFFF and
              len(RGBA_CACHE) == 1,
              "SDK white cache entry did not match expected setup")
        white_eval.to_mesh_clear()

        gray_eval = gray_obj.evaluated_get(depsgraph)
        for attempt in range(MAX_ATTEMPTS):
            gray_mesh = gray_eval.to_mesh()
            gray_key = gray_mesh.color_attributes["C"].data[0].color
            same_hash = hash(gray_key) == white_hash
            equal_key = same_hash and gray_key == white_key
            if equal_key:
                raw = [float(value) for value in gray_key]
                cache_before = len(RGBA_CACHE)
                cached_value = RGBA_CACHE.get(gray_key)
                stale = UsfMeshColorSet.rgba_to_saber(gray_key)
                cache_after_stale = len(RGBA_CACHE)
                RGBA_CACHE.clear()  # Disposable in-process control only.
                fresh = UsfMeshColorSet.rgba_to_saber(gray_key)
                collision = {
                    "attempt": attempt, "sameHash": same_hash,
                    "equalKey": equal_key, "rawRgba": raw,
                    "cacheBeforeLookup": cache_before,
                    "cachedValue": cached_value,
                    "stalePacked": stale,
                    "cacheAfterStale": cache_after_stale,
                    "freshAfterClearPacked": fresh,
                    "cacheAfterFresh": len(RGBA_CACHE),
                }
                gray_eval.to_mesh_clear()
                break
            gray_eval.to_mesh_clear()
    finally:
        RGBA_CACHE.clear()
        for obj in (white_obj, gray_obj):
            if obj is not None and obj.name in bpy.data.objects:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh.name in bpy.data.meshes:
                    bpy.data.meshes.remove(mesh)

    require_hash(Path(bpy.app.binary_path), blender_sha256,
                 "Blender executable after")
    require_hash(Path(__file__), worker_sha256, "worker after")
    require_hash(host, host_sha256, "host after")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1,
        "status": ("SDK_RGBA_STALE_CACHE_REPRODUCED" if collision and
                   collision["stalePacked"] == 0xFFFFFFFF and
                   collision["freshAfterClearPacked"] == 0xFF334C66
                   else "SDK_RGBA_COLLISION_NOT_REPRODUCED"),
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sdkMeshSha256": "4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337",
        "workerSha256": worker_sha256, "hostSha256": host_sha256,
        "maxAttempts": MAX_ATTEMPTS,
        "whiteKeyType": white_type,
        "whitePacked": white_packed,
        "collision": collision,
        "acceptedAssetOpened": False,
        "blendSaved": False, "usfExported": False,
        "sdkFileChanged": False,
        "nativeBlendExportApproved": False,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_probe(
        sdk_root=args.sdk_script_root,
        worker_sha256=args.worker_sha256,
        host_sha256=args.host_sha256,
        blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
