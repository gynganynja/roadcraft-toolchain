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

A markup **ragdoll** (`tpl_markup_constraint_ragdoll`) twists about the constraint frame's **X** (Havok); the
retail whip antenna's `childRotation [0,0,90]` on an identity bone points it up. Use
`roadcraft.vehicle.ragdoll_child_rotation(axis_native)`. (Grade: Retail; Inferred, see secondary-physics.md.)

## Mass

| Rule | Grade |
|---|---|
| The engine starts from the volume centroid of a body's collision shapes; `hkCenterOfMassOffset` (native axes) is **added** to it | Build (D11T engine readout: centroid 2.261 - 1.15 = comLocal 1.111); Game (WALL-E editor bench: centroid 0.5448 + [0, -0.245, 0] = comLocal 0.2998) |
| `havokMassCenter = False` with `boneCenterOfMassOffset = [x, y, z]` sets the centre of mass **absolutely**, at that point of the body's native frame (from its bone); the form the SDK previewer script (`previewer_tpl.ssc`) switches on | Game (WALL-E bench: `[0, 0.30, 0]` read back as exactly 0, 0.30, 0) |
| `overrideCenterOfMass = True` changes nothing: `hkCenterOfMassOffset` is still added to the centroid (WALL-E: `[0, 0.30, 0]` gave 0.845 m and the robot fell over backwards). Read the result instead of trusting a form: the body's `GetCenterOfMassLocal()` and `GetMass()` through ExecSsl (physics-bench.md) | Game (WALL-E bench) |
| Wheels are not rigid bodies of the model; their mass is in the wheel BRO | Build |
| Keep masses falling along a linkage: each body carrying at most about 3.3 times its own mass (the Crayfish sample's joint block is 3000 kg in a 0.5 m cube, its bogies 2000 kg plates) | Build (16M3 grader, from the SDK sample) |
| Official defaults: angular damping 1.5, linear damping 0.01, restitution 0.01, mass set by hand | SDK (documentation). **Superseded 2026-10-13 as engine defaults** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, Q2 and F2): a markup body's per-key defaults are angularDamping 0.05, linearDamping 0, friction 0.5, restitution 0.4, massFromDensity true at 600 kg/m3; retail markups mostly set angularDamping 0.5, linearDamping 0.2, restitution 0-0.2 or leave it unset (crawlers). The wheeled mods' 0.01 is a mod convention. Body-vs-terrain restitution is 0 regardless (terrain restitution 0, geometric-mean combine) |
| Masses, centre-of-mass offsets and constraints are read from the `.tpl_markup` text when the vehicle loads; the compiled `.tpl` holds none of them, so changing them needs no model rebuild | Build, Game (KGS-25 fix 2 changed only markup and class text in the package) |
| Springs of wheels hung on a light body come out far softer than the vehicle-mass formula (KGS-25 track frames at 6 % of the mass: 25-40 times); keep wheel-carrying bodies heavy (retail track frames 7.5 t) | Game (editor bench); the scaling Inferred (tracked-vehicles.md). **Superseded 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3): the 25-40x figure came from a frozen bench run and code shows no mass scaling of `strength`. Heavy wheel-carrying bodies stay supported by KGS-25 fix 2 (Game) |

## Collision

Convex hulls made from the body's own vertices are the quickest good shape. A hull's bottom is the
lowest vertex in its region, so floor the region above small low protrusions (brackets, tube ends)
or the body will catch on terrain where the visible underside would not (Game, buggy).

## Locators, levels of detail, collision objects

| Rule | Grade |
|---|---|
| Locators (`_cockpit_camera`, `_third_person_camera`, `_equipment_camera`) and collision objects keep identity world orientation in the SDK Lynx `.blend` | SDK |
| Collision is convex `cdt_` objects only; the root `BoneChassis_cdt` at the origin; objects at scale 1 and rotation 0 | SDK (documentation) |
| Levels of detail are authored `<stem>_LOD0 .. _LODn`; the exporter drops `_LOD0`. Compiled naming can retain `<stem>` as the geometry group (Y61) rather than an explicitly named `<stem>_vis`; inspect the actual table and geometry report. Hide distances: 800 m vehicle, 350 m wheel; the LWI transition off for trucks | Build (EX5600), SDK |
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



