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
| Gears: `angularVelocity`, `gearRatio`, `targetSpeedRangeKmh`. A gear's top road speed fits **`angularVelocity x gearRatio x rolling radius`** (rolling radius = wheel radius, plus the section height on tracks): Lynx first gear 2.5 x 3.7 on the Roamer's 0.458 m wheels predicts 15.3 km/h, measured 16; the Karelian's gears reach 12.9 / 23.8 / 31 / 47.6 / 52 km/h, each above its upshift bound; the D11's 0.22 m + 0.129 contact gave about 5 km/h against a 6 km/h upshift ("slow"). Keep every gear's top above its upper `targetSpeedRangeKmh` bound | Retail tables + Game (Roamer, D11); rule Inferred |
| Engine fields (SDK script `ssl/trucks/truck_components.ssl`): `gearRatio` = "full engine rotations per wheel rotation"; defaults `finalDriveRatio` 3.9, `rpmIdle` 800, `rpmOnNeutralMax` 1500, `gasPedalMaxRpmBoost` 250, `rpmDropTime` 1; `useDeprecatedAutoGearSwitchLogic` false (the gearbox shifts on `targetSpeedRangeKmh`) | SDK |
| **Do not scale `angularVelocity` up to keep a donor's road speeds on smaller wheels.** WALL-E (0.097 m rolling radius) with the Karelian's table x 4.9: the engine idled at 800 + pedal x 250 rpm and no wheel turned, at torque 950 and at 19,000; the unscaled table (2 / 5 / 8 / 14) drove at the same torque, and KGS-25's (0.8 / 1.6) did too. Keep stock-range angular velocities (no stock vehicle exceeds 23) and accept the smaller wheels' lower speeds; scale `targetSpeedRangeKmh` with the gears' real tops so the automatic box still shifts | Game (WALL-E editor bench, 2026-10-04: runs t20, gk1, xgearbox, xengine) |
| A very light vehicle needs more mass than to scale: at 122 kg on 1.5 kg wheels every unloaded wheel spun to 110-190 rad/s, dug in and the robot rolled to 84 deg; at 1200 kg on 45 kg wheels (torque 10,000, `maxDeltaAngVel` 0.002) roll stayed under 3.3 deg. `maxDeltaAngVel` 0.002 instead of 0.01 evened the wheel spin and made the pivots symmetric | Game (WALL-E bench) |
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

## Dump truck loads with `roadcraft.load_volume` (start here, 2026-10-02)

The load-in-tub recipe that works, as shared code (`src/roadcraft/load_volume.py`; Blender side
`blender_load.py`) and checks (`lint-bro` RC033, RC035, RC036; the Blender-side grid emulation RC040-RC044).
The sections below keep the history and evidence of each step.

1. **Bodies and joints.** A dump body (`BoneDump_cdt`) hinged to the chassis with the controllable
   constraint `dump` (`constraintControllerSettings.controllableConstraints`, 0 to its maximum angle;
   `axisControls` DUMP_CONSTRAINT; `dumpConstraintSettings`). A tail lid body (`BoneLid_cdt`; Dump Twuck
   `BoneSandCap_cdt`) hinged to the dump body with a powered constraint whose open and closed states the
   hydraulic lid controller drives (`canBeDynamicallyOpened`, `volumeClosingConstraintName`, `hydraulicLid`;
   Bowhead lid 0 / 20 degrees, Baikal 65206 0 / 15). A fixed rear wall holds sand but blocks unloading. An
   open-backed tub (EPEC LT200) has no lid and no back border.
2. **Load volume** (`blender_load.floor_sampler`, `heap_top`, `heap_hull`). A hidden mesh under the dump body
   at the model origin, like the Bowhead's `_load_volume`. The engine convex-hulls it and draws the carried
   sand as one height sheet where it is authored: no pivot offset. Ray-sample the tub's real floor from the
   bed art (faces weighted to the dump body), lift it a few centimetres, and close it with a heaped top that
   meets the walls and thins to nothing at sloping or open ends, so the hull tapers onto the steel. Keep the
   height range under 4 m. Native capacity came out near the hull volume (+5%).
