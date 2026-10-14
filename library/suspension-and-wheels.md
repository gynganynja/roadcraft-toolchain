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
| The engine applies a fixed Ackermann: for each turn direction one wheel of a left/right pair gets 0.8 x the slot `steeringAngle`, and the other gets the full angle. The factor is hard-coded, so set `steeringAngle` to the inner-wheel lock you want. The rack and knuckles are visual only (symmetric), so at lock the outer knuckle is off its wheel by 0.2 x `steeringAngle` (Roamer 105: 30 against 24 degrees). There is no toe. Steer -1 held at rest gives the same 30/24 | Code (`FUN_14061d7a0`; research/physics_semantics.md "Steering geometry"), Game (Roamer 105, which shows the reduced wheel is the outer one) |
| `steeringCastor` (wheel class, slider 0-45) has no engine consumer that could be found, and no retail wheel sets it. Treat it as inert | Code search (Unknown), Retail |
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
| **An unloaded wheel hangs at the spring neutral (position = `height`), not at the droop stop.** There is no preload term: the wheel body is created at slot minus height, which is the soft constraint's pivot, and its own weight pulls it only ~0.16-0.22 m further. A droop stop beyond the neutral is never reached when the wheel lifts (forklift tilt, a wheel over a hole). For flex, put the neutral at or past the droop stop (`max <= 0`), as half the retail axles do (Armiger 0.275 / -0.05, Minuteman 0.33 / -0.08, Invictus 0.38 / 0), and lower `strength` so the loaded rest stays where wanted. Nothing else limits droop: the axle controller only moves bones and `fakeStrength` is fake-wheel mode only | Code (laptop, physics_semantics.md "Unloaded wheel rest"), Game (Trophy Truck v3: "wheels still don't droop") |

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
- Watcher 61 drive 1 (2026-10-13, all five configurations designed at beta 58, sag 0.18, lifts 0-0.10): owner
  "The suspension on all of them is way to high". Another vehicle on the beta ~105 side (at 105 the design rests
  ~0.15 m higher, plus bigger tyres). Expedition pass 2 is designed at beta 105, rest as modelled, same strength
  (height 0.0994, `C:/RC/watcher61/tools/w61_config.py` `suspension()`). If it now rests level with the model,
  calibrate with `roadcraft suspension --calibrate` and consider making 105 the design default.
  Result (owner drives 2-3): the beta-105 rest was close. The owner asked only for "a little bit more" lower (0.04 m, applied as a
  -0.04 lift) after softening the springs x0.7 (strength 0.0179 / 0.0156 on 2.3-2.6 t) and damping to 0.12 / 0.13.
  That shipped to all five configurations (v6). This is a second vehicle supporting beta ~105 over 58. **Game** (owner
  feel, no measured rest).
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

Without them (engine facts, library 4fe7b99): a missing `default` gives frictionValue 2.0, and a surface with no entry
(asphalt here) keeps the previous surface's friction, so road grip depended on where the car came from. Lada v11 (sha 308a32d1)
adds `default` 1.75 / 0 / 0.5 and `asphalt` 1.0 / 0 / 2, after a player report that the wheels "interact poorly with
the ground" (Venk88, 6 Oct). Evidence grade: **Retail data** for the gap; the effect on the report is **Unverified**
(no editor runs; owner drive pending). Check new wheel BROs for both entries.

`roadcraft compare` against the retail Lynx (91 wheeled trucks) on v11 also flags: `ground.substanceFriction` 0 (schema
default; retail 0.75-4.5, median 1.6) and wheel mass 60 (retail minimum 70). Both come from the v4 rut fix, which
rewrote `ground` and `mud` as `{terrainDeformationFactor}` only, so they also run at frictionValue 2.0 (schema default)
against 0.8-1.0 on the Lada's other surfaces. When a project scales excavation, edit `terrainDeformationFactor` in the
existing entries instead of replacing them. Not changed in v11: the owner accepted the v4-v7 handling with these
values, so a correction waits for the owner's call.

Owner decision 2026-10-13 ("correct everything you found"): Lada v12 (sha f2fedd23) writes full `ground` (1.0 / 0.3 / 1.5)
and `mud` (0.8 / 0.3 / 2.5) entries and raises wheel mass to 70 kg. `compare` outliers fall from 8 to 5. The derived
four-wheel mass, 280 kg, is still under the retail 340 because the lightest retail trucks carry more wheel mass than
70 x 4. Unmeasured; owner drive pending.

## Wheel ruts: what deforms the terrain (code analysis, static, 2026-10-14)

Source: `C:\RC_RE\research\physics_semantics.md`, "Terrain deformation under wheels".

