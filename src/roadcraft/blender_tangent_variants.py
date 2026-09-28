"""Pinned, no-save D11 v2/v3 tangent readback against each USF side."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from . import blender_tangent_payload as base
from .blender_animation_variants import VARIANTS, _inputs
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, require_hash, require_sdk_pins,
)
from .blender_mesh_inventory import (
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST_SHA256,
    MeshInventoryError,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_tangent_variants_worker.py")
WORKER_SHA256 = "873ca98851060561400fc621195ad270f229440414ef71cd1d59332a4e2e3ed0"
INPUT_HOST = Path(__file__).with_name("blender_animation_variants.py")
INPUT_HOST_SHA256 = "d5a9a3cf75bac45f1a92d818614f4b83b3bf2e9e06ad9377ff6e111582832ae9"
BASE_HOST = Path(__file__).with_name("blender_tangent_payload.py")
BASE_HOST_SHA256 = "16f391d31a02f0e55d10f87fa7ae6d3f4ab36011db01d8ea708dca2d3ddcd029"
MAPPER_WORKER = Path(__file__).with_name("blender_mesh_inventory_worker.py")
MAPPER_WORKER_SHA256 = "e29122c28bbe60a254a7c239fcc84be7d2f05a57c0ce305132069edd5b264113"
RESULT_PREFIX = "ROADCRAFT_TANGENT_VARIANTS "
MAX_JSON_BYTES = 1024 * 1024
EXPECTED_ROWS = 126
SHA = re.compile(r"[0-9a-f]{64}\Z")


class TangentVariantError(RuntimeError):
    """A pinned tangent variant, row, or no-write result differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def compare_tangent_arrays(source_mesh, target_mesh) -> dict:
    """Compare SDK-projected and parsed arrays at float32 bit precision.

    Different layer lengths have no component-wise correspondence and receive
    a shape result rather than a misleading difference count.
    """
    source_layers = base._layers(source_mesh)
    target_layers = base._layers(target_mesh)
    source = base.summarize_tangents(source_layers)
    target = base.summarize_tangents(target_layers)
    source_names = [uv.name for uv in source_mesh.uvsets.uvs]
    target_names = [uv.name for uv in target_mesh.uvsets.uvs]
    if (any(not isinstance(name, str) for name in source_names + target_names) or
            len(source_names) != len(source_layers) or
            len(target_names) != len(target_layers)):
        raise TangentVariantError("UV layer identity is malformed")
    names_equal = source_names == target_names
    if source["layerLengths"] != target["layerLengths"]:
        return {"status": "SHAPE_MISMATCH", "source": source,
                "target": target, "sourceUvNames": source_names,
                "targetUvNames": target_names, "uvNamesEqual": names_equal,
                "differingValues": None,
                "maxAbsoluteDifference": None, "match": False}
    counts = {name: 0 for name in base.COMPONENTS}
    maxima = {name: 0.0 for name in base.COMPONENTS}
    for source_layer, target_layer in zip(source_layers, target_layers):
        for source_vector, target_vector in zip(source_layer, target_layer):
            for name, (source_bytes, source_value), (target_bytes, target_value) in zip(
                    base.COMPONENTS, source_vector, target_vector):
                if source_bytes != target_bytes:
                    counts[name] += 1
                    maxima[name] = max(maxima[name],
                                       abs(source_value - target_value))
    if any((source["componentSha256"][name] ==
            target["componentSha256"][name]) != (counts[name] == 0)
           for name in base.COMPONENTS):
        raise TangentVariantError("component digest and count disagree")
    match = names_equal and source == target
    status = ("BITWISE_MATCH" if match else
              "UV_NAME_MISMATCH" if not names_equal else
              "TANGENT_DIFFERENCE")
    return {"status": status, "source": source, "target": target,
            "sourceUvNames": source_names, "targetUvNames": target_names,
            "uvNamesEqual": names_equal,
            "differingValues": counts,
            "maxAbsoluteDifference": maxima, "match": match}


def _summary(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
            "layerLengths", "vectors", "sha256", "componentSha256"}:
        raise TangentVariantError("tangent summary shape differs")
    lengths = value["layerLengths"]
    if (not isinstance(lengths, list) or len(lengths) > 16 or
            any(type(length) is not int or length < 0 for length in lengths) or
            type(value["vectors"]) is not int or
            value["vectors"] != sum(lengths) or
            not isinstance(value["sha256"], str) or
            SHA.fullmatch(value["sha256"]) is None or
            not isinstance(value["componentSha256"], dict) or
            set(value["componentSha256"]) != set(base.COMPONENTS) or
            any(not isinstance(digest, str) or SHA.fullmatch(digest) is None
                for digest in value["componentSha256"].values())):
        raise TangentVariantError("tangent summary values differ")
    return value


