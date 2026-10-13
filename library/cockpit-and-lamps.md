# Cockpit instruments and lamps



## Steering wheel and gauges: `dataDashboard`



```text

dataDashboard = {

   isEnabled = True

   dashboard = {

      Speed = { nameBone = "ctrl_dashboard_speed", axis = "Y", minRotationAngle = 0, maxRotationAngle = 270,

                dashboardSubtype = "SPEED", damping = 0.5, scale = 1.5, __type = "DashboardElementCockpit" }

      RPM = { nameBone = "ctrl_dashboard_rpm", axis = "Y", maxRotationAngle = 240, dashboardSubtype = "RPM",

              damping = 0.1, __type = "DashboardElementCockpit" }

   }

   steering = { steering_wheel = { nameBone = "ctrl_steering_wheel", axis = "Y", minRotationAngle = -360,

                maxRotationAngle = 360, steeringSubtype = "WHEEL", __type = "SteerigElementCockpit" } }

   __type = "CockpitDashboardSetting"

}

```



| Rule | Grade |

|---|---|

| Each element turns its bone about the bone's local `axis` from the modelled pose; subtypes seen: SPEED, RPM, FUEL, ENGINE_ENABLED; switchers DIFFLOCK, ENGINE_ENABLED; steering WHEEL | Retail (Armiger) |

| The Armiger's instrument bones have native Y pointing forward, away from the driver (along the column / out of the dial) | Retail |

| `scale` multiplies forward velocity before normalization by final target km/h; see the native-source correction below | SDK |

| Model needles at the dial's zero mark, or turn them there in the build: a needle modelled pointing up rests at mid-scale | Build (buggy); rotation direction awaits a drive |

| Keep only the steering wheel rim and hub on `ctrl_steering_wheel`; a lower column that is not coaxial wobbles | Build (buggy) |

| The compiled class carries it as `prop_cockpit_dashboard` | Retail, Build |



## Exterior lamps and beacons with `roadcraft.lamps` (start here, 2026-10-02)

The lamp recipe that has worked, as shared code (`src/roadcraft/lamps.py`; Blender side
`blender_lamps.py`) and checks (`lint-bro` RC037-RC039). The sections below keep the history and
evidence of each step.

1. **Lenses.** Each lamp is an unlit lens mesh named like retail lamps (`head_lights`, `tail_lights`,
   `reverse_lights`; no `_lp_` prefix) on an opaque `vehicle_body` instance, plus a coincident lit copy
   `<name>_on` (`blender_lamps.lit_copy`) on a `vehicle_lights` instance; the stop state is its own copy of
   the tail lens, `brake_lights_on`. Do not put glass and opaque lamp parts on one texture in one object:
   the exporter keeps one material per texture (`lamps.material_conflicts`, build-pipeline.md).
2. **Strobes and beacons never switch the unlit lens.** Flash a lit overlay: the lens pushed 1 mm out along
   its normals (`blender_lamps.lit_shell`) over a lens that stays, as the CAT 793D's strobes switch only their
   emitter objects. Swapping the lens with its lit copy made the mesh disappear and reappear instead of
   glowing (L275 v7, Dump Twuck v4).
3. **Accessory lenses** (a light bar's stop/tail or reverse lens) join the existing lamp object of the same
   LOD as another material slot (`blender_lamps.join_lens` renames the UV channel first), so the existing
   states switch them.
4. **Markup.** Lit copies and overlays stay default-visible: no `objSettings` visibility entry. Hide only
   helper geometry that must never render (`sfx_exhaust_*`, `sfx_radiator_haze` faces). The graph's init
   hides the lit copies.
5. **Materials** (`lamps.lit_material`, `unlit_material`, `EMISSION`): the Lada's headlamps 80 / bloom 4, tail
   8 / 1 with tint [255, 255, 12, 3], brake 45 / 2, reverse 45 / 2; the L275 amber beacon 30 / 2, tint
   [255, 255, 140, 0]. The emission mask `<atlas>_em` must be bright under the lens UVs (L275 and Lada lenses
   0.3-0.9 mean).
6. **Beams** (`lamps.light_effect`, `LIGHTS`): `sfx_group` / `sfx_light_base` on empties at the lenses, aimed
   along native +Z (Blender -Y): head spot 65 degrees, 38 m, intensity 20, shadows; tail point 1.3 m / 0.14;
   reverse spot 100 degrees, 8 m / 1.2; amber beacon point 7 m / 0.6. Not auto-started: the states restart
   and stop them.
   **Head beam brightness (2026-10-13):** a player reported the Lada's headlights "far too bright" (Venk88, 6 Oct,
   Unverified). The 38 m / 20 head preset was tuned in the editor by day, never compared at night; retail scouts
   carry no beam emitter of their own (their `vehicleLightMaterials` Headlights entry drives the lighting), so there
   is no retail number to copy. Lada v11 uses 32 m / 8, matching the Dump Twuck low beam (35 m / 8; high 60 m / 12).
   Lens glow 80 / bloom 4 is within retail (Lynx headlamps 80, Crayfish 50 / bloom 20) and was kept. The kit's
   `LIGHTS['head']` preset still holds 38 / 20 (KGS 25 and Kanga 25 use it); pass overrides until a drive confirms
   the lower value.
