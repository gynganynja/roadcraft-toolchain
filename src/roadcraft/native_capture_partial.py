"""Fail-closed partial per-view linkage for a future D11 native capture runner.

This module never launches the editor or grants matched-pair eligibility. It
binds a transport declaring ``readOnly`` to the following CaptureCab action,
copied PNG, and self-declared action windows. A loaded scene, complete renderer
state, exact screenshot trigger instant, and native process origin remain
unverified.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from . import native_capture_observation, native_capture_postflight, review


HEX_RUN = re.compile(r"[0-9a-f]{8}\Z")
REQUEST_ID = re.compile(r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9a-f]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}\Z")
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_RAW_REPLY_BYTES = 65_536
MAX_PRE_TRIGGER_GAP_SECONDS = 10
EVENTS = (
    "setCamera", "settleCamera", "sourceGuard", "preScreenshotRead",
    "captureTrigger", "copyScreenshot",
)


class PartialViewError(ValueError):
    """A proposed pre-screenshot link is missing or internally inconsistent."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise PartialViewError(message)


def _utc(value: Any, label: str) -> datetime:
    _need(isinstance(value, str) and bool(value), f"{label} needs a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PartialViewError(f"{label} is not an ISO timestamp") from error
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          f"{label} must be UTC")
    return parsed.astimezone(timezone.utc)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _read(path: Path, label: str, limit: int) -> tuple[bytes, str]:
    _need(path.is_absolute() and not path.is_symlink(), f"{label} must be an absolute plain file")
    _need(path.is_file(), f"{label} is missing")
    before = path.stat()
    _need(before.st_size <= limit, f"{label} exceeds size limit")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, f"{label} grew beyond size limit while reading")
    after = path.stat()
    _need(len(raw) == before.st_size, f"{label} length changed while reading")
    _need((before.st_size, before.st_mtime_ns, before.st_ino) ==
          (after.st_size, after.st_mtime_ns, after.st_ino),
          f"{label} changed while reading")
    return raw, sha256(raw).hexdigest()


def _transport(path: Path, label: str, mode: str, read_only: bool,
               pid: int, helper_sha: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw, digest = _read(path, label, MAX_JSON_BYTES)
    try:
        row = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON: {value}")))
    except (UnicodeError, ValueError) as error:
        raise PartialViewError(f"{label} is invalid JSON") from error
    _need(isinstance(row, dict), f"{label} is not an object")
    _need(row.get("schema") == 1 and row.get("status") == "pass" and
          row.get("stage") == "response_received", f"{label} did not pass")
    _need(row.get("mode") == mode and row.get("readOnly") is read_only,
          f"{label} mode or read-only classification mismatch")
    _need(type(row.get("engineProcessId")) is int and row["engineProcessId"] == pid,
          f"{label} engine PID mismatch")
    _need(row.get("helperSha256") == helper_sha, f"{label} helper SHA-256 mismatch")
    _need(isinstance(row.get("workspace"), str) and bool(row["workspace"]),
          f"{label} native workspace missing")
    request_id = row.get("requestId")
    _need(isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id) is not None,
          f"{label} request ID malformed")
    script, response, encoded = row.get("script"), row.get("response"), row.get("responseBase64")
    _need(isinstance(script, str) and bool(script) and isinstance(response, str)
          and isinstance(encoded, str), f"{label} exact request or reply missing")
    _need(len(encoded) <= 4 * ((MAX_RAW_REPLY_BYTES + 2) // 3),
          f"{label} encoded response exceeds bound")
    try:
        reply_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise PartialViewError(f"{label} raw reply is malformed") from error
    _need(1 <= len(reply_bytes) <= MAX_RAW_REPLY_BYTES,
          f"{label} raw reply exceeds byte bound")
    _need(reply_bytes.endswith(b"\0") and reply_bytes.count(b"\0") == 1,
          f"{label} raw reply terminator is invalid")
    _need(type(row.get("responseBytes")) is int and row["responseBytes"] == len(reply_bytes),
          f"{label} raw reply length mismatch")
    try:
        decoded = reply_bytes[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PartialViewError(f"{label} raw reply is not UTF-8") from error
    _need(decoded == response, f"{label} decoded reply mismatch")
    sent = _utc(row.get("requestSentUtc"), f"{label} request")
    received = _utc(row.get("receivedUtc"), f"{label} response")
    _need(sent <= received, f"{label} response precedes request")
    try:
        observed = native_capture_observation.inspect_transport(row)
    except native_capture_observation.NativeObservationError as error:
        raise PartialViewError(f"{label} partial editor context failed: {error}") from error
    pin = {
        "path": str(path), "sha256": digest, "mode": mode,
        "readOnly": read_only, "requestId": request_id,
        "requestScriptSha256": sha256(script.encode("utf-8")).hexdigest(),
        "responseSha256": sha256(response.encode("utf-8")).hexdigest(),
        "rawResponseSha256": sha256(reply_bytes).hexdigest(),
        "requestSentUtc": row["requestSentUtc"], "responseReceivedUtc": row["receivedUtc"],
    }
    return pin, observed, row


def _windows(action_events: list[dict[str, Any]], view: str,
             pid: int) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[datetime, datetime]]]:
    mode = view.title().replace("_", "")
    labels = {
        "setCamera": "SetCab" + mode,
        "settleCamera": "SettleCamera",
        "sourceGuard": "ScreenshotSourceGuard",
        "preScreenshotRead": "ReadPreCapture",
        "captureTrigger": "CaptureCab" + mode,
        "copyScreenshot": "SaveScreenshot:" + view,
    }
    _need(isinstance(action_events, list) and len(action_events) == len(EVENTS),
          "Partial view needs exactly six ordered action events")
    windows: dict[str, dict[str, Any]] = {}
    parsed: dict[str, tuple[datetime, datetime]] = {}
    previous_end: datetime | None = None
    for key, event in zip(EVENTS, action_events, strict=True):
        _need(isinstance(event, dict) and event.get("action") == labels[key] and
              event.get("view") == view and event.get("status") == "PASS" and
              type(event.get("enginePid")) is int and event["enginePid"] == pid,
              f"{key} action identity or status mismatch")
        start = _utc(event.get("startedUtc"), f"{key}.startedUtc")
        end = _utc(event.get("finishedUtc"), f"{key}.finishedUtc")
        _need(start <= end and (previous_end is None or previous_end <= start),
              f"{key} action windows overlap or reverse")
        previous_end = end
        windows[key] = {field: event[field] for field in
                        ("action", "view", "enginePid", "status", "startedUtc", "finishedUtc")}
        parsed[key] = (start, end)
    return windows, parsed