def _row(row: object, expected_path: str, seen: set[str]) -> dict:
    if (not isinstance(row, dict) or set(row) != {
            "path", "sourceObject", "comparison"} or
            row["path"] != expected_path or
            not isinstance(row["sourceObject"], str) or
            not row["sourceObject"] or row["sourceObject"] in seen):
        raise TangentVariantError("tangent row path/source coverage differs")
    seen.add(row["sourceObject"])
    item = row["comparison"]
    if not isinstance(item, dict) or set(item) != {
            "status", "source", "target", "sourceUvNames",
            "targetUvNames", "uvNamesEqual", "differingValues",
            "maxAbsoluteDifference", "match"}:
        raise TangentVariantError("tangent row comparison shape differs")
    source = _summary(item["source"])
    target = _summary(item["target"])
    source_names = item["sourceUvNames"]
    target_names = item["targetUvNames"]
    if (not isinstance(source_names, list) or
            not isinstance(target_names, list) or
            len(source_names) != len(source["layerLengths"]) or
            len(target_names) != len(target["layerLengths"]) or
            any(not isinstance(name, str) for name in source_names + target_names) or
            type(item["uvNamesEqual"]) is not bool or
            item["uvNamesEqual"] != (source_names == target_names) or
            type(item["match"]) is not bool):
        raise TangentVariantError("tangent UV layer identity differs")
    same_shape = source["layerLengths"] == target["layerLengths"]
    if not same_shape:
        if (item["status"] != "SHAPE_MISMATCH" or
                item["differingValues"] is not None or
                item["maxAbsoluteDifference"] is not None or
                item["match"] is not False):
            raise TangentVariantError("shape-mismatched row claims comparison")
        return row
    counts = item["differingValues"]
    maxima = item["maxAbsoluteDifference"]
    if (not isinstance(counts, dict) or set(counts) != set(base.COMPONENTS) or
            not isinstance(maxima, dict) or set(maxima) != set(base.COMPONENTS)):
        raise TangentVariantError("tangent component result is incomplete")
    for name in base.COMPONENTS:
        count = counts[name]
        magnitude = maxima[name]
        if (type(count) is not int or not 0 <= count <= source["vectors"] or
                type(magnitude) not in (int, float) or
                not math.isfinite(magnitude) or magnitude < 0 or
                (count == 0 and magnitude != 0) or
                (count == 0) != (source["componentSha256"][name] ==
                                  target["componentSha256"][name])):
            raise TangentVariantError("tangent component digest/count contradiction")
    equal_values = source == target
    expected_match = item["uvNamesEqual"] and equal_values
    expected_status = ("BITWISE_MATCH" if expected_match else
                       "UV_NAME_MISMATCH" if not item["uvNamesEqual"] else
                       "TANGENT_DIFFERENCE")
    if item["match"] != expected_match or item["status"] != expected_status or (
            equal_values != all(count == 0 for count in counts.values())):
        raise TangentVariantError("tangent row match/status contradicts values")
    return row


