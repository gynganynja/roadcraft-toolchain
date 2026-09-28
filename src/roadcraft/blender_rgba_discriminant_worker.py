"""Blender-side, bounded call-time RGBA trace for the pinned D11 v2 probe."""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import sys

import bpy
import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft import blender_mesh_variant_payload as variant  # noqa: E402
from roadcraft import blender_rgba_discriminant as probe  # noqa: E402
from roadcraft.blender_mesh_variant_payload_worker import (  # noqa: E402
    _raw_color_sets, run_readback,
)
from roadcraft.blender_left_push_probe import (  # noqa: E402
    require_hash, require_sdk_pins,
)
from roadcraft.blender_mesh_inventory_worker import _predicted_path  # noqa: E402
from roadcraft.blender_mesh_payload import WORKLIST_SHA256  # noqa: E402
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    WORKER_SHA256 as MAPPER_WORKER_SHA256,
)


def _stateless_pack(rgba) -> int:
    """Repeat the SDK's four-channel conversion without its RGBA_CACHE."""
    values = [ctypes.c_ulong(int(numpy.clip(rgba[index], 0.0, 1.0) * 255.0)).value
              for index in range(4)]
    return ctypes.c_ulong(((values[3] & 255) << 24) |
                          ((values[0] & 255) << 16) |
                          ((values[1] & 255) << 8) |
                          (values[2] & 255)).value


