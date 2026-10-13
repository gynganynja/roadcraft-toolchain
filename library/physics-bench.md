# Physics bench: measure before installing

A change to suspension, wheels, body masses, centres of mass or joints can make a vehicle drive
worse even when the library's formulas say otherwise. KGS-25 fix 1 was designed from the
suspension formula and installed unmeasured; the owner reported "it does it worse now" (Game,
2026-10-02). The bench measures such a change in the Mod Editor first, on a copy of the mod, and
compares it with the installed version.

A windowless variant without IntegrationStudio, with a private mod folder per run, is described in
[headless-bench.md](headless-bench.md) (not yet run against the real engine).

**Ask the owner first.** Each run starts the editor and its engine for about three and a half minutes and takes
the GPU, the CPU and window focus. The launcher refuses to start while the game or another editor
runs. Bench results are evidence of grade Game (editor play mode) on a flat pad; the owner's drive
in the retail game remains the acceptance.

## Set up a bench (once per mod)

```text
roadcraft bench init --bench <a folder of your own> --project <mod editor project> \
    --data-dir <editor data> --profiles-dir <editor profiles> --editor <IntegrationStudio.exe> \
    --scene xscenes/mods/<scene>/<scene>.scn --vehicle <object name in the scene> \
    --class autogen_dw/trucks/auto_<truck>/auto_<truck>.cls --markup models/mods/<tpl>.tpl.asset/<tpl>.tpl_markup \
    [--wheel contact=autogen_dw/trucks/auto_<truck>/auto_wheel_<truck>_contact.cls ...] \
    [--sdk-editor-dir <SDK root>/tools/bin/ModEditor]      (default: sdkRoot of the machine configuration)
```

It copies the project's `mods_source`, `.project`, `game_launcher.cfg` and `config/*.cfg` into
`<bench>/project` with the project's absolute paths rewritten (both slash styles; `leftoverReferences`
lists any it missed), copies the editor data and profiles, and writes `play.scenario` (open the scene,
start the engine, play, echo `BENCH_GAME_MODE_READY`, hold 30 minutes) and `bench.json`. The source
project is never written. Add `"hull"` and `"frames"` (body names) to `bench.json` when the hull is not
`BoneChassis_cdt` or the frames are not named `*TrackSusp*`, `*TrackFrame*` or `*Bogie*`.

The scene should be a flat static pad with the vehicle on it. KGS-25 used its acceptance scene
with the crane at (0, 60.12, -18).

## Describe a variant

A variant is a JSON file of changes to the pristine project. The first apply keeps pristine copies
in `<bench>/pristine`, and every apply starts from them, so variants never stack. KGS-25 fix 2:

```json
{"axles": {"Fixed": {"min": 0, "max": 0, "height": 0, "strength": 1, "damping": 0.85},
           "Contact": {"min": 0, "max": 0.4, "height": 0, "strength": 0.001, "damping": 0.3}},
 "tracks": [{"track": 0, "wheelIds": [0, 1, 2, 8], "fakeWheelIds": [3, 4, 5, 6, 7]},
            {"track": 1, "wheelIds": [9, 10, 11, 17], "fakeWheelIds": [12, 13, 14, 15, 16]}],
 "slotAxles": {"kgs_L_contact0": 0, "kgs_L_contact6": 0, "kgs_R_contact0": 0, "kgs_R_contact6": 0},
 "bodies": {"BoneChassis_cdt": {"mass": 9900, "com": [0, -1, 0]},
            "BoneTrackSusp_L_cdt": {"mass": 7500}, "BoneTrackSusp_R_cdt": {"mass": 7500}}}
```

| Key | Changes |
|---|---|
| `axles` | `suspensionAxleCollection` entries by their `suspensionCollectionMap` name; listed fields only (min, max, height, strength, damping), the rest take the engine defaults |
| `tracks` | the n-th track's `wheelIds` / `fakeWheelIds` |
| `slotAxles` | a wheel slot's `suspensionCollectionAxleIndex`, by `geomName` |
| `wheels` | top-level `prop_truck_wheel` fields of a wheel class named by `--wheel` (mass, isSoftContactEnabled, softForceScale ...) |
| `bodies` | markup body `mass` and `hkCenterOfMassOffset` (engine axes, Y up) |
| `spawn` | the vehicle's position in the scene |
| `constraints` | markup constraint fields by constraint `name` (angleStart, angleEnd, minLimit, maxLimit, massFactor ...); `motor` = {tau, damping, maxForce, ...} edits its motor block |
| `steering` | a `controllableSteeringConstraints` entry by `constraintName` (angularSpeed, minAngle, maxAngle) |
| `truck` | top-level `prop_truck_rb` scalars of the compiled class (maxSteerSpeed, pedalsResponsiveness ...) |

