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
    if not isinstance(scene, dict) or set(scene) - {"level", "loadSsl", "settleSeconds", "readyTimeoutSeconds"}:
        raise ScenarioError("scene must be {level, loadSsl, settleSeconds, readyTimeoutSeconds}")
    for key in ("level", "loadSsl"):
        if scene.get(key) is not None and (not isinstance(scene[key], str) or not scene[key].isprintable()
                                           or '"' in scene[key] or "\\" in scene[key]):
            raise ScenarioError(f"scene.{key} must be a plain string")
    out["scene"] = {"level": scene.get("level"), "loadSsl": scene.get("loadSsl"),
                    "settleSeconds": _number(scene.get("settleSeconds", 5), "scene.settleSeconds", 0, 600),
                    "readyTimeoutSeconds": _number(scene.get("readyTimeoutSeconds", 120),
                                                   "scene.readyTimeoutSeconds", 1, 3600)}
    vehicle = data.get("vehicle") or {}
    allowed = {"tpl", "hull", "frames", "restHeightModelled", "suspensionTravel"}
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
    out["vehicle"] = {"tpl": tpl, "hull": hull, "frames": list(vehicle.get("frames") or []) or None,
                      "restHeightModelled": None if vehicle.get("restHeightModelled") is None else
                      _number(vehicle["restHeightModelled"], "vehicle.restHeightModelled", -1000, 10000),
                      "suspensionTravel": travel}
    spawn = data.get("spawn") or {"method": "none"}
    if not isinstance(spawn, dict) or set(spawn) - {"method", "scene", "vehicle", "position"}:
        raise ScenarioError("spawn must be {method, scene, vehicle, position}")
    method = _choice(spawn.get("method", "none"), "spawn.method", ("none", "scene"))
    if method == "scene":
        position = spawn.get("position")
        if not (isinstance(position, list) and len(position) == 3):
            raise ScenarioError("spawn.position must be [x, y, z]")
        if not isinstance(spawn.get("scene"), str) or not isinstance(spawn.get("vehicle"), str):
            raise ScenarioError("spawn.scene (relative to mods_source) and spawn.vehicle are required")
        spawn = {"method": method, "scene": spawn["scene"], "vehicle": spawn["vehicle"],
                 "position": [_number(v, "spawn.position", -1e5, 1e5) for v in position]}
    else:
        spawn = {"method": "none"}
    out["spawn"] = spawn
    probes = data.get("probes") or {}
    if not isinstance(probes, dict) or set(probes) - {"rateHz", "items"}:
        raise ScenarioError("probes must be {rateHz, items}")
    items = probes.get("items", ["engine", "bodies", "com", "wheels"])
    if not isinstance(items, list) or set(items) - set(PROBE_ITEMS) or not items:
        raise ScenarioError(f"probes.items must be a non-empty subset of {list(PROBE_ITEMS)}")
    out["probes"] = {"rateHz": _number(probes.get("rateHz", 10), "probes.rateHz", 0.1, 60),
                     "items": [i for i in PROBE_ITEMS if i in items]}
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
    }
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
    return f"LoadSceneRes({eng.ssl_string(res_tag)})"  # Inferred: SSL name in the exe strings, not run


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
            f += 0.5 * (a - c) / denom / (m * dt)
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


def summarise(samples: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any]:
    """Max roll/pitch in pivots, rest heights, stop hits, settle times, judder frequency (DFT), yaw achieved."""
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
    return {
        "scenario": scenario["name"], "seed": scenario["seed"], "timestepS": scenario["timestep"],
        "hull": hull, "samples": len(rows), "sampleHz": round((len(rows) - 1) / span, 2) if span > 0 else None,
        "maxRollPivotDeg": round(max((abs(r["roll"]) for r in pivot_rows), default=0.0), 3) if pivot_rows else None,
        "maxPitchPivotDeg": round(max((abs(r["pitch"]) for r in pivot_rows), default=0.0), 3) if pivot_rows else None,
        "rest": rest, "stopHits": stops, "settleSeconds": settle, "judder": judder, "judderStrongest": strongest,
        "yaw": motion, "phases": phases}