def run_probe(*, blend: Path, repaired: Path, native: Path, worklist: Path,
              summary: Path, sdk_root: Path, probe_worker_sha256: str,
              probe_host_sha256: str, blender_sha256: str) -> dict:
    if blender_sha256 != probe.BLENDER_SHA256:
        raise probe.RgbaDiscriminantError("Blender pin is outside 5.2 probe")
    if probe_worker_sha256 != probe.WORKER_SHA256:
        raise probe.RgbaDiscriminantError("RGBA worker pin differs")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), probe_worker_sha256, "RGBA probe worker")
    require_hash(Path(probe.__file__), probe_host_sha256, "RGBA probe host")
    require_hash(Path(variant.__file__), probe.VARIANT_HOST_SHA256,
                 "reviewed variant mesh host")
    require_hash(variant.WORKER, probe.VARIANT_WORKER_SHA256,
                 "reviewed variant mesh worker")
    sdk = require_sdk_pins(sdk_root)
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMesh, UsfMeshColorSet

    original_b_read = UsfMesh.b_read
    original_pack = UsfMeshColorSet.rgba_to_saber
    active = False
    target_seen = False
    cache_before = cache_after = None
    rgba_key_type = None
    records = []
    sentinel = object()

    def traced_pack(rgba):
        nonlocal rgba_key_type
        if not active:
            return original_pack(rgba)
        raw = tuple(float(value) for value in rgba)
        if rgba_key_type is None:
            rgba_key_type = type(rgba).__name__
        prior = RGBA_CACHE.get(rgba, sentinel)
        hit = prior is not sentinel
        direct = _stateless_pack(raw)
        actual = original_pack(rgba)
        records.append((raw, hit, prior if hit else None, direct, actual))
        return actual

    def traced_b_read(self, obj, flip_uv=True):
        nonlocal active, target_seen, cache_before, cache_after
        is_target = _predicted_path(obj) == probe.TARGET_PATH
        if is_target:
            if active or target_seen:
                raise probe.RgbaDiscriminantError("target projected more than once")
            active = True
            target_seen = True
            cache_before = len(RGBA_CACHE)
        try:
            return original_b_read(self, obj, flip_uv=flip_uv)
        finally:
            if is_target:
                cache_after = len(RGBA_CACHE)
                active = False

    UsfMesh.b_read = traced_b_read
    UsfMeshColorSet.rgba_to_saber = staticmethod(traced_pack)
    try:
        raw_result = run_readback(
            asset_name=probe.ASSET, blend=blend, repaired=repaired,
            native=native, worklist=worklist, summary=summary,
            sdk_root=sdk, worker_sha256=probe.VARIANT_WORKER_SHA256,
            mapper_sha256=MAPPER_WORKER_SHA256,
            host_sha256=probe.VARIANT_HOST_SHA256,
            blender_sha256=blender_sha256)
    finally:
        UsfMesh.b_read = original_b_read
        UsfMeshColorSet.rgba_to_saber = staticmethod(original_pack)
    if not target_seen or active or cache_before is None or cache_after is None:
        raise probe.RgbaDiscriminantError("target RGBA trace was not completed")

    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    candidates = [row for row in evidence["assets"]
                  if row.get("asset") == probe.ASSET]
    if len(candidates) != 1:
        raise probe.RgbaDiscriminantError("worklist variant is not unique")
    gap_rows = sorted(candidates[0]["findings"]["changedMeshNodes"],
                      key=lambda row: row["path"])
    interpreted = variant.interpret_readback(raw_result, gap_rows,
                                             probe.ASSET, blender_sha256,
                                             probe.VARIANT_HOST_SHA256)
    target_rows = [row for row in raw_result["rows"]
                   if row["path"] == probe.TARGET_PATH]
    if len(target_rows) != 1:
        raise probe.RgbaDiscriminantError("target payload row is not unique")
    color_field = target_rows[0]["fields"]["packedColors"]
    if (color_field["source"]["elements"] != probe.TARGET_ELEMENTS or
            color_field["source"]["sets"] != 1 or
            color_field["native"]["sets"] != 1):
        raise probe.RgbaDiscriminantError("target color shape differs")

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_sets = _raw_color_sets(native, {probe.TARGET_PATH}, probe.ASSET)
    finally:
        BinaryIO.read_bytearray = original_reader
    values = native_sets[probe.TARGET_PATH]
    if len(values) != 1:
        raise probe.RgbaDiscriminantError("native target has multiple color sets")
    detail = probe.summarize_trace(records, values[0], color_field["source"],
                                   color_field["native"])
    if detail["elements"] != probe.TARGET_ELEMENTS:
        raise probe.RgbaDiscriminantError("target trace length differs")
    for path, digest, label in (
            (blend, variant.ASSET_PINS[probe.ASSET]["blendSha256"], "source Blend"),
            (repaired, variant.ASSET_PINS[probe.ASSET]["repairedUsfSha256"],
             "repaired USF"),
            (native, variant.ASSET_PINS[probe.ASSET]["nativeUsfSha256"],
             "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, variant.ASSET_PINS[probe.ASSET]["summarySha256"],
             "native summary"),
            (Path(__file__), probe_worker_sha256, "RGBA probe worker"),
            (Path(probe.__file__), probe_host_sha256, "RGBA probe host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "status": "SOURCE_RGBA_DISCRIMINANT",
        "asset": probe.ASSET, "targetPath": probe.TARGET_PATH,
        "blenderSha256": blender_sha256,
        "probeHostSha256": probe_host_sha256,
        "probeWorkerSha256": probe_worker_sha256,
        "variantHostSha256": probe.VARIANT_HOST_SHA256,
        "variantWorkerSha256": probe.VARIANT_WORKER_SHA256,
        "nativeBlendExportApproved": False,
        "blendSaved": False, "usfExported": False,
        "mappedRows": interpreted["mappedRows"],
        "matchingNativeColorsRows": interpreted["matchingNativeRowsByField"]["packedColors"],
        "rowsDigestSha256": interpreted["rowsDigestSha256"],
        "rgbaKeyType": rgba_key_type,
        "cacheBeforeTarget": cache_before, "cacheAfterTarget": cache_after,
        "detail": detail,
        "sourceUnchanged": True, "sdkUnchanged": True,
        "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=(probe.ASSET,), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--probe-worker-sha256", required=True)
    parser.add_argument("--probe-host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_probe(
        blend=args.blend, repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, summary=args.summary,
        sdk_root=args.sdk_script_root,
        probe_worker_sha256=args.probe_worker_sha256,
        probe_host_sha256=args.probe_host_sha256,
        blender_sha256=args.blender_sha256)
    print(probe.RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