7. **Graph** (`lamps.lamp_states`, the Lada's): engine started, running when loaded (0.5 s schedule), shutdown,
   brake pull / release, reverse / released; init shows the unlit lenses and hides every lit copy.
   `lamps.flasher(prefix, [overlay], effects=..., pattern=SINGLE_FLASH | DOUBLE_FLASH)` returns one-shot
   `BlueprintNodeTickTimer` nodes that restart each other plus the inputs for the running branch and for the
   stopped branch and init; `lamps.exterior_lights(anchors, flashers=...)` composes everything, and
   `roadcraft lamps SPEC.json --output X.bro` writes it as a BRO fragment. A class patched without the
   generator takes the graph and effects verbatim (build-pipeline.md, lamp-graph sync).
8. **Checks.** `lint-bro` reads the body markup beside the compiled model, so the shared vehicle checks cover
   every build and test: RC037 a lit copy hidden by the markup, RC038 a lit copy left visible at init, RC039 a
   strobe that hides the unlit lens. On 2026-10-02 they flagged the Dump Twuck v4 (RC037 for four lit copies,
   RC039 for `blue_beacons`) and the L275 v7 package (RC037, RC039 for `beacon`); the L275 v9 and Lada
   projects are clean.

| Rule | Grade |
|---|---|
| Lens states, the engine / brake / reverse graph and the Lada emission values | Game (Lada) |
| A strobe is one-shot tick timers switching an emitter while the lamp body stays | Game (CAT 793D RC20) |
| Lit copies default-visible in the markup, hidden at init | Game (Lada works this way). That the markup flag kept the L275 v4-v8 and Dump Twuck v4 lit copies dark is Inferred from both owners' drives (same flag, same symptom) |
| Lit shell over a lens that stays, 0.4 s on / 0.4 s off; double flash 0.08 / 0.10 / 0.08 / 0.55 s | Build (L275 v8/v9, Dump Twuck v4 timing); owner drives open |

Evidence: `tests/test_lamps.py` (graph states, flasher chains, findings on a Dump Twuck v4 replica, CLI);
L275 `tools/exterior_effects.py`, `accessories.py`, `reports/lights_v9/completion.json`; Lada
`tools/exterior_effects.py`; dumptwuck_mod `tools/exterior.py`; CAT 793D RC20 `GreenStrobe_*` nodes.

**Using the kit from a project (Dump Twuck v5, its first consumer, 2026-10-02; Build).**
Import it from the checkout that `local/toolchain.json` names (`sys.path.insert(0, TOOLCHAIN/'src')`),
in the BRO tools and inside Blender 5.0, whose Python 3.11 imports both modules. Pin
`src/roadcraft/{__init__,lamps,blender_lamps}.py` as recipe inputs, so a kit change shows in the
receipts and cannot change during a build. Make lit copies and shells per LOD from each decimated
lens LOD: faces then match the lens at every LOD, where a copy decimated on its own could drift off
it. `light_effect(anchor, role, **overrides)` takes whole `sfx_light_base` fields (`RadiusCtrl`,
`Intensity`, `ColorCtrl`, `spotAngle`, `enableSM`), which carries project beam values;
`lamp_states(reverse=None)` keeps reversing floods for art without a reversing lens. Project checks
worth copying: `lamp_findings` on the compiled graph with the markup, `simulate` of init (lenses
shown, lit copies hidden), and "the beacon lens is never switched".

## Lamps that work in the retail campaign



The method proven on the CAT 793D (RC20) and the Apocalypse Buggy (headlights seen lit, Game):



1. Lamp meshes named as the game's own trucks name them, without the `_lp_` prefix

   (`reflector_headlights`, `tail_lights`, `marker_lights`, ...), on an opaque `vehicle_body`

   material instance (unlit state).

2. A coincident copy of each, named `<name>_on`, with a `vehicle_lights` material instance:



   ```text

   shaders = { glt_shader = { base = { params = {

      texDiff = "mod_x_lights"  texSpec = "mod_x_lights_spec"

      emissive = { intensity = 120  bloomIntensity = 8 }      headlights; tail lamps ~30 / 2

      tex = { emissiveTex = "mod_x_lights_em" }

   } } } }

   __type = "vehicle_lights"

   ```



3. Four `BlueprintNodeShowHideGeomObjects` nodes (show / hide the lit set, show / hide the unlit set)

   in the engine blueprint, wired to: `BlueprintNodeOnEngineStarted.OnEngineStarted` (lit on),

   `BlueprintNodeOnEngineShutdown.OnEngineShutdown` (lit off), `BlueprintCommonLibraryOninit.OnExit`

   (lit off), and `BlueprintNodeOnEngineRunningOnInit.OnEngineRunning` -> a `BlueprintTimeLibrarySchedule`

   (`startDelay` 0.5 s, stops itself) -> lit on, so a vehicle loaded with its engine running lights up

   after the blueprint's own init.



| Rule | Grade |

|---|---|

| The deprecated `BlueprintLibraryChangematerial` never renders (editor captures identical) | Build (CAT 793D) |

| Retail has no headlight key (only an editor debug hotkey), so lamps that follow the engine cannot rely on the `Headlights` light type | Game (CAT 793D) |

| Native `prop_vehicle_lights_material` brake / reverse states did not light in the campaign | Game (CAT 793D RC20) |

| RC21 drives brake and reverse lamps by show/hide on the brake pull / release events and `BlueprintNodeOnEngineReverse` (`OnEngineReverse` / `OnReleased`, the retail Bowhead's pattern) | Retail (pattern), Build (RC21 not yet confirmed in the game) |

| All 108 lit retail truck classes name lamp meshes without `_lp_` and give the unlit state an opaque `vehicle_body` instance; the SDK TUZ sample's lamp material is misspelt `lights_emmissive`: do not copy it | Retail, SDK |

| The engine's `Headlights` / `CockpitLights` material groups follow the engine running, not a switch: turn-signal lenses given a light role glow all the time, so leave indicators without one | Game (Roamer 105, editor play mode) |

| `BlueprintNodeShowHideGeomObjects` works in retail (the 793D's strobes, then its engine lamps) | Game (CAT 793D RC20) |

| Real beam authoring now exists in Roamer and Lada native SFX helpers; see the scoped evidence below before claiming a tested result | Build; Lada daylight native states/captures, night reach open |



## Source-fitted exterior effects (Lada v5/v6, 2026-09-30)



**SDK/Build; Game (isolated native editor):** inline `effects.propSfx.list`

entries can contain `sfx_group` / `sfx_light_base` spotlights. Attach the group

and light child to the fitted lens locator with `nameParent`, keep group

`isAutoStart=False`, and drive VfxRestart/VfxStop from engine events. Combine

them with ShowHideGeomObjects lens states. Rear brake state takes precedence

over dim running state; delayed engine-running-on-load handles init ordering.

V6 native probes observed running/off, braking and reversing states with normal

input. Daylight captures show head lenses on/off, red tails and white reverse

strips. Brake state was measured without a separate close-up brightness capture;

night beam reach and retail campaign behavior remain untested for this Lada.

No new key mapping was added. Red emission tint corrected v5's pink/white rear

lenses. Preserve original unlit lens art and controller joint identities.



**Corrected exhaust approach:** stock `part_exhaust_small_cars` uses

`local__parentArea` sources. V5 authored a 20 mm face at the source pipe lip,

but a started SFX, visible source face and amountScale=1 trial did not establish

a visible plume. A source surface alone is therefore not a proven recipe.

V6 preserves the stock root effect name/control graph, parents it to the fitted

`lnv_exhaust_outlet` empty, enables parent rotation, and overrides Smoke_Flow_2

with a point source aiming native -Z along the pipe. A 7-9/s flow, 0.4-0.8 m/s

initial speed, 0.8-1.2 s life and 0.045-to-0.30 m particle size made a small

visible plume at the real left rear outlet. The second large parent-area child

is disabled. These are Lada settings, not universal particle defaults.



**Game correction:** the final plume was visibly emitting while the SFX root

amountScale getter returned zero. Do not use that getter alone as proof of no

particles. Check actual captures, SFX state, emitter state and outlet alignment.

Likewise, physical Debug input overrides bypass normal movement-state events;

use the normal input State method to test brake/reverse blueprints and restore

neutral pedals/handbrake afterwards.



**Native startup correction:** v5's `visibility.__type="invisible"` had no

resource dependency and crashed during scene TPL markup loading. Replacing only

that brand reference with inline `tpl_markup_visibility_flags` containing

`visibleDefault=False` and `visibleInReflectionCubemap=False` allowed Play.

V6 uses those flags. Do not repeat the prior advice to use an unresolved

`invisible` brand. The unsupported geom-settings `collision` field was also

removed, but was not the isolated fix and is not identified as the crash cause.



Evidence: Lada `tools/exterior_effects.py`, `effect_geometry.py`, `audit_exterior.py`,

build-007/test-008, `revisions/effects_v5/native_diagnostic_result.json`, and

`package/candidates/lnv-exterior-20260930-v6/effects_result.json`. All 361 sealed

fixture files matched after the native run. Local audit checks concrete visibility,

fitted locator and compiled point-emitter limits; shared custom-trail checks are

separately wired. A universal exhaust/visibility validator is premature because

valid external brands and other emitter modes need not use this local recipe.







## Native cockpit and paired wiper clips (Lada v8, 2026-09-30)



**SDK/Build:** `dataDashboard` supports `BRAKE_PEDAL`, `HANDBRAKE`, `LOW_GEAR`

and `DIFFLOCK` switchers, plus a `GearStickElementCockpit` whose AUTO/REVERSE/

LOW_GEAR/HIGH_GEAR states rotate about two local axes. It follows driving modes,

not a manual H-pattern for every automatic ratio. The shipped Armiger uses an

RPM dashboard element for its accelerator pedal. The clutch is not implied by

that binding. `PropCockpitDashboard` updates these controls while the high-poly

cockpit is active; entering first person is part of a meaningful live check.



**SDK correction:** speed `scale` is not directly degrees per km/h. The native

controller reads absolute forward velocity times scale and normalizes against

the last gear's targetSpeedRangeKmh.y. For a dial spanning D degrees to V km/h,

use angular range D and scale `3.6 * finalTargetKmh / V`. Lada uses 270 degrees,

160 km/h dial, 42 km/h final target and scale 0.945. Confirm the result in motion;

this formula is grounded in the installed PropCockpitDashboard source.



**Build:** fit visual bones to source parts and decode their native local axes.

A bone pointing along the desired Blender rotation axis exports native local Z

opposite that axis. Keep shafts, boots and housings on appropriate separate

weights. Adding these visual bones does not add serialized controllable joints.

The Lada's needle cards used a separate opacity image but an opaque material;

tracing the supplied silhouette into real geometry exposes the dial markings

without changing the shared material or other texture bytes. Zero-align before

runtime rotation. The small gauges remain source-painted in this revision.



**SDK/Build:** wipers use two non-looping TPL actions with disjoint absolute frame

ranges, `tplAnimation.controller` entries, and enabled `truckRainSettings` with

matching forward/return clip names. Lada's source arms and blades sweep 52 degrees

about fitted windshield-normal pivots. Native auto mode checks rain, occupancy

and engine state, returns to park on stop, and adjusts pause to rain strength.

Animation-name metadata for this exporter is in `.tpl`, with the corresponding

`anim_list.json`; looking only in `.tpl_data` falsely reports missing clips.

Rain wipe shaders are a separate feature and are not required for blade motion.



The opt-in `native_cockpit.cockpit_animation_report` checks missing/competing

cockpit targets and missing/duplicate wiper clips. Seven focused negative/positive

tests pass; Lada wires it into its final validation with compiled TPL names.

Geometry fitting remains asset-specific in `interior_geometry.py` and

`audit_interior.py`. Evidence: Lada build-009 model export, build-011 preliminary

package, test-013 (169 checks), `revisions/interior_v8` and source script copies.

Native observations are recorded separately in the version's runtime review.





**Lada v8 live refinement:** the initial isolated run measured all nine native

cockpit elements. Stock RPM normalization at 1500 made an uncalibrated 8000-RPM

dial indicate mid-scale at 800 RPM. Use a 50.625-degree controller maximum for

this 270-degree, 8000-RPM dial (270 * 1500 / 8000); do not change engine physics

to correct artwork. The source accelerator uses the stock RPM/increase pattern;

small ancillary gauges and the clutch remain source-static.



The native TPL animation at time zero sampled one frame after the action start,

leaving the initial wipers 3.06 degrees off park. Hold start and start+1 at the

same pose, as well as the final two frames, in both forward and return actions.

This avoids a boundary step between paired clips. The preliminary live run

confirmed automatic rain activation and both animation samplers progressing;

final parking/calibration evidence is recorded with the final candidate.



### Final Lada v8 cockpit measurements

**Game (isolated native editor, final build-012/test-014):** final candidate
`lnv-interior-20260930-v8`, SHA-256
`7c87c66e8dd2f4bb6f95966ff8a939f5c3a072b5b63ced93e51ecc56ac4c277e`,
passes 172 package/static and 817 export checks. The shared cockpit contract's
seven tests pass and it is wired into the package audit. The final first-person
run measured steering input +/-0.35 as wheel rotation -/+126 degrees. At 799 RPM
the needle measured -26.95 degrees, matching the 8000-RPM dial calibration.
At 15.31 km/h the speed needle measured -25.55 degrees, close to the undamped
-25.83-degree target. Damping means instantaneous values need a tolerance.

The stock accelerator controller with `increase=16` returned to zero at idle
and reached -11.63 degrees under the observed drive; this is RPM-driven visual
motion, not a direct pedal-position signal. Brake input at 8.55 km/h produced
-18 degrees. Capture braking before the vehicle has stopped: an earlier delayed
probe missed this transient. Handbrake on/off was -26/0; low and differential-lock
levers reached -15; AUTO/REVERSE/LOW mode poses matched their authored values.

Normal rain (without debug auto-mode toggles) ran both wipers in phase. Samples
observed up to 45.57 degrees of the authored 52-degree sweep, both forward and
return samplers progressed, and both arms returned to the exact authored rest
after the weather cleared. Two parked probes three seconds apart remained at
rest. Duplicate boundary poses fixed the preliminary 3.06-degree initial offset.
Leave sufficient time for the active return before declaring parking failure.
The source glass texture and rain-clearing shader are separate from this motion.

Evidence: `runtime/interior_v8_final/review.json`, matching raw native probes and
captures, and `package/candidates/lnv-interior-20260930-v8/interior_result.json`.
All 362 source fixture files matched their pre-run seal; editor exit was zero.
Cockpit screenshots were visually reviewed, including a lower inspection angle
with the high-poly cockpit still active. Clutch and ancillary small gauges remain
static. No retail campaign/multiplayer or owner acceptance is inferred.

## L275 final lighting and installation (2026-10-01)

**Build/Blender review:** L275 v4 ports the Lada v6/v8 engine/load/brake/reverse
graph and off/on lens geometry; it does not copy Lada geometry or cockpit values.
810 front head/fog faces and 540 red / 540 reverse-lens faces retain their baked
UVs. Four emissive materials reuse the glass/trim bakes as emission art; six
light anchors sit at the ute's fitted lens footprints. Concrete hidden defaults,
red emission tint and delayed loaded-running activation preserve the Lada fixes. **Correction (L275 v9):** the Lada's concrete hidden flags are on its effect helper faces only, never on lit
lamp copies; hiding the L275 lit copies kept every lamp dark (see "Do not hide lit lamp copies in the markup").
Amber indicators remain separate. Forty-five actual artifact checks cover native
states/anchors, graph references/events, emission mip payloads, untouched gameplay
properties and unchanged physics except render triangle counts.

Evidence: L275 tools/exterior_geometry.py, exterior_effects.py, audit_exterior.py,
build/exterior_effects.json, reports/exterior_validation_v4.json; build-011,
test-013 and final Blender day/night previews. Lada's existing Game grade stays
with its own sealed fixture. No L275 v4 lamp behavior or native night reach is
claimed: no focus-taking editor/game test was launched. The source has no animated
instrument needles; the combined shared cockpit+wiper checker is not applied
to a static cockpit just because the Lada uses it.

## Roamer scout lens states (2026-10-01)

**Game (isolated SDK 7.3 editor):** Roamer scout `scout_20260930_01`, package
`4e69411afddcce27033b74711fb03ac7d1a14c58b28824b9c1c098fc43533c7d`,
reuses its fitted lens surfaces and existing emission materials, exporting explicit
off/on/running geometry at all four LODs for all eleven finishes. Automatic low
beams, high/roof lamps and left/right indicators passed native visibility probes;
normal signed AUTO-pedal braking showed all three brake lenses on, and signed
reverse showed the white reverse lens on. Shop init hides added lit surfaces.
Existing cockpit/mirror material aliases stay separate. Native palette/material
slot changes were observed in the original Roamer, so the Lada's alias-rendering
failure must not be generalized to every geometry/material binding.

Use signed pedals matching the stock movement FSM for native lamp tests. Forcing
REVERSE gear with positive state pedals can move backward while the stock engine
FSM reports acceleration; that bypassed input transformation is not a brake/lamp
failure. Release through neutral before braking and sample while velocity still
has its original sign. Evidence: `runtime/final03/{forward_state,brake_state01,
brake_state02,signed_reverse_state}.json`; candidate02 contains preserved earlier
misleading harness trials. Automatic rain wipers moved together in `wiper_seq2`
and returned in `wiper_seq3`; low rain power lengthens the stock idle interval.
No retail campaign, multiplayer or owner acceptance is inferred.

The opt-in `native_visibility.markup_visibility_report` detects the unresolved
hidden alias fault while allowing explicitly resolved custom brands. Five focused
tests pass, and the Roamer package validation checks body and wheel markup.


## A camera switch succeeds but the eye is outside the cab

**Native private fixture, Dump Twuck 2026-10-01:** IsCockpit()==true and an active
camera do not prove an interior view. An early transition frame put the eye behind the
cab, while native screenshots showed the platform and railing. Compiled marker
and steady-frame measurements subsequently put the source marker near the
windshield, ahead of the instruments; the early frame was not a settled pose. Validate the runtime eye in the body's local basis against actual
cab geometry/bounds, then inspect the image. RbCockpitCameraParams.eyeOffset can
place a camera relative to its attachment; verify its direction in the native
engine. A copied donor's adaptive chase interestPoints can likewise misframe
different vehicle proportions. Stable focus, suitable orbit distances and
actual post-transition captures require separate verification.

Source: dumptwuck_mod/history/build_010_behavior_pass_camera_failed/captures,
runtime/052_cockpit_frames.json and the archived 32-check behavior review. The
camera failure remained distinct from passing drive/dump measurements and
prevented sealing that package. No retail campaign camera acceptance is implied.


### Corrected camera-transition diagnosis (Dump Twuck, 2026-10-01)

**Native/Compiled TPL:** the source marker is [2.30, 6.35, 5.163] in native
body coordinates, near the windshield and ahead of the instruments. An early
post-switch frame behind the cab was still transitioning; it led to a rejected
forward offset. The new bounds check measured [2.33, 6.05, 6.313] for that attempt,
beyond the cab front. Preserve the incorrect assumption and failed build-011
evidence; do not relabel it as a success. A seat target [2.65, 6.20, 3.563] requires
eyeOffset [0.35, -0.15, -1.60] from the actual compiled marker. Subsequent native
measurement and visual review must validate the target. A switcher's immediate
IsCockpit state is not proof that the camera transition has settled.

Evidence: dumptwuck_mod/history/build_011_camera_failed/correction.json,
066_cockpit_frames.json and its FAIL_NATIVE review. Earlier numerical drive/dump
passes remain distinct. No campaign acceptance is implied.


### Dump Twuck final candidate: native behavior and camera pass

**Native private fixture, 2026-10-01:** final PAK 4b6aff7f549156f007566e4bde0122f004b998548d5337bb1fd20f749b1f4ea7 passed 603 retail export checks, 130 static checks, 159 saved-Blender checks and 34 native checks. The corrected cockpit eye measured [2.65, 6.20, 3.563] in native body coordinates and is inside the cab; a settled native screenshot shows dashboard, steering wheel and forward road. The chase view shows the whole truck after removing donor interest points and widening the orbit. Camera screenshots/review are pinned separately from numerical behavior. Source: dumptwuck_mod/reports/native_review.json, visual_review.json, build-012/test-011 job receipts and the sealed dtw-20261001-v1 candidate.

The initialization guard also waits for at least 120 simulation frames, six wheel contacts and chassis speed below 0.15 m/s, bounded by 45 seconds. The post-load frame-3 drop remains preserved rather than weakening contact checks. Final seeded load was 87.685 m3 before tipping and 0.382 m3 afterward; observed settled carrying volume depends on pose/settlement. Retail campaign/refill/save/multiplayer and recipient acceptance remain untested. The candidate is sealed, unaccepted and uninstalled. Original 21 source files pass direct verify --manifest; source-check intentionally requires an accepted authoring inventory, so its unavailable gate was not bypassed or called a pass.



### Whole-truck chase framing is insufficient for driving

**Owner report / compiled TPL / native fixture, Dump Twuck 2026-10-01:**
v1's whole-truck screenshot passed review but the driving view was misplaced.
Its supplied chase marker was 9 m high and 15.737 m behind the chassis before
the preset's extra offset and orbit distance. Check the compiled attachment
frame before tuning the preset. Chassis anchoring removed that compounded
offset; however the first intermediate post-cockpit view still measured only
4.5 degrees down and the bed blocked the road. Check settled post-cockpit
and driving views, including actual pitch and clear road ahead, not only
focus alignment/distance or firstLaunchCameraAngles. Follow-angle limits
and terrain offset are separate native preset controls.

Evidence: dumptwuck_mod/history/revision_002_before/feedback.json and
history/revision_002_fixed_cap_rejected/runtime/captures/driving_v2.png;
runtime/106_driving_camera.json. Build-014 raises the follow camera; fresh
visual and runtime evidence is still required before calling it fixed.


### Follow-camera correction after owner feedback

**Native private fixture/visual review, Dump Twuck v2, 2026-10-01:** use the
canonical chassis attachment, focus [0,6,1], 26-36 m scroll distances and
follow activation at 0.5 m/s rather than compounding the supplied distant
chase marker with the orbit. Follow pitch limits 22-42 degrees and terrain
offsets 8-10.5 m leave space above the broad canopy. The supplied cockpit eye
offset remains [0.35,-0.15,-1.60], validated inside the cab.

Numeric alignment/height and owner reports must be followed by image review.
A prior focus 9 m up passed numerical camera checks but cropped most of the
truck; history/revision_002_load_pass_camera_crop preserves that visual failure
alongside the successful payload tests. Earlier follow settings looked better
at rest but dropped the camera when driving. The final protocol checks both
post-cockpit and moving states and separately reviews actual captures.

Evidence: dumptwuck_mod/package/candidates/dtw-20261001-v2, PAK `d1e02c4e93c67884a1536b3b2654400014b7349adc74edef0184dbf5091d91e4`,
reports/visual_review.json and native_review.json. Whole-truck presence in v1's
far orbit did not establish usable driving framing. The project-specific
native/visual gates are retained; no universal camera-position rule is added
for vehicles with different canopy/boom shapes. Retail owner acceptance remains
separate from private fixture review.

## L275 v6 accessory lamps: joined lenses, flashing beacon, bar floods (2026-10-01)

**Build:** accessory lamps can join the vehicle's existing lamp objects instead of
adding graph nodes. L275 v6 joins its headboard light bar's stop/tail lens into
`tail_lights`, `tail_lights_on` and `brake_lights_on` and its reverse lens into
`reverse_lights` and `reverse_lights_on`, at every LOD, as extra material slots
(`vehicle_body` off, `vehicle_lights` on, own emission mask). The existing
`BlueprintNodeShowHideGeomObjects` nodes switch objects by name, so they switch
the new lenses with no graph change. Rename the piece's UV channel to the
target's before a Blender join (see build-pipeline.md).

**Build / Inferred:** a flashing beacon is two `BlueprintTimeLibrarySchedule`
nodes with the same `period` (0.8 s) and `startDelay` values one lit-time apart
(0.05 and 0.45 s); their `OnPeriod` drives lit and dark show/hide states that also
VfxRestart / VfxStop an amber `sfx_light_base` point light at the beacon. Start
both from the engine-running branch (`Apply.OnTrue`), stop both and force the
dark state in `Apply.OnFalse` and `Init`. That a schedule keeps firing without a
Stop is **Inferred** from its period parameter and from L275's LoadDelay, which
stops itself after one period; whether the beacon flashes in the retail game is
**Open** until the owner's drive. The steady alternative is listing the beacon
in the head-lamp states. **Game correction (v7 drive):** the schedules do keep
firing, but the whole dome appeared and disappeared; see "L275 v8 beacon: switch
only a lit shell" below for the replacement.

**Build:** spot lights at the light bar's reverse lenses join the reversing
effect list, so the bar floods the deck and ground behind when reversing.

Evidence: L275 `tools/accessories.py`, `exterior_effects.py`,
`patch_compiled_lamps.py`, `audit_exterior.py`, `build/accessories.json`;
first build-019/test-020, final build-021 (job 20261001T104224Z-3aedaec175c0) and
test-022 (319 static checks pass), installed as candidate
l275-accessories-20261001-v6 (package ee8463ff...). No in-game test yet.

## Dump Twuck v4: artist light sockets, beams, beacons, exhaust and sounds (2026-10-01)

**Build; owner chose no engine runs, so every effect below awaits the owner's retail drive.**
Owner request: "make all the features such as lights and everything work". Revisions
1-3 had glowing lens copies only: no beams, no stop or reversing lamps, steady beacons,
no exhaust, no wheel dust, and the TUZ Lynx scout's engine sound.

- **Check the source for light sockets first.** The supplied blend had 20 empties,
  18 of them `ls_*` light sockets (headlight high/low, deck and side work lamps, tails,
  eight beacons), aimed along their local -Z like Blender lights. Native cones follow the
  anchor's Blender -Y, so the build re-aims each socket in place with
  `aim.to_track_quat('-Y', 'Z')` (aim = socket -Z). The compiled TPL then has native +Z of
  each anchor equal to `rc_to_native(aim)` for all 18 (a static check now); on export a
  Blender object's frame converts by change of basis.
- **Beams:** 22 `sfx_group` / `sfx_light_base` groups: high beams (spot, 60 m, shadows),
  low beams, deck and side work lamps, red tail points, brighter stop points and white
  reversing floods on the tail sockets, blue points on the beacons (bed beacons ride the bed).
- **Lens states:** a `brake_lights_on` copy of the tail lens on its own `vehicle_lights`
  instance (emissive 170 / bloom 6 against 65 / 3), hidden by default. The art has no
  reversing lens, so the reversing states are VfxRestart / VfxStop only (no show/hide node
  with an empty name list).
- **Graph:** the Lada / L275 engine, brake and reverse state graph. The beacons double-flash
  with the CAT 793D's chained one-shot `BlueprintNodeTickTimer` nodes (lit 0.08 s, dark
  0.10, lit 0.08, rest 0.55; the pattern seen working in the retail campaign), started
  from the engine-running branch, stopped with a forced dark state on shutdown and init;
  each lit phase also restarts the beacon lights.
- **Effects module:** `effects = { propSfx = { list = { ... } }, __type = "WheelExtraBigVfx01" }`
  keeps the shipped Baikal 65206's module (53 effects, 16 dry / 12 wet wheel particle
  materials, water splash) and adds list entries, as the Greenway 740 Cross and EPEC TC305
  chassis templates add `part_exhaust_horizontal_01`. The compiled class merged 76 effects.
  The module's water splash tracks an `sfx_water_impact` locator; add one.
- **Exhaust and haze sources:** stock effects live in `default_other.pak` as
  `ssl/sfx/*.sfx`. `part_exhaust_horizontal_01` emits from `sfx_exhaust_*`,
  `part_track_acceleration_single_exh_01` shows only its `sfx_exhaust_01` emitter, and
  `part_radiator_haze` emits from `sfx_radiator_haze` (all its emitters except
  `CPU_Smoke_6` are authored invisible; retail trucks switch some on per truck). All use `local__parentArea`
  sources emitting by face normal. The build adds rigid, visible meshes with those names:
  12-segment discs recessed 0.12 m in the two horizontal chrome pipes, facing out, and a
  quad under the front deck plate, facing up. The SFX graph follows the Greenway template:
  burst on starting, haze plus horizontal idle smoke on started, burst on acceleration or
  reverse, all stopped on shutdown.
- **Sounds:** the Lynx sample's engine graph uses the same RPM, speed, gear and acceleration
  RTPCs and fuel switch as the Baikal 65206, so only the event names change (engine,
  start, stop, handbrake). Added: brake pull / release and the underneath rumble, and the
  Baikal's Addon graph (sand refill and pour loops, heavy dump-bed open / close / stop on
  the `dump` controllable state) without its sound-emitter clone, whose tracker names a
  Baikal locator. Horn, collision, suspension, rain and sand sounds already come from the
  base truck layer that every compiled truck class merges in (Body, Cockpit and
  ForceFeedback graphs appear in the class without being in the BRO).