3. **Borders** (`blender_load.load_borders`). The native grid spans the four border meshes, not the volume.
   Left, right and front hang from the dump body; the back hangs from the lid, because its transform is
   composed with its parent's (under the dump body the pivot applies twice). Keep all four inside the tub
   and at least 5 cm thick (samples move 1/64 m toward the body origin), with tops at the sand height beside
   them: a cell the hull misses takes the border's height, or the pivot height with none. Hide the volume
   and borders with concrete markup flags (`load_volume.hidden_markup`).
4. **Settings** (`load_volume.load_settings`). `volumeMesh` and `dumpBodyName` name the volume;
   `bodySettings` names the dump body and the borders; `volumeMass` is the full payload mass (density =
   mass / capacity); `sandQuantity` the capacity; the refill stream follows the volume
   (`sfxMovableDumpPositionBone`, offset above the heap); the warning marker sits on the volume. Also enable
   `aiRouteFollowingSettings` (the load controller requires it) and set
   `detailsInfo.dumpTipperDetails.sandCapacity`.
5. **Checks.** In Blender, `blender_load.grid_report(volume, borders, rig, parent_body, tub=...)` on the saved
   model: RC040 cells at the pivot height (a curtain), RC041 a sheet over 4 m, RC042 a border the engine
   reads elsewhere, RC043 a ledge over 0.5 m at a border, RC044 a grid leaving the tub. `lint-bro --tpl`
   checks the names and the back border's parent (RC036), the refill stream (RC035) and route following
   (RC033). In game, check the retained load at rest and while driving separately from discharge when
   tipped (95% or more).

| Rule | Grade |
|---|---|
| One height sheet at the authored hull position, 4 m range, thin cells clipped | SDK shader; Native captures (Dump Twuck builds 019-023) |
| Grid spans the borders; back border composed with its parent; cells the hull misses take a border's height or the pivot height; 4 cells per metre, 2 to 32 per axis | Disassembly (Roadcraft ModEditor.exe); Game (Dump Twuck v3 curtain and slab) |
| Back border under the lid body | Retail (Bowhead `_load_border_rear` under `BoneLid_cdt`); Build (Dump Twuck v4/v5); owner's v4 drive pending |
| Borders at least 5 cm thick | Disassembly (1/64 m sample nudge) and emulation: the Dump Twuck v5 2 cm front slab leaves its two front-corner cells at the pivot height; Game not observed |
| Hydraulic lid opens and closes with tipping; refill stream on the volume | Native fixture (Dump Twuck v2); Retail |

Kit evidence on the Dump Twuck v5 model (read-only Blender run, 2026-10-02): `heap_hull` with the project's
values rebuilt the shipped volume exactly (143.411 m3, 173 vertices); `grid_report` flagged revision 3's
borders (295 cells at the pivot height, back border read 3.677 m rearward and 4.2 m up) and v5's 2 cm front
slab (two front-corner cells); `load_borders` at 5 cm with the same tops gave none. Dump Twuck values:
crown 8.25 m, sides 6.95 m, front and rear slopes 32 / 30 degrees, clearance 0.06 m at the front rising to
0.16 m at the tail; borders: sides and front at the hull's bounds, tops 6.95 / 6.85 m, back block y 6.10 to
7.30 m, 6.0 m bottom, top 6.62 rising to 6.86 m. Tests: `tests/test_load_volume_kit.py`.

## Payload

| Rule | Grade |
|---|---|
| A dump body's load is a hidden mesh volume: its shape is the heap (CAT 793D: a heaped pile, crown 1.5 m, 138 m3), with `pourMultiplier` and `sfxMovableDumpPositionBone` naming it | Build (CAT 793D RC21) |
| The engine draws a full load as one height sheet over the convex hull of `volumeMesh`, at its authored model position. There is no dump-pivot offset and the helper's node origin does not matter: author the hull inside the tub in model space (shipped `_load_volume` nodes sit at the model origin) | SDK shader; Native captures (Dump Twuck builds 019-023 reprojected); Retail |
| Keep the hull's height range under 4 m: sheet heights are stored relative to the grid minimum times `LOAD_VOLUME_MAX_HEIGHT = 4` | SDK shader |
| Cells thinner than about 0.1 m are clipped, but the sheet between a thick cell and an empty one is drawn. Follow the steel with the hull floor and thin the load to nothing at open or sloping edges, or a curtain hangs below a thin-shell tray | SDK shader; Native captures |
| `sfxRefillLocalPosition` is in truck space unless `sfxMovableDumpPositionBone` names a node; the Bowhead names `_load_volume` with offset y 4.5. RC035 warns | Retail; SDK script |
| `volumeMass` is the full payload mass (native `GetMaxMass`), independent of `density` x volume | Native fixture |


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