def interpret_readback(result: object, asset: str, blender_sha: str,
                       host_sha: str, paths: list[str]) -> dict:
    if asset not in VARIANTS:
        raise TangentVariantError("unreviewed tangent variant")
    pins = VARIANTS[asset]
    expected = {
        "schemaVersion": 1, "asset": asset,
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": pins["repairedSha256"],
        "nativeExportUsfSha256": pins["nativeSha256"],
        "summarySha256": pins["summarySha256"],
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "hostSha256": host_sha,
        "workerSha256": WORKER_SHA256,
        "inputHostSha256": INPUT_HOST_SHA256,
        "baseTangentHostSha256": BASE_HOST_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "repairedRootName": "cat_d11t", "nativeRootName": asset,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if (not isinstance(result, dict) or
            set(result) != set(expected) | {
                "blenderVersion", "nativeRows", "repairedRows"} or
            any(type(result.get(key)) is not type(value) or
                result.get(key) != value for key, value in expected.items()) or
            blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise TangentVariantError("variant tangent identity or no-write fields differ")
    if (not isinstance(paths, list) or len(paths) != EXPECTED_ROWS or
            paths != sorted(set(paths))):
        raise TangentVariantError("worklist tangent path coverage differs")
    sides = {}
    for side in ("native", "repaired"):
        rows = result[side + "Rows"]
        if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
            raise TangentVariantError(f"{side} tangent row coverage differs")
        seen = set()
        checked = [_row(row, path, seen) for row, path in zip(rows, paths)]
        sides[side] = checked
    if any(n["sourceObject"] != r["sourceObject"] or
           n["comparison"]["source"] != r["comparison"]["source"] or
           n["comparison"]["sourceUvNames"] != r["comparison"]["sourceUvNames"]
           for n, r in zip(sides["native"], sides["repaired"])):
        raise TangentVariantError("source projection changed between USF sides")
    counts = {}
    for side, rows in sides.items():
        comparable = [row["comparison"] for row in rows
                      if row["comparison"]["status"] != "SHAPE_MISMATCH"]
        counts[side] = {
            "mappedRows": len(rows),
            "comparableRows": len(comparable),
            "shapeMismatchRows": len(rows) - len(comparable),
            "matchingRows": sum(item["match"] for item in comparable),
            "uvNameMismatchRows": sum(not item["uvNamesEqual"] for item in comparable),
            "differingValuesByComponent": {
                name: sum(item["differingValues"][name] for item in comparable)
                for name in base.COMPONENTS},
            "maxAbsoluteDifferenceByComponent": {
                name: max((item["maxAbsoluteDifference"][name]
                           for item in comparable), default=0.0)
                for name in base.COMPONENTS},
            "rowsDigestSha256": hashlib.sha256(_canonical(rows)).hexdigest(),
        }
    payload = {key: result[key] for key in expected}
    payload.update({
        "status": "SOURCE_VARIANT_TANGENT_ARRAY_READBACK",
        "blenderVersion": result["blenderVersion"],
        "sourceProjectionConsistentAcrossSides": True,
        "sideSummaries": counts,
        "nativeRows": sides["native"],
        "repairedRows": sides["repaired"],
    })
    if len(_canonical(payload)) > MAX_JSON_BYTES:
        raise TangentVariantError("variant tangent result exceeded bound")
    return payload


def _gap_paths(worklist: Path, asset: str) -> list[str]:
    evidence = json.loads(worklist.read_text(encoding="utf-8"))
    rows = [row for row in evidence["assets"] if row.get("asset") == asset]
    if len(rows) != 1:
        raise TangentVariantError("worklist variant is not unique")
    paths = sorted(row["path"] for row in rows[0]["findings"]["changedMeshNodes"])
    if len(paths) != EXPECTED_ROWS or len(set(paths)) != EXPECTED_ROWS:
        raise TangentVariantError("worklist mesh coverage differs")
    return paths


def run_probe(*, asset_name: str, registry_path: Path,
              blender_executable: Path, sdk_script_root: Path,
              timeout_seconds: int = 1200) -> dict:
    if asset_name not in VARIANTS:
        raise TangentVariantError("unreviewed tangent variant")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise TangentVariantError("timeout must be a positive integer")
    dependencies = ((INPUT_HOST, INPUT_HOST_SHA256, "variant input host"),
                    (BASE_HOST, BASE_HOST_SHA256, "base tangent host"),
                    (MAPPER_WORKER, MAPPER_WORKER_SHA256, "mesh mapper worker"),
                    (WORKER, WORKER_SHA256, "variant tangent worker"))
    for path, digest, label in dependencies:
        require_hash(path, digest, label)
    paths = _inputs(registry_path, asset_name)
    expected_paths = _gap_paths(paths["worklist"], asset_name)
    pins = VARIANTS[asset_name]
    blender = base._unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise TangentVariantError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(WORKER), "--", "--asset", asset_name,
               "--blend", str(paths["blend"]),
               "--repaired-usf", str(paths["repaired"]),
               "--native-usf", str(paths["native"]),
               "--worklist", str(paths["worklist"]),
               "--summary", str(paths["summary"]),
               "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--host-sha256", host_sha,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise TangentVariantError(f"Blender exited {completed.returncode}: {tail}")
    matches = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise TangentVariantError("Blender did not emit one bounded tangent readback")
    result = interpret_readback(json.loads(matches[0]), asset_name,
                                blender_sha, host_sha, expected_paths)
    require_hash(paths["registry"], paths["registrySha"],
                 "registry after readback")
    require_hash(paths["inventoryPath"], INVENTORY_SHA256,
                 "inventory after readback")
    for path, digest, label in (
            (paths["blend"], BLEND_SHA256, "source Blend"),
            (paths["repaired"], pins["repairedSha256"], "repaired USF"),
            (paths["native"], pins["nativeSha256"], "retained native USF"),
            (paths["worklist"], WORKLIST_SHA256, "worklist"),
            (paths["summary"], pins["summarySha256"], "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (Path(__file__), host_sha, "variant tangent host"), *dependencies):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise TangentVariantError("final tangent result exceeded bound")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args(argv)
    try:
        result = run_probe(asset_name=args.asset, registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (TangentVariantError, base.TangentPayloadError, LeftPushProbeError,
            MeshInventoryError, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
