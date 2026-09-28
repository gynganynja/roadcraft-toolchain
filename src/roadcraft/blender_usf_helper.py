"""Blender-side, read-only-source USF roundtrip probe.

Run only through blender_bridge.py.  The source is opened for reading by the
SDK parser; the serialized copy and this diagnostic JSON stay in disposable
scratch.  This script never opens, saves, or exports a Blender document.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _semantic_summary(scene) -> dict:
    """Record a bounded structural summary, never claim full semantic parity."""
    totals = {"nodes": 0, "meshNodes": 0, "vertices": 0, "faces": 0,
              "normals": 0, "materialSlots": 0, "uvSets": 0, "colorSets": 0,
              "skinEntries": 0, "skinBones": 0, "animatedNodes": 0,
              "animationSplines": 0, "animationSplineKeys": 0,
              "animationSplineBytes": 0}
    digest = hashlib.sha256()
    critical = {}
    stack = [(scene._root_node, "")]
    while stack:
        node, parent_path = stack.pop()
        node_path = parent_path + "|" + node.name
        totals["nodes"] += 1
        row = {"path": node_path, "uid": node.uid,
               "sourceId": node.source_id, "nodeVersion": node.node_ver,
               "childCount": len(node.children),
               "matrixLocal": [[float(item) for item in line] for line in node.matrix_local],
               "matrixWorld": [[float(item) for item in line] for line in node.matrix_world]}
        mesh = node.mesh
        if mesh is not None:
            totals["meshNodes"] += 1
            counts = {
                "vertices": len(mesh.vertices), "faces": len(mesh.faces),
                "normals": len(mesh.normals),
                "materialSlots": len(mesh.materials.data),
                "uvSets": len(mesh.uvsets.uvs),
                "colorSets": len(mesh.colorsets.sets),
                "skinEntries": len(mesh.skin.skin),
                "skinBones": len(mesh.skin.skin_bones),
            }
            for key, value in counts.items():
                totals[key] += value
            row["mesh"] = counts
            row["materialDigest"] = hashlib.sha256(
                "\x00".join(material.mat for material in mesh.materials.data).encode("utf-8")
            ).hexdigest()
            row["skinBoneUids"] = [bone.usf_node_uid for bone in mesh.skin.skin_bones]
        if node.anim is not None:
            totals["animatedNodes"] += 1
            splines = []
            for name in ("spl_translate", "spl_rotation", "spl_scale", "spl_visibility"):
                spline = getattr(node.anim, name)
                if spline is not None:
                    totals["animationSplines"] += 1
                    totals["animationSplineKeys"] += spline.keys_count
                    totals["animationSplineBytes"] += len(spline.data)
                    splines.append({"name": name, "keys": spline.keys_count,
                                    "bytes": len(spline.data),
                                    "dataSha256": hashlib.sha256(spline.data).hexdigest()})
            row["animation"] = splines
        serialized = json.dumps(row, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False).encode("utf-8")
        digest.update(len(serialized).to_bytes(8, "little"))
        digest.update(serialized)
        if node.name in ("Body_vis", "Body_vis_LOD1", "Body_vis_LOD2",
                         "BoneBlade_cdt", "_cockpit_camera"):
            critical[node_path] = {"uid": node.uid,
                                   "mesh": row.get("mesh"),
                                   "animation": row.get("animation")}
        stack.extend((child, node_path) for child in reversed(node.children))
    return {**totals, "structuralDigest": digest.hexdigest(),
            "criticalNodes": critical}


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    args = parser.parse_args(argv)

    source = args.source.resolve(strict=True)
    scratch = args.scratch_root.resolve(strict=True)
    output = args.output.resolve()
    receipt = args.receipt.resolve()
    sdk_script = args.sdk_script_root.resolve(strict=True)
    if (not source.is_file() or source.suffix.lower() != ".usf" or
            not output.is_relative_to(scratch) or not receipt.is_relative_to(scratch) or
            output == source or receipt == source or output.exists() or receipt.exists()):
        raise ValueError("source or disposable output paths are invalid")
    before = _sha(source)
    if before != args.source_sha256.lower():
        raise ValueError("repaired USF changed before Blender read")

    sys.path.insert(0, str(sdk_script))
    from saber.blender.lib.binary_io import BinaryIO  # noqa: E402
    from saber.blender.lib.usf.scene import usf_read, usf_save  # noqa: E402

    # The SDK reader calls read_bytearray(size), while this bundled BinaryIO
    # method is written with no size argument.  The established D11 audit uses
    # this scoped compatibility shim before parsing animation spline payloads.
    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )

    header, scene = usf_read(str(source))
    source_semantic = _semantic_summary(scene)
    usf_save(str(output), header, scene)
    del header, scene
    gc.collect()
    written_header, written_scene = usf_read(str(output))
    output_semantic = _semantic_summary(written_scene)
    del written_header, written_scene
    gc.collect()

    if _sha(source) != before:
        raise RuntimeError("repaired USF changed during Blender roundtrip")
    result = {
        "schemaVersion": 1,
        "sourceSha256": before,
        "sourceBytes": source.stat().st_size,
        "outputSha256": _sha(output),
        "outputBytes": output.stat().st_size,
        "sourceSemantic": source_semantic,
        "outputSemantic": output_semantic,
        "semanticSummaryEqual": source_semantic == output_semantic,
    }
    result["byteIdentical"] = (result["sourceSha256"] == result["outputSha256"] and
                               result["sourceBytes"] == result["outputBytes"])
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print("ROADCRAFT_USF_ROUNDTRIP " + json.dumps({
        "byteIdentical": result["byteIdentical"],
        "semanticSummaryEqual": result["semanticSummaryEqual"],
        "sourceSha256": before,
        "outputSha256": result["outputSha256"],
        "nodes": source_semantic["nodes"],
        "faces": source_semantic["faces"],
    }), flush=True)


if __name__ == "__main__":
    main()
