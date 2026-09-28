"""Read-only audit of the D11 pre-screenshot SSL request content.

This checks the pinned generator chain and, when supplied, a generated helper
and a Read transport record. It does not contact the editor or authenticate a
native reply, loaded scene, screenshot, or complete renderer state.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SOURCE_SHA256 = {
    "D11_Final_Candidate_20260925/native_controls_template.ps1":
        "9722e35723f75fd841f95e81848cdf1759261d9ef2141fd6948ac9e23ac60c0d",
    "D11_Final_Candidate_20260925/native_acceptance.py":
        "89b1431099bacc00a3173ffbe46c9dbfc1047707828db929df949e40df11f580",
    "D11_Interior_Repair_20260926/capture_interior.py":
        "dae524f24afad50e04902d8310775478577d5f48c8610fb3595e3b376ea8f19f",
    "D11_Interior_Repair_20260926/capture_cab_survey.py":
        "083652fc56cf6d0bcc54ab139c7100f126427f9a5d2da9df5fb29dbf3eeec2ef",
    "D11_Interior_AAA_20260928/capture_candidate_native.py":
        "6449ddc08c81165231ee39f90e171b2f5a2c7fdecc9e2e21b1b2c1b2d4733585",
}
READ_SCRIPT_SHA256 = "61cd4d77e6441660f094bb86fa62eda0fa9a93c37c85aa7d31df5fac111b732e"
NORMALIZED_HELPER_SHA256 = "44bf3dacc0fd2bb7fb163ea464da4ac117d0c3139e9667fa8a734dae85c1fda5"
HELPER_RUN_ID_COUNT = 20
HELPER_RUN = re.compile(r"aaa_(maroon|nearnew|worn)_([0-9a-f]{8})(ma|ne|wo)\Z")
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TRANSPORT_BYTES = 4 * 1024 * 1024
REPLACE_LINE = "$script=$script.Replace('__ACTION__',$action)"


class PrecaptureRequestError(ValueError):
    """The current pre-screenshot request no longer matches reviewed bytes."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise PrecaptureRequestError(message)


