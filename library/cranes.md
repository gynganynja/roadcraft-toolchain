# Cranes: boom, telescopes, hook and crane controls

How a RoadCraft mobile crane is put together, read from the retail cranes and built twice: the KGS-25
crawler crane (Codex's kgs25_mod, 2026-10-02) and the Kanga 25 articulated pick-and-carry crane (kanga25_mod,
2026-10-10, from a Franna MAC25-4 asset). Grades as in [README.md](README.md). Rig frames and hinge axes:
[frames.md](frames.md); visual cylinders: [ik-visual-rigs.md](ik-visual-rigs.md); articulation:
[articulated-steering.md](articulated-steering.md).

## The pieces

| Piece | Where | Grade |
|---|---|---|
| `craneSettings` (`CraneSettings`): `propCraneIK` (bodies the game moves to put the hook where the player steers it), `winchSettings` (`CraneWinchSettings`: `maxLenght` - the misspelling is the field name - `minWinchLength`, `strength`, `craneZoneRadius`, `winchSource` {bodyName, offsetInBodySpace}), `craneWinchMode`, `isMultiWinch`, `amountOfWinches`, `isAnchorsEnabled` | Truck BRO | Retail |
| Slew, luff and telescope joints: `tpl_markup_constraint_hinge` / `_prismatic` with a `tpl_markup_position_motor` | Body model markup | Retail |
| Controls: `axisControls` / `staticTruckAxisControls` with `CRANE_X`, `CRANE_Y`, `CRANE_Z`, `CRANE_ROTATE`, `CRANE_WINCH`; the action lists (`alternativeActions`, `legacyCraneActions`, `firstAction`..`sixthAction`); `equipmentCameraSettings` type `CRANE` | Truck BRO | Retail |
| Shop and details: `uiType UID_TRUCKS_TYPE_CRANE`, `detailsInfo.craneDetails` {LiftWeight t, boomLength m} | Truck BRO | Retail |
| Crane sounds: the Addon graph's `BlueprintNodeOnCraneArrowPositionChanged` (`rootBodyName`, `hookBodyName`, `xConstraintName` - the donor's names must be remapped, lint RC045), `BlueprintNodeOnCraneWinchChanged`, `BlueprintFunctionCraneAxisControlSoundNode` | Compiled class graphs | Retail, Build (KGS-25) |
| The hook and rope are drawn by the game's crane winch; no retail crane has a modelled free hook body | - | Retail |

## IK chains seen in retail

| Vehicle | `propCraneIK.bodyNames` | Notes |
|---|---|---|
| Baikal 5916 crane | Body, Tower, ArmHinge, Arm1 | articulated wheeled crane, crane on the rear (root) body |
| Aramatsu Forester Neo crane | **Front**, Tower, ArmHinge, **Arm_01, Arm** | articulated; the chain starts at the front (non-root) body; **two telescope prismatics** (0-3 m each, childRotation [180,0,0] on its bones) |
| EPEC TC305, MAG240 | Chassis, Cabin, CraneSeg1, CraneSeg2 | tracked, `isAnchorsEnabled False` (no outriggers) |
| ZiKZ 612C, HWC945 | Body/Chassis, Tower, segment 1, segment 2 | truck cranes |
| truck loader cranes | Crane, RotationBase, ArmHinge, Arm1 | the chain starts at a crane-base body |

**Rules (Retail):** every chain starts with the body the crane stands on, then a slew (`Tower`) hinge, then the
luff hinge, then one or two telescope prismatics. The first body need not be the physics root (Forester: front
frame; loader cranes: crane base). A crane without outriggers sets `isAnchorsEnabled = False` and uses the TC305
action lists (no `UID_HUD_CRANE_ANCHORS` / `seventhAction`).

## Kanga 25 build (2026-10-10, Build; owner drive Open)

* Chain `[BoneFront_cdt, BoneTower_cdt, BoneBoom_cdt, BoneTele1_cdt, BoneTele2_cdt, BoneTele3_cdt]`:
  **three telescope prismatics** (one more than any retail crane) at the owner's request, 0-3.9 m each, identity
  `childRotation` on identity bones (slides along native +Z = Blender -Y, KGS-25 frames rule).