## Direction-change delays (Lada follow-up, 2026-09-30)

**SDK/Retail:** `truck_components.ssl` documents `defaultGearSwitchDelay` for non-upshift changes, plus `clutchSwitchTime`; higher forward gears use the separate upper-gear delay formula. Shipped Armiger scouts use 0.15 s default delay, 0.1 s clutch and 0.1 s downshift delay. Lada v3 used 0.75/0.5 s and the owner reported 1–2 s forward/reverse hesitation (**Game report**). V4 adopts the scout delays and lowers the upper gear angular velocities while preserving first gear. Do not confuse these timers with the standstill-to-neutral timer. Parameter arithmetic is not a measured complete direction-change time. Evidence: Lada `revisions/rut_contact_v4/retail_contact.json`, `feedback.json`, and native `truck_components.ssl`.

## Scout utility components need playable controls (Lada v7, 2026-09-30)

**Retail/SDK; Game (isolated native editor):** a winch component or scanner
component alone does not make the capability usable. Lada v6 had a winch and
front/rear sockets, but no attach/pull/detach input actions, and an objective
scanner with no radius. Author named actions alongside enabled settings.

| Capability | BRO settings | Required playable action |
|---|---|---|
| Winch | winchSettings, winchSockets | TRY_ATTACH_WINCH axis; ACTIVATE_PULL_WINCH and DEACTIVATE_WINCH |
| Objective scanner | objectiveScanner | ACTIVATE_OBJECTIVE_SCANNER |
| Terrain scanner | extrusionScanner with usable SFX descriptor | SWITCH_EXTRUSION_SCANNER |
| Exploration radar | explorerSettings | TOGGLE_EXPLORER |

Use shipped Armiger scout BRO controls and Minuteman explorer settings as
references, adapting them to the actual vehicle. The Lada's 45 m objective and
40 m terrain scanners use explicit 5 s cooldowns; its winch is 20 m/20000 native
pull strength. Front/rear source and recovery points reference the physical
chassis and native body-local coordinates. Check both compiled components and
normal control-section availability. The SDK duplicates authored winch source
points in the generated controller; inspect distinct positions, not only count.
`amountOfWinchPoints` should not exceed the authored recovery socket count
(native Init clamps it). The ship's shop preview lacks gameplay utilities:
validate gameplay CLS, and separately preserve preview handling/visual assets.

Explorer controller rotation/constraint properties are optional. A functional
map scan does not require a new dish mesh or controllable joint. Native defaults
allow a 300 m reveal; the Lada uses a 15 s stationary scan costing one recovery
token. `fuelCost` refers to recovery tokens, not vehicle fuel. The native radar
unit is `TruckExplorerUnit` in the replicated descriptor. Velocity calculation
is inherited from `truck_view_base`, so absence in a leaf CLS is not a failure.

**Native results:** Lada pulses/terrain markers captured; both winch pulls attach
to the respective socket and move the truck; a freshly spawned radar consumes
one token and clears fog sampled 200 m away. Actions were checked in compiled
HUD mappings and exercised through native state, not physical button presses.
Radar campaign persistence and multiplayer remain untested. Optional towing
assist uses a target's PropTowing; ordinary winch pulling works without it.

Integration: opt-in `roadcraft.native_utilities.utility_action_report` checks
requested gameplay components AND control bindings, enabled UI sections, winch
targeting/source points, nonzero objective radius and terrain effect binding.
Seven focused tests cover missing components/controls, zero default radius,
disabled section, explicit scope and unknown utility names. Lada
`tools/audit_utilities.py` calls it during package validation; configure_workflow
pins the helper. No universal scout feature requirement is added to other mods.
Evidence: Lada build-008, test-011 and v7 utilities_result.json; shipped
Armiger/Minuteman BRO and native explorer/winch/scanner sources captured under
revisions/utilities_v7/native. Source references are primary installed SDK data.

## Gullwing toolbox controls and native utility confirmation (L275 v1)

