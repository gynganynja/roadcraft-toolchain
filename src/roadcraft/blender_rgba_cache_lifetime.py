"""Pinned, no-save SDK RGBA cache lifetime diagnostic in background Blender.

The worker creates disposable in-memory meshes only. It never opens a source
Blend or USF, changes the installed SDK, or writes an output file.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_left_push_probe import (
    LeftPushProbeError, SDK_PINS, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .source import file_sha256


WORKER = Path(__file__).with_name("blender_rgba_cache_lifetime_worker.py")
WORKER_SHA256 = "54d5805321b57fd263ad35016706611ef627a703c2ebadee9bb32a21f19b8037"
SDK_MESH_SHA256 = SDK_PINS["saber/blender/lib/usf/mesh.py"]
RESULT_PREFIX = "ROADCRAFT_RGBA_CACHE_LIFETIME "
MAX_JSON_BYTES = 4096
MAX_ATTEMPTS = 4096
EXPECTED_RAW = (0.2, 0.3, 0.4, 1.0)


class CacheLifetimeError(RuntimeError):
    """A pinned input or bounded no-save cache observation differs."""


def interpret_result(result: dict, *, blender_sha: str,
                     host_sha: str) -> dict:
    expected = {
        "schemaVersion": 1,
        "blenderSha256": blender_sha,
        "sdkMeshSha256": SDK_MESH_SHA256,
        "workerSha256": WORKER_SHA256,
        "hostSha256": host_sha,
        "maxAttempts": MAX_ATTEMPTS,
        "whiteKeyType": "bpy_prop_array",
        "whitePacked": 0xFFFFFFFF,
        "acceptedAssetOpened": False,
        "blendSaved": False,
        "usfExported": False,
        "sdkFileChanged": False,
        "nativeBlendExportApproved": False,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise CacheLifetimeError("cache probe identity or no-write flags differ")
    if (blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise CacheLifetimeError("Blender version differs")
    status = result.get("status")
    collision = result.get("collision")
    if collision is None:
        if status != "SDK_RGBA_COLLISION_NOT_REPRODUCED":
            raise CacheLifetimeError("no-collision status contradicts observation")
        return result
    if not isinstance(collision, dict) or set(collision) != {
            "attempt", "sameHash", "equalKey", "rawRgba",
            "cacheBeforeLookup", "cachedValue", "stalePacked",
            "cacheAfterStale", "freshAfterClearPacked", "cacheAfterFresh"}:
        raise CacheLifetimeError("cache collision detail is incomplete")
    if (type(collision["attempt"]) is not int or
            not 0 <= collision["attempt"] < MAX_ATTEMPTS or
            collision["sameHash"] is not True or
            collision["equalKey"] is not True or
            not isinstance(collision["rawRgba"], list) or
            len(collision["rawRgba"]) != 4 or
            any(type(value) not in (float, int) or not math.isfinite(value) or
                abs(value - expected_value) > 1e-6
                for value, expected_value in zip(collision["rawRgba"],
                                                 EXPECTED_RAW)) or
            any(type(collision[key]) is not int for key in (
                "cacheBeforeLookup", "cachedValue", "stalePacked",
                "cacheAfterStale", "freshAfterClearPacked",
                "cacheAfterFresh"))):
        raise CacheLifetimeError("cache collision fields are invalid")
    reproduced = (collision["cacheBeforeLookup"] == 1 and
                  collision["cachedValue"] == 0xFFFFFFFF and
                  collision["stalePacked"] == 0xFFFFFFFF and
                  collision["cacheAfterStale"] == 1 and
                  collision["freshAfterClearPacked"] == 0xFF334C66 and
                  collision["cacheAfterFresh"] == 1)
    if status != ("SDK_RGBA_STALE_CACHE_REPRODUCED" if reproduced
                  else "SDK_RGBA_COLLISION_NOT_REPRODUCED"):
        raise CacheLifetimeError("cache status contradicts observed values")
    return result


def parse_result(stdout: str, *, blender_sha: str,
                 host_sha: str) -> dict:
    lines = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1 or len(lines[0].encode("utf-8")) > MAX_JSON_BYTES:
        raise CacheLifetimeError("Blender emitted no unique bounded cache result")
    try:
        raw = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise CacheLifetimeError("Blender cache result is malformed") from exc
    return interpret_result(raw, blender_sha=blender_sha, host_sha=host_sha)


def run_probe(*, blender_executable: Path, sdk_script_root: Path,
              timeout_seconds: int = 60) -> dict:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise CacheLifetimeError("timeout must be between 1 and 300 seconds")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise CacheLifetimeError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "cache lifetime worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256, "--host-sha256", host_sha,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise CacheLifetimeError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, blender_sha=blender_sha,
                          host_sha=host_sha)
    require_hash(blender, blender_sha, "Blender executable after")
    require_sdk_pins(sdk)
    require_hash(worker, WORKER_SHA256, "worker after")
    require_hash(Path(__file__), host_sha, "host after")
    result["inputsUnchanged"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        result = run_probe(blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (CacheLifetimeError, LeftPushProbeError, OSError, ValueError,
            TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
