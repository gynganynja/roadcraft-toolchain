# Headless bench: the editor's engine without the editor

Stage 2 of the headless editor (desktop requirements 4 "bench" and 5 "capture"). It runs
`Roadcraft ModEditor.exe` the way IntegrationStudio runs its viewport engine, but with no editor,
no window, on a private desktop, with a private mod folder per run, and drives it over the same
ConsoleTre `Automation/ExecSsl` channel that the [editor bench](physics-bench.md) already uses.

**Every engine run needs the owner's go-ahead for that run.** `EngineSession.start` refuses without
`owner_approved="<text>"`; the command line refuses without `--owner-approved "<text>"` and then only
prints a dry run. It also refuses while the game, the Mod Editor, an engine or another ConsoleTre
hub (port 20563) is running, and it never writes into the game folder, `root\mods`,
`root\mods_source` or the owner's `Documents\Saber\IntegrationStudio\mods_source`.

Written before the first live runs (corrected 2026-10-13: see "First live runs" and the KGS-25 campaign,
which ran it against the real engine). Everything below marked Build was
exercised against the real SDK hub code and a fake engine (`tests/fake_engine.py`); the engine side is
SDK (read in the decompile or the shipped config) or Inferred.

## Commands

```text
python -m roadcraft.bench_headless smoke   --out <new folder> [--pak <pak>] --owner-approved "<who/when/why>"
python -m roadcraft.bench_headless run     <scenario.json> --pak <candidate.pak> [--baseline <pak>] --out <new folder> --owner-approved "..."
python -m roadcraft.bench_headless capture <scenario.json> --pak <pak> --out <new folder> --owner-approved "..."
python -m roadcraft.bench_headless scene   --out <new folder> [--scene <scn under mods_source>] [--mode play|edit] --owner-approved "..."
python -m roadcraft.bench_headless analyse <run folder> --scenario <scenario.json>
    common: [--dry-run] [--strategy moddirs|project-copy] [--project <folder with mods_source>]
            [--game-root <RoadCraft folder>] [--sdk-editor-dir <...\tools\bin\ModEditor>] [--adapter-id N]
```

Without `--owner-approved` (or with `--dry-run`) the command prints, as JSON, the exact engine
command line and its environment, the hub build and launch commands, the private folders and files it
would create, every SSL script (ready check, probe, each input step, release, capture states and
cameras) and the outputs, and launches nothing (not even `dotnet`). The output folder must not exist.

Python use: `with EngineSession(layout, ...) as s: s.start(owner_approved="..."); s.exec_ssl(script);
s.screenshot(abs_path)`; `engine.plan_layout` / `prepare_layout` make the private folders.

## How it works

