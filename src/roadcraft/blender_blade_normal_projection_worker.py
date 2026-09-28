"""No-save Blender worker: project accepted USF blade normals in memory."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_blade_normal_projection import (  # noqa: E402
    BLADE_HOST, BLADE_HOST_SHA256, BLEND_SHA256, BLENDER_VERSION_PINS,
    EXPECTED_CORNERS, EXPECTED_TRIANGLES, FIELD_NAMES, LEAVES, MESH_HOST,
    MESH_HOST_SHA256, NATIVE_PARENT, REPAIRED_PARENT, RESULT_PREFIX,
    SOURCE_WORKER, SOURCE_WORKER_SHA256, USF_SHA256, WORKLIST_SHA256,
    NormalProjectionError, _canonical, _require, require_hash,
    require_sdk_pins,
)
from roadcraft.blender_blade_payload_worker import _source_path  # noqa: E402
from roadcraft.blender_mesh_payload import summarize_mesh  # noqa: E402


def _usf_blades(path: Path, parent: str) -> dict[str, dict]:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == "cat_d11t", f"USF root differs: {path.name}")
    target = {parent + "|" + leaf: leaf for leaf in LEAVES}
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, node_path = stack.pop()
        if node_path in target:
            _require(node_path not in found and node.mesh is not None,
                     f"blade mesh missing or duplicated: {node_path}")
            mesh = node.mesh
            found[node_path] = {
                "vertices": mesh.vertices,
                "normals": mesh.normals,
                "summary": summarize_mesh(mesh),
            }
        for child in node.children:
            stack.append((child, node_path + "|" + child.name))
    _require(set(found) == set(target),
             f"USF exact-path coverage differs: {path.name}")
    del scene, root, stack
    gc.collect()
    return found


def _project_one(obj, native: dict, repaired: dict) -> dict:
    from saber.blender.lib.usf.mesh import UsfMesh

    mesh = obj.data
    _require(mesh.users == 1 and mesh.shape_keys is None,
             f"blade source mesh is shared or shaped: {obj.name}")
    _require("saber_normals" not in mesh.attributes and
             "custom_normal" not in mesh.attributes and
             not mesh.has_custom_normals,
             f"blade source already has custom normals: {obj.name}")
    mesh.calc_loop_triangles()
    triangles = list(mesh.loop_triangles)
    corner_count = len(repaired["normals"])
    _require(len(triangles) == len(mesh.polygons) and
             all(len(poly.vertices) == 3 for poly in mesh.polygons) and
             len(triangles) * 3 == len(mesh.loops) == corner_count and
             len(native["normals"]) == corner_count,
             f"blade triangle/corner mapping differs: {obj.name}")
    loop_ids = [int(loop_id) for triangle in triangles
                for loop_id in triangle.loops]
    _require(len(set(loop_ids)) == len(loop_ids) == corner_count and
             set(loop_ids) == set(range(len(mesh.loops))),
             f"blade loop mapping is not one-to-one: {obj.name}")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    try:
        baseline = summarize_mesh(UsfMesh().b_read(obj))
    finally:
        evaluated.to_mesh_clear()
    _require(baseline == native["summary"],
             f"source/native SDK payload differs: {obj.name}")

    attribute = mesh.attributes.new(
        name="saber_normals", type="FLOAT_VECTOR", domain="CORNER")
    try:
        for index, loop_id in enumerate(loop_ids):
            attribute.data[loop_id].vector = repaired["normals"][index]
        mesh.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        try:
            projected_mesh = UsfMesh().b_read(obj)
            projected = summarize_mesh(projected_mesh)
            exact_normals = projected_mesh.normals == repaired["normals"]
        finally:
            evaluated.to_mesh_clear()
    finally:
        mesh.attributes.remove(attribute)
        mesh.update()
    _require("saber_normals" not in mesh.attributes,
             f"blade in-memory attribute was not removed: {obj.name}")
    _require(exact_normals and
             projected["normals"] == repaired["summary"]["normals"],
             f"projected/accepted normal array differs: {obj.name}")
    other_fields = [field for field in FIELD_NAMES if field != "normals"]
    _require(all(projected[field] == baseline[field] == native["summary"][field]
                 for field in other_fields),
             f"projected non-normal payload changed: {obj.name}")
    return {
        "leafName": obj.name,
        "nativePath": NATIVE_PARENT + "|" + obj.name,
        "repairedPath": REPAIRED_PARENT + "|" + obj.name,
        "triangleCount": len(triangles),
        "cornerCount": corner_count,
        "sourceHadCustomNormals": False,
        "projectedNormalsExactRepaired": True,
        "baselineFieldsExactNative": {
            field: baseline[field] == native["summary"][field]
            for field in FIELD_NAMES},
        "projectedOtherFieldsUnchanged": {
            field: projected[field] == baseline[field]
            for field in other_fields},
        "baselineNormalSha256": baseline["normals"]["sha256"],
        "repairedNormalSha256": repaired["summary"]["normals"]["sha256"],
        "projectedNormalSha256": projected["normals"]["sha256"],
        "baselineOtherFieldsSha256": hashlib.sha256(_canonical(
            {field: baseline[field] for field in other_fields})).hexdigest(),
        "projectedOtherFieldsSha256": hashlib.sha256(_canonical(
            {field: projected[field] for field in other_fields})).hexdigest(),
    }


def run(*, blend: Path, native: Path, repaired: Path, worklist: Path,
        sdk_root: Path, blender_sha: str, worker_sha: str, host_sha: str,
        native_sha: str) -> dict:
    _require(blender_sha in BLENDER_VERSION_PINS and
             bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha]),
             "Blender executable version differs")
    _require(not bpy.data.filepath, "startup scene must not load a Blend")
    pins = (
        (Path(bpy.app.binary_path), blender_sha, "Blender executable"),
        (Path(__file__), worker_sha, "projection worker"),
        (Path(__file__).with_name("blender_blade_normal_projection.py"),
         host_sha, "projection host"),
        (blend, BLEND_SHA256, "source Blend"),
        (native, native_sha, "retained native USF"),
        (repaired, USF_SHA256, "accepted repaired USF"),
        (worklist, WORKLIST_SHA256, "reconstruction worklist"),
        (BLADE_HOST, BLADE_HOST_SHA256, "blade mapping host"),
        (MESH_HOST, MESH_HOST_SHA256, "mesh digest host"),
        (SOURCE_WORKER, SOURCE_WORKER_SHA256, "source mapping worker"),
    )
    for path, digest, label in pins:
        require_hash(path, digest, label)
    sdk = require_sdk_pins(sdk_root)
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO

    old_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else old_reader(self))
    try:
        native_blades = _usf_blades(native, NATIVE_PARENT)
        repaired_blades = _usf_blades(repaired, REPAIRED_PARENT)
    finally:
        BinaryIO.read_bytearray = old_reader

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    _require(bpy.context.scene.frame_current == 1, "source frame differs")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    _require(len(scene_meshes) == 210, "source scene mesh count differs")
    rows = []
    for leaf in LEAVES:
        obj = bpy.data.objects.get(leaf)
        _require(obj is not None and scene_meshes.get(leaf) == obj and
                 _source_path(obj) == NATIVE_PARENT + "|" + leaf,
                 f"source blade exact path differs: {leaf}")
        rows.append(_project_one(
            obj, native_blades[NATIVE_PARENT + "|" + leaf],
            repaired_blades[REPAIRED_PARENT + "|" + leaf]))
        if len(rows) % 10 == 0:
            gc.collect()
    _require(sum(row["triangleCount"] for row in rows) == EXPECTED_TRIANGLES and
             sum(row["cornerCount"] for row in rows) == EXPECTED_CORNERS,
             "blade triangle/corner total differs")
    for path, digest, label in pins:
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "status": "IN_MEMORY_NORMAL_PROJECTION",
        "blendSha256": BLEND_SHA256,
        "nativeUsfSha256": native_sha,
        "repairedUsfSha256": USF_SHA256,
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "blenderVersion": bpy.app.version_string,
        "workerSha256": worker_sha,
        "hostSha256": host_sha,
        "sourceWorkerSha256": SOURCE_WORKER_SHA256,
        "bladeHostSha256": BLADE_HOST_SHA256,
        "meshHostSha256": MESH_HOST_SHA256,
        "sceneFrame": 1,
        "sourceSceneMeshCount": len(scene_meshes),
        "normalInputSpace": "saber",
        "leaves": len(rows),
        "triangles": EXPECTED_TRIANGLES,
        "corners": EXPECTED_CORNERS,
        "sourceUnchanged": True,
        "sdkUnchanged": True,
        "nativeUsfUnchanged": True,
        "repairedUsfUnchanged": True,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
        "equivalenceVerified": False,
        "rows": rows,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--worklist", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    args = parser.parse_args(argv)
    result = run(
        blend=args.blend, native=args.native_usf,
        repaired=args.repaired_usf, worklist=args.worklist,
        sdk_root=args.sdk_script_root, blender_sha=args.blender_sha256,
        worker_sha=args.worker_sha256, host_sha=args.host_sha256,
        native_sha=args.native_usf_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True, allow_nan=False),
          flush=True)


if __name__ == "__main__":
    main()
