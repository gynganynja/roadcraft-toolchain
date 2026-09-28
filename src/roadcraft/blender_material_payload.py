"""Pinned, no-save D11 source/native/repaired material-payload readback.

This inspects the Saber SDK's in-memory mesh material projection and parsed
USFs. It never serializes a USF or changes the approved build method.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_blade_relocation import BladeRelocationError, _rows_and_native
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
WORKER = Path(__file__).with_name("blender_material_payload_worker.py")
WORKER_SHA256 = "26020a54b4278dc0285784668eddb83fc62b86182642408c3998e04c514c7bcc"
RESULT_PREFIX = "ROADCRAFT_MATERIAL_PAYLOAD "
EXPECTED_ROWS = 126
MAX_JSON_BYTES = 2 * 1024 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MATERIAL_NAME = re.compile(r'material\s*=\s*\{\s*name\s*=\s*"([^"\r\n]+)"')
TEXTURE_NAME = re.compile(r'textureName\s*=\s*"([^"\r\n]*)"')
ALBEDO_TINT = re.compile(r'albedo_tint\s*=\s*(\[[^\]\r\n]*\])')


class MaterialPayloadError(RuntimeError):
    """A pinned input, complete mapping, or material readback differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _material_text(material) -> str:
    text = material.build_string() if callable(getattr(material, "build_string", None)) else material.mat
    if not isinstance(text, str) or len(text) > 256 * 1024:
        raise MaterialPayloadError("invalid or oversized SDK material text")
    return text