| Piece | What | Grade |
|---|---|---|
| Engine command line | `"Roadcraft ModEditor.exe" --startup --set /Config/Video/WindowSizeY h --set /Config/Video/WindowSizeX w --set /Config/Debug/ConsoleChannel <our pid> --set /Config/CONFIG/enableWindow false --editor --cfg ../../config/editor/editor.cfg --set /Config/Video/API dx12 --set /Config/Video/AdapterId <id>`, cwd `root\bin\pc`: the editor's own assembly order (`EngineViewportProcessStarter`) | **SDK** (decompiled editor); that the engine starts and registers without the editor present is **Inferred** |
| Dialog and focus switches | `Video/WindowMode windowed`, `Debug/ErrorToConsoleOnly true` (not AutomationMode, which adds an Automation/EventFailure reporter), `VideoDriverVersionWarning/Show false`, `Video/LowCpuMemoryWarning/Ignored true`, `Streaming/LowCpuMemoryWarning/Enabled false`, `Input/ClipCursorDisabled true`, `Asserts/IntegrationStudio/RunAutomaticallyOnError false`, `--dont_send_crashdump --crashdump_directory <run>\crash`; env `S3D_FORCE_SILENT_CRASH_REPORT=1`, `S3D_TOOLS_CRASHDUMP_DIR` | keys **SDK** (editor.cfg); effect of each and the nested `--set` path form **Inferred** (focus_dialogs_native.md) |
| Private mods (`--strategy moddirs`, default) | `ResourceManager/ModDirs/local` = `<run>\root\mods` holding only a copy of the candidate pak, `ModDirs/pros` = an empty folder, `external/ModsSourceLocal` = an empty folder | keys **SDK** (editor.cfg); `--set` on a dictionary key **Inferred**; which mods the engine *enables* from that folder is **Open** (the mod id list `local:<name>` comes from somewhere not yet decompiled) |
| Fallback (`--strategy project-copy --project <mod project>`) | a private copy of the project's `mods_source` (like `physics_bench.init_bench`) as `external/ModsSourceLocal`, empty mod folders; `spawn.method: scene` moves the vehicle in the copied scene | the FileSystem TagLayer `$(external.ModsSourceLocal)` is **SDK** (editor.cfg); the override **Inferred** |
| Fixed timestep | scenario `timestep` sets `EDITOR/FPS/FIXED/editorFixedFpsValue` and `playModeFixedFpsValue` to 1/timestep | keys **SDK**; effect **Inferred**. `seed` is recorded only: no engine seed setting is known (**Open**) |
| ConsoleTre hub | `integrations/consoletre-hub`: a .NET 8 helper that hosts the SDK's own `ConsoleServer(127.0.0.1, 20563)` (what IntegrationStudio does with `AutoStartConsoleTre = Host`) and sends ExecSsl through the SDK's `ConsoleClient` exactly as `series_probe.ps1`/`input_override.ps1` (mirrored listener passport, reply listener `__PrivateId__ = {GUID}`, request GUID16 + string, reply one NUL-terminated UTF-8 string). Loads `Saber.ConsoleTre.dll`/`Saber.Json.dll` from `<game>\tools\bin\ModEditor` at run time; built once into `%LOCALAPPDATA%\roadcraft-toolchain\consoletre-hub\<hash>` with `dotnet build` through `quiet.run`; runs through `quiet.start(pipes=True)` and speaks JSON lines | **Build** (tests: real SDK hub + fake engine). Binding 127.0.0.1 instead of the editor's 0.0.0.0 avoids a firewall prompt |
| Discovery | the helper's `RequestConnect("127.0.0.1")` sends `CONSOLE_IPDISCOVERY20563` to UDP 20663 for 5 s; the session repeats one datagram every 5 s while it waits | **SDK**; whether the engine needs it (it should connect to `Debug.ConsoleServerIp` itself) **Inferred** |
| Launch | engine and helper through `quiet.start(desktop="private", priority="below_normal")`, engine output to `<run>\root\logs\engine.log`; registration = a hub client whose PID is in the engine's job with a `Module=Automation, Type=ExecSsl` listener; attach refuses an ambiguous destination | **Build** with the fake; D3D12 on the private desktop **Open** |
| Stop | detach, close the hub, kill the engine job (whole tree), record leaked/private windows; a watchdog kills the engine at the wall-clock limit (`wallClockSeconds`, default 900) | **Build** |
| Timeouts | an unanswered request rotates the reply GUID so a late reply is never read as the next one | **Build** |
| Screenshots | `SaveScreenshot(ScreenshotSaveTarget.FILE,"<absolute path>",false,ScreenshotFormat.PNG)`, then wait for PNG signature, IEND and a size stable over two polls | statement **Build** (earlier editor sessions); windowless without `StartFrameSharing` **Inferred** |

## Scenario

```json
{"schemaVersion": 1, "name": "pad-pivot", "seed": 1, "timestep": 0.0166667,
 "durationSeconds": 64, "wallClockSeconds": 900, "startupTimeoutSeconds": 300,
 "scene": {"level": null, "loadSsl": null, "settleSeconds": 5, "readyTimeoutSeconds": 120},
 "vehicle": {"tpl": "*", "hull": "BoneChassis_cdt", "restHeightModelled": 1.19,
             "suspensionTravel": {"min": 0.0, "max": 0.4}},
 "spawn": {"method": "none"},
 "inputs": {"method": "Debug", "schedule": "normal"},
 "probes": {"rateHz": 10, "items": ["engine", "bodies", "com", "wheels", "joints", "tracks"]},
 "capture": {"cameras": [{"name": "side", "offset": [5, 1.6, -3.5], "target": [0, 0, 0]}],
             "states": [{"name": "lamps_on", "headlights": true}, {"name": "night", "dayTime": 23}]},
 "analysis": {"pivotSteer": 0.5, "settle": {"rollDeg": 0.2, "pitchDeg": 0.2, "heightMm": 5},
              "stopToleranceM": 0.005, "judderMinHz": 0.3}}
```

