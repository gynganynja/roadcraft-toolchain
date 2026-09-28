"""Pinned, no-save reconstruction of the unskinned D11 blade-roll pivot mesh.

Call only in a disposable Blender process after the reviewed blade-roll bone
has been reconstructed. This module never saves a Blend or exports a USF.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import bpy

from .blender_left_push_probe import require_hash, require_sdk_pins
from .blender_push_branches_worker import unique_node


BLEND_SHA256 = "1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731"
USF_SHA256 = "49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170"
BLENDER_SHA256 = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
MATERIAL_SHA256 = "61c091034b813dd12ffa0973c5dda7555281a1b83e4868f7b2b7d00879e7c42c"
ARMATURE = "D11T_Rig.005"
ROLL = "BoneBladeRoll_cdt"
PIVOT = "cdt_blade_roll_pivot"
COMPONENTS = ("@root", ARMATURE, "BoneChassis_cdt", "BoneBladeLift_cdt", ROLL, PIVOT)
PATH = "|".join(("",) + COMPONENTS)
TOLERANCE = 1e-5
TANGENT_TOLERANCE = 1e-7


class PivotRepairError(RuntimeError):
    """The narrowly reviewed pivot target or its live projection differs."""


def need(condition: bool, message: str) -> None:
    if not condition:
        raise PivotRepairError(message)


def matrix_error(left, right) -> float:
    return max(abs(float(a) - float(b))
               for left_row, right_row in zip(left, right, strict=True)
               for a, b in zip(left_row, right_row, strict=True))


def vector_error(left, right) -> tuple[int, float]:
    need(len(left) == len(right), "vector count differs")
    exact = sum(tuple(a) == tuple(b) for a, b in zip(left, right, strict=True))
    error = max((abs(float(a) - float(b))
                 for left_row, right_row in zip(left, right, strict=True)
                 for a, b in zip(left_row, right_row, strict=True)), default=0.0)
    return exact, error


def install_in_memory_pivot(*, blend: Path, repaired: Path,
                            sdk_root: Path, blender_sha256: str) -> dict:
    """Add the repaired pivot to the live rig and verify its SDK readback."""
    need(blender_sha256 == BLENDER_SHA256 and
         bpy.app.version_string.startswith("5.2.0"),
         "Blender version or executable pin differs")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "accepted repaired USF")
    sdk = require_sdk_pins(sdk_root)
    need(Path(bpy.data.filepath).resolve() == blend.resolve() and
         bpy.context.scene.frame_current == 1,
         "live scene is not the pinned frame-one Blend")
    arm = bpy.context.scene.objects.get(ARMATURE)
    need(arm is not None and arm.type == "ARMATURE" and
         arm.pose.bones.get(ROLL) is not None and
         bpy.context.scene.objects.get(PIVOT) is None and
         sum(obj.type == "MESH" for obj in bpy.context.scene.objects) == 210,
         "source rig, pivot absence or mesh count differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.mesh import UsfMesh
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf.transform import (
        FROM_SABER_CONVERT, TO_SABER_CONVERT, convert_to_saber_transform)

    reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else reader(self))
    try:
        _, parsed = usf_read(str(repaired))
    finally:
        BinaryIO.read_bytearray = reader
    node = unique_node(parsed._root_node, COMPONENTS)
    target = node.mesh
    need(target is not None and node.anim is None and not node.children and
         len(target.faces) == 12 and len(target.vertices) == 36 and
         len(target.normals) == 36 and len(target.uvsets.uvs) == 1 and
         len(target.colorsets.sets) == 0 and
         len(target.skin.skin) == len(target.skin.skin_bones) == 0 and
         len(target.materials.data) == 1 and
         all(face.material_index == 0 for face in target.faces),
         "repaired pivot payload shape differs")
    material_text = target.materials.data[0].build_string()
    need(hashlib.sha256(material_text.encode()).hexdigest() == MATERIAL_SHA256,
         "repaired pivot material differs")

    loaded = target.load("reviewed_pivot_mesh")
    obj = bpy.data.objects.new(PIVOT, loaded)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = ROLL
    obj.matrix_world = FROM_SABER_CONVERT @ node.matrix_world @ TO_SABER_CONVERT
    bpy.context.view_layer.update()
    world_error = matrix_error(
        convert_to_saber_transform(obj.matrix_world), node.matrix_world)
    roll_saber = convert_to_saber_transform(
        arm.matrix_world @ arm.pose.bones[ROLL].matrix)
    local_error = matrix_error(
        roll_saber.inverted() @ convert_to_saber_transform(obj.matrix_world),
        node.matrix_local)
    need(world_error <= TOLERANCE and local_error <= TOLERANCE,
         "pivot world or local matrix differs")

    loaded.transform(FROM_SABER_CONVERT)
    for layer in loaded.uv_layers:
        for loop_index in range(len(loaded.loops)):
            uv = layer.uv[loop_index].vector
            uv[1] = 1.0 - uv[1]
    loaded.materials.clear()  # The reviewed target is the SDK's no-material default.
    loaded.update()

    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    try:
        projected = UsfMesh().b_read(obj)
        position_exact, position_error = vector_error(
            target.vertices, projected.vertices)
        normal_exact, normal_error = vector_error(
            target.normals, projected.normals)
        uv_exact, uv_error = vector_error(
            target.uvsets.uvs[0].co, projected.uvsets.uvs[0].co)
        tangent_exact, tangent_error = vector_error(
            target.uvsets.tangents[0], projected.uvsets.tangents[0])
        material_projected = projected.materials.data[0].build_string()
        need(len(projected.faces) == 12 and
             [(face.material_index, face.edge_index)
              for face in projected.faces] ==
             [(face.material_index, face.edge_index)
              for face in target.faces] and
             len(projected.uvsets.uvs) == 1 and
             projected.uvsets.uvs[0].name == target.uvsets.uvs[0].name and
             len(projected.colorsets.sets) == 0 and
             len(projected.skin.skin) == 0 and
             len(projected.skin.skin_bones) == 0 and
             projected.materials.data[0].ver == target.materials.data[0].ver and
             projected.materials.data[0].vc_usage ==
             target.materials.data[0].vc_usage and
             material_projected == material_text and
             position_exact == normal_exact == uv_exact == 36 and
             position_error == normal_error == uv_error == 0 and
             tangent_error <= TANGENT_TOLERANCE,
             "pivot SDK mesh readback differs")
    finally:
        evaluated.to_mesh_clear()

    require_hash(blend, BLEND_SHA256, "source Blend after pivot reconstruction")
    require_hash(repaired, USF_SHA256,
                 "accepted repaired USF after pivot reconstruction")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1,
        "status": "IN_MEMORY_PIVOT_MESH_MATCH",
        "asset": "cat_d11t", "path": PATH,
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "blenderSha256": BLENDER_SHA256,
        "sourceMeshCountAfter": 211,
        "faces": 12, "corners": 36,
        "positionsExact": position_exact,
        "normalsExact": normal_exact,
        "uvsExact": uv_exact,
        "tangentsExact": tangent_exact,
        "tangentMaxError": tangent_error,
        "materialTextSha256": MATERIAL_SHA256,
        "worldMatrixMaxError": world_error,
        "localMatrixMaxError": local_error,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
