"""Pinned, no-save comparison of D11 source mesh payload and retained USF.

This projects meshes through the reviewed SDK in memory. It neither writes a
USF nor decides whether native-Blend export is allowed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_blade_relocation import (
    BladeRelocationError, _rows_and_native,
)
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import (
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256, WORKLIST,
    WORKLIST_SHA256, MeshInventoryError, _worklist_rows,
)
from .blender_mesh_inventory import WORKER as MAPPER_WORKER
from .blender_mesh_inventory import WORKER_SHA256 as MAPPER_WORKER_SHA256
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_mesh_payload_worker.py")
WORKER_SHA256 = "f34d24f4c29628adc51e6483d002a602c11948205ee5b282b94912c379a9a553"
RESULT_PREFIX = "ROADCRAFT_MESH_PAYLOAD "
FIELD_NAMES = ("positions", "normals", "faceMaterialEdges", "uvCoordinates",
               "packedColors", "skinIndicesWeights")
EXPECTED_ROWS = 126
MAX_JSON_BYTES = 384 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class MeshPayloadError(RuntimeError):
    """A pinned input, full coverage, or payload readback differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _float32(value: object, label: str) -> bytes:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite")
        return struct.pack("<f", number)
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise MeshPayloadError(f"invalid {label} float32") from exc


def _int32(value: object, label: str, *, signed: bool) -> bytes:
    if type(value) is not int or value < 0:
        raise MeshPayloadError(f"invalid {label} index")
    try:
        return struct.pack("<i" if signed else "<I", value)
    except struct.error as exc:
        raise MeshPayloadError(f"out-of-range {label} index") from exc


def _vector_digest(values, width: int, label: str) -> dict:
    digest = hashlib.sha256()
    count = len(values)
    digest.update(struct.pack("<Q", count))
    for vector in values:
        if len(vector) != width:
            raise MeshPayloadError(f"invalid {label} vector width")
        for component in vector:
            digest.update(_float32(component, label))
    return {"elements": count, "sha256": digest.hexdigest()}


def summarize_mesh(mesh) -> dict:
    """Digest the SDK's USF-writing values, excluding known drifting tangents.

    The same function handles a retained USF mesh and `UsfMesh.b_read(obj)`.
    `<f` is the SDK's float32 wire precision. No bytes or arrays are emitted.
    """
    positions = _vector_digest(mesh.vertices, 3, "position")
    normals = _vector_digest(mesh.normals, 3, "normal")

    digest = hashlib.sha256()
    faces = mesh.faces
    digest.update(struct.pack("<Q", len(faces)))
    for face in faces:
        digest.update(_int32(face.material_index, "face material", signed=False))
        digest.update(_int32(face.edge_index, "face edge", signed=False))
    face_summary = {"elements": len(faces), "sha256": digest.hexdigest()}

    digest = hashlib.sha256()
    uvs = mesh.uvsets.uvs
    digest.update(struct.pack("<Q", len(uvs)))
    uv_names = []
    uv_entries = 0
    for uv in uvs:
        if not isinstance(uv.name, str) or len(uv.name) > 256:
            raise MeshPayloadError("invalid UV layer name")
        name = uv.name.encode("utf-8")
        digest.update(struct.pack("<I", len(name)))
        digest.update(name)
        digest.update(struct.pack("<Q", len(uv.co)))
        uv_names.append(uv.name)
        uv_entries += len(uv.co)
        for value in uv.co:
            if len(value) != 2:
                raise MeshPayloadError("invalid UV vector width")
            for component in value:
                digest.update(_float32(component, "UV"))
    uv_summary = {"elements": uv_entries, "sets": len(uvs),
                  "names": uv_names, "sha256": digest.hexdigest()}

    digest = hashlib.sha256()
    color_sets = mesh.colorsets.sets
    digest.update(struct.pack("<Q", len(color_sets)))
    color_entries = 0
    for color_set in color_sets:
        digest.update(struct.pack("<Q", len(color_set.colors)))
        color_entries += len(color_set.colors)
        for color in color_set.colors:
            digest.update(_int32(color, "packed color", signed=False))
    color_summary = {"elements": color_entries, "sets": len(color_sets),
                     "sha256": digest.hexdigest()}

    digest = hashlib.sha256()
    skin = mesh.skin
    bpv = skin.bones_per_vertex
    digest.update(_int32(bpv, "bones per vertex", signed=False))
    digest.update(struct.pack("<Q", len(skin.skin)))
    for vertex in skin.skin:
        if len(vertex.bone_idx) != bpv or len(vertex.weight) != bpv:
            raise MeshPayloadError("invalid skin vertex width")
        for index in vertex.bone_idx:
            digest.update(_int32(index, "skin bone", signed=True))
        for weight in vertex.weight:
            digest.update(_float32(weight, "skin weight"))
    skin_summary = {"elements": len(skin.skin), "bonesPerVertex": bpv,
                    "sha256": digest.hexdigest()}

    return {"positions": positions, "normals": normals,
            "faceMaterialEdges": face_summary, "uvCoordinates": uv_summary,
            "packedColors": color_summary, "skinIndicesWeights": skin_summary}


