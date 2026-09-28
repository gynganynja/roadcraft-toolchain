"""Capture the staged D11 cab from the native editor with a reversible PAK swap.

Run this only after the candidate project and package have been built and audited.
The script pins the current combined PAK, temporarily loads the candidate,
captures the requested cab variants and views, then restores the original PAK
in ``finally``. The default is the full three-variant, fifteen-view review.
It reuses the proven editor controls from the earlier D11 interior survey.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
PROJECT = HERE / "p"
NATIVE = HERE / "native"
RUNS = NATIVE / "runs"
LOCK = NATIVE / "candidate_capture.lock.json"
LIVE = WORKSPACE.parent / "root/mods/cat_d11t.pak"
EXPECTED_BASE_SHA = "3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16"
PACKAGE_RECEIPT = HERE / "build/package_receipt.json"
PROTOTYPE_RECEIPT = HERE / "build/prototype/package_receipt.json"
OLD_INTERIOR = WORKSPACE / "D11_Interior_Repair_20260926"
SCENES = {
    "maroon": "d11t_maroon_validation/d11t_maroon_validation.scn",
    "nearnew": "d11t_nearnew_validation/d11t_nearnew_validation.scn",
    "worn": "d11t_worn_validation/d11t_worn_validation.scn",
}
MODEL_BY_VARIANT = {"maroon": "cat_d11t_v2", "nearnew": "cat_d11t",
                    "worn": "cat_d11t_v3"}
VIEWS = (
    "front_seat", "front_down",
    "right", "right_down", "right_panel_detail", "right_outer_low",
    "left", "left_down", "left_panel_detail",
    "rear", "rear_down", "rear_right_detail", "rear_left_detail",
    "overhead", "overhead_rear",
)
EXTRA_VIEWS = {
    # Optional close proof for the source TEMP/FAN legends at the far LH edge.
    "left_hvac_detail": ((0.05, 0.37, -0.14), (0.38, 1.14, -0.72)),
}
INTERIOR_NODES = (
    "D11_InteriorV1_vis", "D11_InteriorV1_vis_LOD0",
    "D11_InteriorV1_vis_LOD1", "D11_InteriorV1_vis_LOD2",
)
EDITOR_CONFIG_NAMES = (
    "editor.cfg", "previewer_tpl.cfg", "thumbnails_tpl.cfg",
    "thumbnails_prefab.cfg", "terraforming_converter.cfg",
)


def guard(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def copy_exclusive(source: Path, target: Path) -> None:
    """Copy a transaction artifact without replacing an existing file."""
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=8 * 1024 * 1024)
        output_stream.flush()
        os.fsync(output_stream.fileno())


def old_helpers():
    sys.path.insert(0, str(OLD_INTERIOR))
    import capture_interior as base
    import capture_cab_survey as survey
    base.PROJECT = PROJECT
    base.RUNS = RUNS
    base.LOCK = LOCK
    base.EXPECTED_LIVE = EXPECTED_BASE_SHA
    base.h.PROJECT = PROJECT
    survey.VIEWS["front_seat"] = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    survey.VIEWS["front_down"] = ((0.0, 0.0, 0.0), (0.7, 0.0, -0.4))
    survey.VIEWS.update(EXTRA_VIEWS)
    return base, survey


def recover(base) -> None:
    guard(LOCK.is_file(), "There is no interrupted candidate capture to recover")
    state = json.loads(LOCK.read_text(encoding="utf-8"))
    run_id = state["runId"]
    backup = Path(state["backup"])
    candidate_sha = state["candidateSha256"]
    guard(state["baselineSha256"] == EXPECTED_BASE_SHA, "Recovery baseline pin mismatch")
    guard(backup.parent.resolve() == NATIVE.resolve() and
          backup.name == f"cat_d11t_before_{EXPECTED_BASE_SHA[:12]}_{run_id}.pak",
          "Recovery backup is outside the expected workspace path")
    guard(sha(backup) == EXPECTED_BASE_SHA, "Recovery backup hash mismatch")
    guard(not base.processes() and not base.runner.LOCK.exists(),
          "Close RoadCraft and the Mod Editor before recovery")
    live_sha = sha(LIVE)
    guard(live_sha in (EXPECTED_BASE_SHA, candidate_sha),
          "Installed package changed; refusing to overwrite an unrelated version")
    if live_sha == candidate_sha:
        stage = LIVE.with_name(f"cat_d11t.restore-{run_id}.tmp")
        guard(not stage.exists(), "Recovery staging path already exists")
        try:
            shutil.copy2(backup, stage)
            guard(sha(stage) == EXPECTED_BASE_SHA, "Recovery staging hash mismatch")
            guard(not base.processes() and sha(LIVE) == candidate_sha,
                  "Installed package or editor state changed during recovery")
            os.replace(stage, LIVE)
        finally:
            if stage.exists():
                stage.unlink()
    guard(sha(LIVE) == EXPECTED_BASE_SHA, "Installed baseline failed recovery hash check")
    receipt = {"status": "BASELINE_RECOVERED", "runId": run_id,
               "recoveredUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "installedPackage": str(LIVE), "restoredSha256": EXPECTED_BASE_SHA,
               "backup": str(backup)}
    save(NATIVE / f"candidate_recovery_{run_id}.json", receipt)
    LOCK.unlink()
    print(json.dumps(receipt, indent=2))


def project_pins(project: Path) -> dict[str, str]:
    files = [project / ".project"]
    files.extend(project / "config" / name for name in EDITOR_CONFIG_NAMES)
    source = project / "mods_source"
    for model in ("cat_d11t", "cat_d11t_v2", "cat_d11t_v3"):
        asset = source / f"models/mods/{model}.tpl.asset"
        files.extend((asset / "export.usf", asset / "tpl" / f"{model}.tpl",
                      asset / "tpl" / f"{model}.tpl_data",
                      asset / "tpl" / "obj_list.json"))
    for scene in SCENES.values():
        files.append(source / "xscenes/mods" / scene)
    for folder in ("material_instances", "pct", "td", "textures"):
        files.extend(path for path in (source / folder).glob("mod_cat_d11t_*") if path.is_file())
    guard(all(path.is_file() for path in files), "Candidate project lacks a compiled model or validation scene")
    return {path.relative_to(project).as_posix(): sha(path) for path in files}


def editor_mount(project: Path) -> dict:
    """Check the copied editor profile's effective wrapped path values."""
    path = project / "config/editor.cfg"
    guard(path.is_file() and not path.is_symlink(), "Staged editor.cfg is missing")
    raw = path.read_bytes()
    old = b"D11_Terrain_Fix_20260927/p"
    new = b"D11_Interior_AAA_20260928/p"
    guard(raw.count(old) == 0 and raw.count(new) == 2,
          "Staged editor.cfg still mounts the previous project")
    content = raw.decode("utf-8")
    # The editor splits paths at the space in "Roadcraft Development Package".
    # YAML folds those continuation lines into one effective path value.
    fields = {}
    for match in re.finditer(
            r"(?m)^  (ModsSourceLocal|ProjectPath): ([^\r\n]*(?:\r?\n    [^\r\n]*)*)",
            content):
        key = match.group(1)
        guard(key not in fields, f"Repeated editor.cfg path field: {key}")
        fields[key] = " ".join(line.strip() for line in match.group(2).splitlines())
    guard(set(fields) == {"ModsSourceLocal", "ProjectPath"},
          "Editor config lacks either project mount path")
    root = project.resolve(strict=True).as_posix()
    guard(fields["ModsSourceLocal"] == root + "/mods_source"
          and fields["ProjectPath"] == root + "/.project",
          "Editor config mounts a source tree other than the staged D11 interior")
    return {"editorConfig": str(path), "editorConfigSha256": sha(path),
            "modsSourceLocal": fields["ModsSourceLocal"],
            "projectPath": fields["ProjectPath"]}


