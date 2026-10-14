# Tracked vehicles

Start here for crawlers: cranes, excavators, dozers and tracked carriers. Sources: a survey of the
33 shipped tracked vehicles (`roadcraft retail tracks`) and the KGS-25 crane, measured on the
editor bench and driven by its owner (2026-10-02). Suspension values in general are in
[suspension-and-wheels.md](suspension-and-wheels.md); how to measure a change before installing it
is in [physics-bench.md](physics-bench.md).

## How a track is described

| Rule | Grade |
|---|---|
| `truckSettings.tracks[]`: `wheelIds` lists the real wheels (wheel-slot indices), `fakeWheelIds` the support wheels, `visualWheelSlots` the road wheels drawn under the belt, `parentTracker.locator` the body the track follows | Retail, Build |
| Every slot, real or fake, picks a suspension axle (`suspensionCollectionItem` in the BRO, `suspensionCollectionAxleIndex` in the class) | Retail, Build |
| A wheel's radius is its `EditableWheel` scale, so a wheel's lowest point is the slot centre minus that scale | Retail |
| Body masses, centres of mass and constraints live in the model's `.tpl_markup`, which the game reads at load; the compiled `.tpl` holds none of them | Build, Game (KGS-25 fix 2 changed only markup and class text) |
| `hkCenterOfMassOffset` is in the body's engine axes (Y up) and is added to the collision centroid; `havokMassCenter = False` + `boneCenterOfMassOffset` sets it absolutely (frames.md). Retail cranes keep the centre of mass low with it (Vostok ETV89: arm `[0, -2.5, 0]`, hull `[0, -1, 0]`) | Retail; Game (WALL-E bench) |
| Compiled retail classes leave `parentFrame` empty. A wheel follows the nearest body bone above its wheel bone (Baikal 65206 hauler, Arling 750R and DS-55 rollers), so removing `parentFrame` does not move a wheel nested under a track-frame bone onto the hull: that needs the bones re-parented in the model | Retail; mechanism Inferred |

| Track section model (`section.tpl`): five shoes, one bone each, spaced `segmentLength` apart. Every bone sits on its shoe's **inner** face (the face that runs on the wheels) and the ground side points along the bone's native -Y (Blender -Z with the KGS bone roll). Retail TC305: shoe from -0.100 (ground side) to +0.052 about its bone, section height 0.2; TUZ 303: -0.022 to +0.115 (thin plate, tall guide horns), height 0.1; KGS-25 and D11 sections follow the same rule | Retail (bone frames and per-object bounding boxes read from the compiled `.tpl`, retail-data.md), Build |
| `section.height` is the distance from a wheel's surface to the tread's ground face: physics rolls on `radius + height` (the D11 / HT500 speed checks), so build the shoe with its ground face `height` below the bone | Retail, Inferred |

## What carries the weight: the retail layouts

`roadcraft retail tracks [truck] --game <sdkRoot>` lists every track's wheels with their role, axle
kind (rigid: min = max; stops: min 0 and strength 0.01 or less, so the wheel rests on its stop;
sprung: anything else), the body each hangs on, and which reach the ground (lowest point within
6 cm of the track's lowest). Retail, 32 vehicles with readable models (Warden Kochevnik's did not
parse):

| Ground contact, per track | Vehicles |
|---|---|
| Sprung real wheels, no ground fakes | 7: TUZ 303 Karelian (3), Vostok MU97 bridgelayer (2), Vostok ETV89 crane, Khan Lo Strannik |
| Rigid real wheels with sprung fakes | 6: EPEC LT200 (2), Aramatsu Forester Neo (2), MTK 100M (2) |
| **Rigid real wheels at ground level, fakes on their stops beside them** | 6: EPEC TC305, EPEC MAG240, Greenway HT500, Arling 120, DS-135 (2) |
| Sprung real wheels with sprung fakes | 5: MTK MD76 (3), Vostok TK53 Krot (2) |
| Rigid real wheels with rigid fakes | 5: Alces PL30C, Aramatsu Kite3, EPEC TC305 grabber, dragline 5111B (2) |
| Sprung fakes only, real wheels raised | 3: Aramatsu Bowhead, Vostok ATM53 (2); the fakes have min < 0 and strength 0.045-0.08 |

