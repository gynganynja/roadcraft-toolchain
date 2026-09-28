"""Read-only diagnostics for fields already returned by the D11 editor helper.

This is deliberately not a ``capture_pair_protocol`` observation producer. The
current helper has no proven runtime readback for global lighting or camera up,
and its SetCab/CaptureCab replies do not bracket the screenshot trigger.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any


MAX_TRANSPORT_BYTES = 4 * 1024 * 1024
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
CAMERA = re.compile(
    rf"^cameraWorld pos ({NUMBER}) ({NUMBER}) ({NUMBER}) "
    rf"forward ({NUMBER}) ({NUMBER}) ({NUMBER})$", re.M)
SIZE = re.compile(r"^cameraResolution (\d+) (\d+)$", re.M)
WINDOW = re.compile(r"^previousResolution (\d+) (\d+)$", re.M)
LIGHT = re.compile(
    rf"^light (\S+) pos ({NUMBER}) ({NUMBER}) ({NUMBER}) "
    rf"tangent ({NUMBER}) ({NUMBER}) ({NUMBER}) intensity ({NUMBER}) "
    rf"radius ({NUMBER}) cone ({NUMBER})$", re.M)
LIGHT_STATE = re.compile(r"^spotStarted (\S+) (true|false)$", re.M)

MISSING_MATCHED_PAIR_RUNTIME_FIELDS = [
    "camera.up",
    "lightingState.environment.weather",
    "lightingState.environment.timeOfDay",
    "lightingState.environment.sunDirection",
    "lightingState.environment.ambientRgb",
    "lightingState.localLights.completeSceneRoster",
    "lightingState.exposure",
    "lightingState.tonemap",
    "lightingState.rendererMode",
]
MISSING_MATCHED_PAIR_CAPTURE_LINKAGE = [
    "runId", "role", "variant", "view", "protocolSha256",
    "loadedSceneSha256", "camera.basis", "camera.spec",
    "screenshot.triggeredUtc", "screenshot.copiedUtc",
    "screenshot.imageSha256", "screenshot.imageDimensions",
]


class NativeObservationError(ValueError):
    """The existing editor transport cannot be read unambiguously."""


def _one(pattern: re.Pattern[str], response: str, label: str) -> tuple[str, ...]:
    matches = pattern.findall(response)
    if len(matches) != 1:
        raise NativeObservationError(f"Expected exactly one {label}, found {len(matches)}")
    return matches[0]


def _floats(values: tuple[str, ...]) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise NativeObservationError("Native response contains non-finite coordinates")
    return result


def inspect_transport(record: dict[str, Any]) -> dict[str, Any]:
    """Extract directly reported fields without inferring an absent control.

    ``record`` is one JSON response emitted by the existing Automation/ExecSsl
    helper. The returned diagnostic is never a capture-pair observation.
    """
    if not isinstance(record, dict) or record.get("status") != "pass" or \
            record.get("stage") != "response_received":
        raise NativeObservationError("Transport did not receive a passing editor response")
    response = record.get("response")
    script = record.get("script")
    mode = record.get("mode")
    if not isinstance(response, str) or not response.startswith("D11T_SYSTEMS_OK\n"):
        raise NativeObservationError("Unexpected or missing D11 editor response")
    if not isinstance(script, str) or not script or not isinstance(mode, str) or not mode:
        raise NativeObservationError("Transport lacks its exact request script or mode")
    engine_pid = record.get("engineProcessId")
    if type(engine_pid) is not int or engine_pid <= 0:
        raise NativeObservationError("Transport lacks a positive engine PID")
    if type(record.get("readOnly")) is not bool:
        raise NativeObservationError("Transport lacks readOnly classification")
    resolution = [int(value) for value in _one(SIZE, response, "camera resolution")]
    window_size = [int(value) for value in _one(WINDOW, response, "video config window size")]
    if min(*resolution, *window_size) <= 0:
        raise NativeObservationError("Editor reported a non-positive screen size")
    camera = _floats(_one(CAMERA, response, "active play camera transform"))
    lights: dict[str, dict[str, Any]] = {}
    for row in LIGHT.findall(response):
        name = row[0]
        if name in lights:
            raise NativeObservationError(f"Duplicate local light: {name}")
        values = _floats(row[1:])
        lights[name] = {
            "id": name, "position": values[0:3], "tangent": values[3:6],
            "intensity": values[6], "radius": values[7], "cone": values[8],
        }
    states: dict[str, bool] = {}
    for name, enabled in LIGHT_STATE.findall(response):
        if name in states:
            raise NativeObservationError(f"Duplicate local light state: {name}")
        states[name] = enabled == "true"
    if set(lights) != set(states):
        raise NativeObservationError("Local light identities lack matching enabled states")
    for name, enabled in states.items():
        lights[name]["enabled"] = enabled
    return {
        "status": "PARTIAL_CONTEXT_ONLY", "pairProtocolEligible": False,
        "transport": {
            "mode": mode, "readOnly": record["readOnly"], "enginePid": engine_pid,
            "requestSentUtc": record.get("requestSentUtc"),
            "receivedUtc": record.get("receivedUtc"),
            "requestScriptSha256": sha256(script.encode("utf-8")).hexdigest(),
            "responseSha256": sha256(response.encode("utf-8")).hexdigest(),
        },
        "reported": {
            "videoConfigWindowSize": window_size,
            "activePlayCameraResolution": resolution,
            "activePlayCamera": {"position": camera[:3], "forward": camera[3:]},
            "truckLocalLights": [lights[name] for name in sorted(lights)],
        },
        "missingMatchedPairRuntimeFields": MISSING_MATCHED_PAIR_RUNTIME_FIELDS.copy(),
        "missingMatchedPairCaptureLinkage": MISSING_MATCHED_PAIR_CAPTURE_LINKAGE.copy(),
        "limitations": [
            "The existing editor helper does not report camera up, global lighting controls, or all scene-local lights.",
            "A SetCab response and a CaptureCab response do not establish a fresh pre-trigger observation.",
            "Scene weather settings are source declarations, not runtime readback.",
            "The transport alone does not bind a run, scene, view, protocol, or screenshot; future runner receipts must do so.",
        ],
    }


def inspect_transport_path(path: str | Path) -> dict[str, Any]:
    """Read one bounded, unlinked transport JSON without changing the file."""
    unresolved = Path(path).expanduser()
    if unresolved.is_symlink():
        raise NativeObservationError("Transport path must not be a link")
    resolved = unresolved.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise NativeObservationError("Transport path is not a regular file")
    if resolved.stat().st_size > MAX_TRANSPORT_BYTES:
        raise NativeObservationError("Transport JSON exceeds size limit")
    try:
        record = json.loads(resolved.read_bytes())
    except (UnicodeError, ValueError) as exc:
        raise NativeObservationError(f"Transport is invalid JSON: {exc}") from exc
    return inspect_transport(record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", type=Path, help="Existing native camera or capture JSON")
    args = parser.parse_args()
    print(json.dumps(inspect_transport_path(args.transport), indent=2))


if __name__ == "__main__":
    main()
