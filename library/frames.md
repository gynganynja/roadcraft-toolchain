# Frames, units and conversions

## Axes

| Frame | Convention | Grade |
|---|---|---|
| Truck frame (authoring in Blender) | metres; front toward -Y, left +X, up +Z; ground at z = 0; origin on the ground under the vehicle | Build (every mod), SDK samples |
| Native (engine / USF) | X left, Y up, Z forward | Build |
| Truck -> native | (x, y, z) -> (x, z, -y) (`roadcraft.vehicle.rc_to_native`) | Build |

## Bones

| Rule | Grade |
|---|---|
| Rigid-body bones (`*_cdt`) with identity orientation are the simplest: native axes = body axes | Build |
| A Blender bone exports with native local X = bone X, native Y = the bone's roll axis (its Z), native Z = minus its head -> tail direction | Build (decoded from compiled models) |
| An identity bone in Blender points along +Y with zero roll | Build |
| A compiled model's node table holds world transforms (row-major, translation in the last row); read it with `roadcraft tpl-nodes` | Build, Retail |
| A wheel follows the nearest body bone (`*_cdt`) above its wheel bone. Compiled retail classes leave `parentFrame` empty (Baikal 65206, Arling 750R, DS-55), so re-parent the bones to move wheels onto another body | Retail; mechanism Inferred (tracked-vehicles.md) |

## Hinges

A markup hinge (`tpl_markup_constraint_hinge`) turns about the constraint frame's Z. `childRotation`
is Euler XYZ degrees (R = Rz . Ry . Rx) applied in the child bone's frame; for identity bones it turns
native Z onto the hinge axis. A positive angle is right-handed about that axis, child relative to
parent. `roadcraft.vehicle.child_rotation(axis_native)` gives the rotation, `euler_axis` the inverse.
(Grade: Build, derived on the SDK samples and the D11T with editor readouts; Game on the 16M3
grader, whose joints turned about the intended axes.)

## Mass

