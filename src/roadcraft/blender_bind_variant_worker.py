"""Blender-side, no-save source/USF bind readback for one D11 variant."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft import blender_bind_identity as base  # noqa: E402
from roadcraft import blender_bind_identity_worker as base_worker  # noqa: E402
from roadcraft import blender_bind_variant as variant  # noqa: E402
from roadcraft.blender_mesh_inventory_worker import (  # noqa: E402
    _predicted_path, _source_object,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise variant.VariantBindError(message)


def _usf_bind_rows(usf: Path, paths: set[str], expected_root: str) -> tuple[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(usf))
    root = scene._root_node
    _require(root.name == expected_root,
             f"USF root differs for {usf.name}")
    uid_nodes = {}
    path_nodes = {}
    stack = [(root, "|@root")]
    while stack:
        node, path = stack.pop()
        _require(type(node.uid) is int and node.uid not in uid_nodes,
                 "USF node UID is missing or duplicated")
        uid_nodes[node.uid] = node
        if path in paths:
            _require(path not in path_nodes and node.mesh is not None,
                     f"mapped USF mesh is absent: {path}")
            path_nodes[path] = node
        for child in node.children:
            stack.append((child, path + "|" + child.name))
    _require(set(path_nodes) == paths, "USF mesh path coverage differs")
    rows = {}
    for path in sorted(paths):
        mesh = path_nodes[path].mesh
        binds = []
        self_error = 0.0
        for bone in mesh.skin.skin_bones:
            target = uid_nodes.get(bone.usf_node_uid)
            _require(target is not None and isinstance(target.source_id, str) and
                     target.source_id.startswith("|"),
                     f"skin bone UID cannot resolve: {path}")
            stored = base_worker._flatten(bone.inv_bind_matr)
            resolved = base_worker._flatten(target.matrix_world.inverted())
            self_error = max(self_error,
                             max(abs(a - b) for a, b in zip(stored, resolved)))
            binds.append({"sourceId": target.source_id, "inverse": stored})
        _require(len(binds) <= 500, f"unbounded USF skin: {path}")
        rows[path] = {"binds": binds, "selfError": self_error}
    del scene, root, uid_nodes, path_nodes, stack
    gc.collect()
    return expected_root, rows


def run_readback(*, asset_name: str, blend: Path, repaired: Path, native: Path,
                 worklist: Path, summary: Path, sdk_root: Path,
                 worker_sha256: str, host_sha256: str,
                 blender_sha256: str) -> dict:
    pins = variant.variants._pins(asset_name)
    _require(blender_sha256 in base.BLENDER_VERSION_PINS,
             "Blender executable pin not reviewed")
    base.require_hash(Path(bpy.app.binary_path), blender_sha256,
                      "Blender executable")
    base.require_hash(Path(__file__), worker_sha256, "variant worker")
    host = Path(__file__).with_name("blender_bind_variant.py")
    base.require_hash(host, host_sha256, "variant host")
    base.require_hash(Path(base.__file__), variant.BASE_HOST_SHA256,
                      "base bind host")
    base.require_hash(Path(base_worker.__file__), variant.BASE_WORKER_SHA256,
                      "base bind worker")
    mapper = Path(__file__).with_name("blender_mesh_inventory_worker.py")
    base.require_hash(mapper, base.MAPPER_WORKER_SHA256, "path mapper")
    base.require_hash(blend, pins["blendSha256"], "variant source Blend")
    base.require_hash(repaired, pins["repairedUsfSha256"], "variant repaired USF")
    base.require_hash(worklist, base.WORKLIST_SHA256, "worklist")
    sdk = base.require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(base.BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    assets = [a for a in evidence["assets"] if a.get("asset") == asset_name]
    _require(len(assets) == 1, "variant worklist asset is not unique")
    asset = assets[0]
    _require(asset.get("sourceAssetDigest") == pins["sourceAssetDigest"] and
             asset.get("blendSha256") == pins["blendSha256"] and
             asset.get("repairedUsfSha256") == pins["repairedUsfSha256"] and
             asset.get("nativeExportRootName") == asset_name and
             asset.get("repairedRootName") == "cat_d11t" and
             asset.get("nativeBlendExportApproved") is False,
             "variant worklist identity or gate differs")
    native_sha = asset["scratchNativeUsfSha256"]
    summary_sha = asset["summarySha256"]
    base.require_hash(native, native_sha, "variant retained native USF")
    base.require_hash(summary, summary_sha, "variant parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    _require(Path(summary_data["blendPath"]) == blend and
             Path(summary_data["baselineUsfPath"]) == repaired and
             Path(summary_data["candidateUsfPath"]) == native and
             summary_data["candidateUsfSha256"] == native_sha and
             summary_data["candidateRootName"] == asset_name and
             summary_data["baselineRootName"] == "cat_d11t" and
             summary_data["nativeBlendExportApproved"] is False,
             "variant summary does not pin own input paths")
    gaps = sorted(asset["findings"]["changedMeshNodes"],
                  key=lambda row: row["path"])
    paths = [row["path"] for row in gaps]
    _require(len(paths) == len(set(paths)) == 126,
             "variant mapped path coverage differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.transform import convert_to_saber_transform

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_root, native_rows = _usf_bind_rows(native, set(paths), asset_name)
        repaired_root, repaired_rows = _usf_bind_rows(repaired, set(paths),
                                                      "cat_d11t")
    finally:
        BinaryIO.read_bytearray = original_reader

    # This is the variant's own accepted Blend path, even when bytes match base.
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    used = set()
    rows = []
    for gap in gaps:
        path = gap["path"]
        obj = _source_object(path)
        _require(obj is not None and _predicted_path(obj) == path and
                 scene_meshes.get(obj.name) == obj and obj.visible_get() and
                 obj.name not in used,
                 f"source mesh mapping differs: {path}")
        used.add(obj.name)
        source = base_worker._source_binds(obj, convert_to_saber_transform)
        n = native_rows[path]
        r = repaired_rows[path]
        _require(len(n["binds"]) == gap["nativeExportSkinBoneUidCount"] and
                 len(r["binds"]) == gap["repairedSkinBoneUidCount"],
                 f"variant skin coverage differs: {path}")
        rows.append({
            "path": path, "sourceObject": obj.name,
            "sourceNative": base.compare_binds(source, n["binds"]),
            "sourceRepaired": base.compare_binds(source, r["binds"]),
            "nativeSelfMaxElementError": n["selfError"],
            "repairedSelfMaxElementError": r["selfError"],
        })
    for path, digest, label in (
            (blend, pins["blendSha256"], "Blend"),
            (repaired, pins["repairedUsfSha256"], "repaired USF"),
            (native, native_sha, "native USF"),
            (worklist, base.WORKLIST_SHA256, "worklist"),
            (summary, summary_sha, "summary"),
            (host, host_sha256, "host"),
            (Path(__file__), worker_sha256, "worker"),
            (Path(base.__file__), variant.BASE_HOST_SHA256, "base host"),
            (Path(base_worker.__file__), variant.BASE_WORKER_SHA256,
             "base worker"),
            (mapper, base.MAPPER_WORKER_SHA256, "mapper")):
        base.require_hash(path, digest, label + " after readback")
    base.require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": base.WORKLIST_SHA256,
        "summarySha256": summary_sha,
        "blenderSha256": blender_sha256, "hostSha256": host_sha256,
        "mapperWorkerSha256": base.MAPPER_WORKER_SHA256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedRootName": repaired_root,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "rows": rows,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=tuple(variant.variants.ASSET_PINS),
                        required=True)
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
        asset_name=args.asset, blend=args.blend,
        repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, summary=args.summary,
        sdk_root=args.sdk_script_root,
        worker_sha256=args.worker_sha256,
        host_sha256=args.host_sha256,
        blender_sha256=args.blender_sha256)
    print(variant.RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
