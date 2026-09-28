"""Read-only integrity check for one completed D11 AAA native capture run.

This checks the legacy runner's outer receipt, all three variant receipts,
45 pinned screenshots and camera probes, and the restored installed PAK. It
does not launch an editor, repair a failed run, compare baseline images, or
make a visual, campaign, or release acceptance decision.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from . import core


VARIANTS = ("maroon", "nearnew", "worn")
VIEWS = (
    "front_seat", "front_down", "right", "right_down", "right_panel_detail",
    "right_outer_low", "left", "left_down", "left_panel_detail", "rear",
    "rear_down", "rear_right_detail", "rear_left_detail", "overhead",
    "overhead_rear",
)
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PostflightError(ValueError):
    """A capture receipt, evidence file, or required identity is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PostflightError(message)


def _digest(value: str, label: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None,
             f"{label} needs a SHA-256 digest")
    return value.lower()


def _path(value: str | Path, label: str) -> Path:
    _require(isinstance(value, (str, Path)) and bool(str(value)), f"{label} needs a path")
    item = Path(value).expanduser()
    _require(item.is_absolute(), f"{label} must be absolute")
    _require(not item.is_symlink(), f"{label} must not be a symlink")
    return item.resolve()


def _same_path(value: Any, expected: Path, label: str) -> None:
    _require(isinstance(value, str) and bool(value), f"{label} needs a path")
    _require(_path(value, label) == expected, f"{label} is not the expected path")


def _read_json(path: Path, label: str, expected_sha: str | None = None) -> tuple[dict[str, Any], str]:
    _require(path.is_file() and not path.is_symlink(), f"{label} is missing or linked")
    before = path.stat()
    _require(before.st_size <= MAX_RECEIPT_BYTES, f"{label} exceeds receipt size limit")
    raw = path.read_bytes()
    after = path.stat()
    _require((before.st_size, before.st_mtime_ns, before.st_ino) ==
             (after.st_size, after.st_mtime_ns, after.st_ino),
             f"{label} changed while reading")
    digest = sha256(raw).hexdigest()
    if expected_sha is not None:
        _require(digest == _digest(expected_sha, f"{label} SHA-256"),
                 f"{label} SHA-256 mismatch")
    try:
        data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON value: {value}")))
    except (UnicodeError, ValueError) as exc:
        raise PostflightError(f"{label} is invalid JSON: {exc}") from exc
    _require(isinstance(data, dict), f"{label} must be a JSON object")
    return data, digest


def _file(path: Path, expected_sha: str, label: str, *, png: bool = False) -> None:
    _require(not path.is_symlink(), f"{label} must not be a symlink")
    pin = _digest(expected_sha, f"{label} SHA-256")
    try:
        identity = core.file_identity(path, pin)
    except OSError as exc:
        raise PostflightError(f"Cannot read {label}: {exc}") from exc
    _require(identity.get("exists") and identity.get("unchangedDuringRead") and
             identity.get("matchesExpected"), f"{label} is missing, changed, or has the wrong hash")
    if png:
        with path.open("rb") as stream:
            _require(stream.read(8) == PNG_SIGNATURE, f"{label} lacks a PNG signature")


