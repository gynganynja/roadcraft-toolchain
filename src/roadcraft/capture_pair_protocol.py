"""Read-only matched-pair gate for future native D11 capture evidence.

This format requires a pinned editor observation immediately before every
screenshot. Historical native receipts lack those observations and cannot be
upgraded by assigning policy-level context labels after the fact.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from . import native_capture_postflight, review


HEX = re.compile(r"^[0-9a-f]{64}$")
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = review.MAX_IMAGE_BYTES


class CapturePairError(ValueError):
    """A pin, capture-time observation, or pair identity is invalid."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise CapturePairError(message)


def _object(value: Any, label: str) -> dict[str, Any]:
    _need(isinstance(value, dict), f"{label} must be an object")
    return value


def _digest(value: Any, label: str) -> str:
    _need(isinstance(value, str) and HEX.fullmatch(value) is not None,
          f"{label} needs a lowercase SHA-256 digest")
    return value


def _safe_id(value: Any, label: str) -> str:
    _need(isinstance(value, str) and SAFE.fullmatch(value) is not None,
          f"{label} needs a safe nonempty ID")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapturePairError(f"Value is not canonical JSON: {exc}") from exc


def _file(pin: Any, base: Path, label: str, *, limit: int | None = None) -> tuple[Path, bytes]:
    row = _object(pin, label)
    _need(set(row) == {"path", "sha256"}, f"{label} needs only path and sha256")
    text = row["path"]
    _need(isinstance(text, str) and text and "://" not in text,
          f"{label} needs a local path")
    candidate = Path(text).expanduser()
    unresolved = candidate if candidate.is_absolute() else base / candidate
    _need(not unresolved.is_symlink(), f"{label} must not be linked")
    path = unresolved.resolve()
    _need(path.is_file() and not path.is_symlink(), f"{label} is missing or linked")
    expected = _digest(row["sha256"], f"{label} SHA-256")
    before = path.stat()
    if limit is not None:
        _need(before.st_size <= limit, f"{label} exceeds size limit")
    if limit is None:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        raw = b""
        observed_sha = digest.hexdigest()
    else:
        raw = path.read_bytes()
        observed_sha = sha256(raw).hexdigest()
    after = path.stat()
    _need((before.st_size, before.st_mtime_ns, before.st_ino) ==
          (after.st_size, after.st_mtime_ns, after.st_ino),
          f"{label} changed while reading")
    _need(observed_sha == expected, f"{label} SHA-256 mismatch")
    return path, raw


def _json(pin: Any, base: Path, label: str) -> tuple[Path, dict[str, Any]]:
    path, raw = _file(pin, base, label, limit=MAX_JSON_BYTES)
    try:
        value = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON value: {value}")))
    except (UnicodeError, ValueError) as exc:
        raise CapturePairError(f"{label} is invalid JSON: {exc}") from exc
    return path, _object(value, label)


def _time(value: Any, label: str) -> datetime:
    _need(isinstance(value, str) and value, f"{label} needs an ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapturePairError(f"{label} is invalid: {exc}") from exc
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          f"{label} must be UTC")
    return parsed.astimezone(timezone.utc)


def _resolution(value: Any, label: str) -> list[int]:
    _need(isinstance(value, list) and len(value) == 2 and
          all(type(item) is int and item > 0 for item in value),
          f"{label} needs [positive width, positive height]")
    return value


def _vector(value: Any, label: str) -> list[int | float]:
    _need(isinstance(value, list) and len(value) == 3 and
          all(type(item) in (int, float) and math.isfinite(item) for item in value),
          f"{label} needs three finite coordinates")
    return value


