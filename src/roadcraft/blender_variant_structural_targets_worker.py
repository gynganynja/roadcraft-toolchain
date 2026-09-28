"""Pinned, no-save comparison of the three accepted D11 repaired rig targets."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_left_push_probe import (  # noqa: E402
    BLEND_SHA256, require_hash, require_sdk_pins,
)
from roadcraft.blender_variant_structural_targets import (  # noqa: E402
    ASSET_USF_SHA256, RESULT_PREFIX, VariantStructuralError,
)


ARMATURE = "D11T_Rig.005"
EXPECTED_DIGEST = "d2694db5513e19b3e6e23527b280f7bb46a4b724c0c3268bf171c95dd92e4369"


def structural_map(root: object) -> dict:
    armatures = [node for node in root.children if node.name == ARMATURE]
    if len(armatures) != 1:
        raise VariantStructuralError("repaired armature roster differs")
    result = {}
    stack = [(armatures[0], "|@root|" + ARMATURE)]
    while stack:
        node, path = stack.pop()
        for child in node.children:
            child_path = path + "|" + child.name
            stack.append((child, child_path))
            if child.mesh is None:
                if child_path in result:
                    raise VariantStructuralError("duplicate structural path")
                result[child_path] = {
                    "matrix": [float(child.matrix_world[i][j])
                               for i in range(4) for j in range(4)],
                    "anim": child.anim is not None,
                    "children": sorted(item.name for item in child.children),
                }
    return result


def run(*, blend: Path, usfs: list[Path], sdk_root: Path,
        worker_sha256: str, blender_sha256: str) -> dict:
    from roadcraft.blender_armature_parity import BLENDER_VERSION_PINS

    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256])):
        raise VariantStructuralError("Blender executable/version differs")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "variant worker")
    require_hash(blend, BLEND_SHA256, "source Blend")
    if len(usfs) != len(ASSET_USF_SHA256):
        raise VariantStructuralError("repaired USF roster differs")
    assets = list(zip(ASSET_USF_SHA256.items(), usfs, strict=True))
    for (name, sha), usf in assets:
        require_hash(usf, sha, name + " repaired USF")
    sdk = require_sdk_pins(sdk_root)
    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read

    maps = {}
    for (name, _), usf in assets:
        reader = BinaryIO.read_bytearray
        BinaryIO.read_bytearray = (
            lambda self, size=None: self.io.read(size) if size is not None
            else reader(self))
        try:
            _, parsed = usf_read(str(usf))
        finally:
            BinaryIO.read_bytearray = reader
        maps[name] = structural_map(parsed._root_node)
        del parsed
        gc.collect()

    base = maps["cat_d11t"]
    rows = []
    for name, paths in maps.items():
        shared = sorted(base.keys() & paths.keys())
        errors = {path: max(abs(a - b) for a, b in
                            zip(base[path]["matrix"], paths[path]["matrix"],
                                strict=True)) for path in shared}
        other_changes = [path for path in shared
                         if base[path]["anim"] != paths[path]["anim"] or
                         base[path]["children"] != paths[path]["children"]]
        rows.append({
            "asset": name,
            "repairedUsfSha256": ASSET_USF_SHA256[name],
            "structuralCount": len(paths),
            "sharedWithBase": len(shared),
            "baseOnlyPaths": sorted(base.keys() - paths.keys()),
            "variantOnlyPaths": sorted(paths.keys() - base.keys()),
            "matrixDifferentPathsOver1e5": [path for path in shared
                                             if errors[path] > 1e-5],
            "maxMatrixElementError": max(errors.values()) if errors else None,
            "animationOrChildRosterDifferentPaths": other_changes,
            "structuralDigest": hashlib.sha256(json.dumps(
                paths, sort_keys=True, separators=(",", ":"),
                allow_nan=False).encode("utf-8")).hexdigest(),
        })

    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    for (name, sha), usf in assets:
        require_hash(usf, sha, name + " repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(Path(__file__), worker_sha256, "variant worker after diagnostic")
    identical = all(row["structuralCount"] == 400 and
                    row["sharedWithBase"] == 400 and
                    row["baseOnlyPaths"] == [] and
                    row["variantOnlyPaths"] == [] and
                    row["matrixDifferentPathsOver1e5"] == [] and
                    row["maxMatrixElementError"] == 0 and
                    row["animationOrChildRosterDifferentPaths"] == [] and
                    row["structuralDigest"] == EXPECTED_DIGEST for row in rows)
    return {
        "schemaVersion": 1,
        "status": ("REPAIRED_VARIANT_STRUCTURES_IDENTICAL" if identical else
                   "REPAIRED_VARIANT_STRUCTURES_DIFFERENT"),
        "blendSha256": BLEND_SHA256,
        "blenderVersion": bpy.app.version_string,
        "blenderSha256": blender_sha256,
        "rows": rows,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--usf", type=Path, action="append", required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run(blend=args.blend, usfs=args.usf,
                 sdk_root=args.sdk_script_root,
                 worker_sha256=args.worker_sha256,
                 blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