**Lint:** RC026 flags a blueprint that starts effects the truck does not declare; the
compiled class of revision 3 fails it (`part_exhaust_small_cars`, `part_radiator_haze`:
the Lynx SFX graph without the Lynx effects block). RC025 flags effects parented to nodes
the model lacks. Evidence: dumptwuck_mod tools/exterior.py, create_models.py (`emitters`,
aimed anchors), build/physics.json (lightAnchors, effectSources), build-026 and test-026
(171 static checks), candidate dtw-20261001-v4.

**Game correction (owner, v4 drive):** the beacons "dont emit when they strobe, the mesh itself
disappears and reappears". v4 hid every lit copy in the model markup (RC037) and its flash swapped
the beacon lens with that copy (RC039). v5 rebuilds the lamps with `roadcraft.lamps` (start here):
lit copies default-visible and hidden at init, a lit shell 1 mm outside the beacon lenses that the
double flash switches over lenses that stay, and the kit's Lada emission values. The beams, effects
and sounds above are unchanged.

**Game correction (owner, 2026-10-02):** "The lamps on the dump twuck dont emit when they strobe, the
mesh itself disappears and reappears and this is a reoccuring problem." The v4 beacon states swap the lens
`blue_beacons` with its lit copy `blue_beacons_on`, which the markup hides by default together with
`head_lights_on`, `tail_lights_on` and `brake_lights_on`. `lint-bro` now reports both faults on the v4 project
(RC037 for the four lit copies, RC039 for `blue_beacons`). The fix is the "start here" recipe: lit copies
default-visible and hidden at init, and a lit overlay that flashes over beacon lenses that stay. Not yet
applied to the Dump Twuck.