| Rule | Grade |
|---|---|
| The engine starts from the volume centroid of a body's collision shapes; `hkCenterOfMassOffset` (native axes) is **added** to it | Build (D11T engine readout: centroid 2.261 - 1.15 = comLocal 1.111) |
| Wheels are not rigid bodies of the model; their mass is in the wheel BRO | Build |
| Keep masses falling along a linkage: each body carrying at most about 3.3 times its own mass (the Crayfish sample's joint block is 3000 kg in a 0.5 m cube, its bogies 2000 kg plates) | Build (16M3 grader, from the SDK sample) |
| Official defaults: angular damping 1.5, linear damping 0.01, restitution 0.01, mass set by hand | SDK (documentation) |
| Masses, centre-of-mass offsets and constraints are read from the `.tpl_markup` text when the vehicle loads; the compiled `.tpl` holds none of them, so changing them needs no model rebuild | Build, Game (KGS-25 fix 2 changed only markup and class text in the package) |
| Springs of wheels hung on a light body come out far softer than the vehicle-mass formula (KGS-25 track frames at 6 % of the mass: 25-40 times); keep wheel-carrying bodies heavy (retail track frames 7.5 t) | Game (editor bench); the scaling Inferred (tracked-vehicles.md) |

## Collision

Convex hulls made from the body's own vertices are the quickest good shape. A hull's bottom is the
lowest vertex in its region, so floor the region above small low protrusions (brackets, tube ends)
or the body will catch on terrain where the visible underside would not (Game, buggy).

## Locators, levels of detail, collision objects

| Rule | Grade |
|---|---|
| Locators (`_cockpit_camera`, `_third_person_camera`, `_equipment_camera`) and collision objects keep identity world orientation in the SDK Lynx `.blend` | SDK |
| Collision is convex `cdt_` objects only; the root `BoneChassis_cdt` at the origin; objects at scale 1 and rotation 0 | SDK (documentation) |
| Levels of detail are authored `<stem>_LOD0 .. _LODn`; the exporter drops `_LOD0` (that node is `<stem>_vis`). Hide distances: 800 m vehicle, 350 m wheel; the LWI transition off for trucks | Build (EX5600), SDK |
| The water cut-off volume is found by name (`cutoff_volume`) | Build |
| Asset names lowercase | SDK (documentation) |

## Source art conversions seen so far

| Source | Conversion | Grade |
|---|---|---|
| FBX in centimetres tagged as inches (imported 2.54 times too large) | scale 0.01 / 0.0254 = 0.3937 | Build (buggy) |
| FBX facing +X with left +Y | truck = (y, -x, z) x scale | Build (buggy) |
| Skinned mesh on an armature | take the mesh evaluated through the armature (rest pose): the raw vertices differed by 2.4 cm at the wheels | Build (buggy) |
| FBX already metric and facing -Y (Warthog) | none | Build |
| One skinned mesh for the whole vehicle | separate it into loose parts and give each to the bone with most of its skin weight; parts blended between two bones (springs) are split | Build (buggy) |

Measure every pivot you configure against the mesh and make the build refuse to run when one is
more than a few millimetres off; the source rig's bone heads are good pivots when they exist.


## Fitted compounds and wheel-arch voids (Lada, 2026-09-30)

**Build:** Three broad boxes did not closely follow the Lada exterior. Its revision partitions source panels before convexification, with arch-clearance clipping, separate bumper corners, mirrors and underbody components. Convex simplification uses support points and a 4 mm plane-distance tolerance relative to each unsimplified hull; this does not assert a 4 mm fit to every concave source surface. Signed tetrahedral volumes recalculate the compound centroid before applying the existing target COM. `tools/audit_collision.py` samples the tyre contact volumes and is wired into final validation; `revisions/rut_contact_v4/collision_*.png` records visual inspection. Initial unrestricted side hulls intruded into 21 samples; arch clipping removed those overlaps. Low-detail VFX boxes stay inside the body rather than inheriting broad AABBs around curved arches. Terrain contact and runtime costs still require driving checks. Automation is project-specific because universal arch-clearance limits depend on the asset and suspension.

## Source proportions versus loaded stance (L275 79 conversion, 2026-09-30)

**User report:** L275's first fitted source had a short single-cab tray and
excessive cab/chassis separation, despite passing functional native smoke
checks. **Build:** measure the deck and bare cab independently; roof accessories
are not the factory cab height. The source deck was 2.0976 m. V2 makes it
2.500 m, lowers the cab 0.350 m and tray 0.300 m, retains wheelbase/door shapes,
extends rear hardware/frame, and refits hinge pivots, cameras, sockets and CDT.
The first lowered bonnet hull intruded into sampled front tyre volumes;
selecting its actual upper panel region removed those overlaps. The failed
clearance report remains in revisions/proportions_v2/bonnet_clearance_before.json.
Static tyre sampling is wired into validate.py, not treated as terrain testing.

**Game on v1; Inferred on v2:** ground-relative loaded height needs a settled
native body frame and the contact plane. Use physical tyre radius (nominal
radius minus radiusOffset), rather than visual tyre extrema. Transform the
bare roof sample through the body/geometry frame. V1's loaded root was about
0.106 m above its rigid pad. Applying that prior measurement to v2 gives a
2.0042 m roof estimate, near the 2.0058 m stock-plus-50.8 mm target. It is not
a measured v2 stance: COM, spring distribution and travel also changed. No
revised game test was launched after the owner prohibited focus-taking tests.
Dimensions come from the official Toyota GXL single-cab table (1955 mm roof,
3180 mm wheelbase) and MITS/Norweld single-cab tray listings (2415/2526 mm).
These corrections are source-specific, not a universal 350 mm cab offset.

The authored volume-weighted convex-hull centroid plus COM offset was
consistent, but v1's native chassis COM differed from that estimate. Keep
static authoring consistency separate from actual Havok compound mass data;
do not label the estimate as verified native COM or tune beta from an
uncertain transform. Evidence: proportion_source_measurements.json,
build/physics.json, v1 initial_probe/drive02 and v2 build-007/test-008. Project
dimension/clearance checks are appropriate; universal truck dimensions and
compound calibration are deferred because their assumptions are asset-specific.

## Recovery points on a nonidentity chassis frame (Roamer scout)

**Game/Build, 2026-10-01:** recovery offsets are in the named rigid body's actual
local frame, not a universal Blender-to-engine axis permutation. The Roamer's
native BoneChassis frame at rest has local Y pointing world +Z and local Z
pointing world -Y. Its matched authoring coordinates therefore used `(x,-y,-z)`
for socket offsets. The earlier test established five valid points and functional
attachment/pulling; it did **not** establish front/rear hardware fit. The owner
reported misplaced front/rear attachments on 1 October. Matched source geometry
then showed the inherited front points about 1 m behind the bullbar, and the rear
point about 0.85 m inside the rear bar. The earlier claim of fitted points is
superseded. Do not copy this sign pattern into an identity-frame truck. Inspect
GetLeft/GetUp/GetForward and transform the intended source point through the
inverse body frame first.

Evidence: Roamer `scout_20260930_01/runtime/candidate02/{settled_rest,utility_initial,
radar_start,winch_before,winch_after}.json`, matched source Blender and source
settings overlay. A normal native targeting/pull attached to another Roamer and
reduced rope from 10.4 to 8.70 m. A universal source-frame validator is deferred:
correct fitting requires the asset's intended source/world points and matching
native transform, neither of which can be guessed from offset values alone.


### Hardware fit after functional winch validation

**Authoring/Build, 2026-10-01, Roamer matched native artwork:** a valid socket and
shortening rope can still attach inside bodywork. Review the source outlet and
target sockets against actual recovery hardware, then check native rope ends
against the live rigid-body transform. Do not infer fitting from offset signs,
validity, height, or a single side pull. Source and target arrays have separate
roles; the SDK may duplicate source points during generation.

`winch_fit_20261001_01/hardware_fit.json` measures the existing front fairlead
outlet at artist `(-0.006,-2.897,0.595)` and rear welded-loop centres at
`(-0.373568,2.722,0.677857)` and `(0.354112,2.722,0.677857)`. The rear tow ball is
excluded. Fit-marker renders retain the unchanged Blender geometry; all eleven
gameplay classes receive the same reviewed arrays. The project-specific fit
checker verifies both rear 120-vertex loops and the front opening region.
Universal hardware-coordinate bounds remain inappropriate: other artwork and
rigid-body frames require their own references. Retail/owner review stays open.


### Recovery hardware on a moving secondary body

**Authoring + prior Game frames, Roamer 2026-10-01:** the front bullbar and rear
bar meshes are entirely weighted to `BoneBody_cdt`, not the primary chassis.
The matched Blender body head is `(0,0,0.878)` and its native rigid-body basis
has the same axis orientation as the chassis. The body has a separate 895 kg
physics body and a spring hinge limited to +/-2 degrees. A chassis-relative
point can fit at rest and still drift away from the hardware under load.

`winch_fit_20261001_02` supersedes the earlier chassis-only fit candidate. The
front/rear points use `BoneBody_cdt` and offsets relative to that body's head:
front `(-0.006,2.897,0.283)`, rear `(-0.373568,-2.722,0.200143)` and
`(0.354112,-2.722,0.200143)`. The side points retain their original chassis
binding. General rule: check the hardware's actual bone/rigid-body weights and
subtract the chosen body's origin before converting the point into its native
local basis. Do not add a body height to a chassis offset or copy a universal
axis/sign rule. Evidence: body_frames.json, geometry_inspection.json,
hardware_fit.json (all vertices/weights and artist-offset round trip), original
native candidate02 settled_rest body frames, and unchanged native markup.
The project-specific native judge checks the selected body's transform and
uses chassis translation, rather than secondary-body hinge motion, as proof
that winching moved the truck. Retail review remains open.

## Native markup prismatic axis versus explicit IK axis (KGS25, 2026-10-02)

**Game / SDK:** native tpl_markup_constraint_prismatic slides on its local Z
axis. KGS25 childRotation [0,-90,0] made the middle telescope move sideways
along native -X: position 1.5 m produced local displacement
[-1.499968,0.41999,7.29000] instead of [0,0.42,8.79], leaving a 2.121 m
attachment error. Identity childRotation aligns this authored boom's native +Z
longitudinal direction. The visual IK constraint explicitly supplies vAxis;
its [1,0,0] is a separate bone-space setting. Do not copy it blindly into
native physics markup orientation.

After native reimport and native-build-007, the fresh repaired05 test reached
4.4998 m and 3.9998 m on the two stages. Crane and fixed track-frame attachment
errors stayed below 3.6 mm through full extension and slewing. Native UI crane
control (hold left mouse + HUD R) also raised the boom from -0.000752 rad to
0.312014 rad; physical/solved effector positions differed by about 8 mm.

Evidence: reports/runtime/repaired04/crane/mid_extended.json (failed),
reports/runtime/repaired05/crane/result.json, after_ui_raise_r.json and
ui_ik_read.json, native-build-007 / build-run-008. This establishes the axis
for this native markup type and rig, not a generic requirement for all rigs.
Retail save/load and payload lifting remain separate acceptance checks.


## Sequential native stabilizers and ground-limited completion (KGS25, 2026-10-02)

**SDK / native editor:** native anchors need enabled anchorsSettings, the crane's
isAnchorsEnabled flag and a TOGGLE_CRANE_ANCHORS action. Each anchor's ordered
constraint list opens the beam before lowering its foot, and closes in reverse.
The native no-collision controller makes the foot bodies phantom while stowed;
the actual pads still collide with the world when deployed. KGS25 uses local-Z
markup prisms rotated [0, +90/-90, 0] for outward beams and [90,0,0] for
downward feet. Fresh body-frame measurements verified their direction.

The stock prop_truck_anchors_controller.prop has a 0.01 m positional completion
tolerance. KGS25's 0.40 m foot command grounded all four feet, but they stopped
near 0.379 m, leaving IsAnchorsOpened false and the action still running. A
bounded live trial at 0.37 m reached native completion; a new build and fresh
spawn then verified full deployment, ground contact and retraction. Fit stroke
to the model and settled stance instead of weakening the global tolerance.
Terrain height variation and payload lifting need their own acceptance checks.

Evidence: references/prop_truck_anchors_controller.prop and .ssc,
runtime/supports02/supports/result.json (failed), stroke37_after.json (trial),
native-build-009 / build-run-010 and reports/runtime/supports-review.json.
KGS25's existing recipe validator checks four synced anchors, prism directions,
matching strokes, ground plate binding and stowed clearance. Completion and
contact require the project's measured native test; no universal stroke is added.