def _read(path: Path, limit: int) -> bytes:
    _need(path.is_absolute() and path.is_file() and not path.is_symlink(),
          f"Missing or linked plain file: {path}")
    before = path.stat()
    _need(0 < before.st_size <= limit, f"File size outside bound: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    after = path.stat()
    _need(len(raw) == before.st_size and
          (before.st_size, before.st_mtime_ns, before.st_ino) ==
          (after.st_size, after.st_mtime_ns, after.st_ino),
          f"File changed while reading: {path}")
    return raw


def _lf(value: str) -> str:
    _need("\r" not in value.replace("\r\n", ""), "Bare CR in request source")
    return value.replace("\r\n", "\n")


def _script_block(helper_source: str) -> str:
    source = _lf(helper_source.lstrip("\ufeff"))
    start = "$script=@'\n"
    end = "\n'@\n$action=''"
    _need(source.count(start) == 1 and source.count(end) == 1,
          "Expected one fixed SSL here-string and empty Read action")
    block = source.split(start, 1)[1].split(end, 1)[0]
    _need(block.count("__ACTION__") == 1, "Expected one action placeholder")
    return block


def _reviewed_read_script(helper_source: str) -> str:
    script = _script_block(helper_source).replace("__ACTION__", "")
    _need(sha256(script.encode("utf-8")).hexdigest() == READ_SCRIPT_SHA256,
          "Read request bytes differ from reviewed script")
    return script


def _generated_helper(helper_path: Path, helper_source: str,
                      expected_script: str) -> None:
    source = _lf(helper_source.lstrip("\ufeff"))
    match = HELPER_RUN.fullmatch(helper_path.parent.name)
    _need(helper_path.name == "native_controls.ps1" and match is not None and
          match.group(3) == {"maroon": "ma", "nearnew": "ne", "worn": "wo"}[match.group(1)],
          "Generated helper path does not identify one D11 variant/run")
    run_token = match.group(2) + match.group(3)
    _need(_script_block(source).replace("__ACTION__", "") == expected_script,
          "Generated helper Read script differs from template")
    action_start = "$action=''\n"
    action_end = "\n" + REPLACE_LINE
    _need(source.count(action_start) == 1 and source.count(action_end) == 1,
          "Generated helper action replacement is ambiguous")
    mode_actions = source.split(action_start, 1)[1].split(action_end, 1)[0]
    _need("'Read'" not in mode_actions,
          "Generated helper adds a Read-mode action")
    _need(source.count(REPLACE_LINE) == 1 and
          source.count("$speaker.Send((New-SslMessage $requestId $script))") == 1,
          "Generated helper request send or action replacement changed")
    after_replace = source.split(REPLACE_LINE, 1)[1].split(
        "$speaker.Send((New-SslMessage $requestId $script))", 1)[0]
    _need(re.search(r"(?m)^\s*\$script\s*=", after_replace) is None,
          "Generated helper changes SSL script after action replacement")
    _need(source.count(run_token) == HELPER_RUN_ID_COUNT and
          sha256(source.replace(run_token, "RUNID").encode("utf-8")).hexdigest()
          == NORMALIZED_HELPER_SHA256,
          "Generated helper differs from reviewed full script")


def _transport(raw: bytes, expected_script: str, helper_sha256: str) -> None:
    try:
        row: Any = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON value: {value}")))
    except (UnicodeError, ValueError) as exc:
        raise PrecaptureRequestError(f"Invalid transport JSON: {exc}") from exc
    _need(isinstance(row, dict), "Transport must be an object")
    _need(row.get("schema") == 1 and row.get("status") == "pass" and
          row.get("stage") == "response_received" and row.get("mode") == "Read" and
          row.get("readOnly") is True, "Transport is not a passing Read reply")
    _need(row.get("helperSha256") == helper_sha256,
          "Transport does not pin the generated helper")
    script = row.get("script")
    _need(isinstance(script, str) and len(script) <= MAX_SOURCE_BYTES,
          "Transport has no bounded request script")
    _need(_lf(script) == expected_script,
          "Sent Read request differs from reviewed SSL bytes")


def audit(workspace: Path, *, helper: Path | None = None,
          transport: Path | None = None) -> dict[str, Any]:
    """Verify exact source chain and optional generated/request bytes, no writes."""
    _need(workspace.is_absolute() and workspace.is_dir(), "Workspace root must exist")
    _need(transport is None or helper is not None,
          "Transport verification requires its generated helper")
    source_bytes: dict[str, bytes] = {}
    for relative, expected in SOURCE_SHA256.items():
        raw = _read(workspace / relative, MAX_SOURCE_BYTES)
        _need(sha256(raw).hexdigest() == expected,
              f"Generator source changed: {relative}")
        source_bytes[relative] = raw
    template = source_bytes["D11_Final_Candidate_20260925/native_controls_template.ps1"]
    try:
        expected_script = _reviewed_read_script(template.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise PrecaptureRequestError("Template is not UTF-8") from exc
    helper_sha = None
    if helper is not None:
        helper_raw = _read(helper, MAX_SOURCE_BYTES)
        try:
            _generated_helper(helper, helper_raw.decode("utf-8-sig"), expected_script)
        except UnicodeError as exc:
            raise PrecaptureRequestError("Generated helper is not UTF-8") from exc
        helper_sha = sha256(helper_raw).hexdigest()
    if transport is not None:
        _transport(_read(transport, MAX_TRANSPORT_BYTES), expected_script, helper_sha)
    return {
        "status": "PINNED_PRECAPTURE_REQUEST_VERIFIED",
        "sourcePinsVerified": True,
        "requestScriptSha256Lf": READ_SCRIPT_SHA256,
        "generatedHelperVerified": helper is not None,
        "transportRequestVerified": transport is not None,
        "generatedHelperSha256": helper_sha,
        "loadedSceneVerified": False,
        "captureProcessAuthenticated": False,
        "pairProtocolEligible": False,
        "nativePostflightVerified": False,
        "scope": "reviewed SSL request content and generator-source identity only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Machine JSON; defaults to local/machine.json")
    parser.add_argument("--helper", type=Path, help="Optional generated native_controls.ps1")
    parser.add_argument("--transport", type=Path, help="Optional Read transport JSON (requires helper)")
    args = parser.parse_args(argv)
    toolchain = Path(__file__).resolve().parents[2]
    config = args.config or toolchain / "local" / "machine.json"
    try:
        machine = json.loads(_read(config.resolve(), MAX_SOURCE_BYTES))
        _need(isinstance(machine, dict) and isinstance(machine.get("sdkRoot"), str),
              "Machine config needs sdkRoot")
        workspace = Path(machine["sdkRoot"])
        result = audit(workspace, helper=args.helper, transport=args.transport)
    except (PrecaptureRequestError, OSError, ValueError) as exc:
        parser.exit(2, f"precapture-request: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
