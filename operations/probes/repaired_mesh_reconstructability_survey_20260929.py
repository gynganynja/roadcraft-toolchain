"""No-save survey of all repaired-only D11 mesh material and skin layouts."""

from collections import Counter
import json
from pathlib import Path
import re
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from roadcraft.blender_left_push_probe import require_hash, require_sdk_pins

inventory_path = ROOT / 'operations/d11_authoring_inventory.json'
worklist_path = ROOT / 'operations/d11_blender_reconstruction_worklist_20260928.json'
require_hash(inventory_path, '03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d', 'inventory')
require_hash(worklist_path, 'a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3', 'worklist')
require_hash(Path(bpy.app.binary_path), 'e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7', 'Blender')
inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
asset = next(x for x in inventory['assets'] if x['asset'] == 'cat_d11t')
usf = Path(inventory['sourceRoot']) / next(x['path'] for x in asset['files'] if x['role'] == 'build-usf')
require_hash(usf, '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170', 'repaired USF')
findings = next(x['findings'] for x in json.loads(worklist_path.read_text(encoding='utf-8'))['assets'] if x['asset'] == 'cat_d11t')
missing = set(findings['repairedOnlyPaths'])
assert len(missing) == 67
sdk = require_sdk_pins(Path(r'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'))
sys.path.insert(0, str(sdk))
from saber.blender.lib.binary_io import BinaryIO
from saber.blender.lib.usf.scene import usf_read
from saber.blender.lib.usf.material import BlenderToUsfSimpleMaterial

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

def simple_material(text):
    name = re.search(r'material = \{\s*name = "([^"]+)"', text)
    tint = re.search(r'albedo_tint = \[([^\]]+)\]', text)
    uv_name = re.search(r'uvSets = \[\s*\{[^}]*name = "([^"]+)"', text)
    if not name or not uv_name:
        return False
    material = BlenderToUsfSimpleMaterial(None, uv_name.group(1))
    material.name = name.group(1)
    material.texture_name = [x for x in re.findall(r'textureName = "([^"]+)"', text) if x]
    material.diffuse_color_str = '[' + (tint.group(1) if tint else '255, 255, 255, 255') + ']'
    try:
        return material.build_string() == text
    except Exception:
        return False

rows = []
material_names = {}
name_conflicts = set()
for path in sorted(missing):
    node = nodes[path]
    mesh = node.mesh
    if mesh is None:
        continue
    weights = Counter()
    used_bones = set()
    for entry in mesh.skin.skin:
        active = [(idx,w) for idx,w in zip(entry.bone_idx, entry.weight) if w]
        weights[len(active)] += 1
        used_bones.update(idx for idx,w in active)
    simple = [simple_material(m.build_string()) for m in mesh.materials.data]
    for item in mesh.materials.data:
        text = item.build_string()
        name = re.search(r'material = \{\s*name = "([^"]+)"', text).group(1)
        if name in material_names and material_names[name] != text:
            name_conflicts.add(name)
        material_names[name] = text
    world_identity = all(abs(float(node.matrix_world[r][c])-(1.0 if r == c else 0.0)) <= 1e-7 for r in range(4) for c in range(4))
    local_identity = all(abs(float(node.matrix_local[r][c])-(1.0 if r == c else 0.0)) <= 1e-7 for r in range(4) for c in range(4))
    rows.append({
        'path': path, 'faces': len(mesh.faces), 'corners': len(mesh.vertices),
        'materialCount': len(simple), 'simpleMaterialCount': sum(simple),
        'uvSets': len(mesh.uvsets.uvs), 'colorSets': len(mesh.colorsets.sets),
        'skinBones': len(mesh.skin.skin_bones), 'skinEntries': len(mesh.skin.skin),
        'bonesPerVertex': mesh.skin.bones_per_vertex,
        'usedSkinBones': len(used_bones), 'weightCounts': dict(weights),
        'worldIdentity': world_identity, 'localIdentity': local_identity,
        'blendShapes': len(mesh.blendshapes.shapes) if hasattr(mesh.blendshapes, 'shapes') else None,
    })
skinned = [x for x in rows if x['skinEntries']]
if (len(rows) != 52 or len(skinned) != 51 or
    sum(x['materialCount'] for x in rows) != 1213 or
    sum(x['simpleMaterialCount'] for x in rows) != 1213 or
    sorted(name_conflicts) != ['mod_cat_d11t_painter_08_l0',
                               'mod_cat_d11t_painter_08_l1',
                               'mod_cat_d11t_painter_08_l2'] or
    [x['path'] for x in rows if not x['worldIdentity']] !=
    ['|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt|BoneBladeRoll_cdt|cdt_blade_roll_pivot']):
    raise RuntimeError('repaired-only mesh reconstructability profile differs')
print('RECONSTRUCTABILITY_SURVEY ' + json.dumps({
    'meshCount': len(rows), 'skinnedCount': len(skinned),
    'materialSlotCount': sum(x['materialCount'] for x in rows),
    'simpleMaterialSlotCount': sum(x['simpleMaterialCount'] for x in rows),
    'allSimpleMeshCount': sum(x['simpleMaterialCount'] == x['materialCount'] for x in rows),
    'skinBoneCounts': dict(Counter(x['skinBones'] for x in skinned)),
    'uvSetCounts': dict(Counter(x['uvSets'] for x in rows)),
    'colorSetCounts': dict(Counter(x['colorSets'] for x in rows)),
    'bonesPerVertexCounts': dict(Counter(x['bonesPerVertex'] for x in skinned)),
    'usedSkinBoneCounts': dict(Counter(x['usedSkinBones'] for x in skinned)),
    'uniqueMaterialNames': len(material_names),
    'materialNameConflicts': sorted(name_conflicts),
    'worldNonidentity': [x['path'] for x in rows if not x['worldIdentity']],
    'localNonidentity': [x['path'] for x in rows if not x['localIdentity']],
    'nonSimple': [x for x in rows if x['simpleMaterialCount'] != x['materialCount']],
    'rows': rows,
}, sort_keys=True), flush=True)
require_hash(usf, '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170', 'repaired USF after survey')
require_sdk_pins(sdk)
