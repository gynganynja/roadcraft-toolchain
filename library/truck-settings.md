# Truck settings (BRO)

The truck BRO (`bro/trucks/<mod>.bro`) is compiled by the SDK's generator into native classes
(`autogen_dw/trucks/auto_<mod>/auto_<mod>.cls` and friends). The generator accepts unknown or
incomplete settings silently: check the compiled class, not only the BRO (`lint-bro --class`). The
SDK's type descriptions also lag the engine: the generator passes through nested fields they do not
list (`rigidBodyNames`, `isNewController`, ...), so judge a field by the schema *or* by shipped use
(Build, 16M3 grader).

## Driving feel

| Setting | SDK default | Retail scouts | Grade |
|---|---|---|---|
| `truckSettings.maxSteerSpeed` | 1 (instant) | 0.027-0.032 | SDK, Retail, Game (Warthog) |
| `truckSettings.backSteerSpeed` | 1 (instant) | 0.054-0.072 | SDK, Retail |
| `truckSettings.pedalsResponsiveness` | 1 | 0.35 (Don 71: 0.51) | SDK, Retail |
| `truckSettings.enableLateralForce` | | True | Retail |
| `slopeAngleFrictionMult`, `wheelsSubstanceResistanceMult` | | splines, e.g. `[0,1, 30,1, 65,0.9, 75,0.35]` and `[0,0.55, 0.5,0.65, 1,0.7]` | Retail |
| `softContactSettings` | | `{ maxPenetrationDepth = 3, forceScale = 0.015 }` | Retail |

## The SDK's TUZ 119 Lynx sample BRO is incomplete

It has a `suspensionCollection` without `useSuspensionCollection` (so its suspension is dropped) and
no steering or pedal speeds (so they are instant). Copy its engine sound graph, winch and effects,
not its truck settings. (Build, Game: the Warthog was built from it.) Its engine sound graph tracks
a locator named `ctrl_switch_handbrake`: add one to the model.

## Engine and gearbox