## L275 v8 beacon: switch only a lit shell (2026-10-01)

**Game (owner, v7):** "The entire mesh appears then disappears for the beacon." v6/v7 swapped two coincident
dome objects (`beacon` unlit, `beacon_on` lit) from two `BlueprintTimeLibrarySchedule` nodes 0.4 s apart; the
flashing ran, but one phase showed no dome. Both objects compiled normally (`obj_list.json`), the graph compiled as
written and the same show-then-hide state pattern lights the Lada's lamps, so the mechanism is not established.
This corrects the v6 entry above: the schedule pair is **not** a proven beacon recipe.

**Build (v8, owner check open):** the unlit dome joins the light-bar mesh and is never switched; a lit shell, the
dome pushed 1 mm out along its normals with the `vehicle_lights` material, is the only switched object
(`beacon_lit`, hidden by default). Two `BlueprintNodeTickTimer` nodes (0.4 s each, not looped) restart each other
and show / hide the shell and VfxRestart / VfxStop the amber glow: the CAT 793D strobe pattern, whose emitters
flash in the retail game while their housings stay. `Apply.OnTrue` stops both timers, shows the shell and starts
the lit timer; `Apply.OnFalse` and `Init` stop both and hide the shell. Whatever the switching does, the dome
cannot vanish.