- `inputs.schedule` is a [physics bench](physics-bench.md) schedule name (`normal`, `harsh`) or a list
  of steps `{"at", "phase", "pedal", "steer", "handbrake": On|Off|Unchanged, "gear": AUTO|LOW_GEAR|HIGH_GEAR|REVERSE|NEUTRAL,
  "engine": true, "awd", "difflock", "controls": [{"controller", "field", "value"}]}`. The statements are
  `input_override.ps1`'s (checked line for line by the tests); `controls` set
  `truck.owner.TryGet<controller>().GetState().<field>.Set(value)` as the D11 RC3 bench set
  `PropTruckViewGraderController.bladeAngle`. Names must be identifiers and values numbers, booleans or
  `Enum.VALUE`: no free SSL.
  A control can instead call a controller method: `{"controller", "call", "args"}` emits
  `truck.owner.TryGet<controller>().<call>(args...)`; args are numbers, booleans, `Enum.VALUE` or
  identifier strings (quoted). Use it where the target is not a plain state field, such as a markup
  linear lift: `{"controller": "PropTruckConstraintView", "call": "SetConstraintTarget", "args": ["lift", 0.857, 0.08]}`
  (the method branches on `IsAngular()` to `SetMotorTargetPosition`; SSL `prop_truck_constraint_view.ssc`, Build: TED 2026-10-19).
- `spawn.boxes` copies the scene's first unit-cube mesh; a scene without one (the SDK 1x1 template) needs a seed cube first. TED's `tools/bench_project.py` parks one under the ground (cube data from the D11 acceptance scene, `bench/cube_mesh_data.txt`).
- **Reverse in the named schedules is a brake test, not a reverse drive.** `normal`/`harsh`/`straight`
  set manual `REVERSE` with a negative pedal; in manual reverse the pedals are not swapped
  (`C:\RC_RE\research\gearbox_semantics.md` section 4), so the back pedal brakes and the wheels barely
  turn (TED c2/c3: gear -1, rpm 1045, wheels 0-0.1 rad/s). To measure reverse drive, use a custom step
  with `"gear": "AUTO"` and a negative pedal (auto reverse swaps the pedals) or manual `REVERSE` with a
  positive pedal. Code (C) for the pedal rule; Game (TED bench) for the symptom.
- `probes.items`: `engine` (G line), `bodies` (B), `com` (C), `wheels` (W) are `series_probe.ps1`
  verbatim (test-checked); `joints` (J: angular constraints, angle and motor target) and `tracks` (T:
  sliding velocity) are the D11 RC3 bench's. Wheel load, slip and constraint forces have no known SSL
  getter yet (**Open**).
- `scene.level` sets `Level/File` on the command line. In `--editor` mode nothing reads it
  (scene_play.md), so it has no effect. `scene.loadSsl` (a res tag) runs the SSL edit-mode load
  `XgineEditMode.StartSceneLoading` (**Inferred**). The old `LoadSceneRes("<tag>")` was not a global
  function. Play mode with a current truck is the `scene` command below; `run` and `capture` still
  wait `readyTimeoutSeconds` for a current truck.
- Capture: `headlights` uses `state.isHeadlightsOn.Set` (**Build**, D11 lamp scripts), `dayTime` uses
  `$preset_sys.SetDayTime` (**Inferred**); cameras use the D11 capture scripts' fly camera.

## Outputs

