"""Pinned no-save v2/Blender-5.2 live RGBA discriminant.

The SDK's UsfMesh.b_read and rgba_to_saber remain unwrapped. Raw evaluated
mesh colors are read only if the target's SDK-packed digest differs from its
retained native counterpart, while that evaluated mesh is still live.
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

from . import blender_mesh_variant_payload as variant
from .blender_left_push_probe import (
    LeftPushProbeError, SDK_PINS, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import BLENDER_VERSION_PINS
from .source import file_sha256


ASSET = "cat_d11t_v2"
TARGET_PATH = "|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1"
TARGET_ELEMENTS = 59238
NATIVE_COLOR_SHA256 = "aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7"
BLENDER_SHA256 = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
VARIANT_HOST_SHA256 = "f2cc1e997b8458e8fe279050a59dcdff7c9e20143d8fbfa0700da4147d6572fb"
VARIANT_WORKER_SHA256 = "cfef0c5e5cdc6ed033c704a769b0c53d466bd1f79b77746343472f50f786bda0"
WORKER = Path(__file__).with_name("blender_v2_rgba_live_discriminant_worker.py")
WORKER_SHA256 = "99cbb46fd054ab0bd9e0e2dba895d40e03fd23ce684d2fd766ff6fc302041eba"
RESULT_PREFIX = "ROADCRAFT_V2_RGBA_LIVE_DISCRIMINANT "
MAX_JSON_BYTES = 16 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class LiveRgbaError(RuntimeError):
    """Pinned inputs, live color shape, or bounded receipt differ."""


def _color_summary(values: list[int]) -> dict:
    if not isinstance(values, list) or len(values) > 10_000_000:
        raise LiveRgbaError("invalid packed color array")
    digest = hashlib.sha256()
    digest.update(struct.pack("<Q", 1))
    digest.update(struct.pack("<Q", len(values)))
    for value in values:
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise LiveRgbaError("invalid packed color value")
        digest.update(struct.pack("<I", value))
    return {"elements": len(values), "sets": 1, "sha256": digest.hexdigest()}


def should_read_live_raw(source: dict, native: dict, *,
                         expected_elements: int = TARGET_ELEMENTS,
                         native_sha: str = NATIVE_COLOR_SHA256) -> bool:
    """Fail closed on a wrong target; never read raw colors on a digest match."""
    for summary in (source, native):
        if (not isinstance(summary, dict) or set(summary) !=
                {"elements", "sets", "sha256"} or
                type(summary["elements"]) is not int or
                summary["elements"] != expected_elements or
                type(summary["sets"]) is not int or summary["sets"] != 1 or
                not isinstance(summary["sha256"], str) or
                HEX_SHA256.fullmatch(summary["sha256"]) is None):
            raise LiveRgbaError("target color shape or digest differs")
    if native["sha256"] != native_sha:
        raise LiveRgbaError("retained native target digest differs")
    return source != native


def stateless_pack(rgba: tuple[float, ...]) -> int:
    """Repeat the SDK clip/truncate/ARGB expression without RGBA_CACHE."""
    if (not isinstance(rgba, tuple) or len(rgba) != 4 or
            any(type(value) is not float or not math.isfinite(value)
                for value in rgba)):
        raise LiveRgbaError("invalid live RGBA value")
    channels = [int(min(1.0, max(0.0, value)) * 255.0)
                for value in rgba]
    return ((channels[3] & 255) << 24) | ((channels[0] & 255) << 16) | \
           ((channels[1] & 255) << 8) | (channels[2] & 255)


def pack_live_triangles(mesh, color_data, *,
                        expected_elements: int = TARGET_ELEMENTS) -> tuple[list[int], list[tuple[float, ...]]]:
    """Use the SDK's b_read_face triangle-loop order on a live mesh only."""
    if (type(expected_elements) is not int or expected_elements <= 0 or
            expected_elements % 3 != 0 or mesh is None or
            len(mesh.loop_triangles) * 3 != expected_elements):
        raise LiveRgbaError("live triangle count differs")
    packed = []
    raw = []
    for triangle in mesh.loop_triangles:
        if len(triangle.loops) != 3:
            raise LiveRgbaError("live triangle loop width differs")
        for loop_index in triangle.loops:
            if (type(loop_index) is not int or loop_index < 0 or
                    loop_index >= len(color_data)):
                raise LiveRgbaError("live color loop index differs")
            rgba = tuple(float(channel) for channel in color_data[loop_index].color)
            packed.append(stateless_pack(rgba))
            raw.append(rgba)
    if len(packed) != expected_elements:
        raise LiveRgbaError("live color coverage differs")
    return packed, raw