**No shipped track rests on stop fakes alone.** Near-zero fakes (min 0, strength about 0.001)
appear only beside rigid real wheels at ground level, e.g. EPEC TC305: fakes min 0 / max 0.4 /
height 0 / strength 0.001 / damping 0.3 (Retail). Nor does any shipped vehicle weld a
wheel-carrying body to the hull with a fixed constraint: track frames and bogies hang on hinges or
slides (Retail, RC047). Retail track frames are heavy: Greenway HT500's weigh 7.5 t each, 12.5 % of
its body mass.

**Retail springs its track frames.** Greenway HT500 (Retail): `BoneTrackSusp_L/R_cdt`, 7.5 t, on a
`tpl_markup_constraint_hinge` with `childRotation [0, 90, 0]`, `limited` -5..5 deg and
`motor = { spring = 10000000, damping = 11000000, __type = "tpl_markup_spring_motor" }`, the pivot at
the frame bone (z -1.86 on a track running 1.03 to -2.87, rear-biased). The owner on the vanilla
HT500: "the track frames have springyness, allows the wheels to move smoothly up and down; my mods
don't" (Game, 2026-10-13). A spring motor takes real units and unlimited force; a position motor's
`spring` key is never read (physics_semantics.md T5, read_fields.md). Mods: Goliath D11 already
hinges its frames HT500-style (+-5 deg, 1.56e7 / 1.7e7); T-80 +-2 deg, 1.2e7 / 4.4e6; Hitachi
EX5600 has no frame bodies; KGS-25 welded its frames with `tpl_markup_constraint_fixed` until
candidate f841eb34 (Build).

## The KGS-25 failure: "like there isn't anything underneath it"

Owner report on candidate 03: the crane lifts on one side and is pushed around while driving.
Candidate 03 had a real idler and sprocket 0.30-0.33 m up, seven stop fakes per track (min 0,
max 0.22, height 0.05, strength 0.0013) on 2.5 t track frames welded to a 19.9 t hull (41,180 kg in
all). On the bench (Game, editor play mode; pad drive with two pivot turns at pedal 0.3,
steer +-0.8):

| Variant (candidate 03 base) | Max roll, pivot + / - | Hull | Yaw in 4 s |
|---|---|---|---|
| Candidate 03 | 4.0 / 2.8 deg | drops 5 cm; one track sinks up to 19 cm into the static pad while its wheels report ground | 35-41 deg |
| Fix 1: fakes sprung from the vehicle-mass formula (min -0.13 / max 0.13 / height 0.06 / strength 0.05), idlers min -0.15 | parked at 2.8 deg roll, 1.3 deg pitch | left-rear wheels on their stops, right track extended | |
| EPEC layout: the end road wheels real and rigid (min = max = 0, strength 1, damping 0.85), fakes as EPEC TC305, hull centre of mass `[0, -1, 0]` | 2.0 / 2.3 deg | 2.5 cm | 31-47 deg |
| Frames 7.5 t, hull 9.9 t (total kept), candidate 03 suspension | 4.2 / 4.3 deg; a track lifts (travel 0.22) | 2 cm | 40 deg |
| Hull centre of mass -1, turret and boom -1.5 | 2.7 / 2.0 deg | 1-3 cm | 40 deg |
| **Fix 2: EPEC layout + 7.5 t frames + 9.9 t hull + hull centre of mass -1** | **0.2 / 0.2 deg** | under 4 mm | 53 deg |

At full inputs (pedal 1 straight, pedal 0.6 at full lock) both candidate 03 and fix 2 judder in
the pivots, a stick-slip lurch at about 1 Hz. Fix 2 lifts a track less (7 cm against 13-15 cm),
keeps roll at 0.8-2.0 deg (candidate 03: 1.5-2.4) and settles at once.

Candidate cause from the engine code (physics_semantics.md T3, code analysis, static): at full lock
the engine zeroes the inner track's wheel spin every step, an unlimited brake, and the TC305 curve
`steeringInputToInnerTrackTorqueMult` ends at -1. Trial (2026-10-13): KGS-25 build cf9dca20, whose
only change against 5c4dd65d is that curve ending at -0.6 (`[0,1, 0.5,0, 1.004563,-0.6]`, main and
preview classes). The owner: "felt the same, maybe a bit smoother" (Game, one drive, first
impression). A weak positive, not a fix: the inner-track brake is not the main source of the
tracked jank. Not yet benched against a retail crawler.

