"""Pinned, no-save v2/Blender 5.2 SDK color-path discriminant.

This instruments one SDK projection in memory. It never saves a Blend, writes
a USF, or changes the reviewed SDK and mesh-payload readback files.
"""

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

from . import blender_mesh_variant_payload as variant
from .blender_left_push_probe import _unlinked_path, require_hash, require_sdk_pins
from .blender_mesh_inventory import BLENDER_VERSION_PINS
from .source import file_sha256


ASSET = "cat_d11t_v2"
TARGET_PATH = "|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1"
TARGET_ELEMENTS = 59238
NATIVE_COLOR_SHA256 = "aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7"
BLENDER_SHA256 = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
VARIANT_HOST_SHA256 = "f2cc1e997b8458e8fe279050a59dcdff7c9e20143d8fbfa0700da4147d6572fb"
VARIANT_WORKER_SHA256 = "cfef0c5e5cdc6ed033c704a769b0c53d466bd1f79b77746343472f50f786bda0"
WORKER = Path(__file__).with_name("blender_rgba_discriminant_worker.py")
WORKER_SHA256 = "9c66e62fd7c06e575d721c120dfc44aa3341c5d56f9b2bf66e948a6338b489d3"
RESULT_PREFIX = "ROADCRAFT_RGBA_DISCRIMINANT "
MAX_JSON_BYTES = 16 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RgbaDiscriminantError(RuntimeError):
    """A pinned input, trace, or bounded readback differs."""


def summarize_trace(records: list[tuple], native: list[int],
                    source_summary: dict, native_summary: dict) -> dict:
    """Compare call-time SDK inputs with stateless and actual packed values."""
    if (not isinstance(records, list) or not isinstance(native, list) or
            len(records) != len(native) or not records):
        raise RgbaDiscriminantError("RGBA trace/native coverage differs")
    actual_values = []
    direct_values = []
    samples = []
    source_native = direct_native = sdk_direct = cache_hits = 0
    hit_disagreements = miss_disagreements = 0
    for index, (record, native_value) in enumerate(zip(records, native)):
        if not isinstance(record, tuple) or len(record) != 5:
            raise RgbaDiscriminantError("invalid RGBA trace entry")
        rgba, hit, prior, direct, actual = record
        if (not isinstance(rgba, tuple) or len(rgba) != 4 or
                any(type(channel) is not float or not math.isfinite(channel)
                    for channel in rgba) or type(hit) is not bool or
                type(native_value) is not int or not 0 <= native_value <= 0xFFFFFFFF or
                type(direct) is not int or not 0 <= direct <= 0xFFFFFFFF or
                type(actual) is not int or not 0 <= actual <= 0xFFFFFFFF or
                (hit and (type(prior) is not int or prior != actual)) or
                (not hit and prior is not None)):
            raise RgbaDiscriminantError("invalid RGBA trace value or cache observation")
        actual_values.append(actual)
        direct_values.append(direct)
        cache_hits += hit
        source_native += actual != native_value
        direct_native += direct != native_value
        sdk_direct += actual != direct
        hit_disagreements += hit and actual != direct
        miss_disagreements += not hit and actual != direct
        if (actual != native_value or actual != direct) and len(samples) < 12:
            samples.append({"index": index, "rgba": list(rgba),
                            "cacheHit": hit, "cachedBefore": prior,
                            "stateless": direct, "sdk": actual,
                            "native": native_value})
    if (variant._color_summary([actual_values]) != source_summary or
            variant._color_summary([native]) != native_summary):
        raise RgbaDiscriminantError("trace contradicts source/native color digests")
    if source_native == 0 and sdk_direct == 0:
        finding = "MISMATCH_NOT_REPRODUCED"
    elif sdk_direct == 0:
        finding = "CALL_TIME_RGBA_PACKS_DIFFERENTLY_FROM_NATIVE"
    elif hit_disagreements == sdk_direct and miss_disagreements == 0:
        finding = "CACHE_RETURN_DIFFERS_FROM_STATELESS_PACK"
    else:
        finding = "SDK_PACK_DIFFERS_FROM_STATELESS_PACK_UNRESOLVED"
    return {
        "finding": finding, "elements": len(records),
        "sourceNativeDifferent": source_native,
        "statelessNativeDifferent": direct_native,
        "sdkStatelessDifferent": sdk_direct,
        "cacheHits": cache_hits,
        "cacheHitDisagreements": hit_disagreements,
        "cacheMissDisagreements": miss_disagreements,
        "source": source_summary, "stateless": variant._color_summary([direct_values]),
        "native": native_summary, "firstDifferences": samples,
    }