def runtime_resource_mount(stdout: str) -> dict:
    """Require the engine's own resource layer to mount this project's source."""
    roots = []
    for line in stdout.splitlines():
        if "res/init" in line and "layer root:" in line:
            roots.append(line.rsplit("layer root:", 1)[1].strip())
    absolute_source_roots = [root for root in roots
                             if Path(root).is_absolute()
                             and Path(root).name.casefold() == "mods_source"]
    expected = str((PROJECT / "mods_source").resolve(strict=True))
    previous = str((WORKSPACE / "D11_Interior_Standalone_20260927/p/mods_source")
                   .resolve(strict=True))
    normalize = lambda path: os.path.normcase(os.path.normpath(path))
    mounted = {normalize(root) for root in absolute_source_roots}
    guard(normalize(previous) not in mounted,
          "Native editor still mounted the previous D11 project source")
    guard(mounted == {normalize(expected)},
          f"Native editor resource layer did not mount the staged interior source: {absolute_source_roots}")
    return {"expectedModsSource": expected,
            "absoluteModsSourceRoots": absolute_source_roots,
            "resourceLayerLines": len(roots)}


def compiled_node_info(variant: str) -> dict:
    """Read the candidate's compiled AABB; this is not a runtime visibility claim."""
    model = MODEL_BY_VARIANT[variant]
    path = (PROJECT / "mods_source/models/mods" / f"{model}.tpl.asset" /
            "tpl/obj_list.json")
    tree = json.loads(path.read_text(encoding="utf-8"))
    found = []
    stack = [tree]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("name") == "D11_InteriorV1_vis" and "axial_bounding_box" in item:
                found.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    guard(len(found) == 1, f"Compiled {model} interior AABB is missing or ambiguous")
    node = found[0]
    bounds = ast.literal_eval(node["axial_bounding_box"])
    guard(len(bounds) == 2 and all(len(side) == 3 for side in bounds),
          "Compiled interior AABB shape is invalid")
    return {"model": model, "objList": str(path), "objListSha256": sha(path),
            "aabbGameXYZ": [[float(value) for value in side] for side in bounds],
            "materialTextures": [row["texture_name"] for row in node["material_info"]]}


