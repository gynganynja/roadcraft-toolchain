"""Headless physics bench: a candidate pak in a windowless engine, timed inputs, probes, summary.

library/headless-bench.md explains use, evidence and the proposed first live run.  This is stage 2
of the headless editor (desktop requirement 4 "bench" and 5 "capture"): no IntegrationStudio, no
install, no owner mods folder.  ``engine.EngineSession`` runs the engine; this module turns a
scenario JSON into SSL statements, drives them on a timetable, records the replies in the
series.jsonl format of integrations/physics-bench/series_probe.ps1 (so physics_bench.parse_series
reads them) and writes one CSV per probe plus summary.json.

    python -m roadcraft.bench_headless run <scenario.json> --pak <candidate.pak> [--baseline <pak>]
        --out <new folder> --owner-approved "<who/when/why>" [--dry-run]
    python -m roadcraft.bench_headless capture <scenario.json> --pak <pak> --out <folder> --owner-approved "..."
    python -m roadcraft.bench_headless smoke --out <folder> [--pak <pak>] --owner-approved "..."
    python -m roadcraft.bench_headless scene --out <folder> [--scene <scn>] [--mode play|edit] --owner-approved "..."
        (C:\\RC_RE\\research\\scene_play.md: Game editor connector, StartFrameSharing, LoadScenePlay, truck, PNG)
    python -m roadcraft.bench_headless analyse <run folder> --scenario <scenario.json>

Without ``--owner-approved`` every command is a dry run: it prints the exact command lines, folders,
files and SSL scripts it would use and launches nothing.

The SSL statements are those of the editor bench (input_override.ps1, series_probe.ps1: Build, run in
the editor's engine), the D11 RC3 bench (joint angles, track sliding: Build) and the D11 capture
scripts (fly camera: Build); what has not run anywhere is marked Inferred where it is built.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from . import engine as eng
from . import physics_bench as pb

SCHEMA_VERSION = 1
PROBE_ITEMS = ("engine", "bodies", "com", "wheels", "joints", "tracks")
GEARS = ("AUTO", "LOW_GEAR", "HIGH_GEAR", "REVERSE", "NEUTRAL")
SWITCH = ("Unchanged", "On", "Off")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENUM_VALUE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")
SCENARIO_KEYS = {"schemaVersion", "name", "note", "seed", "timestep", "durationSeconds", "wallClockSeconds",
                 "startupTimeoutSeconds", "scene", "vehicle", "spawn", "inputs", "probes", "capture", "analysis"}
STEP_KEYS = {"at", "phase", "pedal", "steer", "handbrake", "gear", "engine", "awd", "difflock", "controls"}


class ScenarioError(ValueError):
    """The scenario file is unusable."""


# ------------------------------------------------------------------ scenario
def _number(value: Any, where: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ScenarioError(f"{where} must be a number")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ScenarioError(f"{where} must be within [{lo}, {hi}]")
    return float(value)


def _choice(value: Any, where: str, options: Sequence[str]) -> str:
    if value not in options:
        raise ScenarioError(f"{where} must be one of {list(options)}")
    return value


def _control(row: Any, where: str) -> dict[str, Any]:
    """A joint/attachment control: ``truck.owner.TryGet<controller>().GetState().<field>.Set(value)``
    (the D11 RC3 bench set ``PropTruckViewGraderController`` ``bladeAngle`` this way)."""
    if not isinstance(row, dict) or set(row) - {"controller", "field", "value"}:
        raise ScenarioError(f"{where} must be {{controller, field, value}}")
    for key in ("controller", "field"):
        if not isinstance(row.get(key), str) or not IDENT.match(row[key]):
            raise ScenarioError(f"{where}.{key} must be an identifier")
    value = row.get("value")
    if isinstance(value, bool):
        literal = "true" if value else "false"
    elif isinstance(value, (int, float)):
        literal = _fmt(_number(value, f"{where}.value", -1e6, 1e6))
    elif isinstance(value, str) and ENUM_VALUE.match(value):
        literal = value
    else:
        raise ScenarioError(f"{where}.value must be a number, a bool or Enum.VALUE")
    return {"controller": row["controller"], "field": row["field"], "value": value, "literal": literal}


def _step(row: Any, k: int, previous: dict[str, Any] | None) -> dict[str, Any]:
    where = f"inputs.schedule[{k}]"
    if not isinstance(row, dict):
        raise ScenarioError(f"{where} must be an object")
    unknown = sorted(set(row) - STEP_KEYS)
    if unknown:
        raise ScenarioError(f"{where}: unknown keys {unknown}")
    step = {"at": _number(row.get("at"), f"{where}.at", 0, 86400),
            "phase": str(row.get("phase") or f"step{k}"),
            "pedal": _number(row.get("pedal", 0), f"{where}.pedal", -1, 1),
            "steer": _number(row.get("steer", 0), f"{where}.steer", -1, 1),
            "handbrake": _choice(row.get("handbrake", "Unchanged"), f"{where}.handbrake", SWITCH),
            "gear": _choice(row.get("gear", ""), f"{where}.gear", ("",) + GEARS),
            "engine": bool(row.get("engine", True)),
            "awd": _choice(row.get("awd", "Unchanged"), f"{where}.awd", SWITCH),
            "difflock": _choice(row.get("difflock", "Unchanged"), f"{where}.difflock", SWITCH),
            "controls": [_control(c, f"{where}.controls[{i}]") for i, c in enumerate(row.get("controls") or [])]}
    if previous is not None and step["at"] <= previous["at"]:
        raise ScenarioError(f"{where}.at must increase")
    return step


def schedule_from_physics_bench(name: str) -> list[dict[str, Any]]:
    """The editor bench's named schedules (physics_bench.SCHEDULES) as scenario steps."""
    plan = pb.SCHEDULES[name]
    return [{"at": at, "phase": plan["names"][k], "pedal": pedal, "steer": steer, "handbrake": brake, "gear": gear}
            for k, (at, (pedal, steer, brake, gear)) in enumerate(plan["steps"])]