* **Slew-less crane:** a pick-and-carry crane swings the load by articulating. A hidden 1.5 t tower body with a
  +-1.5 degree slew hinge keeps the retail chain shape (every retail chain has a slew joint); `CRANE_ROTATE`
  therefore barely moves anything. Whether the IK solver behaves well with a near-locked slew is **Open** until
  driven; the fallback is a single telescope joint with the inner sections following.
* Luff hinge `childRotation [0,-90,0]` (positive raises; KGS-25), limits 0..60 degrees (the art's boom tail meets the
  rear deck above ~49 degrees straight ahead: visual only, boom and rear share a no-collision group), maxForce 9 MN.
* Hook: the modelled hook block hangs from the boom head on a `tpl_markup_constraint_ball_and_socket` (250 kg,
  angular damping 4); a `HookBlock` graph hides it (and its rope falls) on `OnAttached` of
  `BlueprintNodeOnCraneWinchChanged` and shows it on `OnDetached` and at init (KGS-25 pattern plus an init node,
  RC038). Winch source = the head sheave on the last telescope.
* Donor for everything else: the retail Baikal 5916 crane BRO **merged over its chassis template**
  (`designer_wizard/trucks/templates/chassis_baikal_5916.bro`; the retail BRO's `__type ChassisBaikal5916` is that
  template), with the complete graphs taken from the compiled retail class (`prop_blueprints`), as the KGS-25 did
  with the TC305. Every donor body/joint/locator name was mapped or dropped; the generator script fails the build
  on any unmapped name.
* Graph locators the Baikal class needs and a modelled crane may lack: `ctrl_switch_handbrake`, `ctrl_gear_stick`,
  `ctrl_gear_stick_low`, `Bone_wiper_left_2`, `Bone_wiper_right_2` (sound emitters), the cockpit crane levers
  `ctrl_grapple_tower|arm_tilt|arm_ext|hook` (rotated by `dataDashboard.equipmentChain` with `CRANE_X|Y|Z|WINCH`),
  and three `cdt_*` collision names used as Addon sound positions.

