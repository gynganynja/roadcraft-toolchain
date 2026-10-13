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

The survey's ground classification uses authored mount geometry, not native
loaded wheel positions. In particular, sprung real wheels may extend to the
ground: Bowhead includes two sprung real trail wheels per side and ATM53
includes sprung real middle wheels. A row labelled "sprung fakes only" therefore
does not prove its real wheels stay airborne during native driving. Confirm the
loaded contact/travel data before copying such a support arrangement (SDK class
inspection, WALL-E investigation2026-10-05).

**No shipped track rests on stop fakes alone in this authored-layout survey.** Near-zero fakes (min 0, strength about 0.001)
appear only beside rigid real wheels at ground level, e.g. EPEC TC305: fakes min 0 / max 0.4 /
height 0 / strength 0.001 / damping 0.3 (Retail). Nor does any shipped vehicle weld a
wheel-carrying body to the hull with a fixed constraint: track frames and bogies hang on hinges or
slides (Retail, RC047). Retail track frames are heavy: Greenway HT500's weigh 7.5 t each, 12.5 % of
its body mass.

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

The owner drove fix 1 in the game: "it does it worse now", "bounces or wobbles" (Game). Fix 2 is
installed; the owner's drive is pending.

## Springs on a light body

Fix 1's frame-hung springs behaved as a weak, nearly constant-force cushion: about 49 kN/m per
wheel, 25-40 times softer than `axle_report` predicts at beta 58-105 from the vehicle's mass
(Game, bench). **Inferred:** a wheel's `strength` scales with the mass of the body it hangs on (the
2.5 t frame: beta about 40), not the whole vehicle's. Retail wheeled vehicles hang their wheels on
the main body, so their survey cannot show it ([retail-data.md](retail-data.md)). Do not size
springs for wheels on track frames or bogies from the vehicle mass; measure them on the bench.

## Recipe for a heavy crawler on track-frame bodies

Game, one vehicle (KGS-25 fix 2); every step was needed, none alone was enough:

1. Make each track's end road wheels real (`wheelIds`) on a rigid axle at ground level
   (min = max = 0, height 0, strength 1, damping 0.85).
2. Keep the other road wheels as fakes on the EPEC values: min 0, max 0.4, height 0,
   strength 0.001, damping 0.3, modelled level with the end wheels.
3. Keep the idler and sprocket real and rigid, raised as modelled.
4. Give the track frames retail-like mass (7.5 t each on a 41 t crane) and take it from the hull,
   keeping the total; lower the hull's centre of mass (`[0, -1, 0]`).
5. Run `roadcraft lint-bro` with the class, model and markup (below), then measure on the bench
   before installing: roll in pivot turns, hull height, frame twist and the yaw achieved.

## A small crawler on the hull: WALL-E (2026-10-04)

