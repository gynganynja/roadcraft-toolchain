"""Capture the accepted D11 project without changing the installed package.

This adapter reuses the hash-pinned D11 camera/capture routine, but mounts the
accepted source project and writes a distinct baseline receipt and run tree.
Its present Read response is partial: a successful run is diagnostic evidence,
not a matched-pair or release pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import shutil
from typing import Any

from . import core


SDK_RUNNER_SHA256 = "78e2f3634cbfde8d2b64b15652275474646338efe7f1f25a760a2140cfdc73dc"
RUN_ID = re.compile(r"[0-9a-f]{8}\Z")


class BaselineCaptureError(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineCaptureError(message)


def _mount(project: Path, digest) -> dict[str, str]:
    """Validate the effective paths in the accepted editor configuration."""
    config = project / "config" / "editor.cfg"
    need(config.is_file() and not config.is_symlink(), "Accepted editor.cfg is missing or linked")
    content = config.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for match in re.finditer(
        r"(?m)^  (ModsSourceLocal|ProjectPath): ([^\r\n]*(?:\r?\n    [^\r\n]*)*)",
        content,
    ):
        name = match.group(1)
        need(name not in fields, f"Repeated editor mount field: {name}")
        fields[name] = " ".join(line.strip() for line in match.group(2).splitlines())
    root = project.resolve(strict=True).as_posix()
    need(fields == {"ModsSourceLocal": root + "/mods_source",
                    "ProjectPath": root + "/.project"},
         "Accepted editor config does not mount the accepted project")
    return {"editorConfig": str(config), "editorConfigSha256": digest(config),
            "modsSourceLocal": fields["ModsSourceLocal"],
            "projectPath": fields["ProjectPath"]}


def _source_is_accepted(registry: dict[str, Any], project: Path) -> None:
    accepted = registry["accepted"]
    need(Path(accepted["sourceRoot"]).resolve(strict=True) == project,
         "Baseline project differs from the accepted registry source root")
    for key in ("sourceManifest", "authoringInventory"):
        pin = accepted[key]
        identity = core.file_identity(pin["path"], pin["sha256"])
        need(identity.get("matchesExpected") is True and
             identity.get("unchangedDuringRead") is True,
             f"Accepted {key} differs from its registry pin")
    source = core.verify_manifest(accepted["sourceManifest"]["path"], project)
    authoring = core.verify_authoring_inventory(
        accepted["authoringInventory"]["path"], project)
    need(source["passed"] and authoring["passed"],
         "Accepted project source differs from its pinned inventory")


def _load_inner(toolchain: Path, project: Path, accepted_sha: str):
    machine = core.read_config(toolchain / "local" / "machine.json")
    sdk = Path(machine["sdkRoot"]).resolve(strict=True)
    runner = sdk / "D11_Interior_AAA_20260928" / "capture_candidate_native.py"
    need(runner.is_file() and not runner.is_symlink(), "Pinned SDK capture runner is missing")
    identity = core.file_identity(runner, SDK_RUNNER_SHA256)
    need(identity.get("matchesExpected") is True and
         identity.get("unchangedDuringRead") is True,
         "SDK capture runner differs from reviewed bytes")
    spec = importlib.util.spec_from_file_location("_roadcraft_d11_baseline_inner", runner)
    need(spec is not None and spec.loader is not None, "Could not load reviewed capture runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    need(module.EXPECTED_BASE_SHA == accepted_sha and
         module.WORKSPACE.resolve() == sdk and
         module.LIVE.resolve(strict=True) ==
         Path(machine["installedPackage"]).resolve(strict=True),
         "SDK runner's baseline or installed package path differs")
    module.TOOLCHAIN_SRC = toolchain / "src"
    module.PROJECT = project
    module.RUNS = module.NATIVE / "baseline_runs"
    module.LOCK = module.NATIVE / "baseline_capture.lock.json"
    module.editor_mount = lambda path: _mount(path, module.sha)
    return module


def _contract(inner, run_id: str, project: Path, package: Path,
              accepted_sha: str, pins: dict[str, str],
              variants: tuple[str, ...], views: tuple[str, ...],
              camera_specs: dict[str, Any]) -> dict[str, Any]:
    outer = inner.NATIVE / f"baseline_capture_{run_id}.json"
    runs = {variant: inner.RUNS / f"aaa_{variant}_{run_id}{variant[:2]}"
            for variant in variants}
    required = [outer]
    screenshots = []
    contexts = {}
    for variant, run in runs.items():
        scene = project / "mods_source" / "xscenes" / "mods" / inner.SCENES[variant]
        candidate_scene = inner.HERE / "p" / "mods_source" / "xscenes" / "mods" / inner.SCENES[variant]
        need(inner.sha(scene) == inner.sha(candidate_scene),
             f"{variant} accepted and candidate validation scenes differ")
        contexts[variant] = {
            "scene": str(scene), "sceneSha256": inner.sha(scene),
            "cameraBasis": "_cockpit_camera; offsets (forward,left,up) in metres",
            "cameraSpecs": {name: camera_specs[name] for name in views},
            "plannedResolutionPixels": {"status": "unknown"},
            "runtimeLighting": {"status": "unknown"},
            "protocol": "SetCab, ReadPreCapture, CaptureCab PNG, copied image, partial view link",
        }
        required.extend(run / name for name in (
            "native_controls.ps1", "probe.scenario", "stdout.log", "stderr.log",
            "report.json", "interior_geom.json", "interior_geom.transport.log"))
        for view in views:
            required.extend(run / f"{stem}_{view}{suffix}" for stem, suffix in (
                ("camera", ".json"), ("camera", ".transport.log"),
                ("pre_capture", ".json"), ("pre_capture", ".transport.log"),
                ("capture", ".json"), ("capture", ".transport.log"),
                ("cab", ".png"), ("partial", ".json")))
            screenshots.append(inner.WORKSPACE.parent / "root" / "bin" / "pc" /
                               f"d11_cab_{run_id}{variant[:2]}_{view}.png")
    collisions = [outer, outer.with_suffix(".json.tmp"), *runs.values(),
                  *screenshots, inner.LOCK]
    need(not any(path.exists() or path.is_symlink() for path in collisions),
         "Baseline run ID or lock already has an output")
    need(not (inner.NATIVE / "candidate_capture.lock.json").exists(),
         "Candidate capture is locked")
    return {
        "schemaVersion": 1, "role": "baseline", "runId": run_id,
        "runner": str(Path(__file__).resolve()),
        "runnerSha256": inner.sha(Path(__file__)),
        "innerRunner": str(Path(inner.__file__).resolve()),
        "innerRunnerSha256": SDK_RUNNER_SHA256,
        "acceptedProject": str(project), "acceptedPackage": str(package),
        "installedPackage": str(inner.LIVE), "acceptedSha256": accepted_sha,
        "sourcePinsSha256": inner.canonical_sha256(pins),
        "sourcePinCount": len(pins),
        "partialLinkerSource": str(inner.TOOLCHAIN_SRC),
        "partialLinkerSourcePins": inner.partial_linker_source_pins(),
        "helperSourcePins": inner.helper_source_pins(),
        "variantContexts": contexts,
        "capturePlan": {"variants": list(variants),
                        "viewsPerVariant": list(views),
                        "fullCapture": (variants == tuple(inner.SCENES) and
                                        views == inner.VIEWS)},
        "outerReceipt": str(outer), "variantRuns": {k: str(v) for k, v in runs.items()},
        "expectedOutputFiles": [str(p) for p in required],
        "screenshotSourceFiles": [str(p) for p in screenshots],
        "packageSwap": False,
    }


def _prepare(run_id: str, requested_variants: tuple[str, ...] | None = None,
             requested_views: tuple[str, ...] | None = None):
    toolchain = Path(__file__).resolve().parents[2]
    registry = core.read_registry(toolchain / "project.json")
    accepted = registry["accepted"]
    project = Path(accepted["sourceRoot"]).resolve(strict=True)
    package = Path(accepted["package"]["path"]).resolve(strict=True)
    accepted_sha = accepted["package"]["sha256"]
    _source_is_accepted(registry, project)
    need(core.file_identity(package, accepted_sha).get("matchesExpected") is True,
         "Accepted package source differs from registry pin")
    inner = _load_inner(toolchain, project, accepted_sha)
    need(inner.sha(inner.LIVE) == accepted_sha,
         "Installed package differs from accepted baseline")
    need(not inner.NATIVE.is_symlink() and not inner.RUNS.is_symlink(),
         "Native evidence path is linked")
    need(shutil.disk_usage(inner.HERE).free >= 4_000_000_000,
         "Less than 4 GB free for native capture")
    base, survey = inner.old_helpers()
    need(not base.runner.LOCK.exists() and not base.processes(),
         "Another native job, RoadCraft or Mod Editor is running")
    pins = inner.project_pins(project)
    need(requested_variants is None or
         len(requested_variants) == len(set(requested_variants)),
         "Baseline variants must not repeat")
    need(requested_views is None or
         len(requested_views) == len(set(requested_views)),
         "Baseline views must not repeat")
    variants = tuple(name for name in inner.SCENES
                     if requested_variants is None or name in requested_variants)
    views = tuple(name for name in inner.VIEWS
                  if requested_views is None or name in requested_views)
    need(variants and views and
         (requested_variants is None or set(variants) == set(requested_variants)) and
         (requested_views is None or set(views) == set(requested_views)),
         "Unknown or empty baseline variant/view selection")
    for variant in variants:
        inner.compiled_node_info(variant)
    mount = _mount(project, inner.sha)
    contract = _contract(inner, run_id, project, package, accepted_sha,
                         pins, variants, views, survey.VIEWS)
    return inner, base, survey, project, accepted_sha, pins, mount, contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--variants", nargs="+", choices=("maroon", "nearnew", "worn"))
    parser.add_argument("--views", nargs="+", choices=(
        "front_seat", "front_down", "right", "right_down", "right_panel_detail",
        "right_outer_low", "left", "left_down", "left_panel_detail", "rear",
        "rear_down", "rear_right_detail", "rear_left_detail", "overhead",
        "overhead_rear"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    args = parser.parse_args(argv)
    need(RUN_ID.fullmatch(args.run_id) is not None,
         "--run-id must be eight lowercase hexadecimal characters")
    need(args.execute == (args.expected_contract_sha256 is not None),
         "--execute requires a reviewed --expected-contract-sha256")
    inner, base, survey, project, accepted_sha, pins, mount, contract = _prepare(
        args.run_id, tuple(args.variants) if args.variants else None,
        tuple(args.views) if args.views else None)
    contract_sha = inner.canonical_sha256(contract)
    if not args.execute:
        print(json.dumps({"status": "BASELINE_OUTPUTS_DECLARED_NO_SWAP",
                          "outputContract": contract,
                          "outputContractSha256": contract_sha,
                          "editorMount": mount}, indent=2))
        return 0
    need(args.expected_contract_sha256 == contract_sha,
         "Baseline output contract changed since review")
    inner.load_partial_linker(contract["partialLinkerSourcePins"])
    inner.NATIVE.mkdir(parents=True, exist_ok=True)
    inner.RUNS.mkdir(parents=True, exist_ok=True)
    lock = inner.LOCK
    outer = Path(contract["outerReceipt"])
    report = {"status": "STARTING", "role": "baseline", "runId": args.run_id,
              "startedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "acceptedProject": str(project), "acceptedSha256": accepted_sha,
              "installedPackage": str(inner.LIVE), "editorMount": mount,
              "sourcePins": pins, "outputContractSha256": contract_sha,
              "variants": []}
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"runId": args.run_id, "role": "baseline",
                   "acceptedSha256": accepted_sha}, stream)
    owned = False
    try:
        with outer.open("x", encoding="utf-8"):
            owned = True
        variants = tuple(contract["capturePlan"]["variants"])
        views = tuple(contract["capturePlan"]["viewsPerVariant"])
        full_capture = contract["capturePlan"]["fullCapture"]
        for variant in variants:
            need(not base.processes(), "An editor remained active after the previous variant")
            report["variants"].append(inner.capture_variant(
                base, survey, variant, args.run_id + variant[:2], accepted_sha,
                pins, views, full_capture, contract["variantContexts"][variant],
                contract_sha, contract["partialLinkerSourcePins"],
                contract["helperSourcePins"]))
        need(inner.project_pins(project) == pins,
             "Accepted project changed during baseline capture")
        need(inner.sha(inner.LIVE) == accepted_sha,
             "Installed package changed during baseline capture")
        report["requiredOutputSha256"] = inner.required_output_digests(contract)
        report["status"] = ("BASELINE_CAPTURES_READY_NO_SWAP" if full_capture
                            else "BASELINE_TRIAGE_CAPTURES_READY_NO_SWAP")
    except BaseException as error:
        report.update(status="FAIL", error=repr(error))
        raise
    finally:
        report["finishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        if owned:
            inner.save(outer, report)
        if not base.processes() and inner.sha(inner.LIVE) == accepted_sha:
            lock.unlink()
    print(json.dumps({"status": report["status"], "receipt": str(outer),
                      "receiptSha256": inner.sha(outer)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
