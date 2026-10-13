# Case studies

Each mod built so far, what its drives showed and what that taught. Newest first. "Not driven"
means no report from the game yet: its rules are graded Build or Inferred, not Game. The owner
installs or approves each candidate, drives it in the retail game and reports what they see.

## Apocalypse Buggy (2026-09-29)

Source: one FBX mesh skinned to a Unity-style vehicle rig (upper/lower wishbones, hubs, coil-overs,
driveshafts, steering rods), centimetres tagged as inches, facing +X; textures without metal or
roughness maps. Tandem two-seater with a central steering wheel.

| Build | Report | Cause | Lesson |
|---|---|---|---|
| 1 `apb-first` | "The suspension is collapsed" (nose low in the screenshot) | `height` 0 read as the rest position (min -0.15, strength 0.014 / 0.016) | height is the spring's neutral offset; `roadcraft suspension` |
| 1 | "Brake calipers on the outside of one set of wheels"; "the suspension doesn't animate correctly" | left wheels showed the wheel model's inner face (identity slots show the model unchanged on both sides); right knuckles and arm ends hung under the slots were thrown outside the wheels; nothing drove the slots | per-side wheel models; see build 2 |
| 2 `apb-rig-soft` | "The suspension isn't rigged at all. It doesn't move with the wheels" | follower chains pinned to wheel slots that never move without the axle controller | wheel slot joints move only under `axleControllerSettings` |
| 2 | "Feels like there is a collision mesh underneath it" | soft springs ("super soft and flexxy", asked after build 1) bottomed the low belly; hull floors at the lowest parts | lift the rest, limit bump, floor the hulls |
| 3 `apb-axles` | not driven | the retail ZiKZ pattern: axle controller and steering rack, chains pinned to the slots, stance +6 cm, hull floor 0.26 m; designed at beta 58, so at the measured 105 it rests about 13 cm high | |

