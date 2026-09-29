# Visual IK rigs

Visual-only linkages (arms, cylinders, rods) are `ikSettings.chains` entries in the truck BRO. They
move bones of the body model so that a chain's end reaches its effector; they carry no physics.

```text
ikSettings = {
   useNamedChains = True
   chains = {
      IK_armupper_FL = {
         ikChainBodies = [ "BoneChassis_cdt", "Bone_IK_armupper_FL_Base", "Bone_IK_armupper_FL_Rod" ]
         ikConstraints = [ { vAxis = [ 0, 0, 1 ] }, { vAxis = [ 0, 0, 1 ] } ]
         effectors = [ { bodyPhysName = "BoneWheelFrontLeft", bodyIKName = "Bone_IK_armupper_FL_Rod" } ]
         __type = "physIK_CHAIN"
      }
   }
   __type = "IkVisualSettings"
}
```

| Rule | Grade |
|---|---|
| `ikChainBodies[0]` is the chain's base (a rigid body or any bone that moves, e.g. a rack or axle frame); the rest are the chain's bones in order, each the parent of the next | Retail, Build |
| One `ikConstraints` entry per chain bone: a hinge about the bone's local axis `vAxis` (no `type`, or `HINGE`), `HINGE2` (two rotations about axes perpendicular to `vAxis`), `PRISMATIC` (slide along `vAxis`, `min` / `max` in metres) | Retail |
| The effector pins the chain's last bone (`bodyIKName`) to `bodyPhysName` at their **rest offset, held in the effector's frame**: the ZiKZ pins wishbone ends 0.44 m inboard and 0.2 m above its wheel slots | Retail |
| Effectors in retail: rigid bodies (370), other bones such as axle frames and steering joints (559), wheel slots (202, only with the axle controller or under a moving body), IK bones of other chains (69) | Retail |
| An effector must itself move for the chain to move: a wheel slot needs the axle controller (see suspension-and-wheels.md) | Game (buggy, Warthog) |
| Retail lists some chains before the chains they pin to (Crayfish harvester) and they work; listing dependencies first costs nothing | Retail |
| Every retail truck sets `useNamedChains = True` | Retail |
| Offset `offsetIk = [length, 0, 0]` on an effector reaches along the IK bone's X (two-bar linkages of the stock loader) | Retail; used on the 994 loader, awaiting a drive |

## Bone frames for chains

A Blender bone exports with native local X = the bone's X axis, native Y = its roll axis (Z in
Blender bone space) and native Z = minus its direction (head -> tail). So build each chain bone with:

| Chain kind | Local X | Local Z (the hinge for `vAxis [0,0,1]`) | Constraints |
|---|---|---|---|
| Wishbone, lower arm + upright | along the part toward its outer end, projected off the pivot line | exactly along the pivot line (longitudinal for wishbones) | hinge, hinge (, hinge) |
| Damper, coil-over, driveshaft | along the part, base -> end | close to the axis it swings about | hinge + `PRISMATIC [1,0,0]` |
| Hydraulic cylinder | along the cylinder, barrel pin -> rod eye | any perpendicular | `HINGE2 [1,0,0]` + `PRISMATIC [1,0,0]` |
| Tie rod | along the rod | any perpendicular | `HINGE2 [1,0,0]` + short `PRISMATIC` |

Grades: bone-frame mapping Build (decoded from compiled models); cylinder pattern Game (16M3 grader:
the blade lift cylinders followed the blade); wishbone patterns Retail (ZiKZ 605E), awaiting a drive
on the buggy.

## Patterns

**Double wishbone** (ZiKZ 605E): upper wishbone = 2 bones from the inner pivot to the upper ball
joint; lower wishbone + upright = 3 bones (inner pivot -> lower ball joint -> upper ball joint);
both pinned to the wheel slot at the upper ball joint. The upright bone connects the two ball joints.

**Coil-over on a wishbone**: base on the chassis at the top mount, end at the lower mount; the effector
is the wishbone's IK bone (it moves in proportion to the wheel), not the slot.

**Driveshaft**: base at the differential output, end at the hub on the wheel axis, pinned to the slot.

**Rocker / Z-bar linkage** (stock loader): two-bar chain, first constraint without type, second
`HINGE`, effector `offsetIk` to the far end of the link.

**Split springs**: a coil stretched between two moving parts is split into an upper and a lower half
on the two ends' bones, overlapping enough to stay closed at full extension (the telescoping halves
show as a spring compressing).

## Things that did not work

- A follower chain pinned to an unmoved wheel slot at zero offset, with the whole linkage hung off
  it: nothing moved, because the slot never moved (Game, buggy v2).
- Knuckles as children of wheel slots and offset pins to slots without an axle controller (Game,
  buggy v1: one side's knuckles ended outside the wheels).