def parse_result(stdout: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > MAX_JSON_BYTES:
        raise RgbaDiscriminantError("no unique bounded RGBA readback")
    try:
        result = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise RgbaDiscriminantError("invalid RGBA readback JSON") from exc
    expected = {
        "schemaVersion": 1, "status": "SOURCE_RGBA_DISCRIMINANT",
        "asset": ASSET, "targetPath": TARGET_PATH,
        "blenderSha256": BLENDER_SHA256,
        "probeHostSha256": host_sha, "probeWorkerSha256": WORKER_SHA256,
        "variantHostSha256": VARIANT_HOST_SHA256,
        "variantWorkerSha256": VARIANT_WORKER_SHA256,
        "nativeBlendExportApproved": False,
        "blendSaved": False, "usfExported": False,
        "mappedRows": 126,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise RgbaDiscriminantError("RGBA readback identity or no-write gate differs")
    for key in ("sourceUnchanged", "sdkUnchanged", "nativeExportUnchanged",
                "repairedUsfUnchanged"):
        if result.get(key) is not True:
            raise RgbaDiscriminantError("RGBA input unchanged proof differs")
    if (not isinstance(result.get("rowsDigestSha256"), str) or
            HEX_SHA256.fullmatch(result["rowsDigestSha256"]) is None or
            not isinstance(result.get("rgbaKeyType"), str) or
            not result["rgbaKeyType"] or len(result["rgbaKeyType"]) > 80):
        raise RgbaDiscriminantError("invalid RGBA digest or key type")
    detail = result.get("detail")
    if (not isinstance(detail, dict) or detail.get("elements") != TARGET_ELEMENTS or
            detail.get("finding") not in {
                "MISMATCH_NOT_REPRODUCED",
                "CALL_TIME_RGBA_PACKS_DIFFERENTLY_FROM_NATIVE",
                "CACHE_RETURN_DIFFERS_FROM_STATELESS_PACK",
                "SDK_PACK_DIFFERS_FROM_STATELESS_PACK_UNRESOLVED"} or
            any(type(detail.get(key)) is not int or
                not 0 <= detail[key] <= TARGET_ELEMENTS for key in (
                    "sourceNativeDifferent", "statelessNativeDifferent",
                    "sdkStatelessDifferent", "cacheHits",
                    "cacheHitDisagreements", "cacheMissDisagreements")) or
            detail["cacheHitDisagreements"] + detail["cacheMissDisagreements"] !=
            detail["sdkStatelessDifferent"] or
            not isinstance(detail.get("firstDifferences"), list) or
            len(detail["firstDifferences"]) > 12):
        raise RgbaDiscriminantError("invalid bounded RGBA detail")
    if (type(result.get("matchingNativeColorsRows")) is not int or
            not 0 <= result["matchingNativeColorsRows"] <= 126 or
            any(type(result.get(key)) is not int or result[key] < 0
                for key in ("cacheBeforeTarget", "cacheAfterTarget")) or
            any(not isinstance(detail.get(key), dict) or
                detail[key].get("elements") != TARGET_ELEMENTS or
                detail[key].get("sets") != 1 or
                not isinstance(detail[key].get("sha256"), str) or
                HEX_SHA256.fullmatch(detail[key]["sha256"]) is None
                for key in ("source", "stateless", "native")) or
            detail["native"]["sha256"] != NATIVE_COLOR_SHA256):
        raise RgbaDiscriminantError("RGBA color identity or cache counters differ")
    for sample in detail["firstDifferences"]:
        if (not isinstance(sample, dict) or set(sample) != {
                "index", "rgba", "cacheHit", "cachedBefore", "stateless",
                "sdk", "native"} or
                type(sample["index"]) is not int or
                not 0 <= sample["index"] < TARGET_ELEMENTS or
                not isinstance(sample["rgba"], list) or len(sample["rgba"]) != 4 or
                any(type(value) is not float or not math.isfinite(value)
                    for value in sample["rgba"]) or
                type(sample["cacheHit"]) is not bool or
                (sample["cacheHit"] and
                 sample["cachedBefore"] != sample["sdk"]) or
                (not sample["cacheHit"] and sample["cachedBefore"] is not None) or
                any(type(sample[key]) is not int or
                    not 0 <= sample[key] <= 0xFFFFFFFF
                    for key in ("stateless", "sdk", "native"))):
            raise RgbaDiscriminantError("invalid RGBA mismatch sample")
    return result


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise RgbaDiscriminantError("timeout must be positive")
    require_hash(Path(variant.__file__), VARIANT_HOST_SHA256,
                 "reviewed variant host")
    require_hash(variant.WORKER, VARIANT_WORKER_SHA256,
                 "reviewed variant worker")
    worker = require_hash(WORKER, WORKER_SHA256, "RGBA probe worker")
    host_sha = file_sha256(Path(__file__))
    before = variant._inputs(registry_path, ASSET)
    if not any(row["path"] == TARGET_PATH for row in before["gapRows"]):
        raise RgbaDiscriminantError("target path is absent from pinned worklist")
    blender = _unlinked_path(blender_executable, "Blender executable")
    require_hash(blender, BLENDER_SHA256, "Blender 5.2 executable")
    if not BLENDER_VERSION_PINS[BLENDER_SHA256].startswith("5.2."):
        raise RgbaDiscriminantError("reviewed Blender 5.2 version pin differs")
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
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise RgbaDiscriminantError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, host_sha)
    after = variant._inputs(registry_path, ASSET)
    if before != after:
        raise RgbaDiscriminantError("variant inputs changed during readback")
    require_hash(worker, WORKER_SHA256, "RGBA probe worker after readback")
    require_hash(Path(__file__), host_sha, "RGBA probe host after readback")
    require_hash(blender, BLENDER_SHA256, "Blender executable after readback")
    require_sdk_pins(sdk)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=variant.base.TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (RuntimeError,
            OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR", "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