Also learned: lamps by the CAT method work (headlights lit in build 1's screenshot); `dataDashboard`
drives the steering wheel and gauges (direction not yet seen); the skinned source must be evaluated in
its rest pose.

## M12 Warthog (2026-09-29)

Sketchfab FBX, metric, already facing -Y; built from the SDK Lynx sample's settings; turret on an
endless hinge worked by the right mouse button.

| Build | Report | Cause | Lesson |
|---|---|---|---|
| 1 `wh12-first` | "The wheels turn almost instantly, wheels are always on the ground, even if body is 2m in air" | steering / pedal speeds unset (default 1); suspension collection dropped (no `useSuspensionCollection`) | never copy the Lynx sample's truck settings |
| 2 `wh12-suspension-steer` | not driven; by the buggy's evidence it sat low, and its left wheels showed their inner face | height 0; identity slots | as the buggy |
| 3 `wh12-wheels-sag` | not driven | height = sag 0.15, per-side wheels | |
| 4 `wh12-axles` | not driven | axle controller (its arms and springs had never moved) and `useNamedChains`; designed at beta 58, so at 105 it rests about 7 cm high | |

## 994 Wheel Loader (2026-09-29)

An earlier build by another agent turned the steering, lift and bucket joints about the machine's
long axis (a donor's `childRotation` values on differently oriented bones), and its tests only read
joint angles. The rebuild with the grader's pipeline confirmed the hinge rule on engine body frames
and joint angles, and that the converter takes its mip count from the descriptor template. Not driven.
Adding the `level` joint broke loaders bought under the earlier build (the dump names it: sell and
buy again). Its wheel model uses the old "outer face -X" rule with identity slots, so its left wheels
are probably inside-out; the owner had not noticed (symmetric rims).

## CAT 16M3 motor grader (2026-09-28)

Driven after every candidate. The owner knows real graders: walkways moved onto the tandems ("the
walkway on the tandems usually moves with the tandem"); the blade lift range opened to the modelled
cylinders' whole stroke; the two lift cylinders became separate controls at the owner's request.
Hydraulic cylinders are `HINGE2 + PRISMATIC` chains. Renaming the lift joints killed the
grader in the owner's save (found in the script crash dump): sell and buy again after joint changes.

## CAT 793D haul truck (2026-09)

Lamps: the ChangeMaterial approach never rendered; show/hide of lit copies worked in the campaign
(RC20) for the engine lamps and strobes; the native brake / reverse states did not, and RC21 moves
them to show/hide (not yet confirmed). RC21 also heaps the payload.

## Roamer 105 (2026-08 to 2026-09-14)

A port of an Expeditions crawler, installed into the owner's editor (Mod Editor play mode, not
retail), with a 15-case acceptance ledger and an autonomous test runner. Most drivetrain and
suspension measurements in this library come from it.

| Report or finding | Cause | Lesson |
|---|---|---|
| Suspension bottomed, tiny travel | its own collection's +-0.018 m range; the TUZ reference runs with no collection at all | compare with a working vehicle's compiled class |
| Links stretched up to 36 mm | rigid links against real travel | telescoping links (owner's choice over reduced travel) |
| "Steering too quick", tie rod swings | steer speed default 1 | 0.03 / 0.045 (the source mod's values) |
| "Too much power and geared too high" | invented torque table; gears from a vehicle with bigger wheels | scale torque by power-to-weight and gears by wheel radius |
| Rolled back on a ramp after a stop | `neutralGearSwitchingDelay` 3 | 60 |
| "When turning it feels like the wheels physically aren't where they are visually" | the rack has no Ackermann (outer knuckle 30 degrees, wheel 24) and it understeered 8-10 % | accepted as an engine limit |
| "Too dark", then "made of plastic" | 8 % luminance paint; roughness 0 spec | x1.6 paint, spec targets (textures-and-materials.md) |
| Every session crashed at scene load | shader permutation not shipped (LOD crossfade + vertex compression) | no crossfade |
| Suspension sweep | height moves the ride height 1:1; sag ~ 1 / strength | beta about 105 (suspension-and-wheels.md) |

The owner rejected a full acceptance suite after every change as too slow: the loop became quick
build -> the owner drives -> report, with sign-off evidence gathered only at milestones.

## CAT D11T dozer, Hitachi EX5600

The D11T is where the toolchain's identities, captures and source parity began, and where the
`hkCenterOfMassOffset` rule was read from the engine. The EX5600 (never driven) first wrote down the
hinge-axis rule, the generic `Truck` joint controls, and the exporter's LOD and UV traps.

## Apoc buggy partial suspension motion and rear scraping, 2026-09-30

Baseline `apb-axles-20260929` (package `7ef2f935717c0b7d...`) was the installed candidate.
Owner report: “some of them move with the wheel but dont appear attached correctly. others
dont move at all”, plus apparent rear ground scraping without visible contact.

The controller-only fix did not resolve the reported problem. Offline geometry found up to
157 mm of unreachable upper-arm travel, lower-arm/upright attachment mismatch, link meshes
weighted only to hinge bones, insufficient tie-rod extension at droop plus lock, and a rear
convex hull bridging open space. These findings supersede the earlier unverified diagnosis
that increased ride height and the controller alone would resolve the symptoms.

Repair candidate `apb-link-clearance-20260930`: independent arm endpoint chains with two-bone
skinning; corrected damper attachment/pivots and spring overlap; explicit per-wheel controller
indices; tie-rod extension; 20 rear collider pieces replacing one broad hull. Physics tuning
and controllable joint names are retained. The existing generated classes were updated only
in IK and axle-controller properties without launching an editor.

Evidence: authoring geometry, exported collider/skin checks, analytical motion sweep, schema
and package checks (**Build**). The analytical steering sweep assumes a centred rack. Native
solver response, actual scraping, handling and campaign acceptance remain **Open** until a
drive of this candidate.

## Apoc buggy softer suspension and compact collision, 2026-09-30

After `apb-link-clearance-20260930`, the owner said the buggy feels stiff, requested softer
suspension, smaller body CDT to avoid bellying out, and more flex (**Game** report).
That report does not establish whether every previous linkage symptom was resolved.

Candidate `apb-soft-flex-20260930` reduces spring strengths by about 43% and damping by
39%, increases wheel travel from 0.36 to 0.58 m, enlarges linkage slider ranges and coil
overlap, and replaces 22 body collision pieces with four narrower, shorter, raised core
hulls. Chassis angular damping changes from 1.5 to 0.35; mass and COM target are preserved.
The existing main and preview native classes receive the same suspension collection.
The source and previous package are retained for rollback.

Analytical sweep, exported skin/collision audit, schema, native class and package checks
are **Build** evidence. Beta-based rest estimates are **Inferred**. No new retail drive
or measured rest height has been recorded; handling and campaign acceptance remain **Open**.

## Apoc phantom mud patch after the soft-flex repair, 2026-09-30

The owner drove `apb-soft-flex-20260930` and reported mud deformation from nothing visible,
clarifying that it was a wide patch underneath the back of the buggy (**Game**). This does
not establish acceptance of suspension feel or all earlier linkage fixes.

Diagnosis found two copied body VFX boxes, `BoxCapsule` and `BoxCapsule3`, enabling mud with
systems=26. With the buggy's identity native chassis transform, their lower bounds were
Y=-2.354 and -2.0925 m; the second was entirely below the modelled ground. Previous collision
audits did not cover this independent effect geometry (**Build**, SDK flag definition).

Candidate `apb-mud-proxy-20260930` replaces donor body environment boxes with four inset core
boxes. All wheel classes, physical collision, suspension and linkage settings are preserved.
Only the main truck class's VFX property may differ in the final archive; the model assets
are pinned and reused. Compiled-volume audit, schema and package checks remain **Build**;
elimination of the observed rear patch awaits the next retail drive (**Open**).

## Apoc rapid wheel chatter after the mud-volume fix, 2026-09-30

Owner report on `apb-mud-proxy-20260930`: the wheels bounce rapidly over some terrain and
the vehicle feels like a shopping trolley; mostly the wheels chatter and the body remains
fairly level (**Game**). This report does not explicitly confirm the previous mud fix.

Candidate `apb-damping-20260930` is a bounded damping trial: front 0.16 and rear 0.18,
both previously 0.085. Comparable retail scouts use 0.15-0.20. Spring strength, ride height,
58 cm travel, wheel definitions, physical model and corrected terrain-effect volumes are
preserved. Only damping in the main/preview suspension arrays may change in the archive.
Underdamped wheel hop is a working diagnosis, not a measured runtime result (**Inferred**).
Compiled/schema/package checks are **Build**; settling over the reported terrain still
requires the owner's drive (**Open**).

## Apoc continuous spring animation, 2026-09-30

While `apb-damping-20260930` was installed, the owner reported that the springs look like
two sliding meshes and requested actual spring animation (**Game**). This does not confirm
whether the earlier wheel-chatter or rear mud-deformation fixes are accepted.

`apb-coil-animation-20260930` replaces overlapping coil halves with connected, round-wire
helices on all four corners, with continuous two-end skinning and three matching LODs.
One close-wound turn at each seat stays attached while six active turns change pitch.
The mixed-weight piston parts are separately classified and follow the moving barrel mouth.
The existing IK bones drive the deformation; no controllable joints are renamed or added.
Package comparison permits only the four compiled body-model resources to change from
the damping candidate. Classes, suspension settings, wheel models, physical markup and
terrain-effect settings remain byte-identical (**Build**). Offline rendered poses, actual
mesh deformation checks and export validation support authorship, not retail acceptance.
The owner's next drive must confirm native animation (**Open**).