Evidence: L275 `tools/accessories.py`, `exterior_effects.py`, `audit_exterior.py`; build-026 / test-027;
CAT 793D `GreenStrobe_*` nodes (package/holds/lights_native_20260916_001).

## Do not hide lit lamp copies in the markup (L275 v9, 2026-10-01)

**Game (owner, two drives) / Inferred cause:** L275 v4-v8 put every lit `_on` copy (`head_lights_on`,
`tail_lights_on`, `brake_lights_on`, `reverse_lights_on`, the beacon's lit object) in the model markup's
`objSettings` with `visibleDefault = False`. No L275 lamp was ever seen lit: in v7 only the default-visible unlit
beacon dome blinked as the graph swapped it ("the entire mesh appears then disappears"), and in v8, with the dome
never switched, the owner saw no lamp glow and no beacon flash. The Lada, whose lamps the owner likes, uses the same
graph, light effects, emission values for the rear lamps and comparable emission masks, but hides only its effect
helper faces (`sfx_exhaust_01`, `sfx_radiator_haze`) in the markup: its lit copies start visible and the graph's
`Init` hides them, then shows them with the engine, brake and reverse.

| Rule | Grade |
|---|---|
| Keep lit lamp copies default-visible in the markup; hide them from the graph's `BlueprintCommonLibraryOninit` (`HeadsOff`, `TailOff`, `ReverseOff`, the beacon's hide) | Game (Lada works; L275 v4-v8 never lit); fix Build (L275 v9, owner drive open) |
| `visibleDefault = False` in `objSettings` is for helper geometry that should never render (effect source faces); a `BlueprintNodeShowHideGeomObjects` show did not make such an object appear in the L275 drives | Inferred (owner reports), not observed directly in the engine |
| Lada lamp emission: headlamps 80 / bloom 4, tails 8 / 1 (tint [255, 255, 12, 3]), brake and reverse 45 / 2 | Game (Lada) |