def summarize_materials(mesh) -> dict:
    """Summarize ordered SDK material structs and face-to-slot indices.

    Full text digests cover the entire SDK material string, including shader
    defaults and parameters. Extracted texture names are references, not image
    bytes, paths, or proof the image was packed in the Blend.
    """
    slots = []
    materials = mesh.materials.data
    if not isinstance(materials, list) or not 1 <= len(materials) <= 1024:
        raise MaterialPayloadError("invalid material slot count")
    for material in materials:
        text = _material_text(material)
        name = MATERIAL_NAME.search(text)
        if name is None or len(name[1]) > 256:
            raise MaterialPayloadError("material payload has no bounded name")
        textures = [value for value in TEXTURE_NAME.findall(text) if value]
        if len(textures) > 1024 or any(len(value) > 256 for value in textures):
            raise MaterialPayloadError("oversized material texture references")
        tints = ALBEDO_TINT.findall(text)
        if len(tints) > 1024 or any(len(value) > 128 for value in tints):
            raise MaterialPayloadError("oversized albedo tint list")
        version = material.ver
        vc_usage = material.vc_usage
        if (type(version) is not int or type(vc_usage) is not int or
                not 0 <= version < 2**31 or not 0 <= vc_usage < 2**31):
            raise MaterialPayloadError("invalid SDK material struct metadata")
        slots.append({
            "name": name[1], "textureReferences": textures,
            "albedoTints": tints, "version": version, "vcUsage": vc_usage,
            "fullTextSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })
    digest = hashlib.sha256()
    count = 0
    for face in mesh.faces:
        index = face.material_index
        if type(index) is not int or not 0 <= index < len(slots):
            raise MaterialPayloadError("face references invalid material slot")
        digest.update(struct.pack("<I", index))
        count += 1
    return {
        "slotCount": len(slots), "slots": slots,
        "orderedSlotsSha256": _sha(slots),
        "faceMaterialIndices": {"count": count, "sha256": digest.hexdigest()},
    }


def _validate_summary(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
            "slotCount", "slots", "orderedSlotsSha256", "faceMaterialIndices"}:
        raise MaterialPayloadError("incomplete material summary")
    count, slots = value["slotCount"], value["slots"]
    if (type(count) is not int or not 1 <= count <= 1024 or
            not isinstance(slots, list) or len(slots) != count):
        raise MaterialPayloadError("invalid material slot coverage")
    for slot in slots:
        if not isinstance(slot, dict) or set(slot) != {
                "name", "textureReferences", "albedoTints", "version",
                "vcUsage", "fullTextSha256"}:
            raise MaterialPayloadError("incomplete material slot")
        if (not isinstance(slot["name"], str) or not 0 < len(slot["name"]) <= 256 or
                type(slot["version"]) is not int or not 0 <= slot["version"] < 2**31 or
                type(slot["vcUsage"]) is not int or not 0 <= slot["vcUsage"] < 2**31 or
                not isinstance(slot["fullTextSha256"], str) or
                HEX_SHA256.fullmatch(slot["fullTextSha256"]) is None):
            raise MaterialPayloadError("invalid material slot metadata")
        for key, max_len in (("textureReferences", 256), ("albedoTints", 128)):
            values = slot[key]
            if (not isinstance(values, list) or len(values) > 1024 or
                    any(not isinstance(item, str) or len(item) > max_len
                        for item in values)):
                raise MaterialPayloadError("invalid material text extract")
    if value["orderedSlotsSha256"] != _sha(slots):
        raise MaterialPayloadError("ordered material slot digest contradicts slots")
    faces = value["faceMaterialIndices"]
    if (not isinstance(faces, dict) or set(faces) != {"count", "sha256"} or
            type(faces["count"]) is not int or faces["count"] < 0 or
            not isinstance(faces["sha256"], str) or
            HEX_SHA256.fullmatch(faces["sha256"]) is None):
        raise MaterialPayloadError("invalid face material index digest")
    return value


def _missing_names(source: dict, repaired: dict) -> list[str]:
    source_names = Counter(slot["name"] for slot in source["slots"])
    repaired_names = Counter(slot["name"] for slot in repaired["slots"])
    return sorted((repaired_names - source_names).elements())


def interpret_readback(result: dict, gap_rows: list[dict], blender_sha: str,
                       native_sha: str, summary_sha: str, host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha, "worklistSha256": WORKLIST_SHA256,
        "summarySha256": summary_sha, "blenderSha256": blender_sha,
        "hostSha256": host_sha, "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedUsfRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise MaterialPayloadError("material readback identity or no-write field differs")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise MaterialPayloadError("Blender version differs")
    rows = result.get("rows")
    if (not isinstance(rows, list) or len(rows) != len(gap_rows) or
            len(rows) != EXPECTED_ROWS):
        raise MaterialPayloadError("material row coverage differs")
    checked = []
    seen = set()
    source_native_exact = 0
    source_native_names = 0
    source_native_textures = 0
    source_native_faces = 0
    source_repaired_exact = 0
    missing_repaired_count = 0
    for row, gap in zip(rows, gap_rows):
        if (not isinstance(row, dict) or set(row) != {
                "path", "sourceObject", "source", "native", "repaired"} or
                row["path"] != gap["path"] or
                not isinstance(row["sourceObject"], str) or
                row["sourceObject"] in seen):
            raise MaterialPayloadError("material path or source mapping differs")
        seen.add(row["sourceObject"])
        source, native, repaired = (_validate_summary(row[key]) for key in
                                    ("source", "native", "repaired"))
        source_native_exact += source["slots"] == native["slots"]
        source_native_names += ([slot["name"] for slot in source["slots"]] ==
                                [slot["name"] for slot in native["slots"]])
        source_native_textures += ([slot["textureReferences"] for slot in source["slots"]] ==
                                   [slot["textureReferences"] for slot in native["slots"]])
        source_native_faces += source["faceMaterialIndices"] == native["faceMaterialIndices"]
        source_repaired_exact += source["slots"] == repaired["slots"]
        missing_repaired_count += len(_missing_names(source, repaired))
        checked.append(row)
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_NATIVE_MATERIAL_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"],
        "mappedRows": len(checked),
        "sourceNativeExactMaterialRows": source_native_exact,
        "sourceNativeOrderedNameRows": source_native_names,
        "sourceNativeTextureReferenceRows": source_native_textures,
        "sourceNativeFaceMappingRows": source_native_faces,
        "sourceRepairedExactMaterialRows": source_repaired_exact,
        "repairedOnlyMaterialLabelOccurrences": missing_repaired_count,
        "rowsDigestSha256": _sha(checked),
        "textureBytesCompared": False,
        "shaderGraphSemanticsCompared": False,
        "nativeBlendExportApproved": False,
        "rows": checked,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise MaterialPayloadError("bounded material result exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict], blender_sha: str,
                 native_sha: str, summary_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > MAX_JSON_BYTES:
        raise MaterialPayloadError("Blender did not emit one bounded material readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise MaterialPayloadError("Blender material readback is malformed") from exc
    return interpret_readback(raw, gap_rows, blender_sha, native_sha,
                              summary_sha, host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise MaterialPayloadError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise MaterialPayloadError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise MaterialPayloadError("authoring inventory is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    parsed = json.loads(worklist.read_text(encoding="utf-8"))
    gap_rows = _worklist_rows(parsed, asset["assetDigest"])
    _, native, native_sha, summary_path, summary_sha = _rows_and_native(
        parsed, asset["assetDigest"], blend, repaired)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise MaterialPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    mapper_worker = require_hash(MAPPER_WORKER, MAPPER_WORKER_SHA256,
                                 "mesh path mapper worker")
    worker = require_hash(WORKER, WORKER_SHA256, "material payload worker")
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
        raise MaterialPayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, gap_rows, blender_sha,
                          native_sha, summary_sha, host_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256, "authoring inventory after")
    if _unlinked_path(Path(inventory["sourceRoot"]), "source root after") != source_root:
        raise MaterialPayloadError("source root changed during readback")
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary_path, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (mapper_worker, MAPPER_WORKER_SHA256, "path mapper worker"),
            (worker, WORKER_SHA256, "material worker"),
            (Path(__file__), host_sha, "material host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True, "repairedUsfUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256,
                   "workerSha256": WORKER_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise MaterialPayloadError("bounded final material result exceeded")
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
    except (MaterialPayloadError, MeshInventoryError, BladeRelocationError,
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