## Absolute canonical bone heads and local mass centres (Dump Twuck revision 006, 2026-10-10)

**Build, offline rig convention:** revision 006 bone definitions store each rest head in absolute truck-space metres, even when the bone has a parent. For this convention, body-local centre equals fitted truck-space centre minus that body's own absolute head; reconstruct truck space by adding that head once. Do not add ancestor heads again. An exporter using parent-relative offsets would need a different conversion: verify the data convention before applying this rule.

The sand-cap example has absolute head `[0,6.58,4.5]` and local centre `[0,0,0.05]`, giving truck centre `[0,6.58,4.55]`; adding the dump bed head again would move its centre away from the actual artwork. Revision 006 explicitly stores `bodyHeadTruckSpace`, `targetCentreLocal` and `truckSpaceCentre` in `build/physics.json`, and the gameplay authoring audit checks their round trip. Axle-load moments use these fitted body centres plus the measured payload hull centroid, with empty/full cases kept separate.

Scope: this canonical rig and offline authoring output. The chosen mechanical-core mass distribution and suspension beta are design assumptions, not native measurements or proof that reported lean/bounce is cured. Evidence: Dump Twuck `tools/model_v6.py`, `tools/truck_bro.py`, `build/physics.json:massProperties`, and `reports/gameplay_v6_audit.json` (nativeTested=false).

## Compiled node conventions vs retail (Kanga 25 model audit, 2026-10-10)

Read with `roadcraft tpl-nodes` (pass known body parent pairs when it reports a tie). **Retail** (crane_truck_2_res and
a 117-vehicle survey of default_tpl_*.pak):

| Node | Retail | Toolchain mods before the fix |
|---|---|---|
| `cdt_*` collision pieces | child of their body bone, origin at the shape, the body's orientation (Baikal 81 of 81, Lada 3 of 3; a few retail trucks have some at the origin: Oshkosh M1070 21/42, Vostok TK53 7/26) | Kanga: all 27 at the model origin (vertices world-placed) |
| `sfx_exhaust_*`, `sfx_radiator_haze` | under the body (Baikal: an `sfx` group under BoneCabin_cdt), origin at the effect | skinned meshes at the model origin |
| wheel `_wheel` | native Z along the axle (+X in 139, -X in 2 of 142 shipped wheels), X = native -Z | identity (Kanga, Lada) |
| body bones | identity frames, 0.5-1.9 m up at frame height (Vostok TK53: root at 0) | identity; Kanga root at ground (0,0,0) |
| `cam_collision_shape*` | 87 of 117 vehicles | none (semantics Open) |
| collision data file | `tpl.tpl.resource cdt: <name>.cdt` | SDK pipeline writes `cdt: ''` for every mod (Open) |

**Why it matters (Retail, effect files):** `part_exhaust_big_cars_gas_mule_01` / `_neutral_01` emit from a
`local__geomPrimitive` plane at position [0,0,0] of their node, so an `sfx_exhaust_01` node at the model origin puts
that smoke on the ground; the face-based `local__parentArea` emitters were unaffected. The wheel BRO's VFX cylinders hang
on `_wheel` (bone = "_wheel") and are authored for the retail frame. **Build:** kanga25_mod `create_models.anchor()`
(origin at the shape, bone-parented, vertices unchanged) and `_wheel` rotated +90 deg about Blender Z (exports as the
retail frame exactly; checked with tpl-nodes); rig-audit check "Collision and effect helpers ... origin at their shape".
Drive effect of the collision origins: Open.


## Frame under a lowered body on unchanged axles (L275 v14, Claude, 2026-10-12)

**Build:** when a body is dropped over axles that keep their wheel centres (L275: cab -350 mm, tray -300 mm), a
straight ladder passes through the cab floor and tray. Fit the rail line to measured body clearances instead: under
the radiator, kick up over the front axle, drop under the cab floor, rise behind the cab to the tray bearers, and
place the kick where the cab's rear lip is not (measure it; L275's hangs to z 0.54). A leaf rear may need
spring-under-axle with notched rails when the tray leaves no room above the tube. Record these as adaptations, not
as the real vehicle's layout. Clash-check every design pose (bump, droop, cross-axle, lock, lock + bump) against the
installed body and wheels, not only the new parts (L275 `uc_check.py`).

