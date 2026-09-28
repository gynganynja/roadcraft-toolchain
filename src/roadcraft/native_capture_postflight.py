"""Read-only integrity check for one completed D11 AAA native capture run.

This checks the reviewed no-write plan, outer receipt, all three variant
receipts, the exact required output roster, 45 partial pre-screenshot links,
the exact SSL content of every sent Read request, and the restored installed PAK. It
does not launch an editor, repair a failed run, compare baseline images, or
make a visual, campaign, or release acceptance decision.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib
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
PRECAPTURE_VERIFIER_SHA256 = (
    "31a1831c3cf899933b5d490c95de0508f8b0b80f250897f7696b08b009f34e80"
)


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
    with path.open("rb") as stream:
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
    _require(len(raw) <= MAX_RECEIPT_BYTES and len(raw) == before.st_size,
             f"{label} grew or changed while reading")
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


def _canonical_sha(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{label} needs UTC time")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PostflightError(f"{label} has invalid time") from exc
    _require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0,
             f"{label} must be UTC")
    return stamp.astimezone(timezone.utc)


def _required_roster(receipt: Path, backup: Path, run_id: str) -> tuple[list[Path], dict[str, Path]]:
    runs = {variant: receipt.parent / "runs" /
            f"aaa_{variant}_{run_id}{variant[:2]}" for variant in VARIANTS}
    required = [receipt, backup]
    for variant, run in runs.items():
        required.extend(run / name for name in (
            "native_controls.ps1", "probe.scenario", "stdout.log", "stderr.log",
            "report.json", "interior_geom.json", "interior_geom.transport.log"))
        for view in VIEWS:
            required.extend(run / name for name in (
                f"camera_{view}.json", f"camera_{view}.transport.log",
                f"pre_capture_{view}.json", f"pre_capture_{view}.transport.log",
                f"capture_{view}.json", f"capture_{view}.transport.log",
                f"cab_{view}.png", f"partial_{view}.json"))
    return required, runs


def _plain_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in
            ("action", "view", "enginePid", "status", "startedUtc", "finishedUtc")}


def _owned_processes(event: dict[str, Any], editor_pid: int, engine_pid: int,
                     label: str) -> None:
    _require(event.get("editorPid") == editor_pid and event.get("enginePid") == engine_pid,
             f"{label} process IDs mismatch")
    for side in ("ownedBefore", "ownedAfter"):
        snapshot = event.get(side)
        _require(isinstance(snapshot, dict) and
                 snapshot.get("editorPid") == editor_pid and
                 snapshot.get("enginePid") == engine_pid and
                 isinstance(snapshot.get("engineExit"), dict) and
                 snapshot["engineExit"].get("status") == "running" and
                 "processProbeError" not in snapshot,
                 f"{label} {side} process snapshot is incomplete")
        rows = snapshot.get("ownedProcesses")
        _require(isinstance(rows, list) and
                 any(isinstance(row, dict) and row.get("pid") == editor_pid
                     for row in rows) and
                 any(isinstance(row, dict) and row.get("pid") == engine_pid and
                     row.get("parentPid") == editor_pid and
                     row.get("name") == "Roadcraft ModEditor.exe" for row in rows),
                 f"{label} {side} lacks the owned editor process chain")


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
             capture_plan: str | Path, capture_plan_sha256: str,
             expected_capture_receipt_sha256: str | None = None) -> dict[str, Any]:
    """Return a capture-integrity result; never write or promote a candidate."""
    result: dict[str, Any] = {
        "scope": "D11 AAA technical capture integrity only",
        "captureIntegrityPassed": False,
        "checkedViews": 0,
        "checkedCameraProbes": 0,
        "checkedPartialViews": 0,
        "checkedReadRequests": 0,
        "checkedRequiredOutputs": 0,
        "preCaptureRequestContentVerified": False,
        "pairProtocolEligible": False,
        "loadedSceneVerified": False,
        "captureProcessAuthenticated": False,
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
        plan_path = _path(capture_plan, "reviewed capture plan")
        reviewed_plan, reviewed_plan_sha = _read_json(
            plan_path, "reviewed capture plan", capture_plan_sha256)
        _require(reviewed_plan.get("status") == "CAPTURE_OUTPUTS_DECLARED_NO_SWAP",
                 "Reviewed capture plan is not a no-swap plan")
        contract = reviewed_plan.get("outputContract")
        _require(isinstance(contract, dict) and contract.get("schemaVersion") == 1 and
                 contract.get("runId") == run_id and
                 contract.get("capturePlan") ==
                 {"fullCapture": True, "variants": list(VARIANTS),
                  "viewsPerVariant": list(VIEWS)},
                 "Reviewed output contract is not the exact D11 full capture")
        contract_sha = _canonical_sha(contract)
        _require(reviewed_plan.get("outputContractSha256") == contract_sha,
                 "Reviewed capture plan output contract SHA-256 mismatch")
        _same_path(contract.get("candidatePackage"), candidate,
                   "Contract candidate package")
        _same_path(contract.get("installedPackage"), installed,
                   "Contract installed package")
        _require(contract.get("candidateSha256") == candidate_sha and
                 contract.get("baselineSha256") == baseline_sha and
                 contract.get("prototype") is False,
                 "Reviewed contract package identity mismatch")
        runner_path = _path(contract.get("runner"), "reviewed runner")
        _require(runner_path.name == "capture_candidate_native.py" and
                 runner_path.parent.name == "D11_Interior_AAA_20260928",
                 "Reviewed runner is outside the D11 SDK layout")
        _file(runner_path, contract.get("runnerSha256"), "Reviewed runner")
        required, runs = _required_roster(
            receipt, receipt.parent / f"cat_d11t_before_{baseline_sha[:12]}_{run_id}.pak",
            run_id)
        _require(len(required) == 383 and
                 contract.get("expectedOutputFiles") == [str(path) for path in required] and
                 contract.get("variantRuns") ==
                 {variant: str(path) for variant, path in runs.items()} and
                 contract.get("outerReceipt") == str(receipt) and
                 contract.get("backup") == str(required[1]),
                 "Reviewed contract required output roster differs from D11 layout")
        linker_root = _path(contract.get("partialLinkerSource"), "partial linker source")
        linker_pins = contract.get("partialLinkerSourcePins")
        module_names = (
            "__init__.py", "native_capture_partial.py", "native_capture_observation.py",
            "native_capture_postflight.py", "native_precapture_request.py",
            "review.py", "core.py")
        _require(isinstance(linker_pins, dict) and
                 set(linker_pins) == {f"roadcraft/{name}" for name in module_names},
                 "Reviewed contract lacks partial linker source pins")
        for name, digest in linker_pins.items():
            _require(isinstance(name, str) and name.startswith("roadcraft/") and
                     "/" not in name[len("roadcraft/"):],
                     "Invalid partial linker source name")
            _file(linker_root / name, digest, f"Partial linker source {name}")
        for name in module_names:
            module_name = ("roadcraft" if name == "__init__.py" else
                           f"roadcraft.{name.removesuffix('.py')}")
            module = importlib.import_module(module_name)
            _require(Path(module.__file__).resolve() ==
                     linker_root / "roadcraft" / name,
                     f"Imported {module_name} is not the reviewed source")
        from . import native_precapture_request
        verifier_path = linker_root / "roadcraft" / "native_precapture_request.py"
        _file(verifier_path, PRECAPTURE_VERIFIER_SHA256,
              "Pre-capture request verifier source")
        _require(Path(native_precapture_request.__file__).resolve() == verifier_path,
                 "Imported pre-capture request verifier is not the reviewed source")
        helper_sources = contract.get("helperSourcePins")
        _require(isinstance(helper_sources, dict) and
                 set(helper_sources) == {"nativeControlsTemplate", "nativeAcceptance",
                                         "interiorCapture", "cabSurvey", "syntaxCheck"},
                 "Reviewed contract lacks helper source pins")
        for name, pin in helper_sources.items():
            _require(isinstance(name, str) and isinstance(pin, dict),
                     "Invalid helper source pin")
            _file(_path(pin.get("path"), f"Helper source {name}"), pin.get("sha256"),
                  f"Helper source {name}")
        template_path = _path(helper_sources["nativeControlsTemplate"]["path"],
                              "native controls template")
        _require(template_path.name == "native_controls_template.ps1" and
                 template_path.parent.name == "D11_Final_Candidate_20260925",
                 "Native controls template is outside the reviewed SDK layout")
        sdk_workspace = template_path.parent.parent
        _require(sdk_workspace == runner_path.parent.parent,
                 "Native controls template and capture runner have different SDK roots")
        result.update(capturePlanPath=str(plan_path), capturePlanSha256=reviewed_plan_sha,
                      outputContractSha256=contract_sha)
        outer, outer_sha = _read_json(receipt, "capture receipt")
        result.update(receiptPath=str(receipt), receiptSha256=outer_sha, runId=run_id)
        if expected_capture_receipt_sha256 is not None:
            _require(outer_sha == _digest(expected_capture_receipt_sha256,
                                          "expected_capture_receipt_sha256"),
                     "Capture receipt SHA-256 differs from the external pin")
        _require(outer.get("runId") == run_id, "Capture receipt run ID mismatch")
        _require(outer.get("outputContractSha256") == contract_sha,
                 "Capture receipt does not match reviewed output contract")
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
        _require(len(source_pins) == contract.get("sourcePinCount") and
                 _canonical_sha(source_pins) == contract.get("sourcePinsSha256"),
                 "Capture source pins differ from reviewed contract")
        output_hashes = outer.get("requiredOutputSha256")
        expected_hash_paths = [str(path) for path in required[1:]]
        _require(isinstance(output_hashes, dict) and
                 list(output_hashes) == expected_hash_paths,
                 "Capture output hash roster is incomplete or out of order")
        for output in required[1:]:
            _file(output, output_hashes[str(output)], f"Required output {output}")
            result["checkedRequiredOutputs"] += 1
        rows = outer.get("variants")
        _require(isinstance(rows, list) and len(rows) == len(VARIANTS),
                 "Capture receipt does not contain exactly three variants")
        from . import native_capture_partial
        request_ids: set[str] = set()
        for variant, row in zip(VARIANTS, rows, strict=True):
            _require(isinstance(row, dict) and row.get("variant") == variant and
                     row.get("views") == len(VIEWS),
                     f"Outer receipt variant {variant} is incomplete or out of order")
            run = runs[variant]
            nested_path = run / "report.json"
            _same_path(row.get("report"), nested_path, f"{variant} report")
            nested_sha = _digest(row.get("reportSha256"), f"{variant} report SHA-256")
            nested, _ = _read_json(nested_path, f"{variant} report",
                                   nested_sha)
            _require(nested.get("status") == "D11_AAA_NATIVE_CAPTURES_READY" and
                     nested.get("variant") == variant and
                     nested.get("candidatePackageSha256") == candidate_sha and
                     nested.get("sourcePins") == source_pins and
                     nested.get("outputContractSha256") == contract_sha,
                     f"{variant} report status, identity, or source chain mismatch")
            _same_path(nested.get("run"), run, f"{variant} run")
            context = contract["variantContexts"][variant]
            _require(nested.get("captureContext") == context and
                     nested.get("scene") == context.get("scene") and
                     nested.get("helperSha256") ==
                     output_hashes[str(run / "native_controls.ps1")],
                     f"{variant} scene or native helper differs from reviewed contract")
            scene = _path(context.get("scene"), f"{variant} scene source")
            _file(scene, context.get("sceneSha256"), f"{variant} scene source")
            editor_pid, engine_pid = nested.get("editorPid"), nested.get("enginePid")
            _require(type(editor_pid) is int and editor_pid > 0 and
                     type(engine_pid) is int and engine_pid > 0 and
                     editor_pid != engine_pid,
                     f"{variant} lacks distinct editor and engine PIDs")
            specs = nested.get("viewSpecs")
            _require(specs == context.get("cameraSpecs") and
                     isinstance(specs, dict) and list(specs) == list(VIEWS),
                     f"{variant} report camera specs differ from reviewed contract")
            images = nested.get("views")
            _require(isinstance(images, list) and len(images) == len(VIEWS),
                     f"{variant} report does not contain exactly fifteen views")
            actions = nested.get("actionEvents")
            boundaries = nested.get("viewEvents")
            _require(isinstance(actions, list) and len(actions) == 1 + len(VIEWS) * 6 and
                     isinstance(actions[0], dict) and
                     actions[0].get("action") == "InspectInteriorGeom" and
                     actions[0].get("status") == "PASS" and
                     isinstance(boundaries, list) and len(boundaries) == len(VIEWS),
                     f"{variant} action or view transcript is incomplete")
            previous_action_end: datetime | None = None
            for action_index, action in enumerate(actions):
                _require(isinstance(action, dict),
                         f"{variant} action {action_index} is malformed")
                action_start = _utc(action.get("startedUtc"),
                                    f"{variant} action {action_index} start")
                action_end = _utc(action.get("finishedUtc"),
                                  f"{variant} action {action_index} finish")
                _require(action_start <= action_end and
                         (previous_action_end is None or
                          previous_action_end <= action_start),
                         f"{variant} action chronology is reversed")
                previous_action_end = action_end
            _owned_processes(actions[0], editor_pid, engine_pid,
                             f"{variant} geometry inspection")
            partial_links: list[dict[str, str]] = []
            previous_boundary_end: datetime | None = None
            for index, (view, image) in enumerate(zip(VIEWS, images, strict=True)):
                _require(isinstance(image, dict) and image.get("view") == view,
                         f"{variant} view {view} is missing or out of order")
                slice_start = 1 + index * 6
                action_slice = actions[slice_start:slice_start + 6]
                mode = view.title().replace("_", "")
                labels = ("SetCab" + mode, "SettleCamera", "ScreenshotSourceGuard",
                          "ReadPreCapture", "CaptureCab" + mode,
                          "SaveScreenshot:" + view)
                for action, label in zip(action_slice, labels, strict=True):
                    _require(isinstance(action, dict) and
                             action.get("action") == label and
                             action.get("view") == view and
                             action.get("status") == "PASS",
                             f"{variant} {view} action transcript is not consecutive")
                    _owned_processes(action, editor_pid, engine_pid,
                                     f"{variant} {view} {label}")
                boundary = boundaries[index]
                _require(isinstance(boundary, dict) and boundary.get("view") == view and
                         boundary.get("status") == "PASS",
                         f"{variant} {view} view boundary identity failed")
                boundary_start = _utc(boundary.get("startedUtc"),
                                      f"{variant} {view} boundary start")
                boundary_end = _utc(boundary.get("finishedUtc"),
                                    f"{variant} {view} boundary finish")
                _require((previous_boundary_end is None or
                          previous_boundary_end <= boundary_start) and
                         boundary_start <=
                         _utc(action_slice[0]["startedUtc"], f"{variant} {view} first action") and
                         _utc(action_slice[-1]["finishedUtc"],
                              f"{variant} {view} final action") <= boundary_end,
                         f"{variant} {view} view boundary does not contain actions")
                previous_boundary_end = boundary_end
                _owned_processes({"editorPid": editor_pid, "enginePid": engine_pid,
                                  "ownedBefore": boundary.get("ownedBefore"),
                                  "ownedAfter": boundary.get("ownedAfter")},
                                 editor_pid, engine_pid, f"{variant} {view} boundary")
                image_path = run / f"cab_{view}.png"
                _same_path(image.get("path"), image_path, f"{variant} {view} image")
                _file(image_path, image.get("sha256"), f"{variant} {view} image", png=True)
                result["checkedViews"] += 1
                for suffix, digest_key in (
                    (f"camera_{view}.json", "cameraProbeSha256"),
                    (f"camera_{view}.transport.log", "cameraTransportLogSha256"),
                    (f"pre_capture_{view}.json", "preCaptureProbeSha256"),
                    (f"pre_capture_{view}.transport.log", "preCaptureTransportLogSha256"),
                    (f"capture_{view}.json", "captureProbeSha256"),
                    (f"capture_{view}.transport.log", "captureTransportLogSha256"),
                ):
                    artifact = run / suffix
                    _require(image.get(digest_key) == output_hashes[str(artifact)],
                             f"{variant} {view} {digest_key} differs from output audit")
                result["checkedCameraProbes"] += 1
                partial_path = run / f"partial_{view}.json"
                _same_path(image.get("partialViewLinkPath"), partial_path,
                           f"{variant} {view} partial link")
                partial_sha = _digest(image.get("partialViewLinkSha256"),
                                      f"{variant} {view} partial SHA-256")
                _require(partial_sha == output_hashes[str(partial_path)] and
                         image.get("sha256") == output_hashes[str(image_path)] and
                         image.get("cameraProbeSha256") ==
                         output_hashes[str(run / f"camera_{view}.json")],
                         f"{variant} {view} per-view hashes differ from output audit")
                partial, _ = _read_json(partial_path, f"{variant} {view} partial link",
                                        partial_sha)
                _require(partial.get("runId") == run_id and
                         partial.get("variant") == variant and
                         partial.get("view") == view and
                         partial.get("enginePid") == engine_pid and
                         partial.get("sceneSource") ==
                         {"path": str(scene), "sha256": context["sceneSha256"]} and
                         partial.get("helper") ==
                         {"path": str(run / "native_controls.ps1"),
                          "sha256": nested["helperSha256"]} and
                         partial.get("screenshot", {}).get("path") == str(image_path) and
                         partial.get("screenshot", {}).get("sha256") == image["sha256"] and
                         partial.get("screenshot", {}).get("resolutionPixels") ==
                         image.get("resolutionPixels"),
                         f"{variant} {view} partial link differs from nested report")
                expected_windows = {key: _plain_event(event) for key, event in
                                    zip(native_capture_partial.EVENTS, action_slice,
                                        strict=True)}
                _require(partial.get("actionWindows") == expected_windows,
                         f"{variant} {view} partial action windows differ from transcript")
                transports = partial.get("transports")
                _require(isinstance(transports, dict),
                         f"{variant} {view} partial transport links missing")
                for key, path, digest_key in (
                    ("setCamera", run / f"camera_{view}.json", "cameraProbeSha256"),
                    ("preScreenshotRead", run / f"pre_capture_{view}.json",
                     "preCaptureProbeSha256"),
                    ("captureTrigger", run / f"capture_{view}.json", "captureProbeSha256"),
                ):
                    transport = transports.get(key)
                    _require(isinstance(transport, dict) and
                             transport.get("path") == str(path) and
                             transport.get("sha256") == image[digest_key],
                             f"{variant} {view} {key} transport differs from report")
                    request_id = transport.get("requestId")
                    _require(isinstance(request_id, str) and request_id not in request_ids,
                             f"{variant} {view} repeats a transport request ID")
                    request_ids.add(request_id)
                pre_request = native_precapture_request.audit(
                    sdk_workspace, helper=run / "native_controls.ps1",
                    transport=run / f"pre_capture_{view}.json")
                _require(pre_request["generatedHelperVerified"] and
                         pre_request["transportRequestVerified"],
                         f"{variant} {view} Read request content did not verify")
                result["checkedReadRequests"] += 1
                verification = native_capture_partial.verify_partial_view(partial)
                _require(verification.get("status") == "PARTIAL_VIEW_LINKAGE_CONSISTENT" and
                         verification.get("pairProtocolEligible") is False and
                         verification.get("nativePostflightVerified") is False,
                         f"{variant} {view} partial link did not verify")
                partial_links.append({"view": view, "path": str(partial_path),
                                      "sha256": partial_sha})
                result["checkedPartialViews"] += 1
            _require(row.get("partialViewLinksSha256") == _canonical_sha(partial_links),
                     f"{variant} partial link digest differs from outer receipt")
        _require(result["checkedReadRequests"] == len(VARIANTS) * len(VIEWS),
                 "Incomplete pre-capture Read request audit")
        result["preCaptureRequestContentVerified"] = True
        result["captureIntegrityPassed"] = True
    except (PostflightError, OSError, ValueError, TypeError, KeyError) as exc:
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
    parser.add_argument("--capture-plan", type=Path, required=True)
    parser.add_argument("--capture-plan-sha256", required=True)
    parser.add_argument("--expected-capture-receipt-sha256")
    args = parser.parse_args(argv)
    report = validate(args.capture_receipt, run_id=args.run_id,
                      candidate_package=args.candidate_package,
                      candidate_sha256=args.candidate_sha256,
                      installed_package=args.installed_package,
                      baseline_sha256=args.baseline_sha256,
                      installed_sha256=args.installed_sha256,
                      capture_plan=args.capture_plan,
                      capture_plan_sha256=args.capture_plan_sha256,
                      expected_capture_receipt_sha256=args.expected_capture_receipt_sha256)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["captureIntegrityPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