`<out>/candidate/` (and `/baseline/`): `run.json`, `session.json` (gates, plan, events, result),
`root/` (the private folders, logs, crash dumps), `series.jsonl` (the editor bench's format, so
`physics_bench.parse_series` reads it), `inputs.json`, one CSV per probe (`engine`, `bodies`, `com`,
`wheels`, `joints`, `tracks`) and `summary.json`: `maxRollPivotDeg`/`maxPitchPivotDeg` (phases with
pedal and |steer| >= `pivotSteer`), `rest` (hull height and wheel travel medians, delta to
`restHeightModelled`), `stopHits` (samples within `stopToleranceM` of `suspensionTravel`),
`settleSeconds` (per settle phase, until roll, pitch and height stay within tolerance of their final
value; null = never), `judder` (strongest pitch/roll/height frequency per driven phase: linear
resampling, detrend, Hann window, zero-padded stdlib DFT, verified on a jittered synthetic 1 Hz signal)
and `yaw` (yaw, distance, top speed per driven phase). With `--baseline`, `comparison.json`.
`capture` writes `<state>__<camera>.png` and `capture.json`.

## Proposed first live run (needs the owner's go-ahead)

```text
cd C:\roadcraft-toolchain-headless
set PYTHONPATH=src
"<toolchain venv>\Scripts\python.exe" -m roadcraft.bench_headless smoke --out C:\RC_RE\bench-headless\smoke_001 --owner-approved "<owner, date, 'smoke run approved'>"
```

- **Which:** the `smoke` command, **no pak** (empty private mod folders), adapter 0 (pass
  `--adapter-id` for the RTX GPU if 0 is the Intel one; the RC3 log showed both). It starts the hub and
  the engine, waits for the ExecSsl listener, reads frame number, level name and "current truck"
  twice two seconds apart, takes one screenshot to `<out>\candidate\smoke.png`, and stops.
- **Duration:** a few seconds for the hub (already built), then the engine start: the editor bench
  took about 3.5 minutes per run including editor start and a 64 s drive, so expect 1-3 minutes;
  wall-clock limit 300 s, startup limit 240 s, after which the whole tree is killed.
- **On screen:** nothing: no window, splash, dialog, focus change or cursor clipping; the engine and
  any dialog it raises are on the private desktop. The owner will see GPU, CPU (below normal) and disk
  load and possibly fan noise, and `Roadcraft ModEditor.exe` and `roadcraft-consoletre-hub.exe` in Task
  Manager. Avoid starting the game or editor during the run (the gate checks only at start).
- **It settles:** D3D12 on a private desktop (engine.log adapter lines, exit code); whether the engine
  registers `Automation/ExecSsl` with no editor (and with which passport); whether frames advance
  windowless; whether SaveScreenshot works without frame sharing; whether the nested `--set` paths
  are accepted (look for "Unexpected command line argument" in engine.log); `privateWindows` in
  session.json names any dialog that appeared.
- **Next, after it passes:** `smoke --pak <candidate>` to look for the mod in engine.log
  (`resources/mods`, "Unable to enable mod"), then a `run` once a way into play mode with a current
  truck is found.

## First live runs (2026-10-13, laptop, owner-approved)

| Run | Result | Grade |
|---|---|---|
| smoke_001 | the hub helper crashed before the engine started: Saber's `ConsoleServer.RequestConnect(string)` builds a `DnsEndPoint` that `Socket.SendTo` rejects; the editor calls the `IPAddress` overload (EngineConnectorPlugin), which the helper now uses | Build |
| smoke_002 | the windowless engine started on the private desktop, registered with the hub in ~8 s and attached the Automation/ExecSsl listener; the first script, sent during `Init hardware`, got no reply in 12 s and the run stopped | Game (engine, no level) |
| smoke_003 | registered in ~3 s; first script answered after ~100 s of resource preloading (10 attempts); frames advanced 1 -> 127 between two calls; no level loaded (`level` empty, no truck); `SaveScreenshot` wrote no PNG within 30 s, presumably because nothing renders without a level; stopped and the tree was killed at 138 s | Game (engine, no level) |

| scene_001 | `bench_headless scene` on the Goliath RC3 bench project (`gd11_bench.scn`, project copy, adapter 1 = the RTX 4060): the "Game editor" connector attached, `StartFrameSharing` + `LoadScenePlay` sent, scene loaded in ~94 s, level `gd11_bench`, truck current, 1 viewport; the screenshot WAS written but as `scene.png.png`: the engine appends the extension itself (now passed without it) | Game (engine, headless play) |
| run_001 | first headless bench drive: same project/scene, `normal` schedule, 10 Hz probes; all 10 inputs applied; forward 5.5 m, pivots -32 / +35 deg, reverse 4.3 m; 563 series samples, six CSVs and summary.json; 224 s wall clock | Game (engine, headless play) |
| pakmount_001 | smoke with the Goliath RC6 candidate copied into the private `ModDirs/local` folder: the engine ran, but in `--editor` mode it builds its resource layers from `local`, `resource_overrides`, `mods_source`, `source_extra` and the retail paks only and never scans a mods folder; no mod line in engine.log. The `ModDirs` override does not mount a pak in the editor engine | Game (engine) |