## Recovered SnowRunner CombineXMesh bind poses (Jimny, 2026-10-05)



**Build:** the Zukterra Jimny's compiled CombineXMesh skinned positions cannot be treated as model-space positions. That put the steering wheel and running gear away from the body. Using the recovered submesh link palette, reconstruct each vertex as `sum(weight * boneWorld * linkMatrix * rawPosition) / sum(weight)` before applying the axis/ground conversion. The stored link matrix is mesh-to-bone here; inverting it was an unsuccessful trial. This is the observed Jimny layout, not a claim about every SnowRunner version.



The source coordinates are X longitudinal, Y vertical, Z lateral. Jimny's RoadCraft Blender conversion is `(Z, -X, Y - groundShift)`; its determinant is negative, so reverse triangle winding. The ground shift is 0.36421945 m for the selected BFG wheel (radius 0.43919055 m). Recompute surface normals after the geometry conversion. When several decoded weight slots refer to the same bone, sum those slots per vertex before calling Blender vertex-group `REPLACE`; repeated replacements discarded part of the chassis weights. After that repair, all 477 saved-source checks passed, and compiled wheel/camera positions matched the intended native coordinates.



Evidence: [C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005/tools/create_models.py](C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005/tools/create_models.py), `reports/debug_skin.txt`, `reports/source_manifest.json`, `reports/source_inspection.json` and `reports/validation.json` in the same Jimny workspace. The decoder reference is Brooen/Snowrunner-Model-Importer (MIT), preserved in Zukterra_Extracted_20261005. Runtime skin deformation remains **Open** until an in-game drive. A universal CombineXMesh validator is deferred because the stored bind-space convention has only been checked for this recovered model; the project's saved-source and compiled-frame checks are wired into its pinned test recipe.





## Verify exported axes before rotating a recovered chassis (Jimny, 2026-10-05)



**User request / Build:** the owner requested a check for a 90-degree chassis rotation. Jimny's compiled BoneChassis_cdt and both axle frames already had native X=(1,0,0), Y=(0,1,0), Z=(0,0,1). The recovered visual chassis meshes also had their longest extent along Blender Y; underside renders confirmed their longitudinal orientation. No global 90-degree rotation was needed. Inspect both the compiled basis and actual running-gear geometry: a zero position alone does not establish orientation, while unfamiliar Blender bone axes alone do not establish a fault.



The project's saved-source checks now assert chassis mesh extents; final validation asserts all nine chassis/axle basis vectors. It also samples 38,880 points in conservative wheel cylinders across +/-35-degree front steering and -0.30/0/+0.13 m travel against measured saved collision boxes, with no intersections. These are static checks, not loaded stance or terrain-contact proof. Evidence: Jimny_RoadCraft_20261005 reports/{polish_underside.png,source_inspection.json,validation.json}, polished-v3 package SHA-256 a1f4618358bc0fc71ba79260ae0449e8abf63c2dd4913c0f0c1af15f962ddef3. An identity-basis requirement stays project-specific because supported nonidentity vehicles exist.





## Roamer 105 ute compiled source and rigid frames (2026-10-05)



**Build, asset-specific:** recovering the owner's `roamer105ute_pc-jmvs.zip` with the MIT SnowRunner importer required a +90-degree X correction for the stored skinned mesh vertices before the ute's XY basis swap and 0.258 m vertical offset. The imported bone-world pivots already used the source skeleton basis and did not take that extra mesh correction. Applying one transform indiscriminately to both misplaced the suspension. This is a finding about this compiled ute/importer path, not a universal CombineXMesh rule; retain the Jimny bind-pose route above.



The visible chassis was already longitudinal (5.069 m along Blender Y versus 1.465 m across), while its inherited rigid-body basis was quarter-turned. Normalising only `BoneChassis_cdt` and `BoneBody_cdt`, restoring bone-parented world transforms and correcting body-local settings preserved existing visual vertices within 0.00000024 m. Native `tpl-nodes` then showed identity axes for both bodies. Evidence: project `Roamer105Ute_20261005`, `chassis_geometry_inspection.json`, `systems_polished.json`, `mechanical_polished.json` and `native_validation/compiled_frames.json`. Collision/handling acceptance remains Open.