The owner drove fix 1 in the game: "it does it worse now", "bounces or wobbles" (Game). Fix 2 is
installed; the owner's drive is pending.

Later KGS-25 drives (2026-10-13; owner's symptoms against the vanilla TC305: a bouncy, jittery hull
and the steering feel off, not tipping or grip):

| Build | Change | Owner | Grade |
|---|---|---|---|
| cf9dca20 | inner-track steering curve ends at -0.6 | "felt the same, maybe a bit smoother" | Game, one drive: weak positive |
| 93c5e889 | TC305 wheel friction tables, `softForceScale` 0.75, drive/idler wheels 120 -> 450 kg | "feels better, still a bit janky when one wheel is climbing something" | Game, one drive: positive |
| f841eb34 | track frames on the HT500 sprung hinge instead of a weld | wants softer springiness; the idler should conform to what it climbs | Game, one drive |
| 3cb0efda | softer frames: hinge +-8 deg, spring motor 3e6 / 3.3e6 (and hook ball-and-socket) | not yet driven | Build |

### Headless bench of the five builds (2026-10-13, laptop)

Grade **Game (engine, headless play)**: the windowless editor engine, each build's pak overlaid on the 2026-10-02 bench
project (`roadcraft.pak_overlay`), checked in the engine by readback (softForceScale, frame-hinge motor spring and
damping). All 18 runs completed (six variants x flat `normal`, `harsh` and a single-track step), in 21 launches.
**One run per cell, so run-to-run noise is unknown.** Scenarios: `library/bench-scenarios/kgs25_*.json`. Results:
`C:\RC_RE\bench-headless\kgs25\results.md`, copied to `\\192.168.0.129\Downloads\roadcraft_laptop_research\kgs25_bench\`.
esults.md`, copied to `\192.168.0.129\Downloads
oadcraft_laptop_research\kgs25_bench\`.

**Step (left track onto a 0.3 m slab, low gear): the hinged frames conform; the welded ones do not.**

| Build | Left frame pitch vs hull (deg) | Front sprocket / rear idler travel (mm) | Mid road-wheel spring (mm) | Hull roll / pitch peak (deg) | Hull jitter roll / pitch RMS (deg) | Residual pitch peak-to-peak (deg) | Settle after stop (s) |
|---|---|---|---|---|---|---|---|
| 5c4dd65d baseline (welded) | 0.11 | +13 / -11 | 170 | 6.4 / 4.35 | 0.47 / 0.33 | 2.67 | 1.09 |
| cf9dca20 curve -0.6 (welded) | 0.08 | +15 / -14 | 173 | 6.9 / 4.26 | 0.45 / 0.32 | 2.51 | 0.55 |
| 93c5e889 wheel feel (welded) | 0.09 | +11 / -8 | 203 | 6.3 / 5.28 | 0.48 / 0.32 | 2.44 | 0.98 |
| f841eb34 hinge +-5, 1e7 | 1.42 | +73 / -74 | 164 | 7.1 / 4.31 | 0.43 / 0.22 | 1.47 | 0.44 |
| 3cb0efda hinge +-8, 3e6 | 2.15 | +114 / -112 | 154 | 6.9 / 3.55 | 0.39 / 0.26 | 1.56 | 0.55 |
| 3cb0efda + frame damping 0.05 / 0 (retail) | 2.28 | +118 / -115 | 151 | 6.5 / 3.55 | 0.34 / 0.22 | 1.65 | 0.22 |

- On the sprung hinge the frame pivots over the step: the sprocket rises and the idler drops by the same amount.
  Less of the step reaches the hull: pitch peak and residual pitch swing drop, roll jitter drops, and it settles
  faster. The roll peak (6.5-7 deg) is the geometry of one track 0.3 m up on a 2.77 m gauge; the hinge pitches, it
  does not roll. The softer 3e6 hinge conforms about 50 % more than 1e7. Retail frame damping is the steadiest
  build on the step.
- Every build yawed about 15 deg toward the slab while climbing (drift 2.1 m): a single-track climb steers the crane.

**Flat pad:**

| Build | Normal pivot (steer 0.8): roll peak / jitter RMS + - (deg) | Normal pivot yaw in 4 s (deg) | Harsh lock+ (steer 1): roll peak / jitter / yaw | Frame swing (deg) | Settle after pivots (s) |
|---|---|---|---|---|---|
| 5c4dd65d | 2.2 / 0.18 0.16 | 45 / 46 (nearly in place) | 2.3 / 0.18 / 63 | 0.04 | 0.4 / 1.2 |
| cf9dca20 | 5.5 / 0.28 0.19 | 19 / 14 (sweeps 7-9 m) | 2.3 / 0.16 / 75 | 0.04 | 1.6 / 1.2 |
| 93c5e889 | 4.0 / 0.19 0.14 | 14 / 9 | 2.3 / 0.18 / 54 | 0.03 | 0.7 / 1.3 |
| f841eb34 | 3.1 / 0.11 0.16 | 11 / 21 | 2.3 / 0.17 / 66 | 0.5-0.6 | 1.4 / 1.6 |
| 3cb0efda | 3.2 / 0.13 0.21 | 13 / 18 | 3.5 / 0.13 / 56 | 0.6-0.85 | 1.7 / 2.7 |
| 3cb0efda + retail frame damping | 3.2 / 0.11 0.11 | 14 / 17 | 3.2 / 0.17 / 56 | 0.6-0.8 | 1.4 / 1.5 |

- Straight driving is calm in every build (residual 0.02-0.05 deg RMS). No full-lock stick-slip judder showed in any
  build at the bench's about 9 Hz sampling (lock jitter 0.06-0.18 deg RMS).
- **The inner-track curve at -0.6 (cf9dca20) cost the part-steer pivot:** at steer 0.8 the crane sweeps forward
  instead of turning in place. At full lock it turns more. Every later build keeps the curve.
- **Retail frame body damping (0.05 / 0) is the best measured build** on the step and in pivots. The 1.5 / 0.03 body
  damping does not steady the hull. Recommended for the next build, with the owner's drive as the acceptance.
- Harsh course: four builds left the pad from the x = -22 lane (two fell). Only their earlier phases are used, and the
  baseline has no lock- figure.

## Springs on a light body

Fix 1's frame-hung springs behaved as a weak, nearly constant-force cushion: about 49 kN/m per
wheel, 25-40 times softer than `axle_report` predicts at beta 58-105 from the vehicle's mass
(Game, bench). **Inferred:** a wheel's `strength` scales with the mass of the body it hangs on (the
2.5 t frame: beta about 40), not the whole vehicle's. Retail wheeled vehicles hang their wheels on
the main body, so their survey cannot show it ([retail-data.md](retail-data.md)). Do not size
springs for wheels on track frames or bogies from the vehicle mass; measure them on the bench.

> **Superseded 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4 and Follow-up F3):
> - The "about 49 kN/m per wheel, 25-40 times softer" figure is withdrawn as evidence. It was read
>   from KGS fix 1 bench run `v1_155728`, which was frozen: every wheel and bone value is identical
>   across all 478 samples while the frame counter advanced, so it is a rigid pose against the pad,
>   not a settled spring, and no spring law can be fitted to it.
> - The inference that `strength` scales with the mass of the body a wheel hangs on is refuted from
>   code: `strength`/`damping` go straight into the Havok wheel constraint's soft tau/damping, and no
>   Saber code scales them by any mass.
> - The physics_semantics.md T4 closed-form sag law is withdrawn as well (F3): the static sag law is
>   **Unknown**. Calibrate per vehicle; the Roamer 105 beta of about 106 is the only valid measurement.
> - Still standing: the owner's "bounces or wobbles" drive of fix 1 (Game; its cause is not
>   established) and the fix 2 recipe below (Game, one vehicle). Measuring springs on a working,
>   non-frozen bench rather than sizing them from a formula remains the advice.

## Recipe for a heavy crawler on track-frame bodies

Game, one vehicle (KGS-25 fix 2); every step was needed, none alone was enough:

1. Make each track's end road wheels real (`wheelIds`) on a rigid axle at ground level
   (min = max = 0, height 0, strength 1, damping 0.85).
2. Keep the other road wheels as fakes on the EPEC values: min 0, max 0.4, height 0,
   strength 0.001, damping 0.3, modelled level with the end wheels.
3. Keep the idler and sprocket real and rigid, raised as modelled.
4. Give the track frames retail-like mass (7.5 t each on a 41 t crane) and take it from the hull,
   keeping the total; lower the hull's centre of mass (`[0, -1, 0]`).
5. Hang each frame on a sprung hinge, never a weld: the HT500 hinge above (`childRotation [0,90,0]`,
   -5..5 deg, spring motor 1e7 / 1.1e7). Fix 2 raised the frame mass but kept the weld; that was
   wrong (corrected 2026-10-13 after the owner's HT500 observation; Retail + Game).
6. Match the retail contact feel: copy the donor's wheel friction tables (`frictionMaterialsList`,
   with `default`, `asphalt` and `mud_sand`) and `softForceScale` (TC305 0.75; KGS's default 1.0 made
   all 22 wheel contacts rigid), and keep wheel bodies near the donor's wheel-to-body mass ratio
   (read_fields.md "Tracked contributors"; code analysis, static).
7. Run `roadcraft lint-bro` with the class, model and markup (below), then measure on the bench
   before installing: roll in pivot turns, hull height, frame twist and the yaw achieved.

## A small crawler on the hull: WALL-E (2026-10-04)

A 1 m tracked robot, every wheel on `BoneChassis_cdt` on one rigid axle (min = max = 0, strength 1, damping
0.85). r1 (hidden physics wheels everywhere, 122 kg) "bounces around and rolls over without doing anything"
(owner, Game). On the editor bench (Game, flat pad; runs in the WALL-E project's `bench_runs/`):

| Layout or setting | Measured |
|---|---|
| Centre of mass at the collision centroid (0.545 m up, 0.32 m footprint) | tipped onto his face at spawn; 0.30 m still crept over; 0.15 m (track level) held. Set with `boneCenterOfMassOffset` (frames.md) |
| Hidden real wheels 1 cm inside the visible front / big wheels (near-coincident circles, 8 mm and 1 mm proud) | the belt, drawn round physics and visual circles together, shook (owner watching the bench) |
| A third rigid ground wheel between the ends, real or fake | wheels jittered 0.5-1 rad/s at rest and the hull crept; three rigid wheels in a line cannot all touch uneven ground |
| Only the two end wheels real, nothing between | stood still to 0.0 rad/s |
| Karelian gear table x 4.9 (to keep its speeds) | no wheel turned at any torque (truck-settings.md) |
| 122 kg on 1.5 kg wheels | wheels spun to 110-190 rad/s, dug in, rolled 84 deg; 1200 kg on 45 kg wheels: under 3.3 deg |
| r5: the visible front and big wheels ARE the real wheels (KGS-25 idler class with `geom`), nose and top rollers visual, no hidden wheels | rests and drives with the belt clear of near-coincident circles |
| r5 driving only the big wheel (a sprocket) | its wheels spun, he barely moved and did not pivot; all four driven: 3.2 m forward, pivots 51 / 67 deg |
| r5 with soft contact (`isSoftContactEnabled`, the default) | the small front wheel sank about 5 cm more than the big one: rested 9 deg nose-down; 4x `softForceScale` launched him; soft contact off: level |
| Hard contact with `sidewaysFrictionMaxVelocity` 1 (default) | ploughed ahead in pivots (10-28 deg); 0.1 m/s: 51-67 deg; 0.02: lopsided (70 / 5 deg) |

Model rule for a real wheel that carries its own model: unit radius, real proportions (X = width / radius,
KGS-25 idler 1.513 units for 0.454 / 0.3), scaled by the class radius (`geomRadius` 1). A visual-only wheel's
model is unit width instead (the visual wheel's X is scaled by `width`). Rolling radius of the small hidden
wheels was radius + section (body speed / wheel spin 0.092-0.098 for 0.074 + 0.022).

Climbing: r5 has no hidden obstacle wheels; a step meets the front wheel (radius + section 0.098 m) and the
belt between the wheels has no collision. **Open:** the owner's drive of r5, steps, slopes and mud.

## Dozer blades: what resists a cut (2026-10-14)

Source: `C:\RC_RE\research\physics_semantics.md`, "Dozer cutting resistance" (code analysis, static; the Goliath D11 RC6 against the Greenway HT500).

**How the engine resists a blade cut.**
- **Code:** `prop_terraforming_bucket` rewrites the blade's terrain contacts in diggable ground to point straight up, with `allowedPenetrationDistance` of slack. A cut face therefore never pushes back physically.
- **Code:** each physics step, a scripted impulse is applied to the **chassis**. With the retail `TerraformingSystem` values it is `min(speed, 1 m/s) × (2500 × buried blade-hull volume + 2000 × volume cut that step) × (1 + downward tilt)`.
- **Code:** an upward impulse, (buried fraction of the hull) × vehicle weight, goes to the **blade body**.
- **Code:** the drag is not scaled by truck mass.
- **Inferred:** a dozer stops when that drag beats track traction, or when the lift unloads the tracks. It is not a torque or engine-stall problem: rpm is cosmetic, and there is no stall logic.
- **Retail (global, not per truck):** dig depth is capped at `defaultDepth` 1.5 m below the original terrain. Static and non-terraformable ground keeps hard contacts, so the blade becomes a wall.

**Modding rules (Inferred until benched):**
- Do not raise engine torque past the traction limit. At 1.3e6 the 111 t D11 already exceeds it; 3e6 only spins the tracks and enlarges the engagement kick.
- Put the 1↔2 range boundary at the 1st/2nd torque crossover. With angularVelocity 1 / 2.5 this is about 3.5 km/h at a 0.43 m rolling radius. Then a loaded downshift costs no torque. With the HT500's 6 km/h boundary, 1st gives 35 % less torque than 2nd at the shift.
- Low range is not stronger than 1st (both have gear factor 1). It only stops auto-shifting.
- Per-pass depth is set by the lift joint's down stop and arm length. The HT500 stops at `Dump` +3° on a 4.2 m arm; the D11 at +5° on a 4.9 m arm, roughly twice the buried hull volume.
- Drag grows with blade-hull thickness (front to back). Lift grows with the buried fraction of the hull's height.
- Players: MANUAL mode, low range, 1-2 km/h, layers of 0.2-0.3 m, no steering in the cut.

## Checks

`roadcraft lint-bro TRUCK.bro --class auto_X.cls --tpl X.tpl` (the markup beside the model is
read by default) runs `roadcraft.tracks`:

| Code | Severity | Finds | Retail |
|---|---|---|---|
| RC046 | warning | a track whose ground wheels are all stop fakes, no real wheel at ground level (needs the model) | none |
| RC047 | warning | a wheel-carrying body (track frame) welded to its parent by a fixed constraint at any mass share, or on a hinge/slide with no motor; the message names a frame under 10 % of the body mass and gives the HT500 hinge as the fix (widened 2026-10-13: fix 2's heavy but welded frames passed the old 10 % rule) | none |
| RC048 | info | sprung wheels on a jointed body under 10 % of the total body mass: expect springs softer than the vehicle-mass formula (rationale superseded 2026-10-13, see below; the flag stays) | Aramatsu Forester Neo crane and forwarder |

**RC048's rationale is now unsupported** (2026-10-13): it rested on the mass-scaling inference and
the frozen-run figure superseded in "Springs on a light body" above (`C:\RC_RE\research\physics_semantics.md`, T4 and F3;
code analysis, static). The check is kept with the same code and severity as an informational flag
for sprung wheels on a light jointed body, whose rest should be measured on the bench; it no longer
claims that such springs come out softer.

Stop fakes beside a rigid real ground wheel are reported as by design (RC005 info), and rigid
axles are exempt from RC004's travel check.

## Changing an installed package quickly

`roadcraft.pak_patch.patch_text_members` rewrites text members of a built package (truck class,
wheel classes, model markup; every copy of a member that occurs twice) and copies every other
member byte for byte. Fix 2 was built this way from candidate 03. The editor sources must then be
changed the same way: a project generator that still writes the old values reverts the fix at its
next build ([build-pipeline.md](build-pipeline.md)).

## Open

- The full-lock judder (both layouts). Settle it by benching a retail crawler (EPEC TC305) with
  the same harsh schedule: if it judders too, it is the engine's.
- ~~Whether `strength` really scales with the parent body's mass~~ Answered from code: no mass
  scaling (physics_semantics.md T4/F3, code analysis, static). Still open: the static sag law,
  which needs a non-frozen bench with known per-wheel load and a damping sweep. The original plan:
  bench one frame-hung axle at two
  frame masses.
- Deformable terrain: spawning the crane on the acceptance scene's terrain crashed the editor
  engine for every variant, so terrain behaviour rests on the owner's drives.
- The owner's drive of fix 2.
- KGS-25 headless bench: repeat runs for run-to-run noise; the harsh course on a centred lane for the baseline,
  cf9dca20, f841eb34 and retail damping (they left the pad); a wider step slab.
