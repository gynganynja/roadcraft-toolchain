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