def _camera(value: Any, label: str) -> dict[str, Any]:
    row = _object(value, label)
    _need(set(row) == {"basis", "spec", "position", "forward", "up"},
          f"{label} needs basis, spec, position, forward, up")
    _safe_id(row["basis"], f"{label}.basis")
    _need(isinstance(row["spec"], list) and len(row["spec"]) == 2,
          f"{label}.spec needs two offset vectors")
    for index, spec in enumerate(row["spec"]):
        _vector(spec, f"{label}.spec[{index}]")
    for field in ("position", "forward", "up"):
        _vector(row[field], f"{label}.{field}")
    _need(any(row["forward"]) and any(row["up"]),
          f"{label} direction vectors cannot be zero")
    return row


def _lighting(value: Any, label: str) -> dict[str, Any]:
    row = _object(value, label)
    _need({"environment", "localLights", "exposure", "tonemap", "rendererMode"}
          <= set(row), f"{label} lacks measured lighting controls")
    environment = _object(row["environment"], f"{label}.environment")
    _need({"weather", "timeOfDay", "sunDirection", "ambientRgb"}
          <= set(environment), f"{label}.environment is incomplete")
    _safe_id(environment["weather"], f"{label}.weather")
    hour = environment["timeOfDay"]
    _need(type(hour) in (int, float) and math.isfinite(hour) and 0 <= hour <= 24,
          f"{label}.timeOfDay must be a finite hour")
    _vector(environment["sunDirection"], f"{label}.sunDirection")
    _vector(environment["ambientRgb"], f"{label}.ambientRgb")
    exposure = row["exposure"]
    _need(type(exposure) in (int, float) and math.isfinite(exposure) and exposure > 0,
          f"{label}.exposure must be positive")
    _safe_id(row["tonemap"], f"{label}.tonemap")
    _safe_id(row["rendererMode"], f"{label}.rendererMode")
    lights = row["localLights"]
    _need(isinstance(lights, list), f"{label}.localLights must be an array")
    seen = set()
    for light in lights:
        light = _object(light, f"{label}.localLights item")
        _need({"id", "enabled", "intensity"} <= set(light),
              f"{label}.localLights item is incomplete")
        light_id = _safe_id(light["id"], f"{label}.localLights ID")
        _need(light_id not in seen, f"{label}.localLights has duplicate IDs")
        seen.add(light_id)
        intensity = light["intensity"]
        _need(type(light["enabled"]) is bool and type(intensity) in (int, float) and
              math.isfinite(intensity) and intensity >= 0,
              f"{label}.localLights item has invalid state")
    return row


def _unique_names(value: Any, label: str) -> list[str]:
    _need(isinstance(value, list) and bool(value), f"{label} needs a nonempty array")
    result = [_safe_id(item, label) for item in value]
    _need(len(set(result)) == len(result), f"{label} has duplicate IDs")
    return result


def _unique_capture_file(path: Path, label: str,
                         seen_paths: dict[Path, str],
                         seen_files: dict[tuple[int, int], str]) -> None:
    """Require one actual output file per capture; equal image bytes are fine.

    A second name for the same hard-linked file is still reuse of an output.
    Some filesystems report inode zero, so the resolved-path check remains the
    minimum rule on those filesystems.
    """
    _need(path not in seen_paths,
          f"{label} reuses the capture output from {seen_paths.get(path)}")
    identity = (path.stat().st_dev, path.stat().st_ino)
    if identity[1]:
        _need(identity not in seen_files,
              f"{label} reuses the capture output from {seen_files.get(identity)}")
        seen_files[identity] = label
    seen_paths[path] = label


