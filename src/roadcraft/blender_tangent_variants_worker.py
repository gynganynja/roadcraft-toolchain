"""Blender-side, no-save D11 v2/v3 source-to-USF tangent readback."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_animation_variants import VARIANTS  # noqa: E402
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)
from roadcraft.blender_tangent_variants import (  # noqa: E402
    BASE_HOST, BASE_HOST_SHA256, INPUT_HOST, INPUT_HOST_SHA256,
    MAPPER_WORKER, MAPPER_WORKER_SHA256, RESULT_PREFIX,
    TangentVariantError, compare_tangent_arrays, require_hash,
    require_sdk_pins,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST_SHA256,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TangentVariantError(message)


def _usf_meshes(path: Path, root_name: str,
                wanted: set[str]) -> tuple[object, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == root_name, "variant USF root differs")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, node_path = stack.pop()
        if node_path in wanted:
            _require(node_path not in found and node.mesh is not None,
                     f"variant USF mesh path differs: {node_path}")
            found[node_path] = node.mesh
        for child in node.children:
            stack.append((child, node_path + "|" + child.name))
    _require(set(found) == wanted, "variant USF mesh coverage differs")
    return scene, found


def _read_side(*, usf: Path, root_name: str, paths: list[str],
               scene_meshes: dict, depsgraph) -> list[dict]:
    from saber.blender.lib.usf.mesh import UsfMesh

    scene, target_meshes = _usf_meshes(usf, root_name, set(paths))
    used = set()
    rows = []
    for node_path in paths:
        obj = _source_object(node_path)
        _require(obj is not None and _predicted_path(obj) == node_path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {node_path}")
        used.add(obj.name)
        evaluated_object = obj.evaluated_get(depsgraph)
        target_mesh = target_meshes.pop(node_path)
        try:
            projected = UsfMesh().b_read(obj)
            comparison = compare_tangent_arrays(projected, target_mesh)
        finally:
            evaluated_object.to_mesh_clear()
        rows.append({"path": node_path, "sourceObject": obj.name,
                     "comparison": comparison})
        del projected, target_mesh, comparison
        if len(rows) % 10 == 0:
            gc.collect()
    _require(not target_meshes and len(used) == 126,
             "variant target/source mesh rows were not consumed")
    del scene, target_meshes
    gc.collect()
    return rows


def run_readback(*, asset: str, blend: Path, repaired: Path,
                 native: Path, worklist: Path, summary: Path,
                 sdk_root: Path, worker_sha256: str,
                 host_sha256: str, blender_sha256: str) -> dict:
    _require(asset in VARIANTS and blender_sha256 in BLENDER_VERSION_PINS,
             "unreviewed variant or Blender executable")
    pins = VARIANTS[asset]
    blender = require_hash(Path(bpy.app.binary_path), blender_sha256,
                           "Blender executable")
    worker = require_hash(Path(__file__), worker_sha256,
                          "variant tangent worker")
    host = require_hash(Path(__file__).with_name("blender_tangent_variants.py"),
                        host_sha256, "variant tangent host")
    for path, digest, label in (
            (INPUT_HOST, INPUT_HOST_SHA256, "variant input host"),
            (BASE_HOST, BASE_HOST_SHA256, "base tangent host"),
            (MAPPER_WORKER, MAPPER_WORKER_SHA256, "mesh mapper worker"),
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, pins["repairedSha256"], "repaired USF"),
            (native, pins["nativeSha256"], "retained native USF"),
            (worklist, WORKLIST_SHA256, "reconstruction worklist"),
            (summary, pins["summarySha256"], "variant parity summary")):
        require_hash(path, digest, label)
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    matches = [row for row in evidence["assets"] if row.get("asset") == asset]
    _require(len(matches) == 1, "variant worklist row differs")
    row = matches[0]
    _require(row.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             row.get("blendSha256") == BLEND_SHA256 and
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
             receipt.get("baselineRootName") == "cat_d11t" and
             receipt.get("candidateRootName") == asset and
             receipt.get("nativeBlendExportApproved") is False,
             "variant parity summary differs")
    paths = sorted(entry["path"] for entry in row["findings"]["changedMeshNodes"])
    _require(len(paths) == len(set(paths)) == 126,
             "variant worklist mesh coverage differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
        _require(bpy.context.scene.frame_current == 1,
                 "source scene frame differs")
        scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                        if obj.type == "MESH"}
        _require(len(scene_meshes) == 210,
                 "source scene mesh count differs")
        depsgraph = bpy.context.evaluated_depsgraph_get()
        native_rows = _read_side(usf=native, root_name=asset, paths=paths,
                                 scene_meshes=scene_meshes, depsgraph=depsgraph)
        repaired_rows = _read_side(usf=repaired, root_name="cat_d11t",
                                   paths=paths, scene_meshes=scene_meshes,
                                   depsgraph=depsgraph)
    finally:
        BinaryIO.read_bytearray = original_reader
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, pins["repairedSha256"], "repaired USF"),
            (native, pins["nativeSha256"], "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary, pins["summarySha256"], "summary"),
            (blender, blender_sha256, "Blender executable"),
            (host, host_sha256, "variant tangent host"),
            (worker, worker_sha256, "variant tangent worker"),
            (INPUT_HOST, INPUT_HOST_SHA256, "variant input host"),
            (BASE_HOST, BASE_HOST_SHA256, "base tangent host"),
            (MAPPER_WORKER, MAPPER_WORKER_SHA256, "mesh mapper worker")):
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
        "inputHostSha256": INPUT_HOST_SHA256,
        "baseTangentHostSha256": BASE_HOST_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "repairedRootName": "cat_d11t", "nativeRootName": asset,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "blenderVersion": bpy.app.version_string,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "nativeRows": native_rows, "repairedRows": repaired_rows,
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