def validate(receipt_path: str | Path, *, run_id: str,
             candidate_package: str | Path, candidate_sha256: str,
             installed_package: str | Path, baseline_sha256: str,
             installed_sha256: str,
             expected_capture_receipt_sha256: str | None = None) -> dict[str, Any]:
    """Return a capture-integrity result; never write or promote a candidate."""
    result: dict[str, Any] = {
        "scope": "D11 AAA technical capture integrity only",
        "captureIntegrityPassed": False,
        "checkedViews": 0,
        "checkedCameraProbes": 0,
        "visualReviewed": False,
        "campaignAccepted": False,
    }
    try:
        _require(isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{8}", run_id) is not None,
                 "run_id must be eight lowercase hexadecimal characters")
        candidate_sha = _digest(candidate_sha256, "candidate_sha256")
        baseline_sha = _digest(baseline_sha256, "baseline_sha256")
        installed_sha = _digest(installed_sha256, "installed_sha256")
        _require(installed_sha == baseline_sha,
                 "Expected installed hash must equal the accepted baseline hash after rollback")
        receipt = _path(receipt_path, "capture receipt")
        candidate = _path(candidate_package, "candidate package")
        installed = _path(installed_package, "installed package")
        _require(receipt.name == f"candidate_capture_{run_id}.json",
                 "Capture receipt name does not match run ID")
        outer, outer_sha = _read_json(receipt, "capture receipt")
        result.update(receiptPath=str(receipt), receiptSha256=outer_sha, runId=run_id)
        if expected_capture_receipt_sha256 is not None:
            _require(outer_sha == _digest(expected_capture_receipt_sha256,
                                          "expected_capture_receipt_sha256"),
                     "Capture receipt SHA-256 differs from the external pin")
        _require(outer.get("runId") == run_id, "Capture receipt run ID mismatch")
        _require(outer.get("status") == "NATIVE_CAPTURES_READY_BASELINE_RESTORED",
                 f"Capture did not complete successfully: {outer.get('status')}")
        _require(outer.get("prototype") is False, "Prototype capture is not the AAA candidate")
        _require(outer.get("candidateSha256") == candidate_sha,
                 "Capture candidate hash mismatch")
        _require(outer.get("baselineSha256") == baseline_sha,
                 "Capture baseline hash mismatch")
        _same_path(outer.get("candidatePackage"), candidate, "Capture candidate package")
        _same_path(outer.get("installedPackage"), installed, "Capture installed package")
        plan = outer.get("capturePlan")
        _require(isinstance(plan, dict) and plan.get("fullCapture") is True and
                 plan.get("variants") == list(VARIANTS) and
                 plan.get("viewsPerVariant") == list(VIEWS),
                 "Capture plan is not the exact three-variant, fifteen-view plan")
        rollback = outer.get("rollback")
        _require(isinstance(rollback, dict) and rollback.get("status") == "BASELINE_RESTORED"
                 and rollback.get("sha256") == baseline_sha,
                 "Capture rollback did not attest baseline restoration")
        backup = receipt.parent / f"cat_d11t_before_{baseline_sha[:12]}_{run_id}.pak"
        _same_path(rollback.get("backup"), backup, "Capture rollback backup")
        _file(candidate, candidate_sha, "Candidate package")
        _file(installed, installed_sha, "Installed package")
        _file(backup, baseline_sha, "Rollback backup")
        source_pins = outer.get("sourcePins")
        _require(isinstance(source_pins, dict) and bool(source_pins),
                 "Capture receipt lacks source pins")
        rows = outer.get("variants")
        _require(isinstance(rows, list) and len(rows) == len(VARIANTS),
                 "Capture receipt does not contain exactly three variants")
        for variant, row in zip(VARIANTS, rows, strict=True):
            _require(isinstance(row, dict) and row.get("variant") == variant and
                     row.get("views") == len(VIEWS),
                     f"Outer receipt variant {variant} is incomplete or out of order")
            run = receipt.parent / "runs" / f"aaa_{variant}_{run_id}{variant[:2]}"
            nested_path = run / "report.json"
            _same_path(row.get("report"), nested_path, f"{variant} report")
            nested_sha = _digest(row.get("reportSha256"), f"{variant} report SHA-256")
            nested, _ = _read_json(nested_path, f"{variant} report",
                                   nested_sha)
            _require(nested.get("status") == "D11_AAA_NATIVE_CAPTURES_READY" and
                     nested.get("variant") == variant and
                     nested.get("candidatePackageSha256") == candidate_sha and
                     nested.get("sourcePins") == source_pins,
                     f"{variant} report status, identity, or source chain mismatch")
            _same_path(nested.get("run"), run, f"{variant} run")
            specs = nested.get("viewSpecs")
            _require(isinstance(specs, dict) and set(specs) == set(VIEWS),
                     f"{variant} report does not declare the required camera views")
            images = nested.get("views")
            _require(isinstance(images, list) and len(images) == len(VIEWS),
                     f"{variant} report does not contain exactly fifteen views")
            for view, image in zip(VIEWS, images, strict=True):
                _require(isinstance(image, dict) and image.get("view") == view,
                         f"{variant} view {view} is missing or out of order")
                image_path = run / f"cab_{view}.png"
                _same_path(image.get("path"), image_path, f"{variant} {view} image")
                _file(image_path, image.get("sha256"), f"{variant} {view} image", png=True)
                result["checkedViews"] += 1
                probe_path = run / f"camera_{view}.json"
                _file(probe_path, image.get("cameraProbeSha256"),
                      f"{variant} {view} camera probe")
                result["checkedCameraProbes"] += 1
        result["captureIntegrityPassed"] = True
    except (PostflightError, OSError) as exc:
        result["error"] = str(exc)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-package", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--installed-package", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--installed-sha256", required=True)
    parser.add_argument("--expected-capture-receipt-sha256")
    args = parser.parse_args(argv)
    report = validate(args.capture_receipt, run_id=args.run_id,
                      candidate_package=args.candidate_package,
                      candidate_sha256=args.candidate_sha256,
                      installed_package=args.installed_package,
                      baseline_sha256=args.baseline_sha256,
                      installed_sha256=args.installed_sha256,
                      expected_capture_receipt_sha256=args.expected_capture_receipt_sha256)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["captureIntegrityPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