def _candidate_native_receipt_links(
        pair: dict[str, Any], pair_file: Path,
        expected_pins: Mapping[str, str],
        run_refs: dict[str, tuple[Path, dict[str, Any]]],
        protocol_runner_path: Path, protocol_runner_sha: str) -> None:
    """Bind candidate context to an externally pinned native capture receipt.

    The existing postflight handles a candidate with baseline restoration. It
    cannot verify a baseline run. Even a passing candidate link does not prove
    that the engine consumed the scene or produced the PNG bytes.
    """
    _need(set(expected_pins) == {"receiptSha256", "planSha256"},
          "External candidate native pins need receiptSha256 and planSha256")
    role = "candidate"
    _, run = run_refs[role]
    _need([row["variant"] for row in run["variants"]] ==
          list(native_capture_postflight.VARIANTS) and
          all([capture["view"] for capture in row["captures"]] ==
              list(native_capture_postflight.VIEWS) for row in run["variants"]),
          "Candidate native binding needs the exact 45-view D11 roster")
    native_rows = {role: _object(pair.get("candidateNativeReceipt"),
                                 "candidateNativeReceipt")}
    for role in ("candidate",):
        external = expected_pins
        _need(set(external) == {"receiptSha256", "planSha256"},
              f"External {role} native pins need receiptSha256 and planSha256")
        receipt_sha = _digest(external["receiptSha256"], f"External {role} receipt")
        plan_sha = _digest(external["planSha256"], f"External {role} plan")
        binding = _object(native_rows[role], f"{role} native receipt binding")
        _need(set(binding) == {"receipt", "plan", "candidatePackage",
                               "installedPackage", "baselineSha256"},
              f"{role} native receipt binding has an incomplete or extra field")
        receipt_path, outer = _json(binding["receipt"], pair_file.parent,
                                    f"{role} native outer receipt")
        plan_path, plan = _json(binding["plan"], pair_file.parent,
                                f"{role} native capture plan")
        _need(binding["receipt"]["sha256"] == receipt_sha and
              binding["plan"]["sha256"] == plan_sha,
              f"{role} native receipt or plan differs from external pin")
        candidate_path, _ = _file(binding["candidatePackage"], pair_file.parent,
                                   f"{role} native candidate package")
        installed_path, _ = _file(binding["installedPackage"], pair_file.parent,
                                   f"{role} native installed package")
        baseline_sha = _digest(binding["baselineSha256"],
                               f"{role} accepted baseline SHA-256")
        run_path, run = run_refs[role]
        _need(run["package"] == binding["candidatePackage"],
              f"{role} pair package differs from native candidate package")
        _need(binding["installedPackage"]["sha256"] == baseline_sha,
              f"{role} installed package differs from accepted baseline")
        run_id = run["runId"]
        _need(re.fullmatch(r"[0-9a-f]{8}", run_id) is not None,
              f"{role} native run ID needs eight lowercase hexadecimal characters")
        postflight = native_capture_postflight.validate(
            receipt_path, run_id=run_id,
            candidate_package=candidate_path,
            candidate_sha256=binding["candidatePackage"]["sha256"],
            installed_package=installed_path,
            baseline_sha256=baseline_sha,
            installed_sha256=binding["installedPackage"]["sha256"],
            capture_plan=plan_path, capture_plan_sha256=plan_sha,
            expected_capture_receipt_sha256=receipt_sha)
        _need(postflight.get("captureIntegrityPassed") is True and
              postflight.get("checkedViews") == 45 and
              postflight.get("checkedPartialViews") == 45 and
              postflight.get("checkedReadRequests") == 45 and
              postflight.get("receiptSha256") == receipt_sha and
              postflight.get("runId") == run_id,
              f"{role} native postflight did not verify the full run")
        output_hashes = _object(outer.get("requiredOutputSha256"),
                                f"{role} native output hashes")
        contract = _object(plan.get("outputContract"),
                           f"{role} native output contract")
        _need(contract.get("runner") == str(protocol_runner_path) and
              contract.get("runnerSha256") == protocol_runner_sha,
              "Candidate protocol runner differs from native contract")
        contexts = _object(contract.get("variantContexts"),
                           f"{role} native variant contexts")
        for variant_row in run["variants"]:
            variant = variant_row["variant"]
            native_run = receipt_path.parent / "runs" / (
                f"aaa_{variant}_{run_id}{variant[:2]}")
            context = _object(contexts.get(variant), f"{role} {variant} native context")
            _need(variant_row["scene"] ==
                  {"path": context.get("scene"), "sha256": context.get("sceneSha256")},
                  f"{role} {variant} scene differs from native contract")
            report_path = native_run / "report.json"
            report_pin = output_hashes.get(str(report_path))
            _need(report_pin is not None, f"{role} {variant} native report is absent")
            _, report = _json({"path": str(report_path), "sha256": report_pin},
                              run_path.parent, f"{role} {variant} native report")
            _need(report.get("enginePid") == variant_row["enginePid"],
                  f"{role} {variant} engine PID differs from native report")
            actions = report.get("actionEvents")
            _need(isinstance(actions, list) and len(actions) == 91,
                  f"{role} {variant} native action transcript is incomplete")
            for index, capture in enumerate(variant_row["captures"]):
                view = capture["view"]
                label = f"{role} {variant} {view}"
                image_path = native_run / f"cab_{view}.png"
                transport_path = native_run / f"pre_capture_{view}.json"
                _need(capture["image"] ==
                      {"path": str(image_path),
                       "sha256": output_hashes.get(str(image_path))},
                      f"{label} image differs from native output")
                _, observed = _json(capture["observation"], run_path.parent,
                                     f"{label} observation")
                _need(observed.get("nativeTransport") ==
                      {"path": str(transport_path),
                       "sha256": output_hashes.get(str(transport_path))},
                      f"{label} observation lacks the exact native transport link")
                _, transport = _json(observed["nativeTransport"], run_path.parent,
                                      f"{label} native transport")
                _need(transport.get("status") == "pass" and
                      transport.get("stage") == "response_received" and
                      transport.get("mode") == "Read" and
                      transport.get("readOnly") is True and
                      transport.get("engineProcessId") == variant_row["enginePid"] and
                      transport.get("script") == observed.get("requestScript") and
                      transport.get("response") == observed.get("responseRaw") and
                      transport.get("requestSentUtc") == observed.get("requestSentUtc") and
                      transport.get("receivedUtc") == observed.get("responseReceivedUtc"),
                      f"{label} observation differs from native transport")
                action_slice = actions[1 + index * 6:1 + (index + 1) * 6]
                _need(len(action_slice) == 6 and
                      action_slice[3].get("action") == "ReadPreCapture" and
                      action_slice[4].get("action") == "CaptureCab" +
                      view.title().replace("_", "") and
                      action_slice[5].get("action") == "SaveScreenshot:" + view and
                      _time(action_slice[3]["startedUtc"], f"{label} read start") <=
                      _time(observed["requestSentUtc"], f"{label} request") <=
                      _time(observed["responseReceivedUtc"], f"{label} response") <=
                      _time(action_slice[3]["finishedUtc"], f"{label} read finish") and
                      _time(action_slice[4]["startedUtc"], f"{label} capture start") <=
                      _time(capture["triggeredUtc"], f"{label} trigger") <=
                      _time(action_slice[4]["finishedUtc"], f"{label} capture finish") and
                      _time(action_slice[5]["startedUtc"], f"{label} copy start") <=
                      _time(capture["copiedUtc"], f"{label} copy") <=
                      _time(action_slice[5]["finishedUtc"], f"{label} copy finish"),
                      f"{label} pair timing differs from native actions")


