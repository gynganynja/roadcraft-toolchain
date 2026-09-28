"""Pinned no-save check of one isolated large D11 LOD case."""

import json
import os
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from roadcraft.blender_left_push_probe import require_hash, require_sdk_pins
from roadcraft.blender_repaired_mesh_families import reconstruct_families
from roadcraft.blender_residual_bones import WORKER_SHA256, validate_result
from roadcraft.blender_residual_bones_worker import run as structural_run

INVENTORY_SHA = '03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d'
WORKLIST_SHA = 'a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3'
BLEND_SHA = '1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731'
USF_SHA = '49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170'
BLENDER_SHA = 'e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7'
MODULE_SHA = '7f86dd84a6867f609d6400a7a17d2c534cf9a62f61f6aaad4e9aa162281b4ad1'

inventory_path = ROOT / 'operations/d11_authoring_inventory.json'
worklist_path = ROOT / 'operations/d11_blender_reconstruction_worklist_20260928.json'
module_path = ROOT / 'src/roadcraft/blender_repaired_mesh_families.py'
require_hash(inventory_path, INVENTORY_SHA, 'accepted inventory')
require_hash(worklist_path, WORKLIST_SHA, 'reconstruction worklist')
require_hash(module_path, MODULE_SHA, 'family importer')
require_hash(Path(bpy.app.binary_path), BLENDER_SHA, 'Blender executable')
if not bpy.app.version_string.startswith('5.2.0'):
    raise RuntimeError('Blender version differs')
inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
asset = next(item for item in inventory['assets'] if item['asset'] == 'cat_d11t')
source_root = Path(inventory['sourceRoot'])
blend = source_root / next(item['path'] for item in asset['files'] if item['role'] == 'blend-reference')
repaired = source_root / next(item['path'] for item in asset['files'] if item['role'] == 'build-usf')
sdk = require_sdk_pins(Path(r'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'))
require_hash(blend, BLEND_SHA, 'source Blend')
require_hash(repaired, USF_SHA, 'repaired USF')
worklist = json.loads(worklist_path.read_text(encoding='utf-8'))
findings = next(item['findings'] for item in worklist['assets'] if item['asset'] == 'cat_d11t')
allowed = set(findings['repairedOnlyPaths'])
if len(allowed) != 67:
    raise RuntimeError('repaired-only worklist coverage differs')

structural = structural_run(blend=blend, usf=repaired, sdk_root=sdk,
                            worker_sha256=WORKER_SHA256,
                            blender_sha256=BLENDER_SHA)
validate_result(structural, BLENDER_SHA)
if structural['status'] != 'IN_MEMORY_STRUCTURAL_MATCH':
    raise RuntimeError('structural repair differs')
arm = bpy.context.scene.objects['D11T_Rig.005']
if sum(obj.type == 'MESH' for obj in bpy.context.scene.objects) != 210:
    raise RuntimeError('source scene mesh count differs')
cases = {
    'lod2_pair': (('D11_InteriorV1_vis', 'D11_DashV5_vis'), (2,),
                  (24285, 4152), False),
    'dash_lod1': (('D11_DashV5_vis',), (1,), (19797,), False),
    'interior_lod1': (('D11_InteriorV1_vis',), (1,), (63468,), False),
    'interior_lod0': (('D11_InteriorV1_vis',), (0,), (65844,), True),
    'dash_lod0': (('D11_DashV5_vis',), (0,), (157482,), True),
}
case_name = os.environ.get('D11_LARGE_MESH_CASE')
if case_name not in cases:
    raise RuntimeError('D11_LARGE_MESH_CASE must name one reviewed case')
families, lod_indices, expected_faces, paths_verified = cases[case_name]
result = reconstruct_families(repaired=repaired, sdk_root=sdk, arm=arm,
                              families=families, allowed_paths=allowed,
                              allow_material_aliases=True,
                              lod_indices=lod_indices)
rows = result['rows']
status = ('IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS' if paths_verified else
          'IN_MEMORY_ISOLATED_LOD_PAYLOAD_MATCH_WITH_GAPS')
if (result['status'] != status or
    len(rows) != len(expected_faces) or
    result['sceneMeshCount'] != 210 + len(expected_faces) or
    tuple(item['faces'] for item in rows) != expected_faces or
    any(item['corners'] != item['faces'] * 3 or
        item['targetSkinBones'] != 1 or
        item['projectedSkinBones'] != 399 or
        item['colorSetCount'] != 0 or
        item['skinFullMismatchCorners'] != 0 or
        item['skinFullExact'] is not True or
        (item['predictedPath'] == item['path']) != paths_verified
        for item in rows) or
    result['materialAliases'] != []):
    raise RuntimeError('large-mesh case coverage or known gaps differ')
from saber.blender.lib.usf.mesh import UsfMeshColorSet
from saber.blender.lib.usf import mesh as sdk_mesh
from saber.blender.lib.usf.material import BlenderToUsfSimpleMaterial
if UsfMeshColorSet.FAST_PACK is not False:
    raise RuntimeError('SDK color mode was not restored')
if sdk_mesh.BlenderToUsfSimpleMaterial is not BlenderToUsfSimpleMaterial:
    raise RuntimeError('SDK material projector was not restored')
require_hash(blend, BLEND_SHA, 'source Blend after reconstruction')
require_hash(repaired, USF_SHA, 'repaired USF after reconstruction')
require_hash(module_path, MODULE_SHA, 'family importer after reconstruction')
require_sdk_pins(sdk)
print('D11_REPAIRED_LARGE_CASE ' + json.dumps(
    {'case': case_name, 'result': result}, sort_keys=True), flush=True)