def build_partial_view(*, run_id: str, variant: str, view: str, engine_pid: int,
                       scene: Path, helper: Path, camera_transport: Path,
                       pre_transport: Path, capture_transport: Path, image: Path,
                       action_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Construct a partial link from exact files and ordered runner events.

    The caller must write/pin this returned JSON during the native run. This
    function authenticates neither the caller nor a loaded scene.
    """
    _need(isinstance(run_id, str) and HEX_RUN.fullmatch(run_id) is not None,
          "run_id needs eight lowercase hex characters")
    _need(variant in native_capture_postflight.VARIANTS, "Unknown D11 variant")
    _need(view in native_capture_postflight.VIEWS, "Unknown D11 view")
    _need(type(engine_pid) is int and engine_pid > 0, "Engine PID must be positive")
    paths = (scene, helper, camera_transport, pre_transport, capture_transport, image)
    _need(all(isinstance(path, Path) for path in paths), "Inputs must be paths")
    run = helper.parent
    scene_name = f"d11t_{variant}_validation"
    _need(scene.name == f"{scene_name}.scn" and scene.parent.name == scene_name,
          "Scene source does not match variant")
    _need(run.name == f"aaa_{variant}_{run_id}{variant[:2]}",
          "Run directory identity does not match run ID and variant")
    _need(helper.name == "native_controls.ps1" and all(path.parent == run for path in
          (camera_transport, pre_transport, capture_transport, image)),
          "Transport, helper, and image must share the exact run directory")
    _need(camera_transport.name == f"camera_{view}.json" and
          pre_transport.name == f"pre_capture_{view}.json" and
          capture_transport.name == f"capture_{view}.json" and
          image.name == f"cab_{view}.png", "Per-view filenames are not exact")
    scene_raw, scene_sha = _read(scene, "scene source", MAX_JSON_BYTES)
    _need(bool(scene_raw), "Scene source is empty")
    helper_raw, helper_sha = _read(helper, "native helper", MAX_JSON_BYTES)
    _need(bool(helper_raw), "Native helper is empty")
    windows, parsed = _windows(action_events, view, engine_pid)
    mode = view.title().replace("_", "")
    camera_pin, _camera_observed, camera_raw = _transport(
        camera_transport, "camera transport", "SetCab" + mode, False,
        engine_pid, helper_sha)
    pre_pin, pre_observed, pre_raw = _transport(
        pre_transport, "pre-screenshot transport", "Read", True,
        engine_pid, helper_sha)
    capture_pin, capture_observed, capture_raw = _transport(
        capture_transport, "capture transport", "CaptureCab" + mode, False,
        engine_pid, helper_sha)
    _need(len({pin["requestId"] for pin in (camera_pin, pre_pin, capture_pin)}) == 3,
          "Transport request IDs are not distinct")
    _need(len({row["workspace"] for row in (camera_raw, pre_raw, capture_raw)}) == 1,
          "Transport native workspaces differ")
    expected_trigger = (f'SaveScreenshot(ScreenshotSaveTarget.FILE,"d11_cab_{run_id}{variant[:2]}_{view}",'
                        'false,ScreenshotFormat.PNG)')
    _need(expected_trigger in capture_raw["script"] and
          capture_raw["script"].count("SaveScreenshot(") == 1 and
          capture_raw["script"].find(expected_trigger) <
          capture_raw["script"].rfind("return result"),
          "CaptureCab request lacks the exact screenshot action")
    _need("SaveScreenshot(" not in pre_raw["script"] and
          "SaveScreenshot(" not in camera_raw["script"],
          "Camera or pre-screenshot query contains a screenshot action")
    for key, pin in (("setCamera", camera_pin), ("preScreenshotRead", pre_pin),
                     ("captureTrigger", capture_pin)):
        start, end = parsed[key]
        _need(start <= _utc(pin["requestSentUtc"], f"{key} request") <=
              _utc(pin["responseReceivedUtc"], f"{key} response") <= end,
              f"{key} transport falls outside its action window")
    pre_received = _utc(pre_pin["responseReceivedUtc"], "pre-screenshot response")
    capture_started = _utc(capture_pin["requestSentUtc"], "capture request")
    _need(0 <= (capture_started - pre_received).total_seconds()
          <= MAX_PRE_TRIGGER_GAP_SECONDS,
          "Pre-screenshot response is not immediately before CaptureCab")
    _need(pre_observed["reported"]["activePlayCameraResolution"] ==
          pre_observed["reported"]["videoConfigWindowSize"],
          "Pre-screenshot camera and video resolution differ")
    image_raw, image_sha = _read(image, "screenshot", review.MAX_IMAGE_BYTES)
    _need(image_raw.startswith(b"\x89PNG\r\n\x1a\n"), "Screenshot is not PNG")
    try:
        _, image_resolution = review._image_info(image_raw)
    except review.ReviewError as error:
        raise PartialViewError(f"Screenshot raster is invalid: {error}") from error
    _need(pre_observed["reported"]["activePlayCameraResolution"] == image_resolution,
          "Pre-screenshot camera resolution differs from PNG")
    _need(capture_observed["reported"]["activePlayCameraResolution"] == image_resolution,
          "Post-trigger camera resolution differs from PNG")
    return {
        "schemaVersion": 1, "kind": "roadcraft.native-partial-view-link",
        "status": "PARTIAL_PRE_SCREENSHOT_CONTEXT", "pairProtocolEligible": False,
        "loadedSceneVerified": False, "captureProcessAuthenticated": False,
        "nativePostflightVerified": False,
        "runId": run_id, "variant": variant, "view": view, "enginePid": engine_pid,
        "sceneSource": {"path": str(scene), "sha256": scene_sha},
        "helper": {"path": str(helper), "sha256": helper_sha},
        "transports": {"setCamera": camera_pin, "preScreenshotRead": pre_pin,
                       "captureTrigger": capture_pin},
        "actionWindows": windows,
        "declaredTriggerWindow": {
            "startedUtc": capture_pin["requestSentUtc"],
            "endedUtc": capture_pin["responseReceivedUtc"],
            "exactTriggerUtcKnown": False,
        },
        "screenshot": {"path": str(image), "sha256": image_sha,
                       "resolutionPixels": image_resolution},
        "preScreenshotReported": pre_observed["reported"],
        "postTriggerReported": capture_observed["reported"],
        "missingMatchedPairRuntimeFields":
            native_capture_observation.MISSING_MATCHED_PAIR_RUNTIME_FIELDS.copy(),
        "limitations": [
            "Action windows and transport replies are runner records, not independently authenticated editor-origin evidence.",
            "readOnly is a helper-declared transport marker; the exact SSL script must be independently reviewed and pinned.",
            "The scene hash covers on-disk source bytes, not a verified loaded scene.",
            "The CaptureCab script triggers the screenshot before its response; the exact trigger instant is not measured.",
            "Camera up, global renderer state, and the complete scene-light roster are absent.",
        ],
    }


def verify_partial_view(record: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a saved partial link from its pinned files and action windows."""
    _need(isinstance(record, dict) and record.get("schemaVersion") == 1 and
          record.get("kind") == "roadcraft.native-partial-view-link",
          "Unknown partial-view record")
    try:
        transports = record["transports"]
        rebuilt = build_partial_view(
            run_id=record["runId"], variant=record["variant"], view=record["view"],
            engine_pid=record["enginePid"], scene=Path(record["sceneSource"]["path"]),
            helper=Path(record["helper"]["path"]),
            camera_transport=Path(transports["setCamera"]["path"]),
            pre_transport=Path(transports["preScreenshotRead"]["path"]),
            capture_transport=Path(transports["captureTrigger"]["path"]),
            image=Path(record["screenshot"]["path"]),
            action_events=[record["actionWindows"][key] for key in EVENTS],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, PartialViewError):
            raise
        raise PartialViewError("Partial-view record is incomplete") from error
    _need(_canonical(record) == _canonical(rebuilt),
          "Partial-view record differs from pinned files or event windows")
    return {"status": "PARTIAL_VIEW_LINKAGE_CONSISTENT",
            "runId": record["runId"], "variant": record["variant"],
            "view": record["view"], "pairProtocolEligible": False,
            "captureProcessAuthenticated": False, "nativePostflightVerified": False}
