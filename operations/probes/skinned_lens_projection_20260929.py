"""Pinned, no-save SDK projection of one repaired-only skinned D11 lens LOD."""

import hashlib
import json
import re
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from roadcraft.blender_residual_bones import WORKER_SHA256, validate_result
from roadcraft.blender_residual_bones_worker import run as structural_run
from roadcraft.blender_left_push_probe import require_hash, require_sdk_pins

BLEND_SHA = '1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731'
USF_SHA = '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170'
INVENTORY_SHA = '03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d'
BLENDER_SHA = 'e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7'

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

inventory_path = ROOT / 'operations/d11_authoring_inventory.json'
require_hash(inventory_path, INVENTORY_SHA, 'accepted inventory')
inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
asset = next(row for row in inventory['assets'] if row['asset'] == 'cat_d11t')
source_root = Path(inventory['sourceRoot'])
blend = source_root / next(row['path'] for row in asset['files'] if row['role'] == 'blend-reference')
usf = source_root / next(row['path'] for row in asset['files'] if row['role'] == 'build-usf')
sdk = require_sdk_pins(Path(r'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'))
require_hash(blend, BLEND_SHA, 'source Blend')
require_hash(usf, USF_SHA, 'repaired USF')
require_hash(Path(bpy.app.binary_path), BLENDER_SHA, 'Blender executable')
need(bpy.app.version_string.startswith('5.2.0'), 'Blender version differs')
structural = structural_run(blend=blend, usf=usf, sdk_root=sdk, worker_sha256=WORKER_SHA256, blender_sha256=BLENDER_SHA)
validate_result(structural, BLENDER_SHA)
need(structural['status'] == 'IN_MEMORY_STRUCTURAL_MATCH', 'structural repair differs')
arm = bpy.context.scene.objects['D11T_Rig.005']
need(len(arm.pose.bones) == 399 and
     sum(obj.type == 'MESH' for obj in bpy.context.scene.objects) == 210,
     'live rig or mesh count differs')
sys.path.insert(0, str(sdk))
from saber.blender.lib.binary_io import BinaryIO
from saber.blender.lib.usf.scene import usf_read
from saber.blender.lib.usf.transform import convert_to_saber_transform
from saber.blender.lib.usf.transform import FROM_SABER_CONVERT
from saber.blender.lib.usf.mesh import UsfMesh
from mathutils import Matrix

reader = BinaryIO.read_bytearray
BinaryIO.read_bytearray = lambda self, size=None: self.io.read(size) if size is not None else reader(self)
try:
    _, parsed = usf_read(str(usf))
finally:
    BinaryIO.read_bytearray = reader
nodes = {}
stack = [(parsed._root_node, '|@root')]
while stack:
    node, path = stack.pop()
    nodes[node.uid] = (path, node)
    stack.extend((child, path + '|' + child.name) for child in node.children)
path = '|@root|D11T_Rig.005|d11t_lenses_front_on_vis|d11t_lenses_front_on_vis_LOD2'
target = next(node for node_path, node in nodes.values() if node_path == path)
need(target.mesh is not None and len(target.mesh.faces) == 16 and
     len(target.mesh.vertices) == 48 and
     len(target.mesh.skin.skin) == 48 and
     len(target.mesh.skin.skin_bones) == 381 and
     len(target.mesh.materials.data) == 2 and
     len(target.mesh.uvsets.uvs) == 1 and
     not target.mesh.colorsets.sets,
     'repaired lens target shape differs')
skin_names = [nodes[b.usf_node_uid][1].name for b in target.mesh.skin.skin_bones]
need(len(set(skin_names)) == 381 and
     set(skin_names) <= set(arm.pose.bones.keys()),
     'skin bone references differ')
pose_names = [b.name for b in arm.pose.bones]
skin_set = set(skin_names)
filtered_pose_names = [name for name in pose_names if name in skin_set]
bind_errors = []
for item in target.mesh.skin.skin_bones:
    name = nodes[item.usf_node_uid][1].name
    live = convert_to_saber_transform(arm.matrix_world @ arm.pose.bones[name].matrix).inverted()
    bind_errors.append(max(abs(float(item.inv_bind_matr[r][c]) - float(live[r][c])) for r in range(4) for c in range(4)))
structure_result = {
    'armBones': len(pose_names), 'skinBones': len(skin_names),
    'sameOrder': pose_names == skin_names,
    'filteredPoseSameOrder': filtered_pose_names == skin_names,
    'filteredPoseMismatches': [(i,a,b) for i,(a,b) in enumerate(zip(filtered_pose_names,skin_names)) if a != b][:25],
    'maxBindError': max(bind_errors),
    'bindsWithin1e5': sum(x <= 1e-5 for x in bind_errors),
    'badBindNames': [(skin_names[i], value) for i,value in enumerate(bind_errors) if value > 1e-5],
    'usedSkinBonePaths': [nodes[target.mesh.skin.skin_bones[i].usf_node_uid][0] for i in (48,50)],
    'firstMismatches': [(i,a,b) for i,(a,b) in enumerate(zip(pose_names,skin_names)) if a != b][:20],
    'skinNotPose': sorted(set(skin_names)-set(pose_names)),
    'poseNotSkin': sorted(set(pose_names)-set(skin_names))[:30],
    'targetMaterialSha256': [hashlib.sha256(m.build_string().encode()).hexdigest() for m in target.mesh.materials.data],
    'sourceLensObjects': [x.name for x in bpy.context.scene.objects if 'lenses_front_on' in x.name],
}
need(structure_result['skinNotPose'] == [] and
     structure_result['sourceLensObjects'] == [] and
     structure_result['bindsWithin1e5'] == 380 and
     [row[0] for row in structure_result['badBindNames']] == ['d11t_beacon'],
     'source/target bind relation differs')