def analyse(folder: str | Path, scenario: dict[str, Any]) -> dict[str, Any]:
    """CSV per probe and summary.json for a recorded run folder (series.jsonl)."""
    folder = Path(folder)
    samples = pb.parse_series(folder / "series.jsonl")
    extra = parse_extra(folder / "series.jsonl")
    csvs = write_csvs(samples, extra, folder)
    summary = summarise(samples, scenario)
    inputs_file = folder / "inputs.json"
    inputs = json.loads(inputs_file.read_text(encoding="utf-8")) if inputs_file.exists() else []
    summary["inputsApplied"] = f"{sum(1 for i in inputs if i.get('ok'))}/{len(inputs)}"
    summary["csv"] = csvs
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
    if scenario["capture"]:
        hull = scenario["vehicle"].get("hull") or "BoneChassis_cdt"
        out["capture"] = {"states": {s["name"]: state_script(s)[0] for s in scenario["capture"]["states"]},
                          "cameras": {c["name"]: camera_script(c, hull) for c in scenario["capture"]["cameras"]}}
    return out


def _session(layout: eng.RunLayout, scenario: dict[str, Any], args: argparse.Namespace,
             factory: Callable[..., Any]) -> Any:
    return factory(layout, game_root=args.game_root, sdk_editor_dir=args.sdk_editor_dir, adapter_id=args.adapter_id,
                   timestep=scenario["timestep"], level=scenario["scene"]["level"],
                   wall_clock=scenario["wallClockSeconds"], startup_timeout=scenario["startupTimeoutSeconds"])


def run_one(label: str, pak: str | None, scenario: dict[str, Any], args: argparse.Namespace, *,
            factory: Callable[..., Any] = eng.EngineSession, clock: Clock = Clock(), mode: str = "run") -> dict[str, Any]:
    out = Path(args.out).resolve() / label
    layout = eng.plan_layout(out / "root", strategy=args.strategy, pak=pak, game_root=args.game_root)
    session = _session(layout, scenario, args, factory)
    if args.dry_run:
        return {"label": label, "folder": str(out), "pak": pak, "session": session.plan()}
    out.mkdir(parents=True, exist_ok=False)
    eng.prepare_layout(layout, pak=pak, project=args.project)
    if scenario["spawn"]["method"] == "scene":
        if layout.strategy != "project-copy":
            raise ScenarioError("spawn.method scene needs --strategy project-copy (it edits the private scene copy)")
        scene = layout.mods_source / scenario["spawn"]["scene"]
        scene.write_text(pb.place_vehicle(scene.read_text(encoding="utf-8"), scenario["spawn"]["vehicle"],
                                          scenario["spawn"]["position"]), encoding="utf-8")
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
            else:
                result["ready"] = wait_ready(session, scenario, clock)
                if mode == "capture":
                    result["capture"] = capture(session, scenario, out, clock)
                else:
                    result["inputs"] = drive(session, scenario, out, clock)
    finally:
        record = getattr(session, "record", {})
        (out / "session.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
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
    for name in ("run", "capture", "smoke"):
        p = sub.add_parser(name)
        if name != "smoke":
            p.add_argument("scenario")
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
    a = sub.add_parser("analyse")
    a.add_argument("folder")
    a.add_argument("--scenario", required=True)
    return parser


SMOKE_SCENARIO = {"name": "smoke", "durationSeconds": 30, "wallClockSeconds": 300, "startupTimeoutSeconds": 240,
                  "inputs": {"schedule": [{"at": 0, "phase": "idle"}]}}


def main(argv: Sequence[str] | None = None, *, factory: Callable[..., Any] = eng.EngineSession,
         clock: Clock = Clock(), stdout=None) -> int:
    stdout = stdout or sys.stdout
    args = _parser().parse_args(argv)
    try:
        if args.command == "analyse":
            print(json.dumps(analyse(args.folder, load_scenario(args.scenario)), indent=1), file=stdout)
            return 0
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
                    "scripts": scripts_for(scenario) if mode != "smoke" else {"ready": ready_script(),
                                                                              "screenshot": eng.screenshot_script(
                                                                                  Path(args.out).resolve()
                                                                                  / "candidate" / "smoke.png")},
                    "outputs": ["run.json", "session.json", "series.jsonl", "inputs.json", "<probe>.csv",
                                "summary.json"] if mode == "run" else
                    (["capture.json", "<state>__<camera>.png"] if mode == "capture" else ["smoke.png", "session.json"])}
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