### Recovered Y61 underbody and steering rest poses (2026-10-06)



**User report / Build:** the recovered Watcher Y61 chassis appeared rotated 90 degrees. Eight skinned nodes (chassis, suspension, knuckles, shocks and steering wheel) needed the same mesh-to-bone link reconstruction described above for Jimny: sum `weight * boneWorld * linkMatrix * rawPosition`, normalize, then convert axes. The first importer treated all skinned positions as model space. Y61's sampled chassis bounds were asymmetric and extended below ground; reconstruction makes it centred laterally. Corrections reached 1.25 m on chassis and 1.50 m on steering geometry. Restore original weight sums when repeated slots refer to one native bone. Preserve each asset's suspension-owned rest offset separately.



The Y61 conversion uses `(Z,-X,Y+groundShift)`; its steering pivot and axis derive from the recovered bone world matrix, with cockpit camera on the right-hand-drive side. Keep chassis root at ground zero when rebasing geometry for smaller tyres. Do not identify a copied hinge childRotation as the proven cause of a visible quarter-turn: it defines a constraint frame, while recovered mesh bindings can independently be wrong. Identity hinge markup is still subject to native verification.



Evidence: WatcherY61_35in_4in `reports/recovered_bind_audit.json`, `bind_repair.json`, tools/repair_bind_geometry.py and successful author-bind-repair job; original recovered CombineXMesh and before-state package retained. This establishes stored rest-pose reconstruction for these Y61 nodes. Native dynamics and the owner's revised drive remain Open.





**Build, Y61 2026-10-06:** final static validation initially falsely required `head_lights_vis`, but the native compiled table and obj_list.json contain literal `head_lights`, `head_lights_on` and the other lamp stems with geom=true and nonzero face counts. The controller graph uses those same stems. Correct the asset-specific check against actual native group names; do not weaken it to checking only a string in source markup. Successful build 20261005T174605Z-a21086bba2b5 and static test 20261005T175129Z-d69d4750944d pin package d2d0e01248ac951437ad97019a21e67e6317029e304a019671d12de16a27dc0b. This proves compiled presence, not live light switching.





### Y61 native body hinge limits (2026-10-06)



**SDK/Game, isolated Y61 editor:** a limited body hinge interval of one degree was rejected: the native phys_markup log reported `curr interval 1.000000, min interval 5.000000`. The final revision uses -3/+3 degrees with its existing spring/damping. Normal and harsh native driving loaded successfully; measured body twist stayed below 0.6 degrees on the flat pad. Do not use an invalid tiny hinge range to hide a recovered bind fault. Evidence: WatcherY61_35in_4in `native_tests/current/runs/current_normal_retry_normal_040508/engine_failure.log`; WatcherY61_Final `native_tests/final_canonical_result.json`, `hard_driving_result.json`. This is this SDK hinge validation and this rig's editor dynamics; owner campaign acceptance remains separate.





**Game, editor play mode Y61 final follow-up:** after the recovered bind correction and valid -3/+3-degree hinge, normal/harsh steering and reversing preserved chassis/body alignment. Native underside captures show longitudinal frame rails and attached running gear. Flat-pad body twist stayed below 0.6 degrees in those runs; terrain transition peaked at 1.18 degrees. Evidence: WatcherY61_Final `reports/native_captures/y61_final_polish_v2_underside.png`, `reports/native_physics_review.json` and final recovery captures. This provides the later editor dynamics evidence for the earlier Y61 bind entry; it does not establish the owner's retail drive.

### Axle-controller rest frames and fitted castings (Jimny, 2026-10-06)

**Game on preserved v6 / Build on v7 source; revised runtime Open:**
Jimny v6 authored axle bone centres near 0.300 m, while its native axle
controller placed those frames near the 0.3937 m wheel-centre height. A source
render cannot establish that a casting is aligned in native play. Simply
raising casting vertices while retaining the low axle bind would double the
correction at runtime. V7 authors axle rest bones at wheel-centre height and
fits recovered castings there; native captures must verify the result.

Evidence: preserved Jimny v6 final_all_092833/steer_left_visual_frames.json,
Jimny reports/suspension_source_inventory.json and tools/create_models.py.
This is a source/frame diagnostic, not a universal fixed offset for axles.