def _validate_component(value: object, name: str) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("source"), dict) or \
            not isinstance(value.get("native"), dict):
        raise MeshPayloadError(f"incomplete {name} component")
    source, native = value["source"], value["native"]
    required = {"elements", "sha256"}
    if name in ("uvCoordinates", "packedColors"):
        required.add("sets")
    if name == "uvCoordinates":
        required.add("names")
    if name == "skinIndicesWeights":
        required.add("bonesPerVertex")
    for side in (source, native):
        if set(side) != required:
            raise MeshPayloadError(f"unexpected {name} component fields")
        if (type(side["elements"]) is not int or side["elements"] < 0 or
                not isinstance(side["sha256"], str) or
                HEX_SHA256.fullmatch(side["sha256"]) is None):
            raise MeshPayloadError(f"invalid {name} digest or count")
        for field in {"sets", "bonesPerVertex"} & required:
            if type(side[field]) is not int or side[field] < 0:
                raise MeshPayloadError(f"invalid {name} {field}")
        if "names" in required and (
                not isinstance(side["names"], list) or
                len(side["names"]) != side["sets"] or
                any(not isinstance(v, str) or len(v) > 256 for v in side["names"])):
            raise MeshPayloadError("invalid UV names")
    if type(value.get("match")) is not bool or value["match"] != (source == native):
        raise MeshPayloadError(f"{name} match flag contradicts payload digests")
    return value


def interpret_readback(result: dict, gap_rows: list[dict], blender_sha: str,
                       native_sha: str, summary_sha: str, host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha, "worklistSha256": WORKLIST_SHA256,
        "summarySha256": summary_sha, "blenderSha256": blender_sha,
        "hostSha256": host_sha, "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise MeshPayloadError("readback identity or no-write fields differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise MeshPayloadError("Blender version differs")
    rows = result.get("rows")
    if (not isinstance(rows, list) or len(rows) != len(gap_rows) or
            len(rows) != EXPECTED_ROWS):
        raise MeshPayloadError("mesh payload row coverage differs")
    seen = set()
    field_matches = {name: 0 for name in FIELD_NAMES}
    checked = []
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or set(row) != {"path", "sourceObject", "fields"} or
                row["path"] != gap["path"] or
                not isinstance(row["sourceObject"], str) or
                row["sourceObject"] in seen or
                not isinstance(row["fields"], dict) or
                set(row["fields"]) != set(FIELD_NAMES)):
            raise MeshPayloadError("mesh payload path, mapping or field coverage differs")
        seen.add(row["sourceObject"])
        for name in FIELD_NAMES:
            item = _validate_component(row["fields"][name], name)
            field_matches[name] += item["match"]
        checked.append(row)
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_NATIVE_MESH_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"],
        "mappedRows": len(checked),
        "matchingRowsByField": field_matches,
        "allComparedFieldsMatchRows": sum(all(row["fields"][field]["match"]
                                           for field in FIELD_NAMES)
                                         for row in checked),
        "rowsDigestSha256": hashlib.sha256(_canonical(checked)).hexdigest(),
        "tangentsCompared": False,
        "materialPayloadCompared": False,
        "inverseBindMatricesCompared": False,
        "rows": checked,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise MeshPayloadError("bounded mesh payload result exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict], blender_sha: str,
                 native_sha: str, summary_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise MeshPayloadError("Blender did not emit one bounded payload readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise MeshPayloadError("Blender payload readback is malformed") from exc
    return interpret_readback(raw, gap_rows, blender_sha, native_sha,
                              summary_sha, host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise MeshPayloadError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise MeshPayloadError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise MeshPayloadError("authoring inventory is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256,
                            "reconstruction worklist")
    parsed = json.loads(worklist.read_text(encoding="utf-8"))
    gap_rows = _worklist_rows(parsed, asset["assetDigest"])
    _, native, native_sha, summary_path, summary_sha = _rows_and_native(
        parsed, asset["assetDigest"], blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise MeshPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    mapper_worker = require_hash(MAPPER_WORKER, MAPPER_WORKER_SHA256,
                                 "mesh path mapper worker")
    worker = require_hash(WORKER, WORKER_SHA256, "mesh payload worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--mapper-sha256",
               MAPPER_WORKER_SHA256, "--host-sha256", host_sha,
               "--blender-sha256", blender_sha, "--native-usf-sha256",
               native_sha, "--summary-sha256", summary_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise MeshPayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, gap_rows, blender_sha,
                          native_sha, summary_sha, host_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256, "authoring inventory after")
    if _unlinked_path(Path(inventory["sourceRoot"]), "source root after") != source_root:
        raise MeshPayloadError("source root changed during readback")
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary_path, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (mapper_worker, MAPPER_WORKER_SHA256, "path mapper worker"),
            (worker, WORKER_SHA256, "payload worker"),
            (Path(__file__), host_sha, "payload host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256,
                   "workerSha256": WORKER_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise MeshPayloadError("bounded final mesh payload result exceeded")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (MeshPayloadError, MeshInventoryError, BladeRelocationError,
            LeftPushProbeError, BlenderAuthoringError, OSError, ValueError,
            KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