def summarize_mismatch(source: list[int], native: list[int],
                       raw_packed: list[int], raw_rgba: list[tuple[float, ...]],
                       *, expected_elements: int = TARGET_ELEMENTS,
                       native_sha: str = NATIVE_COLOR_SHA256) -> dict:
    if (not all(isinstance(array, list) and len(array) == expected_elements
                for array in (source, native, raw_packed, raw_rgba)) or
            _color_summary(native)["sha256"] != native_sha):
        raise LiveRgbaError("live/native detail coverage or pin differs")
    source_summary = _color_summary(source)
    raw_summary = _color_summary(raw_packed)
    native_summary = _color_summary(native)
    differences = {"sourceNative": 0, "rawNative": 0, "sourceRaw": 0}
    samples = []
    for index, (sdk_value, native_value, raw_value, rgba) in enumerate(
            zip(source, native, raw_packed, raw_rgba)):
        if stateless_pack(rgba) != raw_value:
            raise LiveRgbaError("raw RGBA contradicts stateless packed value")
        differences["sourceNative"] += sdk_value != native_value
        differences["rawNative"] += raw_value != native_value
        differences["sourceRaw"] += sdk_value != raw_value
        if (sdk_value != native_value or raw_value != native_value or
                sdk_value != raw_value) and len(samples) < 12:
            samples.append({"index": index, "rawRgba": list(rgba),
                            "source": sdk_value, "stateless": raw_value,
                            "native": native_value})
    if differences["sourceNative"] == 0:
        raise LiveRgbaError("conditional raw readback lacks a source mismatch")
    if differences["rawNative"] == 0:
        finding = "SDK_PACK_OR_CACHE_DIFFERS_FROM_LIVE_RAW"
    elif differences["sourceRaw"] == 0:
        finding = "LIVE_RAW_DIFFERS_FROM_NATIVE"
    else:
        finding = "MIXED_COLOR_DIFFERENCE_UNRESOLVED"
    return {"finding": finding, "elements": expected_elements,
            "source": source_summary, "native": native_summary,
            "stateless": raw_summary, "different": differences,
            "firstDifferences": samples}


