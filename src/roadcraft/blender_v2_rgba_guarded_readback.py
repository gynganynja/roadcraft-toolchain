"""Pinned, no-save D11 v2 color readback with one opt-in RGBA cache guard.

The existing reviewed 126-row worker supplies mesh projection and comparison.
This host only installs a bounded guard for the source projection interval.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from . import blender_rgba_cache_guard as guard
from . import blender_v2_rgba_live_discriminant as live
from . import blender_mesh_variant_payload as variant
from .blender_left_push_probe import (
    LeftPushProbeError, _unlinked_path, require_hash, require_sdk_pins,
)
from .source import file_sha256


GUARD_SHA256 = "9a8454527dde123a7f6fdcc4daf55b53662c570b844b2a9614a01a1e53b5813c"
LIVE_HOST_SHA256 = "311fee930e4f9057c3d44b9f4561d4f841c7242fd7386bfaf8c70e433f80cef5"
LIVE_WORKER_SHA256 = "99cbb46fd054ab0bd9e0e2dba895d40e03fd23ce684d2fd766ff6fc302041eba"
WORKER = Path(__file__).with_name("blender_v2_rgba_guarded_readback_worker.py")
WORKER_SHA256 = "902ab34cbffed884831cf2a8c272291f34188fcb2c7395c07dcf231743b3a612"
RESULT_PREFIX = "ROADCRAFT_V2_RGBA_GUARDED_READBACK "


class GuardedReadbackError(RuntimeError):
    """The bounded guarded readback or a pinned input differs."""


class ProjectionGuard:
    """Enter one cache context at the first source b_read; close after 126.

    USF parsing precedes opening the Blend in the reviewed worker. Until the
    exact source Blend is open, attribute access returns the original method.
    Class and packer hooks are restored even when projection raises.
    """

    def __init__(self, mesh_class, color_class, rgba_cache: dict, *,
                 source_is_open: Callable[[], bool],
                 is_mesh_object: Callable[[object], bool],
                 expected_reads: int = 126):
        if type(expected_reads) is not int or expected_reads <= 0:
            raise GuardedReadbackError("invalid projection read count")
        self.mesh_class = mesh_class
        self.color_class = color_class
        self.rgba_cache = rgba_cache
        self.source_is_open = source_is_open
        self.is_mesh_object = is_mesh_object
        self.expected_reads = expected_reads
        self.reads = 0
        self.contexts_entered = 0
        self.guard_state = None
        self.hook_restored = False
        self._original_getattribute = None
        self._original_packer = None
        self._guard_context = None

    def _close_guard(self, exc_type=None, exc=None, tb=None) -> None:
        context = self._guard_context
        if context is None:
            return
        self._guard_context = None
        context.__exit__(exc_type, exc, tb)

    def __enter__(self):
        if self.mesh_class.__getattribute__ is not object.__getattribute__:
            raise GuardedReadbackError("SDK mesh attribute access is not reviewed")
        self._original_getattribute = self.mesh_class.__getattribute__
        self._original_packer = self.color_class.rgba_to_saber

        def guarded_getattribute(instance, name):
            original = self._original_getattribute(instance, name)
            if name != "b_read" or not self.source_is_open():
                return original

            def guarded_b_read(*args, **kwargs):
                if (kwargs or len(args) != 1 or
                        not self.is_mesh_object(args[0]) or
                        self.reads >= self.expected_reads):
                    raise GuardedReadbackError("source b_read call shape or count differs")
                if self._guard_context is None:
                    if self.reads != 0:
                        raise GuardedReadbackError("RGBA guard closed before final read")
                    self._guard_context = guard.immutable_rgba_cache(
                        self.color_class, self.rgba_cache)
                    self.guard_state = self._guard_context.__enter__()
                    self.contexts_entered += 1
                try:
                    result = original(*args, **kwargs)
                except BaseException:
                    self._close_guard(*sys.exc_info())
                    raise
                self.reads += 1
                if self.reads == self.expected_reads:
                    self._close_guard()
                return result

            return guarded_b_read

        self.mesh_class.__getattribute__ = guarded_getattribute
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._close_guard(exc_type, exc, tb)
        finally:
            self.mesh_class.__getattribute__ = self._original_getattribute
            self.hook_restored = (
                self.mesh_class.__getattribute__ is self._original_getattribute)
            packer_restored = (
                self.color_class.rgba_to_saber is self._original_packer)
        if exc_type is None and (
                self.reads != self.expected_reads or
                self.contexts_entered != 1 or
                self.guard_state is None or
                not self.guard_state["restored"] or
                not self.guard_state["cacheClearedAfter"] or
                not self.hook_restored or not packer_restored):
            raise GuardedReadbackError("guard did not cover and restore 126 reads")
        return False


def parse_result(stdout: str, host_sha256: str) -> dict:
    lines = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1 or len(lines[0].encode("utf-8")) > 16 * 1024:
        raise GuardedReadbackError("no unique bounded guarded receipt")
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise GuardedReadbackError("malformed guarded receipt") from exc
    expected = {
        "schemaVersion": 1,
        "status": "SOURCE_V2_RGBA_GUARDED_READBACK",
        "asset": live.ASSET,
        "blenderSha256": live.BLENDER_SHA256,
        "hostSha256": host_sha256,
        "workerSha256": WORKER_SHA256,
        "guardSha256": GUARD_SHA256,
        "liveHostSha256": LIVE_HOST_SHA256,
        "liveWorkerSha256": LIVE_WORKER_SHA256,
        "blendSha256": guard.BLEND_SHA256,
        "nativeUsfSha256": variant.ASSET_PINS[live.ASSET]["nativeUsfSha256"],
        "repairedUsfSha256": guard.BASELINE_USF_SHA256,
        "sdkMeshSha256": guard.SDK_MESH_SHA256,
        "mappedRows": 126,
        "guardEnabled": True,
        "sdkPackerTemporarilyGuarded": True,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceUnchanged": True,
        "sdkUnchanged": True,
    }
    if not isinstance(result, dict) or any(
            type(result.get(key)) is not type(value) or result.get(key) != value
            for key, value in expected.items()):
        raise GuardedReadbackError("guarded receipt identity or no-write gate differs")
    guard_receipt = result.get("guard")
    if (not isinstance(guard_receipt, dict) or
            set(guard_receipt) != {"reads", "packCalls", "singleContext",
                                   "packerRestored", "hookRestored",
                                   "cacheClearedAfter"} or
            type(guard_receipt["reads"]) is not int or
            guard_receipt["reads"] != 126 or
            type(guard_receipt["packCalls"]) is not int or
            guard_receipt["packCalls"] <= 0 or
            any(guard_receipt[key] is not True for key in (
                "singleContext", "packerRestored", "hookRestored",
                "cacheClearedAfter"))):
        raise GuardedReadbackError("guard coverage or restoration differs")
    target = result.get("target")
    if (not isinstance(target, dict) or
            live.should_read_live_raw(target.get("source"), target.get("native")) !=
            target.get("rawReadbackPerformed") or
            type(result.get("matchingNativeColorsRows")) is not int or
            not 0 <= result["matchingNativeColorsRows"] <= 126 or
            type(result.get("otherColorMismatchRows")) is not int or
            result["otherColorMismatchRows"] != 0):
        raise GuardedReadbackError("guarded color comparison differs")
    return result


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 1200:
        raise GuardedReadbackError("timeout is outside 1..1200 seconds")
    require_hash(Path(guard.__file__), GUARD_SHA256, "reviewed RGBA guard")
    require_hash(Path(live.__file__), LIVE_HOST_SHA256, "reviewed live host")
    require_hash(live.WORKER, LIVE_WORKER_SHA256, "reviewed live worker")
    worker = require_hash(WORKER, WORKER_SHA256, "guarded worker")
    host_sha256 = file_sha256(Path(__file__))
    before = variant._inputs(registry_path, live.ASSET)
    blender = _unlinked_path(blender_executable, "Blender executable")
    require_hash(blender, live.BLENDER_SHA256, "Blender 5.2 executable")
    sdk = require_sdk_pins(sdk_script_root)
    pins = variant.ASSET_PINS[live.ASSET]
    guard.require_pins(
        asset_name=live.ASSET, blend_sha256=pins["blendSha256"],
        baseline_usf_sha256=pins["repairedUsfSha256"],
        blender_sha256=live.BLENDER_SHA256,
        sdk_mesh_sha256=guard.SDK_MESH_SHA256,
        blender_version="5.2.0")
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--asset", live.ASSET,
               "--blend", str(before["blend"]),
               "--repaired-usf", str(before["usf"]),
               "--native-usf", str(before["native"]),
               "--worklist", str(before["worklist"]),
               "--summary", str(before["summary"]),
               "--sdk-script-root", str(sdk),
               "--guard-worker-sha256", WORKER_SHA256,
               "--guard-host-sha256", host_sha256,
               "--blender-sha256", live.BLENDER_SHA256]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=timeout_seconds, env=environment, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise GuardedReadbackError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, host_sha256)
    after = variant._inputs(registry_path, live.ASSET)
    if before != after:
        raise GuardedReadbackError("variant inputs changed during readback")
    for path, digest, label in (
            (worker, WORKER_SHA256, "guarded worker"),
            (Path(__file__), host_sha256, "guarded host"),
            (Path(guard.__file__), GUARD_SHA256, "reviewed guard"),
            (Path(live.__file__), LIVE_HOST_SHA256, "reviewed live host"),
            (live.WORKER, LIVE_WORKER_SHA256, "reviewed live worker"),
            (blender, live.BLENDER_SHA256, "Blender executable")):
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
