# Physics bench: measure before installing

A change to suspension, wheels, body masses, centres of mass or joints can make a vehicle drive
worse even when the library's formulas say otherwise. KGS-25 fix 1 was designed from the
suspension formula and installed unmeasured; the owner reported "it does it worse now" (Game,
2026-10-02). The bench measures such a change in the Mod Editor first, on a copy of the mod, and
compares it with the installed version.

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