**Build/Game, 2026-09-30:** two identity-frame child bodies with physical hinge
axes native Z (minus Blender Y), opposite limits 0..105 and -105..0, 32 deg/s
controllable joint speed and position motors opened the L275's paired doors.
Actual constraint angles reached +104.7045/-104.7123 degrees and closed within
0.02 degrees of zero. Door labels and hardware share the child's skin. Keep
stable constraint names and bind separate axis controls: left mouse horizontal
and vertical for the doors, right mouse for winch targeting. Native state was
exercised; manual mouse/controller input was not certified.

The same v1 fixture confirmed both actual AWD/diff-lock states on/off, low-range
turns, reverse, front/rear source-socket winch pulls, objective/terrain scan
activation/reset, and a fresh radar's one-token consumption with fog clearing
at a 200 m sample. Scene-placed explorer controllers again cached an empty
level before initialization; a fresh truck acquired l275_drive, matching the
existing Lada finding. Do not diagnose that fixture ordering as a retail bug.
Evidence: runtime/native_v1/review.json (28 checks), doors_opened/closed,
drive02, front/rear_attached/pulling and radar_*; package hash begins 1f78529e.
The opt-in shared native_utilities checker is already wired into L275
validate.py. V2 changes geometry/physics and requires separate runtime evidence;
the v1 result cannot be transferred to it or counted as campaign acceptance.

## Controlled selector versus forced physical differential (Roamer, 2026-10-01)

**SDK/Game, isolated native editor:** CONTROLLED in the gearbox controller does
not override an inherited physical `prop_truck_rb.diffLockType=ALWAYS`.
The installed SDK's PropTruckViewController.SetState forces the physical input
for non-DEFAULT modes: ALWAYS is true and NONE is false. Use DEFAULT when the
vehicle is intended to expose a working controlled selector, retaining the
actual controller's bindings. Forced/permanent modes remain valid for vehicles
designed for them; this is not a universal DEFAULT requirement.

Roamer v1 reported physical true even with its selector off. Changing only this
leaf in 22 gameplay/preview classes produced final package `8a340adc...`. Native
final_diff04 then measured both controller and physical false when off, true when
on, four contacts, forward/reverse and 2.843 km/h crawl. The package comparison
proves all other class properties/resources equal to the tested lamp candidate.
The scout validator enforces this explicit requested behavior for all eleven
variants. Retail multiplayer and owner driving remain unverified.

Evidence: captured installed prop_truck.ssc enum/default and
prop_truck_view_controller.ssc SetState in reports/native_controls_sources;
campaign/scout_20260930_01/native_final_review.json, differentialRefinement,
package_audit.json and tools/scout_finish.py. The Lada omits the forced leaf,
but the native SDK source and actual final Roamer input establish this finding.



## Native sand-load controller requires route-following (Dump Twuck, 2026-10-01)

**SDK/Native startup:** generated `truck_view` classes containing
`prop_load_volume_controller` also need `prop_route_following`. Enable
`aiRouteFollowingSettings`; it supplies this property even when the truck is
player driven. A successful BRO build and resource-closure audit miss the
dependency: the engine aborts at scene load with `Required property
PropRouteFollowing ... can't be resolved`. The shared compiled-class linter
now emits RC033 by inspecting explicit property declarations, including a
regression against misleading string mentions. Custom inherited class bases
are outside this check's scope.

Evidence: Dump Twuck history/runtime_001_failed/error and crash_data archives,
the pinned build-007 package, native PropLoadVolumeController require declaration,
and tests/test_load_volume_dependency.py. Later driving/unloading and campaign
acceptance remain separate evidence. RC033 runs through existing shared vehicle
compiled/final recipe checks.


## Donor sound blueprints can require absent gameplay components

**SDK/Native startup, Dump Twuck 2026-10-01:** copying the TUZ Lynx engine
blueprint also copied `BlueprintNodeOnWinchStateChanged`. Without `PropWinch`,
its HandleBlueprintInited dereferences null and the native play engine crashes.
Remove the whole winch sound branch when the authored vehicle has no winch;
retaining ordinary engine/gear/handbrake sound nodes is sufficient. Audit donor
emitter locators against the new rig as well. RC034 inspects complete generated
truck_view property tables for the specific subscriber/controller dependency;
custom inherited bases are outside its scope. Mere text mentions do not count.

Evidence: dumptwuck_mod/history/runtime_002_failed/crashes contains the native
SSL stack, exact build-009 PAK, fixture and run identity. The engine loaded the
scene but failed in BlueprintNodeOnWinchStateChanged.HandleBlueprintInited.
This is startup evidence, separate from driving, unloading and campaign tests.


