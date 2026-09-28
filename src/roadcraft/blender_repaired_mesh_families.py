"""Reconstruct repaired-only D11 LOD mesh families in a disposable scene.

This module does not save a Blend or write a USF. Callers must pin the source
Blend, accepted USF, Blender executable and SDK before invoking it.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sys

import bpy
from mathutils import Matrix

from .blender_mesh_inventory_worker import _predicted_path


class MeshFamilyRepairError(RuntimeError):
    """The requested family cannot be represented or projected as reviewed."""


def need(ok: bool, message: str) -> None:
    if not ok:
        raise MeshFamilyRepairError(message)


def max_error(left, right) -> float:
    need(len(left) == len(right), "vector count differs")
    return max((abs(float(a) - float(b))
                for lr, rr in zip(left, right, strict=True)
                for a, b in zip(lr, rr, strict=True)), default=0.0)


def read_nodes(repaired: Path, sdk_root: Path):
    """Read the already pinned target in RAM and index its nodes by path/UID."""
    sys.path.insert(0, str(sdk_root))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read

    original = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original(self))
    try:
        _, parsed = usf_read(str(repaired))
    finally:
        BinaryIO.read_bytearray = original
    by_path = {}
    by_uid = {}
    stack = [(parsed._root_node, "|@root")]
    while stack:
        node, path = stack.pop()
        need(path not in by_path and node.uid not in by_uid,
             "duplicate target path or UID")
        by_path[path] = node
        by_uid[node.uid] = node
        stack.extend((child, path + "|" + child.name)
                     for child in node.children)
    return parsed, by_path, by_uid


@contextmanager
def reviewed_readback(*, allow_material_aliases: bool):
    """Scope packed colors and optional reviewed material-name aliases."""
    from saber.blender.lib.usf import mesh as sdk_mesh
    from saber.blender.lib.usf.mesh import UsfMeshColorSet

    original = UsfMeshColorSet.FAST_PACK
    need(original is False, "SDK packed-color mode unexpectedly enabled")
    original_material = sdk_mesh.BlenderToUsfSimpleMaterial

    class ReviewedMaterial(original_material):
        def __init__(self, material, uvset_name="UVMap"):
            super().__init__(material, uvset_name)
            if material is not None and 'roadcraft_target_name' in material:
                self.name = material['roadcraft_target_name']
                expected_sha = material.get('roadcraft_target_sha256')
                need(isinstance(expected_sha, str) and
                     hashlib.sha256(self.build_string().encode()).hexdigest()
                     == expected_sha,
                     "reviewed material alias text differs")

    UsfMeshColorSet.FAST_PACK = True
    if allow_material_aliases:
        sdk_mesh.BlenderToUsfSimpleMaterial = ReviewedMaterial
    try:
        yield
    finally:
        UsfMeshColorSet.FAST_PACK = original
        sdk_mesh.BlenderToUsfSimpleMaterial = original_material


def material_from_target(target_material, *, allow_aliases: bool):
    """Author only materials exactly representable by the reviewed SDK."""
    from saber.blender.lib.usf import mesh as sdk_mesh
    projector = sdk_mesh.BlenderToUsfSimpleMaterial

    text = target_material.build_string()
    name_match = re.search(r'material = \{\s*name = "([^"]+)"', text)
    tint_match = re.search(r'albedo_tint = \[([^\]]+)\]', text)
    need(name_match is not None and tint_match is not None,
         "target material does not match the simple template")
    name = name_match.group(1)
    texture_names = [item for item in
                     re.findall(r'textureName = "([^"]+)"', text) if item]
    tint = [int(item.strip()) for item in tint_match.group(1).split(',')]
    need(len(tint) == 4 and all(0 <= item <= 255 for item in tint),
         "material tint differs")
    existing = bpy.data.materials.get(name)
    if existing is not None:
        if projector(existing).build_string() == text:
            return existing
        need(allow_aliases, "same-name material text collision: " + name)
        material_name = name + '__rc_' + hashlib.sha256(text.encode()).hexdigest()[:12]
        alias = bpy.data.materials.get(material_name)
        if alias is not None:
            need(alias.get('roadcraft_target_name') == name and
                 projector(alias).build_string() == text,
                 "reviewed material alias collision")
            return alias
    else:
        material_name = name
    material = bpy.data.materials.new(material_name)
    if material_name != name:
        material['roadcraft_target_name'] = name
        material['roadcraft_target_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    need(bsdf is not None, "Principled material node missing")
    bsdf.inputs['Base Color'].default_value = tuple(
        item / 255 for item in (tint[1], tint[2], tint[3], tint[0]))
    for texture_name in texture_names:
        texture = material.node_tree.nodes.new('ShaderNodeTexImage')
        texture.image = (bpy.data.images.get(texture_name) or
                         bpy.data.images.new(texture_name, width=1, height=1))
    need(projector(material).build_string() == text,
         "authored material text differs: " + name)
    return material


def family_targets(families: tuple[str, ...]) -> list[tuple[str, str]]:
    result = []
    for family in families:
        need(re.fullmatch(r'[A-Za-z0-9_]+_vis', family) is not None,
             "family name is not a reviewed mesh name")
        base = "|@root|D11T_Rig.005|" + family
        result.extend(((base, family + "_LOD0"),
                       (base + "|" + family + "_LOD1", family + "_LOD1"),
                       (base + "|" + family + "_LOD2", family + "_LOD2")))
    need(len(result) == len(set(result)), "duplicate family target")
    return result


def reconstruct_families(*, repaired: Path, sdk_root: Path, arm,
                         families: tuple[str, ...],
                         allowed_paths: set[str],
                         allow_material_aliases: bool = False) -> dict:
    """Add whole flat-LOD families, then compare SDK projections in memory."""
    sys.path.insert(0, str(sdk_root))
    from saber.blender.lib.usf.mesh import UsfMesh
    from saber.blender.lib.usf.transform import FROM_SABER_CONVERT

    need(arm is not None and arm.name == "D11T_Rig.005" and
         arm.type == "ARMATURE" and len(arm.pose.bones) == 399,
         "live reconstructed rig differs")
    pairs = family_targets(families)
    need(set(path for path, _ in pairs) <= allowed_paths,
         "family not in pinned repaired-only worklist")
    parsed, by_path, by_uid = read_nodes(repaired, sdk_root)
    new_objects = []
    with reviewed_readback(allow_material_aliases=allow_material_aliases):
        for path, name in pairs:
            target = by_path.get(path)
            need(target is not None and target.mesh is not None and
                 bpy.data.objects.get(name) is None,
                 "target mesh or Blender name differs: " + path)
            mesh = target.mesh
            identity = Matrix.Identity(4)
            need(len(mesh.skin.skin) == len(mesh.vertices) ==
                 len(mesh.faces) * 3 and
                 len(mesh.uvsets.uvs) == 1 and
                 len(mesh.colorsets.sets) <= 1 and
                 1 <= len(mesh.skin.skin_bones) <= 399 and
                 max_error(target.matrix_world, identity) <= 1e-7 and
                 max_error(target.matrix_local, identity) <= 1e-7,
                 "target mesh shape or transform differs: " + path)
            loaded = mesh.load("reviewed_" + name)
            obj = bpy.data.objects.new(name, loaded)
            bpy.context.scene.collection.objects.link(obj)
            obj.parent = arm
            obj.matrix_world = identity
            loaded.transform(FROM_SABER_CONVERT)
            for layer in loaded.uv_layers:
                for loop_index in range(len(loaded.loops)):
                    uv = layer.uv[loop_index].vector
                    uv[1] = 1.0 - uv[1]
            loaded.materials.clear()
            for material in mesh.materials.data:
                loaded.materials.append(material_from_target(
                    material, allow_aliases=allow_material_aliases))
            for index, polygon in enumerate(loaded.polygons):
                polygon.material_index = mesh.faces[index].material_index
            skin_names = [by_uid[item.usf_node_uid].name
                          for item in mesh.skin.skin_bones]
            need(len(skin_names) == len(set(skin_names)) and
                 set(skin_names) <= set(arm.pose.bones.keys()),
                 "skin bone identities differ: " + path)
            for index, entry in enumerate(mesh.skin.skin):
                for bone_idx, weight in zip(entry.bone_idx, entry.weight):
                    if weight:
                        group_name = skin_names[bone_idx]
                        group = (obj.vertex_groups.get(group_name) or
                                 obj.vertex_groups.new(name=group_name))
                        group.add([index], weight, 'REPLACE')
            modifier = obj.modifiers.new('reviewed_skin', 'ARMATURE')
            modifier.object = arm
            modifier.show_viewport = False
            loaded.update()
            new_objects.append((path, obj, mesh, skin_names))

        bpy.context.view_layer.update()
        rows = []
        for path, obj, target, skin_names in new_objects:
            projected = UsfMesh().b_read(obj)
            projected_names = [item.name for item in
                               projected.skin.skin_bones]
            by_name = {name: index for index, name in
                       enumerate(skin_names)}
            normalized = [
                (tuple(by_name[projected_names[index]] if weight else 0
                       for index, weight in zip(entry.bone_idx, entry.weight)),
                 tuple(entry.weight))
                for entry in projected.skin.skin]
            expected = [(tuple(entry.bone_idx), tuple(entry.weight))
                        for entry in target.skin.skin]
            active_actual = [[(index, weight) for index, weight in
                              zip(indices, weights) if weight]
                             for indices, weights in normalized]
            active_expected = [[(index, weight) for index, weight in
                                zip(indices, weights) if weight]
                               for indices, weights in expected]
            target_colors = [item.colors for item in target.colorsets.sets]
            projected_colors = [item.colors for item in
                                projected.colorsets.sets]
            row = {
                "path": path, "predictedPath": _predicted_path(obj),
                "faces": len(target.faces),
                "corners": len(target.vertices),
                "positionMaxError": max_error(target.vertices,
                                              projected.vertices),
                "normalMaxError": max_error(target.normals,
                                            projected.normals),
                "uvMaxError": max_error(target.uvsets.uvs[0].co,
                                        projected.uvsets.uvs[0].co),
                "tangentMaxError": max_error(
                    target.uvsets.tangents[0],
                    projected.uvsets.tangents[0]),
                "facePairsEqual": [
                    (item.material_index, item.edge_index)
                    for item in target.faces] == [
                    (item.material_index, item.edge_index)
                    for item in projected.faces],
                "materialTextEqual": [item.build_string() for item in
                                      target.materials.data] == [
                                      item.build_string() for item in
                                      projected.materials.data],
                "materialMetaEqual": [(item.ver, item.vc_usage) for item in
                                      target.materials.data] == [
                                      (item.ver, item.vc_usage) for item in
                                      projected.materials.data],
                "colorsExact": target_colors == projected_colors,
                "colorSetCount": len(target_colors),
                "activeSkinExact": active_actual == active_expected,
                "skinFullExact": normalized == expected,
                "skinFullMismatchCorners": sum(
                    actual != target_row for actual, target_row in
                    zip(normalized, expected, strict=True)),
                "targetSkinBones": len(skin_names),
                "projectedSkinBones": len(projected_names),
            }
            need(row['predictedPath'] == path and
                 row['positionMaxError'] == 0 and
                 row['normalMaxError'] == 0 and
                 row['uvMaxError'] == 0 and
                 row['facePairsEqual'] and
                 row['materialTextEqual'] and
                 row['materialMetaEqual'] and
                 row['colorsExact'] and
                 row['activeSkinExact'] and
                 row['projectedSkinBones'] == 399,
                 "SDK family payload differs: " + json.dumps(row))
            rows.append(row)
    need(len(rows) == len(pairs), "family path coverage differs")
    return {"status": "IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS",
            "families": list(families), "rows": rows,
            "materialAliases": sorted({material.name
                                       for _, obj, _, _ in new_objects
                                       for material in obj.data.materials
                                       if material is not None and
                                       'roadcraft_target_name' in material}),
            "sceneMeshCount": sum(obj.type == 'MESH' for obj in
                                  bpy.context.scene.objects),
            "blendSaved": False, "usfExported": False}
