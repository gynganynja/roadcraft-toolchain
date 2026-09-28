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
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


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


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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


def capture_variant(base, survey, variant: str, run_id: str,
                    package_sha: str, pins: dict[str, str],
                    views: tuple[str, ...], full_capture: bool) -> dict:
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
        "editorLaunch": {"projectArgument": str(PROJECT),
                         "workingDirectory": str(base.h.EDITOR),
                         "mount": editor_mount(PROJECT)},
    }
    proc = out = err = None
    engine_pid = None
    try:
        proc, out, err = base.h.launch_editor(run, scenario)
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
        report["loadedInteriorGeom"] = inspect_loaded_geom(
            base, run, helper, engine_pid, variant)
        for name in views:
            mode = name.title().replace("_", "")
            base.h.probe(run, "camera_" + name, helper, engine_pid, "SetCab" + mode)
            time.sleep(1.5)
            base.h.probe(run, "capture_" + name, helper, engine_pid, "CaptureCab" + mode)
            source = base.h.SDK / "root/bin/pc" / f"d11_cab_{run_id}_{name}.png"
            target = run / f"cab_{name}.png"
            base.screenshot(source, target, proc)
            report["views"].append({
                "view": name, "path": str(target), "sha256": sha(target),
                "cameraProbeSha256": sha(run / f"camera_{name}.json"),
            })
        guard(project_pins(PROJECT) == pins, "Candidate project changed during capture")
        guard(sha(LIVE) == package_sha, "Installed candidate changed during capture")
        report["status"] = ("D11_AAA_NATIVE_CAPTURES_READY"
                            if full_capture
                            else "D11_AAA_NATIVE_TRIAGE_CAPTURES_READY")
    except Exception as exc:
        report.update(status="FAIL", error=repr(exc))
    finally:
        try:
            close_owned_editor(base, proc, (out, err), engine_pid)
        except BaseException as cleanup_error:
            report.update(status="FAIL", cleanupError=repr(cleanup_error))
            raise
        finally:
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
    parser.add_argument("--prototype", action="store_true",
                        help="Admit the sealed texture-only prototype for early lighting QA")
    parser.add_argument("--recover", action="store_true",
                        help="Restore the pinned baseline after an interrupted capture")
    args = parser.parse_args()
    if args.recover:
        guard(not args.execute and not args.prototype and not args.candidate_pak and not args.expected_candidate_sha
              and args.variants is None and args.views is None,
              "--recover takes no candidate, selection, or execute arguments")
        base, _ = old_helpers()
        recover(base)
        return
    guard(args.candidate_pak is not None and args.expected_candidate_sha is not None,
          "Provide both --candidate-pak and --expected-candidate-sha")
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
    if not args.execute:
        print(json.dumps({"status": ("PREFLIGHT_READY_NO_SWAP" if full_capture
                                      else "PREFLIGHT_TRIAGE_READY_NO_SWAP"),
                          "candidate": str(candidate),
                          "candidateSha256": expected, "baselineSha256": EXPECTED_BASE_SHA,
                          "prototype": args.prototype,
                          "project": str(PROJECT), "pinnedFiles": len(pins),
                          "editorMount": mount,
                          "variants": list(variants), "viewsPerVariant": list(views)}, indent=2))
        return

    NATIVE.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    backup = NATIVE / f"cat_d11t_before_{EXPECTED_BASE_SHA[:12]}_{run_id}.pak"
    stage = LIVE.with_name(f"cat_d11t.standalone-{run_id}.tmp")
    restore = LIVE.with_name(f"cat_d11t.restore-{run_id}.tmp")
    report_path = NATIVE / f"candidate_capture_{run_id}.json"
    report = {"status": "STARTING", "runId": run_id,
              "startedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "candidatePackage": str(candidate), "candidateSha256": expected,
              "prototype": args.prototype,
              "installedPackage": str(LIVE), "baselineSha256": EXPECTED_BASE_SHA,
              "project": str(PROJECT), "editorMount": mount,
              "sourcePins": pins, "capturePlan": {"variants": list(variants),
                                                    "viewsPerVariant": list(views),
                                                    "fullCapture": full_capture},
              "variants": []}
    swapped = False
    with LOCK.open("x", encoding="utf-8") as stream:
        json.dump({"runId": run_id, "baselineSha256": EXPECTED_BASE_SHA,
                   "candidateSha256": expected, "backup": str(backup)}, stream)
    try:
        shutil.copy2(LIVE, backup)
        guard(sha(backup) == EXPECTED_BASE_SHA, "Baseline backup failed hash check")
        guard(not stage.exists() and not restore.exists(), "Staging path already exists")
        shutil.copy2(candidate, stage)
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
                views, full_capture))
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
                shutil.copy2(backup, restore)
                guard(sha(restore) == EXPECTED_BASE_SHA, "Rollback staging hash mismatch")
                os.replace(restore, LIVE)
                guard(sha(LIVE) == EXPECTED_BASE_SHA, "Baseline rollback failed hash check")
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
            for path in (stage, restore):
                if path.exists():
                    path.unlink()
            report["finishedUtc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            save(report_path, report)
            if report.get("rollback", {}).get("status") in ("BASELINE_RESTORED", "NO_SWAP_NEEDED"):
                LOCK.unlink()
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "variants": report["variants"]}, indent=2))


if __name__ == "__main__":
    main()

