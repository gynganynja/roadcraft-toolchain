"""Blender worker: parse two pinned USFs and compare blade payloads in memory."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import bpy

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadcraft.blender_blade_geometry import (  # noqa: E402
    BLENDER_VERSION_PINS, EXPECTED_CORNERS, LEAVES, MAX_JSON_BYTES,
    NATIVE_PARENT, REPAIRED_PARENT, RESULT_PREFIX, USF_SHA256,
    BladeGeometryError, _aggregate, _require, compare_arrays,
    require_hash, require_sdk_pins,
)


NATIVE_USF_SHA256 = "80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370"


def _nodes(path: Path, parent_path: str) -> dict:
    from saber.blender.lib.usf.scene import usf_read

    _, scene = usf_read(str(path))
    root = scene._root_node
    _require(root.name == "cat_d11t", f"USF root differs: {path.name}")
    target_paths = {parent_path + "|" + leaf: leaf for leaf in LEAVES}
    found = {}
    stack = [(root, "|@root")]
    while stack:
        node, node_path = stack.pop()
        if node_path in target_paths:
            _require(node_path not in found and node.mesh is not None,
                     f"blade path missing mesh or duplicated: {node_path}")
            found[node_path] = node
        for child in node.children:
            stack.append((child, node_path + "|" + child.name))
    _require(set(found) == set(target_paths),
             f"blade exact-path coverage differs: {path.name}")
    return found


def run(*, native: Path, repaired: Path, sdk_root: Path,
        blender_sha: str, worker_sha: str, host_sha: str) -> dict:
    _require(blender_sha in BLENDER_VERSION_PINS, "Blender pin differs")
    _require(bpy.app.version_string.startswith(BLENDER_VERSION_PINS[blender_sha]),
             "Blender version differs")
    _require(not bpy.data.filepath, "startup scene must not load a Blend")
    require_hash(Path(bpy.app.binary_path), blender_sha, "Blender executable")
    require_hash(Path(__file__), worker_sha, "geometry worker")
    host = Path(__file__).with_name("blender_blade_geometry.py")
    require_hash(host, host_sha, "geometry host")
    require_hash(native, NATIVE_USF_SHA256, "retained native USF")
    require_hash(repaired, USF_SHA256, "repaired USF")
    sdk = require_sdk_pins(sdk_root)

    sys.path.insert(0, str(sdk))
    from saber.blender.lib.binary_io import BinaryIO

    original_reader = BinaryIO.read_bytearray
    BinaryIO.read_bytearray = (
        lambda self, size=None: self.io.read(size) if size is not None
        else original_reader(self)
    )
    try:
        native_nodes = _nodes(native, NATIVE_PARENT)
        repaired_nodes = _nodes(repaired, REPAIRED_PARENT)
    finally:
        BinaryIO.read_bytearray = original_reader
    rows = []
    for leaf in LEAVES:
        native_path = NATIVE_PARENT + "|" + leaf
        repaired_path = REPAIRED_PARENT + "|" + leaf
        before = native_nodes[native_path]
        after = repaired_nodes[repaired_path]
        measured = compare_arrays(
            before.mesh.vertices, after.mesh.vertices,
            before.mesh.normals, after.mesh.normals,
            before.matrix_world, after.matrix_world,
            before.matrix_local, after.matrix_local,
        )
        rows.append({"leafName": leaf, "nativePath": native_path,
                     "repairedPath": repaired_path, **measured})
    _require(sum(row["corners"] for row in rows) == EXPECTED_CORNERS,
             "blade corner total differs")
    for path, digest, label in (
            (native, NATIVE_USF_SHA256, "native USF"),
            (repaired, USF_SHA256, "repaired USF"),
            (Path(__file__), worker_sha, "worker"),
            (host, host_sha, "host"),
            (Path(bpy.app.binary_path), blender_sha, "Blender")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "status": "BLADE_GEOMETRY_READBACK",
        "nativeUsfSha256": NATIVE_USF_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "blenderSha256": blender_sha,
        "blenderVersion": bpy.app.version_string,
        "workerSha256": worker_sha, "hostSha256": host_sha,
        "nativeBlendExportApproved": False,
        "blendSaved": False, "usfExported": False,
        "equivalenceVerified": False,
        "summary": _aggregate(rows), "rows": rows,
    }
    _require(len(json.dumps(result, sort_keys=True, allow_nan=False)) <= MAX_JSON_BYTES,
             "bounded blade geometry result exceeded")
    return result


def main() -> None:
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-usf", type=Path, required=True)
    parser.add_argument("--repaired-usf", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--native-usf-sha256", required=True)
    parser.add_argument("--blender-sha256", required=True)
    parser.add_argument("--worker-sha256", required=True)
    parser.add_argument("--host-sha256", required=True)
    values = parser.parse_args(args)
    _require(values.native_usf_sha256 == NATIVE_USF_SHA256,
             "native USF pin differs")
    result = run(native=values.native_usf, repaired=values.repaired_usf,
                 sdk_root=values.sdk_script_root,
                 blender_sha=values.blender_sha256,
                 worker_sha=values.worker_sha256,
                 host_sha=values.host_sha256)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True, allow_nan=False),
          flush=True)
    gc.collect()


if __name__ == "__main__":
    main()