def parse_result(stdout: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > MAX_JSON_BYTES:
        raise LiveRgbaError("no unique bounded live RGBA result")
    try:
        result = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise LiveRgbaError("malformed live RGBA JSON") from exc
    pins = variant.ASSET_PINS[ASSET]
    expected = {
        "schemaVersion": 1, "status": "SOURCE_V2_RGBA_LIVE_DISCRIMINANT",
        "asset": ASSET, "targetPath": TARGET_PATH,
        "blenderSha256": BLENDER_SHA256, "probeHostSha256": host_sha,
        "probeWorkerSha256": WORKER_SHA256,
        "variantHostSha256": VARIANT_HOST_SHA256,
        "variantWorkerSha256": VARIANT_WORKER_SHA256,
        "blendSha256": pins["blendSha256"],
        "nativeUsfSha256": pins["nativeUsfSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "worklistSha256": variant.WORKLIST_SHA256,
        "summarySha256": pins["summarySha256"],
        "sdkMeshSha256": SDK_PINS["saber/blender/lib/usf/mesh.py"],
        "sdkFunctionsUnwrapped": True, "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
        "mappedRows": 126,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise LiveRgbaError("live RGBA identity or no-write gate differs")
    if (not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[BLENDER_SHA256]) or
            any(result.get(key) is not True for key in (
                "sourceUnchanged", "sdkUnchanged", "nativeExportUnchanged",
                "repairedUsfUnchanged")) or
            type(result.get("matchingNativeColorsRows")) is not int or
            not 0 <= result["matchingNativeColorsRows"] <= 126 or
            type(result.get("otherColorMismatchRows")) is not int or
            not 0 <= result["otherColorMismatchRows"] <= 125 or
            not isinstance(result.get("rowsDigestSha256"), str) or
            HEX_SHA256.fullmatch(result["rowsDigestSha256"]) is None):
        raise LiveRgbaError("live RGBA aggregate result differs")
    target = result.get("target")
    if not isinstance(target, dict) or set(target) != {
            "source", "native", "rawReadbackPerformed", "detail",
            "cacheBefore", "cacheAfter"}:
        raise LiveRgbaError("target detail is incomplete")
    differs = should_read_live_raw(target["source"], target["native"])
    if (type(target["rawReadbackPerformed"]) is not bool or
            target["rawReadbackPerformed"] != differs or
            any(type(target[key]) is not int or target[key] < 0
                for key in ("cacheBefore", "cacheAfter")) or
            target["cacheAfter"] < target["cacheBefore"]):
        raise LiveRgbaError("target conditional readback or cache shape differs")
    detail = target["detail"]
    if not differs:
        if detail is not None:
            raise LiveRgbaError("raw detail emitted on a matching target")
    elif (not isinstance(detail, dict) or set(detail) != {
            "finding", "elements", "source", "native", "stateless",
            "different", "firstDifferences"} or
            detail["source"] != target["source"] or
            detail["native"] != target["native"] or
            detail["elements"] != TARGET_ELEMENTS or
            detail["finding"] not in {
                "SDK_PACK_OR_CACHE_DIFFERS_FROM_LIVE_RAW",
                "LIVE_RAW_DIFFERS_FROM_NATIVE",
                "MIXED_COLOR_DIFFERENCE_UNRESOLVED"} or
            not isinstance(detail["different"], dict) or
            set(detail["different"]) != {"sourceNative", "rawNative", "sourceRaw"} or
            any(type(value) is not int or not 0 <= value <= TARGET_ELEMENTS
                for value in detail["different"].values()) or
            detail["different"]["sourceNative"] < 1 or
            not isinstance(detail["firstDifferences"], list) or
            len(detail["firstDifferences"]) > 12 or
            not isinstance(detail["stateless"], dict) or
            detail["stateless"].get("elements") != TARGET_ELEMENTS or
            detail["stateless"].get("sets") != 1 or
            not isinstance(detail["stateless"].get("sha256"), str) or
            HEX_SHA256.fullmatch(detail["stateless"]["sha256"]) is None):
        raise LiveRgbaError("bounded live mismatch detail differs")
    return result


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 1200:
        raise LiveRgbaError("timeout is outside 1..1200 seconds")
    require_hash(Path(variant.__file__), VARIANT_HOST_SHA256,
                 "reviewed variant host")
    require_hash(variant.WORKER, VARIANT_WORKER_SHA256,
                 "reviewed variant worker")
    worker = require_hash(WORKER, WORKER_SHA256, "live RGBA worker")
    host_sha = file_sha256(Path(__file__))
    before = variant._inputs(registry_path, ASSET)
    if not any(row["path"] == TARGET_PATH for row in before["gapRows"]):
        raise LiveRgbaError("target path absent from pinned worklist")
    blender = _unlinked_path(blender_executable, "Blender executable")
    require_hash(blender, BLENDER_SHA256, "Blender 5.2 executable")
    sdk = require_sdk_pins(sdk_script_root)
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--asset", ASSET,
               "--blend", str(before["blend"]),
               "--repaired-usf", str(before["usf"]),
               "--native-usf", str(before["native"]),
               "--worklist", str(before["worklist"]),
               "--summary", str(before["summary"]),
               "--sdk-script-root", str(sdk),
               "--probe-worker-sha256", WORKER_SHA256,
               "--probe-host-sha256", host_sha,
               "--blender-sha256", BLENDER_SHA256]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise LiveRgbaError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, host_sha)
    after = variant._inputs(registry_path, ASSET)
    if before != after:
        raise LiveRgbaError("variant inputs changed during readback")
    for path, digest, label in (
            (worker, WORKER_SHA256, "live RGBA worker"),
            (Path(__file__), host_sha, "live RGBA host"),
            (blender, BLENDER_SHA256, "Blender executable")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=variant.base.TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (RuntimeError, LeftPushProbeError, OSError, ValueError, KeyError,
            TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