A 1 m tracked robot, every wheel on `BoneChassis_cdt` on one rigid axle (min = max = 0, strength 1, damping
0.85). r1 (hidden physics wheels everywhere, 122 kg) "bounces around and rolls over without doing anything"
(owner, Game). On the editor bench (Game; originally called a flat pad, later measured as terrain contact; runs in the WALL-E project's `bench_runs/`):

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

## Checks

`roadcraft lint-bro TRUCK.bro --class auto_X.cls --tpl X.tpl` (the markup beside the model is
read by default) runs `roadcraft.tracks`:

| Code | Severity | Finds | Retail |
|---|---|---|---|
| RC046 | warning | a track whose ground wheels are all stop fakes, no real wheel at ground level (needs the model) | none |
| RC047 | warning | a wheel-carrying body welded to its parent by a fixed constraint and under 10 % of the total body mass (KGS-25 frames: 6 %) | none |
| RC048 | info | sprung wheels on a jointed body under 10 % of the total body mass: expect springs softer than the vehicle-mass formula | Aramatsu Forester Neo crane and forwarder |

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
- Whether `strength` really scales with the parent body's mass: bench one frame-hung axle at two
  frame masses.
- Deformable terrain: spawning the crane on the acceptance scene's terrain crashed the editor
  engine for every variant, so terrain behaviour rests on the owner's drives.
- The owner's drive of fix 2.

## WALL-E r2 follow-up: idle belt and straightness (2026-10-05)

**Owner report; reproduced in native editor:** physical wheels and chassis can
be stationary while the animated belt changes outline. Review fixed-camera
native image sequences separately from physical telemetry. Tension 10 held the
outline in reviewed post-drive/idle sequences, but its isolated drive still failed
straightness. It is a visual improvement, not a validated complete repair.

Measure full zero-steer paths in both directions, including launch, and repeat
the exact packaged candidate. Test turning and sustained full throttle as well.
WALL-E r3/r4 passed build checks and looked better in some short trials, but
failed repeated native drives; neither was installed. Higher damping, wheel
friction, differential locking or rear metadata are not established remedies.

Confirm the surface with native ground/terrain flags and support height. The
unchanged r2 was much straighter on a verified static platform than on template
terrain. A different surface is diagnostic evidence, not proof of a repair.
Separate startup failures from driving results and retain native readiness probes.

The full [WALL-E stability case](../docs/case-studies/walle-stability.md) preserves
measurements, failed approaches, source/build identities and corrections.
**Game (owner feedback, 2026-10-05):** installed r5 fixes the reported track
flapping; the owner calls the remaining wandering "isnt that bad" and identifies
flapping as the main issue. Preserve r5 as the working version. It combines
tension10 with crawl/contact/damping changes; the report supports the combined
build's visual outcome, not a universal tension-only causal claim. The previous
0.5497m repeat failure against the0.5m bench gate remains numerical evidence.
Package `fe6fd41188940e0a243a9cde8d8f01c22869bcbb9fcba9305ba9fa33282c4ae1`,
transaction `8ca355d7acf54874a874b86a2326cb65`; exact feedback is preserved in
the mod's `stability_20261005/owner_feedback_r5.json`. No extra automated check
is warranted for this subjective owner assessment.


## Applying the WALL-E findings to KGS-25 (2026-10-05)

**Build (current package inspection):** installed KGS-25 is the later curb-repair
package `bcb343c6bd5abe398d0c580b3c43fd3e78eee75fb9254e340223b8b430b87114`,
matching its repair build receipt and distributed package, not the older fix2
identity in the historical account above. Both tracks omit trackTensionDefault
and use trackTensionDrive0.13. Engine jerkingScale2 and maxDeltaAngVel0.001,
neutralGearSwitchingDelay60, and reverse wheel resistance enabled are confirmed
in the installed truck class. The curb repair retains fix2's support arrangement
and adds raised ramp fakes; those additions were build-checked, not validated by
this read-only comparison.

**Inferred priorities, not KGS-tested fixes:**
- If its belt flaps with stationary bodies, isolate a tension change first.
  WALL-E's default/drive10 combination held its outline in editor sequences and
  shipped in the owner-confirmed r5 fix. This makes tension a strong test lead;
  it does not establish10 as a universal or necessary crawler setting.
- For the recorded KGS full-lock judder, compare jerkingScale2 with0 while keeping
  the same support, gearing, surface and inputs. WALL-E's successful combined
  version uses0, but earlier no-pulse variants failed other handling checks.
  The source field is a testable lead, not proof that pulses cause KGS judder.
- Use fixed-camera rest/post-drive sequences alongside body and wheel telemetry
  to distinguish animated-belt flapping from support motion. Use normal State
  controls when assessing controller smoothing, and label terrain versus static
  contact; earlier KGS tests used a static pad.
- Do not transplant WALL-E's damping100, mass distribution, friction0.2, crawl
  gears or extra radius into the41t frame-supported crane. They were combined
  miniature-rig tuning, whereas KGS has independent support/curb requirements.

Evidence: WALL-E r5 package `fe6fd41188940e0a243a9cde8d8f01c22869bcbb9fcba9305ba9fa33282c4ae1`,
owner-confirmed track fix and preserved repeat failure in
[the stability case](../docs/case-studies/walle-stability.md); KGS curb-repair
`repair_2026-10-03/build/receipt.json` and direct installed-package inspection.
No KGS files/settings were changed, and no native test was run for this comparison.
No validator is added: the cross-vehicle tuning hypotheses need matched tests.
