"""Pinned, no-save D11 source/native tangent comparison.

The SDK projects the historical Blend mesh in memory; neither this host nor
its worker accepts an asset output path or calls a USF writer.
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
from .blender_blade_relocation import BladeRelocationError, _rows_and_native
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import (
    BLEND_SHA256, BLENDER_VERSION_PINS, USF_SHA256, WORKLIST,
    WORKLIST_SHA256, MeshInventoryError, _worklist_rows,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_tangent_payload_worker.py")
WORKER_SHA256 = "12fe33903af200229f989f7ca707b786bad5b8fd0e869aa9645ca99a062a3058"
MAPPER_HOST = Path(__file__).with_name("blender_mesh_inventory.py")
MAPPER_HOST_SHA256 = "32db82dd01e40d5808d830564f999489c0f80fc373c34b8665b88fd462fd68e2"
MAPPER_WORKER = Path(__file__).with_name("blender_mesh_inventory_worker.py")
MAPPER_WORKER_SHA256 = "e29122c28bbe60a254a7c239fcc84be7d2f05a57c0ce305132069edd5b264113"
PAYLOAD_HOST = Path(__file__).with_name("blender_mesh_payload.py")
PAYLOAD_HOST_SHA256 = "2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e"
PAYLOAD_WORKER = Path(__file__).with_name("blender_mesh_payload_worker.py")
PAYLOAD_WORKER_SHA256 = "f34d24f4c29628adc51e6483d002a602c11948205ee5b282b94912c379a9a553"
RESULT_PREFIX = "ROADCRAFT_TANGENT_PAYLOAD "
COMPONENTS = ("x", "y", "z", "sign")
EXPECTED_ROWS = 126
MAX_JSON_BYTES = 384 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class TangentPayloadError(RuntimeError):
    """Pinned inputs, full coverage, or tangent comparison differ."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _f32(value: object) -> tuple[bytes, float]:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite")
        packed = struct.pack("<f", number)
        return packed, struct.unpack("<f", packed)[0]
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise TangentPayloadError("non-finite or invalid tangent float32") from exc


def _layers(mesh) -> list[list[tuple[bytes, float]]]:
    """Return ordered float32 values from the SDK's in-memory tangent arrays."""
    layers = []
    if len(mesh.uvsets.tangents) != len(mesh.uvsets.uvs):
        raise TangentPayloadError("tangent/UV layer counts differ")
    for index, layer in enumerate(mesh.uvsets.tangents):
        if len(layer) != len(mesh.uvsets.uvs[index].co) or len(layer) != len(mesh.vertices):
            raise TangentPayloadError("tangent/UV/vertex lengths differ")
        vectors = []
        for vector in layer:
            if len(vector) != 4:
                raise TangentPayloadError("tangent vector is not float4")
            vectors.append(tuple(_f32(component) for component in vector))
        layers.append(vectors)
    return layers


def summarize_tangents(layers: list) -> dict:
    lengths = [len(layer) for layer in layers]
    component_hashes = {name: hashlib.sha256() for name in COMPONENTS}
    all_hash = hashlib.sha256()
    all_hash.update(struct.pack("<Q", len(layers)))
    for length in lengths:
        marker = struct.pack("<Q", length)
        all_hash.update(marker)
        for digest in component_hashes.values():
            digest.update(marker)
    for layer in layers:
        for vector in layer:
            for name, (packed, _) in zip(COMPONENTS, vector):
                component_hashes[name].update(packed)
                all_hash.update(packed)
    return {"layerLengths": lengths, "vectors": sum(lengths),
            "sha256": all_hash.hexdigest(),
            "componentSha256": {name: digest.hexdigest()
                                 for name, digest in component_hashes.items()}}


