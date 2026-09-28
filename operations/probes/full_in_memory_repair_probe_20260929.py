"""Disposable no-save composition check for the pinned D11 repairs.

This deliberately does not invoke the SDK exporter or write an asset.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from roadcraft.blender_armature_parity import compare_static_armature
from roadcraft.blender_blade_normal_scratch_repair import (
    install_in_memory_blade_normals,
)
from roadcraft.blender_push_branches_worker import flatten, source_paths
from roadcraft.blender_residual_bones import WORKER_SHA256, validate_result
from roadcraft.blender_residual_bones_worker import run as residual_run
from roadcraft.blender_wiper_repair import (
    SDK_MISC_SHA256, SDK_SCENE_SHA256, install_scratch_wiper_repair,
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(path: Path, digest: str) -> None:
    if sha(path) != digest:
        raise RuntimeError(f"pin differs: {path}")


inventory_path = ROOT / "operations/d11_authoring_inventory.json"
require(inventory_path, "03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d")
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
asset = next(row for row in inventory["assets"] if row["asset"] == "cat_d11t")
source = Path(inventory["sourceRoot"])
blend_row = next(row for row in asset["files"] if row["role"] == "blend-reference")
usf_row = next(row for row in asset["files"] if row["role"] == "build-usf")
blend = source / blend_row["path"]
usf = source / usf_row["path"]
sdk = Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script")
native = ROOT / "local/blend-authoring-parity-base-normalized/candidate.usf"
native_sha = "80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370"
blender_sha = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"

require(blend, blend_row["sha256"])
require(usf, usf_row["sha256"])
require(native, native_sha)
require(Path(bpy.app.binary_path), blender_sha)
require(sdk / "saber/blender/lib/usf/misc.py", SDK_MISC_SHA256)
require(sdk / "saber/blender/lib/usf/scene.py", SDK_SCENE_SHA256)

structural = residual_run(
    blend=blend, usf=usf, sdk_root=sdk,
    worker_sha256=WORKER_SHA256, blender_sha256=blender_sha)
validate_result(structural, blender_sha)
if structural["status"] != "IN_MEMORY_STRUCTURAL_MATCH":
    raise RuntimeError("structural reconstruction differs")

normal = install_in_memory_blade_normals(
    blend=blend, repaired=usf, native=native,
    native_sha256=native_sha, sdk_root=sdk,
    blender_sha256=blender_sha, blade_roll_present=True)
if (normal["status"] != "IN_MEMORY_BLADE_NORMALS_INSTALLED" or
        normal["leaves"] != 60 or normal["triangles"] != 2162 or
        normal["corners"] != 6486 or
        normal["rowsDigestSha256"] !=
        "533058ffdaa47a8aa064c284c7f717096dc27282a3dd300fab7330d50b00fa23"):
    raise RuntimeError("blade normal installation differs")

from saber.blender.lib.usf import misc as sdk_misc
from saber.blender.lib.usf.transform import convert_to_saber_transform

arm = bpy.data.objects["D11T_Rig.005"]
sfx = bpy.data.objects["sfx"]
sfx_path = "|@root|D11T_Rig.005|BoneChassis_cdt|sfx"

def scene_paths() -> dict:
    bpy.context.view_layer.update()
    return {**source_paths(arm, convert_to_saber_transform),
            sfx_path: flatten(convert_to_saber_transform(sfx.matrix_world))}


before = scene_paths()
trace = install_scratch_wiper_repair(
    bpy, sdk_misc, blend_sha256=blend_row["sha256"],
    sdk_misc_sha256=SDK_MISC_SHA256,
    sdk_scene_sha256=SDK_SCENE_SHA256)
after = scene_paths()
comparison = compare_static_armature(after, before)
if (len(after) != 400 or comparison["status"] != "STATIC_ARMATURE_MATCH" or
        comparison["changedMatrixCount"] != 0 or
        comparison["sourceOnlyPaths"] or comparison["repairedOnlyPaths"]):
    raise RuntimeError("wiper hook changed the frame-one rig")
attributes = sum(
    obj.data.attributes.get("saber_normals") is not None
    for obj in bpy.context.scene.objects if obj.type == "MESH")
if attributes < 60:
    raise RuntimeError(f"blade normal attribute coverage differs: {attributes}")
require(blend, blend_row["sha256"])
require(usf, usf_row["sha256"])
require(native, native_sha)
result = {
    "structuralStatus": structural["status"],
    "structuralPathCount": len(before),
    "normalStatus": normal["status"],
    "normalLeaves": normal["leaves"],
    "normalRowsDigestSha256": normal["rowsDigestSha256"],
    "namedBladeNormalAttributes": attributes,
    "wiperHookStrategy": trace["strategy"],
    "wiperActionOrder": trace["actionOrder"],
    "wiperSampleCounts": trace["sampleCounts"],
    "postHookComparison": {
        "status": comparison["status"],
        "sharedPathCount": comparison["sharedPathCount"],
        "changedMatrixCount": comparison["changedMatrixCount"],
        "maxSharedMatrixError": comparison["maxSharedMatrixError"],
        "sourceOnlyPaths": comparison["sourceOnlyPaths"],
        "repairedOnlyPaths": comparison["repairedOnlyPaths"],
    },
    "blendSaved": False,
    "usfExported": False,
}
print("ROADCRAFT_FULL_IN_MEMORY " + json.dumps(result, sort_keys=True), flush=True)