## Seeded native sand is not a rigid box fill (Dump Twuck, 2026-10-01)

**Native private fixture:** SetVolume(GetMaxVolume()) initially measured
119.030 m3 / 222536 kg. The open-backed bed settled near 92.14 m3; raising its
powered hinge to 0.87267 rad reduced this to 0.385 m3. Separate immediate fill,
settled carrying load and tipped discharge measurements. The subsequent owner report identified unwanted sand loss with the tray down.
The earlier check treated that loss as acceptable settlement; this did not establish
a working carrying load. Require stable retained volume and no pour emission at
rest and while driving, separately from tipped discharge. The native grid capacity also differs from a Blender box's
123.631 m3 envelope; record native measurements rather than equating the two.

Six tires retained contact with loaded spring travel 0.136-0.165 m out of
0.800 m. The hinge returned within 0.00003 rad of down. These are private
flat-pad/seeded-payload observations, not refill-station or campaign evidence.
Source: dumptwuck_mod/history/build_010_behavior_pass_camera_failed/native_review.json,
the pinned build-010 PAK and runtime's numbered correlated SSL responses.


## Generated winch views use the view controller (L275, 2026-10-01)

**Retail/Build:** the RC034 subscriber check initially required a literal
`prop_winch` property. This rejected the already working L275 winch setup.
Shipped truck_view classes with `BlueprintNodeOnWinchStateChanged` declare
`prop_truck_view_winch_controller` instead. Either actual declaration satisfies
the component dependency; `prop_winchable` is only a target and string mentions
are insufficient. Keep the no-controller rejection from Dump Twuck.

Evidence: l275_minespec_mod/reports/front_end_v5/winch_check_survey.json records
each inspected retail member and SHA; build-016 failed at the compiled check,
before packaging. tests/test_winch_blueprint_dependency.py covers the generated
view controller and target-only/text-only refusal. This corrects lint scope,
not the vehicle's authored winch behavior or in-game acceptance.


## Fixed rear cap retains sand but can block unloading (Dump Twuck correction)

**Owner report / SDK / native private fixture, 2026-10-01:** v1 spilled sand
with the tray down. A rear load boundary retained 170.376 m3 after settling,
stationary hold and driving/braking with empty native pour emit data, but the
fixed cap only lost 3.7 percent at 50 degrees. A small volume decrease cannot
prove functional unloading. Preserve this intermediate package as rejected.

The installed `PropLoadVolumeController` schedules hydraulic cap checking only
with `canBeDynamicallyOpened` and hydraulic lid enabled. Its CheckConstraint
sets the cap from dump angle and refill threshold; it also needs a real closing
physical joint and matching powered states. `TruckConstraintState.Set(string,
string)` indexes those state maps/arrays: nonexistent strings are unsafe. Hidden
load boundaries need explicit native markup visibility flags; a Blender
hide_render flag alone does not hide their exported mesh.

Evidence: dumptwuck_mod/history/revision_002_before/feedback.json;
history/revision_002_fixed_cap_rejected/manifest.json and native_review.json;
reference/prop_load_volume_controller.ssc and truck_constraint_state.ssl.
Build-014's native lid implementation remains pending fresh runtime evidence.
Do not require rear walls on all vehicles: shipped open-backed mine trucks
exist. Project runtime gates now measure retained volume, emission and at
least 95 percent discharge. General static enforcement is deferred until a
vehicle-independent load protocol is supported.


### Validated dynamic sand-cap correction

**Native private flat-pad fixture, Dump Twuck v2, 2026-10-01:** package
`d1e02c4e93c67884a1536b3b2654400014b7349adc74edef0184dbf5091d91e4` passed 46 native checks. It retained
170.375854 m3 through loaded driving/braking, with no pour emission,
and tipped from 170.375854 to 0.548963 m3.
A real hidden 20 kg closing body/hinge and powered closed/open states drive the
stock hydraulic lid controller; the original user-controlled dump joint is
retained. The native cap closes at dump angles <=4 degrees within the refill
threshold, opens when tipping, and closes after returning down. This changes
the saved joint layout: sell and buy a fresh vehicle after updating.

