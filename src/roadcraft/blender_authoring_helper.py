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
from blender_rgba_cache_guard import (SDK_MESH_SHA256, immutable_rgba_cache,
                                      require_pins as require_rgba_guard_pins)


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
    parser.add_argument("--push-branch-scratch-repair", action="store_true")
    parser.add_argument("--push-branch-host-sha256")
    parser.add_argument("--push-branch-worker-sha256")
    parser.add_argument("--blade-roll-scratch-repair", action="store_true")
    parser.add_argument("--blade-roll-host-sha256")
    parser.add_argument("--blade-roll-worker-sha256")
    parser.add_argument("--blade-normal-scratch-repair", action="store_true")
    parser.add_argument("--blade-normal-repair-sha256")
    parser.add_argument("--blade-normal-native-usf", type=Path)
    parser.add_argument("--blade-normal-native-sha256")
    parser.add_argument("--rgba-cache-guard", action="store_true")
    parser.add_argument("--rgba-cache-guard-sha256")
    parser.add_argument("--asset")
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
    push_host_file = Path(__file__).with_name("blender_push_branches.py")
    push_worker_file = Path(__file__).with_name("blender_push_branches_worker.py")
    if args.push_branch_scratch_repair:
        if (not args.push_branch_host_sha256 or
                not args.push_branch_worker_sha256 or
                _sha(push_host_file) != args.push_branch_host_sha256 or
                _sha(push_worker_file) != args.push_branch_worker_sha256):
            raise ValueError("push-branch module differs from host pin")
    elif (args.push_branch_host_sha256 is not None or
          args.push_branch_worker_sha256 is not None):
        raise ValueError("push-branch hashes require opt-in")
    roll_host_file = Path(__file__).with_name("blender_blade_roll.py")
    roll_worker_file = Path(__file__).with_name("blender_blade_roll_worker.py")
    if args.blade_roll_scratch_repair:
        if (not args.push_branch_scratch_repair or
                not args.blade_roll_host_sha256 or
                not args.blade_roll_worker_sha256 or
                _sha(roll_host_file) != args.blade_roll_host_sha256 or
                _sha(roll_worker_file) != args.blade_roll_worker_sha256):
            raise ValueError("blade-roll module differs from host pin")
    elif (args.blade_roll_host_sha256 is not None or
          args.blade_roll_worker_sha256 is not None):
        raise ValueError("blade-roll hashes require opt-in")
    blade_repair_file = Path(__file__).with_name(
        "blender_blade_normal_scratch_repair.py")
    blade_native = None
    if args.blade_normal_scratch_repair:
        if (not args.blade_normal_repair_sha256 or
                not args.blade_normal_native_usf or
                not args.blade_normal_native_sha256 or
                _sha(blade_repair_file) != args.blade_normal_repair_sha256):
            raise ValueError("blade-normal module differs from host pin")
        blade_native = args.blade_normal_native_usf.resolve(strict=True)
        if (blade_native.suffix.lower() != ".usf" or
                blade_native == baseline or
                blade_native.is_relative_to(scratch) or
                _sha(blade_native) != args.blade_normal_native_sha256):
            raise ValueError("retained native USF differs from host pin")
    elif (args.blade_normal_repair_sha256 is not None or
          args.blade_normal_native_usf is not None or
          args.blade_normal_native_sha256 is not None):
        raise ValueError("blade-normal arguments require opt-in")
    rgba_guard_file = Path(__file__).with_name("blender_rgba_cache_guard.py")
    sdk_mesh_file = sdk / "saber/blender/lib/usf/mesh.py"
    if args.rgba_cache_guard:
        if (not args.rgba_cache_guard_sha256 or
                _sha(rgba_guard_file) != args.rgba_cache_guard_sha256):
            raise ValueError("RGBA cache guard module differs from host pin")
        require_rgba_guard_pins(
            asset_name=args.asset, blend_sha256=blend_before,
            baseline_usf_sha256=baseline_before,
            blender_sha256=_sha(Path(bpy.app.binary_path)),
            sdk_mesh_sha256=_sha(sdk_mesh_file),
            blender_version=bpy.app.version_string)
    elif args.rgba_cache_guard_sha256 is not None or args.asset is not None:
        raise ValueError("RGBA cache guard arguments require opt-in")

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO
    from saber.blender.lib.usf.export import export_to_usf
    from saber.blender.lib.usf.scene import usf_read
    from saber.blender.lib.usf import misc as sdk_misc
    if args.rgba_cache_guard:
        from saber.blender.lib.usf.mesh import RGBA_CACHE, UsfMeshColorSet
        if Path(UsfMeshColorSet.rgba_to_saber.__code__.co_filename).resolve() != \
                sdk_mesh_file.resolve():
            raise ValueError("RGBA cache packer is outside reviewed SDK mesh")

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )

    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    push_branch_repair = None
    if args.push_branch_scratch_repair:
        from blender_push_branches_worker import run as reconstruct_push_branches
        from roadcraft import blender_armature_parity, blender_left_push_probe
        from roadcraft.blender_push_branches import (
            ARMATURE_PARITY_SHA256, LEFT_PROBE_SHA256, validate_result)

        if (_sha(Path(blender_left_push_probe.__file__)) != LEFT_PROBE_SHA256 or
                _sha(Path(blender_armature_parity.__file__)) !=
                ARMATURE_PARITY_SHA256):
            raise ValueError("push-branch dependency differs from reviewed pin")
        blender_sha = _sha(Path(bpy.app.binary_path))
        push_branch_repair = reconstruct_push_branches(
            blend=blend, usf=baseline, sdk_root=sdk,
            worker_sha256=args.push_branch_worker_sha256,
            blender_sha256=blender_sha)
        validate_result(push_branch_repair, blender_sha)
        if (push_branch_repair["status"] != "IN_MEMORY_PUSH_BRANCH_MATCH" or
                push_branch_repair["blendSaved"] is not False or
                push_branch_repair["usfExported"] is not False or
                push_branch_repair["nativeBlendExportApproved"] is not False):
            raise RuntimeError("in-memory push-branch reconstruction differs")
        push_branch_repair["workerSha256"] = args.push_branch_worker_sha256
    blade_roll_repair = None
    if args.blade_roll_scratch_repair:
        from blender_blade_roll_worker import run as reconstruct_blade_roll
        from roadcraft.blender_blade_roll import validate_result as validate_roll

        blender_sha = _sha(Path(bpy.app.binary_path))
        blade_roll_repair = reconstruct_blade_roll(
            blend=blend, usf=baseline, sdk_root=sdk,
            worker_sha256=args.blade_roll_worker_sha256,
            blender_sha256=blender_sha,
            loaded_scene=True, push_branches_present=True)
        validate_roll(blade_roll_repair, blender_sha,
                      push_branches_present=True)
        if blade_roll_repair["status"] != "IN_MEMORY_BLADE_ROLL_MATCH":
            raise RuntimeError("in-memory blade-roll reconstruction differs")
        blade_roll_repair["workerSha256"] = args.blade_roll_worker_sha256
    blade_normal_repair = None
    if args.blade_normal_scratch_repair:
        from blender_blade_normal_scratch_repair import (
            blade_normals_by_leaf, install_in_memory_blade_normals,
            require_dependency_pins)
        from roadcraft.blender_blade_normal_projection import (
            LEAVES, NATIVE_PARENT, REPAIRED_PARENT)

        blade_normal_repair = install_in_memory_blade_normals(
            blend=blend, repaired=baseline, native=blade_native,
            native_sha256=args.blade_normal_native_sha256, sdk_root=sdk,
            blender_sha256=_sha(Path(bpy.app.binary_path)),
            blade_roll_present=args.blade_roll_scratch_repair)
        if (blade_normal_repair["status"] !=
                "IN_MEMORY_BLADE_NORMALS_INSTALLED" or
                blade_normal_repair["normalAttributesInLiveScene"] != 60):
            raise RuntimeError("blade normal installation differs")
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
    rgba_guard_detail = None
    if args.rgba_cache_guard:
        with immutable_rgba_cache(UsfMeshColorSet, RGBA_CACHE) as rgba_guard_detail:
            export_to_usf(bpy.context.scene, str(candidate), config)
        if not (rgba_guard_detail["restored"] and
                rgba_guard_detail["cacheClearedAfter"] and
                rgba_guard_detail["packCalls"] > 0):
            raise RuntimeError("RGBA cache guard did not complete")
        rgba_guard_detail["moduleSha256"] = _sha(rgba_guard_file)
        if rgba_guard_detail["moduleSha256"] != args.rgba_cache_guard_sha256 or \
                _sha(sdk_mesh_file) != SDK_MESH_SHA256:
            raise RuntimeError("RGBA cache guard or SDK changed during scratch export")
    else:
        export_to_usf(bpy.context.scene, str(candidate), config)
    if blade_normal_repair is not None:
        blade_normal_repair["normalAttributesAfterExport"] = sum(
            bpy.data.objects[leaf].data.attributes.get("saber_normals") is not None
            for leaf in LEAVES)
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
    if blade_normal_repair is not None:
        candidate_blade_normals = blade_normals_by_leaf(
            native_scene._root_node,
            REPAIRED_PARENT if blade_roll_repair is not None else NATIVE_PARENT)
    if push_branch_repair is not None:
        target_paths = [row["path"] for row in
                        push_branch_repair["targetMatrixErrors"]]
        push_branch_repair["nativeTargetPathsPresent"] = all(
            path in native_rows for path in target_paths)
        push_branch_repair["nativeTargetPathCount"] = sum(
            path in native_rows for path in target_paths)
    if blade_roll_repair is not None:
        target_paths = [row["path"] for row in
                        blade_roll_repair["targetMatrixErrors"]]
        blade_roll_repair["nativeTargetPathsPresent"] = all(
            path in native_rows for path in target_paths)
        blade_roll_repair["nativeTargetPathCount"] = sum(
            path in native_rows for path in target_paths)
        parent = "|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt|BoneBladeRoll_cdt|BoneBlade_cdt"
        blade_roll_repair["nativeBladeMeshPathCount"] = sum(
            parent + f"|cdt_blade_{index}" in native_rows
            for index in range(60))
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
    if blade_normal_repair is not None:
        repaired_blade_normals = blade_normals_by_leaf(
            baseline_scene._root_node, REPAIRED_PARENT)
        blade_normal_repair["nativeNormalMatchesRepaired"] = sum(
            candidate_blade_normals[leaf] == repaired_blade_normals[leaf]
            for leaf in candidate_blade_normals)
    del baseline_scene
    gc.collect()

    if _sha(blend) != blend_before or _sha(baseline) != baseline_before:
        raise RuntimeError("authoring input changed during scratch export")
    if push_branch_repair is not None and (
            _sha(push_host_file) != args.push_branch_host_sha256 or
            _sha(push_worker_file) != args.push_branch_worker_sha256 or
            _sha(Path(blender_left_push_probe.__file__)) != LEFT_PROBE_SHA256 or
            _sha(Path(blender_armature_parity.__file__)) !=
            ARMATURE_PARITY_SHA256):
        raise RuntimeError("push-branch module changed during scratch export")
    if blade_roll_repair is not None and (
            _sha(roll_host_file) != args.blade_roll_host_sha256 or
            _sha(roll_worker_file) != args.blade_roll_worker_sha256):
        raise RuntimeError("blade-roll module changed during scratch export")
    if blade_normal_repair is not None and (
            _sha(blade_repair_file) != args.blade_normal_repair_sha256 or
            _sha(blade_native) != args.blade_normal_native_sha256):
        raise RuntimeError("blade-normal input changed during scratch export")
    if blade_normal_repair is not None:
        require_dependency_pins()
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
        "pushBranchRepair": push_branch_repair,
        "bladeRollRepair": blade_roll_repair,
        "bladeNormalRepair": blade_normal_repair,
    }
    if rgba_guard_detail is not None:
        result["rgbaCacheGuard"] = rgba_guard_detail
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