def load_scenario(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a scenario (file or dict)."""
    data = source if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ScenarioError("scenario must be a JSON object")
    unknown = sorted(set(data) - SCENARIO_KEYS)
    if unknown:
        raise ScenarioError(f"unknown scenario keys: {unknown}")
    if data.get("schemaVersion", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ScenarioError(f"schemaVersion must be {SCHEMA_VERSION}")
    out: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "name": str(data.get("name") or "scenario"),
                           "note": data.get("note")}
    seed = data.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ScenarioError("seed must be an integer")
    out["seed"] = seed
    out["timestep"] = None if data.get("timestep") is None else _number(data["timestep"], "timestep", 1 / 1000, 1)
    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict) or set(inputs) - {"method", "schedule"}:
        raise ScenarioError("inputs must be {method, schedule}")
    method = _choice(inputs.get("method", "Debug"), "inputs.method", ("Debug", "State"))
    raw = inputs.get("schedule", "normal")
    if isinstance(raw, str):
        if raw not in pb.SCHEDULES:
            raise ScenarioError(f"inputs.schedule names one of {sorted(pb.SCHEDULES)} or lists steps")
        raw_steps, default_duration = schedule_from_physics_bench(raw), pb.SCHEDULES[raw]["duration"]
    elif isinstance(raw, list) and raw:
        raw_steps, default_duration = raw, None
    else:
        raise ScenarioError("inputs.schedule must be a name or a non-empty list")
    steps: list[dict[str, Any]] = []
    for k, row in enumerate(raw_steps):
        steps.append(_step(row, k, steps[-1] if steps else None))
    duration = data.get("durationSeconds", default_duration)
    if duration is None:
        duration = steps[-1]["at"] + 10
    out["durationSeconds"] = _number(duration, "durationSeconds", 1, 3600)
    if steps[-1]["at"] >= out["durationSeconds"]:
        raise ScenarioError("the last input step must come before durationSeconds")
    out["inputs"] = {"method": method, "schedule": steps,
                     "source": raw if isinstance(raw, str) else "scenario"}
    out["wallClockSeconds"] = _number(data.get("wallClockSeconds", 900), "wallClockSeconds", 30, 7200)
    out["startupTimeoutSeconds"] = _number(data.get("startupTimeoutSeconds", 300), "startupTimeoutSeconds", 10, 3600)
    scene = data.get("scene") or {}
    if not isinstance(scene, dict) or set(scene) - {"level", "loadSsl", "file", "settleSeconds", "readyTimeoutSeconds"}:
        raise ScenarioError("scene must be {level, loadSsl, file, settleSeconds, readyTimeoutSeconds}")
    for key in ("level", "loadSsl", "file"):
        if scene.get(key) is not None and (not isinstance(scene[key], str) or not scene[key].isprintable()
                                           or '"' in scene[key] or "\\" in scene[key]):
            raise ScenarioError(f"scene.{key} must be a plain string")
    out["scene"] = {"level": scene.get("level"), "loadSsl": scene.get("loadSsl"), "file": scene.get("file"),
                    "settleSeconds": _number(scene.get("settleSeconds", 5), "scene.settleSeconds", 0, 600),
                    "readyTimeoutSeconds": _number(scene.get("readyTimeoutSeconds", 120),
                                                   "scene.readyTimeoutSeconds", 1, 3600)}
    vehicle = data.get("vehicle") or {}
    allowed = {"tpl", "hull", "frames", "restHeightModelled", "suspensionTravel", "wheelNames"}
    if not isinstance(vehicle, dict) or set(vehicle) - allowed:
        raise ScenarioError(f"vehicle keys are {sorted(allowed)}")
    tpl = vehicle.get("tpl", "*")
    if not isinstance(tpl, str) or not re.match(r"^[\w./*-]+$", tpl):
        raise ScenarioError("vehicle.tpl must be a template name or *")
    travel = vehicle.get("suspensionTravel")
    if travel is not None:
        if not isinstance(travel, dict) or set(travel) != {"min", "max"}:
            raise ScenarioError("vehicle.suspensionTravel must be {min, max}")
        travel = {k: _number(travel[k], f"vehicle.suspensionTravel.{k}", -10, 10) for k in ("min", "max")}
    hull = vehicle.get("hull")
    if hull is not None and (not isinstance(hull, str) or not IDENT.match(hull)):
        raise ScenarioError("vehicle.hull must be a body name")
    wheel_names = vehicle.get("wheelNames")
    if wheel_names is not None and (not isinstance(wheel_names, list)
                                    or not all(isinstance(n, str) and IDENT.match(n) for n in wheel_names)):
        raise ScenarioError("vehicle.wheelNames must list wheel names in truck.GetWheels() order")
    out["vehicle"] = {"tpl": tpl, "hull": hull, "frames": list(vehicle.get("frames") or []) or None,
                      "restHeightModelled": None if vehicle.get("restHeightModelled") is None else
                      _number(vehicle["restHeightModelled"], "vehicle.restHeightModelled", -1000, 10000),
                      "suspensionTravel": travel, "wheelNames": list(wheel_names) if wheel_names else None}
    spawn = data.get("spawn") or {"method": "none"}
    if not isinstance(spawn, dict) or set(spawn) - {"method", "scene", "vehicle", "position", "boxes"}:
        raise ScenarioError("spawn must be {method, scene, vehicle, position, boxes}")
    method = _choice(spawn.get("method", "none"), "spawn.method", ("none", "scene"))
    if method == "scene":
        position = spawn.get("position")
        if not (isinstance(position, list) and len(position) == 3):
            raise ScenarioError("spawn.position must be [x, y, z]")
        if not isinstance(spawn.get("scene"), str) or not isinstance(spawn.get("vehicle"), str):
            raise ScenarioError("spawn.scene (relative to mods_source) and spawn.vehicle are required")
        spawn = {"method": method, "scene": spawn["scene"], "vehicle": spawn["vehicle"],
                 "position": [_number(v, "spawn.position", -1e5, 1e5) for v in position],
                 "boxes": [_box(b, f"spawn.boxes[{i}]") for i, b in enumerate(spawn.get("boxes") or [])]}
    else:
        spawn = {"method": "none"}
    out["spawn"] = spawn
    probes = data.get("probes") or {}
    if not isinstance(probes, dict) or set(probes) - {"rateHz", "items", "readback"}:
        raise ScenarioError("probes must be {rateHz, items, readback}")
    items = probes.get("items", ["engine", "bodies", "com", "wheels"])
    if not isinstance(items, list) or set(items) - set(PROBE_ITEMS) or not items:
        raise ScenarioError(f"probes.items must be a non-empty subset of {list(PROBE_ITEMS)}")
    out["probes"] = {"rateHz": _number(probes.get("rateHz", 10), "probes.rateHz", 0.1, 60),
                     "items": [i for i in PROBE_ITEMS if i in items], "readback": bool(probes.get("readback", False))}
    out["capture"] = load_capture(data.get("capture"))
    analysis = data.get("analysis") or {}
    out["analysis"] = {
        "pivotSteer": _number(analysis.get("pivotSteer", 0.5), "analysis.pivotSteer", 0, 1),
        "pivotPhases": list(analysis.get("pivotPhases") or []),
        "settle": {"rollDeg": _number((analysis.get("settle") or {}).get("rollDeg", 0.2), "settle.rollDeg", 0, 90),
                   "pitchDeg": _number((analysis.get("settle") or {}).get("pitchDeg", 0.2), "settle.pitchDeg", 0, 90),
                   "heightMm": _number((analysis.get("settle") or {}).get("heightMm", 5), "settle.heightMm", 0, 1e4)},
        "stopToleranceM": _number(analysis.get("stopToleranceM", 0.005), "analysis.stopToleranceM", 0, 1),
        "judderMinHz": _number(analysis.get("judderMinHz", 0.3), "analysis.judderMinHz", 0.01, 30),
        "articulation": _articulation_spec(analysis.get("articulation")),
    }
    return out


def _box(row: Any, where: str) -> dict[str, Any]:
    """A static collision box added to the private scene copy (physics_bench.add_box)."""
    if not isinstance(row, dict) or set(row) - {"name", "position", "scale", "yaw"}:
        raise ScenarioError(f"{where} must be {{name, position, scale, yaw}}")
    if not isinstance(row.get("name"), str) or not IDENT.match(row["name"]):
        raise ScenarioError(f"{where}.name must be an identifier")
    vecs = {}
    for key in ("position", "scale"):
        vec = row.get(key)
        if not (isinstance(vec, list) and len(vec) == 3):
            raise ScenarioError(f"{where}.{key} must be [x, y, z]")
        vecs[key] = [_number(v, f"{where}.{key}", -1e5, 1e5) for v in vec]
    if min(vecs["scale"]) <= 0:
        raise ScenarioError(f"{where}.scale must be positive")
    return {"name": row["name"], **vecs, "yaw": _number(row.get("yaw", 0), f"{where}.yaw", -360, 360)}


def _articulation_spec(raw: Any) -> dict[str, Any] | None:
    """``analysis.articulation``: track-frame pitch against the hull and wheel travel in the hull frame.
    ``frames`` body names (default: physics_bench.guess_bodies), ``wheels`` names (vehicle.wheelNames) or
    indices, ``joints`` constraint names whose J-probe angle is reported."""
    if raw is None or raw is False:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - {"frames", "wheels", "joints"}:
        raise ScenarioError("analysis.articulation must be {frames, wheels, joints}")
    out: dict[str, Any] = {}
    for key in ("frames", "joints"):
        names = raw.get(key)
        if names is not None and (not isinstance(names, list) or not all(isinstance(n, str) and IDENT.match(n)
                                                                         for n in names)):
            raise ScenarioError(f"analysis.articulation.{key} must list names")
        out[key] = list(names) if names is not None else None
    wheels = raw.get("wheels") or []
    if not isinstance(wheels, list) or not all((isinstance(w, str) and IDENT.match(w)) or
                                               (isinstance(w, int) and not isinstance(w, bool) and w >= 0)
                                               for w in wheels):
        raise ScenarioError("analysis.articulation.wheels must list wheel names or indices")
    out["wheels"] = list(wheels)
    return out


def load_capture(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {"cameras", "states", "settleSeconds"}:
        raise ScenarioError("capture must be {cameras, states, settleSeconds}")
    cameras = []
    for i, cam in enumerate(raw.get("cameras") or []):
        if not isinstance(cam, dict) or set(cam) - {"name", "offset", "target"} or not IDENT.match(str(cam.get("name"))):
            raise ScenarioError(f"capture.cameras[{i}] must be {{name, offset, target}}")
        offset = cam.get("offset")
        target = cam.get("target", [0, 0, 0])
        for key, vec in (("offset", offset), ("target", target)):
            if not (isinstance(vec, list) and len(vec) == 3):
                raise ScenarioError(f"capture.cameras[{i}].{key} must be [x, y, z]")
        cameras.append({"name": cam["name"], "offset": [_number(v, "offset", -1e3, 1e3) for v in offset],
                        "target": [_number(v, "target", -1e3, 1e3) for v in target]})
    if not cameras:
        raise ScenarioError("capture.cameras must list at least one camera")
    states = []
    for i, st in enumerate(raw.get("states") or [{"name": "as_loaded"}]):
        if not isinstance(st, dict) or set(st) - {"name", "headlights", "dayTime"} or not IDENT.match(str(st.get("name"))):
            raise ScenarioError(f"capture.states[{i}] must be {{name, headlights, dayTime}}")
        row = {"name": st["name"]}
        if "headlights" in st:
            row["headlights"] = bool(st["headlights"])
        if "dayTime" in st:
            row["dayTime"] = _number(st["dayTime"], "dayTime", 0, 24)
        states.append(row)
    return {"cameras": cameras, "states": states,
            "settleSeconds": _number(raw.get("settleSeconds", 1.0), "capture.settleSeconds", 0, 60)}


# ------------------------------------------------------------------ SSL
def _fmt(value: float) -> str:
    return f"{value:.3f}"


TRUCK_PREAMBLE = [
    'var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()',
    'if truck == null', ' return "ROAMER_NO_CURRENT_TRUCK"', 'end',
    'var viewController = truck.owner.TryGet<PropTruckViewController>()',
    'if viewController == null', ' return "ROAMER_NO_VIEW_CONTROLLER"', 'end',
    'var state = viewController.GetState()',
    'if state == null', ' return "ROAMER_NO_TRUCK_STATE"', 'end',
    'var gearbox = truck.owner.TryGet<PropTruckGearboxController>()']


def input_script(step: dict[str, Any] | None, method: str = "Debug") -> str:
    """input_override.ps1 Build-InputScript, statement for statement (``step`` None = Release), plus
    the scenario's joint/attachment controls."""
    lines = list(TRUCK_PREAMBLE)
    if step is None:
        if method == "State":
            lines += ["state.pedals.Set(0.000)", "state.steering.Set(0.000)"]
        else:
            lines += ["viewController.dbgOverrideInputs = false", "viewController.dbgAccelerationOverride = 0.000",
                      "viewController.dbgSteerOverride = 0.000"]
    else:
        if step["engine"]:
            lines.append("state.isEngineOff.Set(false)")
        if step["handbrake"] != "Unchanged":
            lines.append(f"state.isHandbrake.Set({'true' if step['handbrake'] == 'On' else 'false'})")
        gearbox = []
        if step["gear"]:
            gearbox.append(f" gearbox.GetState().gearState.Set(GearState.{step['gear']})")
        if step["awd"] != "Unchanged":
            gearbox.append(f" gearbox.GetState().isAwdOn.Set({'true' if step['awd'] == 'On' else 'false'})")
        if step["difflock"] != "Unchanged":
            gearbox.append(f" gearbox.GetState().isDifflockOn.Set({'true' if step['difflock'] == 'On' else 'false'})")
        if gearbox:
            lines += ["if gearbox != null and gearbox.GetState() != null", *gearbox, "end"]
        if method == "State":
            lines += [f"state.pedals.Set({_fmt(step['pedal'])})", f"state.steering.Set({_fmt(step['steer'])})"]
        else:
            lines += ["viewController.dbgOverrideInputs = true",
                      f"viewController.dbgAccelerationOverride = {_fmt(step['pedal'])}",
                      f"viewController.dbgSteerOverride = {_fmt(step['steer'])}"]
        for i, control in enumerate(step["controls"]):
            lines += [f"var control{i} = truck.owner.TryGet<{control['controller']}>()",
                      f"if control{i} != null and control{i}.GetState() != null",
                      f" control{i}.GetState().{control['field']}.Set({control['literal']})", "end"]
    lines += [
        'var result = "ROAMER_INPUT_APPLIED\\n"',
        'result += StringFormat("requestedPedals %.3f\\n", state.pedals.Get())',
        'result += StringFormat("requestedSteer %.3f\\n", state.steering.Get())',
        'result += StringFormat("inputPedals %.3f\\n", truck.input.pedals)',
        'result += StringFormat("inputSteer %.3f\\n", truck.input.steer)',
        'result += "handbrake " + BoolToString(state.isHandbrake.Get(), "true", "false") + "\\n"',
        'result += "handbrakeLocked " + BoolToString(state.handbrakeIsLocked.Get(), "true", "false") + "\\n"',
        'result += "lowRange " + BoolToString(truck.input.isLowRangeMode, "true", "false") + "\\n"',
        'result += "awdInput " + BoolToString(truck.input.isAllWheelDrive, "true", "false") + "\\n"',
        'result += "difflockInput " + BoolToString(truck.input.isDiffLock, "true", "false") + "\\n"',
        'if gearbox != null and gearbox.GetState() != null',
        ' result += "awdOn " + BoolToString(gearbox.GetState().isAwdOn.Get(), "true", "false") + "\\n"',
        ' result += "difflockOn " + BoolToString(gearbox.GetState().isDifflockOn.Get(), "true", "false") + "\\n"',
        'end']
    if method == "Debug":
        lines.append('result += "debugOverride " + BoolToString(viewController.dbgOverrideInputs, "true", "false") + "\\n"')
    lines.append("return result")
    return "\n".join(lines)


def probe_script(items: Sequence[str], tpl: str = "*") -> str:
    """series_probe.ps1's read-only statement (lines F, G, B, C, W) plus the D11 RC3 bench's joint (J)
    and track (T) lines; ``tpl`` other than * refuses another truck (RC3 bench)."""
    lines = ['var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()',
             'if truck == null', ' return "NO_TRUCK"', 'end']
    if tpl != "*":
        lines += [f'if truck.owner.Get<Geom>().GetTplName() != "{tpl}"',
                  ' return "WRONG_TRUCK " + truck.owner.Get<Geom>().GetTplName()', 'end']
    lines += ['var ps = truck.owner.Get<PropPhysSystem>().GetPhysSys()', 'if ps == null', ' return "NO_PHYS"', 'end',
              'var result = StringFormat("F %i %.4f %.3f", GetFrameNmb(), truck.GetForwardLinearVelocity(), '
              'truck.input.pedals)',
              'result += StringFormat(" %.3f\\n", truck.input.steer)']
    if "engine" in items:
        lines += ['result += StringFormat("G %i %.1f", truck.GetGear(), truck.GetCurrentEngineRpm())',
                  'result += " " + BoolToString(truck.input.isHandbrake, "1", "0")',
                  'var viewController = truck.owner.TryGet<PropTruckViewController>()',
                  'if viewController != null',
                  ' result += " " + BoolToString(viewController.GetSslEngine().IsEngineRunning(), "1", "0")',
                  ' result += " " + BoolToString(viewController.GetSslEngine().IsBrakePull(), "1", "0")',
                  'end', 'result += "\\n"']
    if "bodies" in items or "com" in items:
        lines += ['for (var i = 0; i < ps.GetBodyCount() and i < 64; i += 1)', ' var body = ps.GetBodyByIdx(i)']
        if "bodies" in items:
            lines += [' var t = body.transform', ' var v = t.GetPosition()', ' result += "B " + body.GetName()',
                      ' result += StringFormat(" %.5f %.5f %.5f", v.x, v.y, v.z)', ' v = t.GetUp()',
                      ' result += StringFormat(" %.5f %.5f %.5f", v.x, v.y, v.z)', ' v = t.GetForward()',
                      ' result += StringFormat(" %.5f %.5f %.5f\\n", v.x, v.y, v.z)']
        if "com" in items:
            lines += [' var cl = body.GetCenterOfMassLocal()', ' var cw = body.GetCenterOfMass()',
                      ' result += "C " + body.GetName() + StringFormat(" %.3f %.5f %.5f %.5f", body.GetMass(), '
                      'cl.x, cl.y, cl.z)',
                      ' result += StringFormat(" %.5f %.5f %.5f\\n", cw.x, cw.y, cw.z)']
        lines.append('end')
    if "wheels" in items:
        lines += ['var wheels = truck.GetWheels()', 'for var wheel in wheels',
                  ' result += StringFormat("W %.4f", wheel.GetCurrentSpringTravelDistance())',
                  ' var info = wheel.runtimeInfo', ' if info != null', '  var wp = info.transform.GetPosition()',
                  '  result += StringFormat(" %.4f %.4f %.4f", wp.x, wp.y, wp.z)',
                  '  result += " " + BoolToString(info.isOnGround, "1", "0")',
                  '  result += StringFormat(" %.3f %.4f %.4f", info.angularVelocity, info.forwardLinearVelocity, '
                  'wheel.GetPhysicalRadius())',
                  '  result += StringFormat(" %.4f", info.mudDepth) + " " + BoolToString(info.isOnTerrain, "1", "0")',
                  ' end', ' result += "\\n"', 'end']
    if "joints" in items:
        lines += ['for var j in ps.GetAllConstraints()', ' if j.IsAngular()',
                  '  result += "J " + j.GetConstraintName() + StringFormat(" %.4f %.4f\\n", j.GetCurrentAngle(), '
                  'j.GetMotorCurrentTargetAngle())', ' end', 'end']
    if "tracks" in items:
        lines += ['var trackProp = truck.owner.TryGet<PropTruckTrack>()', 'if trackProp != null',
                  ' for var ti, track in trackProp.GetTracks()',
                  '  result += StringFormat("T %i %.4f\\n", ti, track.GetAverageSlidingVelocity())', ' end', 'end']
    lines.append("return result")
    return "\n".join(lines)


_RB_HEAD = ['var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()', 'if truck == null',
            ' return "NO_TRUCK"', 'end']
_RB_PS = ['var ps = truck.owner.Get<PropPhysSystem>().GetPhysSys()', 'if ps == null', ' return "NO_PHYS"', 'end']


def readback_scripts() -> dict[str, str]:
    """Read-only checks that the loaded truck is the build under test, one script per accessor so an
    accessor the engine rejects costs only its own line (KGS-25 campaign 2026-10-13).  ``identity``: model
    and owner; ``wheels``: physical radius and spring travel (series_probe.ps1's getters); ``softForce``:
    PropTruckWheel.softForceScale (a member name in the engine's PropTruckWheel table, Inferred readable);
    ``constraints``: name, angular, motor; ``motors``: GetMotorSpring/GetMotorDamping; ``limits``:
    GetAngularLimits (both from the engine's PhysConstraintInstance natives, Inferred)."""
    return {
        "identity": "\n".join(_RB_HEAD + ['var r = "RB_IDENTITY\\n"',
                                          'r += "tpl " + truck.owner.Get<Geom>().GetTplName() + "\\n"',
                                          'r += "owner " + truck.owner.ToString() + "\\n"', 'return r']),
        "wheels": "\n".join(_RB_HEAD + ['var r = "RB_WHEELS\\n"', 'for var wheel in truck.GetWheels()',
                                        ' r += StringFormat("w %.4f %.4f\\n", wheel.GetPhysicalRadius(), '
                                        'wheel.GetMaxSpringTravelDistance())', 'end', 'return r']),
        "softForce": "\n".join(_RB_HEAD + ['var r = "RB_SOFTFORCE\\n"', 'for var wheel in truck.GetWheels()',
                                           ' r += StringFormat("s %.4f\\n", wheel.softForceScale)', 'end', 'return r']),
        "constraints": "\n".join(_RB_HEAD + _RB_PS + [
            'var r = "RB_CONSTRAINTS\\n"', 'for var j in ps.GetAllConstraints()',
            ' r += "c " + j.GetConstraintName() + " " + BoolToString(j.IsAngular(), "1", "0") + " " '
            '+ BoolToString(j.HasMotor(), "1", "0") + "\\n"', 'end', 'return r']),
        "motors": "\n".join(_RB_HEAD + _RB_PS + [
            'var r = "RB_MOTORS\\n"', 'for var j in ps.GetAllConstraints()', ' if j.HasMotor()',
            '  r += "m " + j.GetConstraintName() + StringFormat(" %.1f %.1f\\n", j.GetMotorSpring(), '
            'j.GetMotorDamping())', ' end', 'end', 'return r']),
        "limits": "\n".join(_RB_HEAD + _RB_PS + [
            'var r = "RB_LIMITS\\n"', 'for var j in ps.GetAllConstraints()', ' if j.IsAngular()',
            '  var l = j.GetAngularLimits()',
            '  r += "l " + j.GetConstraintName() + StringFormat(" %.5f %.5f\\n", l.x, l.y)', ' end', 'end',
            'return r']),
    }


def parse_readback(replies: dict[str, str]) -> dict[str, Any]:
    """The readback replies as values; a reply without its RB_ marker is kept as an error text."""
    out: dict[str, Any] = {"errors": {}}
    markers = {"identity": "RB_IDENTITY", "wheels": "RB_WHEELS", "softForce": "RB_SOFTFORCE",
               "constraints": "RB_CONSTRAINTS", "motors": "RB_MOTORS", "limits": "RB_LIMITS"}
    constraints: dict[str, dict[str, Any]] = {}
    for key, reply in replies.items():
        if not isinstance(reply, str) or not reply.startswith(markers.get(key, "?")):
            out["errors"][key] = (reply or "")[:300] if isinstance(reply, str) else repr(reply)
            continue
        lines = [ln.split() for ln in reply.splitlines()[1:] if ln.strip()]
        try:
            if key == "identity":
                out["identity"] = {p[0]: " ".join(p[1:]) for p in lines if p}
            elif key == "wheels":
                out["wheelRadius"] = [float(p[1]) for p in lines if p[0] == "w"]
                out["wheelMaxTravel"] = [float(p[2]) for p in lines if p[0] == "w"]
            elif key == "softForce":
                out["softForceScale"] = [float(p[1]) for p in lines if p[0] == "s"]
            elif key == "constraints":
                for p in lines:
                    if p[0] == "c":
                        constraints.setdefault(p[1], {}).update(angular=p[2] == "1", motor=p[3] == "1")
            elif key == "motors":
                for p in lines:
                    if p[0] == "m":
                        constraints.setdefault(p[1], {}).update(spring=float(p[2]), damping=float(p[3]))
            elif key == "limits":
                for p in lines:
                    if p[0] == "l":
                        constraints.setdefault(p[1], {}).update(limits=[float(p[2]), float(p[3])])
        except (IndexError, ValueError) as exc:
            out["errors"][key] = f"unparsed: {exc}: {reply[:200]}"
    if constraints:
        out["constraints"] = constraints
    return out


def readback(session: Any, folder: Path) -> dict[str, Any]:
    """Run every readback script once (at rest, before the inputs); readback.json keeps raw and parsed."""
    replies = {key: _try_ssl(session, script, timeout=8.0) for key, script in readback_scripts().items()}
    parsed = parse_readback(replies)
    (folder / "readback.json").write_text(json.dumps({"replies": replies, "parsed": parsed}, indent=1),
                                          encoding="utf-8")
    return parsed


def camera_script(camera: dict[str, Any], hull: str) -> str:
    """D11 capture scripts: fly camera at hull position + offset, looking at hull position + target."""
    v = lambda xs: "V3Create(" + ",".join(_fmt(x) for x in xs) + ")"  # noqa: E731
    return "\n".join([
        'var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()',
        'if truck == null', ' return "NO_TRUCK"', 'end',
        'var ps = truck.owner.Get<PropPhysSystem>().GetPhysSys()',
        f'var body = ps.GetBody("{hull}")', 'if body == null', f' return "NO_BODY {hull}"', 'end',
        f'var aim = body.transform.GetPosition()+{v(camera["target"])}',
        'var shot = new Transform3d()', f'shot.SetPosition(aim+{v(camera["offset"])})',
        'shot.LookAt(aim,V3Create(0,1,0))',
        'GetCameraManager().ActivateCameraByKeymapLayer(KeymapCommon.FLY_CAMERA)',
        'GetCameraManager().SetActiveCameraTransform(shot)', 'return "CAMERA_SET"'])


def state_script(state: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Statements for a capture state and their grades."""
    lines, grades = [], {}
    if "headlights" in state:
        lines += list(TRUCK_PREAMBLE[:12]) + [f"state.isHeadlightsOn.Set({'true' if state['headlights'] else 'false'})"]
        grades["headlights"] = "Build (state.isHeadlightsOn.Set ran in the D11 lamp scripts through the editor)"
    if "dayTime" in state:
        lines.append(f"$preset_sys.SetDayTime({_fmt(state['dayTime'])})")
        grades["dayTime"] = "Inferred ($preset_sys.GetDayTime read in prior probes; SetDayTime not run)"
    lines.append('return "STATE_SET"')
    return "\n".join(lines), grades


def ready_script() -> str:
    return "\n".join(['var r = "RC_READY\\n"', 'r += StringFormat("frame %i\\n", GetFrameNmb())',
                      'r += "level " + $sslEngineCtrl.GetLevelName() + "\\n"',
                      'var truck = $globalStorage.TryGet<TruckManagerRb>()?.TryGetCurrent()',
                      'r += "truck " + BoolToString(truck != null, "1", "0") + "\\n"', 'return r'])


def load_scene_script(res_tag: str) -> str:
    """Scenario ``scene.loadSsl`` (a scene res tag): the SSL edit-mode load.  ``LoadSceneRes`` is a
    GameEditor method with five arguments (ssl editor/game_editor.ssl), not a global; the editor's own
    route is XgineEditMode.StartSceneLoading (scene_play.md, Inferred: not run)."""
    name = res_tag.rstrip("/").rsplit("/", 1)[-1].replace(".resource", "")
    return ssl_scene_script(name, res_tag, play=False)


# ------------------------------------------------------------------ scene / play (scene_play.md)
def _ssl_scene_params(name: str, res_tag: str) -> list[str]:
    return ["var p = new XgineSceneLoadParams()", f"p.name = {eng.ssl_string(name)}", 'p.psOverrides = ""',
            f"p.resTag = {eng.ssl_string(res_tag)}", 'p.resOverrides = ""', "p.unloadedBlocks = new array<string>()"]


def ssl_scene_script(name: str, res_tag: str, *, play: bool) -> str:
    """The SSL-only fallback (``--via ssl``, Inferred).  Edit: what XgineEditMode.ProcessLoadScene does
    with the message fields (all public).  Play: what XginePlayMode.StartSceneLoading/StartPlayMode do,
    through public members only (its private isPlaying/playModeSettings stay unset, scene-specific
    EditorSceneSettings.playModeSettings are not looked up: the extension's default ``settings`` plays)."""
    lines = ["var c = GetGameEditorController()"] + _ssl_scene_params(name, res_tag)
    if not play:
        return "\n".join(lines + ["DbgSetActorNoInitTerm(true)", "c.extensions.Get<XgineEditMode>().StartSceneLoading(p)",
                                  'return "SSL_LOAD_REQUESTED"'])
    return "\n".join(lines + [
        "c.extensions.Get<XgineEditMode>().Deactivate()",
        "c.gameEditor.SetSceneResource(p.resTag, \"\")",
        "c.gameEditor.SetPlayMode(true)",
        "c.extensions.Get<GameEditorFpsController>().SetMode(GameEditorFpsControllerMode.PLAY)",
        "c.sceneLoader.LoadScene(p)",
        "c.extensions.Get<XginePlayMode>().settings.Play(c)",
        'return "SSL_PLAY_REQUESTED"'])


def ssl_frame_sharing_script(width: int, height: int) -> str:
    """What XgineViewportsController.ProcessStartFrameSharing does for viewport 0 (public members; Inferred)."""
    w, h = max(64, int(width)), max(64, int(height))
    return "\n".join(["var c = GetGameEditorController()",
                      "var vp = GetGameEditorState().GetOrCreateViewport(c.viewports, 0)",
                      "vp.StartSharing()", f"vp.SetResolution({w}, {h})", f"vp.SetClientRect(0, 0, {w}, {h})",
                      "vp.SetVisible(true)", "EnableSimulationInputDevice(true)", 'return "SSL_FRAME_SHARING"'])


def adapter_script() -> str:
    """Which GPU the engine renders on: VideoConfig.api/adapter and the adapter names in AdapterId order
    ($sslEngineCtrl natives, ssl/lib/systems/engine_control.ssl; bug_reporter.ssc uses the same calls)."""
    return "\n".join(['var r = "RC_ADAPTER\\n"', "var cfg = $sslEngineCtrl.GetCurrentConfig()",
                      'r += StringFormat("api %i adapter %i\\n", cfg.api, cfg.adapter)',
                      'r += "current " + $sslEngineCtrl.GetVideoAdapterName(cfg.api, cfg.adapter) + "\\n"',
                      "var n = $sslEngineCtrl.GetVideoAdapterCount(cfg.api)",
                      "for (var i = 0; i < n; i += 1)",
                      '   r += StringFormat("adapter %i ", i) + $sslEngineCtrl.GetVideoAdapterName(cfg.api, i) + "\\n"',
                      "end", "return r"])


def editor_state_script() -> str:
    """Is the editor's SSL side up (FindObject("editor"), editor_main_base.ssl), which scene, viewports, trucks."""
    return "\n".join(['var r = "RC_EDITOR\\n"',
                      'r += "editorMain " + BoolToString(FindObject("editor") != null, "1", "0") + "\\n"',
                      'r += "level " + $sslEngineCtrl.GetLevelName() + "\\n"',
                      'r += "scene " + GetGameEditorState().GetCurrentScene() + "\\n"',
                      'r += StringFormat("viewports %i\\n", GetGameEditorState().GetViewports().Count())',
                      "var tm = $globalStorage.TryGet<TruckManagerRb>()",
                      "if tm != null",
                      '   r += StringFormat("trucks %i\\n", tm.GetTrucks().Count())',
                      "end",
                      'r += "truck " + BoolToString(tm?.TryGetCurrent() != null, "1", "0") + "\\n"',
                      "return r"])


def force_current_truck_script() -> str:
    """Opt-in fallback: TruckManagerRb.SetCurrent(start truck or first truck) - what
    StartAtExistingTruck does without the ownership checks (Inferred)."""
    return "\n".join(['var tag = "RC_FORCE_CURRENT"', "var tm = $globalStorage.TryGet<TruckManagerRb>()",
                      "if tm == null", '   return "NO_TRUCK_MANAGER"', "end",
                      "if tm.TryGetCurrent() != null", '   return "ALREADY_CURRENT"', "end",
                      "var trucks = tm.GetTrucks()", "if trucks.IsEmpty()", '   return "NO_TRUCKS"', "end",
                      "var t = tm.GetStartTruckOnLevel()", "if t == null", "   t = trucks[0]", "end",
                      "tm.SetCurrent(t, true)", 'return "SET_CURRENT " + t.owner.ToString()'])


def _ready_fields(reply: str) -> dict[str, str]:
    out = {}
    for line in reply.splitlines()[1:]:
        key, _, value = line.partition(" ")
        out[key] = value
    return out


def wait_scene(session: Any, *, timeout: float, need_truck: bool, clock: "Clock") -> dict[str, Any]:
    """Poll ready_script until a level is loaded (and, for play, a current truck exists)."""
    deadline = clock.monotonic() + timeout
    started, last = clock.monotonic(), ""
    level_at = None
    while True:
        try:
            last = session.exec_ssl(ready_script(), timeout=10)
        except eng.EngineTimeout:
            last = "timeout"
        fields = _ready_fields(last)
        if fields.get("level") and level_at is None:
            level_at = round(clock.monotonic() - started, 1)
        if fields.get("level") and (not need_truck or fields.get("truck") == "1"):
            return {"ok": True, "reply": last, "levelAfter": level_at,
                    "truckAfter": round(clock.monotonic() - started, 1) if need_truck else None}
        if clock.monotonic() >= deadline:
            return {"ok": False, "reply": last, "levelAfter": level_at}
        clock.sleep(1.0)


def _try_ssl(session: Any, script: str, timeout: float = 12.0) -> str:
    try:
        return session.exec_ssl(script, timeout=timeout)
    except eng.EngineError as exc:
        return f"ERROR {type(exc).__name__}: {exc}"


def scene_run(session: Any, folder: Path, data: "eng.SceneLoadData", *, mode: str = "play", via: str = "editor",
              size: tuple[int, int] = (1280, 720), ready_timeout: float = 300.0, settle: float = 5.0,
              force_current: bool = False, clock: "Clock" = None) -> dict[str, Any]:
    """scene_play.md recipe: wait for the first reply (preloading), open the editor connector, share
    viewport 0, LoadScenePlay (or LoadScene), wait for Scene Loaded, a level and (play) a current truck,
    take one screenshot.  Each step's outcome is recorded; a failed wait does not skip the screenshot."""
    clock = clock or Clock()
    out: dict[str, Any] = {"scene": data.as_json(), "mode": mode, "via": via, "steps": []}

    def step(name: str, **info) -> None:
        out["steps"].append({"step": name, "t": round(clock.monotonic() - t0, 1), **info})

    t0 = clock.monotonic()
    first, attempts = first_reply(session, ready_script(), clock=clock)
    step("first-reply", attempts=attempts, reply=first)
    out["adapter"] = _try_ssl(session, adapter_script())
    out["editorBefore"] = _try_ssl(session, editor_state_script())
    if hasattr(session, "snapshot_clients"):
        session.snapshot_clients("clientsBeforeEditor")
    if via == "editor":
        attached = session.attach_editor(eng.GAME_EDITOR)
        step("editor-attached", engineListener=attached.get("engineListener"), manager=attached.get("manager"))
        mark = session.editor_mark()
        session.send_editor(eng.minimize_on_deactivate_message(False))
        session.send_editor(eng.start_frame_sharing_message(0, *size))
        shared = session.wait_editor(eng.is_frame_shared, 60.0, since=mark)
        step("frame-shared", ok=shared is not None, fields=(shared or {}).get("fields"))
        sent = session.send_editor(eng.load_scene_message(data, play=mode == "play"))
        step("load-sent", message="LoadScenePlay" if mode == "play" else "LoadScene", bytes=sent.get("bytes"))
        loaded = session.wait_editor(eng.is_scene_loaded, ready_timeout, since=mark)
        step("scene-loaded", ok=loaded is not None)
    else:
        step("ssl-frame-sharing", reply=_try_ssl(session, ssl_frame_sharing_script(*size)))
        step("ssl-load", reply=_try_ssl(session, ssl_scene_script(data.name, data.res_tag, play=mode == "play"), 30))
    ready = wait_scene(session, timeout=ready_timeout, need_truck=mode == "play", clock=clock)
    step("ready", **ready)
    if mode == "play" and not ready["ok"] and force_current:
        step("force-current", reply=_try_ssl(session, force_current_truck_script()))
        ready = wait_scene(session, timeout=15, need_truck=True, clock=clock)
        step("ready-after-force", **ready)
    out["ready"] = ready["ok"]
    clock.sleep(settle)
    try:
        out["screenshot"] = session.screenshot((folder / "scene.png").resolve(), timeout=30)
    except eng.EngineError as exc:
        out["screenshot"] = {"error": str(exc)}
    step("screenshot", ok="error" not in out["screenshot"])
    out["editorAfter"] = _try_ssl(session, editor_state_script())
    return out


# ------------------------------------------------------------------ analysis
def dominant_frequency(times: Sequence[float], values: Sequence[float], *, fmin: float = 0.3,
                       fmax: float | None = None, oversample: int = 4) -> dict[str, float] | None:
    """Strongest oscillation of a non-uniformly sampled signal: linear resampling onto a uniform grid,
    least-squares detrend, Hann window, zero-padded DFT (stdlib), parabolic peak refinement."""
    pairs = sorted((float(t), float(v)) for t, v in zip(times, values))
    n = len(pairs)
    if n < 8 or pairs[-1][0] - pairs[0][0] <= 0:
        return None
    t0, span = pairs[0][0], pairs[-1][0] - pairs[0][0]
    dt = span / (n - 1)
    grid, j = [], 0
    for k in range(n):
        t = t0 + k * dt
        while j < n - 2 and pairs[j + 1][0] < t:
            j += 1
        (ta, va), (tb, vb) = pairs[j], pairs[j + 1]
        grid.append(va if tb == ta else va + (vb - va) * (t - ta) / (tb - ta))
    xs = [k * dt for k in range(n)]
    mx, my = statistics.fmean(xs), statistics.fmean(grid)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, grid)) / sxx if sxx else 0.0
    window = [0.5 - 0.5 * math.cos(2 * math.pi * k / (n - 1)) for k in range(n)]
    signal = [(y - my - slope * (x - mx)) * w for x, y, w in zip(xs, grid, window)]
    m = n * max(1, oversample)
    nyquist = 0.5 / dt
    top = min(fmax or nyquist, nyquist)
    mags = []
    for b in range(1, m // 2 + 1):
        f = b / (m * dt)
        if f > top:
            break
        re_, im_ = 0.0, 0.0
        step = -2 * math.pi * b / m
        for k, s in enumerate(signal):
            re_ += s * math.cos(step * k)
            im_ += s * math.sin(step * k)
        mags.append((f, math.hypot(re_, im_)))
    candidates = [i for i, (f, _) in enumerate(mags) if f >= fmin]
    if not candidates:
        return None
    i = max(candidates, key=lambda c: mags[c][1])
    f, peak = mags[i]
    if 0 < i < len(mags) - 1:
        a, b, c = mags[i - 1][1], peak, mags[i + 1][1]
        denom = a - 2 * b + c
        if denom:
            # a true parabolic vertex lies within half a bin; a flat or one-sided neighbourhood (a peak on the
            # fmin edge) gave shifts of several bins, even negative frequencies (KGS-25 campaign 2026-10-13)
            f += max(-0.5, min(0.5, 0.5 * (a - c) / denom)) / (m * dt)
    f = max(f, fmin)
    return {"hz": round(f, 4), "amplitude": round(2 * peak / sum(window), 6)}


def parse_extra(path: str | Path) -> list[dict[str, Any]]:
    """Joint (J) and track (T) lines of series.jsonl, per sample time (physics_bench.parse_series reads the rest)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        text = row.get("r") or ""
        if not text.startswith("F "):
            continue
        joints, tracks = [], []
        for ln in text.splitlines():
            p = ln.split()
            if p and p[0] == "J" and len(p) >= 4:
                joints.append({"name": p[1], "angle": float(p[2]), "target": float(p[3])})
            elif p and p[0] == "T" and len(p) >= 3:
                tracks.append({"track": int(p[1]), "sliding": float(p[2])})
        rows.append({"t": row["t"], "joints": joints, "tracks": tracks})
    return rows


def _hull_angles(h: dict[str, Any]) -> tuple[float, float, float]:
    left = pb._cross(h["up"], h["fwd"])
    roll = math.degrees(math.asin(max(-1.0, min(1.0, left[1]))))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, h["fwd"][1]))))
    return roll, pitch, pb._yaw(h)


def write_csvs(samples: list[dict[str, Any]], extra: list[dict[str, Any]], folder: str | Path) -> list[str]:
    """One CSV per probe (engine, bodies, com, wheels, joints, tracks); only those with data."""
    folder = Path(folder)
    tables: dict[str, tuple[list[str], list[list[Any]]]] = {
        "engine": (["t", "frame", "speed", "pedal", "steer", "gear", "rpm", "handbrake", "running", "brakePull"], []),
        "bodies": (["t", "body", "x", "y", "z", "upX", "upY", "upZ", "fwdX", "fwdY", "fwdZ", "rollDeg", "pitchDeg",
                    "yawDeg"], []),
        "com": (["t", "body", "mass", "localX", "localY", "localZ", "worldX", "worldY", "worldZ"], []),
        "wheels": (["t", "wheel", "travel", "x", "y", "z", "ground", "spin", "wheelSpeed", "physicalRadius",
                    "mudDepth", "onTerrain"], []),
        "joints": (["t", "joint", "angle", "target"], []),
        "tracks": (["t", "track", "sliding"], []),
    }
    for s in samples:
        e = s.get("engine") or {}
        tables["engine"][1].append([s["t"], s.get("frame"), s.get("speed"), s.get("pedal"), s.get("steer"),
                                    e.get("gear"), e.get("rpm"), _b(e.get("handbrake")), _b(e.get("running")),
                                    _b(e.get("brakePull"))])
        for name, b in s["bodies"].items():
            if "pos" in b:
                tables["bodies"][1].append([s["t"], name, *b["pos"], *b["up"], *b["fwd"],
                                            *(round(a, 4) for a in _hull_angles(b))])
            if "mass" in b:
                tables["com"][1].append([s["t"], name, b["mass"], *b["comLocal"], *b["comWorld"]])
        for i, w in enumerate(s["wheels"]):
            tables["wheels"][1].append([s["t"], i, w["travel"], *w["pos"], _b(w["ground"]), w.get("spin"),
                                        w.get("wheelSpeed"), w.get("physicalRadius"), w.get("mudDepth"),
                                        _b(w.get("onTerrain"))])
    for row in extra:
        for j in row["joints"]:
            tables["joints"][1].append([row["t"], j["name"], j["angle"], j["target"]])
        for tr in row["tracks"]:
            tables["tracks"][1].append([row["t"], tr["track"], tr["sliding"]])
    written = []
    for name, (header, rows) in tables.items():
        if not rows:
            continue
        with open(folder / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
        written.append(f"{name}.csv")
    return written


def _b(value: Any) -> Any:
    return None if value is None else int(bool(value))


def phase_kinds(steps: list[dict[str, Any]], analysis: dict[str, Any]) -> list[str]:
    kinds, driven = [], False
    for k, step in enumerate(steps):
        if step["phase"] in analysis["pivotPhases"] or (step["pedal"] and abs(step["steer"]) >= analysis["pivotSteer"]):
            kind = "pivot"
        elif step["pedal"]:
            kind = "drive"
        elif driven:
            kind = "settle"
        else:
            kind = "rest"
        driven = driven or bool(step["pedal"])
        kinds.append(kind)
    return kinds


def _phase_index(t: float, steps: list[dict[str, Any]]) -> int:
    index = 0
    for k, step in enumerate(steps):
        if t >= step["at"]:
            index = k
    return index


def settle_time(rows: list[dict[str, Any]], tol: dict[str, float]) -> float | None:
    """Seconds from the phase start until roll, pitch and height stay within tolerance of their final
    value (median of the last second); None when the phase never settles."""
    if len(rows) < 4:
        return None
    end = rows[-1]["t"]
    tail = [r for r in rows if r["t"] >= end - 1.0] or rows[-1:]
    final = {k: statistics.median(r[k] for r in tail) for k in ("roll", "pitch", "y")}
    limits = {"roll": tol["rollDeg"], "pitch": tol["pitchDeg"], "y": tol["heightMm"] / 1000}
    settled_at = None
    for r in rows:
        inside = all(abs(r[k] - final[k]) <= limits[k] for k in limits)
        if not inside:
            settled_at = None
        elif settled_at is None:
            settled_at = r["t"]
    if settled_at is None or settled_at > end - 0.5:
        return None
    return round(settled_at - rows[0]["t"], 3)


def summarise(samples: list[dict[str, Any]], scenario: dict[str, Any],
              extra: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Max roll/pitch in pivots, rest heights, stop hits, settle times, judder frequency (DFT), yaw achieved;
    with ``analysis.articulation`` also track-frame angles and wheel travel in the hull frame."""
    steps = scenario["inputs"]["schedule"]
    analysis = scenario["analysis"]
    vehicle = scenario["vehicle"]
    guessed = pb.guess_bodies(samples)
    hull = vehicle.get("hull") or guessed[0]
    kinds = phase_kinds(steps, analysis)
    rows = []
    for s in samples:
        h = s["bodies"].get(hull)
        if not h or "up" not in h:
            continue
        roll, pitch, yaw = _hull_angles(h)
        rows.append({"t": s["t"], "k": _phase_index(s["t"], steps), "roll": roll, "pitch": pitch, "yaw": yaw,
                     "y": h["pos"][1], "pos": h["pos"], "speed": s.get("speed", 0.0),
                     "travel": [w["travel"] for w in s["wheels"]]})
    if not rows:
        raise pb.BenchError(f"no samples of the hull {hull}")
    by_phase: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_phase.setdefault(r["k"], []).append(r)
    phases = {}
    for k, step in enumerate(steps):
        rs = by_phase.get(k, [])
        if not rs:
            continue
        phases[f"{k:02d}_{step['phase']}"] = {
            "kind": kinds[k], "n": len(rs), "rollMaxAbsDeg": round(max(abs(r["roll"]) for r in rs), 3),
            "pitchMaxAbsDeg": round(max(abs(r["pitch"]) for r in rs), 3),
            "heightRangeMm": round(1000 * (max(r["y"] for r in rs) - min(r["y"] for r in rs)), 1)}
    pivot_rows = [r for r in rows if kinds[r["k"]] == "pivot"]
    rest_rows = [r for r in rows if kinds[r["k"]] == "rest"] or rows[:1]
    rest_height = statistics.median(r["y"] for r in rest_rows)
    wheel_count = max(len(r["travel"]) for r in rows)
    rest = {"hullHeightM": round(rest_height, 4), "samples": len(rest_rows),
            "wheelTravelM": [round(statistics.median(r["travel"][i] for r in rest_rows if len(r["travel"]) > i), 4)
                             for i in range(wheel_count) if any(len(r["travel"]) > i for r in rest_rows)],
            "modelledM": vehicle.get("restHeightModelled")}
    if vehicle.get("restHeightModelled") is not None:
        rest["deltaVsModelledMm"] = round(1000 * (rest_height - vehicle["restHeightModelled"]), 1)
    limits = vehicle.get("suspensionTravel")
    if limits:
        tol = analysis["stopToleranceM"]
        per = []
        for i in range(wheel_count):
            values = [r["travel"][i] for r in rows if len(r["travel"]) > i]
            per.append({"wheel": i, "low": sum(1 for v in values if v <= limits["min"] + tol),
                        "high": sum(1 for v in values if v >= limits["max"] - tol)})
        stops = {"limits": limits, "toleranceM": tol, "perWheel": per,
                 "total": sum(p["low"] + p["high"] for p in per)}
    else:
        stops = {"limits": None, "note": "set vehicle.suspensionTravel {min, max} to count stop hits"}
    settle = {}
    judder = {}
    motion = {}
    for k, step in enumerate(steps):
        rs = by_phase.get(k, [])
        name = f"{k:02d}_{step['phase']}"
        if kinds[k] == "settle":
            settle[name] = settle_time(rs, analysis["settle"])
        if kinds[k] in ("drive", "pivot") and rs:
            entry = {}
            for key, label, scale in (("pitch", "pitch", 1.0), ("roll", "roll", 1.0), ("y", "height", 1000.0)):
                f = dominant_frequency([r["t"] for r in rs], [r[key] * scale for r in rs], fmin=analysis["judderMinHz"])
                entry[label] = f
            judder[name] = entry
            end = (steps[k + 1]["at"] if k + 1 < len(steps) else scenario["durationSeconds"]) + 1.5
            window = [r for r in rows if step["at"] <= r["t"] <= end]
            if len(window) >= 2:
                a, b = window[0], window[-1]
                motion[name] = {"yawDeg": round((b["yaw"] - a["yaw"] + 180) % 360 - 180, 2),
                                "movedM": round(math.dist((a["pos"][0], a["pos"][2]), (b["pos"][0], b["pos"][2])), 3),
                                "vmax": round(max(abs(r["speed"]) for r in window), 3)}
    strongest = None
    for name, entry in judder.items():
        for label in ("pitch", "roll"):
            f = entry.get(label)
            if f and (strongest is None or f["amplitude"] > strongest["amplitudeDeg"]):
                strongest = {"phase": name, "axis": label, "hz": f["hz"], "amplitudeDeg": f["amplitude"]}
    span = rows[-1]["t"] - rows[0]["t"]
    out = {
        "scenario": scenario["name"], "seed": scenario["seed"], "timestepS": scenario["timestep"],
        "hull": hull, "samples": len(rows), "sampleHz": round((len(rows) - 1) / span, 2) if span > 0 else None,
        "maxRollPivotDeg": round(max((abs(r["roll"]) for r in pivot_rows), default=0.0), 3) if pivot_rows else None,
        "maxPitchPivotDeg": round(max((abs(r["pitch"]) for r in pivot_rows), default=0.0), 3) if pivot_rows else None,
        "rest": rest, "stopHits": stops, "settleSeconds": settle, "judder": judder, "judderStrongest": strongest,
        "yaw": motion, "phases": phases}
    if analysis.get("articulation") is not None:
        out["articulation"] = articulation(samples, scenario, hull, extra)
    return out


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def frame_pitch_deg(hull: dict[str, Any], frame: dict[str, Any]) -> float:
    """A track frame's pitch against the hull (deg, nose up positive): its forward axis in the hull's
    forward/up plane."""
    f = frame["fwd"]
    return math.degrees(math.atan2(_dot(f, hull["up"]), _dot(f, hull["fwd"])))


def articulation(samples: list[dict[str, Any]], scenario: dict[str, Any], hull: str,
                 extra: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Track-frame pitch against the hull, wheel heights in the hull frame (travel of rigid idlers and
    sprockets comes from the frame, of road wheels from frame + spring) and the hull's signed roll/pitch
    extremes, per phase, all against the median of the first (rest) phase.  Wheels are named by
    ``vehicle.wheelNames`` (truck.GetWheels() order)."""
    spec = scenario["analysis"]["articulation"] or {}
    steps = scenario["inputs"]["schedule"]
    names = scenario["vehicle"].get("wheelNames") or []
    frames = spec.get("frames") or list(pb.guess_bodies(samples)[1])
    wanted: list[tuple[str, int]] = []
    for w in spec.get("wheels") or []:
        if isinstance(w, int):
            wanted.append((names[w] if w < len(names) else f"wheel{w}", w))
        elif w in names:
            wanted.append((w, names.index(w)))
        else:
            raise pb.BenchError(f"articulation wheel {w} is not in vehicle.wheelNames")
    rows = []
    for s in samples:
        h = s["bodies"].get(hull)
        if not h or "up" not in h:
            continue
        roll, pitch, _ = _hull_angles(h)
        row = {"t": s["t"], "k": _phase_index(s["t"], steps), "roll": roll, "pitch": pitch, "frames": {}, "wheels": {}}
        for f in frames:
            b = s["bodies"].get(f)
            if b and "fwd" in b:
                row["frames"][f] = frame_pitch_deg(h, b)
        for label, i in wanted:
            if i < len(s["wheels"]):
                w = s["wheels"][i]
                row["wheels"][label] = (_dot([a - b for a, b in zip(w["pos"], h["pos"])], h["up"]), w["travel"])
        rows.append(row)
    if not rows:
        return {"frames": frames, "note": "no hull samples"}
    rest_rows = [r for r in rows if r["k"] == 0] or rows[:1]
    base_f = {f: statistics.median(r["frames"][f] for r in rest_rows if f in r["frames"])
              for f in frames if any(f in r["frames"] for r in rest_rows)}
    base_w = {lab: statistics.median(r["wheels"][lab][0] for r in rest_rows if lab in r["wheels"])
              for lab, _ in wanted if any(lab in r["wheels"] for r in rest_rows)}
    base_roll = statistics.median(r["roll"] for r in rest_rows)
    base_pitch = statistics.median(r["pitch"] for r in rest_rows)
    joint_rows: dict[str, list[tuple[float, float]]] = {}
    for row in extra or []:
        for j in row["joints"]:
            if spec.get("joints") and j["name"] in spec["joints"]:
                joint_rows.setdefault(j["name"], []).append((row["t"], j["angle"]))

    def summary_of(rs: list[dict[str, Any]], t0: float | None = None, t1: float | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "rollDeg": [round(min(r["roll"] for r in rs), 3), round(max(r["roll"] for r in rs), 3)],
            "pitchDeg": [round(min(r["pitch"] for r in rs), 3), round(max(r["pitch"] for r in rs), 3)],
            "frameDeg": {}, "wheelMm": {}, "springTravelM": {}}
        for f, b in base_f.items():
            vals = [r["frames"][f] - b for r in rs if f in r["frames"]]
            if vals:
                entry["frameDeg"][f] = [round(min(vals), 3), round(max(vals), 3)]
        for lab, b in base_w.items():
            vals = [r["wheels"][lab] for r in rs if lab in r["wheels"]]
            if vals:
                entry["wheelMm"][lab] = [round(1000 * (min(v[0] for v in vals) - b), 1),
                                         round(1000 * (max(v[0] for v in vals) - b), 1)]
                entry["springTravelM"][lab] = [round(min(v[1] for v in vals), 4), round(max(v[1] for v in vals), 4)]
        if joint_rows:
            entry["jointAngle"] = {}
            for name, vals in joint_rows.items():
                sel = [a for t, a in vals if (t0 is None or t >= t0) and (t1 is None or t < t1)]
                if sel:
                    entry["jointAngle"][name] = [round(min(sel), 5), round(max(sel), 5)]
        return entry

    by_phase: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_phase.setdefault(r["k"], []).append(r)
    phases = {}
    for k, step in enumerate(steps):
        if by_phase.get(k):
            end = steps[k + 1]["at"] if k + 1 < len(steps) else None
            phases[f"{k:02d}_{step['phase']}"] = summary_of(by_phase[k], step["at"], end)
    overall = summary_of(rows)
    peak = {"frameDegMaxAbs": {f: max(abs(v) for v in rng) for f, rng in overall["frameDeg"].items()},
            "wheelMmMaxAbs": {lab: max(abs(v) for v in rng) for lab, rng in overall["wheelMm"].items()},
            "rollFromRestDegMaxAbs": round(max(abs(r["roll"] - base_roll) for r in rows), 3),
            "pitchFromRestDegMaxAbs": round(max(abs(r["pitch"] - base_pitch) for r in rows), 3)}
    return {"frames": frames, "wheels": [lab for lab, _ in wanted],
            "rest": {"rollDeg": round(base_roll, 3), "pitchDeg": round(base_pitch, 3),
                     "frameDeg": {f: round(v, 3) for f, v in base_f.items()},
                     "wheelHeightInHullM": {lab: round(v, 4) for lab, v in base_w.items()}},
            "peak": peak, "overall": overall, "phases": phases}


def analyse(folder: str | Path, scenario: dict[str, Any]) -> dict[str, Any]:
    """CSV per probe and summary.json for a recorded run folder (series.jsonl)."""
    folder = Path(folder)
    samples = pb.parse_series(folder / "series.jsonl")
    extra = parse_extra(folder / "series.jsonl")
    csvs = write_csvs(samples, extra, folder)
    summary = summarise(samples, scenario, extra)
    inputs_file = folder / "inputs.json"
    inputs = json.loads(inputs_file.read_text(encoding="utf-8")) if inputs_file.exists() else []
    summary["inputsApplied"] = f"{sum(1 for i in inputs if i.get('ok'))}/{len(inputs)}"
    summary["csv"] = csvs
    readback_file = folder / "readback.json"
    if readback_file.exists():
        summary["readback"] = json.loads(readback_file.read_text(encoding="utf-8")).get("parsed")
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def compare(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    def delta(key):
        a, b = candidate.get(key), baseline.get(key)
        return None if a is None or b is None else round(a - b, 3)
    return {"maxRollPivotDeg": delta("maxRollPivotDeg"), "maxPitchPivotDeg": delta("maxPitchPivotDeg"),
            "restHeightMm": round(1000 * (candidate["rest"]["hullHeightM"] - baseline["rest"]["hullHeightM"]), 1),
            "stopHits": (candidate["stopHits"].get("total") or 0) - (baseline["stopHits"].get("total") or 0)
            if candidate["stopHits"].get("limits") else None}


# ------------------------------------------------------------------ running
class Clock:
    """Injected time so tests can drive the timetable fast."""
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


def drive(session: Any, scenario: dict[str, Any], folder: Path, clock: Clock = Clock()) -> list[dict[str, Any]]:
    """Apply the timetable while probing at the scenario rate; writes series.jsonl and inputs.json."""
    steps = scenario["inputs"]["schedule"]
    method = scenario["inputs"]["method"]
    probe = probe_script(scenario["probes"]["items"], scenario["vehicle"]["tpl"])
    period = 1.0 / scenario["probes"]["rateHz"]
    log: list[dict[str, Any]] = []
    t0 = clock.monotonic()
    next_step, next_probe, i = 0, 0.0, 0
    with open(folder / "series.jsonl", "w", encoding="utf-8") as series:
        while True:
            t = clock.monotonic() - t0
            if t >= scenario["durationSeconds"]:
                break
            if next_step < len(steps) and t >= steps[next_step]["at"]:
                step = steps[next_step]
                entry = {"step": next_step, "phase": step["phase"], "at": step["at"], "t": round(t, 3), "ok": False}
                for attempt in range(3):  # the editor bench saw occasional registration timeouts
                    try:
                        reply = session.exec_ssl(input_script(step, method), timeout=5)
                        entry.update(ok=reply.startswith("ROAMER_INPUT_APPLIED"), reply=reply[:400],
                                     attempts=attempt + 1)
                        if entry["ok"]:
                            break
                    except eng.EngineTimeout as exc:
                        entry.update(error=str(exc), attempts=attempt + 1)
                log.append(entry)
                next_step += 1
                continue
            if t >= next_probe:
                sent = t
                try:
                    reply = session.exec_ssl(probe, timeout=5)
                    series.write(json.dumps({"i": i, "t": round(sent, 4), "utc": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "r": reply}) + "\n")
                except eng.EngineTimeout:
                    series.write(json.dumps({"i": i, "t": round(sent, 4), "missing": True}) + "\n")
                i += 1
                next_probe = sent + period
                continue
            wait = min(next_probe - t, (steps[next_step]["at"] - t) if next_step < len(steps) else period)
            clock.sleep(max(0.001, min(wait, 0.05)))
    try:
        reply = session.exec_ssl(input_script(None, method), timeout=5)
        log.append({"step": "release", "ok": reply.startswith("ROAMER_INPUT_APPLIED"), "reply": reply[:400]})
    except eng.EngineError as exc:
        log.append({"step": "release", "ok": False, "error": str(exc)})
    (folder / "inputs.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    return log


def wait_ready(session: Any, scenario: dict[str, Any], clock: Clock = Clock()) -> str:
    """Until a current truck answers (or the scene timeout), then the settle delay."""
    deadline = clock.monotonic() + scenario["scene"]["readyTimeoutSeconds"]
    reply = ""
    while clock.monotonic() < deadline:
        reply = session.exec_ssl(ready_script(), timeout=10)
        if "\ntruck 1" in reply:
            clock.sleep(scenario["scene"]["settleSeconds"])
            return reply
        clock.sleep(1.0)
    raise eng.EngineTimeout(f"no current truck within {scenario['scene']['readyTimeoutSeconds']:.0f} s; last: {reply!r}")


def capture(session: Any, scenario: dict[str, Any], folder: Path, clock: Clock = Clock()) -> list[dict[str, Any]]:
    """Every state x camera -> <folder>/<state>__<camera>.png (absolute paths, complete PNGs)."""
    spec = scenario["capture"]
    if not spec:
        raise ScenarioError("the scenario has no capture section")
    hull = scenario["vehicle"].get("hull") or "BoneChassis_cdt"
    shots = []
    for state in spec["states"]:
        script, grades = state_script(state)
        reply = session.exec_ssl(script, timeout=10)
        clock.sleep(spec["settleSeconds"])
        for camera in spec["cameras"]:
            cam_reply = session.exec_ssl(camera_script(camera, hull), timeout=10)
            clock.sleep(0.5)
            path = (folder / f"{state['name']}__{camera['name']}.png").resolve()
            row = {"state": state["name"], "camera": camera["name"], "stateReply": reply,
                   "cameraReply": cam_reply, "grades": grades}
            try:
                row.update(session.screenshot(path))
            except eng.EngineError as exc:
                row["error"] = str(exc)
            shots.append(row)
    (folder / "capture.json").write_text(json.dumps(shots, indent=1), encoding="utf-8")
    return shots


def scripts_for(scenario: dict[str, Any]) -> dict[str, Any]:
    steps = scenario["inputs"]["schedule"]
    out = {"ready": ready_script(), "probe": probe_script(scenario["probes"]["items"], scenario["vehicle"]["tpl"]),
           "inputs": {f"{k:02d}_{s['phase']}": input_script(s, scenario["inputs"]["method"]) for k, s in enumerate(steps)},
           "release": input_script(None, scenario["inputs"]["method"])}
    if scenario["scene"]["loadSsl"]:
        out["loadScene"] = load_scene_script(scenario["scene"]["loadSsl"])
    if scenario["probes"].get("readback"):
        out["readback"] = readback_scripts()
    if scenario["capture"]:
        hull = scenario["vehicle"].get("hull") or "BoneChassis_cdt"
        out["capture"] = {"states": {s["name"]: state_script(s)[0] for s in scenario["capture"]["states"]},
                          "cameras": {c["name"]: camera_script(c, hull) for c in scenario["capture"]["cameras"]}}
    return out


def _session(layout: eng.RunLayout, scenario: dict[str, Any], args: argparse.Namespace,
             factory: Callable[..., Any]) -> Any:
    return factory(layout, game_root=args.game_root, sdk_editor_dir=args.sdk_editor_dir, adapter_id=args.adapter_id,
                   timestep=scenario["timestep"], level=scenario["scene"]["level"],
                   wall_clock=scenario["wallClockSeconds"], startup_timeout=scenario["startupTimeoutSeconds"],
                   extra_sets=list(getattr(args, "extra_sets", None) or []))


def _scene_file_data(scenario: dict[str, Any], args: argparse.Namespace) -> "eng.SceneLoadData | None":
    """``scene.file`` (relative to mods_source): load it with the editor's LoadScenePlay recipe
    (scene_play.md; scene_001 2026-10-13 loaded gd11_bench and made the truck current headless)."""
    rel = scenario["scene"].get("file")
    if not rel:
        return None
    if args.strategy == "project-copy":
        if not args.project:
            raise ScenarioError("scene.file with --strategy project-copy needs --project <folder with mods_source>")
        source = Path(args.project) / "mods_source"
    else:
        source = eng.project_context.game_root(args.game_root) / "root" / "mods_source"
    return eng.scene_load_data(rel, source, ps="file")


def run_one(label: str, pak: str | None, scenario: dict[str, Any], args: argparse.Namespace, *,
            factory: Callable[..., Any] = eng.EngineSession, clock: Clock = Clock(), mode: str = "run") -> dict[str, Any]:
    out = Path(args.out).resolve() / label
    scene_file = _scene_file_data(scenario, args) if mode in ("run", "capture") else None
    if scene_file is not None and eng.START_AT_TRUCK_ON_SCENE not in (getattr(args, "extra_sets", None) or []):
        args.extra_sets = [*(getattr(args, "extra_sets", None) or []), eng.START_AT_TRUCK_ON_SCENE]
    layout = eng.plan_layout(out / "root", strategy=args.strategy, pak=pak, game_root=args.game_root)
    session = _session(layout, scenario, args, factory)
    if args.dry_run:
        return {"label": label, "folder": str(out), "pak": pak, "session": session.plan()}
    out.mkdir(parents=True, exist_ok=False)
    eng.prepare_layout(layout, pak=pak, project=args.project, game_root=args.game_root)
    if scenario["spawn"]["method"] == "scene":
        if layout.strategy != "project-copy":
            raise ScenarioError("spawn.method scene needs --strategy project-copy (it edits the private scene copy)")
        scene = layout.mods_source / scenario["spawn"]["scene"]
        text = pb.place_vehicle(scene.read_text(encoding="utf-8"), scenario["spawn"]["vehicle"],
                                scenario["spawn"]["position"])
        for box in scenario["spawn"]["boxes"]:
            text = pb.add_box(text, box["name"], box["position"], box["scale"], box["yaw"])
        scene.unlink()  # the private copy may be a hard link; never write through it
        scene.write_text(text, encoding="utf-8", newline="")
    if scene_file is not None and layout.strategy == "project-copy":
        # LoadScenePlay sends the scene text itself as psOverrides: send the private copy (with the spawn
        # position and boxes), not the source project's file (KGS-25 campaign 2026-10-13)
        scene_file = eng.scene_load_data(scenario["scene"]["file"], layout.mods_source, ps="file")
    meta = {"label": label, "pak": pak, "scenario": scenario, "ownerApproved": args.owner_approved,
            "startedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "run.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    result: dict[str, Any] = {"label": label, "folder": str(out)}
    try:
        with session:
            session.start(owner_approved=args.owner_approved)
            if scenario["scene"]["loadSsl"]:
                result["loadScene"] = session.exec_ssl(load_scene_script(scenario["scene"]["loadSsl"]), timeout=30)
            if mode == "smoke":
                result.update(smoke(session, out, clock))
            elif mode == "scene":
                result.update(scene_run(session, out, args.scene_data, mode=args.mode, via=args.via,
                                        ready_timeout=args.ready_timeout, settle=args.settle,
                                        force_current=args.force_current_truck, clock=clock))
                (out / "scene.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
            else:
                if scene_file is not None:
                    result["scene"] = scene_run(session, out, scene_file, mode="play", via="editor",
                                                ready_timeout=scenario["scene"]["readyTimeoutSeconds"],
                                                settle=scenario["scene"]["settleSeconds"], clock=clock)
                result["ready"] = wait_ready(session, scenario, clock)
                if scenario["probes"].get("readback"):
                    result["readback"] = readback(session, out)
                if mode == "capture":
                    result["capture"] = capture(session, scenario, out, clock)
                else:
                    result["inputs"] = drive(session, scenario, out, clock)
    finally:
        record = getattr(session, "record", {})
        (out / "session.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
        if getattr(args, "prune_copy", False) and layout.strategy == "project-copy" and layout.mods_source.is_dir():
            shutil.rmtree(layout.mods_source, ignore_errors=True)  # the private project copy (GBs); logs stay
            result["prunedCopy"] = str(layout.mods_source)
    if mode == "run":
        result["summary"] = analyse(out, scenario)
    return result


FIRST_REPLY_BUDGET = 180.0   # s; smoke 2026-10-13: the listener registers ~8 s in, during "Init hardware",
                             # before the main loop that answers scripts runs


def first_reply(session: Any, script: str, budget: float = FIRST_REPLY_BUDGET, attempt: float = 10.0,
                clock: Clock = Clock()) -> tuple[str, int]:
    """Send a read-only script until the engine answers; returns (reply, attempts)."""
    started, attempts = clock.monotonic(), 0
    while True:
        attempts += 1
        try:
            return session.exec_ssl(script, timeout=attempt), attempts
        except eng.EngineTimeout:
            if clock.monotonic() - started + attempt > budget:
                raise


def smoke(session: Any, folder: Path, clock: Clock = Clock()) -> dict[str, Any]:
    """Proposed first live run: read-only replies twice (frames must advance), one screenshot."""
    first, attempts = first_reply(session, ready_script(), clock=clock)
    clock.sleep(2.0)
    second = session.exec_ssl(ready_script(), timeout=12)
    frames = [int(m.group(1)) for m in (re.search(r"frame (\d+)", r) for r in (first, second)) if m]
    shot: dict[str, Any]
    try:
        shot = session.screenshot((folder / "smoke.png").resolve(), timeout=30)
    except eng.EngineError as exc:
        shot = {"error": str(exc)}
    return {"replies": [first, second], "firstReplyAttempts": attempts, "framesAdvance": len(frames) == 2 and frames[1] > frames[0],
            "screenshot": shot}


# ------------------------------------------------------------------ CLI
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadcraft.bench_headless", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "capture", "smoke", "scene"):
        p = sub.add_parser(name)
        if name in ("run", "capture"):
            p.add_argument("scenario")
        if name == "scene":
            p.add_argument("--scene", default=DEFAULT_SCENE,
                           help="scene .scn relative to mods_source (the --project copy, else <game>/root/mods_source)")
            p.add_argument("--mode", choices=("play", "edit"), default="play")
            p.add_argument("--via", choices=("editor", "ssl"), default="editor",
                           help="editor: IntegrationStudio's Game editor messages (default); ssl: ExecSsl-only fallback")
            p.add_argument("--scene-ps", dest="scene_ps", choices=("file", "empty"), default="file")
            p.add_argument("--ready-timeout", dest="ready_timeout", type=float, default=300.0)
            p.add_argument("--settle", type=float, default=5.0)
            p.add_argument("--force-current-truck", dest="force_current_truck", action="store_true",
                           help="if no current truck appears, SetCurrent the start (or first) truck (Inferred)")
            p.add_argument("--no-start-at-truck", dest="start_at_truck", action="store_false",
                           help="omit the DbgVar Game/Startup/Start at truck on scene")
            p.add_argument("--wall-clock", dest="wall_clock", type=float, default=900.0)
        p.add_argument("--pak", help="candidate .pak (copied into the run's private mods folder)")
        if name == "run":
            p.add_argument("--baseline", help="baseline .pak, run the same way after the candidate")
        p.add_argument("--out", required=True, help="new output folder (absolute or relative; must not exist)")
        p.add_argument("--owner-approved", dest="owner_approved",
                       help="the owner's go-ahead for this engine run (who/when/why); without it: dry run")
        p.add_argument("--dry-run", action="store_true", help="print commands, files and scripts; launch nothing")
        p.add_argument("--strategy", choices=eng.STRATEGIES, default="moddirs")
        p.add_argument("--project", help="mod project folder holding mods_source (project-copy strategy)")
        p.add_argument("--game-root", default=None, help="default: ROADCRAFT_GAME_ROOT, ROADCRAFT_ROOT, machine.json sdkRoot, Steam")
        p.add_argument("--sdk-editor-dir", default=None, help="<game>/tools/bin/ModEditor (Saber.ConsoleTre.dll)")
        p.add_argument("--adapter-id", type=int, default=0)
        p.add_argument("--prune-copy", dest="prune_copy", action="store_true",
                       help="project-copy: delete the run's private mods_source copy after the run (logs, CSVs stay)")
    a = sub.add_parser("analyse")
    a.add_argument("folder")
    a.add_argument("--scenario", required=True)
    return parser


SMOKE_SCENARIO = {"name": "smoke", "durationSeconds": 30, "wallClockSeconds": 300, "startupTimeoutSeconds": 240,
                  "inputs": {"schedule": [{"at": 0, "phase": "idle"}]}}
DEFAULT_SCENE = "xscenes/mods/example/example.scn"   # root/.project xgine-default-scene-path


def _scene_setup(args: argparse.Namespace) -> dict[str, Any]:
    """Scene command: the scenario shell, the scene's load data (read from the source mods_source; the
    private copy holds the same files) and the play-mode DbgVar."""
    if args.strategy == "project-copy":
        if not args.project:
            raise ScenarioError("--strategy project-copy needs --project <folder with mods_source>")
        source = Path(args.project) / "mods_source"
    else:
        source = eng.project_context.game_root(args.game_root) / "root" / "mods_source"
    args.scene_data = eng.scene_load_data(args.scene, source, ps=args.scene_ps)
    args.extra_sets = [eng.START_AT_TRUCK_ON_SCENE] if args.mode == "play" and args.start_at_truck else []
    scenario = load_scenario({**SMOKE_SCENARIO, "name": "scene", "wallClockSeconds": args.wall_clock})
    w, h = 1280, 720
    messages = [eng.minimize_on_deactivate_message(False), eng.start_frame_sharing_message(0, w, h),
                eng.load_scene_message(args.scene_data, play=args.mode == "play")]
    plan = {"scene": args.scene_data.as_json(), "modsSource": str(source), "mode": args.mode, "via": args.via,
            "connector": eng.GAME_EDITOR,
            "messages": [{"name": m[0], "fields": [(k, v if not isinstance(v, str) or len(v) <= 120 else
                                                   f"<{len(v.encode('utf-8'))} bytes>") for k, v in m[1]]}
                         for m in messages] if args.via == "editor" else [],
            "scripts": {"ready": ready_script(), "adapter": adapter_script(), "editorState": editor_state_script(),
                        "screenshot": eng.screenshot_script(Path(args.out).resolve() / "candidate" / "scene.png")}}
    if args.via == "ssl":
        plan["scripts"]["frameSharing"] = ssl_frame_sharing_script(w, h)
        plan["scripts"]["load"] = ssl_scene_script(args.scene_data.name, args.scene_data.res_tag,
                                                   play=args.mode == "play")
    if args.force_current_truck:
        plan["scripts"]["forceCurrent"] = force_current_truck_script()
    return {"scenario": scenario, "plan": plan}


def main(argv: Sequence[str] | None = None, *, factory: Callable[..., Any] = eng.EngineSession,
         clock: Clock = Clock(), stdout=None) -> int:
    stdout = stdout or sys.stdout
    args = _parser().parse_args(argv)
    try:
        if args.command == "analyse":
            print(json.dumps(analyse(args.folder, load_scenario(args.scenario)), indent=1), file=stdout)
            return 0
        scene_plan = None
        if args.command == "scene":
            setup = _scene_setup(args)
            scenario, scene_plan = setup["scenario"], setup["plan"]
        else:
            scenario = load_scenario(SMOKE_SCENARIO if args.command == "smoke" else args.scenario)
        if args.command in ("run", "capture") and not args.pak and args.strategy == "moddirs":
            raise ScenarioError("--pak is required (or --strategy project-copy --project <folder>)")
        if args.command == "capture" and not scenario["capture"]:
            raise ScenarioError("the scenario has no capture section")
        reason = None
        if not (args.owner_approved or "").strip():
            args.dry_run, reason = True, "no --owner-approved: dry run only (engine runs need the owner's go-ahead)"
        elif args.dry_run:
            reason = "--dry-run"
        labels = [("candidate", args.pak)]
        if getattr(args, "baseline", None):
            labels.append(("baseline", args.baseline))
        mode = args.command
        if args.dry_run:
            plan = {"dryRun": True, "reason": reason, "command": mode, "scenario": scenario,
                    "runs": [run_one(label, pak, scenario, args, factory=factory, clock=clock, mode=mode)
                             for label, pak in labels],
                    "scripts": (scene_plan["scripts"] if mode == "scene" else scripts_for(scenario) if mode != "smoke"
                                else {"ready": ready_script(),
                                      "screenshot": eng.screenshot_script(Path(args.out).resolve()
                                                                          / "candidate" / "smoke.png")}),
                    "outputs": ["run.json", "session.json", "series.jsonl", "inputs.json", "<probe>.csv",
                                "summary.json"] if mode == "run" else
                    (["capture.json", "<state>__<camera>.png"] if mode == "capture" else
                     ["scene.png", "scene.json", "session.json", "run.json"] if mode == "scene" else ["smoke.png", "session.json"])}
            if scene_plan:
                plan["scenePlan"] = {k: v for k, v in scene_plan.items() if k != "scripts"}
            print(json.dumps(plan, indent=1, default=str), file=stdout)
            return 0
        results = [run_one(label, pak, scenario, args, factory=factory, clock=clock, mode=mode) for label, pak in labels]
        report: dict[str, Any] = {"command": mode, "runs": results}
        if mode == "run" and len(results) == 2:
            report["comparison"] = compare(results[0]["summary"], results[1]["summary"])
            (Path(args.out) / "comparison.json").write_text(json.dumps(report["comparison"], indent=1), encoding="utf-8")
        print(json.dumps(report, indent=1, default=str), file=stdout)
        return 0
    except (ScenarioError, eng.EngineError, pb.BenchError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=stdout)
        return 2


if __name__ == "__main__":
    sys.exit(main())
