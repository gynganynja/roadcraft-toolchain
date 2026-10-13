# Suspension and wheels

## Wheel slots

A wheel is a `wheelSlots` entry in the truck BRO (`truckSettings.wheelSlots`) whose `geomName` is a
joint (bone) in the body model. The wheel model itself is a separate model (`wheelPool` ->
`EditableWheel` -> wheel class -> wheel BRO -> wheel `.tpl`), placed by the game at the slot.

| Rule | Grade |
|---|---|
| The wheel sits with its centre on the slot joint as modelled; model the vehicle at its intended stance with the tyres touching z = 0 | Build, Game |
| Wheel BRO `truckWheel.radius = 1` with `width` and `rimRadius` as fractions of the radius; `wheelPool.<name>.scale` is the radius in metres (the generated wheel scales both) | Build |
| Several `EditableWheel` entries may share one wheel class with different scales (front/rear sizes) | Game (Warthog) |
| Retail slot joints are oriented differently per vehicle: Armiger identity, ZiKZ 605E local X forward on both sides, SDK Lynx sample rotated per side (local Z inboard) | Retail |
| Identity slot orientation alone does not determine final wheel handedness. Inspect the native rim/object frame as well as the slot and wheel actor. Lada identity slots produce left `rimLeft` near -X and right near +X at rest | Game (Lada, 2026-09-30; `runtime/rut_baseline/terrain_rest2.json`) |
| Author each wheel for its measured final frame. Lada therefore uses the right-facing source master for both named assets; the native left object rotation supplies the opposite side. The earlier buggy report of exposed brake discs led to separate +X/-X masters, but that unvalidated remedy was incorrectly generalized | Game observation; Lada correction Build pending visual drive |
| The SDK documentation's "outer face -X" rule goes with its sample's per-side joint orientation | SDK, Retail |
| Keep one source wheel's tyre, rim and brake disc together in the wheel model; calipers belong to the hub, not the wheel | Build |

## The axle controller: what moves the slot joints

**Wheel slot joints only follow their wheels when an axle controller names them.** Without it every
visual part hung on or pinned to a slot stays where it was modelled while the wheel moves. Every
retail vehicle that pins IK to wheel slots has the controller. (Game: the Warthog's and the buggy's
first builds, and the Roamer 105 in the editor's play mode, whose slot bones never moved, not even as
steering joints; Retail: all 84 trucks with the block.) `lint-bro` code `RC010` / `RC031`.

```text
axleControllerSettings = {
   isEnabled = True
   independentAxleSettings = [ { frameName = "BoneWheelFrontLeft", isIndependent = True }, ... ]
   axleSettings = [ { frameName = "BoneAxleFront" } ]                    solid axles: an axle frame
   steeringRackSettings = [ { frameName = "BoneRack", rightWheelFrameName = "BoneKnuckleFR",
                              leftWheelFrameName = "BoneKnuckleFL", rackHalfLength = 0.772 } ]
   __type = "AxlesControllerSettings"
}
```

It compiles to `prop_truck_axles_controller { independentAxles [ { frame, singleWheelID = -1 } ],
steeringRacks [ { frame, rightWheelFrame, leftWheelFrame, rackHalfLength } ] }` (Build, matches the
retail ZiKZ class). A slot that hangs under another moving rigid body (a rocker) moves with that body
and needs no entry (Retail: ZiKZ rear axles).

### Steering joints and racks

| Rule | Grade |
|---|---|
| `customSteeringJointObjName` on a steered slot names an identity-oriented joint on the wheel axis at the kingpin (0.23-0.29 m inboard of the wheel centre in retail) | Retail (Armiger `BoneRackLeft/Right`, ZiKZ `r_rack_01`) |
| That joint hangs under the wheel slot (ZiKZ) or under a solid-axle frame (Armiger); `steeringRackSettings` names it as a rack wheel frame | Retail |
| `rackHalfLength` = lateral distance from the rack centre to the steering joints (ZiKZ 0.928 = its kingpin x) | Retail |
| Tie-rod chains pin to the steering joint (Armiger `SteeringRod` -> `BoneRackRight`); the ZiKZ bases its steering-rod chains on bones that move with the rack | Retail |
| The rack has no per-side (Ackermann) settings, only its frames and `rackHalfLength`, and the wheel slot has none either: expect the outer knuckle and the outer wheel to disagree at full lock (Roamer 105: 30 against 24 degrees) | SDK (type description), Game (Roamer 105, editor play mode) |
| Without a steering rack, hubs hung under slots as steering joints ended up outside the wheels on one side | Game (buggy); cause not isolated (Open) |