All three: no window and no dialog on the user's desktop (`leakedWindows` empty); the engine's own
windows (`RoadBuilder`, five child console windows) stayed invisible on the private desktop.
Confirmed: the engine runs without IntegrationStudio, without a window, on a private desktop, and
answers ExecSsl through the helper hub. Since scene_001/run_001 also confirmed: loading a scene, entering play with a current truck,
screenshots, and a full scripted drive with probes, all headless. Not possible as designed: mounting a
candidate .pak through `ModDirs` (the editor engine reads no mods folder). To bench a built package,
lay it over a project copy with `roadcraft.pak_overlay` ("Benching a built package" below; done for the
KGS-25 campaign). Determinism across two identical runs: see the KGS-25 campaign's repeat run.

## Benching a built package: the pak overlay (KGS-25 campaign, 2026-10-13)

The editor engine mounts no pak (pakmount_001), so a built package is benched by laying it over a copy of an
editor project that holds the bench scene:

```text
python -m roadcraft.pak_overlay --project <editor project> --pak <installed.pak> --out <new folder>
    [--suffix kgs25] [--markup-body "BoneTrackSusp_L_cdt:angularDamping=0.05,linearDamping=0"]
python -m roadcraft.bench_headless run <scenario> --strategy project-copy --project <overlay folder> --adapter-id 1 \
    --prune-copy --owner-approved "..."
```