def compare_tangents(source_mesh, native_mesh) -> dict:
    source_layers = _layers(source_mesh)
    native_layers = _layers(native_mesh)
    source = summarize_tangents(source_layers)
    native = summarize_tangents(native_layers)
    if source["layerLengths"] != native["layerLengths"]:
        raise TangentPayloadError("source/native tangent shape differs")
    differing = {name: 0 for name in COMPONENTS}
    max_absolute = {name: 0.0 for name in COMPONENTS}
    for source_layer, native_layer in zip(source_layers, native_layers):
        for source_vector, native_vector in zip(source_layer, native_layer):
            for name, (a_bytes, a_value), (b_bytes, b_value) in zip(
                    COMPONENTS, source_vector, native_vector):
                if a_bytes != b_bytes:
                    differing[name] += 1
                    max_absolute[name] = max(max_absolute[name],
                                             abs(a_value - b_value))
    for name in COMPONENTS:
        if (source["componentSha256"][name] == native["componentSha256"][name]) != (
                differing[name] == 0):
            raise TangentPayloadError("component digest/count contradiction")
    return {"source": source, "native": native,
            "differingValues": differing,
            "maxAbsoluteDifference": max_absolute,
            "match": source == native}


def _validate_row(row: object, path: str, seen: set[str]) -> dict:
    if (not isinstance(row, dict) or
            set(row) != {"path", "sourceObject", "tangents"} or
            row["path"] != path or
            not isinstance(row["sourceObject"], str) or
            not row["sourceObject"] or row["sourceObject"] in seen):
        raise TangentPayloadError("tangent path or source-object coverage differs")
    seen.add(row["sourceObject"])
    item = row["tangents"]
    if (not isinstance(item, dict) or
            set(item) != {"source", "native", "differingValues",
                          "maxAbsoluteDifference", "match"}):
        raise TangentPayloadError("incomplete tangent comparison")
    for side_name in ("source", "native"):
        side = item[side_name]
        if (not isinstance(side, dict) or
                set(side) != {"layerLengths", "vectors", "sha256",
                              "componentSha256"} or
                not isinstance(side["layerLengths"], list) or
                len(side["layerLengths"]) > 16 or
                any(type(n) is not int or n < 0 for n in side["layerLengths"]) or
                type(side["vectors"]) is not int or
                side["vectors"] != sum(side["layerLengths"]) or
                not isinstance(side["sha256"], str) or
                HEX_SHA256.fullmatch(side["sha256"]) is None or
                not isinstance(side["componentSha256"], dict) or
                set(side["componentSha256"]) != set(COMPONENTS) or
                any(not isinstance(digest, str) or
                    HEX_SHA256.fullmatch(digest) is None
                    for digest in side["componentSha256"].values())):
            raise TangentPayloadError("invalid tangent side summary")
    if item["source"]["layerLengths"] != item["native"]["layerLengths"]:
        raise TangentPayloadError("source/native tangent shapes differ")
    if (not isinstance(item["differingValues"], dict) or
            set(item["differingValues"]) != set(COMPONENTS) or
            not isinstance(item["maxAbsoluteDifference"], dict) or
            set(item["maxAbsoluteDifference"]) != set(COMPONENTS)):
        raise TangentPayloadError("incomplete per-component tangent differences")
    for name in COMPONENTS:
        count = item["differingValues"][name]
        magnitude = item["maxAbsoluteDifference"][name]
        if (type(count) is not int or count < 0 or
                count > item["source"]["vectors"] or
                type(magnitude) not in (int, float) or
                not math.isfinite(magnitude) or magnitude < 0 or
                (count == 0 and magnitude != 0) or
                (count == 0) != (
                    item["source"]["componentSha256"][name] ==
                    item["native"]["componentSha256"][name])):
            raise TangentPayloadError("contradictory tangent component")
    if (type(item["match"]) is not bool or
            item["match"] != (item["source"] == item["native"]) or
            item["match"] != all(count == 0 for count in
                                 item["differingValues"].values())):
        raise TangentPayloadError("tangent match flag contradicts components")
    return row