## Suspension values

A suspension axle is a `SuspensionAxle` in `truckSettings.suspensionCollection` (named items, each
slot picks one with `suspensionCollectionItem`) or in `suspensionSet` (front / rear).

| Rule | Grade |
|---|---|
| **`useSuspensionCollection = True` is required**: without it the generator drops the collection and compiles no `suspensionAxleCollection` | Build (class), Game (Warthog), Retail (all 41 retail collections set it; only the SDK samples do not) |
| With no suspension block the engine default is min 0, max 1 m, height 0, strength 0: the body rests on its bump stops and the wheels hang up to a metre when it lifts | SDK (type description), Game (Warthog) |
| Position is measured from the wheel's modelled place, + = lower (droop). **The stops are at `height + min` (top, bump) and `height + max` (bottom, droop)**, not at `min` and `max` themselves as this row said until 2026-10-02 | Game (KGS-25 bench, Lada trials; "Stop geometry" below); the earlier reading was Retail (every retail axle), Inferred |
| **`height` is the spring's neutral offset: a positive value raises the vehicle.** It is not the rest position; with height 0 the vehicle sinks by its whole static sag | Game (buggy sat low with height 0; Roamer 105 in the editor's play mode: the ride height followed height about 1:1) |
| Static sag is inversely proportional to `strength`: sag ~= share / (strength x beta), share = one wheel's fraction of the weight | Game (Roamer 105: sag ~ 1 / strength); that `strength` is relative to the vehicle's mass is Inferred (lowest scatter of three models over the retail scouts). **Note 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3): no Saber code scales `strength`/`damping` by any mass (they are Havok soft tau/damping), and the closed-form sag law is **Unknown**; treat this form as a per-vehicle calibration fit, not a law |
| **beta is uncertain by a factor of about two.** The 4-wheel retail scouts under 6 t give a median of 58 *if they rest as modelled* (spread about +-40 %, log-sd 0.35). The one direct measurement gives about 105: the Roamer 105 (2.9 t) in the editor's play mode, front height 0.265 / strength 0.017 and rear 0.23 / 0.030, rested level 0.142 m above its modelled stance | Inferred (58, `roadcraft retail survey`), Game (105, `roadcraft suspension --calibrate`). **A single beta shared across vehicles is superseded 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3): beta is not a constant; calibrate per vehicle. The Roamer 105's beta of about 106 is the only valid measurement; the retail 58 rests on the unverified assumption that the scouts rest as modelled |
| ~~Retail designs often rest topped out on the droop stop (e.g. Armiger: rest above its max of -0.05)~~ An artefact of reading min/max as stop positions: with the measured stops the Armiger rests between them | Superseded 2026-10-02 (was Inferred) |
| `damping` 0.12-0.25 on scouts; rigid axles use min = max = 0 with strength 0.25-1 | Retail |

### Designing an axle

With the measured stop geometry ("Stop geometry" below; the design rule itself is **Inferred**
until a vehicle is driven on it):

```text
height   = sag + lift          lift: how much higher than modelled it should rest
min      = -(sag + bump)       bump: travel up from rest (top stop at height + min)
max      = droop - sag         droop: travel down from rest (bottom stop at height + max)
strength = share / (sag x 58)
```

`roadcraft suspension --geometry measured --sag 0.16 --share 0.205 --lift 0.06 --bump 0.16
--droop 0.20` does this (min -0.32, max 0.04, height 0.22) and reports the rest and remaining
travel at beta, at +-40 % and at the measured 105 (`measured`).

Until 2026-10-02 this section gave min = lift - bump and max = lift + droop, which is still the
default `roadcraft suspension` and `vehicle.design_axle` (kept for pinned recipes). Those limits
put both stops `height` lower than intended. Whenever bump is less than height, the wheel then
rests on its top stop: the vehicle stands higher than designed with no bump travel (the same
example gives min -0.1, max 0.26, a top stop at 0.12 and a rest of 0.12 instead of 0.06).

Design at 58, the default. If the truth is nearer 105 the vehicle rests higher and stiffer than
designed (the sag is about 0.55 of the design), which keeps it off its bump stops; designing at 105
when 58 is right would sink it by 1.8 times the design sag, the failure already seen on the buggy.
Check that the `measured` case still leaves droop travel. Keep the bump stop reachable at the soft
edge only if ground clearance allows it: clearance at rest minus bump travel should stay above
~0.1 m or the belly scrapes (Game, buggy).

