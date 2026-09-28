"""Pinned, no-save reconstruction against a D11 variant structural target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_armature_parity import (  # noqa: E402
    BLENDER_VERSION_PINS, compare_static_armature,
)
from roadcraft.blender_left_push_probe import (  # noqa: E402
    BLEND_SHA256, USF_SHA256, require_hash, require_sdk_pins,
)
from roadcraft.blender_residual_bones import (  # noqa: E402
    DEPENDENCIES, WORKER_SHA256 as RESIDUAL_SHA, validate_result,
)
from roadcraft.blender_residual_bones_worker import run as reconstruct  # noqa: E402
from roadcraft.blender_push_branches_worker import (  # noqa: E402
    flatten, repaired_paths, source_paths,
)
from roadcraft.blender_variant_reconstruction import (  # noqa: E402
    ASSET_USF_SHA256, RESULT_PREFIX, VariantReconstructionError,
)


SFX_PATH = "|@root|D11T_Rig.005|BoneChassis_cdt|sfx"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise VariantReconstructionError(message)


def run(*, asset: str, blend: Path, base_blend: Path, base_usf: Path,
        variant_usf: Path, sdk_root: Path, worker_sha256: str,
        blender_sha256: str) -> dict:
    need(asset in ("cat_d11t_v2", "cat_d11t_v3"), "variant name differs")
    need(blend != base_blend, "variant has no separate Blend path")
    need(blender_sha256 in BLENDER_VERSION_PINS and
         bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
         "Blender executable/version differs")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "variant worker")
    require_hash(blend, BLEND_SHA256, "variant source Blend")
    require_hash(base_blend, BLEND_SHA256, "base source Blend")
    require_hash(base_usf, USF_SHA256, "base repaired USF")
    require_hash(variant_usf, ASSET_USF_SHA256[asset],
                 "variant repaired USF")
    sdk = require_sdk_pins(sdk_root)
    require_hash(Path(reconstruct.__code__.co_filename), RESIDUAL_SHA,
                 "residual reconstruction worker")
    module_root = Path(__file__).resolve().parent
    for name, sha in DEPENDENCIES:
        require_hash(module_root / name, sha, name)

    base_result = reconstruct(blend=blend, usf=base_usf,
                              sdk_root=sdk, worker_sha256=RESIDUAL_SHA,
                              blender_sha256=blender_sha256)
    validate_result(base_result, blender_sha256)
    need(base_result["status"] == "IN_MEMORY_STRUCTURAL_MATCH",
         "base reconstruction did not match")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf.transform import convert_to_saber_transform

    reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else reader(self))
    try:
        _, parsed = usf_read(str(variant_usf))
    finally:
        BinaryIO.read_bytearray = reader
    target = repaired_paths(parsed._root_node)
    arm = bpy.data.objects.get("D11T_Rig.005")
    need(arm is not None and arm.type == "ARMATURE", "source armature differs")
    source = source_paths(arm, convert_to_saber_transform)
    sfx = bpy.data.objects.get("sfx")
    need(sfx is not None and sfx.type == "EMPTY" and sfx.parent == arm and
         sfx.parent_type == "BONE" and sfx.parent_bone == "BoneChassis_cdt",
         "sfx source kind differs")
    need(SFX_PATH not in source, "sfx became a pose bone")
    with_empty = {**source,
                  SFX_PATH: flatten(convert_to_saber_transform(sfx.matrix_world))}
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
    require_hash(variant_usf, ASSET_USF_SHA256[asset],
                 "variant repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(Path(__file__), worker_sha256,
                 "variant worker after diagnostic")
    for name, sha in DEPENDENCIES:
        require_hash(module_root / name, sha, name + " after diagnostic")
    return {
        "schemaVersion": 1,
        "asset": asset,
        "variantBlendPath": str(blend),
        "variantBlendSha256": BLEND_SHA256,
        "baseRepairedUsfSha256": USF_SHA256,
        "variantRepairedUsfSha256": ASSET_USF_SHA256[asset],
        "blenderVersion": bpy.app.version_string,
        "blenderSha256": blender_sha256,
        "sourcePoseBoneCount": len(source),
        "repairedStructuralCount": len(target),
        "sharedPathCount": comparison["sharedPathCount"],
        "sourceOnlyPaths": comparison["sourceOnlyPaths"],
        "repairedOnlyPaths": comparison["repairedOnlyPaths"],
        "changedMatrixCount": comparison["changedMatrixCount"],
        "maxSharedMatrixError": comparison["maxSharedMatrixError"],
        "baseReconstructionStatus": base_result["status"],
        "baseMeshWorldError": base_result["meshWorldError"],
        "sfxSourceKind": base_result["sfxSourceKind"],
        "status": ("IN_MEMORY_VARIANT_STRUCTURAL_MATCH" if matched else
                   "IN_MEMORY_VARIANT_STRUCTURAL_DIFFERENT"),
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", choices=("cat_d11t_v2", "cat_d11t_v3"),
                        required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--base-blend", type=Path, required=True)
    parser.add_argument("--base-usf", type=Path, required=True)
    parser.add_argument("--variant-usf", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run(asset=args.asset, blend=args.blend,
                 base_blend=args.base_blend, base_usf=args.base_usf,
                 variant_usf=args.variant_usf, sdk_root=args.sdk_script_root,
                 worker_sha256=args.worker_sha256,
                 blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
