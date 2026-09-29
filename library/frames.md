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
