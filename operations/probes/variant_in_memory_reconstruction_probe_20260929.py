"""Disposable, pinned, no-save variant reconstruction experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

toolchain = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(toolchain / "src"))
from roadcraft.blender_authoring import _pinned_asset  # noqa: E402
from roadcraft.blender_armature_parity import compare_static_armature  # noqa: E402
from roadcraft.blender_left_push_probe import (  # noqa: E402
    BLEND_SHA256, INVENTORY_SHA256, USF_SHA256, require_hash,
    require_sdk_pins,
)
from roadcraft.blender_residual_bones import (  # noqa: E402
    DEPENDENCIES, WORKER_SHA256, validate_result,
)
from roadcraft.blender_residual_bones_worker import run as reconstruct  # noqa: E402
from roadcraft.blender_push_branches_worker import (  # noqa: E402
    flatten, repaired_paths, source_paths,
)
from roadcraft.blender_variant_structural_targets import (  # noqa: E402
    ASSET_USF_SHA256,
)
from roadcraft.source import file_sha256  # noqa: E402


def need(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--asset", choices=("cat_d11t_v2", "cat_d11t_v3"),
                    required=True)
args = parser.parse_args(argv)

registry = json.loads((toolchain / "project.json").read_text(encoding="utf-8"))
reference = registry["accepted"]["authoringInventory"]
need(reference["sha256"] == INVENTORY_SHA256, "inventory pin differs")
inventory = toolchain / reference["path"]
require_hash(inventory, INVENTORY_SHA256, "authoring inventory")
_, _, _, blend, variant_usf = _pinned_asset(
    inventory, INVENTORY_SHA256, args.asset)
_, _, _, base_blend, base_usf = _pinned_asset(
    inventory, INVENTORY_SHA256, "cat_d11t")
need(blend != base_blend, "variant has no separate source path")
require_hash(blend, BLEND_SHA256, "variant source Blend")
require_hash(base_blend, BLEND_SHA256, "base source Blend")
require_hash(base_usf, USF_SHA256, "base repaired USF")
require_hash(variant_usf, ASSET_USF_SHA256[args.asset],
             "variant repaired USF")
blender = Path(bpy.app.binary_path)
blender_sha = file_sha256(blender)
sdk = toolchain.parent.parent / "tools/bin/blender_to_usf_script"
require_sdk_pins(sdk)
require_hash(Path(reconstruct.__code__.co_filename), WORKER_SHA256,
             "residual reconstruction worker")
for name, sha in DEPENDENCIES:
    require_hash(toolchain / "src/roadcraft" / name, sha, name)

base_result = reconstruct(blend=blend, usf=base_usf,
                          sdk_root=sdk, worker_sha256=WORKER_SHA256,
                          blender_sha256=blender_sha)
validate_result(base_result, blender_sha)
need(base_result["status"] == "IN_MEMORY_STRUCTURAL_MATCH",
     "base reconstruction did not match")

sys.path.insert(0, str(sdk))
from saber.blender.lib.binary_io import BinaryIO  # noqa: E402
from saber.blender.lib.usf.scene import usf_read  # noqa: E402
from saber.blender.lib.usf.transform import convert_to_saber_transform  # noqa: E402

reader = BinaryIO.read_bytearray
BinaryIO.read_bytearray = (
    lambda self, size=None: self.io.read(size) if size is not None
    else reader(self))
try:
    _, parsed = usf_read(str(variant_usf))
finally:
    BinaryIO.read_bytearray = reader
target = repaired_paths(parsed._root_node)
arm = bpy.data.objects["D11T_Rig.005"]
source = source_paths(arm, convert_to_saber_transform)
sfx = bpy.data.objects["sfx"]
need(sfx.type == "EMPTY" and sfx.parent == arm and
     sfx.parent_type == "BONE" and sfx.parent_bone == "BoneChassis_cdt",
     "sfx source kind differs")
sfx_path = "|@root|D11T_Rig.005|BoneChassis_cdt|sfx"
need(sfx_path not in source, "sfx became a bone")
with_empty = {**source,
              sfx_path: flatten(convert_to_saber_transform(sfx.matrix_world))}
comparison = compare_static_armature(with_empty, target)
matched = (len(source) == 399 and len(target) == 400 and
           comparison["sharedPathCount"] == 400 and
           comparison["sourceOnlyPaths"] == [] and
           comparison["repairedOnlyPaths"] == [] and
           comparison["changedMatrixCount"] == 0 and
           comparison["maxSharedMatrixError"] <= 1e-5)
require_hash(blend, BLEND_SHA256, "variant source Blend after diagnostic")
require_hash(base_blend, BLEND_SHA256, "base source Blend after diagnostic")
require_hash(base_usf, USF_SHA256, "base repaired USF after diagnostic")
require_hash(variant_usf, ASSET_USF_SHA256[args.asset],
             "variant repaired USF after diagnostic")
require_sdk_pins(sdk)
print("ROADCRAFT_VARIANT_RECONSTRUCTION " + json.dumps({
    "schemaVersion": 1, "asset": args.asset,
    "variantBlendPath": str(blend), "variantBlendSha256": BLEND_SHA256,
    "baseRepairedUsfSha256": USF_SHA256,
    "variantRepairedUsfSha256": ASSET_USF_SHA256[args.asset],
    "blenderVersion": bpy.app.version_string, "blenderSha256": blender_sha,
    "sourcePoseBoneCount": len(source),
    "repairedStructuralCount": len(target),
    "sharedPathCount": comparison["sharedPathCount"],
    "sourceOnlyPaths": comparison["sourceOnlyPaths"],
    "repairedOnlyPaths": comparison["repairedOnlyPaths"],
    "changedMatrixCount": comparison["changedMatrixCount"],
    "maxSharedMatrixError": comparison["maxSharedMatrixError"],
    "baseReconstructionStatus": base_result["status"],
    "status": ("IN_MEMORY_VARIANT_STRUCTURAL_MATCH" if matched else
               "IN_MEMORY_VARIANT_STRUCTURAL_DIFFERENT"),
    "blendSaved": False, "usfExported": False,
    "nativeBlendExportApproved": False,
}, sort_keys=True), flush=True)
need(matched, "variant reconstruction differs from repaired target")