Evidence: kanga25_mod `tools/prepare_mod.py`, `tools/kanga_config.py`, `tools/audit_rig.py`; recipes build-002 /
test-002 (all steps passed), candidate `kanga25-20261010-c1`, installed 2026-10-10; no engine run (owner's choice).

## Kanga 25 c2 (2026-10-10): shaking and a deploy crash fixed (Build; drive Open)

* Owner on c1: "When the boom is extended forward and up the crane shakes violently". Crane joint values now follow
  the retail Baikal 5916 (motors with damping 0.99, telescope 0.8 MN; tower 2.2 t) rather than stiffer, lightly
  damped motors on light bodies; the modelled hook is secondary physics (`massFactor 0`). Unbenched (owner: no
  engine runs).
* A crane without anchors must drop the donor's `BlueprintNodeOnAnchorsStateChanged` nodes (they assert the anchors
  controller; c1's crash dump). See [symptoms.md](symptoms.md).
* Toolchain note: a test phase that reads the built package needs it as a per-step input with its sha256 (a global
  source pin makes the build's package step fail "changed pinned input"); kanga25_mod `tools/pin_test_inputs.py`
  writes the current hash before `mod-recipe`.

## Kanga 25 c3 (2026-10-10): benched shake, steering and slew fixes (Measured; drive Open)

* First crane tuned on the editor bench (`kanga25_mod/tools/bench`: timed SSL commands on the sampler connection,
  crane input through `PropIk.Update` in model space, plans `crane`, `carry`, `kdrive`). Luff motor tau 0.8 -> 0.4,
  damping 1.0 removed the raised-boom rocking ([symptoms.md](symptoms.md)).
* A slew-less crane still needs the tower body in the IK chain; lock it with `angleStart = angleEnd = 0` on the slew
  hinge and drop the `CRANE_X` axis controls (and the `grapple_tower` dashboard lever) so the mouse cannot swing it.
  Measured: sideways crane input leaves slew at 0.
* Single bench runs are noisy (the same variant twice: launch angular rate 0.014 vs 0.10, slalom roll rate 6.6 vs
  10.4 deg/s); trust only differences that repeat across variants. One carry run stalled at full lock from standstill
  with a front wheel unloaded and did not repeat.

## Telescope joints in the IK chain: retail survey and the visual follower (Kanga 25 c5, 2026-10-10)

**Retail (compiled classes, default_other.pak):** every telescopic crane IK chain has one prismatic: Baikal 5916
(Body, Tower, ArmHinge, Arm1), ZiKZ 612C (Body, Tower, Segment_1, Segment_2), EPEC HWC945, Vostok ETV89; the Aramatsu
Forester Neo crane is the only one with two (Front, Tower, ArmHinge, Arm_01, Arm; 1 t each, tau 0.9, 0.3 MN,
`constraintInertiaStabilizationAmount 0`). No retail crane slides inner sections that are not IK bodies.

**Game (owner report, Kanga c4):** with three telescope prismatics the boom oscillated with the boom raised and a load
on, kept going after the load was dropped and stopped once the boom was retracted. **Inferred cause:** the redundant
chain lets the IK split one target among three joints in many ways; fully retracted, every joint sits on its stop.
**Build (c5, owner's choice):** two joints as the Forester (tele1 0-3.9 m, tip 0-7.8 m) and the middle section as a
visual follower: its meshes skinned 0.5 / 0.5 to the outer-section and tip bones. Prismatic joints keep the sections
parallel, so linear blend skinning moves it exactly half way, undeformed, in every LOD (kanga25_mod `FOLLOWERS`,
`create_models.bind`, rig-audit follower check). The follower has no collision hull. Drive: Open.


## Outriggers (anchors): retail values and stowing them clear (KGS-25 final, 2026-10-11)

**Owner report on the KGS-25 r4 legs:** "hit on everything in their current tucked up position, dont extend down far
enough and look not good". r4 hung its jacks outboard of the tracks with the pads 0.33 m up and a 0.37 m lower stroke
(chosen because a 0.40 m stroke stalled 2 cm short against the ground and the anchors never reported open).

**Retail (truck BROs + markups, Retail):**

| Vehicle | Beam / swing | Foot body | Foot motor | Foot stroke | Mass scalers |
|---|---|---|---|---|---|
| EPEC HWC945 | prismatic 2.3 m, 1500 kg, 0.8 MN | 850 kg | tau 0.73, 10 MN | 0.6 m | chassis x4, beams x4, feet x2 |
| ZiKZ 612C | hinge -90 deg, 1000 kg | 600 kg | tau 0.73, 10 MN | 0.515 m | body x3, legs x4, feet x2 |
| KGS-25 r4 (mod) | prismatic 1.15 m, 150 kg | 100 kg | tau 0.6, damping 0.8, 3.5 MN | 0.37 m | feet x3 |

Retail stowed pads sit ~0.35-0.45 m up and the strokes reach 0.1-0.25 m below the ground line, so retail outriggers
lift the vehicle. The anchors controller completes only when every constraint reaches its max (0.01 m tolerance).

**Build (KGS-25 final, unmeasured, drive Open):** stations moved to the empty corner pockets beyond the track ends
(under the bumper and the tail deck, inside the hull outline); beams retract into the hull body (their collision
boxes stay inside the hull when stowed); 3-stage visual jacks (middle stage skinned 0.5/0.5 like the Kanga
telescope follower); beam 1.6 m, foot 0.58 m from 0.46 m up; masses 400 / 300 kg taken off the hull with its COM
offset lowered so hull + stowed legs keep their centre; retail foot motor and scalers. Find corner pockets and check
the whole stroke with BVH overlaps (kgs25 final `tools/probe_voids.py`, `clash_detail.py`): the KGS front beams had
to dodge cab-door boarding steps and the sloped nose underside. If anchors stall again, shorten the lower stroke.


## Retail truck features a designer-wizard mod lacks (KGS-25 features pass, 2026-10-11)

**Owner:** "its a bit slow ... it needs smoke, terrain deformation, and any other features that vanilla vehicles
have". The r4 compiled class had an empty `vfx`, an empty `prop_wheel_particles_base`, no effects library or SFX graph,
untextured trails, no winch sockets, towing, driver or cockpit dashboard.

**Retail (compiled classes, Retail):** empty `{}` entries in a truck's `sfx.list` resolve to `ssl/sfx/<name>.sfx`
through the class resource's `linksDescVisual`; the exhaust effects find their node by `nameParent = "sfx_exhaust_*"`,
the haze by `"sfx_radiator_haze"`. The TC305 "SFX" blueprint (VfxRestart/VfxStop on engine starting / started /
acceleration / reverse / shutdown) drives them. `vfx` bones may hang on physics bones with `boneOffset` (209 shipped
vehicles do, incl. on `BoneChassis_cdt`); systems 26 + water/grass params give deformation, grass and splashes. Trail
textures need `linksPct` in the WHEEL class resource. Copying a donor's resource links: leave out `linksTpl` and
`parents` (the Baikal links its own `crane_truck_2_res` model).

**Build (unmeasured, drive Open):** kgs25 final `tools/features_class.py` copies TC305 `sfx` list + SFX graph,
`prop_wheel_particles_base`, `prop_water_*`, `prop_towing`, `prop_truck_steering_wheel`; writes the vfx boxes, winch
sockets, driver offset and a 27-element dashboard (Baikal `EquipmentChainOrientationInputElementCockpit` for crane
levers, TUZ 303 `SteerigElementCockpit` RL for steering levers) into both compiled classes, and a best-effort BRO
mirror (`propVFX`, `effects`, `towing`, `winchSockets`, `dataDashboard`, wheel `propWheelTrail`). Speed: road speed
~ angularVelocity x 4 x contact radius (m/s); the KGS's 0.2 m contacts made its 10 km/h gearbox ~4.6 km/h.
**Trap repeated:** the first build skinned the emitter meshes at the model origin, so `tpl-nodes` showed both
`sfx_*` nodes at [0,0,0] (smoke on the ground, frames.md). Bone-parent them with the origin at the effect and check
the compiled node positions before install.


## Player feedback on the published KGS-25: hook, controls, operator view (2026-10-13)

**Player reports (saber.games, Unverified):** "the hook is decorative only and doesn't do its job"; "no view from the
operator's cab"; animations criticised without detail.

**Retail (compiled classes, Retail):**
* All 21 shipped cranes carry `staticTruckAxisControls` in `prop_truck_view_actions_mapper` (Game.First/Second/Third
  axes -> CRANE_Z, X, Y, ROTATE, WINCH) beside the mouse-button `axisControls`. Both mod cranes (KGS-25, Kanga 25)
  declare them in the BRO, but their compiled classes lack them. Check the compiled class, not the BRO.
  **Corrected cause (Kanga 25, 2026-10-13, Build):** the generator does emit the field; both projects' own `build.py`
  generate stage removed it (`mapper.pop('staticTruckAxisControls', None)`, comment "no static axis duplicates",
  first in the original kgs25_mod build and copied into kanga25_mod). Keep the generated block (Baikal: 6 mouse
  `axisControls` + 5 stick/key `staticTruckAxisControls`, `isMainActionsMapped True`); kanga25_mod package audit
  now checks CRANE_Y / CRANE_Z / CRANE_WINCH are bound.
* A crane with a separate operator cab (Baikal 5916) has `equipment_cockpit` in `prop_game_camera_user` (joint
  `_equipment_cockpit_camera`) plus `prop_truck_camera_equipment_cockpit_preset`; a model node alone gives no view.
* No retail crane has a modelled hook or a show/hide graph for one; `crane_winch_controller` (7 m scanner, ground point,
  `winch_trail` rope) does the work. A modelled hook at the boom head reads as decorative because it never follows
  the winch length.
* `BlueprintNodeOnAnchorsStateChanged` outputs: OnOpenStarted, OnOpenEnded, OnCloseStarted, OnCloseEnded. Retail
  HWC945 and ZiKZ 612C use it with `prop_truck_anchors_no_collision_controller` alone (no `prop_truck_anchors_controller`).

**Build (KGS-25 feedback pass, drive Open):** TC305 `staticTruckAxisControls` copied in; Baikal camera logic and a
trimmed preset added, node moved to the operator eye the interior was built around; the modelled hook hides on
OnOpenEnded and on attach, shows on OnCloseStarted; its 180 kg pendulum becomes a retail ragdoll (cone / plane /
twist 25, spring 100 / damping 10, twist axis native up via childRotation [0,0,90], `massFactor 0`, body
`no_collision`); IK caps raised to the Baikal's 0.9 m/s / 50 deg/s and `maxTargetPositionError` 0.5 (r4 had 0.65 / 15
and 0.35) after the Kanga 25 c9 audit below (kgs25 final `tools/feedback_fixes.py`, `features_class.tune`). Markup
joints are read at load: the compiled .tpl holds no constraint data, so a markup-only change needs no recompile.
**Owner drive (Game, 2026-10-13): the 25 deg ragdoll hook stopped hanging plumb once the boom luffed** (luff 0..75 deg;
the cone limits the hook relative to the tip, and the spring motor drags it along). A boom-head hook needs a joint
range covering the whole luff plus tilt: back to the unlimited ball-and-socket (schema takes `massFactor`), kept
massFactor 0 + no_collision, angular damping 4 (kgs25 final `tools/hook_swing.py`). Retail dangling-part ragdoll
limits suit parts fixed to one body, not a hook on a luffing boom. The Kanga 25 c9 hook has the same limit.

## Animation audit vs retail (Kanga 25 c9, 2026-10-13; player report "criticises its animations", nonspecific)

Offline audit of every animated subsystem against the retail Baikal 5916 / Forester Neo classes and markup:

| Subsystem | Kanga c8 | Retail | Action |
|---|---|---|---|
| Crane IK joint caps (`propCraneIK.ikSystem`) | prismatic 0.6 m/s, hinge 12 deg/s | 0.9 m/s, 50 deg/s (Baikal, Forester) | c9: retail caps; target speeds (1.2 / 0.8 m/s) kept |
| Modelled hook block | unlimited ball-and-socket, collides | dangling parts: `tpl_markup_constraint_ragdoll` (Baikal lamp: coneAngle 30, twist -10..20, motors [{spring 100, damping 10}], massFactor 0) and body `collisionLayer "no_collision"` | c9: ragdoll 25 / +-25 (twist axis not established, so symmetric) + no_collision |
| Stick / keyboard crane axes (`staticTruckAxisControls`) | popped by our build.py | present in 21 / 21 shipped cranes | c9: kept |
| Cab levers, steering wheel, pedal | Baikal values (levers +-8 deg, speed 20; wheel +-360) | same | none |
| Solid-axle followers (`dependentAxles` wheel IDs -1) | -1 | -1 in 53 retail classes | none |
| Visual cylinder strokes | luff 0..1.20 m needed within -0.6..1.6; steer +-0.27 within +-0.45 | - | none |
| Luff cylinder base `HINGE2` | two axes | Baikal tower piston: single `HINGE`; HINGE2 also retail for cylinders | kept (no in-game evidence of wobble) |
| Skinned hoses at the limits (artic +-30, luff 60) | no collapse in renders | - | none |

**Inferred, not driven:** with a 12 deg/s cap the luff cannot follow the IK target near the boom foot; the target
stops at `maxTargetPositionError` and the boom moves stop-start. Grades: retail values **Retail**; effects **Inferred**
(no Mod Editor runs, owner rule). Evidence: kanga25_mod `kanga_config.py` (CRANE_IK_CAPS, NO_COLLISION_BODIES, hook
JOINTS entry), `prepare_mod.py` ragdoll branch.

## Reaching the operator-cab camera; hook show/hide (KGS-25 v8, 2026-10-14)

**Owner (Game):** "Cant find operator cab view?" **How the game reaches it (Retail, code:
`ssl/camera/game_camera_vehicle_switcher.ssc`, `ssl/game/truck/player_input_truck_controller.ssc`):** the vehicle
camera has two independent states, first/third person and VEHICLE/EQUIPMENT. `game_camera_equipment_cockpit` is
first person + EQUIPMENT, found by `prop_game_camera_user.additionalActivationLogics[*].info.cameraUid`. Two ways in:
the named action `TOGGLE_EQUIPMENT_CAMERA` (HUD "UID_HUD_EQUIPMENT_MODE", `fourthAction` on the Baikal 5916 and the
KGS) pressed while in the cockpit view, or entering crane controls (legacy mode) from the cockpit view. The HUD hint
shows only when `CanSwitchEquipmentCamera` holds (first person needs both the cockpit and the equipment-cockpit
logic). Tell owners: cockpit camera first, then Equipment mode / crane mode.

**Hook block (Build, drive Open):** the modelled hook hides on OnAttached and shows on OnDetached, all seven meshes
skinned to the hook bone listed; the pass-1 outrigger triggers are gone (owner: hook "never comes back"). See
symptoms.md, "A hidden part leaves stray vertices behind".


## SuperHeavy Crane audit (2026-10-14): joint axes taken from the wrong bone frame (Build; drive Open)

A client's editor-built 12-axle crane (`SuperHeavy Crane.pak`, 17-section 213 m boom, swing-out outriggers) had
every crane joint on the wrong axis. Its childRotations were the identity-bone values (`[90,-90,0]` vertical,
`[0,0,0]` along the stowed boom) on bones that point **up** in Blender, so by the [frames.md](frames.md) bone rule
(native Z = minus head -> tail) the compiled node table showed native Z straight down: the 17 telescope prismatics
slid each section out of the bottom of the boom (the client's "sections fan apart"), slew turned about the fore-aft
axis, the pod swing hinges about a horizontal axis, the inner beams slid vertically and the jacks fore-aft. Luff was
right only because its bone pointed along the boom. **Rule (Build, compiled frames checked with `tpl-nodes`):** never
copy a childRotation between rigs; compute it from the child bone's frame for the intended world axis
(`zombie_crane/tools/fix_model.py` `rot_for`: native frame from the bone matrix, then `vehicle.child_rotation`).

Fix (candidate c1, installed, not driven): 2 IK telescope bodies (sections 9 and 17, identity bones) and the other
15 sections as linear-blend followers - section i skinned base/tele_9 at i/9 below 9, tele_9/tele_17 at (i-9)/8 above
- which generalises the Kanga 25 half-way follower to any number of nested sections (posed check: every section 1.08 m
inside its neighbour at full extension). Also: no suspension at all (RC063, strength 0), the lit material in every
lamp state (RC067), a 0.5 m/s IK prismatic cap for 200 m of travel, an 80 m winch on a 213 m boom, and no visual IK
on the luff cylinders. The editor's Build Mod packs material instances under `materials/<name>_<guid>.mi`; the
validator now resolves that folder too (it reported 73 false RC070 errors).

**Follow-up (c1 drive, owner: "All the controls are messed up and dont do the correct thing"):** the crane IK moves
its target in the **first chain body's** frame: `prop_ik.ssc` `UpdateTargetPosition` builds the effector frame from
`GetRootTransform()` (that body + `rootBodyLocalOffset`), uses its native Y as up and rotates the target about its
position. The client's root `BoneChassis_cdt` pointed up in Blender (native Y along the truck, native Z into the
ground), so crane "up" ran along the truck. Every retail crane chain body is identity (ZiKZ 612C Body, Tower,
Segment_1, Segment_2; Kanga 25 too). **Rule (SSL source + compiled frames):** make the chain bodies identity, put
`rootBodyLocalOffset` on the slew axis (at luff-pin height), and check the class's other offsets on those bodies
(winch points, VFX boxes) were authored for that frame. Also missing in the client class: `equipmentCameraType CRANE`
on `prop_camera_equipment_preset` (ZiKZ, Kanga), crane sound graph (`Addon`), effect emitter nodes
(`sfx_exhaust_*`, `sfx_radiator_haze`) and the effect/sound links in the class `.resource`. c3 installed; drive Open.

**Telescope reach wall (c4-c7, owner: the boom stops at about 45 m total, about 23 m per joint; engine read 2026-10-22).**
The native crane IK puts no cap on how far a telescope can reach (C, `C:\RC_RE\research\physics_semantics.md`
"IK prismatic reach").
- **Limits:** each prismatic's limits are the Havok limits from the markup, unchanged.
- **Solver:** `dq = (JᵀJ + 0.1·I)⁻¹Jᵀe`, then a uniform speed cap and a clamp to the limits. There is no reach, length,
  root-distance or cdt-derived limit.
- **Even split:** two telescope joints on the same axis always share an extension equally. An even 23/23 stop
  therefore means neither joint hit its own limit.
- **Hard stop:** the wall was the same in c4 and c7, although the motor-target lead differed about 10x. That points
  to a hard stop (I). In order of likelihood:
  1. a `propCraneIK.blockedZones` box, which moves and slews with the crane;
  2. compiled telescope limits that are not 104.94 / 93.28;
  3. a cdt contact at that pose.
- **Rules:**
  - keep `blockedZones` empty unless a zone is wanted;
  - check the compiled telescope limits with `tpl-nodes`;
  - in game, dbg var `Game/Truck/IK` shows whether the blue target sphere or the physical effector stops first.
- **SuperHeavy c7 check (2026-10-22, static, R):** all 18 jointed bodies (chassis to both telescopes and the outriggers)
  are in `main_collision_grp`, so they are mutually filtered whatever the group is called; the wheels are `phantom_truck`.
  The joint sweep finds no contact on any boom joint (`sweep.status` clear, 0 pairs) and the markup limits are
  104.94 / 93.28. A contact between the truck's own bodies is therefore ruled out. Still open: `blockedZones`, the
  compiled limits (`tpl-nodes`), or contact with the world or a modelled hook.
- **Winch rope ruled out (2026-10-22, C/R):** with nothing hooked, the crane has no rope constraint, rope bodies or hook body.
  - `TruckWinch.constraint` (`ConstraintKeepDistance`: a Havok stiff spring, min 1e-6, max = length) and the drawn `PhysRope` exist only between `TryAttach` and `Detach`.
  - Unattached, `maxLength` is just the length of the downward ground ray used to find hookable loads.
  - The rope hangs from `winchSource`, which in all 15 retail crane classes is on the last IK body (the tip), so it never spans the boom.
  - **Retail:** `maxLength` = `craneZoneMaxLenght`, and `maxLength` >= `craneDetails.boomLength` (HWC945 30/25.5, ZiKZ 30/21, TC305 25/18.5).
  - **SuperHeavy:** an 80 m rope only stops hooking loads once the tip is above about 80 m. Raise `winchSettings.maxLenght` and `craneZoneMaxLenght` together if that matters; no cap was found.
  - **Remaining wall suspects:** a contact at the 23 m pose, or a modelled hook that collides.
  - No validator check added: the rope does not limit reach.

## LTM 1150-5.3 all-terrain crane on the HWC945 donor (2026-10-22, Build; native stages and drive Open)

New mod `ltm1150_mod` (Liebherr LTM 1150-5.3 from the script-built source `C:\RC\LTM1150_Model`), Kanga 25 pipeline,
retail **EPEC HWC945** heavy crane as donor (BRO merged over `chassis_epec_hwc945.bro`, graphs from the compiled class).
Offline stages only (owner rule); grades below are Build unless stated.

* **Six telescope sections on two IK prismatics** (SuperHeavy generalisation): Tele3 carries sections 1-3, Tele6 4-6;
  sections 1, 2 skinned base/Tele3 at 2/3-1/3 and 1/3-2/3, 4, 5 Tele3/Tele6 likewise. Real 12.33 -> 66 m = 8.945 m per
  section (26.835 m per joint) leaves >= 1.87 m of every section inside the one behind (sections ~11 m long). Rig audit
  poses section i at exactly i x 8.945 m along the boom.
* **A boom that rests tilted needs a computed prismatic axis.** The LTM boom rests 0.548 deg nose-down; an identity
  telescope (childRotation 0) slides along the horizontal and would leave the sections 0.26 m off the boom axis after
  26.8 m. childRotation = `child_rotation(native boom axis)` = [0.5477, 0, 0]. Compute it whenever a long prismatic is
  not exactly along a native axis (frames.md rule, extended to small tilts that the eye misses at rest).
* **Outrigger beams with two visible stages:** HWC945 retail = one beam prismatic per corner (2.3 m) + foot. Here the
  inner stage (carrying the jack) is the anchor body over the full 2.71 m and the outer stage is a visual follower
  skinned 0.5 chassis / 0.5 beam body - it moves half the stroke, as the real two-stage beam does. Anchors without the
  HWC945 stowed-pad platform swap (`platformAttachedToAnchor/Truck`) like the KGS-25: pads hang under the rods.
* **Modelled jack rods limit the foot stroke:** retail strokes reach 0.1-0.25 m below ground (above). The LTM rear rods
  (1.0 m in a 0.84 m housing, pads 0.65 m up) reach 0.12 m below ground only after stretching the hidden rod top
  0.11 m inside the housing; front rods were retracted 0.15 m to stow the pads 0.40 m up and reach 0.20 m below. Audit
  the rod left in the housing at full stroke (`audit_rig.py`, >= 0.05 m).
* **Rear counter-steer on five axles:** retail per-slot `steeringAngle` (HWC945 30 / 20 / 0 / -20). LTM: one turning
  centre just ahead of axle 3, front from axle 1 at 30 deg, rear scaled so axle 5 sits at the retail -20 ->
  30 / 11.1 / -1.7 / -12.0 / -20. At a consistent -30.6 deg the axle-5 tyre swept into the rear outrigger box (rig
  audit: tyre sweep vs carrier hulls); retail tables are not geometrically consistent either.
* **Hook block from a transport pose:** the source hooks the block into the front coupling, tilted 51 deg. The model
  stage turns every mesh under `HOOK_BLOCK` about the sheave axis until the hook is plumb, then lowers it until the block
  top is 0.12 m under the lowest head geometry above it (1.97 m below the head sheave), and replaces the modelled falls
  with straight ropes skinned to the hook body (they swing with the ball joint). Hide/show list = every mesh bound to
  the hook bone (KGS-25 v8 rule).
* **Donor Body graph wiper nodes:** the HWC945 Body graph has `BlueprintNodeTplAnimOnBegin/OnEnd` (wiper sounds) that
  need `tplAnimation` wiper clips; with no modelled wipers the build drops those two nodes and their links (Inferred
  assert risk, the anchors-node lesson above). Wiper locators `BoneWiper_*_B` stay as sound positions.
* IK root: `rootBodyLocalOffset` on the slew axis at the slewing ring (HWC945: slew axis, 0.6 m above its root); masses
  scaled from the HWC945 (34 / 8 / 4 / 2.5 / 1.5 t, beams 1 t, feet 0.5 t, 61 t with wheels).

Evidence: `ltm1150_mod/tools/{ltm_config,create_models,prepare_mod,audit_rig}.py`, `build/model_layout.json`,
`reports/rig_audit.json` (PASS 50/50), `reports/prepare.json`. Import, generation, packaging and the drive are Open.

**SuperHeavy c8 (2026-10-22): the ~45 m telescope "invisible wall" = the collision group's NAME.** Laptop RE (code)
+ Mammoth RC75 bench (Confirmed): markup collision groups are numbered after the built-ins `default` = 0 and
`no_self_collision` = 1; a custom group name (the client's `main_collision_grp`) only filters members whose
breadth-first joint number happens to equal its index, so the boom sections, base and superstructure collided with
each other. The IK itself has no reach cap (limits pass through unchanged; even split of extension across collinear
prismatics). **Rule:** name a self-collision group `no_self_collision`. Retail ZiKZ `new_group` names are therefore not
a safe pattern to copy. c8 (8c0a116a) renames it; drive Open.