Evidence: Lada `tools/niva_config.py` `HIDDEN_EFFECT_GEOMETRY` and its installed package markup; L275
`tools/l275_config.py`, `prepare.py`, `audit_exterior.py` (checks that no lit copy is markup-hidden and that `Init`
hides every one); build-028 (`jobs/20261001T131155Z-085f36751560`), test-030 (`jobs/20261001T131622Z-8d3292fa4df5`), 337 static checks, package `da8fbaabea0226b044d1de4d9d55fd90f85246ef6b272c449e06d8aae06bc8eb`.


## Native seated driver placement (Lada v10, 2026-10-02)

**SDK / Retail:** truck BRO exposes `hideDriver`, `driverBone` (default
`_cockpit_camera`) and nullable `driverBoneOffset` in native bone-local XYZ.
Enabling the driver emits `prop_driver`; the shipped property uses the
`driver_static_01` actor with a cycling `idle` animation and child-actor fade.
It follows a tracker on the named vehicle bone. This supplies a seated idle
character, not hand-to-wheel or foot-to-pedal IK. Reuse an appropriate existing
frame when its orientation is correct; a new controllable joint is unnecessary.

The shipped `PropDriver` follows normal current/occupied/on-route visibility,
global hide-driver and photo-mode controls. It hides in the high-poly cockpit,
when sunken, or for applicable phantom states. These rules come from its source;
only third-/first-person switching was exercised in the Lada test. Do not force
the actor visible globally merely to make an editor screenshot work.

Fit the actual seated model against the seat cushion/back, roof, wheel and
footwell. Do not reuse another vehicle's offset: Lada's measured trial used
native `[0.035,-0.62,0.08]` from its upright `_cockpit_camera`, putting the actor
origin at `[0.446,0.66,-0.17]` in truck coordinates. These are Lada values.
**Game, isolated editor:** side/cabin views showed a seated, forward-facing
driver with roof clearance; first-person hid the actor and third-person restored
it. The stock hands rest by the lower wheel; no custom control tracking claimed.

**Build:** the generator omits `boneName` when it equals the shipped default.
Resolve that specific property default when comparing a diagnostic fixture to
generated classes, and record both raw and resolved comparisons. Do not replace
a full package-preservation check with loosely normalized dictionaries. Lada's
final gameplay document matches after this one default is resolved; 191 compiled
visual assets match the tested fixture byte-for-byte and 362 sealed files remain
unchanged. All v9 package members outside the driver actor-brand delta are checked.

**Native diagnostic correction:** for the stock driver's skeletal landmarks,
`GetObjModelTransform(name)` returned parent-local posed transforms. Use
`GetTransformObj(name)` for world positions and the truck transform's
`TransformPointInvert` for truck-relative positions. The misleading initial
landmark sample remains preserved; do not use it to infer a deformed character.

Evidence: Lada `revisions/driver_v10/sdk/ssl/game/truck/driver/prop_driver.ssc`,
`prop_driver.prop`, retail BRO survey and driver TPL node snapshot;
`runtime/driver_v10_trial/` side/cabin captures and first-/third-person probes;
`revisions/driver_v10/native_parity.json`, build-016/test-016, v10
`driver_result.json`. `tools/audit_driver.py` is wired into local validation and
the `--driver-only` adapter pins reused assets. A shared pose/clearance validator
is deferred: fitting needs each cabin's geometry and resolved stock pose; this
first case does not establish universal offsets or automatic clearance limits.
Retail campaign, multiplayer and owner acceptance remain separate.


## CAT 793D RC26 consumes the lamp kit (2026-10-02)

**Build; retail rendering open.** The owner requested the 793D strobes and all lamps be repaired
with the kit. RC25's body model matched the retained RC23 native source byte for byte before
editing, and its markup had no hidden lamp flags; RC037/RC039 are not established causes here.
The adapter now composes `lamps.lamp_states`, `flasher`, `light_effect`, `lit_material` and
`blender_lamps.lit_shell`. Existing head/work/marker pairs share the head-state branch; the
separate brake lens base is hidden in the bright state and restored in dim/off states. Green
emitters use DOUBLE_FLASH (replacing 40 / 35 / 40 / 440 ms), while amber flashes only a 1 mm
shell over a persistent lens. Fourteen measured anchors supply beams and glow. Original rig
bones, non-lamp meshes and existing compiled transforms are retained; load, sound, shop and
handling fields remain byte-identical or semantically identical outside the lamp sections.

Evidence: `cat_lamp26/tools/{lamp_graph,model_lamps,build,check_lamp_events}.py`,
`reports/{model,audit,events,completion}.json`, and `cat793d_thiess_fix/LAMPS_TOOLCHAIN_20261002.md`.
The official import completed; final build/test receipts pass with 1,275 package/model checks,
18 exported-graph event checks and zero shared-lint findings. RC26 was installed with an exact
RC25 backup; no campaign acceptance is inferred. Existing helpers/checks cover this pattern;
new universal lamp restrictions are not warranted by a request without a detailed drive report.