An empty file (`{}`) leaves the copied project unchanged; when that is the installed version, run it as
the baseline.

## Run and read

```text
roadcraft bench run c03.json --bench <bench> [--schedule harsh]     one variant
roadcraft bench batch c03.json fix2.json --bench <bench>             several, then restore the pristine project
roadcraft bench apply fix2.json --bench <bench>                      patch only (no file: restore)
roadcraft bench analyse <run folder> ...                             re-analyse recorded runs
roadcraft bench compare <run folder> ...                             phase tables side by side
```

Each run folder (`<bench>/runs/<name>_<schedule>_<HHMMSS>`) keeps `variant.json`, `launch.json`,
the editor's `stdout.log`, `series.jsonl` (every body's position and axes and every wheel's spring
travel, position and ground flag, about 10 Hz), `inputs.json` and `summary.json`.

| Schedule | Phases (start second: input) |
|---|---|
| `normal`, 64 s | 0 rest (handbrake) - 10 forward 0.35 - 14 stop - 22 pivot + (pedal 0.3, steer 0.8) - 26 settle - 36 pivot - - 40 settle - 50 reverse 0.35 - 54 final |
| `harsh`, 56 s | 0 rest - 6 fast (pedal 1) - 14 brake - 20 full lock + (pedal 0.6) - 25 settle - 31 full lock - - 36 settle - 42 fast reverse - 48 final |

The probe also records, per sample, the gear, engine rpm, handbrake, engine-running and brake flags
(`engine`), each body's engine-side mass and centre of mass (`mass`, `comLocal` in the body frame, Y up)
and per wheel its spin (rad/s), its own forward speed, physical radius, mud depth and terrain flag
(`parse_series`). These found WALL-E's faults: a stalled drive shows rpm at idle + pedal x 250 with every
wheel at 0 rad/s; a markup centre-of-mass form is checked by reading `comLocal` back; body speed / wheel
spin gives the real rolling radius (WALL-E 2026-10-04).

Per phase the summary gives the hull's largest roll and pitch and their ranges (deg), its height
range and its median height against rest (mm), the largest frame-to-hull twist (deg), the largest and
mean spring travel, and the most wheels off the ground. `motion` gives each driven phase's yaw,
distance and top speed up to 1.5 s after it ends: a steady variant that no longer turns or drives is
not a fix.

What the KGS-25 numbers looked like (normal schedule, pivot +): candidate 03 rolled 3.97 deg with a
73 mm height range and turned 35 deg; fix 2 rolled 0.16 deg, 3.4 mm, and turned 53 deg. **A wheel's
ground flag is not proof of support:** candidate 03's wheels reported ground while their track sank
19 cm into the pad; read the hull height and the frame twist. Raised real idlers and sprockets
count as off the ground in every phase.

## Pitfalls (Build)

- The launcher's console window must not be captured through a pipe: the editor inherits the pipe
  and the call never returns. `physics_bench` writes its output to `launch.stdout`.
- The probe and input scripts need absolute output paths ("Absolute new output report required").
- The console receiver sometimes times out an input registration; each input is tried three times
  with a 5 s timeout, and `inputs.json` records the attempts (`inputsApplied` in the summary).
- A run can stall at the scenario's `wait-viewport`; the launcher gives up after 10 minutes and the
  run fails. Run it again.
- The editor may ask "Send errors from past sessions?" after a crash; the launcher answers Later
  (nothing is sent).
- Spawning the KGS-25 on the acceptance scene's deformable terrain crashed the engine for every
  variant: keep to the pad.
- Sampling reaches 7-10 Hz, not the requested 25 Hz; the analysis uses the recorded times.

## Code

