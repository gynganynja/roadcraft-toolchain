"""Read-only integrity check for a D11 accepted-package baseline capture.

The result binds a no-swap baseline runner's declared outputs and the existing
partial native view links. It does not prove rendered scene bytes, PNG origin,
complete capture-time lighting, visual quality, or release acceptance.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from . import core, native_baseline_capture, native_capture_partial
from .native_capture_postflight import VARIANTS, VIEWS


MAX_JSON = 16 * 1024 * 1024


class BaselinePostflightError(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise BaselinePostflightError(message)


def _sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink(),
         f"File is missing or linked: {path}")
    before = path.stat()
    digest = core.sha256_file(path)
    after = path.stat()
    need((before.st_size, before.st_mtime_ns, before.st_ino) ==
         (after.st_size, after.st_mtime_ns, after.st_ino),
         f"File changed while hashing: {path}")
    return digest


def _json(path: Path, expected_sha: str, label: str) -> dict[str, Any]:
    need(path.is_absolute() and path.is_file() and not path.is_symlink(),
         f"{label} is missing or linked")
    before = path.stat()
    need(before.st_size <= MAX_JSON, f"{label} exceeds size limit")
    raw = path.read_bytes()
    after = path.stat()
    need(len(raw) == before.st_size and
         (before.st_size, before.st_mtime_ns, before.st_ino) ==
         (after.st_size, after.st_mtime_ns, after.st_ino),
         f"{label} changed while reading")
    need(sha256(raw).hexdigest() == expected_sha, f"{label} SHA-256 mismatch")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            need(key not in value, f"{label} repeats JSON key {key}")
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda item: (_ for _ in ()).throw(
                               ValueError(f"Non-finite JSON value: {item}")))
    except (UnicodeError, ValueError) as error:
        raise BaselinePostflightError(f"{label} is invalid JSON") from error
    need(isinstance(value, dict), f"{label} is not an object")
    return value


def _roster(contract: dict[str, Any], outer: Path) -> tuple[list[Path], dict[str, Path]]:
    run_id = contract["runId"]
    need(native_baseline_capture.RUN_ID.fullmatch(run_id) is not None,
         "Baseline run ID is invalid")
    need(outer.name == f"baseline_capture_{run_id}.json",
         "Baseline receipt filename differs from run ID")
    capture_plan = contract["capturePlan"]
    variants = capture_plan["variants"]
    views = capture_plan["viewsPerVariant"]
    runs = {variant: outer.parent / "baseline_runs" /
            f"aaa_{variant}_{run_id}{variant[:2]}" for variant in variants}
    need(contract.get("variantRuns") == {k: str(v) for k, v in runs.items()},
         "Baseline variant directories differ from contract")
    required = [outer]
    for run in runs.values():
        required.extend(run / name for name in (
            "native_controls.ps1", "probe.scenario", "stdout.log", "stderr.log",
            "report.json", "interior_geom.json", "interior_geom.transport.log"))
        for view in views:
            required.extend(run / f"{stem}_{view}{suffix}" for stem, suffix in (
                ("camera", ".json"), ("camera", ".transport.log"),
                ("pre_capture", ".json"), ("pre_capture", ".transport.log"),
                ("capture", ".json"), ("capture", ".transport.log"),
                ("cab", ".png"), ("partial", ".json")))
    need(len(required) == 1 + len(variants) * (7 + len(views) * 8) and
         contract.get("expectedOutputFiles") == [str(p) for p in required],
         "Baseline required output roster is incomplete")
    screenshot_root = outer.parent.parent.parent.parent / "root" / "bin" / "pc"
    screenshot_sources = [
        screenshot_root / f"d11_cab_{run_id}{variant[:2]}_{view}.png"
        for variant in variants for view in views]
    need(contract.get("screenshotSourceFiles") ==
         [str(path) for path in screenshot_sources],
         "Baseline screenshot-source roster differs")
    return required, runs


def validate(plan_path: str | Path, receipt_path: str | Path, *,
             expected_plan_sha256: str, expected_receipt_sha256: str) -> dict[str, Any]:
    plan_file = Path(plan_path).absolute()
    receipt_file = Path(receipt_path).absolute()
    need(plan_file != receipt_file, "Plan and receipt must be separate files")
    plan = _json(plan_file, expected_plan_sha256, "Externally pinned baseline plan")
    need(plan.get("status") == "BASELINE_OUTPUTS_DECLARED_NO_SWAP",
         "Baseline plan was not the no-swap preflight")
    contract = plan.get("outputContract")
    need(isinstance(contract, dict) and contract.get("schemaVersion") == 1 and
         contract.get("role") == "baseline" and contract.get("packageSwap") is False,
         "Baseline contract is not a no-swap D11 capture")
    capture_plan = contract.get("capturePlan")
    need(isinstance(capture_plan, dict) and
         set(capture_plan) == {"variants", "viewsPerVariant", "fullCapture"},
         "Baseline capture plan is incomplete")
    variants = capture_plan["variants"]
    views = capture_plan["viewsPerVariant"]
    need(isinstance(variants, list) and bool(variants) and
         variants == [name for name in VARIANTS if name in variants] and
         isinstance(views, list) and bool(views) and
         views == [name for name in VIEWS if name in views] and
         capture_plan["fullCapture"] is
         (variants == list(VARIANTS) and views == list(VIEWS)),
         "Baseline variant or view selection differs from D11 order")
    contract_sha = sha256(json.dumps(contract, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()
    need(plan.get("outputContractSha256") == contract_sha,
         "Baseline contract digest differs from the plan")
    need(contract.get("outerReceipt") == str(receipt_file),
         "Baseline receipt differs from reviewed plan")
    need(Path(contract["runner"]).resolve(strict=True) ==
         Path(native_baseline_capture.__file__).resolve(strict=True) and
         _sha(Path(contract["runner"])) == contract.get("runnerSha256"),
         "Baseline runner differs from reviewed plan")
    need(_sha(Path(contract["innerRunner"])) ==
         contract.get("innerRunnerSha256") ==
         native_baseline_capture.SDK_RUNNER_SHA256,
         "Inner SDK capture routine differs from reviewed bytes")
    linker_root = Path(contract["partialLinkerSource"])
    linker_pins = contract.get("partialLinkerSourcePins")
    need(isinstance(linker_pins, dict) and
         set(linker_pins) == {f"roadcraft/{name}" for name in (
             "__init__.py", "native_capture_partial.py",
             "native_capture_observation.py", "native_capture_postflight.py",
             "native_precapture_request.py", "review.py", "core.py")},
         "Baseline partial-linker source roster differs")
    for name, digest in linker_pins.items():
        need(_sha(linker_root / name) == digest,
             f"Baseline partial-linker source changed: {name}")
    helpers = contract.get("helperSourcePins")
    need(isinstance(helpers, dict) and set(helpers) == {
        "nativeControlsTemplate", "nativeAcceptance", "interiorCapture",
        "cabSurvey", "syntaxCheck"},
         "Baseline helper source roster differs")
    for name, pin in helpers.items():
        need(isinstance(pin, dict) and _sha(Path(pin["path"])) == pin["sha256"],
             f"Baseline helper source changed: {name}")
    accepted_sha = contract.get("acceptedSha256")
    need(isinstance(accepted_sha, str) and len(accepted_sha) == 64,
         "Accepted package SHA-256 is missing")
    toolchain = Path(native_baseline_capture.__file__).resolve().parents[2]
    registry = core.read_registry(toolchain / "project.json")
    accepted = registry["accepted"]
    project = Path(contract["acceptedProject"]).resolve(strict=True)
    need(project == Path(accepted["sourceRoot"]).resolve(strict=True) and
         Path(contract["acceptedPackage"]).resolve(strict=True) ==
         Path(accepted["package"]["path"]).resolve(strict=True) and
         accepted_sha == accepted["package"]["sha256"],
         "Baseline source or package differs from accepted registry")
    native_baseline_capture._source_is_accepted(registry, project)
    need(plan.get("editorMount") ==
         native_baseline_capture._mount(project, _sha),
         "Baseline editor mount changed since plan")
    for label in ("acceptedPackage", "installedPackage"):
        path = Path(contract[label])
        need(path.is_file() and not path.is_symlink() and _sha(path) == accepted_sha,
             f"{label} differs from accepted bytes")
    required, runs = _roster(contract, receipt_file)
    outer = _json(receipt_file, expected_receipt_sha256,
                  "Externally pinned baseline receipt")
    status = ("BASELINE_CAPTURES_READY_NO_SWAP" if capture_plan["fullCapture"]
              else "BASELINE_TRIAGE_CAPTURES_READY_NO_SWAP")
    need(outer.get("status") == status and
         outer.get("role") == "baseline" and
         outer.get("runId") == contract["runId"] and
         outer.get("acceptedProject") == str(project) and
         outer.get("acceptedSha256") == accepted_sha and
         outer.get("installedPackage") == contract["installedPackage"] and
         outer.get("outputContractSha256") == contract_sha and
         outer.get("editorMount") == plan.get("editorMount"),
         "Baseline receipt identity differs from reviewed plan")
    pins = outer.get("sourcePins")
    need(isinstance(pins, dict) and len(pins) == contract["sourcePinCount"] and
         sha256(json.dumps(pins, sort_keys=True, separators=(",", ":"))
                .encode("utf-8")).hexdigest() == contract["sourcePinsSha256"],
         "Baseline source pins differ from reviewed plan")
    for relative, digest in pins.items():
        path = (project / relative).resolve(strict=True)
        need(path.is_relative_to(project) and path.is_file() and
             not path.is_symlink() and _sha(path) == digest,
             f"Baseline source changed: {relative}")
    hashes = outer.get("requiredOutputSha256")
    need(isinstance(hashes, dict) and set(hashes) ==
         {str(path) for path in required[1:]},
         "Baseline receipt output hash roster differs")
    for path in required[1:]:
        need(path.is_file() and not path.is_symlink() and
             _sha(path) == hashes[str(path)],
             f"Baseline required output changed or is missing: {path}")
    variants = outer.get("variants")
    need(isinstance(variants, list) and
         [row.get("variant") for row in variants] == capture_plan["variants"],
         "Baseline receipt variant order differs")
    checked = 0
    request_ids: set[str] = set()
    for variant, row in zip(capture_plan["variants"], variants, strict=True):
        run = runs[variant]
        report_path = run / "report.json"
        need(row.get("report") == str(report_path) and
             row.get("reportSha256") == hashes[str(report_path)] and
             row.get("views") == len(views),
             f"{variant} report link differs from baseline output")
        report = _json(report_path, hashes[str(report_path)],
                       f"{variant} baseline variant report")
        context = contract["variantContexts"][variant]
        variant_status = ("D11_AAA_NATIVE_CAPTURES_READY" if
                          capture_plan["fullCapture"] else
                          "D11_AAA_NATIVE_TRIAGE_CAPTURES_READY")
        need(report.get("status") == variant_status and
             report.get("project") == str(project) and
             report.get("scene") == context["scene"] and
             report.get("candidatePackageSha256") == accepted_sha and
             report.get("captureContext") == context and
             report.get("outputContractSha256") == contract_sha and
             report.get("run") == str(run) and
             report.get("sourcePins") == pins and
             report.get("helperSha256") == hashes[str(run / "native_controls.ps1")] and
             report.get("editorLaunch", {}).get("projectArgument") == str(project),
             f"{variant} native report differs from baseline contract")
        engine_pid = report.get("enginePid")
        actions = report.get("actionEvents")
        need(type(engine_pid) is int and engine_pid > 0 and
             isinstance(actions, list) and len(actions) == 1 + 6 * len(views) and
             actions[0].get("action") == "InspectInteriorGeom" and
             all(action.get("status") == "PASS" and
                 action.get("enginePid") == engine_pid for action in actions),
             f"{variant} action transcript is incomplete")
        view_rows = report.get("views")
        need(isinstance(view_rows, list) and
             [view.get("view") for view in view_rows] == views,
             f"{variant} view order differs from plan")
        links = []
        for index, (view, view_row) in enumerate(zip(views, view_rows, strict=True)):
            image = run / f"cab_{view}.png"
            partial_path = run / f"partial_{view}.json"
            need(view_row.get("path") == str(image) and
                 view_row.get("sha256") == hashes[str(image)] and
                 view_row.get("partialViewLinkPath") == str(partial_path) and
                 view_row.get("partialViewLinkSha256") == hashes[str(partial_path)],
                 f"{variant} {view} image or partial link differs")
            partial = _json(partial_path, hashes[str(partial_path)],
                            f"{variant} {view} partial link")
            verified = native_capture_partial.verify_partial_view(partial)
            need(verified["status"] == "PARTIAL_VIEW_LINKAGE_CONSISTENT" and
                 verified["pairProtocolEligible"] is False and
                 partial["runId"] == contract["runId"] and
                 partial["variant"] == variant and partial["view"] == view and
                 partial["enginePid"] == engine_pid and
                 partial["screenshot"]["path"] == str(image),
                 f"{variant} {view} partial link failed")
            request_id = partial["transports"]["preScreenshotRead"]["requestId"]
            need(request_id not in request_ids,
                 f"{variant} {view} reused a pre-screenshot request ID")
            request_ids.add(request_id)
            action_slice = actions[1 + index * 6:1 + (index + 1) * 6]
            need(len(action_slice) == 6, f"{variant} {view} action slice is incomplete")
            for key, action in zip(native_capture_partial.EVENTS, action_slice,
                                   strict=True):
                expected_window = {field: action.get(field) for field in (
                    "action", "view", "enginePid", "status", "startedUtc",
                    "finishedUtc")}
                need(partial["actionWindows"].get(key) == expected_window,
                     f"{variant} {view} partial action differs from native report")
            links.append({"view": view, "path": str(partial_path),
                          "sha256": hashes[str(partial_path)]})
            checked += 1
        links_sha = sha256(json.dumps(links, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()
        need(row.get("partialViewLinksSha256") == links_sha,
             f"{variant} partial-view digest differs from outer receipt")
    return {"status": "BASELINE_PARTIAL_CAPTURE_INTEGRITY_VERIFIED",
            "checkedViews": checked, "checkedRequiredOutputs": len(required) - 1,
            "d11RosterComplete": capture_plan["fullCapture"],
            "planSha256": expected_plan_sha256,
            "receiptSha256": expected_receipt_sha256,
            "acceptedSha256": accepted_sha, "packageSwapDeclared": False,
            "pairProtocolEligible": False, "loadedSceneVerified": False,
            "captureProcessAuthenticated": False,
            "technicalPassed": False, "releaseReady": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args(argv)
    result = validate(args.plan, args.receipt,
                      expected_plan_sha256=args.plan_sha256,
                      expected_receipt_sha256=args.receipt_sha256)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
