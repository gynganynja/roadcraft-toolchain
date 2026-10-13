# Articulated (centre-pivot) steering

Wheel loaders, articulated dump trucks, graders, rollers and pick-and-carry cranes steer by turning one frame
against the other about a vertical king pin. Grades as in [README.md](README.md); hinge maths in
[frames.md](frames.md).

## How retail does it

| Rule | Grade |
|---|---|
| The articulation is a markup hinge (usually named `steering`) on the steered frame's body; the BRO lists it in `truckSettings.controllableSteeringConstraints` {constraintName, isAngular True, angularSpeed deg/s, minAngle, maxAngle}; the wheel slots keep `steeringAngle = 0` | Retail (Baikal 5916 +-60, Kronenwerk L34 +-28, Baikal 65206 ADT +-30, Forester +-30, MTK Proseka +-20, rollers +-25..30) |
| A third body between the frames carries the rear-frame oscillation: Baikal 5916 `BoneBody_cdt` -> `BoneJunction_cdt` (3 t, `steering`) -> `BoneCabin_cdt` (roll hinge +-9, spring 700 000 / damping 50 000); Forester `BoneRear_cdt` -> `BoneMiddle_cdt` (3 t, roll +-5) -> `BoneFront_cdt` (`steering`) | Retail |
| Each wheel slot names the frame it rides on in `parentFrame` | Retail |
| Steering rams are visual chains (hinge + prismatic) from one frame with the effector on the other | Retail (Baikal `IK_Junction_*_Piston`, Forester `IK_Rear_*`) |
| Sign: with identity bones and `childRotation [90,-90,0]` (axis native down) the BRO lists the **right-turn angle first** (`minAngle = +A`, `maxAngle = -A`) | Game (16M3 grader, driven by the owner) |

## Builds

* **16M3 grader** (2026-09-28): front frame on the rear chassis, +-20, plus front-wheel lean on the same input.
  Driven; articulation direction was right ([case-studies.md](case-studies.md)).
* **994 loader** (2026-09-29): `steering` +-40 at the measured pin, position motor tau 0.1 / 2e7; not driven.
* **Kanga 25 crane** (2026-10-10, Build; drive Open): rear (engine) frame root -> `BoneMiddle_cdt` (3 t, roll
  +-6, Baikal spring) -> `BoneFront_cdt` (`steering` +-30, `[90,-90,0]`, BRO min 30 / max -30, 30 deg/s; the asset's
  own rig said +-40, but its steering cylinders only stroke +-30); the crane
  stands on the front frame. Front wheels `parentFrame BoneFront_cdt`, rear `BoneRear_cdt`; solid axles follow
  their wheels through `axleControllerSettings.axleSettings` frames under each frame (Armiger pattern).
  The articulation and luff hoses are skinned between the two frames' bones (weights from the asset's skeletal FBX).
  Collision groups `truck` (rear, middle, front, tower, boom) and `crane` (front .. hook) disable contacts between the
  frames, so the hulls at the pin cannot jam the articulation.

Check at the model stage: the steering cylinders must stroke over +-A with the roll range applied (kanga25_mod
`tools/audit_rig.py`), and the boom/tail must clear the other frame at full lock.

## Steering feel (Kanga 25 c3, Measured on the editor bench)

Owner on c2: "twitchy". A stiff articulation motor (tau 0.3, damping 0.6, 3 MN) with `angularSpeed` 30 gave a
slalom yaw-rate sd of 0.33-0.35. Every slower, damped variant (`angularSpeed` 20; motor tau 0.5-0.7, damping 0.4-0.8,
0.2-1 MN, Baikal recovery velocities) cut it to 0.23-0.25. The soft Baikal motor (0.2 MN) let the joint wiggle at
launch (sd 0.6-3.6 mrad); 1 MN, damping 0.8 kept launch as calm as the stiff motor. Shipped c3: tau 0.5, damping 0.8,
1 MN, `angularSpeed` 20, suspension strength 0.08 / damping 0.95.

