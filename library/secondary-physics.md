# Secondary physics: swinging flaps, flags, antennas and hinged accessories

Parts that swing with the vehicle but must never move it: mudflaps, whip flags, antennas, tent flaps,
air fresheners, swing-out brackets. Retail does them all the same way.

## The retail pattern (Retail, read from the shipped `.tpl_markup` and compiled `.tpl` files, 2026-10-12)

| Rule | Evidence |
|---|---|
| Each swinging part is its own rigid-body bone (`Bone<Name>_cdt`) with one convex `cdt_*` shape under it; the shape gives the centroid and inertia, the mass is set by hand | cargo van, semi trucks, AI asphalt truck, semi tent |
| The body property carries `collisionLayer = "no_collision"` (nothing hits it, it hits nothing) | every retail mudguard, flap, wire, antenna, air freshener |
| The constraint carries `massFactor = 0`: the vehicle never feels the part | same |
| The bodies are listed in the model's collision group, but **not** in the BRO's `syncedBodyNames` / `propPhysSubstance` | Wayfarer ST7050 tent trailer (`syncedBodyNames` = the trailer only) |
| Nothing in the BRO or class is needed: the Lynx scout's mudguards appear only in the markup | `tuz_119lynx_scout_res` BRO and class |
| Some light parts are also named in BRO `constraintSolvingMethodSettings.constraintNames` (`prop_constraint_solving_method_changer` in 78 of 1126 retail classes: Sunshield_*, Mirror_L, KeyFobRing, Radiowire, ParfumeTree). Mudguards and the unnamed ragdoll antenna are not; what the changer does is **Open** | retail classes |
| Retail bones are identity-oriented at the pivot (mudguard at its top edge, antenna at its base) | `roadcraft tpl-nodes` on cargo_van, highway_semitruck_tent, ai_truck_asphalt_2cargo |

Retail values (spring motor `{spring, damping}`; units unmeasured):

| Part | Constraint | childRotation | Limits | Motor | Mass |
|---|---|---|---|---|---|
| Mudguard (cargo van, semis) | hinge, axis native X | [0,90,0] (right side [180,90,0]) | -60..24 / -60..60 | 0.5-1 / 0.05-0.1 | unset or 2 |
| Tent flap (semi tent) | hinge | [0,90,0] | 0..25 | 0 / 2 | 5 |
| Radio wire (AI asphalt) | hinge | [0,-90,0] | -35..0 | 30 / 0.3 | 0.5 |
| Whip antenna (AI asphalt) | ragdoll | [0,0,90] | cone 10, plane +-30, twist +-5 | `motors: [{motor: 60 / 0.1}]` | 2, `boneCenterOfMassOffset` half its length |
| Air freshener (semi tent) | ragdoll, no motor | [-90,90,0] on a tilted bone | cone 60, plane 0..45, twist +-0.1 | none | unset |

## Ragdoll axes

The SDK ragdoll is Havok's: the **twist axis is the constraint frame's X**, the plane axis its Y. On an
identity bone, `childRotation [0,0,90]` turns X onto native up, which is what the retail whip antenna
uses (Retail; Inferred from the antenna's identity base bone and Havok's atom order, not measured in
game). `roadcraft.vehicle.ragdoll_child_rotation(axis_native)` gives the rotation for any twist axis.
Ragdoll fields (meta): `coneAngle` 0-90, `planeMinAngle` -90-0, `planeMaxAngle` 0-90, `twistAngleMin/Max`,
`limitTau`, `motors` (each `{axis: ALL|TWIST|PLANE|CONE|..., motor}`).

## Making one (L275 v15, Build; not yet driven)

1. Bone: identity, head at the pivot, parented to the body it hangs from (chains: segment under segment).
2. Markup entry: body property `{collisionLayer: no_collision, massFromDensity: False, mass, angularDamping}`,
   one constraint `{name, target: parent, childRotation, massFactor: 0, limits, motor}`; add the bone to the
   model collision group. Hinge axis from `child_rotation`, ragdoll twist from `ragdoll_child_rotation`.
3. Shape: one small convex hull per body (thin parts: give the hull some thickness).
4. Skin: rigid parts to their bone; a bending part (whip pole, coil spring, flag) blended across the chain
   with linear weight ramps around each joint, so it bends instead of kinking.
5. Limits from a clearance sweep of the art about the joint axis against the static model (L275 reel:
   clear from -110 to +4 degrees; set -95..+3).
6. Gravity restores only hanging parts (flaps). A vertical-axis swivel or flag needs a spring motor to
   settle, and there is no air drag: raise the body's angular damping instead.

L275 v15 values (unmeasured, owner drives): reel swing hinge 13 kg, spring 25 / damping 3, -95..+3;
mudflaps 2 kg, 1 / 0.1, -25..60; whip pole ragdolls 1.0 kg 150 / 1 and 0.6 kg 40 / 0.5 (cone 12 / 10);
flag panel hinges 0.2 / 0.15 kg, 0.3 / 0.05 and 0.15 / 0.03, angular damping 2. Project:
`l275_minespec_mod/tools/secondary_physics.py`, `prepare.secondary_object_infos`, art `art/physics_v15`.

## Pitfalls

* A joined mesh with a fingerprinted UV patch (the L275 tray) cannot lose faces before the patch is applied:
  tag the faces to split (face attribute) before the join and split them off after the patch (Build, L275 v15).
* Spring units are not established. If the pole falls to its limit or the flaps never settle, measure
  before changing every value (physics-bench.md).