There are three separate channels. None of them is a terraforming brush; the dozer `TerraformingSystem` and its 1.5 m dig cap are a different path.

| Channel | What drives it | Grade |
|---|---|---|
| Physical extrusion | A contact listener on every physical wheel body (fakes too). Per contact point it adds a depth to the terrain's per-cell map and writes it into the 2x2 cells around the point. It writes only on deformable-layer cells, more where the ground is wet. Gate: dbg var `physics/truck/enable wheel extrusion from wetness` | Code |
| Visual mud push | `vfx.vfxSkeleton` cylinders on `_wheel` with `systems` bit 16 (mud; 2 water, 8 grass) | SDK flags; Game (Apoc body boxes) |
| Rut decal | `prop_wheel_trail_rb` (`trailParams.width`, height map, parallax) | Retail/Code (SSL) |

**Depth of one stamp (Code, `FUN_140dbcf50`):**

```
terrainDeformationFactor * (softForceScale/0.56 + 0.5) * min(1, (truck mass / wheel count - wheel mass) / 4000)
   * ( 0.24 / ((clamp(width/0.52, 0.25, 4) + 1)/2) + 1.44 * max(0, |spin speed - ground speed| - 0.5) * clamp((speed - 1.2)/2.4, 0, 1) )
```

Inferred: the meanings of truck mass, wheel count, spin and ground speed. What follows from the law:
- **Code:** `terrainDeformationFactor` (from the friction table entry for the current surface) scales only this depth. It does not scale sinkage (the separate soft-contact force), the mud push or any radius.
- **Code:** `softForceScale` also scales ruts: 1.0 digs 2.3x deeper than 0.28.
- **Code:** a wide wheel digs less in its static term.
- **Code:** wheelspin above 0.5 m/s, at more than 1.2 m/s, digs much more.
- **Code:** the stamp footprint is the terrain cell grid. No wheel or vfx size sets it.

**An empty `vfx` is not "no ruts":**
- **Inferred:** the wheel pushes no mud, bends no grass and makes no splash.
- **Code:** the physical extrusion and the trail are unaffected.
- **Retail:** the 5111B dragline ships empty `vfx` on its end wheels.

**Rules (Retail unless graded):**
- `terrainDeformationFactor`: 0 on asphalt, gravel and `default`; 0.25 on mud and sand; up to 2.5 on grass and ground (HT500).
- Cylinder: radius 0.85-1.2 and height 0.5-1.5 in wheel-model units; `systems` 18 or 26. No retail cylinder has a zero or negative dimension.
- **Code (SSL):** mirror `trailSfxDesc` into `defaultTrailSfxDesc`, or a mod wheel loses its trail (`ResetTrailDesc`).
- Crawlers: [tracked-vehicles.md](tracked-vehicles.md), "Ruts, mud and trails under a crawler" (RC079).

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