def validate(pair_path: str | Path, *,
             expected_candidate_native_pins: Mapping[str, str] | None = None
             ) -> dict[str, Any]:
    """Verify a sealed baseline/candidate pair without writing or launching tools."""
    unresolved_pair = Path(pair_path).expanduser()
    _need(not unresolved_pair.is_symlink(), "Pair manifest must not be linked")
    pair_file = unresolved_pair.resolve(strict=True)
    _need(pair_file.stat().st_size <= MAX_JSON_BYTES,
          "Pair manifest exceeds size limit")
    try:
        pair = json.loads(pair_file.read_bytes(), parse_constant=lambda value: (
            _ for _ in ()).throw(ValueError(f"Non-finite JSON value: {value}")))
    except (UnicodeError, ValueError) as exc:
        raise CapturePairError(f"Pair manifest is invalid JSON: {exc}") from exc
    _object(pair, "pair manifest")
    _need(pair.get("schemaVersion") == 1, "Unsupported pair schemaVersion")
    protocol_path, protocol = _json(pair.get("protocol"), pair_file.parent, "protocol")
    _need(protocol.get("schemaVersion") == 1, "Unsupported protocol schemaVersion")
    protocol_id = _safe_id(protocol.get("id"), "protocol.id")
    protocol_sha = pair["protocol"]["sha256"]
    runner_path, _ = _file(protocol.get("runner"), protocol_path.parent, "protocol runner")
    runner_sha = protocol["runner"]["sha256"]
    probe_path, probe_raw = _file(protocol.get("probeScript"), protocol_path.parent,
                                   "protocol probe script", limit=MAX_JSON_BYTES)
    probe_sha = protocol["probeScript"]["sha256"]
    try:
        probe_script = probe_raw.decode("utf-8")
    except UnicodeError as exc:
        raise CapturePairError("protocol probe script must be UTF-8") from exc
    _need(bool(probe_script), "protocol probe script cannot be empty")
    variants = _unique_names(protocol.get("variants"), "protocol.variants")
    view_rows = protocol.get("views")
    _need(isinstance(view_rows, list) and bool(view_rows),
          "protocol.views needs a nonempty array")
    views: dict[str, dict[str, Any]] = {}
    for row in view_rows:
        row = _object(row, "protocol view")
        name = _safe_id(row.get("view"), "protocol view")
        _need(name not in views, "Duplicate protocol view")
        camera = _object(row.get("camera"), f"protocol camera {name}")
        _need(set(camera) == {"basis", "spec"},
              f"protocol camera {name} needs basis and spec")
        _safe_id(camera["basis"], f"protocol camera {name}.basis")
        _need(isinstance(camera["spec"], list) and len(camera["spec"]) == 2,
              f"protocol camera {name}.spec needs two offsets")
        for index, spec in enumerate(camera["spec"]):
            _vector(spec, f"protocol camera {name}.spec[{index}]")
        views[name] = camera
    resolution = _resolution(protocol.get("resolution"), "protocol.resolution")
    lighting_state = _lighting(protocol.get("lightingState"), "protocol.lightingState")
    lighting_sha = sha256(_canonical(lighting_state)).hexdigest()
    max_age = protocol.get("maxObservationAgeSeconds")
    _need(type(max_age) is int and 1 <= max_age <= 60,
          "maxObservationAgeSeconds must be 1..60")
    runs = _object(pair.get("runs"), "runs")
    _need(set(runs) == {"baseline", "candidate"},
          "runs needs exactly baseline and candidate")
    run_results: dict[str, dict[str, Any]] = {}
    pair_camera: dict[tuple[str, str], bytes] = {}
    pair_scene: dict[str, str] = {}
    pair_lighting: dict[tuple[str, str], bytes] = {}
    seen_capture_paths: dict[Path, str] = {}
    seen_capture_files: dict[tuple[int, int], str] = {}
    seen_run_ids: set[str] = set()
    run_refs: dict[str, tuple[Path, dict[str, Any]]] = {}
    for role in ("baseline", "candidate"):
        run_path, run = _json(runs[role], pair_file.parent, f"{role} run")
        _need(run.get("schemaVersion") == 1 and run.get("status") == "CAPTURE_READY",
              f"{role} run is not capture-ready schema 1")
        _need(run.get("role") == role, f"{role} run role mismatch")
        run_id = _safe_id(run.get("runId"), f"{role}.runId")
        _need(run_id not in seen_run_ids, "Baseline and candidate run IDs must differ")
        seen_run_ids.add(run_id)
        _need(run.get("protocolSha256") == protocol_sha and
              run.get("runnerSha256") == runner_sha,
              f"{role} run protocol or runner mismatch")
        package_path, _ = _file(run.get("package"), run_path.parent, f"{role} package")
        began = _time(run.get("startedUtc"), f"{role}.startedUtc")
        ended = _time(run.get("finishedUtc"), f"{role}.finishedUtc")
        _need(began < ended, f"{role} run timestamps are reversed")
        variant_rows = run.get("variants")
        _need(isinstance(variant_rows, list) and
              [row.get("variant") if isinstance(row, dict) else None for row in variant_rows]
              == variants, f"{role} run variant roster differs from protocol")
        checked = 0
        previous_copy: datetime | None = None
        for variant_row in variant_rows:
            variant = variant_row["variant"]
            scene_path, _ = _file(variant_row.get("scene"), run_path.parent,
                                  f"{role} {variant} scene")
            scene_sha = variant_row["scene"]["sha256"]
            if role == "baseline":
                pair_scene[variant] = scene_sha
            else:
                _need(pair_scene[variant] == scene_sha,
                      f"{variant} scene bytes differ between runs")
            pid = variant_row.get("enginePid")
            _need(type(pid) is int and pid > 0, f"{role} {variant} needs enginePid")
            captures = variant_row.get("captures")
            _need(isinstance(captures, list) and
                  [row.get("view") if isinstance(row, dict) else None for row in captures]
                  == list(views), f"{role} {variant} view roster differs from protocol")
            for capture in captures:
                view = capture["view"]
                label = f"{role} {variant} {view}"
                image_path, image_raw = _file(capture.get("image"), run_path.parent,
                                               f"{label} image", limit=MAX_IMAGE_BYTES)
                _unique_capture_file(image_path, f"{label} image",
                                     seen_capture_paths, seen_capture_files)
                try:
                    _, image_resolution = review._image_info(image_raw)
                except review.ReviewError as exc:
                    raise CapturePairError(f"{label} image is invalid: {exc}") from exc
                _need(image_resolution == resolution, f"{label} image resolution mismatch")
                observed_path, observed = _json(capture.get("observation"), run_path.parent,
                                                 f"{label} observation")
                _unique_capture_file(observed_path, f"{label} observation",
                                     seen_capture_paths, seen_capture_files)
                _need(observed.get("requestScript") == probe_script,
                      f"{label} editor request differs from the pinned probe script")
                response_raw = observed.get("responseRaw")
                _need(isinstance(response_raw, str) and bool(response_raw),
                      f"{label} needs the raw editor response")
                try:
                    response = json.loads(response_raw, parse_constant=lambda value: (
                        _ for _ in ()).throw(ValueError(f"Non-finite JSON value: {value}")))
                except ValueError as exc:
                    raise CapturePairError(f"{label} raw editor response is invalid JSON: {exc}") from exc
                response = _object(response, f"{label} editor response")
                _need(observed.get("schemaVersion") == 1 and
                      observed.get("source") == "native-editor-response" and
                      observed.get("probeScriptSha256") == probe_sha and
                      response.get("status") == "OBSERVED" and
                      response.get("runId") == run_id and
                      response.get("role") == role and
                      response.get("variant") == variant and
                      response.get("view") == view and
                      response.get("enginePid") == pid and
                      response.get("protocolSha256") == protocol_sha and
                      response.get("loadedSceneSha256") == scene_sha,
                      f"{label} observation provenance mismatch")
                sent = _time(observed.get("requestSentUtc"), f"{label} observation request")
                received = _time(observed.get("responseReceivedUtc"), f"{label} observation response")
                triggered = _time(capture.get("triggeredUtc"), f"{label} trigger")
                copied = _time(capture.get("copiedUtc"), f"{label} copy")
                _need(began <= sent <= received <= triggered <= copied <= ended and
                      (triggered - received).total_seconds() <= max_age,
                      f"{label} observation was not captured immediately before the image")
                _need(previous_copy is None or previous_copy <= sent,
                      f"{label} observation overlaps an earlier capture")
                previous_copy = copied
                _need(_resolution(response.get("resolution"), f"{label} observed resolution")
                      == resolution, f"{label} observed resolution mismatch")
                camera = _camera(response.get("camera"), f"{label} observed camera")
                _need({key: camera[key] for key in ("basis", "spec")} == views[view],
                      f"{label} observed camera differs from protocol")
                camera_bytes = _canonical(camera)
                if role == "baseline":
                    pair_camera[(variant, view)] = camera_bytes
                else:
                    _need(pair_camera[(variant, view)] == camera_bytes,
                          f"{label} observed camera differs from baseline")
                observed_lighting = _lighting(response.get("lightingState"),
                                              f"{label} observed lighting")
                _need(sha256(_canonical(observed_lighting)).hexdigest() == lighting_sha,
                      f"{label} observed lighting differs from protocol")
                lighting_bytes = _canonical(observed_lighting)
                if role == "baseline":
                    pair_lighting[(variant, view)] = lighting_bytes
                else:
                    _need(pair_lighting[(variant, view)] == lighting_bytes,
                          f"{label} observed lighting differs from baseline")
                checked += 1
        run_results[role] = {"receiptPath": str(run_path),
                             "receiptSha256": runs[role]["sha256"],
                             "packagePath": str(package_path),
                             "packageSha256": run["package"]["sha256"],
                             "runId": run_id, "checkedViews": checked}
        run_refs[role] = (run_path, run)
    if expected_candidate_native_pins is not None:
        _candidate_native_receipt_links(
            pair, pair_file, expected_candidate_native_pins, run_refs,
            runner_path, runner_sha)
    full_d11_roster = (variants == list(native_capture_postflight.VARIANTS) and
                       list(views) == list(native_capture_postflight.VIEWS))
    return {"schemaVersion": 1, "kind": "roadcraft.capture-pair",
            "scope": "pinned comparison context only",
            "contextComparable": True,
            "d11RosterComplete": full_d11_roster,
            "pairComparable": full_d11_roster,
            "nativePostflightVerified": False,
            "candidateNativePostflightVerified": expected_candidate_native_pins is not None,
            "candidateNativeReceiptLinked": expected_candidate_native_pins is not None,
            "nativeEvidenceLinked": False,
            "captureProcessAuthenticated": False,
            "technicalPassed": False,
            "releaseReady": False,
            "protocolId": protocol_id,
            "protocolPath": str(protocol_path), "protocolSha256": protocol_sha,
            "runnerPath": str(runner_path), "runnerSha256": runner_sha,
            "probeScriptPath": str(probe_path), "probeScriptSha256": probe_sha,
            "lightingStateSha256": lighting_sha,
            "matchedViews": len(variants) * len(views), "runs": run_results,
            "visualReviewed": False, "campaignAccepted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path, help="Pair manifest with pinned protocol and run receipts")
    parser.add_argument("--candidate-native-receipt-sha256")
    parser.add_argument("--candidate-native-plan-sha256")
    args = parser.parse_args(argv)
    native_args = (args.candidate_native_receipt_sha256,
                   args.candidate_native_plan_sha256)
    if any(value is not None for value in native_args) and not all(
            value is not None for value in native_args):
        parser.error("Both external candidate receipt and plan SHA-256 pins are required")
    expected_candidate_native_pins = None
    if all(value is not None for value in native_args):
        expected_candidate_native_pins = {
            "receiptSha256": args.candidate_native_receipt_sha256,
            "planSha256": args.candidate_native_plan_sha256}
    try:
        result = validate(args.pair,
                          expected_candidate_native_pins=expected_candidate_native_pins)
    except (CapturePairError, OSError) as exc:
        parser.exit(2, f"capture-pair: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
