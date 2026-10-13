"""Vehicle authoring helpers: frames, hinge axes and the suspension model.

Frames (library/frames.md): the RoadCraft truck frame used for authoring in Blender is metres, front
toward -Y, left +X, up +Z, ground at z = 0.  The engine's native (USF) frame is X left, Y up, Z forward.

Suspension (library/suspension-and-wheels.md): per axle, a position of the wheel relative to its
modelled place (+ = lower); ``min`` is the bump stop, ``max`` the droop stop, ``height`` the spring's
neutral offset (a positive value raises the vehicle) and ``strength`` is relative to the vehicle's own
mass.  Static sag ~= share / (strength * beta), share = the wheel's fraction of the weight (0.25 on an
even four-wheeler).  Two estimates of beta disagree: ~58 is the median over the retail scouts if they
rest as modelled (they spread about +-40 % around it), ~105 was measured on the Roamer 105 in the
editor's play mode.  Designs use 58 (a vehicle that turns out stiffer rides high, which is the milder
failure) and are checked at 105 as well; ``calibrate_beta`` settles it from a drive.
"""

from __future__ import annotations

import math
from typing import Any

SUSPENSION_BETA = 58.0
SUSPENSION_BETA_SPREAD = 0.40
# Roamer 105, editor play mode, 2026-09-12: front height 0.265 / strength 0.017 and rear 0.23 / 0.030
# rested level 0.142 m above modelled (0.185 / 0.15 gave +0.060 / +0.063); calibrate_beta on those rests.
SUSPENSION_BETA_MEASURED = 105.0
# Driving feel of the retail scouts.  The SDK default of all three is 1, which is instant.
RETAIL_SCOUT_DRIVING = {"maxSteerSpeed": 0.03, "backSteerSpeed": 0.06, "pedalsResponsiveness": 0.35}


def rc_to_native(p: tuple[float, float, float]) -> tuple[float, float, float]:
    """RoadCraft/Blender truck frame -> native (X left, Y up, Z forward)."""
    x, y, z = p
    return (x, z, -y)