## Three-place digital speed with stock BPN geometry visibility (Dump Twuck revision 006, 2026-10-10)

**SDK / offline Build; native Open:** the supplied new-cab README calls the digital readouts Blender-only and exports a static `888`. This describes that source package, rather than proving the engine cannot drive digits. The installed SDK exposes signed m/s through `BlueprintNodeTruckVelocity.GetLinearVelocity`, stock float/int arithmetic and switches, a repeating schedule, and `BlueprintNodeShowHideGeomObjects`. A project graph can therefore select one of ten separately named glyph meshes at each of three positions without custom runtime code or Blender drivers.

The authored `DtwDigitalDash` graph hides all 30 `lcd_speed_{h,t,u}_{0..9}` meshes at init and engine shutdown. Engine start and running-on-load refresh immediately and start a 0.1 s timer. Each refresh first hides all glyphs, snapshots `clamp(abs(velocity)*3.6+0.5,0,999)`, casts to int, and selects zero-padded hundreds/tens/units: `000` at rest, the same magnitude in reverse. The float snapshot is inspectable in private debug builds. Engine-off output is blank. Preserve individual mesh names and default-visible markup, and fit a static `km/h` legend to the actual display.

**SDK analogue calibration:** a 0–60 km/h dial with a -270-degree sweep uses the existing speed scale formula `3.6*lastGearTargetKmh/60`, separate from engine performance. The installed `TruckEngineParams.rpmOnNeutralMax` default is 1500; a 0–3000 RPM dial therefore uses a -135-degree native sweep at that maximum, rather than changing mechanical RPM to suit its face. Fuel reads normalized current/max fuel with the authored -100-degree sweep. Bind `ctrl_dashboard_speed`, `ctrl_dashboard_rpm` and `ctrl_dashboard_fuel` to their measured exported frame: source-local Y is not sufficient proof of the native axis. Revision 006 reframes these bones so the exported native Y follows the source dial normal.

**Visual (offline only):** the corrected driver-eye render shows all three central `000` glyphs unobscured. The measured central placeholder consists of `body_ci_darkpanel` components 109–129, 21 bars/756 vertices; guarded removal preserves the screen backing. The replacement is fitted to this face, and `lcd_speed_units` supplies converted `km/h` text. Geometry placement and a static diagnostic render are distinct from native speed updates or readable native pixels.

Evidence: Dump Twuck `source/revision_006/manifest.json`, pinned `generated_authoring_inventory.json`, `tools/digital_dashboard.py`, `tools/digital_model.py`, `tools/model_v6.py`, and `tests/test_digital_dashboard.py`; five offline tests passed on 2026-10-10, including real SDK fields/link signatures, rounding carries, reverse, engine lifecycle and glyph geometry. SDK source: `blueprint_node_truck_velocity.ssc`, `blueprint_node_show_hide_geom_objects.ssc`, `blueprint_time_library.ssc`, `prop_cockpit_dashboard.ssc` and `truck_components.ssl`. These tests do not prove native compilation, rendered digits, axes/sweeps or cockpit usability. A matched native capture and live visibility/speed/frame telemetry remain required.

## Water cut-off volume must stay inside the cab shell (Kanga 25 c7, 2026-10-10)

**Owner report (c6):** "the left windows is dark and overhangs the cab (its not the right shape)". **Build:** the
`cutoff_volume` was an axis-aligned box from the cab's extents; the cab's inboard rear corner is chamfered, so two box
corners stood 0.25 m outside the shell and showed through that window as a dark pane. Retail cut-off volumes are
meshes, not boxes. Fix: the convex hull of the cab shell scaled about its centroid (0.95 left only 1.2 cm at the
tightest wall, 0.90 gives >= 2.5 cm), still containing the equipment cockpit camera (it is that camera's
`boundingVolumeObjectName`); a rig-audit check measures it against the shell hull (kanga25_mod `audit_rig.py`).
Also check supplied interiors against the shell: the MAC25 asset's rear seat leaned 0.2 m through the back wall in
its own source.


## Instruments hidden by their own dash; dial artwork must follow each gauge's zero (KGS-25, 2026-10-11)

**Game (owner):** "Gauges are cut off by an intersection and the little ones arent straight." A binnacle tilted back
toward the driver sank behind the dash body's vertical front face, hiding the top third of the big dials; an
operator instrument plate sat half inside the console box below it. Neither shows in a straight-on render.
**Build:** check every dial with rays from points on its face to the cockpit camera (`_cockpit_camera`,
`_equipment_cockpit_camera`) and list what is hit first (kgs25 final `tools/interior/check_dials.py`); move the whole
instrument group (panel, bezels, dials, lamps, needles) clear. Dial artwork: draw each scale from the gauge's
modelled zero angle and sweep (KGS-25: big -135/270, small -60/120, load-moment -120/240), anchored on the needle
modelled at zero; one shared sweep rotated every small scale.

## Finishing a supplied cockpit (L275 v22, 2026-10-12; Build, pose-tested offline, not yet driven)

Owner: "Can you make the interior fully polished and finalized". An audit of the supplied interior found:

* **Wrong-hand drive.** The source cab was left-hand drive; the vehicle's camera and steering box were right-hand
  drive, so first person sat in the passenger seat with no wheel. Check the steering wheel's x against the cockpit
  camera's x before anything else. Fix: mirror the interior (x -> -x, reverse face winding, clear custom normals) and
  re-bake.
* **Camera in front of the wheel.** `_cockpit_camera` was 75 mm *ahead* of the wheel centre (y -0.75 vs -0.675), so the
  view looked down onto the cluster hood. A seated eye is ~0.4-0.45 m behind the wheel and ~0.62 m above the cushion
  (L275: y -0.26, z 1.56). Validate `eye.y > wheel.y + 0.3` (forward is -y).
* **An opaque cluster lens over empty dials.** A smoked lens in the opaque interior material hid decimation-lumpy hubs
  on a blank backplate. Remove the lens and internals by loose-part bounding boxes; author a cluster insert: a face
  plate fitted to the backplate's plane (SVD) 3 mm proud, printed scales in its own atlas (6 px/mm), bezels, needles
  modelled at their zero mark, hub caps on the needle bones.
* **Controls the Lada way** (cockpit eye check above): bone head at the pivot, tail along the axis *away from the
  driver* (column axis from the rim's SVD plane; dial axis = -plate normal; pedals (-1,0,0) at their top), parented to
  the cab bone, BRO axis `Z`. Pose check offline: the game's negative native-Z angle equals a positive Blender pose
  rotation about the bone's own Y (+135 degrees put a -270-degree 0-180 km/h needle at 90). Speed scale
  `3.6*topGearKmh/dialKmh`; RPM maximum `-270*1500/dialRpm` (stock normalisation at 1500); fuel `-100` over E..F.
* **Steering wheel pivot by a circle fit (v23).** The vertex mean of the wheel's outer verts is pulled by spokes and
  by uneven mesh density (L275: 42 mm low), so the wheel orbits its column. Fit a least-squares circle to the outer
  rim band in the rim's SVD plane and refit after dropping inner points (residual ~ the rim tube's thickness).
* **Mesh-group movers.** Keep the steering wheel and pedals inside the interior mesh as vertex groups (`ctrl_*`),
  assigned by loose-part bounding boxes after reduction; decimated LODs keep the groups.