The intermediate fixed cap remains rejected, and the earlier large v1
stationary loss is no longer accepted as settling. The final adapter explicitly
clears startup payload before empty/camera measurements, fills through the
native controller, measures full stationary/carried load and requires >=95
percent discharge. Native grid capacity is 170.376 m3, distinct from the
123.631 m3 authored box envelope; maximum mass remains 222536 kg.

Evidence: dumptwuck_mod/package/candidates/dtw-20261001-v2,
recipes/build-017-camera-framing.json and test-017-final-framing.json;
reports/native_review.json and preserved numbered SSL responses. Refill-station,
retail save and multiplayer acceptance remain separate and untested.
The project regression is wired into its pinned test phase; universal static
rear-wall enforcement remains unjustified for shipped open-backed mining trucks.


### Where the carried surface and pour stream are defined

**SDK/generated declaration inspection, Dump Twuck, 2026-10-01:**
`prop_load_volume.volumeMesh` names the authored hidden load envelope;
`parentBody` binds it to the moving dump body. Left/right/front/back walls are
separate named load boundaries. In the generated Dump Twuck class these are
`hidden__load_volume`, `BoneDump_cdt` and `hidden__load_border_*`. The particle
controller separately selects `gpu_sand_pour`. The native `PropLoadVolume` API
tracks current volume/mass and returns `SandParticleEmitData` entries containing
position and amount. `CheckSandPouring` transforms these local positions through
the truck geometry into world space for domain checks. The hydraulic branch's
`CheckConstraint` reads the actual dump joint angle and toggles `SetCapEnabled`
using the dump/refill thresholds. These are distinct authoring, simulation and
effect controls; retained mass alone cannot prove a fitted visual surface.

The internal surface reconstruction and deposition solver are native code, not
exposed by these script declarations. Do not claim a particular voxel spacing,
per-grain rigid-body simulation, particle-to-terrain algorithm or exact cause of
the observed full-load rear overhang from these interfaces. The authored box
versus measured native capacity discrepancy above requires runtime validation.
The official terrain documentation describes sand as a terrain component stored
in a texture map, with per-chunk changes; this supports describing the resulting
ground pile as terrain data, without claiming the native deposition algorithm.

Evidence: dumptwuck_mod/tools/create_models.py and truck_bro.py;
project/mods_source/autogen_dw/trucks/auto_dumptwuck/auto_dumptwuck.cls;
reference/prop_load_volume.ssc (native API and SandParticleEmitData) and
prop_load_volume_controller.ssc (CheckSandPouring and CheckConstraint).
Official terrain reference:
https://roadcraft-modding.prismray.io/scene_components/terrain/export_load_terrain/.
Documentation clarification only; no new build, install or acceptance.

**Superseded in part (2026-10-02):** the grid spacing and the cause of the full-load rear overhang are now
decoded: see Correction 2 below and "Dump truck loads with `roadcraft.load_volume`".


### Correction: how the carried sand is drawn (Dump Twuck revision 3, 2026-10-01)