### Calibrating from a drive

Measure where each axle rests in the game (a side screenshot: the wheel-to-arch gap against the
model's) and give every axle to the solver:

```text
roadcraft suspension --calibrate '[{"axle": {"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0221}, "rest": 0.12, "wheels": 2},
                                   {"axle": {"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0318}, "rest": 0.12, "wheels": 2}]'
```

`rest` is + when the body is higher than modelled. With every axle listed the weight shares come out
too (the Roamer's rests give beta 105.7, shares 0.221 front and 0.279 rear). An axle resting on a stop
is refused: it says nothing about its spring. Record each calibration here with its vehicle.
Add `--geometry measured` so the stop test uses `height + min` / `height + max`: the example
above (height 0.22, min -0.1, rest 0.12) is then refused, because it rests on its top stop.

Weight share: with the centre of mass a distance `c` behind the front axle and wheelbase `L`, each
front wheel carries (1 - c / L) / 2 and each rear wheel (c / L) / 2.

### Retail scout values (for comparison)

| Vehicle | Mass (bodies) | Axle | min | max | height | strength | damping |
|---|---|---|---|---|---|---|---|
| Armiger Thunder scout | 1974 kg | Front / Rear | -0.42 | -0.05 | 0.275 / 0.295 | 0.016 / 0.018 | 0.16 |
| Don 71 | 1584 kg | Front / Rear | -0.28 | 0.45 | 0.15 | 0.015 / 0.02 | 0.15 |
| Minuteman K350 scout | 2800 kg | Front / Rear | -0.45 | -0.08 | 0.33 / 0.34 | 0.014 | 0.2 |
| Invictus Type A scout | 3600 kg | Front / Rear | -0.43 | 0 | 0.38 / 0.30 | 0.027 / 0.013 | 0.25 / 0.22 |

### Open

- beta: 58 (retail, assumed to rest as modelled) against about 105 (Roamer 105, measured). The buggy
  (`apb-axles-20260929`) and the Warthog (`wh12-axles-20260929`) were designed at 58; at 105 the buggy
  would rest about 0.13 m above its modelled stance instead of 0.06 and the Warthog about 0.07 m
  instead of 0, both stiffer than designed. Their next drives settle it (calibrate as above).
- The units of `strength` and `damping`, and whether `strength` really scales with the mass. Partly answered 2026-10-13 (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3): they are the Havok wheel constraint's dimensionless per-step soft tau and damping, with no Saber mass scaling; the static sag law that follows from them is still **Unknown**.
- Whether the steering rack also turns joints hung under an identity-oriented slot correctly on the
  right side (the buggy's v3 rig; awaiting a drive).
- Whether axles designed with the earlier formulas (min = lift - bump) rest on their top stops as
  the measured stop geometry predicts whenever bump < height. Check a vehicle's compiled axles with
  `roadcraft suspension --geometry measured --axle ...` before its next drive.

## Rig recipe for independent suspension (the retail ZiKZ 605E pattern)

1. Wheel slots as identity joints under the chassis at the wheel centres.
2. `axleControllerSettings.independentAxleSettings` for every slot.
3. Front: a steering joint per wheel under its slot at the kingpin; a rack bone at the steering rack;
   `steeringRackSettings` with `rackHalfLength` = kingpin x; `customSteeringJointObjName` on the slot.
   Rear: a plain hub joint under the slot. Hub / knuckle / caliper meshes on these joints.
4. IK chains pinned to the slot at their real points: upper wishbone (2 bones), lower wishbone +
   upright (3 bones, ending at the upper ball joint), dampers (hinge + prismatic), driveshafts. See
   [ik-visual-rigs.md](ik-visual-rigs.md).
5. Tie rods from the rack bone to the steering joint.
6. `lint-bro --class --tpl` before installing.

## Apoc buggy follow-up (2026-09-30)

The owner reported partial motion and detached parts after driving `apb-axles-20260929`.
The axle-controller presence checks passed, so presence alone does not validate attachment
or per-wheel response (**Game** symptom, **Build** checks). The follow-up candidate explicitly
sets `singleWheelID` to each slot's index, and removes the undocumented `isIndependent` field.
The mapping is supported by the SDK schema; improvement in this vehicle's runtime movement
remains **Open**. See the IK article for the independently verified reach/skin faults.

The repeated rear scraping report was not enough to establish spring bottoming as the sole
cause. A ray sample of the original rear hull showed collision in open space below the frame
and engine. The candidate decomposes the lower rear and retains two upper hulls, keeping the
existing suspension tune. Offline clearance checks include full bump and opposite-axle pitch,
with a 40 mm contact allowance. Terrain behavior still requires a drive.

## Apoc soft-flex revision (2026-09-30)

The owner reports stiff handling with the preceding linkage/collision candidate (**Game**).
The old 0.16 m design-sag tune is therefore not accepted as soft. Candidate
`apb-soft-flex-20260930` uses front/rear strengths 0.0126/0.0182, damping 0.085, stops
-0.18/+0.40 m and neutral height 0.36 m. Body angular damping decreases to 0.35.
These are authored **Build** settings, not measured runtime behavior.

The 0.28 m design sag plus 0.08 m lift keeps predicted rests off both stops at beta 34.8,
58, 81.2 and 105 (**Inferred**). There is no measured buggy rest height in this drive report,
so beta cannot be recalibrated honestly. The compact collision core excludes low rails and
side skirts to provide compression clearance. Full droop requires longer visual sliders
and coil overlap; recheck both endpoints after export. Softness, flex and terrain clearance
remain **Open** until the next drive.

## Apoc wheel-chatter damping trial (2026-09-30)

The owner drove `apb-mud-proxy-20260930` and reported rapid wheel chatter while the body
stayed fairly level (**Game**). The 0.085 damping inherited from the soft-flex tune is
therefore not accepted as controlled dynamic behavior. Reducing spring strength to obtain
compliance does not establish that damping should also be reduced; evaluate its transient
response separately (**Inferred**, supported by this report and retail comparison).

Candidate `apb-damping-20260930` changes only suspension damping: 0.085 to 0.16 front and
0.18 rear. Don 71 uses 0.15, Armiger scout 0.16 and Minuteman scout 0.20 (**Retail**, current
shipped BROs). The buggy retains strengths 0.0126/0.0182, stops -0.18/+0.40 m, height 0.36 m,
wheel-contact settings, compact CDT and corrected body mud volumes. More damping is intended
to settle wheel hop without removing slow articulation (**Inferred**). A static beta sweep
can verify rest margin but cannot validate chatter frequency, damping ratio or grip.
No measured buggy rest or dynamic trace was supplied, so beta is not recalibrated. Dynamic
improvement and handling acceptance remain **Open** until the next drive.

## Compiled wheel contact and persistent jitter (Apoc, 2026-09-30)

The 0.16/0.18 damping trial did not resolve the owner's wheel jitter (**Game** report on
`apb-coil-animation-20260930`). Do not infer dynamic stability from a static sag calculation,
rig closure or a spring animation repair. No buggy rest or dynamic trace was supplied.

**Build / Retail:** Compare compiled wheel properties. The buggy's EditableWheel scale
produced radii 0.3977/0.4161 and scaled width/rim radius, while mass remained 35 and the
donor radiusOffset remained 0.085. The installed Armiger scout class uses radius 0.448,
mass 125 and offset 0.045 on a 1974 kg body. The offset/radius ratios are approximately
21/20% versus 10%; wheel/body mass ratios are 2.8% versus 6.33%. Its compiled softForceScale
is 0.55 even though the referenced wheel BRO contains 0.25: the compiled class is the
runtime evidence. These comparisons do not make every differing value a fault.

**SDK:** `PropTruckWheel.isWheelStabilizationEnabled` defaults to false. When enabled,
the documented visual wheel position blends from physical position to a cylinder-cast
position between `maxSpeedFullPhysWheel` and `maxSpeedFullFakeWheel` (defaults 15 and
30 km/h). This smooths displayed wheels; it does not prove better physical grip or damping.
No explicit enabling entry was found in the surveyed shipped wheel classes. It is absent
from the BRO TruckWheel schema, so the Apoc adapter records and patches the native fields
explicitly and tests their presence. Recheck hub/coil attachment in the game at both speed
boundaries; source skinning checks do not establish which position the native rack follows.

**Inferred candidate:** `apb-handling-audit-20260930` uses 80 kg wheels (stock wheel/body
ratio scaled to a 1250 kg body), offset 0.04, lateral friction multiplier 0.6, damping
0.22/0.24 and torque 37000 (stock torque scaled by body mass and front wheel radius).
Soft-force scale 0.4, spring rates, ride height, travel, tyre dimensions, deformation,
collision and visuals remain unchanged. This is a coordinated handling trial, not a
measured solution. Native wheel stabilization is enabled at the SDK's 15/30 thresholds.

Shared `vehicle.wheel_contact_metrics` reports absolute compiled values and normalized
ratios, and validates enabled speed transitions. `test_wheel_contact_metrics.py` covers
compiled stock/buggy values and invalid inputs. The project handling audit uses this helper
for all gameplay and preview wheels. No universal mass or contact-offset threshold is
enforced because no controlled native jitter experiment supports one (**Open**).

## Dual-purpose articulation and overhang clearance (Apoc, 2026-09-30)

Increasing droop also changes the extreme pitched contact plane under body overhangs.
Recheck physical hulls and environment-effect proxies separately, even if their model
resources are unchanged (**Build**, Apoc analytical sweep). At stops -0.18/+0.58 m, the
unchanged compact CDT has a minimum 0.1131 m clearance including a 0.04 m contact allowance.
The rear-most body environment box needed its bottom raised another 0.06 m to preserve
the stricter 0.15 m effect gate; its resulting minimum is 0.1766 m. Do not weaken a
clearance assertion simply to permit extra travel. These are flat-contact-plane extreme
checks, not proof of collision clearance over arbitrary rock shapes (**Open**).

`apb-crawl-trophy-20260930` uses 0.76 m travel (previous 0.58), strengths 0.0098/0.0141,
neutral height 0.50, design lift 0.14 and retained damping 0.22/0.24. Estimated rest stays
off both stops at beta 34.8/58/81.2/105 (**Inferred**, no measured buggy calibration).
The owner's goal combines slow rock crawling and fast trophy-truck-like absorption;
the linear native spring/damper settings are a compromise, not a verified progressive
race suspension. Acceptance and the earlier jitter complaint remain **Open**.

Integration: existing project motion/body-effects checks enforce the separate margins,
and the compiled handling/package checks enforce the intended travel/gearing changes.
These asset-specific clearance thresholds are not promoted to universal toolchain rules.
Evidence: Apoc reports/motion_collision_audit.json, body_effects_audit.json and
vehicle_handling_audit.json for the crawl/trophy candidate.


## Native-limit sign correction from the Lada drive (2026-09-30)

> **Superseded in part (2026-10-02):** the measured stop geometry ("Stop geometry" below) explains
> this drive without a sign reversal. The v2 front sat on its top stop at `height + min` = 0.09; the
> trial's min -0.22 raised that stop to -0.04. Use `native_suspension.stop_positions` and
> `design_axle` (`--geometry measured`), not `bodyMin = -nativeMax` or `min = -(L + D)`,
> `max = B - L`. The measured travels and the trial's acceptance below stand.

**Game, RoadBuilder 7.3:** native `min/max` are wheel displacement along the
up axis: negative extends a wheel downward. The legacy `axle_report` uses
positive BODY lift instead. The earlier design examples above passed native
bounds straight into a body-lift solver; their stop-margin conclusions must
not be relied on. Convert bounds to `bodyMin=-nativeMax`,
`bodyMax=-nativeMin`, or use `roadcraft.native_suspension.native_axle_report`.
For a desired body lift L, bump B and droop D, native limits are
`min=-(L+D)`, `max=B-L`. Height/strength estimates and beta uncertainty remain
separate, and static predictions still require a drive.

On the Lada, unchanged spring/damper values with limits -0.09/+0.19 produced
front travel 0.000565/0.001170 m in a 0.28 m range. The isolated -0.22/+0.12
trial produced 0.093344/0.096716 m front and 0.141080/0.144484 m rear in a
0.34 m range; all wheels contacted the pad. It accelerated, stopped,
reversed and steered, then climbed the 30-degree ramp with all four contact
flags true in every sampled frame. This establishes this setup's short test,
not universal beta, long-run durability or owner retail acceptance.

Evidence: Lada `runtime/drive04/02_rest.json`,
`runtime/drive05_suspension_trial/review.json`, `runtime/suspension_trial.json`,
`runtime/ramp_sample_1.json` through `ramp_sample_4.json`, `ramp_stopped.json`.
Shared `native_suspension` helpers are wired into the Lada static and runtime
checks; focused tests preserve the measured failure and corrected cases.
The legacy API remains unchanged to preserve other projects' pinned recipes.

**Native tyre naming:** deformable wheels require a mesh object named `tire`
(author `tire_LOD0` etc.); a tyre material on a combined `wheel` object is
insufficient. Lada v1 crashed at `truck_wheel_prop.cpp:527`; separate `tire`
and `rim` objects compiled and spawned successfully in v2. The Lada audit
checks compiled names. Adding this to generic BRO lint is deferred because
that interface currently receives a body TPL, not the wheel model inputs.


## Lada mud-surface result, distinct from dozer-rut acceptance (2026-09-30)

V4 uses 60 kg wheels, damping 0.24/0.26 and softForceScale 0.22, with explicit scout tyre-deformation parameters. The native protocol measured stationary wheel centres without sample-to-sample movement on the `mud` surface, then low-range travel and steering with contact. All four resting wheel travels had reserve. These coordinated changes were not isolated one at a time, and extrusion-depth queries were zero; neither a particular cause nor a fix for deeply cut terrain is established. Keep the owner's original rut report open until that location is retested. Evidence: Lada v4 pinned driving result and `runtime/rut_candidate/measurements2`; grade **Game** for the bounded editor observations, **Open** for the original symptom resolution.

## Custom tread scale and terrain excavation (Lada effects v5/v6, 2026-09-30)

Do not infer excessive vehicle mass from deep or oversized tracks. Inspect wheel
`frictionMaterials.*.terrainDeformationFactor`, environment cylinders, trail width,
parallax depth and the mod reset descriptor separately from suspension/contact.
Lada v4 owner feedback reported much better driving but giant ruts and the wrong
tread (**Game, owner report**); that does not isolate a physical cause. V6 retains
1365 kg and v4 suspension/contact/gearing, scaling soil coefficients to 30%.
All 57 non-effects component comparisons match the v4 compiled baseline.

The native shader's longitudinal repeat is `trailParams.width[1] * height/width`
of `visuals.texture.nameTex` (TRAIL_DIFF). Projection `height/yOffset` define a
vertical projection volume, not circumference. Unroll one circumference into
a 1:8 image padded to circumference/8 and mask contact inside the measured tyre
width. Lada uses a 0.2822197 m padded envelope, 0.180797 m active contact width,
2.257758 m repeat and 0.009 parallax, derived from the actual source UV/normal
detail. Its donor used widthScale 1.8, TUZ tread and 0.05 parallax. These are
**SDK/Build** dimensions, not measured physical rut depth. Wheel environment
cylinders also needed width correction independently of the tread projection.

For mod wheels, mirror the whole `trailSfxDesc` into `defaultTrailSfxDesc`:
native mod initialization can reset the active descriptor. Compare compiled
contents, not only native descriptor object identity. The final Lada fixture
reported isMod=false with two distinct descriptor objects; it did not exercise
the retail mod-only reset branch. The complete compiled descriptor content is
equal, and runtime physical tyre width measured 0.202487618 m.

Evidence: shipped `wheel_trail.cls/.sfx`, `trail.vsh`, Roamer trail contracts,
Lada build-007/test-008 and v6 `effects_result.json`. Shared
`roadcraft.native_trails.custom_trail_report` checks reset parity, compiled texture
dimensions, TRAIL_DIFF binding, projection width and repeat; six focused tests
pass and Lada audits all four wheels. The rule is opt-in for custom trails.

**Game scope/limits:** final native startup and brief driving/braking passed with
four settled contacts. The fixture's extrusion readings remained zero and its
raised mud strip was pre-existing, not a new rut. Captures did not isolate the
new tread or measure rut depth. The owner's exact dozer-cut campaign terrain
still needs a comparison; 30% coefficients do not prove 70% shallower ruts.



## Missing `default` / `asphalt` friction from the Lynx mod sample (Lada v11, 2026-10-13)

The shipped sample `mods_source/bro/wheels/wheel_tuz_119lynx_mod.bro` lists only sand, grass, sub_mud, mud_grass,
gravel and mud_sand. Every retail scout wheel also defines `default` and `asphalt`; the Lada and any project copying
the sample inherit the gap:
- retail Lynx res: `default` 5 / 0 / 0.5 (frictionValue / terrainDeformationFactor / substanceFriction), asphalt 1.2 / 0 / 0.5
- Thunder, K350, Type A: `default` 1.75 / 0 / 0.5, asphalt 0.85 / 0 / 2

Without them the wheel falls back to engine defaults on roads, rock and any unlisted surface. Lada v11 (sha 308a32d1)
adds `default` 1.75 / 0 / 0.5 and `asphalt` 1.0 / 0 / 2, after a player report that the wheels "interact poorly with
the ground" (Venk88, 6 Oct). Evidence grade: **Retail data** for the gap; the effect on the report is **Unverified**
(no editor runs; owner drive pending). Check new wheel BROs for both entries.

## Stop geometry (measured, 2026-10-02)

**Game (KGS-25 editor bench; the Lada trials fit it too):** a wheel sits `height + min + travel`
below its modelled place, the spring travel (`GetCurrentSpringTravelDistance`) running from 0 at
the top stop (fully compressed) to `max - min` at the bottom stop. So the stops are at
`height + min` and `height + max`, and an unloaded wheel hangs at `height`, the spring's neutral
point, when that lies between them.

| Axle | Stops, m below modelled | Seen |
|---|---|---|
| KGS-25 candidate 02 fakes: min 0, max 0.22, height 0.05 | 0.05 to 0.27 | at 0.050 + travel |
| KGS-25 fix 1 idlers: min -0.15, max 0, height 0 | -0.15 to 0 | raised idlers hang at travel 0.15, exactly as modelled |
| KGS-25 fix 1 fakes: min -0.13, max 0.13, height 0.06 | -0.07 to 0.19 | at -0.07 + travel |
| Lada front, v2 limits -0.09 / +0.19 against the trial's -0.22 / +0.12, height 0.18 | 0.09 to 0.37 against -0.04 to 0.30 | v2 on its top stop (travel 0.0006); the trial rests at 0.053-0.057, between the stops |
| Lada rear, same two axles | | rests at 0.103 and 0.104: one spring equilibrium in both |

**A negative `min` raises the top stop:** the wheel may be pushed above its modelled place. It does
not extend the wheel down (this replaces the reading in "Native-limit sign correction" below).
Read this way, the retail scouts rest near their modelled stance between their stops at beta 58
(Armiger front 6 mm below it with 0.15 m bump and 0.22 m droop, Minuteman 2-3 cm); read as stop
positions, five of their eight axles would rest on a droop stop (**Inferred**). The Roamer 105
calibration stands: its rests (0.142) lie between its stops (min -0.4, max 0.4).

`roadcraft.native_suspension`: `stop_positions`, `position_from_travel`, and for design and
calibration `design_axle`, `rest_report`, `calibrate_beta` (`roadcraft suspension --geometry
measured`).

## Tracked vehicles

Moved to [tracked-vehicles.md](tracked-vehicles.md) (retail track layouts, the KGS-25 failure and
its fix, springs on light bodies, RC046-RC048).

## Independent front on a solid-rear truck (CAT 793D RC29, 2026-10-08)

**Retail:** the Nota Allegro (`auto_nota_allegro_*`) is the shipped pattern for a solid rear axle
with independently sprung, steered front wheels. Its class has `dependentAxles [{frame BoneAxleRear}]`
plus `independentAxles [{frame BoneAxleLeft|Right, singleWheelID}]` and one
`steeringRacks [{rightWheelFrame BoneRackRight, leftWheelFrame BoneRackLeft, rackHalfLength}]`
with no rack `frame`. Its tpl hangs `BoneAxleLeft/Right` (identity) under the chassis next to the
wheel, `BoneRackLeft/Right` (identity, the slots' `customSteeringJointObjName`) under them, and the
knuckle IK under the racks; the wheel slots stay identity joints under the chassis with no children.

**Build:** the 793D's front now copies that: identity `BoneAxleFront*` and `BoneRackFront*` at the
wheel centres, `singleWheelID` 0/1 (the slot indices), `rackHalfLength` 2.504, spindle/hub meshes on
the racks, strut and steering-cylinder chains (`HINGE2 [1,0,0]` + `PRISMATIC`) from the chassis pinned
to the racks, and a tie-rod chain based on the left rack pinned to the right one. The class was
patched directly; `lint-bro --class --tpl --markup` reports no findings. **Open:** whether the
slots, racks and chains move in game.

**Design note (Build):** physics wheels steer about their own centre, so the visual steering joint
sits at the wheel centre even though the real 793D kingpin is ~0.75 m inboard (the strut line).
The hub then stays centred in the rim and the IK strut tilts slightly at full lock instead.
Evidence: `RoadCraft/cat793d_detail/tools/axles.py`, `reports/package_audit_rc29.json`.


### Rim handedness and directional tread are separate checks (Dump Twuck preview, 2026-10-10)

**Source / Inferred visual diagnosis:** Dump Twuck v6 authoring previews reuse each wheel master on both sides, with a left-side 180-degree yaw. That maps (X, Y, Z) to (-X, -Y, Z): it turns the rim face and also reverses fore-aft directional features. The owner flagged the screen-right tyres as backwards. Verify rim handedness and tread direction independently across all six final wheel poses; radius, width and clearance checks cannot close that finding. A separate tyre variant or reflection remains a possible remedy until measured native wheel-object frames and tyre-direction markers establish the required pose. Do not generalize one donor's handedness or alter drive controls based on this image.

Evidence: Dump Twuck inspect-042-v6-peaked-mound, run 20261010T003736Z-3a344fc4bf44, and reports/revision_006/wheel_direction_review/{review.json,WHEEL_DIRECTION_ADDENDUM.md}, which pin the preview image/script, model_v6.py and final_status.json. No model or PAK was changed; native mounting remains open after three failed compilation attempts. The earlier source/evidence ZIPs retain their sealed bytes.

## Donor wheel-pool overrides are lost with the donor wheel pool (Kanga 25, 2026-10-10)

**Retail:** a truck BRO's `wheelPool` entry can override wheel fields (Baikal 5916: `truckWheel { softForceScale 0.4,
substanceFriction 2.1, activateCriticalCollisionTypeOnInit False }` plus per-surface `frictionMaterials`); the compiled
wheel class carries the override (0.4), not the wheel BRO's 0.19. A mod that replaces the donor wheel pool with its own
wheels keeps only the wheel BRO values. **Game (editor bench):** against the retail Baikal on the same drive the Kanga
showed about twice the rear-body angular jerk and wheel-travel step (slalom 2.3-2.6 vs 1.0-1.45 rad/s2, 0.014-0.019 vs
0.006-0.008 m per sample). Restoring softForceScale 0.4 alone lowered slalom chatter but braked harder and ran slower
(confounded by the c3 gear hunting). **Build (c5, owner's choice, unmeasured - no editor runs):** the full Baikal
override (`truckWheel` fields + `frictionMaterials`) merged into each Kanga `wheelPool` entry's `wheel`.



### Side-specific directional tyre geometry (Dump Twuck source fix, 2026-10-10)

**Source / Build geometry checks:** The new Dump Twuck candidate retains the three supplied normalized wheel masters for right slots and adds three left templates. Only tyre-local Y is reflected, face winding is reversed and invalidated custom normals are cleared; the rims and wheel markers retain the master frame. Under the preview's left half-turn, the placed tread is an X reflection with matching fore-aft Y and vertical Z features. All 48 independent saved-geometry checks pass across three wheel kinds and four LODs, including vertex positions, face normals, unchanged rim geometry, UVs and materials. The saved main model and peaked mound retain their previous hashes. Truck slots select the side variants without changing physical wheel order or controls.

**Correction, Game (owner's v9 drive, 2026-10-11):** "The tyres on the left are correct but on the right are
wrong." With the original tread on the right slots and the Y-reflected copy on the left, the two sides looked
different in the game. Under a half-turn of the left wheel (the preview's assumption) they would have matched,
so the engine places left-slot wheels as a mirror of the master (X), which keeps the tread's rolling direction.
For a directional tread, use the same tread on both sides: one master serves every slot (the rim face still
comes out on the outside, as the Lada's did). Dump Twuck v10 gives every slot the Y-reflected tread the owner
approved on the left (`TREAD_VARIANT` in dumptwuck_config.py). A rim-only observation (Lada) cannot tell a
half-turn from a mirror; tread direction can.

Evidence: Dump Twuck `reports/revision_007_tyres/{tyre_build.json,tyre_saved_audit.json}`, `tools/{tyre_sides_v7.py,audit_tyre_sides_v7.py}`, and `history/revision_007_before_tyres/preservation_receipt.json`. Decimal-rounded equality produced false failures at float boundaries; direct per-vertex and face-normal vector distances passed (maximum placed vertex error below one micrometre). This does not establish native mounting: measure the rendered **tire** object frame separately from the rim, then inspect both sides in a matching candidate run. The original tyre carries no verified manufacturer rotation arrow; the check establishes cross-side consistency. The local geometry validator is wired into the pinned inspection recipe and checkpoint. General shared enforcement is deferred until the native tire-frame evidence is complete.

### Brake parts on a skinned body do not spin (L275 v14, 2026-10-12)

**Build:** wheel slots carry the wheel tpls; nothing in the skinned body turns with the wheel. Skin rotors, hats and
hubs to the steering joint (front) or axle frame (rear) and keep them rotationally symmetric (no drilled pattern or
logo that should visibly turn). Calipers, splash shields and hoses on the same bone stay put while steering.