def controls_with_geom_probe(base, survey, run: Path, run_id: str) -> Path:
    """Extend the proven native camera helper with read-only Geom queries."""
    helper = survey.controls(run, run_id)
    source = helper.read_text(encoding="utf-8")
    source = base.h.replace_once(
        source, "'CaptureCabLeftHvacDetail')][string]$Mode",
        "'CaptureCabLeftHvacDetail','InspectInteriorGeom','InspectInteriorHidden')][string]$Mode",
    )
    actions = r'''
if($Mode -eq 'InspectInteriorGeom'){
 $action=@'
var cabGeom=truck.owner.Get<Geom>()
result += "interiorTpl " + cabGeom.GetTplName() + "\n"
var cabNames=new array<string>()
cabNames.Add("D11_InteriorV1_vis")
cabNames.Add("D11_InteriorV1_vis_LOD0")
cabNames.Add("D11_InteriorV1_vis_LOD1")
cabNames.Add("D11_InteriorV1_vis_LOD2")
for var cabName in cabNames
 var cabId=cabGeom.GetObjIdByName(cabName)
 result += StringFormat("interiorNode %s id %i\n",cabName,cabId)
 if cabId >= 0
  for var slotIndex, slotName in cabGeom.GetObjectMaterials(cabName)
   result += StringFormat("interiorMaterial %s slot %i %s\n",cabName,slotIndex,slotName)
  end
 end
end
result += StringFormat("bodyNode Body_vis id %i\n",cabGeom.GetObjIdByName("Body_vis"))
'@
}
if($Mode -eq 'InspectInteriorHidden'){
 $action=@'
var cabGeom=truck.owner.Get<Geom>()
var cabNames=new array<string>()
cabNames.Add("D11_InteriorV1_vis")
cabNames.Add("D11_InteriorV1_vis_LOD0")
cabNames.Add("D11_InteriorV1_vis_LOD1")
cabNames.Add("D11_InteriorV1_vis_LOD2")
for var cabName in cabNames
 var cabId=cabGeom.GetObjIdByName(cabName)
 if cabId >= 0
  result += "interiorHidden " + cabName + " " + BoolToString(cabGeom.IsObjHidden(cabName),"true","false") + "\n"
 end
end
'@
}
'''
    source = base.h.replace_once(
        source, "$script=$script.Replace('__ACTION__',$action)",
        actions + "\n$script=$script.Replace('__ACTION__',$action)",
    )
    helper.write_text(source, encoding="utf-8")
    syntax = WORKSPACE / "D11_All_Repairs_20260925/handling/syntax_check.ps1"
    check = subprocess.run(
        [str(base.h.PWSH), "-NoProfile", "-File", str(syntax), str(helper)],
        capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    guard(check.returncode == 0, "Native probe PowerShell syntax check failed: "
          + check.stdout[-500:] + check.stderr[-500:])
    return helper


def inspect_loaded_geom(base, run: Path, helper: Path, engine_pid: int,
                        variant: str) -> dict:
    """Record the loaded truck node and slots before taking screenshots."""
    base.h.probe(run, "interior_geom", helper, engine_pid, "InspectInteriorGeom")
    path = run / "interior_geom.json"
    response = json.loads(path.read_text(encoding="utf-8"))["response"]
    names = {name: int(obj_id) for name, obj_id in re.findall(
        r"^interiorNode (\S+) id (-?\d+)$", response, re.M)}
    slots: dict[str, list[dict]] = {}
    for name, slot, material in re.findall(
            r"^interiorMaterial (\S+) slot (\d+) (.+)$", response, re.M):
        slots.setdefault(name, []).append({"slot": int(slot), "material": material})
    tpl = re.search(r"^interiorTpl (.+)$", response, re.M)
    body = re.search(r"^bodyNode Body_vis id (-?\d+)$", response, re.M)
    guard(set(names) == set(INTERIOR_NODES),
          "Runtime Geom probe omitted a D11 interior node")
    guard(names["D11_InteriorV1_vis"] >= 0,
          "D11_InteriorV1_vis did not load in the truck Geom")
    guard(tpl is not None and body is not None, "Runtime Geom probe omitted truck context")
    loaded = {name: {"id": names[name], "materials": slots.get(name, [])}
              for name in INTERIOR_NODES}
    guard(any(row["materials"] for row in loaded.values()),
          "D11 interior Geom loaded without any material slots")
    result = {"probe": str(path), "probeSha256": sha(path),
              "tplName": tpl.group(1), "bodyVisId": int(body.group(1)),
              "nodes": loaded, "compiledNode": compiled_node_info(variant)}
    try:
        base.h.probe(run, "interior_hidden", helper, engine_pid, "InspectInteriorHidden")
        hidden_path = run / "interior_hidden.json"
        hidden_response = json.loads(hidden_path.read_text(encoding="utf-8"))["response"]
        hidden = {name: state == "true" for name, state in re.findall(
            r"^interiorHidden (\S+) (true|false)$", hidden_response, re.M)}
        guard(hidden, "IsObjHidden did not return a parseable state")
        result["hiddenProbe"] = str(hidden_path)
        result["hiddenProbeSha256"] = sha(hidden_path)
        result["hiddenByNode"] = hidden
    except Exception as exc:
        # Keep this supplemental visibility probe separate from the ID/material
        # load gate in case a particular editor build lacks the API.
        result["hiddenProbeUnavailable"] = repr(exc)
    return result


def close_owned_editor(base, proc: subprocess.Popen | None, streams: tuple,
                       engine_pid: int | None) -> None:
    """Stop only the editor and engine identities observed for this run."""
    try:
        if proc is not None:
            current = base.processes()
            by_pid = {int(row["ProcessId"]): row for row in current}
            guard(len(by_pid) == len(current), "Duplicate editor process IDs")
            parent_live = proc.poll() is None
            parent_row = by_pid.get(proc.pid)
            if parent_live:
                guard(parent_row is not None
                      and parent_row["Name"] == "IntegrationStudio.exe",
                      "Owned editor process identity changed; inspect before terminating")
            else:
                guard(parent_row is None,
                      "Exited editor PID was reused; inspect before terminating")
            children = [row for row in current
                        if int(row["ParentProcessId"]) == proc.pid]
            if engine_pid is None:
                guard(len(children) <= 1 and all(
                    row["Name"] == "Roadcraft ModEditor.exe" for row in children),
                    "Unexpected editor child; inspect before terminating")
                if children:
                    engine_pid = int(children[0]["ProcessId"])
            else:
                guard(engine_pid != proc.pid, "Editor and engine PIDs unexpectedly match")
                guard(all(int(row["ProcessId"]) == engine_pid for row in children),
                      "Unexpected editor child; inspect before terminating")
            engine_row = by_pid.get(engine_pid) if engine_pid is not None else None
            if engine_row is not None:
                guard(engine_row["Name"] == "Roadcraft ModEditor.exe"
                      and int(engine_row["ParentProcessId"]) in (0, proc.pid),
                      "Recorded engine PID identity changed; inspect before terminating")
            targets = ([(engine_pid, "Roadcraft ModEditor")]
                       if engine_row is not None else [])
            if parent_live:
                targets.append((proc.pid, "IntegrationStudio"))
            for pid, process_name in targets:
                # Resolve the same PID and name again inside PowerShell before
                # Stop-Process, narrowing the process-exit/PID-reuse race.
                script = (f"$owned=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                          "if($null -ne $owned){ "
                          f"if($owned.ProcessName -ne '{process_name}'){{ throw 'PID identity changed' }}; "
                          "Stop-Process -InputObject $owned -Force -ErrorAction Stop }")
                stopped = subprocess.run(
                    [str(base.h.PWSH), "-NoProfile", "-Command", script],
                    capture_output=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                guard(stopped.returncode == 0,
                      f"Could not stop owned {process_name} PID {pid}: "
                      + stopped.stderr.decode(errors="replace")[-500:])
            deadline = time.monotonic() + 20
            while True:
                remaining = {int(row["ProcessId"]): row for row in base.processes()}
                guard(not any(pid in remaining and
                              remaining[pid]["Name"] != expected + ".exe"
                              for pid, expected in targets),
                      "Owned editor PID was reused during cleanup")
                if all(pid not in remaining for pid, _ in targets):
                    break
                guard(time.monotonic() < deadline,
                      "Owned editor or engine remained active after stop")
                time.sleep(0.5)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Owned editor process handle remained active")
    finally:
        for stream in streams:
            if stream is not None:
                stream.close()


class OwnedEngineHandle:
    """Keep the observed child process object alive for an exact exit code."""

    def __init__(self, pid: int) -> None:
        guard(os.name == "nt" and pid > 0, "Engine exit probe requires a Windows PID")
        import ctypes

        self.pid = pid
        self._ctypes = ctypes
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int,
                                             ctypes.c_uint32)
        self._kernel.OpenProcess.restype = ctypes.c_void_p
        self._kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p,
                                                      ctypes.c_uint32)
        self._kernel.WaitForSingleObject.restype = ctypes.c_uint32
        self._kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_uint32))
        self._kernel.GetExitCodeProcess.restype = ctypes.c_int
        self._kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._kernel.CloseHandle.restype = ctypes.c_int
        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION. The handle pins the
        # process object even if its numeric PID is later reused.
        self._handle = self._kernel.OpenProcess(0x00100000 | 0x1000, 0, pid)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess engine PID {pid}")

    def sample(self) -> dict:
        guard(self._handle is not None, "Engine exit handle was closed")
        result = self._kernel.WaitForSingleObject(self._handle, 0)
        if result == 0x102:  # WAIT_TIMEOUT
            return {"status": "running"}
        if result != 0:  # WAIT_OBJECT_0
            raise OSError(self._ctypes.get_last_error(),
                          f"WaitForSingleObject engine PID {self.pid}: {result:#x}")
        code = self._ctypes.c_uint32()
        if not self._kernel.GetExitCodeProcess(self._handle,
                                               self._ctypes.byref(code)):
            raise OSError(self._ctypes.get_last_error(),
                          f"GetExitCodeProcess engine PID {self.pid}")
        return {"status": "exited", "exitCodeUnsigned": code.value,
                "exitCodeHex": f"0x{code.value:08x}"}

    def close(self) -> None:
        if self._handle is not None:
            handle, self._handle = self._handle, None
            if not self._kernel.CloseHandle(handle):
                raise OSError(self._ctypes.get_last_error(),
                              f"CloseHandle engine PID {self.pid}")


