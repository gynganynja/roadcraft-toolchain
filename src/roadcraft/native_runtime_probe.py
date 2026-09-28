"""Parse scratch-only RoadCraft SSL runtime API probe replies.

These fragments have not been executed in the native editor. Parsed replies
remain partial diagnostic observations, never capture-pair evidence.
"""

from __future__ import annotations

import math
import re
from typing import Any


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
CAMERA = re.compile(
    rf"D11R_CAMERA_UP pos ({NUMBER}) ({NUMBER}) ({NUMBER}) "
    rf"forward ({NUMBER}) ({NUMBER}) ({NUMBER}) "
    rf"up ({NUMBER}) ({NUMBER}) ({NUMBER})"
)
WEATHER = re.compile(rf"D11R_WEATHER_STATE rainEnabled (true|false) rainPower ({NUMBER})")
SUN = re.compile(rf"D11R_SUN_DIRECTION ({NUMBER}) ({NUMBER}) ({NUMBER})")
DAYTIME = re.compile(rf"D11R_DAYTIME ({NUMBER})")
PATTERNS = {
    "camera_up": CAMERA, "weather_state": WEATHER,
    "sun_direction": SUN, "daytime": DAYTIME,
}


class NativeRuntimeProbeError(ValueError):
    """A probe reply is missing, malformed, or outside its documented scope."""


def _numbers(values: tuple[str, ...]) -> list[float]:
    numbers = [float(value) for value in values]
    if not all(math.isfinite(value) for value in numbers):
        raise NativeRuntimeProbeError("Probe contains a non-finite number")
    return numbers


def _nonzero(vector: list[float], name: str) -> None:
    if math.sqrt(sum(value * value for value in vector)) < 1e-8:
        raise NativeRuntimeProbeError(f"{name} vector is zero")


def parse_probe_reply(kind: str, response: str) -> dict[str, Any]:
    """Parse one exact native reply without inferring renderer or scene state.

    The caller must separately preserve the native transport, exact request
    script, engine PID, UTC times, and source/project pins. A synthetically
    valid string alone does not authenticate an editor observation.
    """
    pattern = PATTERNS.get(kind)
    if pattern is None:
        raise NativeRuntimeProbeError(f"Unknown probe kind: {kind}")
    if not isinstance(response, str):
        raise NativeRuntimeProbeError("Probe reply is not a string")
    match = pattern.fullmatch(response)
    if match is None:
        raise NativeRuntimeProbeError(f"{kind} probe did not return its exact success record")
    if kind == "camera_up":
        numbers = _numbers(match.groups())
        forward, up = numbers[3:6], numbers[6:9]
        _nonzero(forward, "Camera forward")
        _nonzero(up, "Camera up")
        reported = {
            "camera": {
                "position": numbers[:3], "forward": forward, "up": up,
            }
        }
    elif kind == "weather_state":
        rain_power = _numbers((match.group(2),))[0]
        if not 0.0 <= rain_power <= 1.0:
            raise NativeRuntimeProbeError("Rain power outside [0, 1]")
        reported = {
            "weatherState": {
                "rainEnabled": match.group(1) == "true", "rainPower": rain_power,
            }
        }
    elif kind == "sun_direction":
        vector = _numbers(match.groups())
        _nonzero(vector, "Sun direction")
        reported = {"sunDirection": vector}
    else:
        reported = {"dayTimeRaw": _numbers(match.groups())[0]}
    return {
        "status": "PARTIAL_RUNTIME_READBACK",
        "pairProtocolEligible": False,
        "probeKind": kind,
        "reported": reported,
        "limitations": [
            "The probe fragments have not been compiled or executed in a disposable editor.",
            "No weather preset, ambient RGB, exposure, tonemap, renderer mode, or complete local-light roster is observed.",
            "The reply alone has no run, scene, image, timing, or transport authentication.",
        ],
    }
