"""Offline validation and explicit runner for four scratch SSL runtime probes.

The PowerShell helper is transport-only. Its reply is not evidence for the
baseline/candidate capture gate; even a valid reply leaves the loaded scene
and complete renderer state unverified.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Any

from .native_runtime_probe import NativeRuntimeProbeError, parse_probe_reply


PROBE_SHA256 = {
    "weather_state": "c39033a632e0ec8e3f36bf6e6dda1f0602d67bdd12d6a77b364461982d43b809",
    "camera_up": "086a93e10c29f97bd5dd215e7a0f155c4f0588618178480105f9d1a50ad9f09b",
    "sun_direction": "2ebd5914d635fae2ff603e73721f0c649fd5de927a50bd7a9aad46f4a1bff6fe",
    "daytime": "be7b9db66ce6a1df6a8ee3e1ed597f9cf6ccebddeb7ec2797c965e7b279ddd86",
}
SCENE_SHA256 = {
    "maroon": "9481bca1db96dd5c3c0c201f9d7f84e0b16fd7e683905c286060b16e9d53dfa1",
    "nearnew": "7bb6428240ecb1acf0d31674d855d8af6eebefe57f62d7f4956bf8d603b0a701",
    "worn": "a518939a52afa5dd946a480161545e257fa89c7d0968d489937a27adf5a1bd8c",
}
EDITOR_SHA256 = "ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7"
JSON_DLL_SHA256 = "60aad8900d2e663fe8a7e3606f644bf9b4e6f482112ca2514a9b499b4c9134cc"
CONSOLE_DLL_SHA256 = "26007b4d104045fc9aed7276761534abe42b07f293ca757385d47635ccd9b3f3"
REQUEST_ID = re.compile(r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9a-f]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}\Z")
OUTPUT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.json\Z")
MAX_RESPONSE_BYTES = 65_536


class ProbeTransportError(ValueError):
    """A scratch probe plan or sealed transport failed verification."""


@dataclass(frozen=True)
class ProbeInputs:
    kind: str
    variant: str
    fragment: Path
    scene: Path
    editor: Path
    json_dll: Path
    console_dll: Path
    helper: Path
    machine_config: Path
    fragment_sha256: str
    scene_sha256: str
    editor_sha256: str
    json_dll_sha256: str
    console_dll_sha256: str


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeTransportError(message)


def _same_path(actual: Any, expected: Path) -> bool:
    return isinstance(actual, str) and os.path.isabs(actual) and os.path.normcase(os.path.abspath(actual)) == os.path.normcase(
        os.path.abspath(expected)
    )


def _utc(value: Any, field: str) -> datetime:
    _check(isinstance(value, str), f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProbeTransportError(f"{field} is not an ISO UTC timestamp") from error
    _check(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
           f"{field} is not UTC")
    return parsed.astimezone(timezone.utc)


def pinned_inputs(kind: str, variant: str) -> ProbeInputs:
    """Resolve the exact reviewed files from machine config, without editor I/O."""
    _check(kind in PROBE_SHA256, "Unknown probe kind")
    _check(variant in SCENE_SHA256, "Unknown validation variant")
    toolchain = Path(__file__).resolve().parents[2]
    config = Path(os.environ.get("ROADCRAFT_CONFIG") or toolchain / "local" / "machine.json")
    machine = json.loads(config.read_text(encoding="utf-8"))
    sdk_root = Path(machine["sdkRoot"])
    _check(sdk_root.is_absolute(), "Machine SDK root is not absolute")
    scene_name = f"d11t_{variant}_validation"
    return ProbeInputs(
        kind=kind, variant=variant,
        fragment=toolchain / "operations" / "probes" / f"d11_{kind}.ssl",
        scene=sdk_root / "D11_Interior_AAA_20260928" / "p" / "mods_source"
              / "xscenes" / "mods" / scene_name / f"{scene_name}.scn",
        editor=sdk_root.parent / "root" / "bin" / "pc" / "Roadcraft ModEditor.exe",
        json_dll=sdk_root.parent / "tools" / "bin" / "ModEditor" / "Saber.Json.dll",
        console_dll=sdk_root.parent / "tools" / "bin" / "ModEditor" / "Saber.ConsoleTre.dll",
        helper=toolchain / "operations" / "probes" / "native_runtime_probe.ps1",
        machine_config=config,
        fragment_sha256=PROBE_SHA256[kind],
        scene_sha256=SCENE_SHA256[variant],
        editor_sha256=EDITOR_SHA256,
        json_dll_sha256=JSON_DLL_SHA256,
        console_dll_sha256=CONSOLE_DLL_SHA256,
    )


def _assert_plain_directory_tree(current: Path) -> None:
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError as error:
            raise ProbeTransportError(f"Scratch directory is missing: {current}") from error
        _check(stat.S_ISDIR(metadata.st_mode), "Scratch path has a non-directory ancestor")
        _check(not current.is_symlink() and not (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ), "Scratch path has a reparse-point ancestor")
        if current.parent == current:
            break
        current = current.parent


def _check_scratch_location(output: Path, toolchain: Path) -> Path:
    _check(output.is_absolute(), "Scratch receipt path is not absolute")
    scratch = toolchain / "local" / "native-probes"
    _check(os.path.normcase(os.path.abspath(output.parent)) ==
           os.path.normcase(os.path.abspath(scratch)),
           "Scratch receipt must be directly under local/native-probes")
    _check(OUTPUT_NAME.fullmatch(output.name) is not None, "Scratch receipt basename is invalid")
    return scratch


def verify_scratch_output(output: Path, toolchain: Path) -> None:
    """Require one new JSON file directly under the ignored local scratch root."""
    scratch = _check_scratch_location(output, toolchain)
    _check(not output.exists() and not output.is_symlink(), "Scratch receipt already exists")
    _assert_plain_directory_tree(scratch)


def _verify_common(record: dict[str, Any], inputs: ProbeInputs) -> None:
    """Verify all reviewed inputs common to an offline plan or a receipt."""
    _check(isinstance(record, dict), "Probe record is not an object")
    _check(record.get("schema") == 1, "Unknown probe record schema")
    _check(record.get("probeKind") == inputs.kind, "Probe kind mismatch")
    _check(record.get("variant") == inputs.variant, "Variant mismatch")
    for field, path in (
        ("fragmentPath", inputs.fragment), ("sceneSourcePath", inputs.scene),
        ("editorPath", inputs.editor), ("helperPath", inputs.helper),
        ("jsonDllPath", inputs.json_dll), ("consoleDllPath", inputs.console_dll),
        ("machineConfigPath", inputs.machine_config),
    ):
        _check(_same_path(record.get(field), path), f"{field} mismatch")
    fragment_bytes = inputs.fragment.read_bytes()
    _check(hashlib.sha256(fragment_bytes).hexdigest() == inputs.fragment_sha256,
           "Current fragment SHA-256 mismatch")
    for label, path, expected in (
        ("scene source", inputs.scene, inputs.scene_sha256),
        ("editor", inputs.editor, inputs.editor_sha256),
        ("Saber.Json.dll", inputs.json_dll, inputs.json_dll_sha256),
        ("Saber.ConsoleTre.dll", inputs.console_dll, inputs.console_dll_sha256),
    ):
        _check(_sha(path) == expected, f"Current {label} SHA-256 mismatch")
    for field, expected in (
        ("fragmentSha256", inputs.fragment_sha256),
        ("requestScriptSha256", inputs.fragment_sha256),
        ("sceneSourceSha256", inputs.scene_sha256),
        ("editorSha256", inputs.editor_sha256),
        ("jsonDllSha256", inputs.json_dll_sha256),
        ("consoleDllSha256", inputs.console_dll_sha256),
        ("helperSha256", _sha(inputs.helper)),
        ("machineConfigSha256", _sha(inputs.machine_config)),
    ):
        _check(record.get(field) == expected, f"{field} mismatch")
    script = fragment_bytes.decode("utf-8", errors="strict")
    _check(record.get("requestScript") == script, "Exact request script mismatch")
    _check(record.get("readOnly") is True, "Read-only marker missing")
    _check(record.get("pairProtocolEligible") is False, "Pair gate must remain false")
    _check(record.get("loadedSceneVerified") is False, "Loaded scene must remain unverified")


def verify_probe_plan(record: dict[str, Any], inputs: ProbeInputs) -> dict[str, Any]:
    """Verify the offline plan and every input the helper would send/use."""
    _verify_common(record, inputs)
    _check(record.get("status") == "PREFLIGHT_ONLY", "Plan status is not offline")
    _check(record.get("transportSent") is False, "Offline plan claims a transport send")
    return {"status": "PREFLIGHT_VERIFIED", "probeKind": inputs.kind,
            "variant": inputs.variant, "transportSent": False, "pairProtocolEligible": False}


def verify_probe_receipt(record: dict[str, Any], inputs: ProbeInputs) -> dict[str, Any]:
    """Verify a transport response; never promote it to matched-capture evidence."""
    _verify_common(record, inputs)
    _check(record.get("status") == "TRANSPORT_RESPONSE_UNVALIDATED", "Transport did not finish")
    _check(record.get("stage") == "response_received", "No completed response stage")
    _check(record.get("transportSent") is True, "Request was not sent")
    _check(type(record.get("engineProcessId")) is int and record["engineProcessId"] > 0,
           "Engine PID missing")
    started = _utc(record.get("engineStartUtc"), "engineStartUtc")
    _check(isinstance(record.get("workspace"), str) and bool(record["workspace"]),
           "Native workspace identity missing")
    _check(isinstance(record.get("requestId"), str) and REQUEST_ID.fullmatch(record["requestId"]) is not None,
           "Native request GUID malformed")
    prepared = _utc(record.get("requestPreparedUtc"), "requestPreparedUtc")
    send_started = _utc(record.get("requestSendStartedUtc"), "requestSendStartedUtc")
    sent = _utc(record.get("requestSentUtc"), "requestSentUtc")
    received = _utc(record.get("responseReceivedUtc"), "responseReceivedUtc")
    _check(started <= prepared <= send_started <= sent <= received,
           "Request/response UTC order invalid")
    _check((received - send_started).total_seconds() <= 60, "Response elapsed time exceeds bound")
    encoded = record.get("responseBase64")
    _check(isinstance(encoded, str), "Raw native response missing")
    _check(len(encoded) <= 4 * ((MAX_RESPONSE_BYTES + 2) // 3),
           "Encoded native response exceeds byte bound")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ProbeTransportError("Raw native response is not valid base64") from error
    _check(1 <= len(raw) <= MAX_RESPONSE_BYTES, "Native response exceeds byte bound")
    _check(type(record.get("responseBytes")) is int and record["responseBytes"] == len(raw),
           "Response byte length mismatch")
    _check(record.get("responseSha256") == hashlib.sha256(raw).hexdigest(),
           "Raw native response SHA-256 mismatch")
    _check(raw.endswith(b"\0") and raw.count(b"\0") == 1, "Native response terminator invalid")
    try:
        response = raw[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ProbeTransportError("Raw native response is not UTF-8") from error
    _check(record.get("response") == response, "Decoded native response mismatch")
    try:
        parsed = parse_probe_reply(inputs.kind, response)
    except NativeRuntimeProbeError as error:
        raise ProbeTransportError(f"Native probe result rejected: {error}") from error
    return {
        "status": "PARTIAL_RESPONSE_CONSISTENCY_VERIFIED",
        "probeKind": inputs.kind,
        "variant": inputs.variant,
        "engineProcessId": record["engineProcessId"],
        "reported": parsed["reported"],
        "sceneSourceSha256": inputs.scene_sha256,
        "loadedSceneVerified": False,
        "pairProtocolEligible": False,
        "limitations": [
            "This transport pins an on-disk scene source; it does not verify the scene loaded in the editor.",
            "Weather preset, ambient RGB, exposure, tonemap, renderer mode, and complete scene lights remain unobserved.",
            "A method smoke reply is not linked to a screenshot or a baseline/candidate capture pair.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=tuple(PROBE_SHA256))
    parser.add_argument("--variant", required=True, choices=tuple(SCENE_SHA256))
    parser.add_argument("--execute", action="store_true", help="Contact an already-running editor")
    parser.add_argument("--engine-pid", type=int)
    parser.add_argument("--output", type=Path, help="New absolute JSON receipt for --execute")
    args = parser.parse_args(argv)
    if args.execute:
        if (not args.engine_pid or args.engine_pid <= 0 or args.output is None
                or not args.output.is_absolute()):
            parser.error("--execute requires --engine-pid > 0 and an absolute --output")
    elif args.engine_pid is not None or args.output is not None:
        parser.error("PID and output are only accepted with --execute")
    executable = shutil.which("pwsh")
    if executable is None:
        raise ProbeTransportError("PowerShell 7 (pwsh) is unavailable")
    inputs = pinned_inputs(args.kind, args.variant)
    if args.execute:
        scratch = _check_scratch_location(args.output, inputs.helper.parents[2])
        _assert_plain_directory_tree(scratch.parent)
        scratch.mkdir(exist_ok=True)
        verify_scratch_output(args.output, inputs.helper.parents[2])
    command = [executable, "-NoProfile", "-NonInteractive", "-File", str(inputs.helper),
               "-Kind", args.kind, "-Variant", args.variant]
    if args.execute:
        command.extend(["-EngineProcessId", str(args.engine_pid),
                        "-OutputPath", str(args.output), "-Execute"])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if completed.returncode != 0:
        raise ProbeTransportError(f"Scratch transport failed: {completed.stderr.strip()}")
    if args.execute:
        record = json.loads(args.output.read_text(encoding="utf-8"))
        result = verify_probe_receipt(record, inputs)
        result["receipt"] = str(args.output)
    else:
        record = json.loads(completed.stdout)
        result = verify_probe_plan(record, inputs)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