def owned_snapshot(base, proc: subprocess.Popen, engine: OwnedEngineHandle) -> dict:
    """Best-effort process census plus the retained engine object's exit state."""
    snapshot = {"observedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "editorPid": proc.pid, "editorExitCode": proc.poll(),
                "enginePid": engine.pid}
    try:
        snapshot["engineExit"] = engine.sample()
    except BaseException as exc:
        snapshot["engineExit"] = {"status": "unavailable", "error": repr(exc)}
    try:
        snapshot["ownedProcesses"] = [
            {"pid": int(row["ProcessId"]),
             "parentPid": int(row["ParentProcessId"]), "name": row["Name"]}
            for row in base.processes()
            if int(row["ProcessId"]) in (proc.pid, engine.pid)]
    except BaseException as exc:
        snapshot["processProbeError"] = repr(exc)
    return snapshot


def capture_contract(run_id: str, variants: tuple[str, ...],
                     views: tuple[str, ...], candidate: Path,
                     candidate_sha: str, pins: dict[str, str],
                     camera_specs: dict, *, prototype: bool,
                     package_receipt: Path, package_receipt_sha: str,
                     package_receipt_status: str,
                     owned_lock: bool = False) -> dict:
    """Declare every named capture artifact before any native write or swap."""
    guard(re.fullmatch(r"[0-9a-f]{8}", run_id) is not None,
          "--run-id must be eight lowercase hexadecimal characters")
    guard(not NATIVE.is_symlink() and not RUNS.is_symlink(),
          "Native evidence directories must not be links")
    backup = NATIVE / f"cat_d11t_before_{EXPECTED_BASE_SHA[:12]}_{run_id}.pak"
    stage = LIVE.with_name(f"cat_d11t.standalone-{run_id}.tmp")
    restore = LIVE.with_name(f"cat_d11t.restore-{run_id}.tmp")
    report = NATIVE / f"candidate_capture_{run_id}.json"
    recovery = NATIVE / f"candidate_recovery_{run_id}.json"
    runs = {variant: RUNS / f"aaa_{variant}_{run_id}{variant[:2]}"
            for variant in variants}
    required_files = [report, backup]
    optional_files = []
    transient_paths = [LOCK, stage, restore,
                       report.with_suffix(report.suffix + ".tmp")]
    screenshot_sources = []
    runtime_directories = {}
    contexts = {}
    for variant in variants:
        run = runs[variant]
        runtime_directories[variant] = {
            "editorData": str(run / "editor_data"),
            "temporary": str(run / "tmp"),
            "localProfilesIfCreated": str(run / "local_profiles"),
        }
        scene = PROJECT / "mods_source/xscenes/mods" / SCENES[variant]
        contexts[variant] = {
            "scene": str(scene), "sceneSha256": sha(scene),
            "cameraBasis": "_cockpit_camera; offsets (forward,left,up) in metres",
            "cameraSpecs": {name: camera_specs[name] for name in views},
            "plannedResolutionPixels": {"status": "unknown"},
            "runtimeLighting": {"status": "unknown"},
            "protocol": "SetCab camera probe, CaptureCab SaveScreenshot PNG, copied source image",
        }
        required_files.extend((run / "native_controls.ps1", run / "probe.scenario",
                               run / "stdout.log", run / "stderr.log",
                               run / "report.json", run / "interior_geom.json",
                               run / "interior_geom.transport.log"))
        optional_files.extend((run / "interior_hidden.json",
                               run / "interior_hidden.transport.log"))
        transient_paths.extend((run / "report.json.tmp", run / "tmp"))
        for view in views:
            required_files.extend((run / f"camera_{view}.json",
                                   run / f"camera_{view}.transport.log",
                                   run / f"capture_{view}.json",
                                   run / f"capture_{view}.transport.log",
                                   run / f"cab_{view}.png"))
            screenshot_sources.append(WORKSPACE.parent / "root/bin/pc" /
                                      f"d11_cab_{run_id}{variant[:2]}_{view}.png")
    collisions = [path for path in (report, backup, recovery,
                                    *(path for path in transient_paths
                                      if path != LOCK or not owned_lock),
                                    *runs.values(), *screenshot_sources)
                  if path.exists() or path.is_symlink()]
    guard(not collisions,
          "Capture run ID has existing outputs; choose a fresh ID: " +
          ", ".join(str(path) for path in collisions[:5]))
    return {"schemaVersion": 1, "runId": run_id,
            "runner": str(Path(__file__).resolve()),
            "runnerSha256": sha(Path(__file__)),
            "candidatePackage": str(candidate), "candidateSha256": candidate_sha,
            "installedPackage": str(LIVE), "baselineSha256": EXPECTED_BASE_SHA,
            "prototype": prototype,
            "packageReceipt": str(package_receipt),
            "packageReceiptSha256": package_receipt_sha,
            "packageReceiptStatus": package_receipt_status,
            "sourcePinsSha256": canonical_sha256(pins),
            "sourcePinCount": len(pins),
            "variantContexts": contexts,
            "capturePlan": {"variants": list(variants),
                            "viewsPerVariant": list(views),
                            "fullCapture": len(variants) == len(SCENES) and views == VIEWS},
            "outerReceipt": str(report), "backup": str(backup),
            "stage": str(stage), "restore": str(restore),
            "lock": str(LOCK),
            "variantRuns": {name: str(path) for name, path in runs.items()},
            "runtimeDirectoryRoots": runtime_directories,
            "expectedOutputFiles": [str(path) for path in required_files],
            "optionalOutputFiles": [str(path) for path in optional_files],
            "transientPaths": [str(path) for path in transient_paths],
            "reservedRecoveryReceipt": str(recovery),
            "screenshotSourceFiles": [str(path) for path in screenshot_sources]}