print('SKINNED_LENS_STRUCTURE ' + json.dumps(structure_result, sort_keys=True), flush=True)

loaded = target.mesh.load('reviewed_lens_mesh')
obj = bpy.data.objects.new('reviewed_lens_LOD2', loaded)
bpy.context.scene.collection.objects.link(obj)
obj.parent = arm
obj.matrix_world = Matrix.Identity(4)
loaded.transform(FROM_SABER_CONVERT)
for layer in loaded.uv_layers:
    for loop in range(len(loaded.loops)):
        uv = layer.uv[loop].vector
        uv[1] = 1.0 - uv[1]
loaded.materials.clear()
from saber.blender.lib.usf.material import BlenderToUsfSimpleMaterial
material_sources = []
for item in target.mesh.materials.data:
    text = item.build_string()
    name = re.search(r'material = \{\s*name = "([^"]+)"', text).group(1)
    texture_name = next(x for x in re.findall(r'textureName = "([^"]+)"', text) if x)
    candidate = bpy.data.materials.get(name)
    if candidate is not None and BlenderToUsfSimpleMaterial(candidate).build_string() == text:
        material_sources.append('existing')
    else:
        candidate = bpy.data.materials.new(name if candidate is None else 'reviewed_'+name)
        candidate.use_nodes = True
        bsdf = candidate.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
        texture = candidate.node_tree.nodes.new('ShaderNodeTexImage')
        image = bpy.data.images.get(texture_name) or bpy.data.images.new(texture_name, width=1, height=1)
        texture.image = image
        material_sources.append('constructed')
    loaded.materials.append(candidate)
for i, poly in enumerate(loaded.polygons):
    poly.material_index = target.mesh.faces[i].material_index
for i, entry in enumerate(target.mesh.skin.skin):
    active = [(idx,weight) for idx,weight in zip(entry.bone_idx, entry.weight) if weight]
    if len(active) != 1 or active[0][1] != 1.0:
        raise RuntimeError('unexpected lens skin entry')
    name = skin_names[active[0][0]]
    group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
    group.add([i], 1.0, 'REPLACE')
modifier = obj.modifiers.new('reviewed_lens_skin', 'ARMATURE')
modifier.object = arm
modifier.show_viewport = False
loaded.update()
bpy.context.view_layer.update()
projected = UsfMesh().b_read(obj)
def field_error(a,b):
    return max((abs(float(x)-float(y)) for ar,br in zip(a,b) for x,y in zip(ar,br)), default=0.0)
projected_names = [b.name for b in projected.skin.skin_bones]
target_by_name = {name:i for i,name in enumerate(skin_names)}
normal_skin = []
for entry in projected.skin.skin:
    normal_skin.append((tuple(target_by_name[projected_names[i]] if w else 0 for i,w in zip(entry.bone_idx,entry.weight)), tuple(entry.weight)))
expected_skin = [(tuple(x.bone_idx), tuple(x.weight)) for x in target.mesh.skin.skin]
projection_result = {
    'objectLocalMatrix': [[float(v) for v in row] for row in obj.matrix_local],
    'faces': len(projected.faces),
    'positionError': field_error(target.mesh.vertices,projected.vertices),
    'normalError': field_error(target.mesh.normals,projected.normals),
    'uvError': field_error(target.mesh.uvsets.uvs[0].co,projected.uvsets.uvs[0].co),
    'tangentError': field_error(target.mesh.uvsets.tangents[0],projected.uvsets.tangents[0]),
    'facePairsEqual': [(f.material_index,f.edge_index) for f in target.mesh.faces] == [(f.material_index,f.edge_index) for f in projected.faces],
    'skinEntries': len(projected.skin.skin),
    'skinBones': len(projected_names),
    'skinRemappedExact': normal_skin == expected_skin,
    'skinFirstMismatch': next(((i,a,b) for i,(a,b) in enumerate(zip(normal_skin,expected_skin)) if a != b),None),
    'materialTextEqual': [m.build_string() for m in target.mesh.materials.data] == [m.build_string() for m in projected.materials.data],
    'materialSources': material_sources,
    'projectedMaterialNames': [m.name for m in projected.materials.data],
}
need(projection_result['faces'] == 16 and
     projection_result['skinEntries'] == 48 and
     projection_result['skinBones'] == 399 and
     projection_result['positionError'] == 0 and
     projection_result['normalError'] == 0 and
     projection_result['uvError'] == 0 and
     projection_result['facePairsEqual'] and
     projection_result['skinRemappedExact'] and
     projection_result['materialTextEqual'] and
     projection_result['tangentError'] <= 0.0002,
     'SDK lens projection differs')
require_hash(blend, BLEND_SHA, 'source Blend after projection')
require_hash(usf, USF_SHA, 'repaired USF after projection')
require_sdk_pins(sdk)
print('SKINNED_LENS_PROJECTION ' + json.dumps({
    'status': 'IN_MEMORY_SKINNED_LENS_PAYLOAD_MATCH_WITH_GAPS',
    'structure': {k: structure_result[k] for k in
                  ('armBones', 'skinBones', 'filteredPoseSameOrder',
                   'bindsWithin1e5', 'badBindNames', 'usedSkinBonePaths',
                   'targetMaterialSha256')},
    'projection': projection_result,
    'blendSaved': False, 'usfExported': False,
    'nativeBlendExportApproved': False,
}, sort_keys=True), flush=True)
