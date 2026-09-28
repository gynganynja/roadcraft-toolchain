"""Pinned no-save check of 45 repaired-only D11 mesh nodes in one scene."""

from collections import Counter
import json
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
families = ('d11t_lenses_front_on_vis', 'd11t_lenses_rear_on_vis',
            'd11t_lenses_side_on_vis', 'd11t_lenses_inner_vis',
            'd11t_lenses_inner_on_vis', 'RearFlex_Ripper_vis',
            'D11_AccessMotorMount_vis', 'D11_DashV5_coolant_vis',
            'D11_DashV5_fuel_vis', 'D11_DashV5_hyd_temp_vis',
            'D11_DashV5_tach_vis', 'D11_DashV5_trans_temp_vis',
            'RearFlex_Body_vis', 'd11t_beacon_on_vis', 'd11t_beacon_off_vis')
result = reconstruct_families(repaired=repaired, sdk_root=sdk, arm=arm,
                              families=families, allowed_paths=allowed, allow_material_aliases=True)
rows = result['rows']
if (result['status'] != 'IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS' or
    len(rows) != 45 or result['sceneMeshCount'] != 255 or
    sum(item['faces'] for item in rows) != 16537 or
    sum(item['corners'] for item in rows) != 49611 or
    Counter(item['targetSkinBones'] for item in rows) !=
    Counter({1: 15, 2: 12, 3: 3, 381: 9, 382: 6}) or
    sum(item['colorSetCount'] for item in rows) != 3 or
    sum(item['skinFullMismatchCorners'] for item in rows) != 378 or
    sum(item['tangentMaxError'] >= 1 for item in rows) != 21 or
    result['materialAliases'] != [
        'mod_cat_d11t_painter_08_l0__rc_b9dad6ac29da',
        'mod_cat_d11t_painter_08_l1__rc_6996939beb62',
        'mod_cat_d11t_painter_08_l2__rc_fa9e63cd37d3']):
    raise RuntimeError('combined family coverage or known gaps differ')
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
print('D11_REPAIRED_FAMILIES ' + json.dumps(result, sort_keys=True), flush=True)