| Step | Why | Grade |
|---|---|---|
| copy the project (hard links; a changed file is unlinked and rewritten), point `documents-dir`, `ModsSourceLocal` and `ProjectPath` at the copy | the source project and pak are only read | Build |
| write every pak member at its resource path (duplicate members must be identical); the pak's root `.mod` replaces `mods/<name>.mod` | the truck is the pak's bytes: classes, wheel classes, model, markup, textures | Build; checked back by sha256 in `overlay.json` |
| remove the project's generated classes that the pak ships staged (`autogen_dw/.../auto_kgs25.cls` -> pak `ssl/auto_kgs25_kgs25.cls`) | the old classes cannot load by their old names | Build |
| **write each removed generated `.sso` back at its project path with the pak's fields** (`.resource` keeps the project brand and `sso:` name) | the editor engine registers trucks and wheel sets by scanning `res://autogen_dw/trucks/auto_<t>/auto_<t>_truck_info.sso` / `_truck_wheel_info.sso` / `trucks/preview/`, key = folder minus `auto_` (retail `ssl/game/autogen_libraries_creator.ssc`, `GatherModEditorContentForAutoLibraries`); installed mods are keyed from their `.mod` instead. Without it: `SSL runtime error: key 'kgs25' is not found in dictionary` in `WheelsLibrary.Get` while loading the scene's prefab (launches 1-2) | Game (engine) |
| keep `auto_truck_library.sso` / `auto_wheels_library.sso` / prefabs, retag them (class staging's own rules) and replace each library entry by the pak's `.sso` fields | an old project's library lacks a newer build's wheels (KGS: the ramp wheel) | Build |
| retag every scene and prefab: `desc __type "auto_kgs25"` -> `"auto_kgs25_kgs25"`, prefab link -> `res://ssl/auto_kgs25_kgs25.cls.resource` | the spawned truck IS the pak's class | Game (readback below) |
| optional `--markup-body` patches a body's physics scalars in the pak's markups | bench variants of a built package | Build |

Bench changes made for this (all tested with the fake engine):

- **Scene text from the private copy.** `LoadScenePlay` sends the scene text as `psOverrides`; `run` read it from the
  source project, so `spawn.position` edits in the private copy were silently ignored. It now sends the private copy.
- `spawn.boxes: [{name, position, scale, yaw}]` adds static collision boxes to the private scene copy
  (`physics_bench.add_box`: the scene's own unit-cube `EditorMesh`, as the Goliath RC3 bench's ledges).
- `probes.readback: true` runs read-only checks once at rest (`readback.json`, `summary.readback`): model name and
  owner; per wheel `GetPhysicalRadius`, `GetMaxSpringTravelDistance` and **`wheel.softForceScale` (works, Game)**; per
  constraint name, `IsAngular`, `HasMotor`, **`GetMotorSpring`/`GetMotorDamping` (work, Game)**.
  `GetAngularLimits()` returns a type without `.x` (`error 2059: can't resolve identifier 'x'`); limits stay unread.
  No body damping getter is known: markup damping is verified from the overlay's bytes only.
- `analysis.articulation {frames, wheels, joints}` + `vehicle.wheelNames` (truck.GetWheels() order = the class's
  wheel-slot order, confirmed on KGS-25 by positions): per phase the track frames' pitch against the hull, wheel
  heights in the hull frame against rest (travel of rigid sprockets/idlers comes from the frame, of road wheels from
  frame + spring), spring travel, the hull's signed roll/pitch extremes and joint angles.
- `--prune-copy` deletes the run's private `mods_source` (1.4 GB for KGS-25) after the run; logs and CSVs stay.

### KGS-25 campaign record (2026-10-13, laptop, owner-approved 18 runs; results in `C:\RC_RE\bench-headless\kgs25\results.md`)

| Launch | Run | Result | Grade |
|---|---|---|---|
| 1 | v1 flat normal | engine crash loading the prefab: `SSL runtime error: key 'kgs25' is not found in dictionary` (`WheelsLibrary.Get`); the first overlay had removed every generated `.sso` | Game (engine) |
| 2 | v1 flat normal | same with the libraries kept and synced: the editor engine does not read the library for project trucks, it scans `autogen_dw/trucks/auto_<t>/` (registration shims added) | Game (engine) |
| 3-7 | v1 flat normal, v1 step, v2-v4 flat normal | complete: 10/10 (4/4) inputs, readback, about 9 Hz probes, 4-5 min each | Game (engine, headless play) |
| 8 | v5 flat normal | the hub helper crashed in Saber `DriverTcpServer.NewClientsThreadProc`: WinSock 10055 (no buffer space), engine fine | Build (environment) |
| 9-10 | v5, v6 flat normal | complete | Game (engine, headless play) |
| - | (stop) | first session stopped: each run grew the system-managed pagefile by about 2.7 GB (34.5 -> 39.8 GB) while the owner's Substance Painter (15.8 GB committed) and Blender (10 GB) were open on the 15.7 GB laptop; free disk fell to 3.1 GB | - |
| 11-21 | step v2-v6, harsh v1-v6 (resumed after the owner freed disk) | all complete, about 3 min each; 11.2 GB free at the end | Game (engine, headless play) |

21 launches for 18 runs. **Course pitfalls found:** the harsh course's full-lock pivots and fast reverse carried
four of six builds over the pad edge from a lane 8 m from it (two fell 15 m), so use a centred lane or a bigger pad
for `harsh`. On a single-track step every build yawed about 15 deg toward the slab and drifted 2.1 m, so the slab
must be wider than the drift (5 m or more). `GetCurrentAngle` of a hinge is in radians (it matched the body-derived
frame angle to 0.1 deg).

**Pitfall: memory and disk.** An engine run commits several GB; with other large applications open, Windows grows the
pagefile into free disk and keeps it until reboot, and the hub can fail with WinSock 10055. Check free virtual memory
and disk before each launch (the campaign's `run_queue.sh` stops below 6 GB / 5 GB) and use `--prune-copy`.

Speed note (KGS-25, Game): `normal`'s pedal 0.35 in AUTO reaches 2 m/s in 1st gear and 2.9 m/s after the shift; for a
slow climb use `gear: LOW_GEAR` (about 1.25 m/s at pedal 0.35).

## Mammoth series-spring bench (2026-10-14, laptop, owner-approved 3 runs; results in `C:\RC_RE\bench-headless\mammoth\results.md`)

Scenario `library/bench-scenarios/mammoth_parked_empty.json`:
- the truck parked, empty, handbrake on, engine on, no pedal;
- 40 s of 10 Hz probes on the roamer105_acceptance pad.

Bench additions for this campaign (all tested with the fake engine):

| Addition | What | Grade |
|---|---|---|
| probe `terrain` | `H <wheel> <GetTerrain().GetHeight(wheel centre)>`; `terrain.csv`; `summary.wheelGround` = wheel bottom (centre y - `GetPhysicalRadius`) vs the higher of terrain and `analysis.groundHeight` (a static scene mesh such as a pad is not in the terrain: on roamer105 the terrain reads 42.499 under the pad top 60.0) | Game (RC60 check) |
| probe `linear` | `L <constraint> <GetCurrentPosition()>` for `IsPositional()` constraints; `linear.csv` | Inferred (RC60 has no prismatic; not yet run on one) |
| checked items | `terrain` and `linear` are tried once at rest (`probe_checks.json`) and left out of the per-sample probe if the reply lacks their lines, so one rejected accessor cannot cost a run's probes | Build |
| readback | `limits` now reads `FloatRange.min/.max` (the `.x` of the KGS campaign was the error); new `positional` (position, `GetLinearLimits`) and `layers` (`GetCollisionFilterInfo().GetLayer()`, system group per body) | limits and layers Game (RC60), positional Inferred |
| `analysis.sprung {bodies, joints}` | each sprung body's offset (left/up/fwd) and roll/pitch against the hull, vs a modelled offset; each prismatic (m) / hinge (deg) series against its limits; `summary.stillness` = hull height/roll/pitch statistics, strongest oscillation, settle time over the whole run | Build |
| `run` + `capture` section | a run's screenshots are taken after the last probe (the settled state) | Build |
| `--link-copy` | the run's private `mods_source` copy is hard links (the spawn scene is unlinked before it is edited); `pak_overlay` keeps a pak member that matches the project's bytes as a hard link (`keptLinked`, 1231 of 1317 Mammoth members): a run costs ~0 disk instead of ~1.6 GB | Build; no kit file changed through the links in launch 1 |

| Launch | Run | Result | Grade |
|---|---|---|---|
| 1 | RC60 (2adf6d7a) parked | Scene loaded and the truck became current (~117 s); readback and probe checks ran at rest. The first input step `state.isEngineOff.Set(false)` then crashed the engine: `ssl game crash` "Shaker hasn't been found. (EngineStart)" (`PropTruckShakerNativeController.StartShaker` from `BlueprintNodeTruckShaker.Play` on `OnEngineStarting`). The Mammoth class plays shakers "EngineStart" / "EngineShutdown" but its `prop_truck_shaker_native_controller` is empty. 0 probe samples | Game (engine headless) |
| - | RC61, RC62 | not launched under the first approval (stop on a failed launch, no relaunch) | - |
| 2-4 | RC60, RC61, RC62 parked, **engine off** (second approval, "3 runs engine-off") | All complete: 362/363/355 samples at about 9 Hz, about 2.5 min each. `terrain` and `linear` passed their checks on RC61 and RC62. Readback confirmed each build: layers, motors and prismatic limits. No kit file changed through the links. Results: `C:\RC_RE\bench-headless\mammoth\results.md` | Game (engine headless) |

Mammoth facts for later benches (Game):
- Markup constraint names are `<child body>|<parent body>`, e.g. `BoneSuspFrontLeft_cdt|BoneChassis_cdt`.
- `GetCurrentPosition` of a prismatic with `childRotation [90,0,0]` is + = down (droop). It matched the body offset
  to 1 mm.
- The chassis body's `GetForward` is world-down. The bench's hull pitch therefore reads -90 at rest, and its
  roll/pitch are in a rotated frame (positions, heights and joints are unaffected).
- A truck that falls off the pad makes the pad-height depth meaningless: check the positions.

**Pitfall: engine start can crash the editor engine.** A truck whose blueprint plays a shaker the class does not define
dies on `isEngineOff.Set(false)`. Before an engine-on scenario, check the class: every
`BlueprintNodeTruckShaker.shakerName` must exist in `prop_truck_shaker_native_controller`. Otherwise leave the
engine off (`"engine": false` sends no engine statement).

## Scene, play mode, truck, screenshot (`scene` command; Build with the fake, not yet run live)

Recipe and evidence: `C:\RC_RE\research\scene_play.md`.
- **Messages.** Scene loading, play and viewports are SSL handlers on the IntegrationStudio callback
  `Game editor`. The hub now opens that connector next to ExecSsl (`editor_attach`: it mirrors the
  engine's own passports, plus the Manager listener) and sends what IntegrationStudio sends on connect
  after its Play button restarts the engine:
  - `MinimizeEditorOnDeactivate(false)`;
  - `StartFrameSharing(0, w, h, 0, 0, w, h, true)`: creates viewport 0; without it nothing renders, the
    likely reason smoke_003 got no PNG;
  - `LoadScenePlay(name, scene PS, res tag, .resource text, false, "localhost", "")`.
- **Completion signals:** `FrameShared`, `LoadingsState("Scene",1,"Loaded")`, Manager `Scene Changed`,
  then ExecSsl level name and `TruckManagerRb.TryGetCurrent()`.
- **The truck** comes from `--set "/DbgVars/Game/Startup/Start at truck on scene" true` (the RC3 bench
  project's xgine-arguments) and a scene that contains a `setAsStartTruck` truck.
- **Project scenes** need a private `editor.cfg` that references the game's and sets `external.ModsSourceLocal`
  (the RC3 project's form). `--set /Config/external/ModsSourceLocal` did not change the layer in smoke_003.
  `--strategy project-copy` now writes that cfg and passes it with `--cfg`.
- **GPU:** `--adapter-id 1` was the RTX 4060 in the RC3 runs; 0 is the Intel UHD. The command prints
  the engine's adapter list (`adapter` in scene.json).
- **Keep the connector open.** The engine exits 3 s after its last `Game editor` connection closes.

```text
python -m roadcraft.bench_headless scene --out <new folder> --owner-approved "..." [--scene xscenes/mods/<x>/<x>.scn]
    [--mode play|edit] [--via editor|ssl] [--scene-ps file|empty] [--ready-timeout 300] [--settle 5]
    [--force-current-truck] [--no-start-at-truck] [--wall-clock 900]  + the common options
```

Output: `candidate/scene.json` holds the steps (first reply, editor attach, frame shared, load sent,
scene loaded, ready with level/truck times, screenshot), the adapter list and the editor state before and
after. `session.json` holds the client snapshot (`clientsBeforeEditor`) and every engine->editor message
(`editorMessages`). `scene.png` is the screenshot.

## Pitfalls

- `dotnet build` is run with `-nodeReuse:false -p:UseSharedCompilation=false` so no MSBuild or
  compiler server outlives the build (they would be killed as orphans by the quiet job).
- The venv `python.exe` is a redirector: the process that registers with the hub is its child. The
  session therefore matches clients by every PID in the engine's job, not by the first PID.
- The ExecSsl round trip through the SDK hub takes about 90 ms on this PC (Build, fake engine), so
  probe rates above about 10 Hz are not reachable with one request at a time.

* The engine registers its console listener seconds after start, long before it answers: scripts
  are only executed once preloading ends (~100 s on the laptop). `first_reply` polls for up to
  180 s; a timed-out read-only script is harmless.
* `RequestConnect(string)` in Saber.ConsoleTre is broken on .NET 8 (DnsEndPoint); use the IPAddress
  overload.

## Code

`src/roadcraft/engine.py` (command line, layouts, gates, hub client, `EngineSession`),
`src/roadcraft/pak_overlay.py` (a built pak over an editor project copy),
`src/roadcraft/bench_headless.py` (scenario, SSL, timetable, analysis, capture, CLI),
`integrations/consoletre-hub/` (helper), `src/roadcraft/quiet.py` (`priority=`, `pipes=`),
`tests/test_engine.py`, `tests/test_bench_headless.py`, `tests/fake_engine.py`.
Research: `C:\RC_RE\research\engine_protocol.md`, `focus_dialogs_native.md`, `prior_notes.md`,
`physics_semantics.md` Q-d; decompiled `C:\RC_RE\decomp\Saber.ConsoleTre`.
