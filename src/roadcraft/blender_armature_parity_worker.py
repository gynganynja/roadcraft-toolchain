"""Blender-side, no-save D11 static armature readback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_armature_parity import (  # noqa: E402
    BLENDER_VERSION_PINS, BLEND_SHA256, RESULT_PREFIX, USF_SHA256,
    ArmatureParityError, compare_static_armature, require_hash, require_sdk_pins,
)


ARMATURE = "D11T_Rig.005"
BONE_AFFIXES = {"export_preserve_position", "export_preserve_geometry"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArmatureParityError(message)


def _flatten(matrix) -> list[float]:
    return [float(matrix[row][col]) for row in range(4) for col in range(4)]


def _source_bone_paths(arm) -> dict[str, list[float]]:
    result = {}
    for bone in arm.pose.bones:
        lineage = []
        cursor = bone
        while cursor is not None:
            lineage.append(cursor.name)
            cursor = cursor.parent
        path = "|@root|" + ARMATURE + "|" + "|".join(reversed(lineage))
        _require(path not in result, f"duplicate source bone path {path}")
        result[path] = _flatten(arm.matrix_world @ bone.matrix)
    return result


def _repaired_structural_paths(usf_root) -> tuple[dict[str, list[float]], list[str], list[str]]:
    _require(usf_root.name == "cat_d11t", "repaired USF root differs")
    matches = [child for child in usf_root.children if child.name == ARMATURE]
    _require(len(matches) == 1, "repaired USF armature is not unique")
    repaired = {}
    affix_bones = []
    unclassified_meshless = []
    stack = [(matches[0], "|@root|" + ARMATURE)]
    while stack:
        node, path = stack.pop()
        for child in node.children:
            child_path = path + "|" + child.name
            stack.append((child, child_path))
            affixes = set(child.get_affixes_names())
            if child.mesh is None:
                _require(child_path not in repaired,
                         f"duplicate repaired structural path {child_path}")
                repaired[child_path] = _flatten(child.matrix_world)
                if BONE_AFFIXES <= affixes:
                    affix_bones.append(child_path)
                else:
                    unclassified_meshless.append(child_path)
    return repaired, sorted(affix_bones), sorted(unclassified_meshless)


def run_readback(*, blend: Path, usf: Path, sdk_root: Path,
                 worker_sha256: str, blender_sha256: str) -> dict:
    _require(blender_sha256 in BLENDER_VERSION_PINS,
             "Blender pin is not reviewed")
    require_hash(Path(bpy.app.binary_path), blender_sha256, "Blender executable")
    require_hash(Path(__file__), worker_sha256, "armature worker")
    blend = require_hash(blend, BLEND_SHA256, "source Blend")
    usf = require_hash(usf, USF_SHA256, "repaired USF")
    sdk = require_sdk_pins(sdk_root)
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha256]),
             "Blender version differs")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf.transform import convert_to_saber_transform

    # Retained SDK USF reader needs this in-process byte-array shim for these
    # bytes. No SDK file or source asset is changed.
    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    _, scene = usf_read(str(usf))
    repaired, affix_bones, unclassified_meshless = _repaired_structural_paths(scene._root_node)

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    arms = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    _require(len(arms) == 1 and arms[0].name == ARMATURE,
             "source armature is not unique")
    _require(bpy.context.scene.frame_current == 1,
             "source scene frame differs from pinned static readback")
    arm = arms[0]
    source_blender = _source_bone_paths(arm)
    source = {}
    for path, values in source_blender.items():
        # Keep the exact SDK basis conversion that native export uses.
        from mathutils import Matrix
        matrix = Matrix([values[row * 4:(row + 1) * 4] for row in range(4)])
        source[path] = _flatten(convert_to_saber_transform(matrix))
    _require(source and repaired, "source or repaired bone set is empty")
    comparison = compare_static_armature(source, repaired)
    require_hash(blend, BLEND_SHA256, "source Blend after readback")
    require_hash(usf, USF_SHA256, "repaired USF after readback")
    require_sdk_pins(sdk)
    return {
        "schemaVersion": 1,
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha256,
        "blenderVersion": bpy.app.version_string,
        "sceneFrame": bpy.context.scene.frame_current,
        "classification": "all meshless nodes beneath USF armature; SDK bone affixes reported separately",
        "affixClassifiedUsfPaths": affix_bones,
        "unclassifiedMeshlessUsfPaths": unclassified_meshless,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceWorldMatrices": source,
        "repairedWorldMatrices": repaired,
        **comparison,
    }


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    args = parser.parse_args(argv)
    result = run_readback(blend=args.blend, usf=args.repaired_usf,
                          sdk_root=args.sdk_script_root,
                          worker_sha256=args.worker_sha256,
                          blender_sha256=args.blender_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
