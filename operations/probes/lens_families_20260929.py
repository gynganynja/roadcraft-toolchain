"""No-save reconstruction of five three-level D11 lens families."""

import json
from pathlib import Path
import re
import sys

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from roadcraft.blender_left_push_probe import require_hash, require_sdk_pins
from roadcraft.blender_mesh_inventory_worker import _predicted_path
from roadcraft.blender_residual_bones import WORKER_SHA256, validate_result
from roadcraft.blender_residual_bones_worker import run as structural_run

inventory_path = ROOT / 'operations/d11_authoring_inventory.json'
require_hash(inventory_path, '03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d', 'inventory')
worklist_path = ROOT / 'operations/d11_blender_reconstruction_worklist_20260928.json'
require_hash(worklist_path, 'a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3', 'worklist')
inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
asset = next(x for x in inventory['assets'] if x['asset'] == 'cat_d11t')
source_root = Path(inventory['sourceRoot'])
blend = source_root / next(x['path'] for x in asset['files'] if x['role'] == 'blend-reference')
usf = source_root / next(x['path'] for x in asset['files'] if x['role'] == 'build-usf')
blender_sha = 'e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7'
require_hash(blend, '1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731', 'Blend')
require_hash(usf, '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170', 'USF')
require_hash(Path(bpy.app.binary_path), blender_sha, 'Blender')
if not bpy.app.version_string.startswith('5.2.0'):
    raise RuntimeError('Blender version differs')
sdk = require_sdk_pins(Path(r'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'))
structural = structural_run(blend=blend, usf=usf, sdk_root=sdk,
                            worker_sha256=WORKER_SHA256, blender_sha256=blender_sha)
validate_result(structural, blender_sha)
if structural['status'] != 'IN_MEMORY_STRUCTURAL_MATCH':
    raise RuntimeError('structural reconstruction failed')
arm = bpy.context.scene.objects['D11T_Rig.005']
if len(arm.pose.bones) != 399 or sum(x.type == 'MESH' for x in bpy.context.scene.objects) != 210:
    raise RuntimeError('live rig or source mesh count differs')
sys.path.insert(0, str(sdk))
from saber.blender.lib.binary_io import BinaryIO
from saber.blender.lib.usf.scene import usf_read
from saber.blender.lib.usf.mesh import UsfMesh
from saber.blender.lib.usf.material import BlenderToUsfSimpleMaterial
from saber.blender.lib.usf.transform import FROM_SABER_CONVERT

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
    nodes[path] = node
    stack.extend((child, path + '|' + child.name) for child in node.children)

def max_error(a,b):
    return max((abs(float(x)-float(y)) for ar,br in zip(a,b) for x,y in zip(ar,br)), default=0.0)

def material_from_target(target_material):
    text = target_material.build_string()
    name = re.search(r'material = \{\s*name = "([^"]+)"', text).group(1)
    texture_names = [x for x in re.findall(r'textureName = "([^"]+)"', text) if x]
    tint = [int(x.strip()) for x in re.search(r'albedo_tint = \[([^\]]+)\]', text).group(1).split(',')]
    existing = bpy.data.materials.get(name)
    if existing:
        if BlenderToUsfSimpleMaterial(existing).build_string() != text:
            raise RuntimeError('same-name material text collision: ' + name)
        return existing
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = tuple(x / 255 for x in (tint[1],tint[2],tint[3],tint[0]))
    for texture_name in texture_names:
        texture = material.node_tree.nodes.new('ShaderNodeTexImage')
        texture.image = bpy.data.images.get(texture_name) or bpy.data.images.new(texture_name, width=1, height=1)
    if BlenderToUsfSimpleMaterial(material).build_string() != text:
        raise RuntimeError('authored material does not project to target: ' + name)
    return material

families = ('d11t_lenses_front_on_vis', 'd11t_lenses_rear_on_vis',
            'd11t_lenses_side_on_vis', 'd11t_lenses_inner_vis',
            'd11t_lenses_inner_on_vis')
target_pairs = []
for family in families:
    base_path = '|@root|D11T_Rig.005|' + family
    target_pairs.extend(zip(
        (base_path, base_path+'|'+family+'_LOD1', base_path+'|'+family+'_LOD2'),
        (family+'_LOD0',family+'_LOD1',family+'_LOD2')))
findings = next(x['findings'] for x in json.loads(worklist_path.read_text(encoding='utf-8'))['assets'] if x['asset'] == 'cat_d11t')
if len(target_pairs) != 15 or not set(path for path,_ in target_pairs) <= set(findings['repairedOnlyPaths']):
    raise RuntimeError('repaired-only lens path coverage differs')