| Rule | Grade |
|---|---|
| Gears: `angularVelocity`, `gearRatio`, `targetSpeedRangeKmh`; the displayed speed range does not follow simply from angularVelocity x wheel radius (Lynx: 12 rad/s on 0.78 m for 37-60 km/h) | Retail; units Open |
| A gear's top road speed grows with the wheel radius: the TUZ gear table on the Roamer 105's 0.458 m wheels (the TUZ's are 0.78 m) held it in first at 16 km/h, below its 18 km/h upshift; scaling every gear's `angularVelocity` by 0.78 / 0.458 fixed it | Game (Roamer 105, editor play mode) |
| Low range: `lowRangeGear.angularVelocity` sets the crawl speed, and the pedal changes it little (Roamer 105: 0.25 -> 8.4 km/h, 0.05 -> 4.1, 0.025 -> 2.1); neither first gear's value nor `gearRatio` changed it | Game (Roamer 105, editor play mode) |
| `neutralGearSwitchingDelay`: after this many seconds at a standstill the gearbox drops to neutral, and on a slope the vehicle rolls back when the brake is released (Roamer 105 at 3: 2.6 m back down a 30 degree ramp); 60 kept it in gear | Game (Roamer 105, editor play mode) |
| Retail scouts: 5 gears, torque 65-85 kN m for 2-3 t (Armiger 65 k for 1.97 t) | Retail |
| Scale torque from a retail vehicle by power-to-weight and wheel radius, never from an invented table: 215000 on the 2.9 t Roamer was "too much power" to its owner | Game (Roamer 105) |
| Heavy machines built here: torque scaled from a similar retail machine, top speed from the real machine | Build |

## Wheels and drive

| Rule | Grade |
|---|---|
| `torqueType` is one of `none`, `defaults`, `connectable`, `full`; `default` is not a value (a Roamer candidate with it drove on its front wheels only) | SDK (enum), Game (Roamer 105, editor play mode) |
| `defaults` wheels are always driven, `full` wheels only while all-wheel drive is engaged: all `full` with it off does not move | Game (Roamer 105, editor play mode) |
| Retail 4x4 scouts: front `full`, rear `defaults`, `gearboxSettings.awdControlType = CONTROLLED` so the driver engages the front axle | Retail |
| Rear counter-steer: a negative `steeringAngle` on rear slots (Derry Longhorn -15, EPEC -20) | Retail |
| `isRightSided` on right-hand slots | Retail |
| `handbrakeStrength` 0.006-0.01 on scouts | Retail |

## Controls

| Rule | Grade |
|---|---|
| A joint the player turns: `constraintControllerSettings.controllableConstraints` + `axisControls` with `SIMPLE_CONTROLLABLE_CONSTRAINT` (e.g. the Bowhead's tower on the right mouse button, endless with limits +-3600) | Retail |
| Grader-style tools: `GRADER_BLADES_POSITION` / `GRADER_BLADES_ANGLE` axis controls, `constraintChains` for the lift, mode actions `GRADER_SWITCH_MODE_PREV/NEXT` | Retail (dozers), Game (16M3 grader, 994 loader controls as asked) |
| An axis control drives one constraint; there is no chain axis type in `AxisControlTypes`, so two joints that must move together need two controls (or one on the native grader chain) | SDK (enum), Build (16M3 grader) |
| Adding or renaming a controllable joint breaks vehicles already in a save (the stored state lacks the joint): keep names stable, or sell and buy again. The script crash dump names the joint (symptoms.md) | Game (994 loader, 16M3 grader) |

## Store and interface

| Rule | Grade |
|---|---|
| `chassisInfo.uiCustomShopIcon` (368 x 308) and `uiInfo.uiCustomIcon` (960 x 640) name UI textures compiled as one-level BC7 with alpha; link them into the catalog descriptor so they are packaged | Build, Game (icons shown) |
| `uiType` places the vehicle in a store section (`UID_TRUCKS_TYPE_SCOUT`, `UID_TRUCKS_TYPE_ROADWORKS`, ...) | Retail, Game |
| The retail game finds mod trucks by flattened `ssl/<brand>_<suffix>` brands (the Mod Manager's export naming), while the editor package keeps them under `autogen_dw/`: every build re-exports the package (build-pipeline.md) | Build, Game (the mods appear in the store) |
| Truck mods need the five `auto_*` `.sso.resource` assets in the Mod Manager and the Vehicle category on PROS, or co-op breaks | SDK (official documentation) |

## Payload

| Rule | Grade |
|---|---|
| A dump body's load is a hidden mesh volume: its shape is the heap (CAT 793D: a heaped pile, crown 1.5 m, 138 m3), with `pourMultiplier` and `sfxMovableDumpPositionBone` naming it | Build (CAT 793D RC21) |

## Body terrain effects are separate from collision (Apoc, 2026-09-30)

`propVFX.vfxSkeleton.vfxBones` compiles to the truck class's `vfx` property. The installed SDK
`vfx_skel_bone.systems` flags specify shadow=1, water=2, slime=4, grass=8, mud=16. In particular,
26 enables water, grass and mud (**SDK**); changing CDT does not rewrite these authored boxes.

The Apoc copied the donor's environment volumes into a different rig without fitting their
positions. Its compiled chassis is identity in native X-left/Y-up/Z-forward coordinates;
the two mud boxes reached Y=-2.354 and -2.0925 m and extended behind the buggy (**Build**).
The owner saw a wide patch of unexplained rear mud deformation after the CDT repair (**Game**).
The observed symptom is consistent with these volumes, independent of spring bottoming.

Candidate `apb-mud-proxy-20260930` replaces the donor environment boxes with four native-axis
boxes inset within the measured compact collision bounds. Audit active mud shapes' bone
transforms, extents and compression/pitch clearance in the packaged class. Keep tyre effects
and wheel definitions intact, and compare archive members occurrence by occurrence. Passing
these checks is **Build** evidence; the next retail mud drive is still required (**Open**).
