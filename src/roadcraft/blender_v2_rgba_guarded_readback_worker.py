"""Blender-side guarded 126-row v2 readback; no save or USF export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft import blender_rgba_cache_guard as guard  # noqa: E402
from roadcraft import blender_mesh_variant_payload as variant  # noqa: E402
from roadcraft import blender_v2_rgba_guarded_readback as host  # noqa: E402
from roadcraft import blender_v2_rgba_live_discriminant as live  # noqa: E402
from roadcraft import blender_v2_rgba_live_discriminant_worker as live_worker  # noqa: E402
from roadcraft.blender_left_push_probe import (  # noqa: E402
    require_hash, require_sdk_pins,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise host.GuardedReadbackError(message)


def run_guarded(*, blend: Path, repaired: Path, native: Path,
                worklist: Path, summary: Path, sdk_root: Path,
                worker_sha256: str, host_sha256: str,
                blender_sha256: str) -> dict:
    _require(worker_sha256 == host.WORKER_SHA256 and
             blender_sha256 == live.BLENDER_SHA256 and
             not bpy.data.filepath,
             "guard worker, Blender, or unopened-scene pin differs")
    for path, digest, label in (
            (Path(__file__), worker_sha256, "guarded worker"),
            (Path(host.__file__), host_sha256, "guarded host"),
            (Path(guard.__file__), host.GUARD_SHA256, "reviewed RGBA guard"),
            (Path(live.__file__), host.LIVE_HOST_SHA256, "reviewed live host"),
            (Path(live_worker.__file__), host.LIVE_WORKER_SHA256,
             "reviewed live worker"),
            (Path(bpy.app.binary_path), blender_sha256, "Blender executable")):
        require_hash(path, digest, label)
    _require(bpy.app.version_string.startswith("5.2."),
             "Blender runtime version differs")
    pins = variant.ASSET_PINS[live.ASSET]
    guard.require_pins(
        asset_name=live.ASSET, blend_sha256=pins["blendSha256"],
        baseline_usf_sha256=pins["repairedUsfSha256"],
        blender_sha256=blender_sha256,
        sdk_mesh_sha256=host.guard.SDK_MESH_SHA256,
        blender_version=bpy.app.version_string)
    for path, digest, label in (
            (blend, pins["blendSha256"], "accepted v2 Blend"),
            (repaired, pins["repairedUsfSha256"], "repaired v2 USF"),
            (native, pins["nativeUsfSha256"], "retained native USF"),
            (worklist, variant.WORKLIST_SHA256, "reconstruction worklist"),
            (summary, pins["summarySha256"], "retained native summary")):
        require_hash(path, digest, label)
    sdk = require_sdk_pins(sdk_root)
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMesh, UsfMeshColorSet

    sdk_mesh = (sdk / "saber" / "blender" / "lib" / "usf" / "mesh.py").resolve()
    original_read = UsfMesh.b_read
    original_pack = UsfMeshColorSet.rgba_to_saber
    original_getattribute = UsfMesh.__getattribute__
    _require(Path(original_read.__code__.co_filename).resolve() == sdk_mesh and
             Path(original_pack.__code__.co_filename).resolve() == sdk_mesh and
             original_getattribute is object.__getattribute__,
             "installed SDK class or packer differs")

    source_path = blend.resolve()

    def source_is_open() -> bool:
        return bool(bpy.data.filepath) and Path(bpy.data.filepath).resolve() == source_path

    projection = host.ProjectionGuard(
        UsfMesh, UsfMeshColorSet, RGBA_CACHE,
        source_is_open=source_is_open,
        is_mesh_object=lambda obj: isinstance(obj, bpy.types.Object) and
        obj.type == "MESH")
    with projection:
        base = live_worker.run_probe(
            blend=blend, repaired=repaired, native=native,
            worklist=worklist, summary=summary, sdk_root=sdk_root,
            probe_worker_sha256=host.LIVE_WORKER_SHA256,
            probe_host_sha256=host.LIVE_HOST_SHA256,
            blender_sha256=blender_sha256)
    _require(source_is_open() and projection.reads == 126 and
             projection.contexts_entered == 1 and
             projection.hook_restored and
             UsfMesh.__getattribute__ is original_getattribute and
             UsfMesh.b_read is original_read and
             UsfMeshColorSet.rgba_to_saber is original_pack and
             projection.guard_state is not None and
             projection.guard_state["packCalls"] > 0,
             "guarded source projection or SDK restoration differs")
    # The reused worker checks SDK function identities at its boundaries. Its
    # own unwrapped flag is deliberately not included in this guarded receipt.
    live.parse_result(live.RESULT_PREFIX + json.dumps(base),
                      host.LIVE_HOST_SHA256)
    for path, digest, label in (
            (Path(__file__), worker_sha256, "guarded worker"),
            (Path(host.__file__), host_sha256, "guarded host"),
            (Path(guard.__file__), host.GUARD_SHA256, "reviewed RGBA guard"),
            (Path(live.__file__), host.LIVE_HOST_SHA256, "reviewed live host"),
            (Path(live_worker.__file__), host.LIVE_WORKER_SHA256,
             "reviewed live worker"),
            (blend, pins["blendSha256"], "accepted v2 Blend"),
            (repaired, pins["repairedUsfSha256"], "repaired v2 USF"),
            (native, pins["nativeUsfSha256"], "retained native USF")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "status": "SOURCE_V2_RGBA_GUARDED_READBACK",
        "asset": live.ASSET, "blenderVersion": bpy.app.version_string,
        "blenderSha256": blender_sha256, "hostSha256": host_sha256,
        "workerSha256": worker_sha256, "guardSha256": host.GUARD_SHA256,
        "liveHostSha256": host.LIVE_HOST_SHA256,
        "liveWorkerSha256": host.LIVE_WORKER_SHA256,
        "blendSha256": pins["blendSha256"],
        "nativeUsfSha256": pins["nativeUsfSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "sdkMeshSha256": guard.SDK_MESH_SHA256,
        "mappedRows": base["mappedRows"],
        "matchingNativeColorsRows": base["matchingNativeColorsRows"],
        "otherColorMismatchRows": base["otherColorMismatchRows"],
        "rowsDigestSha256": base["rowsDigestSha256"],
        "target": base["target"],
        "guardEnabled": True, "sdkPackerTemporarilyGuarded": True,
        "guard": {
            "reads": projection.reads,
            "packCalls": projection.guard_state["packCalls"],
            "singleContext": projection.contexts_entered == 1,
            "packerRestored": projection.guard_state["restored"],
            "hookRestored": projection.hook_restored,
            "cacheClearedAfter": projection.guard_state["cacheClearedAfter"],
        },
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceUnchanged": base["sourceUnchanged"],
        "sdkUnchanged": base["sdkUnchanged"],
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=(live.ASSET,), required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--guard-worker-sha256", required=True)
    parser.add_argument("--guard-host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_guarded(
        blend=args.blend, repaired=args.repaired_usf,
        native=args.native_usf, worklist=args.worklist,
        summary=args.summary, sdk_root=args.sdk_script_root,
        worker_sha256=args.guard_worker_sha256,
        host_sha256=args.guard_host_sha256,
        blender_sha256=args.blender_sha256)
    print(host.RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