new_objects = []
uid_to_name = {node.uid:node.name for node in nodes.values()}
for path, name in target_pairs:
    target = nodes[path]
    mesh = target.mesh
    identity = Matrix.Identity(4)
    if (bpy.data.objects.get(name) or mesh is None or
        len(mesh.skin.skin) != len(mesh.vertices) or
        len(mesh.skin.skin_bones) not in (2,381) or
        len(mesh.uvsets.uvs) != 1 or len(mesh.colorsets.sets) != 0 or
        max_error(target.matrix_world,identity) > 1e-7 or
        max_error(target.matrix_local,identity) > 1e-7):
        raise RuntimeError('family object presence or target skin differs')
    loaded = mesh.load('reviewed_'+name)
    obj = bpy.data.objects.new(name,loaded)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = arm
    obj.matrix_world = Matrix.Identity(4)
    loaded.transform(FROM_SABER_CONVERT)
    for layer in loaded.uv_layers:
        for loop in range(len(loaded.loops)):
            uv = layer.uv[loop].vector
            uv[1] = 1.0 - uv[1]
    loaded.materials.clear()
    for item in mesh.materials.data:
        loaded.materials.append(material_from_target(item))
    for i, poly in enumerate(loaded.polygons):
        poly.material_index = mesh.faces[i].material_index
    skin_names = []
    for item in mesh.skin.skin_bones:
        skin_names.append(uid_to_name[item.usf_node_uid])
    for i, entry in enumerate(mesh.skin.skin):
        for bone_idx, weight in zip(entry.bone_idx,entry.weight):
            if weight:
                group = obj.vertex_groups.get(skin_names[bone_idx]) or obj.vertex_groups.new(name=skin_names[bone_idx])
                group.add([i],weight,'REPLACE')
    mod = obj.modifiers.new('reviewed_skin','ARMATURE')
    mod.object = arm
    mod.show_viewport = False
    loaded.update()
    new_objects.append((path,obj,target,skin_names))

bpy.context.view_layer.update()
rows = []
for path,obj,target,skin_names in new_objects:
    mesh = target.mesh
    projected = UsfMesh().b_read(obj)
    projected_names = [b.name for b in projected.skin.skin_bones]
    target_by_name = {name:i for i,name in enumerate(skin_names)}
    normalized = [(tuple(target_by_name[projected_names[i]] if w else 0 for i,w in zip(e.bone_idx,e.weight)),tuple(e.weight)) for e in projected.skin.skin]
    expected = [(tuple(e.bone_idx),tuple(e.weight)) for e in mesh.skin.skin]
    row = {
        'path': path, 'predictedPath': _predicted_path(obj),
        'faces': len(mesh.faces), 'corners': len(mesh.vertices),
        'positionError': max_error(mesh.vertices,projected.vertices),
        'normalError': max_error(mesh.normals,projected.normals),
        'uvError': max_error(mesh.uvsets.uvs[0].co,projected.uvsets.uvs[0].co),
        'tangentError': max_error(mesh.uvsets.tangents[0],projected.uvsets.tangents[0]),
        'facePairsEqual': [(f.material_index,f.edge_index) for f in mesh.faces] == [(f.material_index,f.edge_index) for f in projected.faces],
        'materialTextEqual': [m.build_string() for m in mesh.materials.data] == [m.build_string() for m in projected.materials.data],
        'materialMetaEqual': [(m.ver,m.vc_usage) for m in mesh.materials.data] == [(m.ver,m.vc_usage) for m in projected.materials.data],
        'colorSetsEqual': len(mesh.colorsets.sets) == len(projected.colorsets.sets) == 0,
        'skinRemappedExact': normalized == expected,
        'targetSkinBones': len(skin_names),
        'projectedSkinBones': len(projected_names),
    }
    if (row['predictedPath'] != path or row['positionError'] != 0 or
        row['normalError'] != 0 or row['uvError'] != 0 or
        not row['facePairsEqual'] or not row['materialTextEqual'] or
        not row['materialMetaEqual'] or not row['colorSetsEqual'] or
        not row['skinRemappedExact'] or row['projectedSkinBones'] != 399):
        raise RuntimeError('lens family projection differs: '+str(row))
    rows.append(row)
if len(rows) != 15 or sum(x['faces'] for x in rows) != 949 or sum(x.type == 'MESH' for x in bpy.context.scene.objects) != 225:
    raise RuntimeError('lens family path or scene-mesh coverage differs')
require_hash(blend, '1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731', 'Blend after')
require_hash(usf, '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170', 'USF after')
require_sdk_pins(sdk)
print('D11_LENS_FAMILIES ' + json.dumps({'status':'IN_MEMORY_LENS_FAMILIES_PAYLOAD_MATCH_WITH_GAPS','rows':rows,'sceneMeshCount':sum(x.type == 'MESH' for x in bpy.context.scene.objects),'blendSaved':False,'usfExported':False},sort_keys=True),flush=True)