`roadcraft.physics_bench` (patchers, bench folder, runs, analysis; checked byte for byte against the
KGS-25 bench script on its ten variants and against its five recorded summaries) and
`integrations/physics-bench/` (`launch_editor.ps1`, `series_probe.ps1` - read-only through the
editor's ExecSsl receiver, `input_override.ps1` from the Roamer 105 port). The KGS-25 bench and its
runs are kept in that mod's drive-fix workspace (`drive_fix/editor`).

## Vanilla reference and drive-feel plans (Kanga 25 project bench, 2026-10-10)

`kanga25_mod/tools/bench/crane_bench.py` extends the shared bench: `BENCH_REF=baikal` swaps the scene vehicle for the
retail prefab (`res://ssl/autogen_designer_wizard/trucks/auto_<truck>/<truck>_prefab.prefab.resource`, type
`<truck>_prefab`, desc `auto_<truck>`) after the variant restore and maps body names, so every metric compares like for
like; plans `kdrive` (launch, brake, slalom, reverse), `accel` (full throttle down a clear lane) and `cruise`; variant
keys `x_gears` / `x_torque` patch the compiled gearbox; the sampler logs `GetGear()` and `GetCurrentEngineRpm()`
(`trace.py` prints shifts and downshifts under pedal); `cmp.py` prints angular rate, angular jerk (sample-to-sample
change of angular velocity) and wheel-travel step per window - jerk and wheel step separated the "glitchy" Kanga from
the vanilla Baikal when plain angular rates did not. Single runs are noisy: repeat before trusting a difference. The
retail Baikal articulates +-60 at 43 deg/s and leaves the 60 x 100 m pad in the kdrive slalom after ~21 s.

## Straight driving and stationary belts (WALL-E follow-up, 2026-10-05)



Use `--schedule straight` for 20-second forward and reverse inputs with zero steering,

at pedal 0.35, separated by parked periods (80 seconds total). Use

`--schedule straightfull` for the same schedule at pedal 1. Keep matched full-pedal

baselines and results separate from partial-pedal comparisons; the short `harsh`

bursts alone do not validate sustained full-throttle tracking. The CLI derives its

choices from these shared schedules. `--schedule idle` tests handbrake-off

rest and settling after short forward/reverse drives (76 seconds). The `stability`

summary excludes the first two seconds and final second of each phase and checks the

observed pedal, steering and handbrake. It records displacement, maximum cross-track

deviation from the initial heading, unwrapped heading change/range, hull-height range,

maximum wheel spin and fraction of wheel samples reporting terrain. Missing telemetry

is unavailable, never evidence of zero movement. Insufficient samples are explicit.

Implementation: `bench_stability.py`; regression tests: `test_bench_stability.py`.



**Game (isolated native editor), WALL-E r2:** the earlier four-second drive and hull-roll

checks missed persistent wandering. The package-matched `baseline_straight_034400`

recorded 2.04 m maximum cross-track error over a settled 15.72 m forward displacement,

with 27.88 degrees heading range at zero steering. Fixed-camera native framebuffer

captures from `baseline_idle_035713` show belt shape changing while the chassis and

physical wheels are stationary. Wheel telemetry alone cannot validate animated belts:

retain a stationary image sequence as separate visual evidence. Rain and temporal

rendering affect pixel differences, so do not treat image difference as a universal

pass threshold. Evidence lives in the WALL-E project's `stability_20261005/`.



**Correction:** this WALL-E scene is terrain contact (`onTerrain` true in every wheel

sample), despite the earlier 'flat pad' description. Scene names do not establish

contact type. This does not revise the separate KGS-25 static-pad measurements.

Candidate measurements remain distinct from the owner's retail-game acceptance.





The summary also includes `stabilityWholePhase`, measured across the complete

contiguous observed control run, with no launch trimming. **Correction:** earlier

versions still clipped this to nominal schedule boundaries. Probe registration and

input writing have separate clock origins, so even a subsecond mismatch could omit

launch and change the initial heading. The nominal window now locates the matching

input run, then analysis extends to its observed transitions. Fragmented matches

report `ambiguous_observed_phase` instead of selecting a favorable fragment.

`stabilityPlannedWholePhase` retains the old nominal calculation; `stabilityObserved`

applies settling margins to actual observed transitions. Historical WALL-E reports

were retained and recalculated separately into `observed_phase_summary.json`. Compare both windows: WALL-E rear-only support could travel straight

after its initial reverse kick, making the settled lateral error look much smaller than

the whole-drive deviation (0.486 m versus 2.638 m in `stable_candidate_straight_060258`).

Each window uses its own initial heading; their lateral values need not be ordered.

The regression `test_whole_phase_retains_launch_kick` covers this failure mode. Gear labels

describe the requested mode; these filters do not assert that the actual gearbox has

already shifted. Inspect raw gear telemetry when testing pure steering after reversing.





### Confirm the surface before comparing handling



**Game, WALL-E 2026-10-05:** original r2 was much straighter on a separate

native static platform than on the original SDK-template terrain. An inline

game_object with an iactor descriptor, Geom and PropPhysBody can provide a

RigidBodyShape / phys_shape_box; use rigid-body behavior Static while keeping

the editor actor non-static so its initialization runs. The diagnostic box was

256 x 256 x 1 m, centre Y44.5, with friction 1 and restitution 0. Its four-wheel

park/partial/full runs all recorded ground contact, no terrain contact, and

hull height near Y45.018. Full construction and verification are retained in

the WALL-E investigation's `pad_fixture.py` and

`reports/static_platform_baseline.json`.



The fixture's name or authored geometry is insufficient: require native support

height, ground/terrain flags and complete wheel telemetry. Include the scene-art

file in each snapshot and restore it for original-terrain runs. Keep static and

terrain measurements separately labelled; do not apply cross-fixture baseline

ratios or declare a repair from an unchanged vehicle's improved surface.



The finite-travel `stable_fake_sprung_straight_084525` trial crashed before

driving; it does not establish fake-wheel handling. Its automation log printed

BENCH_GAME_MODE_READY after the engine disconnected and then skipped through

remaining commands. The launcher's process/readiness check correctly rejected

it. A marker alone is not readiness, and the Wwise leak assertions emitted at

shutdown do not identify the crash cause.





The observed-window correction has five additional regression tests (25 total

bench tests, plus 9 workflow tests passing). Its recalculated r2 whole baseline

is 2.244 m lateral over 18.364 m forward and 2.111 m over 14.016 m reverse;

the older settled values above remain separately labelled. Keep achieved gear

and speed history: the same 0.35 pedal input left one WALL-E run in first gear and

shifted another through third. Input equality alone does not mean equal speed.





Native terrain type and geometric flatness are separate checks. WALL-E's rocky

looking template terrain returned identical world height 42.499123 m, upward

normals and zero extrusion at 231 points across X0..10/Z0..50 m, while wheels

reported terrain contact. Use the installed SDK's Terrain.GetHeight/GetNormal/

GetExtrusion/GetMaterial APIs to record sample positions, spacing and limits;

texture appearance alone does not establish bumps. This remains a terrain

fixture, distinct from the static-box benchmark. Evidence: WALL-E stability

reports/terrain_grid.json and its pinned raw reply (2026-10-05).





### When readiness stalls: inspect the native log



**Game (WALL-E, 2026-10-05):** IntegrationStudio stdout can stop after scene

loading while the native engine is already showing a crash. Read the configured

engine sandbox's `xgine/logs/log.txt` and its `logs.bakN` rotations; preserve

the matching launch-time log before another startup rotates it. Search for

`ap/assert` and retain the assertion context. In WALL-E, this exposed a track

roller X-alignment assertion and a zero-active-rollers assertion absent from

the captured studio stdout. A timeout alone does not identify either cause.

See the [case study](../docs/case-studies/walle-stability.md). Sandbox paths are

configuration-dependent; do not hardcode a machine's SDK path in shared code.





### Distinguish direct physics inputs from controller smoothing



**SDK (2026-10-05):** `game/truck/prop_truck_view_controller.ssc`

`DbgUpdateInputs` assigns `truck.input.pedals` and `truck.input.steer` directly.

The normal `UpdatePedals` uses `pedalsResponsiveness` in a LerpFloat and

`UpdateSteering` applies steering rate logic. The bench's `-Method Debug` is

therefore a direct-input stress test; changing those controller smoothing fields

cannot be validated through that override. `-Method State` requests normal

controller state, but verify sustained actual inputs before relying on it.

Preserve the input method in evidence and compare matching methods. When testing

a ramp, include its complete launch: selecting only samples already within the

target-pedal tolerance can omit the ramp. See the WALL-E case study. Native

State-method persistence was then verified on original-size WALL-E r2

(`r2_state_path_stateprobe_142617`): target pedal held across a9m drive; the

following partial/full schedules applied5/5 inputs each. This verifies that

session, not every game's controller or input-focus configuration.



`stabilityBrakeBounded` now measures straight throttle ramps using observed

handbrake boundaries, seeded by target pedal and requiring straight steering.

Only alternating handbrake protocols are supported; missing target pedal is

unavailable and disjoint/missing brake telemetry is ambiguous. Original

constant-input windows remain available. Compare both: each starts with its own

heading, so either lateral maximum can be larger. Six ramp-window regressions

pass alongside the25 existing bench tests and9 vehicle-workflow tests.





### Use a stock control without replacing the repair baseline



**Game (WALL-E investigation, 2026-10-05):** unmodified EPEC TC-305 on the same

terrain and normal State controls held heading within1.64deg over61.45m

forward and1.59deg over47.79m reverse. Its explicitly separate first20m

comparison had0.131/0.166m lateral maxima. This gives context for WALL-E's

larger heading swings; different size, mass, wheel layout and speed prevent a

unique causal attribution. Preserve the full control windows and exact stock

resource/scene identities. A shorter distance comparison is not permission to

trim the mod's whole-path acceptance windows or replace its installed baseline.

Evidence: WALL-E stability retail_control/comparison.json and the linked

[case study](../docs/case-studies/walle-stability.md).





### Separate a static mesh from a suspected animated-belt defect



**SDK/Game, WALL-E native editor (2026-10-05):** after completing telemetry,

fixed-camera captures using `Geom.HideObj/ShowObj` for the named frame and

`Geom.Hide/Show` for the body distinguished static frame detail from the

animated running gear. Restore visibility and retain whole/isolated/restored

images plus the exact commands. This is diagnostic rendering, not a geometry

fix or permission to hide an unwanted part in delivery. Ground occlusion and

shadows can still prevent a complete belt assessment. WALL-E's apparent lower

bunching included static frame detail; the remaining obscured belt was not

promoted to a broken-loop conclusion or visual acceptance. Evidence:

`reports/longtrack_visibility_isolation.json` and the WALL-E case study.





### Matched axle variants and finite test pads (Y61, 2026-10-06)



**SDK/Game / Build:** physics_bench.patch_axles replaces each named SuspensionAxle entry; omitted fields take engine defaults, as its docstring states. For a matched ride-height comparison, retain min, max, strength and damping and change only height. Y61's first wrapped variant failed before launch; its subsequent height-only variant loaded but was invalid as a matched reference. Preserve both rather than interpreting either as a measured lift. The v3 fixture explicitly copies all five fields.



Y61's 80-second straight schedule drove 148 m and crossed a 256 m pad centred near the spawn, landing on terrain roughly 2.5 m below. Native terrain flags and airborne samples identify that transition. Keep it as transition evidence and repeat on a 1024 m pad for one-surface handling. Compare whole control windows and cross-track/yaw range, not only final heading. Evidence: WatcherY61_Final `native_tests/long_drive_result.json`, `scene_art_256m.scn`, `zero_extra_lift_v3.json` and native-remaining-suite-v1 recipe. Do not silently alter a fixture or variant during a pinned job; prepare a new immutable recipe.





### Roamer ute fixture and input identity (2026-10-06)



**SDK/Game / Build:** SDK YAML can fold an absolute project path at a space. Literal replacement left Roamer's copied bench pointing at its authoring project. physics_bench._rewrite_bytes now recognizes whitespace-folded occurrences while preserving unrelated SDK paths; FoldedBenchPathTests covers slash and Windows path forms. All 647 configured tests ran successfully (seven skipped) before the later reverse-control correction.



The scene prefab was not the selected truck: the default Minuteman was current. Explicitly list trucks, select the intended scene instance and verify its truckName before measuring. Preserve the wrong-vehicle run as excluded evidence. The task runner implements this gate. A general selector is deferred because scene-instance, spawned and branded actor naming need distinct supported contracts.



DbgUpdateInputs copies its acceleration override directly to signed truck.input.pedals. The earlier positive-pedal REVERSE schedule travelled forward despite its phase name. Preserve those series as forward driving, not reverse proof. The shared five reverse schedules now use negative pedal, with ReverseScheduleTests; the configured full suite passes 648 tests (seven skipped). Native ordinary State input confirmed gear -1 and negative forwardVelocity, and exercised the reverse/brake callbacks bypassed by debug input. See the existing Y61 ordinary-control lesson in cockpit-and-lamps.md. Input acknowledgement and an absolute moved-distance metric alone do not establish driving direction.



Long nested bench paths exceeded the native preview resource path limit and failed CreateFile with error 3 even with an existing preview directory. A shorter immutable bench path loaded (longest generated path 226 characters). Do not assume every code-3 failure has this cause. Evidence: Roamer105Ute_20261005/native_validation, R105Bench_20261006 and R105Final_20261006 retained logs and identity receipts.





### Jimny fixture failures (2026-10-06)



**Build:** play-mode fixtures require the full SDK editor data, including `ModEditor/.project`; the isolated generator profile data alone stalled before Xgine UI initialization. Canonicalize source/bench paths before substitutions, so a sibling path containing `..` does not leave runtime configs pointing at the source snapshot. The fresh Jimny fixture removed the auto-select-at-start flag and verifies its selected prefab/truck identity explicitly. The missing `game_launcher.cfg` warning also occurs in successful Roamer runs; it did not diagnose this failure.



**Game, startup failure:** Jimny then asserted in `PropTruckWheel.InitNative`: deforming object `tire` missing on `jimny_wheel`. Renaming the recovered wheel objects to native `tire`/`rim` fixes the proven reference mismatch. Presence is checked statically by RC049; native retesting determines whether startup succeeds. Evidence: Jimny `J31TestC_20261006/runs/baseline_normal_075503/native_assert_log.txt`, retained failed launch; `tools/create_models.py`, `tools/validate.py`, `tools/prepare_bench.py`. A viewport disconnect during Play can be the normal engine restart; inspect the subsequent engine and assertion logs before calling it a crash.



**Correction, Jimny native follow-up:** the debug signed-reverse schedule selected gear -1 but barely moved (0.03–0.07 m); ordinary State/AUTO negative pedal immediately produced negative forward velocity and real reverse movement. Do not infer a vehicle gearbox fault from this debug-only result. The ordinary final normal run moved 6.86 m in reverse, and its 20-second full-pedal reverse moved 52.59 m. Keep the debug baseline and ordinary results as different control protocols. Existing signed-debug schedule regressions do not validate this vehicle's reverse FSM. No global schedule change was made; per-project ordinary-control wrapper retains native inputs/gear/spin evidence.



**Game, loaded stance calibration:** Jimny's factory-plus-4-inch authored roof was 1.8663 m, but the initial neutral spring height of 0.16 m added another 77.75 mm front / 50.58 mm rear in the engine. Project wheel positions transformed into the live body frame expose this extra offset: 0.3937 minus measured wheel-local Y. Adjust front/rear neutral height by their observed mean offsets while preserving absolute stops `height+min=-0.13`, `height+max=0.30` and the original strength/damping. The final rest is within 4.1 mm per wheel and 0.58 mm in the mean of the authored reference; all four radii are 0.393700004 m, widths 0.2667 m, contacts true. This is a source/body-frame calibration on deformable SDK terrain, not an independently measured stock vehicle or a universal beta. Evidence: Jimny reports/native_loaded_{baseline,final}.json; J31TestE/F runs and stance.json.



**SDK/native helper transport, Jimny 2026-10-06:** sending Python's three vector
components as separate tokens after PowerShell `-File -Position` bound the first
component only and consumed later components as positional parameters (a Toggle
validation failure). Use a named invariant-culture CSV parameter parsed explicitly
to a validated three-component double vector, or a real PowerShell expression
with an array. Jimny's owned helper uses PositionCsv/TargetCsv; normal spawn and
camera receipts verify the fix. See J31TestF final_all_092833 failure and
final_services_all_093912 / final_views_all_094631 successful bounded retries.
No physics or installed package change was needed for this helper fault.