**SDK shader source / native captures re-measured:** the surface path is
inspectable after all. `root/paks/client/default/default_non_retail_resources.pak`
ships `shaders/code/load_volume.{vsh,hsh,dsh,psh}`, `load_volume_consts.fx` and
`registers_load_volume.fx`. A grid of quads covers `LOAD_VOLUME_AABB_MIN/MAX`
in x/z; each vertex is `aabbMin.y` plus a height from `LOAD_VOLUME_LOAD_MAP`
(blue = surface, alpha = column floor) times `LOAD_VOLUME_MAX_HEIGHT = 4` m,
then `LOAD_VOLUME_WORLD_MATRIX`. No sides are drawn. The pixel shader clips by
`saturate(thickness / 0.1)` against displacement noise, so empty cells vanish
but the steep sheet between a thick cell and an empty one stays visible.
Engine strings show the mesh is convex-hulled ("convex hull creation of load
volume failed") and simulated as a Havok height field. Native capacity was the
hull volume plus about 5% (Dump Twuck builds 019/020: 56.35 m3, hull 53.37 m3).

Reprojecting builds 020, 021 and 023 (logged fly-camera eye/target, F = 842 px
at 1732 px, hub-calibrated to 6 px) put the drawn sand at the authored model
position, +0.25..1.0 m rearward and 0 vertical (IoU 0.70-0.84; the supposed
3.677 m pivot shift scored 0.14-0.35). The pivot double-offset theory and its
compensation are withdrawn. The piece under the tray matched the sheet falling
off the volume's thick rear edge; a side curtain, which would have been plainly
visible from the same camera, was absent. How far the grid extends past the
hull is still unproven.

Evidence: dumptwuck_mod/reports/revision_003_refit/ (shaders, scripts/proj.py,
render_hyp2/3.py, render_curtains.py, jobs3.json, tub_probe*.json, images) and
history/revision_003_build023_superseded/. The retail Aramatsu Bowhead's
`_load_volume` node sits at the model origin with model-space bounds exactly
between its tub walls (bounding records read with scripts/tpl_boxes.py); the
Tayga 6455B's node is also at the origin (its bounds were not decoded).

### Correction 2: the sand grid comes from the border meshes (Dump Twuck revision 4, 2026-10-01)

**Disassembly (Roadcraft ModEditor.exe, load-volume setup near 0x1405DC800-0x1405E0800) /
Game (owner's retail screenshots of revision 3):** revision 3's "thick rear edge"
explanation above was incomplete. How the engine builds the height grid:

| Step | Decoded behaviour |
|---|---|
| Volume | Mesh vertices go through the node's local-to-parent matrix, then a convex hull |
| Grid rectangle (x/z) | Union of the four `bodySettings` border meshes' bounds in the `parentBody` frame, **not** the volume's; insets: min x +0.01, max x -0.01, rear (native min z) +0.2, front -0.01 |
| Back border | Its transform is composed with its **parent's** local transform before the bounds are taken (the other three use their own local-to-parent transform). Shipped dump trucks hang the back border from the tail-lid body |
| Cells | 4 per metre per axis, count `int(size * 4 + 0.5)` clamped to 2..32 |
| Columns | Vertical rays from +-16 m through the hull give floor and surface; samples are nudged 1/64 m inward beyond +-0.125 m |
| Cells the hull misses | Floor = surface = the height where the ray hits a border mesh; with no hit, 0 in the body frame (the `parentBody` pivot height) |
| Sheet range | `aabbMin.y` / `aabbMax.y` are the minimum / maximum over all cells |

Dump Twuck revision 3 hung `hidden__load_border_back` under the bed body
(`BoneDump_cdt`, pivot native (0, 4.2, -3.677)), so the bed pivot was applied twice
and the grid ran about 3.7 m past the tail. 295 cells beyond the hull dropped to
the pivot height: the owner saw a sand curtain behind and below the tail with a
full heap, and a flat slab past the tail while tipping. An emulator of the decoded
rules (dumptwuck_mod/reports/revision_004/grid_sim.py) reproduces both.

Revision 4 hangs the back border from `BoneSandCap_cdt` as a sloped block at the
rear corners (y 6.10-7.30, bottom 6.0, top 6.62 rising to 6.86) and lowers the side
(6.95) and front (6.85) border tops to the sand height beside them, so cells the
hull misses sit at the local surface. Emulated grid: 31 x 32 cells inside the tub,
0 cells at the pivot height, 21 border cells, steps of at most 0.32 m where they
meet the heap. **Build (emulated); Game pending the owner's drive.**

Rules: hang the back border from the lid body (RC036); keep the left, right and
front borders under `parentBody`; keep all four inside the tub, since they set
the grid; give border tops the sand height beside them. Thin heap edges still
matter where the hull meets a border cell. The Bowhead and Tayga observations
above remain.

## Store price and fuel tank (retail values, 2026-10-02)

**Retail data (C:/RC/reference/bro_json/trucks):** `uiInfo.buyCost` / `sellCost` set the
store price and sell-back; shipped trucks sell back at 0.85-0.92 of the price (Aramatsu
Bowhead 65,000 / 58,900, Baikal 65206 36,000 / 32,400, Warden Kochevnik 120,000 /
110,000, Vostok MU97 82,000 / 70,000). `fuelSettings.maxFuelTankVolume` is the tank in
litres (80 for scouts, 730 for the Baikal 65206 heavy dump truck, 1,224-1,746 for heavy
tracked machines, 2,850 the largest), with `fuelConsumption` 0.04-1.18 (Baikal 65206 0.39).
The Dump Twuck v5 owner asked for at least 4,000 L and $1,150,000; it sells back at 90%.
A project export check that pins the store entry must read these values from the
project's settings: the Dump Twuck's preflight still expected `buyCost == 1` and stopped
build-027 in the package step.
