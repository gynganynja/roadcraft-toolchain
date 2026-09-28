"""Blender-side scratch export and SDK node comparison.

Only the wrapper launches this script. It opens a pinned historical .blend and
reads a pinned repaired USF; the export and helper JSON live in disposable
scratch. It never saves a .blend or writes to the authoritative USF.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_parity_diff import compare_node_rows
from blender_usf_helper import _semantic_summary
from blender_wiper_repair import install_scratch_wiper_repair


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _node_rows(scene) -> dict[str, dict]:
    """Index every parsed node by hierarchy path, including rig and mesh data."""
    rows = {}
    duplicate_paths = {}
    stack = [(scene._root_node, "")]
    while stack:
        node, parent = stack.pop()
        # The SDK may retain a historical root name in repaired variant USFs
        # while a native export names its root from the variant .blend file.
        # Align descendant paths, but record the root-name difference below.
        path = parent + "|" + node.name if parent else "|@root"
        ordinal = duplicate_paths.get(path, 0) + 1
        duplicate_paths[path] = ordinal
        indexed_path = path if ordinal == 1 else f"{path}[#{ordinal}]"
        row = {
            "nodeVersion": node.node_ver,
            "childCount": len(node.children),
            "localTransformSha256": _digest(
                [[float(value) for value in line] for line in node.matrix_local]
            ),
            "worldTransformSha256": _digest(
                [[float(value) for value in line] for line in node.matrix_world]
            ),
        }
        mesh = node.mesh
        if mesh is not None:
            materials = [material.mat for material in mesh.materials.data]
            bind_matrices = [
                [[float(value) for value in line] for line in bone.inv_bind_matr]
                for bone in mesh.skin.skin_bones
            ]
            row["mesh"] = {
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
                "normals": len(mesh.normals),
                "uvSets": len(mesh.uvsets.uvs),
                "colorSets": len(mesh.colorsets.sets),
                "materialNames": materials,
                "skinEntries": len(mesh.skin.skin),
                "skinBoneNodeUids": [bone.usf_node_uid
                                     for bone in mesh.skin.skin_bones],
                "inverseBindMatricesSha256": _digest(bind_matrices),
            }
        if node.anim is not None:
            row["animation"] = {
                name: {"keys": spline.keys_count,
                       "dataSha256": hashlib.sha256(spline.data).hexdigest()}
                for name in ("spl_translate", "spl_rotation", "spl_scale",
                             "spl_visibility")
                if (spline := getattr(node.anim, name)) is not None
            }
        rows[indexed_path] = row
        stack.extend((child, path) for child in reversed(node.children))
    return rows


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--blend-sha256", required=True)
    parser.add_argument("--baseline-usf", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--candidate-usf", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--wiper-scratch-repair", action="store_true")
    args = parser.parse_args(argv)

    blend = args.blend.resolve(strict=True)
    baseline = args.baseline_usf.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    candidate = args.candidate_usf.resolve()
    result_path = args.result.resolve()
    sdk = args.sdk_script_root.resolve(strict=True)
    if (blend.suffix.lower() != ".blend" or baseline.suffix.lower() != ".usf" or
            not blend.is_file() or not baseline.is_file() or
            candidate.exists() or result_path.exists() or
            not candidate.is_relative_to(scratch) or
            not result_path.is_relative_to(scratch) or
            candidate == result_path):
        raise ValueError("source or scratch output paths are invalid")
    blend_before = _sha(blend)
    baseline_before = _sha(baseline)
    if (blend_before != args.blend_sha256.lower() or
            baseline_before != args.baseline_sha256.lower()):
        raise ValueError("authoring source differs from its inventory pin")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.export import export_to_usf
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf import misc as sdk_misc

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    wiper_repair = None
    if args.wiper_scratch_repair:
        wiper_repair = install_scratch_wiper_repair(
            bpy, sdk_misc, blend_sha256=blend_before,
            sdk_misc_sha256=_sha(sdk / "saber/blender/lib/usf/misc.py"),
            sdk_scene_sha256=_sha(sdk / "saber/blender/lib/usf/scene.py"),
        )
    config_path = sdk / "saber/blender/blender_to_usf/name_convention_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update({"src_fmt": "blend", "src_filename": blend.name})
    export_to_usf(bpy.context.scene, str(candidate), config)
    if wiper_repair is not None:
        if (wiper_repair["actionOrder"] !=
                ["d11_wipers_backward", "d11_wipers_forward"] or
                wiper_repair["sampleCounts"] !=
                {"d11_wipers_backward": 18, "d11_wipers_forward": 18}):
            raise RuntimeError("scratch SDK wiper bake did not run both actions")

    _, native_scene = usf_read(str(candidate))
    native_root_name = native_scene._root_node.name
    native_summary = _semantic_summary(native_scene)
    native_rows = _node_rows(native_scene)
    if wiper_repair is not None:
        wiper_path = "|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront"
        splines = native_rows.get(wiper_path, {}).get("animation", {})
        wiper_repair["nativeSplineKeys"] = {
            name: splines.get(name, {}).get("keys")
            for name in ("spl_translate", "spl_rotation", "spl_scale")
        }
        wiper_repair["nativeSplineKeyCountMatchesRepaired"] = all(
            value == 36 for value in wiper_repair["nativeSplineKeys"].values())
    del native_scene
    gc.collect()
    _, baseline_scene = usf_read(str(baseline))
    baseline_root_name = baseline_scene._root_node.name
    baseline_summary = _semantic_summary(baseline_scene)
    baseline_rows = _node_rows(baseline_scene)
    del baseline_scene
    gc.collect()

    if _sha(blend) != blend_before or _sha(baseline) != baseline_before:
        raise RuntimeError("authoring input changed during scratch export")
    result = {
        "schemaVersion": 1,
        "blendSha256": blend_before,
        "baselineUsfSha256": baseline_before,
        "candidateUsfSha256": _sha(candidate),
        "candidateUsfBytes": candidate.stat().st_size,
        "blenderVersion": bpy.app.version_string,
        "blendUnchanged": True,
        "baselineUsfUnchanged": True,
        "baselineSemantic": baseline_summary,
        "candidateSemantic": native_summary,
        "baselineRootName": baseline_root_name,
        "candidateRootName": native_root_name,
        "rootNameMatches": baseline_root_name == native_root_name,
        "nodeDiff": compare_node_rows(baseline_rows, native_rows),
        "nativeBlendExportApproved": False,
        "wiperRepair": wiper_repair,
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("ROADCRAFT_AUTHORING_PROBE " + json.dumps({
        "baselineNodes": baseline_summary["nodes"],
        "candidateNodes": native_summary["nodes"],
        "baselineFaces": baseline_summary["faces"],
        "candidateFaces": native_summary["faces"],
        "missingPaths": len(result["nodeDiff"]["missingNodePaths"]),
        "extraPaths": len(result["nodeDiff"]["extraNodePaths"]),
    }), flush=True)


if __name__ == "__main__":
    main()