def native_to_rc(p: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = p
    return (x, -z, y)


def child_rotation(axis_native: tuple[float, float, float]) -> list[float]:
    """Euler XYZ degrees for a markup hinge's ``childRotation`` so that the constraint's Z axis
    (the hinge axis) is ``axis_native``; R = Rz @ Ry @ Rx with rz = 0."""
    x, y, z = axis_native
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    rx = -math.asin(max(-1.0, min(1.0, y)))
    ry = math.atan2(x, z) if abs(math.cos(rx)) > 1e-9 else 0.0
    return [round(math.degrees(rx), 4), round(math.degrees(ry), 4), 0]


def ragdoll_child_rotation(axis_native: tuple[float, float, float]) -> list[float]:
    """Euler XYZ degrees for a markup ragdoll's ``childRotation`` so that its twist axis (the constraint
    frame's X, Havok) is ``axis_native``; R = Rz @ Ry @ Rx with rx = 0. Up (0, 1, 0) gives [0, 0, 90], the
    retail whip antenna's value (library/secondary-physics.md)."""
    x, y, z = axis_native
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    ry = -math.asin(max(-1.0, min(1.0, z)))
    rz = math.atan2(y, x) if abs(math.cos(ry)) > 1e-9 else 0.0
    return [0, round(math.degrees(ry), 4) + 0.0, round(math.degrees(rz), 4) + 0.0]


def euler_x_axis(rotation: list[float]) -> tuple[float, float, float]:
    """The native axis that ``childRotation`` Euler XYZ degrees turn X onto (inverse of ragdoll_child_rotation)."""
    rx, ry, rz = (math.radians(a) for a in rotation)
    v = (1.0, 0.0, 0.0)
    v = (v[0], v[1] * math.cos(rx) - v[2] * math.sin(rx), v[1] * math.sin(rx) + v[2] * math.cos(rx))
    v = (v[0] * math.cos(ry) + v[2] * math.sin(ry), v[1], -v[0] * math.sin(ry) + v[2] * math.cos(ry))
    return (v[0] * math.cos(rz) - v[1] * math.sin(rz), v[0] * math.sin(rz) + v[1] * math.cos(rz), v[2])


def euler_axis(rotation: list[float]) -> tuple[float, float, float]:
    """The native axis that ``childRotation`` Euler XYZ degrees turn Z onto (inverse of child_rotation)."""
    rx, ry, rz = (math.radians(a) for a in rotation)
    v = (0.0, -math.sin(rx), math.cos(rx))
    v = (v[0] * math.cos(ry) + v[2] * math.sin(ry), v[1], -v[0] * math.sin(ry) + v[2] * math.cos(ry))
    v = (v[0] * math.cos(rz) - v[1] * math.sin(rz), v[0] * math.sin(rz) + v[1] * math.cos(rz), v[2])
    return v


def static_sag(strength: float, share: float, beta: float = SUSPENSION_BETA) -> float:
    """Metres the wheel rises from its spring's neutral point under the vehicle's weight."""
    if strength <= 0:
        return math.inf
    return share / (strength * beta)


def rest_position(axle: dict[str, Any], share: float, beta: float = SUSPENSION_BETA) -> float:
    """Where the wheel settles relative to its modelled place (+ = lower), before the stops."""
    return float(axle.get("height", 0.0)) - static_sag(float(axle.get("strength", 0.0)), share, beta)


def design_axle(sag: float, share: float, *, lift: float = 0.0, bump: float = 0.16, droop: float = 0.20,
                damping: float = 0.15, beta: float = SUSPENSION_BETA) -> dict[str, Any]:
    """A SuspensionAxle that rests ``lift`` metres higher than modelled with ``sag`` of static sag,
    ``bump`` of travel up and ``droop`` down from that rest."""
    if sag <= 0 or share <= 0:
        raise ValueError("sag and share must be positive")
    rest = lift                                   # wheel this far below its modelled place = body this far higher
    return {"min": round(rest - bump, 4), "max": round(rest + droop, 4), "height": round(sag + lift, 4),
            "strength": round(share / (sag * beta), 5), "damping": damping, "__type": "SuspensionAxle"}


def axle_report(axle: dict[str, Any], share: float, beta: float = SUSPENSION_BETA,
                spread: float = SUSPENSION_BETA_SPREAD, measured: float | None = SUSPENSION_BETA_MEASURED
                ) -> dict[str, Any]:
    """Predicted rest and remaining travel of an axle, also at the edges of beta's uncertainty and at
    the measured beta."""
    low, high = float(axle.get("min", 0.0)), float(axle.get("max", 1.0))
    cases = [("expected", beta), ("softer", beta * (1 - spread)), ("stiffer", beta * (1 + spread))]
    if measured and not math.isclose(measured, beta, rel_tol=0.05):
        cases.append(("measured", measured))
    rows = {}
    for label, b in cases:
        rest = rest_position(axle, share, b)
        clamped = min(max(rest, low), high)
        rows[label] = {"beta": round(b, 2), "rest": round(rest, 4), "onBumpStop": rest <= low,
                       "onDroopStop": rest >= high, "bumpRoom": round(clamped - low, 4),
                       "droopRoom": round(high - clamped, 4)}
    return {"share": share, "sag": round(static_sag(float(axle.get("strength", 0.0)), share, beta), 4),
            "cases": rows}


def calibrate_beta(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """beta from rests seen in the game.  Each observation is ``{"axle": SuspensionAxle, "rest": metres
    the wheel sits below its modelled place (+ = vehicle higher), "wheels": wheels on that axle}``; the
    listed axles must carry the whole weight and no wheel may rest on a stop.  With every axle observed
    the weight shares need not be known: sum(wheels * strength * sag) = 1 / beta."""
    total = 0.0
    sags = []
    for item in observations:
        axle = item["axle"]
        strength = float(axle.get("strength", 0.0))
        sag = float(axle.get("height", 0.0)) - float(item["rest"])
        low, high = float(axle.get("min", 0.0)), float(axle.get("max", 1.0))
        if strength <= 0 or sag <= 0:
            raise ValueError("each observed axle needs strength > 0 and a rest below its height")
        if not low < float(item["rest"]) < high:
            raise ValueError("an axle resting on a stop says nothing about its spring")
        sags.append((sag, strength))
        total += int(item.get("wheels", 2)) * strength * sag
    beta = 1.0 / total
    return {"beta": round(beta, 2),
            "shares": [round(beta * strength * sag, 4) for sag, strength in sags],
            "sags": [round(sag, 4) for sag, _ in sags]}


def wheel_contact_metrics(wheel: dict[str, Any], *, body_mass: float | None = None) -> dict[str, Any]:
    """Inspect compiled wheel values without mistaking them for normalized BRO dimensions.

    Radius and width are scaled by EditableWheel; mass/radiusOffset remain explicit
    native values (Apoc and stock Armiger compiled comparison, 2026-09-30).
    SDK PropTruckWheel describes speed-based VISUAL stabilization, not a physics fix.
    Ratios are diagnostics, not universal handling pass/fail thresholds.
    """
    def number(key: str, default: Any = None) -> float:
        value = wheel.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"wheel {key} must be a finite number")
        return float(value)

    radius, mass = number("radius"), number("mass")
    offset = number("radiusOffset", 0)
    if radius <= 0 or mass <= 0:
        raise ValueError("compiled wheel radius and mass must be positive")
    enabled = wheel.get("isWheelStabilizationEnabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("isWheelStabilizationEnabled must be boolean")
    physical, stabilized = number("maxSpeedFullPhysWheel", 15), number("maxSpeedFullFakeWheel", 30)
    if enabled and not 0 <= physical < stabilized:
        raise ValueError("visual stabilization needs 0 <= physical speed < stabilized speed")
    result = {"radius": radius, "mass": mass, "radiusOffset": offset,
              "radiusOffsetFraction": offset / radius,
              "visualStabilization": {"enabled": enabled, "physicalThroughKmh": physical,
                                      "stabilizedFromKmh": stabilized}}
    if body_mass is not None:
        if isinstance(body_mass, bool) or not isinstance(body_mass, (int, float)) or not math.isfinite(body_mass) or body_mass <= 0:
            raise ValueError("body_mass must be finite and positive")
        result["wheelBodyMassRatio"] = mass / body_mass
    return result
