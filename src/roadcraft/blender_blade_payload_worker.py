"""Blender-side, no-save payload projection of 60 D11 blade collision meshes."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_blade_payload import (  # noqa: E402
    BLADE_HOST, BLADE_HOST_SHA256, BLEND_SHA256, BLENDER_VERSION_PINS,
    BladePayloadError, FIELD_NAMES, LEAVES, MESH_HOST, MESH_HOST_SHA256,
    NATIVE_PARENT, REPAIRED_PARENT, RESULT_PREFIX, USF_SHA256,
    WORKLIST_SHA256, require_hash, require_sdk_pins,
)
from roadcraft.blender_mesh_payload import summarize_mesh  # noqa: E402


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BladePayloadError(message)


def _usf_payloads(path: Path, expected_paths: set[str]) -> tuple[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == "cat_d11t", f"USF root differs: {path.name}")
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, node_path = stack.pop()
        if node_path in expected_paths:
            _require(node_path not in found and node.mesh is not None,
                     f"USF blade mesh missing or duplicated: {node_path}")
            found[node_path] = summarize_mesh(node.mesh)
        for child in node.children:
            stack.append((child, node_path + "|" + child.name))
    _require(set(found) == expected_paths, "USF blade path coverage differs")
    del scene, root, stack
    gc.collect()
    return "cat_d11t", found


def _source_path(obj) -> str:
    _require(obj is not None and obj.type == "MESH", "source blade mesh missing")
    _require(bpy.context.scene.objects.get(obj.name) == obj and obj.visible_get(),
             f"source blade is outside visible scene: {obj.name}")
    armature = obj.parent
    _require(armature is not None and armature.type == "ARMATURE" and
             armature.name == "D11T_Rig.005" and obj.parent_type == "BONE" and
             obj.parent_bone == "BoneBlade_cdt" and armature.visible_get() and
             bpy.context.scene.collection.objects.get(armature.name) == armature,
             f"source blade parent differs: {obj.name}")
    bone = armature.pose.bones.get(obj.parent_bone)
    _require(bone is not None, f"source blade bone missing: {obj.name}")
    lineage = []
    while bone is not None:
        lineage.append(bone.name)
        bone = bone.parent
    predicted = "|@root|" + armature.name + "|" + "|".join(reversed(lineage)) + "|" + obj.name
    _require(predicted == NATIVE_PARENT + "|" + obj.name,
             f"source blade path differs: {obj.name}")
    return predicted


def run_readback(*, blend: Path, repaired: Path, native: Path,
                 worklist: Path, sdk_root: Path, worker_sha256: str,
                 host_sha256: str, blade_host_sha256: str,
                 mesh_host_sha256: str, blender_sha256: str,
                 native_sha256: str, summary_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS, "Blender pin not reviewed")
    _require(blade_host_sha256 == BLADE_HOST_SHA256 and
             mesh_host_sha256 == MESH_HOST_SHA256,
             "reviewed helper hashes differ")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "blade payload worker")
    host = Path(__file__).with_name("blender_blade_payload.py")
    require_hash(host, host_sha256, "blade payload host")
    require_hash(BLADE_HOST, BLADE_HOST_SHA256, "blade relocation host")
    require_hash(MESH_HOST, MESH_HOST_SHA256, "mesh payload host")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    require_hash(native, native_sha256, "retained native USF")
    require_hash(worklist, WORKLIST_SHA256, "reconstruction worklist")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")
    _require(not bpy.data.filepath, "Blender startup scene was already opened")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMesh

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    native_paths = {NATIVE_PARENT + "|" + leaf for leaf in LEAVES}
    repaired_paths = {REPAIRED_PARENT + "|" + leaf for leaf in LEAVES}
    try:
        native_root, native_payload = _usf_payloads(native, native_paths)
        repaired_root, repaired_payload = _usf_payloads(repaired, repaired_paths)
    finally:
        BinaryIO.read_bytearray = original_reader

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source scene frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    cache_before = len(RGBA_CACHE)
    rows = []
    for leaf in LEAVES:
        obj = bpy.data.objects.get(leaf)
        predicted = _source_path(obj)
        _require(scene_meshes.get(leaf) == obj, f"source mesh name differs: {leaf}")
        evaluated_obj = obj.evaluated_get(depsgraph)
        try:
            projected = UsfMesh().b_read(obj)
            source = summarize_mesh(projected)
        finally:
            evaluated_obj.to_mesh_clear()
        native_path = NATIVE_PARENT + "|" + leaf
        repaired_path = REPAIRED_PARENT + "|" + leaf
        fields = {
            field: {"source": source[field],
                    "native": native_payload[native_path][field],
                    "repaired": repaired_payload[repaired_path][field]}
            for field in FIELD_NAMES
        }
        rows.append({
            "leafName": leaf, "nativeExportPath": native_path,
            "repairedPath": repaired_path, "equivalenceVerified": False,
            "sourceObject": obj.name, "sourcePredictedPath": predicted,
            "sourceParentBone": obj.parent_bone, "fields": fields,
        })
        del projected, source
        if len(rows) % 10 == 0:
            gc.collect()
    cache_after = len(RGBA_CACHE)
    for path, digest, label in (
            (blend, BLEND_SHA256, "Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha256, "native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (host, host_sha256, "blade payload host"),
            (Path(__file__), worker_sha256, "blade payload worker"),
            (BLADE_HOST, BLADE_HOST_SHA256, "blade relocation host"),
            (MESH_HOST, MESH_HOST_SHA256, "mesh payload host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha256,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha256,
        "blenderSha256": blender_sha256, "hostSha256": host_sha256,
        "bladeHostSha256": BLADE_HOST_SHA256,
        "meshHostSha256": MESH_HOST_SHA256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "sourceSceneMeshCount": len(scene_meshes),
        "nativeExportRootName": native_root,
        "repairedRootName": repaired_root,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False, "sdkPackerGuarded": False,
        "cacheBeforeSourceMeshes": cache_before,
        "cacheAfterSourceMeshes": cache_after,
        "rows": rows,
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
    parser.add_argument("--blade-host-sha256", required=True)
    parser.add_argument("--mesh-host-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    parser.add_argument("--summary-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(
        blend=args.blend, repaired=args.repaired_usf, native=args.native_usf,
        worklist=args.worklist, sdk_root=args.sdk_script_root,
        worker_sha256=args.worker_sha256, host_sha256=args.host_sha256,
        blade_host_sha256=args.blade_host_sha256,
        mesh_host_sha256=args.mesh_host_sha256,
        blender_sha256=args.blender_sha256,
        native_sha256=args.native_usf_sha256,
        summary_sha256=args.summary_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