Project: `l275_minespec_mod/tools/interior_v20.py` (bones, groups), `ute_systems.py` (dataDashboard),
`art/interior_v20/generator/{r10_interior,r50_gauges,r51_gauge_art,gauge_layout}.py`.

## Recovering separate lamp regions and a steering axis (Jimny, 2026-10-05)



**Build:** Jimny's recovered clear tail lens covered both red and white sections. Emitting through the whole lens tinted the reversing section red. Its revised source derives disjoint emitters from the original opaque lamp body: sample each face's UV centroid in its recovered colour atlas, classify red faces for tail/brake and neutral white faces for reverse. This recovered atlas uses solid red/white islands; these thresholds are asset-specific. The clear lens remains visible in all states. The native lamp graph switches the emitters, with independent rear-facing reverse beams; unique diff textures avoid material/preset conflicts. Each red emitter has 4,958 source triangles; white reverse has 1,376. This is source/compiled validation; native visual and reverse-event testing remain Open.



The recovered steering rim's smallest covariance eigenvector identifies its column axis. Align the steering bone's Blender Z to that normal, then verify its exported native Y and connect dataDashboard steering with axis Y. Rebinding in rest pose preserves source geometry. A geometry-derived axis is suitable for this planar rim, not an arbitrary steering assembly. Project validation checks a >0.999 axis dot product and generated prop_cockpit_dashboard; actual live animation remains Open. Evidence: Jimny_RoadCraft_20261005 tools/{create_models.py,build_bro.py,validate.py}, reports/rig.json, reports/polish_cockpit.png and the polished-v3 package identity recorded in frames.md.





## Verify parked animation frames after compilation (Roamer ute, 2026-10-05)



**Build:** Blender 5.2 source wipers parked at zero rotation, but the first native model compiled the two controller frames at the 44-degree raised pose when the clips were named `r105ute_wipers_backward` and `r105ute_wipers_forward`. Ordering them as `r105ute_wipers_forward` then `r105ute_wipers_return` restored compiled parked frames while retaining both explicit, disjoint frame ranges (1–18 and 20–37). Keep source rest, compiled rest and live clip motion as separate checks; a successful exporter and an animation-name list do not prove a correct parked state. The precise ordering mechanism is Open, so do not enforce this naming scheme on other assets.



Evidence: `Roamer105Ute_20261005/fix_wiper_rest.py`, `native_validation/source_services.json`, `native_validation/compiled_frames.json` and native `anim_list.json`; source sweeps rose from about 1.45 m to 1.81/1.84 m. Package audit checks both clips and parked controller axes. Runtime rain/animation validation awaits the owner's editor-test go-ahead. No universal validator was added for a single exporter-order observation.





### Y61 live light and recovery validation (editor play mode, 2026-10-06)



**SDK / Game, native editor:** use PropVehiclesHeadlights.namesFxVhc for beams that follow the ordinary headlight switch; starting those same effects from an engine-start graph prevents the switch from owning them. Y61's final beam service turns both heads and tails off/on with isHeadlightsOn. Its lens graph keeps the shipped engine-running convention separately. Native visibility probes confirmed service-brake overlays, independent reverse lenses/beams, and release states.



DbgUpdateInputs writes truck.input directly, bypassing TruckState.pedals and the ordinary movement FSM. It is useful for repeatable rigid-body trials but did not exercise Y61 brake/reverse callbacks. The State method sustained ordinary inputs in this fixture: positive AUTO drove forward; negative AUTO braked then reversed. Sample braking while forward velocity remains positive; the first short/full-brake probe was already reversing by the time its correlated response arrived. Ten seconds of acceleration followed by -0.15 pedal produced two confirmed BRAKE_PULL observations with visible brake overlays. Do not label a missing event in a debug-only drive a broken lamp.



Recovery source-controller points and PropWinchable target sockets are separate declarations. Y61 now explicitly declares four recovered target sockets and eight source entries (the existing duplicated source convention). The final editor test attached through ordinary targeting, pulled a second Y61, released, then separately attached valid source/target physical bodies. Earlier source-only classes and the rejected eight-target assumption are retained. The project package validator checks target sockets against the BRO's four recovered points; no universal explicit-target requirement is imposed on stock vehicles. Evidence: WatcherY61_Final `native_tests/final_recovery_result.json`, job 20261005T190903Z-3f1ff73a5714, `reports/final_native_verification.json` (86 checks), `tools/fit_recovery_points.py`; shipped sources `prop_truck_view_controller.ssc`, `prop_vehicles_headlights.ssc`, and movement-FSM states. Retail campaign acceptance remains separate.





### Reflected conversion text and gauge sweeps (Roamer ute, 2026-10-06)



**Build / SDK/Game:** a canonical conversion with negative determinant can preserve correct topology yet reverse cockpit-facing text. Roamer's live cockpit exposed mirrored dashboard lettering. Reflect U only on text-bearing cluster/head-unit/button/plate slots, then refit needle pivots against the corrected cluster UV plane and reverse their sweep signs where the fitted basis reverses. Do not reflect the entire finished rig. The saved-source fit remained within 0.003 m, source geometry was retained, and the native cockpit capture shows readable dial text and working wiper sweeps. Evidence: Roamer105Ute_20261005/final_cockpit_uv.py, native_validation/cockpit_uv_correction.json and R105Final_20261006/runs/final_native_suite_all_063805/{cockpit,cockpit_wipers}.png.



**SDK/Build/Game:** the ute reused the Y61 native headlight service pattern. This SDK generator omitted direct effect group names when bonesNames was empty, producing an empty prop_vehicles_headlights. Task build_native.gameplay now restores the authored namesFxVhc/namesFxVhcFake arrays after generation and verifies every effect exists. Native probes show all ten front/auxiliary effects false/true as the switch changes. Ordinary State controls confirmed reverse lenses and both reverse beams, then brakePull while still travelling forward and the bright brake overlay with dim tail hidden. Debug-only missing callbacks were excluded. Evidence: native_validation/native_class_regeneration.json, headlight_service.json and R105Final_20261006/runs/zero_reference_v3_lamps_parked_070216 receipts. General post-generation automation is deferred because another generator/version may support direct groups differently.





### Jimny native service correction (2026-10-06)



**Game / SDK / Build:** the recovered Jimny's engine-start lamp graph kept head beams active even when the headlight state was off. Assign ordinary beams to `prop_vehicles_headlights`, remove those beam names from engine-start graph ownership, and restore explicit direct effect groups after this SDK generator omitted empty-bone-name entries. Reverse beams remain event-controlled separately. Retain failed switch probes: Jimny J31TestE services 019/022/024 showed head beams always active. Target recovery sockets are explicit copies of the recovered four points, separately from the view-winch source points; preserve the generator's existing duplicated source convention. Final switch/attachment retesting uses J31TestF. This reuses the previously proven Y61/Roamer native pattern; no new universal effect-group repair is imposed.



**Game, Jimny live steering probe (2026-10-06):** in third-person, highPoly=false
dashboard telemetry retained currentAngle zero even at steer +/-1. Switch to
first-person and wait for highPoly=true before testing cockpit animation; the
same source then reports +/-360 degrees on BoneSteering's configured Y axis.
This is a visibility/update-protocol distinction, not evidence of a broken rig.
Both pose/frame sets are preserved in J31TestF final_all_092833 and
final_services_all_093912. Native camera rendering/steering were validated;
the recovered cockpit has no authored gauge or wiper clips.