def interpret_readback(result: dict, gap_rows: list[dict], blender_sha: str,
                       native_sha: str, summary_sha: str, host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": native_sha,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": summary_sha,
        "blenderSha256": blender_sha, "hostSha256": host_sha,
        "workerSha256": WORKER_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "payloadWorkerSha256": PAYLOAD_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
    }
    if (not isinstance(result, dict) or
            any(type(result.get(key)) is not type(value) or
                result.get(key) != value for key, value in expected.items())):
        raise TangentPayloadError("tangent readback identity or no-write fields differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise TangentPayloadError("Blender version differs")
    rows = result.get("rows")
    if (not isinstance(rows, list) or len(rows) != len(gap_rows) or
            len(rows) != EXPECTED_ROWS):
        raise TangentPayloadError("tangent row coverage differs")
    seen = set()
    checked = [_validate_row(row, gap["path"], seen)
               for row, gap in zip(rows, gap_rows)]
    counts = {name: sum(row["tangents"]["differingValues"][name]
                        for row in checked) for name in COMPONENTS}
    maxima = {name: max(row["tangents"]["maxAbsoluteDifference"][name]
                        for row in checked) for name in COMPONENTS}
    compact = {key: result[key] for key in expected}
    compact.update({
        "status": "SOURCE_NATIVE_TANGENT_PAYLOAD_READBACK",
        "blenderVersion": result["blenderVersion"],
        "mappedRows": len(checked),
        "matchingRows": sum(row["tangents"]["match"] for row in checked),
        "differingValuesByComponent": counts,
        "maxAbsoluteDifferenceByComponent": maxima,
        "rowsDigestSha256": hashlib.sha256(_canonical(checked)).hexdigest(),
        "materialPayloadCompared": False,
        "inverseBindMatricesCompared": False,
        "rows": checked,
    })
    if len(_canonical(compact)) > MAX_JSON_BYTES:
        raise TangentPayloadError("bounded tangent result exceeded")
    return compact


def parse_result(stdout: str, gap_rows: list[dict], blender_sha: str,
                 native_sha: str, summary_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise TangentPayloadError("Blender did not emit one bounded tangent readback")
    try:
        raw = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise TangentPayloadError("Blender tangent readback is malformed") from exc
    return interpret_readback(raw, gap_rows, blender_sha, native_sha,
                              summary_sha, host_sha)


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise TangentPayloadError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise TangentPayloadError("accepted authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise TangentPayloadError("authoring inventory is outside checkout")
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
        raise TangentPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    inputs = ((MAPPER_HOST, MAPPER_HOST_SHA256, "mapper host"),
              (MAPPER_WORKER, MAPPER_WORKER_SHA256, "mapper worker"),
              (PAYLOAD_HOST, PAYLOAD_HOST_SHA256, "payload host"),
              (PAYLOAD_WORKER, PAYLOAD_WORKER_SHA256, "payload worker"),
              (WORKER, WORKER_SHA256, "tangent worker"))
    for path, digest, label in inputs:
        require_hash(path, digest, label)
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(WORKER), "--", "--blend", str(blend),
               "--repaired-usf", str(repaired), "--native-usf", str(native),
               "--worklist", str(worklist), "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--host-sha256", host_sha,
               "--mapper-sha256", MAPPER_WORKER_SHA256,
               "--payload-worker-sha256", PAYLOAD_WORKER_SHA256,
               "--blender-sha256", blender_sha,
               "--native-usf-sha256", native_sha,
               "--summary-sha256", summary_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise TangentPayloadError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, gap_rows, blender_sha,
                          native_sha, summary_sha, host_sha)
    require_hash(registry, registry_sha, "registry after readback")
    require_hash(inventory_path, INVENTORY_SHA256, "authoring inventory after")
    if _unlinked_path(Path(inventory["sourceRoot"]), "source root after") != source_root:
        raise TangentPayloadError("source root changed during readback")
    for path, digest, label in (
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "retained native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary_path, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (Path(__file__), host_sha, "tangent host"), *inputs):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise TangentPayloadError("bounded final tangent result exceeded")
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
    except (TangentPayloadError, MeshInventoryError, BladeRelocationError,
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