**Note 2026-10-14 (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, "Unloaded
wheel rest"):** the stop positions are confirmed from code. The spring neutral is also confirmed at
`height`. One correction: an unloaded wheel does not hang exactly at `height`. Its own weight sags
it further, by roughly as much as the loaded sag (about 0.15-0.2 m at strength ~0.015 and damping
0.14; Inferred). It reaches the droop stop only when `height + max` lies within that reach. To make
wheels hang on the droop stop, use `max <= 0` (neutral at or beyond the droop stop), as 15 of the
30 retail survey axles do (Armiger, Minuteman, Invictus).

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

### Engine-side chatter sources (code analysis, static, 2026-10-14)

| Rule | Grade |
|---|---|
| Soft contact is two-rate. Each wheel contact is scaled by `softForceScale` (terrain and dynamic bodies) or `softForceScaleStatic` (other fixed bodies). Past a penetration of physRadius/4 the scale ramps to fully rigid within a further small depth. A soft tyre (e.g. the Kanga's BRO 0.19 instead of the Baikal override's 0.4) sinks further and reaches the rigid band on every load peak, which reads as jerk. Restore the donor's override before tuning anything else | Code (`FUN_140ca86d0`); effect Inferred; Game ("0.4 alone lowered the chatter") |
| `activateCriticalCollisionTypeOnInit` sets Havok quality CRITICAL: continuous (TOI) collision against dynamic bodies too. Against terrain it adds nothing over the default. It matters where a tyre touches a truck body, its own carrier included. All 515 retail wheel classes set True; the Baikal 5916 pool sets False. Test False as a single variable on a chattering wheel that touches its own hulls | Code (`FUN_140dc8e50`, `FUN_14155f340`, map at 0x1450c2a30); Retail; effect Inferred |
| A wheel collides with its own carrier body's hulls, and a buggy's carrier is the chassis. Keep chassis, fender and stop-block cdt clear of each tyre across full bump, full droop and full steer: those contacts are scaled by `softForceScale`, get CRITICAL TOI, and are a prime suspect for the Apoc chatter | Code (filter); Inferred (Apoc) |
| Tyre friction is mu = sqrt(wheel `bodyFriction` x the other surface's friction): static and terrain default 1.2, or the per-triangle mesh material. Dropping a donor's `frictionMaterials` changes mu on every surface | Code (`FUN_140ca8fd0`) |
| `sidewaysFrictionMultiplier` / `sidewaysFrictionMaxVelocity` act (WALL-E pivots changed with them), but their engine reader could not be found. Keep retail values (multiplier 0.1-0.85, max velocity 1) | Game (tracked-vehicles.md); Code search (Unknown); Retail |



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

## Load-adaptive suspension (code analysis, static, 2026-10-14)

Full analysis: `C:\RC_RE\research\physics_semantics.md`, "Load-adaptive suspension".

| Rule | Grade |
|---|---|
| `linearLimitsStiffness` / `linearLimitsDamping` are **not** bump/droop-stop softness. They soften the wheel's sideways and fore-aft location (Havok `lin1`/`lin2` tau/damping factors). The stops are always hard, so there is no progressive or second-stage spring in the wheel joint. Leave both at -1; no retail truck sets them | Code (reflection plus `FUN_140cac360`), Retail (0 of 124) |
| `strength` / `damping` are the suspension atom's `tauFactor` / `dampingFactor`. Nothing changes them at runtime: there is no SSL setter, and the desc is read once at wheel init | Code |
| Whether the wheel-joint sag grows with payload is **Unknown**. A two-launch Dump Twuck bench (empty vs `spawnFull`) settles it; the protocol is in the research file, section 2 | Open |
| For a large payload swing, use the retail **physical series spring**: wheel joint near-rigid (strength 0.25, damping 1.0, min = max = 0, `height` = lift), wheels parented to axle/side bodies on a `tpl_markup_constraint_prismatic` with `tpl_markup_spring_motor{spring N/m, damping N·s/m}` sized `k = loaded axle load x g / loaded sag`. Retail precedents: Lynx scout / Mutt / trailer, 2e5-6e5 N/m on 500 kg axle bodies; ZiKZ 605E trailer, balancers 2.1e6 N·m/rad | Retail; sag proportional to load Inferred; not yet driven on a mod |
| Retail dump trucks (Baikal 65206, Tayga, Voron, OFT96) use only soft wheel joints: strength 0.025-0.08, **damping 0.35-0.75**, 0.25-0.5 m of bump travel from neutral. Their spring-motor hinges are frame-roll articulations, not load springs | Retail |
| A load volume's payload is its own rigid body, joined to `parentBody`. Its mass follows the fill (minimum 1 kg); its COM stays at the volume mesh's centroid | Code (`FUN_1405e2590`, `FUN_1405dc380`) |

### Series spring as built: Mammoth (CAT 793D) RC61 (2026-10-14)

Package `Mammoth_20261014_SeriesSpring_RC61.pak` (sha 8bf628da): built, `validate` 0 new against the installed
package, `lint-bro` 0/0; **not installed, not benched, not driven** (Build).

- **Front, per wheel:** a 6 t body on a prismatic, `childRotation [90,0,0]`, -0.23/+0.20, spring motor
  3.51e6 N/m, c 2.71e5.
- **Rear:** a 4 t heave body on a prismatic, -0.27/+0.22, 1.13e7 N/m, c 8.8e5. Under it, a 12 t axle-housing
  body on a roll hinge (`childRotation [0,0,0]`, +-4 deg, 7.23e6 N·m/rad, c 5.6e5), carrying both duals.
- **Wheel axles:** min 0 / max 0 / strength 0.45 / damping 1, height 0.15 (front) / 0.12 (rear).
- **Chassis:** 72 -> 44 t, so the total mass and COM are unchanged.
- **Design sag:** front 0.090 / 0.149 m, rear 0.046 / 0.199 m (empty / loaded with 218 t).

| Rule | Grade |
|---|---|
| A wheel slot's parent body is the nearest physics bone above the wheel node in the tpl tree. Re-parenting the wheel bones in Blender is the whole hookup; there is no class field. `physics report` resolves `slot.parentBody` this way | Build |
| Move the axles controller's visual frames (`BoneAxleFront*`, `BoneAxleRear`) under the sprung bodies too. With min = max = 0 the controller shows no wheel travel, so frames left on the chassis detach visually | Build |
| A rigid rear axle needs two bodies to keep cross-axle articulation: heave on a prismatic, then roll on a hinge along the truck axis, with roll rate = heave rate x strut spacing^2 / 4. A single prismatic body removes articulation | Build (design) |
| Keep wheel mass / sprung-body mass at or below about 1, the retail maximum. A 3 t front body under a 5.7 t wheel gave `slot.massRatio` 1.9 in `compare` | Build, Retail |
| Identity-frame new bones (Blender head -> tail along +Y, roll 0) come out identity in the tpl (as `BoneDump_cdt` / `BoneAxleRear`), so prismatic-down is `childRotation [90,0,0]`. This confirms the Dump Twuck example's inferred axis at Build grade | Build |
| A linear spring cannot serve a 4.3x axle-load swing (rear 53.5 -> 229.6 t) at both <= 0.10 m empty and <= 0.2 m loaded. Sizing for loaded leaves the empty rear at 0.046 m. This is why the two-payload bench, and a two-stage option, matter | Build (design) |
| RC61 gave the four sprung bodies `collisionLayer = "no_collision"` (copied from secondary-physics props). At spawn every tyre sank ~0.7-1 m and the truck rested on its hulls. RC62 removes the four lines and is not yet driven | Game |
| **A wheel takes its collision layer from its parent body at spawn.** Every spawned truck runs `SwitchPhantomState(false)`, which calls `PropTruckWheel.ResetCollisionFilterInfo` on each wheel and copies its parent body's layer onto it (an unset/`default` parent reads `constr_vhc`). A wheel carrier on `no_collision` therefore gives `no_collision` wheels, with no ground contact: that was RC61. The wheel class's own `collisionLayer` lasts only until then. Never put a wheel-carrying body on a non-colliding layer. No retail wheel carrier (251 resolved) sets `collisionLayer` | Code (`FUN_140dc8ff0`; research/physics_semantics.md "Jointed-body collision filtering"), Game (RC61 bench), Retail |
| Inside one truck, only a body and its **direct** constraint parent are filtered (the markup's constraints set the sub-ids, child first; the layer matrix is not used). Siblings, grandparent pairs, a body against a body fixed to the chassis (e.g. a sprung body vs `BoneBody_cdt`), and a wheel against its own carrier body and sibling bodies all collide. A wheel is filtered only against its carrier's constraint parent. Markups with **31 or more constraints get no filtering at all**. The first-listed constraint's child (sub-id 0) is not filtered against its own children. A markup Collision Group stops its members colliding with each other but replaces their constraint filtering. So a sprung box overlapping the chassis's **own** hulls is safe only when the chassis is its direct parent; overlaps with the body, the dump, a sibling, a tyre, or the roll body against the chassis are not | Code (`FUN_14153cb90`, `FUN_1415abce0`, `FUN_141a27c00`); Retail (7 of 118 truck markups have 31 or more) |

#### Headless bench of RC60/RC61/RC62 as built (laptop, 2026-10-14; `C:\RC_RE\bench-headless\mammoth\results.md`)

| Rule | Grade |
|---|---|
| Engine start crashes the editor engine on all three builds. The class's blueprint plays truck shakers "EngineStart" / "EngineShutdown", but its `prop_truck_shaker_native_controller` is empty ("Shaker hasn't been found"; launch 1). The comparison below was run with the engine off | Game (engine headless) |
| **RC60 (control)** stands on all four wheels (`isOnGround` 1), tyre bottoms 1.8 cm above the pad, with no motion at all over 40 s | Game (engine headless) |
| **RC61 sinks because its sprung bodies are `no_collision`.** All four wheels sit 1.09-1.13 m below the pad from the first sample (0.08 s), then stay constant; `isOnGround` is 0 throughout. The chassis rests on its hulls, 1.05 m lower than RC60. The rig is intact: the joints sit at +0.023-0.028 m (droop under their hanging weight only, k-consistent), roll 0, never at a limit, and each wheel stays 0.14-0.15 m (= axle height) below its body. So the wheels simply have no ground contact. This overturned the first static reading; the mechanism is now traced (see the wheel-layer row above). Never put a wheel-carrying body on `no_collision` | Game (engine headless; A/B with RC62); mechanism Code (the wheel copies its parent's layer at spawn, row above) |
| **RC62 is unstable from spawn, not a steady oscillation.** At the first sample (0.08 s) the truck is already thrown 4 m up and rolled about 80 deg, with the front prismatics at or through their -0.23 bump limit (-0.25). It tumbled for about 20 s, left the pad, fell 17 m and ended upside down. Limits were overrun: roll ±10.5 deg vs ±4, rear -0.279 vs -0.27. The roll hinge sat on a limit in 61% of samples. It never settled. This is the overlapping cdt (every tyre starts inside its own sprung body's hull) once the layer filter is gone | Game (engine headless); cause Inferred from the geometry |
| Fix order for a series spring: keep the sprung bodies on a colliding layer **and** keep their cdt_ hulls clear of every wheel (README variant A). Then judge the motor regime (rear heave c·dt/m 3.7), which these parked runs could not load | Game + Build |
| RC60 readback at rest: wheel physical radius 1.6223 (class radius 1.682), max spring travel 0.45 front / 0.75 rear, `softForceScale` 0.24, no prismatic constraints; chassis, body and dump on layer `constr_vhc` | Game (engine headless) |
| The series-spring regime is outside retail per 60 Hz step. Rear heave: k·dt²/m 0.79, **c·dt/m 3.7** (4 t body between the 44 t chassis and 34.8 t of roll body plus duals). Front: 0.16 / 0.75. Retail: 0.11-0.33 / 0.4-0.6. A light link with c·dt/m > 2 is the leading candidate for RC62's limit-to-limit swing and a candidate for RC61's sinking (solver drift in the chain) | Build (arithmetic); mechanism Inferred, not benched |
| The front sprung cdt (a 0.7 m cube at the wheel centre) lies wholly inside its 1.68 m tyre, and the rear roll box reaches ~0.4 m into the inner duals. With the layers removed (RC62), every tyre starts in deep contact with its own sprung body. That predicts a permanent shake | Build (geometry, `series_spring_rc61.py`); effect Inferred |
| RC62 (RC61 minus the four `no_collision` lines; installed as `mammoth.pak` sha cc4c712b, then rolled back to the 2026-10-13 build 2adf6d7a at 12:08) no longer sinks. But the whole truck shakes and the suspension swings slowly from limit to limit, constantly, even parked and empty | Game (owner) |
| Keep every sprung body's cdt_ hulls clear of its own wheels, and keep them clear over the whole steering sweep: rotate the wheel about the steering joint by +-`steeringAngle`. Also keep them clear of sibling sprung bodies and of the chassis. RC62 brought back these contacts, and the lead reports a 0.7 m front cube at each wheel centre (inside the 1.68 m tyre) and a rear roll box overlapping the inner duals by 0.4 m. Overlapping hulls in one vehicle are pushed apart every step, which fits a constant shake while parked. Do not hide an overlap with `no_collision`: that was RC61, which sank. No lint rule: per-hull extents are not decoded, and a node-origin test hits 12 retail trucks (roller forks, track rollers) | Code (filter); Game (RC61/RC62); Inferred (overlap and cause) |
| A spring motor's per-step numbers use m_eff, the constraint row's virtual mass from the **two jointed bodies only**. m_eff is at most their reduced mass m1·m2/(m1+m2) and never includes the load carried below. The engine computes k·dt²/m_eff and c·dt/m_eff and **clamps each to 1**. So the most it can deliver is a rate of m_eff/dt² and a damping of m_eff/dt (at 60 Hz: 3,600·m_eff and 60·m_eff). Requests above that are silently capped, not unstable. maxForce is HK_REAL_MAX: there is no force clamp | Code (`FUN_1442406f0`, `FUN_14423aa80`, `FUN_141594b60`; physics_semantics.md 'Spring-motor stability') |
| Keep load-bearing prismatic springs at k·dt²/m_eff ≤ ~0.4 and c·dt/m_eff ≤ ~0.7. That is the retail maximum: the TUZ Lynx frames run 0.14-0.22 / 0.52 and the Lynx trailer axles 0.28-0.38 / 0.53-0.68. RC62's front prismatic is at ≥ 0.18 / ≥ 0.86. The rear heave is at ≥ 0.86 / ≥ 4.0, so its damping is clamped and only ≤ 2.2e5 of the 8.8e5 N·s/m arrives (25 %). To deliver a damping c, m_eff must be ≥ c·dt. Lint RC076 flags this | Code (clamp), Retail (62 prismatic springs, 0 flagged), Inferred (that the shortfall causes the swing) |
| Keep a prismatic sprung body at ≥ 1/2 of the mass hung below it and ≥ 1/8 of its parent's mass. Retail goes no further than 2.0 and 8 (Lynx). RC62's rear heave is a 4 t link between 44 t of chassis and 34.8 t below it (the 12 t roll body and two 11.4 t duals), so 8.7 and 11 | Retail; Inferred (that exceeding the ratios fails) |