def timed_action(report: dict, base, proc: subprocess.Popen,
                 engine: OwnedEngineHandle, action: str, callback,
                 *, view: str | None = None) -> None:
    """Bracket a native command with timestamps and retained process state."""
    event = {"action": action,
             "startedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "editorPid": proc.pid, "enginePid": engine.pid,
             "ownedBefore": owned_snapshot(base, proc, engine)}
    if view is not None:
        event["view"] = view
    report.setdefault("actionEvents", []).append(event)
    try:
        guard(event["ownedBefore"]["engineExit"]["status"] == "running",
              f"Owned engine was not running before {action}")
        callback()
        event["status"] = "PASS"
    except BaseException as exc:
        event.update(status="FAIL", error=repr(exc))
        raise
    finally:
        event["finishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        after = owned_snapshot(base, proc, engine)
        event["ownedAfter"] = after
        event["editorExitCode"] = after["editorExitCode"]
        event["engineExitCode"] = after["engineExit"].get("exitCodeUnsigned")
        if "ownedProcesses" in after:
            event["ownedProcessesAfter"] = after["ownedProcesses"]
        if "processProbeError" in after:
            event["processProbeError"] = after["processProbeError"]


@contextmanager
def view_boundary(report: dict, base, proc: subprocess.Popen,
                  engine: OwnedEngineHandle, view: str):
    """Keep the full camera-to-file interval, including pauses, in evidence."""
    event = {"view": view,
             "startedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
             "ownedBefore": owned_snapshot(base, proc, engine)}
    report.setdefault("viewEvents", []).append(event)
    try:
        yield
        event["status"] = "PASS"
    except BaseException as exc:
        event.update(status="FAIL", error=repr(exc))
        raise
    finally:
        event["finishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        event["ownedAfter"] = owned_snapshot(base, proc, engine)


def png_dimensions(path: Path) -> list[int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    guard(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR"
          and len(header) == 24, f"Screenshot lacks a PNG IHDR: {path}")
    width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    guard(width > 0 and height > 0, f"Screenshot dimensions are invalid: {path}")
    return [width, height]


def capture_variant(base, survey, variant: str, run_id: str,
                    package_sha: str, pins: dict[str, str],
                    views: tuple[str, ...], full_capture: bool,
                    context: dict, contract_sha: str) -> dict:
    run = RUNS / f"aaa_{variant}_{run_id}"
    run.mkdir(parents=True)
    helper = controls_with_geom_probe(base, survey, run, run_id)
    scene = PROJECT / "mods_source/xscenes/mods" / SCENES[variant]
    scenario = run / "probe.scenario"
    scenario.write_text(f'''open "{scene.as_posix()}"
command GameEditorCommands Play
wait-viewport
wait-scene-loading
echo D11_STANDALONE_READY_{run_id}
delay 00:05:00
command GameEditorCommands Stop
exit
''', encoding="utf-8")
    report = {
        "status": "STARTING", "variant": variant, "run": str(run),
        "project": str(PROJECT), "scene": str(scene),
        "candidatePackageSha256": package_sha,
        "cameraBasis": "_cockpit_camera; offsets (forward,left,up) in metres",
        "viewSpecs": {name: survey.VIEWS[name] for name in views},
        "helperSha256": sha(helper), "sourcePins": pins, "views": [],
        "captureContext": context, "outputContractSha256": contract_sha,
        "editorLaunch": {"projectArgument": str(PROJECT),
                         "workingDirectory": str(base.h.EDITOR),
                         "mount": editor_mount(PROJECT)},
    }
    proc = out = err = None
    engine_pid = None
    engine = None
    try:
        proc, out, err = base.h.launch_editor(run, scenario)
        report["editorPid"] = proc.pid
        report["editorLaunchedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        deadline = time.monotonic() + 170
        while time.monotonic() < deadline:
            guard(proc.poll() is None, "Editor exited before scene readiness")
            guard(shutil.disk_usage(HERE).free >= 1_500_000_000,
                  "Less than 1.5 GB free during editor launch")
            log = (run / "stdout.log").read_text(errors="replace")
            errors = (run / "stderr.log").read_text(errors="replace")
            guard("Engine has crashed" not in log and "Unhandled exception" not in errors,
                  "Native editor reported a crash: " + errors[-500:])
            if f"D11_STANDALONE_READY_{run_id}" in log:
                break
            time.sleep(2)
        else:
            raise TimeoutError("Native editor scene readiness")
        report["runtimeResourceMount"] = runtime_resource_mount(log)
        engine_pid = base.find_engine_pid(proc.pid)
        report["enginePid"] = engine_pid
        engine = OwnedEngineHandle(engine_pid)
        report["engineHandleAttachedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report["ownedAtAttach"] = owned_snapshot(base, proc, engine)
        guard(report["ownedAtAttach"]["engineExit"]["status"] == "running"
              and any(row["pid"] == engine_pid
                      and row["parentPid"] == proc.pid
                      and row["name"] == "Roadcraft ModEditor.exe"
                      for row in report["ownedAtAttach"].get("ownedProcesses", [])),
              "Owned child engine exited or changed identity before capture")
        loaded_geom = []
        timed_action(report, base, proc, engine, "InspectInteriorGeom",
                     lambda: loaded_geom.append(inspect_loaded_geom(
                         base, run, helper, engine_pid, variant)))
        report["loadedInteriorGeom"] = loaded_geom[0]
        for name in views:
            mode = name.title().replace("_", "")
            with view_boundary(report, base, proc, engine, name):
                timed_action(report, base, proc, engine, "SetCab" + mode,
                             lambda name=name, mode=mode: base.h.probe(
                                 run, "camera_" + name, helper, engine_pid,
                                 "SetCab" + mode), view=name)
                timed_action(report, base, proc, engine, "SettleCamera",
                             lambda: time.sleep(1.5), view=name)
                source = base.h.SDK / "root/bin/pc" / f"d11_cab_{run_id}_{name}.png"
                timed_action(report, base, proc, engine, "ScreenshotSourceGuard",
                             lambda: guard(not source.exists() and not source.is_symlink(),
                                           f"Native screenshot output already exists: {source}"),
                             view=name)
                timed_action(report, base, proc, engine, "CaptureCab" + mode,
                             lambda name=name, mode=mode: base.h.probe(
                                 run, "capture_" + name, helper, engine_pid,
                                 "CaptureCab" + mode), view=name)
                target = run / f"cab_{name}.png"
                timed_action(report, base, proc, engine, "SaveScreenshot:" + name,
                             lambda: base.screenshot(source, target, proc), view=name)
                report["views"].append({
                    "view": name, "path": str(target), "sha256": sha(target),
                    "cameraProbeSha256": sha(run / f"camera_{name}.json"),
                    "resolutionPixels": png_dimensions(target),
                })
        guard(project_pins(PROJECT) == pins, "Candidate project changed during capture")
        guard(sha(LIVE) == package_sha, "Installed candidate changed during capture")
        report["status"] = ("D11_AAA_NATIVE_CAPTURES_READY"
                            if full_capture
                            else "D11_AAA_NATIVE_TRIAGE_CAPTURES_READY")
    except Exception as exc:
        report.update(status="FAIL", error=repr(exc))
    finally:
        report["cleanupStartedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        if proc is not None and engine is not None:
            report["ownedBeforeCleanup"] = owned_snapshot(base, proc, engine)
        try:
            close_owned_editor(base, proc, (out, err), engine_pid)
        except BaseException as cleanup_error:
            report.update(status="FAIL", cleanupError=repr(cleanup_error))
            raise
        finally:
            report["cleanupFinishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            if proc is not None:
                report["editorExitCodeAfterCleanup"] = proc.poll()
            if proc is not None and engine is not None:
                report["ownedAfterCleanup"] = owned_snapshot(base, proc, engine)
                try:
                    engine.close()
                except BaseException as close_error:
                    report.update(status="FAIL", engineHandleCloseError=repr(close_error))
            save(run / "report.json", report)
    guard(report["status"] in ("D11_AAA_NATIVE_CAPTURES_READY",
                               "D11_AAA_NATIVE_TRIAGE_CAPTURES_READY"),
          f"Native capture failed for {variant}: {report.get('error')}")
    return {"variant": variant, "report": str(run / "report.json"),
            "reportSha256": sha(run / "report.json"), "views": len(report["views"]),
            "loadedInteriorGeom": report["loadedInteriorGeom"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-pak", type=Path)
    parser.add_argument("--expected-candidate-sha")
    parser.add_argument("--variants", nargs="+", choices=tuple(SCENES),
                        help="Capture only these cab variants (default: all three)")
    parser.add_argument("--views", nargs="+", choices=VIEWS + tuple(EXTRA_VIEWS),
                        help="Capture only these camera views (default: all fifteen)")
    parser.add_argument("--execute", action="store_true",
                        help="Perform the guarded temporary swap and native captures")
    parser.add_argument("--run-id", help="Predeclared eight-character lowercase hex run ID")
    parser.add_argument("--expected-contract-sha256",
                        help="SHA-256 from the reviewed --plan output; required with --execute")
    parser.add_argument("--plan", action="store_true",
                        help="Print the no-write output contract for --run-id")
    parser.add_argument("--prototype", action="store_true",
                        help="Admit the sealed texture-only prototype for early lighting QA")
    parser.add_argument("--recover", action="store_true",
                        help="Restore the pinned baseline after an interrupted capture")
    args = parser.parse_args()
    if args.recover:
        guard(not args.execute and not args.plan and not args.run_id
              and not args.expected_contract_sha256 and not args.prototype
              and not args.candidate_pak and not args.expected_candidate_sha
              and args.variants is None and args.views is None,
              "--recover takes no candidate, selection, or execute arguments")
        base, _ = old_helpers()
        recover(base)
        return
    guard(args.candidate_pak is not None and args.expected_candidate_sha is not None,
          "Provide both --candidate-pak and --expected-candidate-sha")
    guard(not (args.plan and args.execute), "--plan and --execute are exclusive")
    guard(not (args.plan or args.execute) or args.run_id is not None,
          "--plan and --execute require --run-id")
    guard(not args.execute or args.expected_contract_sha256 is not None,
          "--execute requires --expected-contract-sha256 from --plan")
    guard(args.execute or args.expected_contract_sha256 is None,
          "--expected-contract-sha256 is only valid with --execute")
    guard(args.expected_contract_sha256 is None or
          re.fullmatch(r"[0-9a-f]{64}", args.expected_contract_sha256) is not None,
          "--expected-contract-sha256 must be 64 lowercase hex characters")
    guard(args.run_id is None or re.fullmatch(r"[0-9a-f]{8}", args.run_id) is not None,
          "--run-id must be eight lowercase hexadecimal characters")
    guard(args.variants is None or len(args.variants) == len(set(args.variants)),
          "--variants must not repeat a variant")
    guard(args.views is None or len(args.views) == len(set(args.views)),
          "--views must not repeat a view")
    variants = tuple(name for name in SCENES
                     if args.variants is None or name in args.variants)
    views = (VIEWS if args.views is None else
             tuple(name for name in VIEWS + tuple(EXTRA_VIEWS)
                   if name in args.views))
    full_capture = len(variants) == len(SCENES) and views == VIEWS
    candidate = args.candidate_pak.resolve(strict=True)
    expected = args.expected_candidate_sha.lower()
    guard(candidate != LIVE.resolve(), "Candidate path cannot be the installed package")
    guard(len(expected) == 64 and all(c in "0123456789abcdef" for c in expected),
          "Expected candidate SHA-256 must be 64 lowercase hex characters")
    guard(sha(candidate) == expected, "Candidate package SHA-256 mismatch")
    package_receipt_path = PROTOTYPE_RECEIPT if args.prototype else PACKAGE_RECEIPT
    expected_status = ("D11_AAA_TEXTURE_PROTO_PACKAGE_AUDITED" if args.prototype
                       else "D11_AAA_PACKAGE_AUDITED")
    guard(package_receipt_path.is_file() and not package_receipt_path.is_symlink(),
          "Audited AAA package receipt is missing")
    package_report = json.loads(package_receipt_path.read_text(encoding="utf-8"))
    guard(package_report.get("status") == expected_status
          and package_report.get("candidatePackageSha256") == expected
          and package_report.get("baselinePackageSha256") == EXPECTED_BASE_SHA
          and Path(package_report["candidatePackage"]).resolve(strict=True) == candidate,
          "Candidate does not match the sealed AAA package audit")
    guard(sha(LIVE) == EXPECTED_BASE_SHA, "Installed D11 package changed; rebase the capture guard")
    guard(PROJECT.is_dir(), "Candidate project is missing")
    guard(not LOCK.exists(), "Another candidate capture is locked")
    guard(shutil.disk_usage(HERE).free >= 4_000_000_000, "Less than 4 GB free")
    base, survey = old_helpers()
    guard(not base.runner.LOCK.exists(), "A native benchmark is locked")
    guard(not base.processes(), "RoadCraft or a Mod Editor is already running")
    pins = project_pins(PROJECT)
    mount = editor_mount(PROJECT)
    contract = (capture_contract(args.run_id, variants, views, candidate, expected,
                                 pins, survey.VIEWS, prototype=args.prototype,
                                 package_receipt=package_receipt_path.resolve(),
                                 package_receipt_sha=sha(package_receipt_path),
                                 package_receipt_status=expected_status)
                if args.run_id else None)
    contract_sha = canonical_sha256(contract) if contract else None
    guard(not args.execute or args.expected_contract_sha256 == contract_sha,
          "Capture output contract changed since --plan")
    if not args.execute:
        preview = {"status": ("PREFLIGHT_READY_NO_SWAP" if full_capture
                              else "PREFLIGHT_TRIAGE_READY_NO_SWAP"),
                   "candidate": str(candidate),
                   "candidateSha256": expected, "baselineSha256": EXPECTED_BASE_SHA,
                   "prototype": args.prototype,
                   "project": str(PROJECT), "pinnedFiles": len(pins),
                   "editorMount": mount,
                   "variants": list(variants), "viewsPerVariant": list(views)}
        if args.plan:
            preview["status"] = "CAPTURE_OUTPUTS_DECLARED_NO_SWAP"
            preview["outputContract"] = contract
            preview["outputContractSha256"] = contract_sha
        print(json.dumps(preview, indent=2))
        return

    NATIVE.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id
    backup = Path(contract["backup"])
    stage = Path(contract["stage"])
    restore = Path(contract["restore"])
    report_path = Path(contract["outerReceipt"])
    report = {"status": "STARTING", "runId": run_id,
              "startedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "candidatePackage": str(candidate), "candidateSha256": expected,
              "prototype": args.prototype,
              "installedPackage": str(LIVE), "baselineSha256": EXPECTED_BASE_SHA,
              "project": str(PROJECT), "editorMount": mount,
              "sourcePins": pins, "capturePlan": {"variants": list(variants),
                                                    "viewsPerVariant": list(views),
                                                    "fullCapture": full_capture},
              "outputContractSha256": contract_sha,
              "variants": []}
    swapped = False
    receipt_owned = False
    with LOCK.open("x", encoding="utf-8") as stream:
        json.dump({"runId": run_id, "baselineSha256": EXPECTED_BASE_SHA,
                   "candidateSha256": expected, "backup": str(backup)}, stream)
    try:
        guard(canonical_sha256(capture_contract(
            run_id, variants, views, candidate, expected,
            pins, survey.VIEWS, prototype=args.prototype,
            package_receipt=package_receipt_path.resolve(),
            package_receipt_sha=sha(package_receipt_path),
            package_receipt_status=expected_status,
            owned_lock=True)) == contract_sha,
            "Capture output contract changed after acquiring the native lock")
        # The outer receipt is reserved before copying or swapping anything.
        # A run-ID race must never overwrite earlier evidence in save().
        with report_path.open("x", encoding="utf-8"):
            receipt_owned = True
        copy_exclusive(LIVE, backup)
        guard(sha(backup) == EXPECTED_BASE_SHA, "Baseline backup failed hash check")
        guard(not stage.exists() and not restore.exists(), "Staging path already exists")
        copy_exclusive(candidate, stage)
        guard(sha(stage) == expected, "Candidate staging failed hash check")
        guard(sha(LIVE) == EXPECTED_BASE_SHA and not base.processes(),
              "Installed package or process state changed before swap")
        os.replace(stage, LIVE)
        swapped = True
        guard(sha(LIVE) == expected, "Installed candidate failed hash check")
        base.EXPECTED_LIVE = expected
        for variant in variants:
            guard(not base.processes(), "An editor remained active after the previous variant")
            report["variants"].append(capture_variant(
                base, survey, variant, run_id + variant[:2], expected, pins,
                views, full_capture, contract["variantContexts"][variant],
                contract_sha))
        report["status"] = ("NATIVE_CAPTURES_READY_ROLLBACK_PENDING" if full_capture
                            else "NATIVE_TRIAGE_CAPTURES_READY_ROLLBACK_PENDING")
    except BaseException as exc:
        report.update(status="FAIL_ROLLBACK_PENDING", error=repr(exc))
        raise
    finally:
        try:
            guard(not base.processes(), "Editor still active; package rollback deferred")
            if swapped:
                guard(sha(LIVE) == expected,
                      "Installed package differs from candidate; refusing to overwrite it")
                copy_exclusive(backup, restore)
                guard(sha(restore) == EXPECTED_BASE_SHA, "Rollback staging hash mismatch")
                os.replace(restore, LIVE)
                guard(sha(LIVE) == EXPECTED_BASE_SHA, "Baseline rollback failed hash check")
            else:
                guard(sha(LIVE) == EXPECTED_BASE_SHA,
                      "Installed baseline changed without this run's swap")
            report["rollback"] = {"status": "BASELINE_RESTORED" if swapped else "NO_SWAP_NEEDED",
                                  "backup": str(backup) if backup.is_file() else None,
                                  "sha256": sha(LIVE)}
            if report["status"] == "NATIVE_CAPTURES_READY_ROLLBACK_PENDING":
                report["status"] = "NATIVE_CAPTURES_READY_BASELINE_RESTORED"
            elif report["status"] == "NATIVE_TRIAGE_CAPTURES_READY_ROLLBACK_PENDING":
                report["status"] = "NATIVE_TRIAGE_CAPTURES_READY_BASELINE_RESTORED"
        except BaseException as rollback_error:
            report["rollback"] = {"status": "MANUAL_RECOVERY_REQUIRED",
                                  "backup": str(backup), "error": repr(rollback_error)}
            report["status"] = "ROLLBACK_FAILED"
            raise
        finally:
            # Any incomplete stage/restore file is retained for inspection.
            # Another process may have won a path race; never delete its file.
            report["finishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            if receipt_owned:
                save(report_path, report)
            if report.get("rollback", {}).get("status") in ("BASELINE_RESTORED", "NO_SWAP_NEEDED"):
                LOCK.unlink()
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "variants": report["variants"]}, indent=2))


if __name__ == "__main__":
    main()

