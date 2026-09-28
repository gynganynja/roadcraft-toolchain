"""Install accepted D11 blade normals only in a live, disposable Blender scene.

This module does not save a Blend or export a USF. The authoring wrapper must
pin this module and supply the separately pinned retained native USF.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft import blender_blade_normal_projection as projection
from roadcraft.blender_blade_normal_projection_worker import (
    _project_one, _usf_blades)
from roadcraft.blender_blade_payload_worker import _source_path


PROJECTION_HOST_SHA256 = "69c839ccc693c570e4b82c32ecd39741f9d6f2786d27042d0ed2d77ece3b0e0c"
PROJECTION_WORKER_SHA256 = "5cbccc066898089906fe766a8ce2f6e040cd925257ae236674bdaeda3382b3b4"
BLADE_PAYLOAD_HOST_SHA256 = "b02a9c8de297c1673d93bc353e50f9460daafe94d316b00603fe0d2d6cec9f70"
BLADE_PAYLOAD_WORKER_SHA256 = "c6a4b4b0c0639a0b412c917e420d320ff5e0015edd915972ec393875b36d3be6"
BLADE_RELOCATION_HOST_SHA256 = "87b272b4f2b52f29488a4188a7df5c2b5e83bdd03fe70527dc036082cc39a8a0"
MESH_PAYLOAD_HOST_SHA256 = "2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e"


def dependency_pins() -> tuple[tuple[Path, str, str], ...]:
    here = Path(__file__).resolve().parent
    return (
        (here / "blender_blade_normal_projection.py", PROJECTION_HOST_SHA256,
         "normal projection host"),
        (here / "blender_blade_normal_projection_worker.py",
         PROJECTION_WORKER_SHA256, "normal projection worker"),
        (here / "blender_blade_payload.py", BLADE_PAYLOAD_HOST_SHA256,
         "blade payload host"),
        (here / "blender_blade_payload_worker.py",
         BLADE_PAYLOAD_WORKER_SHA256, "blade payload worker"),
        (here / "blender_blade_relocation.py", BLADE_RELOCATION_HOST_SHA256,
         "blade relocation host"),
        (here / "blender_mesh_payload.py", MESH_PAYLOAD_HOST_SHA256,
         "mesh payload host"),
    )


def require_dependency_pins() -> None:
    for path, digest, label in dependency_pins():
        projection.require_hash(path, digest, label)


def _source_path_with_roll(obj) -> str:
    """Require the exact repaired blade lineage in the loaded scratch scene."""
    projection._require(obj is not None and obj.type == "MESH" and
                        bpy.context.scene.objects.get(obj.name) == obj and
                        obj.visible_get(),
                        "source blade mesh is outside visible scene")
    armature = obj.parent
    projection._require(
        armature is not None and armature.type == "ARMATURE" and
        armature.name == "D11T_Rig.005" and obj.parent_type == "BONE" and
        obj.parent_bone == "BoneBlade_cdt" and armature.visible_get() and
        bpy.context.scene.collection.objects.get(armature.name) == armature,
        f"source blade parent differs: {obj.name}")
    bone = armature.pose.bones.get(obj.parent_bone)
    lineage = []
    while bone is not None:
        lineage.append(bone.name)
        bone = bone.parent
    path = "|@root|" + armature.name + "|" + "|".join(reversed(lineage)) + "|" + obj.name
    projection._require(path == projection.REPAIRED_PARENT + "|" + obj.name,
                        f"source blade-roll path differs: {obj.name}")
    return path


def install_in_memory_blade_normals(*, blend: Path, repaired: Path,
                                    native: Path, native_sha256: str,
                                    sdk_root: Path, blender_sha256: str,
                                    blade_roll_present: bool = False) -> dict:
    """Verify the 60 source meshes and keep exact normal attributes in RAM."""
    projection._require(blender_sha256 in projection.BLENDER_VERSION_PINS and
                        bpy.app.version_string.startswith(
                            projection.BLENDER_VERSION_PINS[blender_sha256]),
                        "Blender executable version differs")
    projection.require_hash(Path(bpy.app.binary_path), blender_sha256,
                            "Blender executable")
    projection.require_hash(blend, projection.BLEND_SHA256, "source Blend")
    projection.require_hash(repaired, projection.USF_SHA256,
                            "accepted repaired USF")
    projection.require_hash(native, native_sha256, "retained native USF")
    require_dependency_pins()
    sdk = projection.require_sdk_pins(sdk_root)
    projection._require(Path(bpy.data.filepath).resolve() == blend.resolve() and
                        bpy.context.scene.frame_current == 1,
                        "the pinned source Blend is not the live frame-one scene")
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    projection._require(len(scene_meshes) == 210,
                        "source scene mesh coverage differs")
    projection._require(type(blade_roll_present) is bool,
                        "blade-roll option must be boolean")

    native_blades = _usf_blades(native, projection.NATIVE_PARENT)
    repaired_blades = _usf_blades(repaired, projection.REPAIRED_PARENT)
    rows = []
    installed = []
    try:
        for leaf in projection.LEAVES:
            obj = scene_meshes.get(leaf)
            expected_parent = (projection.REPAIRED_PARENT if
                               blade_roll_present else projection.NATIVE_PARENT)
            path = (_source_path_with_roll(obj) if blade_roll_present else
                    _source_path(obj))
            projection._require(obj is not None and
                                path == expected_parent + "|" + leaf,
                                f"source blade path differs: {leaf}")
            native_row = native_blades[projection.NATIVE_PARENT + "|" + leaf]
            repaired_row = repaired_blades[projection.REPAIRED_PARENT + "|" + leaf]
            row = _project_one(obj, native_row, repaired_row)
            mesh = obj.data
            mesh.calc_loop_triangles()
            loop_ids = [int(loop_id) for triangle in mesh.loop_triangles
                        for loop_id in triangle.loops]
            projection._require(len(loop_ids) == row["cornerCount"] and
                                len(set(loop_ids)) == len(mesh.loops),
                                f"blade corner mapping changed: {leaf}")
            attribute = mesh.attributes.new(
                name="saber_normals", type="FLOAT_VECTOR", domain="CORNER")
            installed.append((mesh, attribute))
            for index, loop_id in enumerate(loop_ids):
                attribute.data[loop_id].vector = repaired_row["normals"][index]
            mesh.update()
            rows.append(row)
        projection._require(
            len(rows) == len(projection.LEAVES) and
            sum(row["triangleCount"] for row in rows) ==
            projection.EXPECTED_TRIANGLES and
            sum(row["cornerCount"] for row in rows) ==
            projection.EXPECTED_CORNERS,
            "blade normal installation coverage differs")
        projection.require_hash(blend, projection.BLEND_SHA256,
                                "source Blend after installation")
        projection.require_hash(repaired, projection.USF_SHA256,
                                "accepted repaired USF after installation")
        projection.require_hash(native, native_sha256,
                                "retained native USF after installation")
        require_dependency_pins()
        projection.require_sdk_pins(sdk)
    except Exception:
        for mesh, attribute in reversed(installed):
            if mesh.attributes.get("saber_normals") == attribute:
                mesh.attributes.remove(attribute)
                mesh.update()
        raise
    row_digest = hashlib.sha256(projection._canonical(rows)).hexdigest()
    return {
        "schemaVersion": 1,
        "status": "IN_MEMORY_BLADE_NORMALS_INSTALLED",
        "asset": "cat_d11t",
        "blendSha256": projection.BLEND_SHA256,
        "repairedUsfSha256": projection.USF_SHA256,
        "nativeUsfSha256": native_sha256,
        "blenderSha256": blender_sha256,
        "leaves": len(rows),
        "triangles": projection.EXPECTED_TRIANGLES,
        "corners": projection.EXPECTED_CORNERS,
        "rowsDigestSha256": row_digest,
        "normalAttributesInLiveScene": len(installed),
        "bladeRollPresent": blade_roll_present,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


def blade_normals_by_leaf(root, parent: str) -> dict[str, list]:
    """Read all reviewed blade normal arrays from a parsed USF tree."""
    projection._require(root.name == "cat_d11t", "USF root differs")
    found = {}
    stack = [(root, "|@root")]
    expected = {parent + "|" + leaf: leaf for leaf in projection.LEAVES}
    while stack:
        node, path = stack.pop()
        if path in expected:
            projection._require(path not in found and node.mesh is not None,
                                f"blade node missing or duplicated: {path}")
            found[path] = node.mesh.normals
        stack.extend((child, path + "|" + child.name)
                     for child in node.children)
    projection._require(set(found) == set(expected),
                        "blade path coverage differs")
    return {leaf: found[path] for path, leaf in expected.items()}
