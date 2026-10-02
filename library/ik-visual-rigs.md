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

**Historical split-spring workaround (rejected visually)**: the Apoc previously used overlapping
upper/lower coil halves on the endpoint bones. The overlap stayed closed in offline travel checks
(**Build**), but the owner reported two visibly sliding meshes on 2026-09-30 (**Game**). The earlier
claim that this looked like spring compression was unverified and contradicted by that drive.
Use a continuous skinned winding instead; see the continuous-coil section below (**Build**,
native appearance still **Open**).

## Things that did not work

- A follower chain pinned to an unmoved wheel slot at zero offset, with the whole linkage hung off
  it: nothing moved, because the slot never moved (Game, buggy v2).
- Knuckles as children of wheel slots and offset pins to slots without an axle controller (Game,
  buggy v1: one side's knuckles ended outside the wheels).

## Apoc buggy: reach and actual mesh attachment (2026-09-30)

The owner drove `apb-axles-20260929` and reported that some suspension pieces moved but were
not attached correctly, while others stayed still (**Game**). Adding an axle controller did
not establish that the complete rig worked. The earlier ZiKZ recipe remains **Retail** for
that vehicle; its direct transfer to the buggy was not validated.

The buggy's fixed upper arms cannot reach vertically displaced wheel targets: a geometric
sweep finds up to 157 mm of missing reach at its configured 260 mm droop (**Build**, analytical).
Its lower chain ended at the upper ball joint, while the visible upright stayed on the wheel
frame instead of the chain's middle bone. That does not guarantee that the lower arm meets the
visible lower joint. Link meshes entirely weighted to the hinge also ignore terminal sliding.

Candidate `apb-link-clearance-20260930` gives both arms their own ball-joint target, a hinge and
a prismatic endpoint. Link meshes use both bones; inner and outer fittings stay rigid while
central sections deform. The front damper follows the lower arm's outer fitting. Two-axis
damper pivots and sufficient coil overlap cover the sweep; tie rods need more than the old
120 mm extension at simultaneous full droop and steering lock. This is a visual adaptation
to native vertical wheel travel, not a rigid mechanical double-wishbone simulation.

Check reach throughout compression, droop and steering, skin weights after USF export,
and coil overlap. Analytical closure and a compiled rig pass are **Build**, not runtime proof;
this candidate still needs the owner's drive (**Open**).

## Continuous coil-over springs (Apoc, 2026-09-30)

Use one connected tube around a helix, with two-bone weights changing along the active
winding. Assign the same weight to every vertex of each wire cross-section: interpolating
by each surface vertex's height squashes the wire as well as the spring. Keep end turns
rigid on their respective seat bones, and blend only the active winding (**Build**, tested
in the Apoc offline rig and exported USF; native runtime acceptance **Open**).

Apoc uses eight turns (six active), 12 mm wire diameter, and three explicit LOD meshes.
The original coil bounds and fitted radius locate its seats and axis. The barrel and
end fittings retain their original rigid skins. The exposed piston has its own mesh;
its length spans the barrel mouth through travel while its radius stays constant. It is
not duplicated with the winding. Body and wheel controllable bone names remain unchanged.

Evaluate actual deformed vertices at compression, droop and diagonal articulation. Check
that the winding is a single closed component, its seat centres follow the correct bones,
its wire thickness remains constant and adjacent turns do not cross. Compare exported
geometry and skin weights with source at every LOD. These checks and an analytical IK
closure sweep do not execute the game's IK solver (**Build**, runtime remains **Open**).

## Exposed-piston inversion at extra compression (Apoc, 2026-09-30)

A connected coil and closed endpoints do not prove the separately skinned exposed piston
can compress farther. Record the original vertex sets at both axial ends and evaluate
their signed separation along the posed shock axis. A sorted bounding-box length can
hide an inverted segment (**Build**, Apoc check_motion.py). Retain the -0.18 wheel bump
stop: rear pistons have only 0.01657 m remaining, front 0.03946 m, at full compression.
The new check requires more than 0.01 m and covers all four detailed-LOD pistons at rest,
compression, extension and diagonal articulation. Pistons are omitted from this asset's
coarser LODs; do not assume every coil LOD includes a piston mesh.

Extra droop to +0.58 requires arm sliders up to 0.4369 m, spring sliders 0.5465 m,
rear shafts 0.3237 m and tie rods 0.3797 m with full steering. The authored limits cover
these values. This continues the game's vertical-wheel-path visual adaptation: central
wishbone geometry extends; it is not a rigid mechanical wishbone solver. The checks are
project-specific because endpoint meshes, axes and LOD omissions vary. Native motion
and appearance remain **Open**; offline renders do not establish drive acceptance.

## L275 front-end feedback and supplied texture update (2026-10-01)

**Game report / Build diagnosis:** L275 v4 owner showed a loose steering joint ahead of the bumper. Its drag-link chain listed chassis + Pitman + base + tip but only two constraints. Preserved v1 VisualFrames data already places the tip far ahead of its rest target; the earlier functional smoke pass did not establish linkage closure. Add the missing terminal HINGE2 and retain a native/owner check as Open. A survey of 1,208 installed retail chains found four two-bone cable chains with only one explicit constraint (two Dragline variants). Therefore shared `lint-bro` RC014 reports count differences as a **warning**, not a universal rejection; L275's project audit requires complete explicit counts for its own linkage. Two focused regression tests cover missing/extra, complete and empty chains; all ten BroLintTests passed. Existing vehicle_workflow source/compiled checks invoke the lint automatically.

Evidence: L275 revisions/front_end_v5/owner_bumper_detail.png, tools/ute_systems.py, reports/front_end_v5/retail_constraint_survey.json, shared_constraint_check.json and shared_lint_tests.log; prior runtime/native_v1/drive02/18_right_turn.json. No new runtime test or Mod Editor was launched for this correction.

## Crane movement-sound references after a donor conversion (KGS25, 2026-10-02)

**SDK / Build:** `BlueprintNodeOnCraneArrowPositionChanged` resolves `rootBodyName`,
`hookBodyName` and the named X/Y/Z/W constraints through `PropPhysSystem` during
blueprint initialization. Copying the TC305 sound graph into KGS25 retained
`BoneCabin_cdt`, `BoneCraneSeg2_cdt` and `cabin`, despite a successful native
generation/package build. Map these to the new rig (Turret, Tip and Slew in
KGS25) and inspect the generated class as well as the BRO. Successful packaging
does not validate these references or the movement sound in a running vehicle.

`lint-bro` RC045 checks explicit body references against a supplied compiled
TPL and explicit joint references when markup is available. Omitted/empty
fields are left to native inheritance. Both source and compiled blueprints are
checked by existing shared vehicle workflow stages. Tests preserve the stale
donor case and correctly renamed, omitted, unrelated-node and no-model cases.

Evidence: KGS25 `references/blueprint_node_on_crane_arrow_position_changed.ssc`,
TC305 donor BRO, initial `revisions/native-build-001/autogen_dw` and native
build receipt `20261002T003025Z-43b00a0d75ea`; `tools/patch_compiled.py` and
`tools/validate.py` audit the correction. Editor/retail testing was deferred by
the owner; no startup failure or sound-behavior acceptance is claimed.

## Preserve all child world transforms before freezing a source rig (KGS25, 2026-10-02)

**Build / Game report:** snapshot every mesh's world matrix before detaching or
baking any parent. A modifier operation refreshes Blender's dependency graph;
reading a child's world matrix afterwards can omit its original parent offset.
KGS25's candidate01 conversion placed its middle telescope at Z 0.115-0.685 m
instead of 3.025-3.595 m, and its hook below model ground. Correct bone pivots
and a successful native import did not detect the displaced mesh geometry.
The owner showed loose telescope/cable parts beside the crane cab. Verify
world-space geometry bounds and bindings as well as bone names and pivots.
Keep hidden piston/telescope overlap through the full intended stroke.

Evidence: KGS25 candidate01 ZIP, tools/create_models.py, the recorded geometry
inspection and native-build-004. The converter now snapshots all matrices and
checks the raw bounds before applying modifiers. The fixed model's telescope,
hook and piston bounds return to the original assembly. Final runtime motion
and retail save behavior remain separate from this geometry proof.


## Bind moving crane assemblies in every LOD (KGS25, 2026-10-02)

**Game report / Build diagnosis / native editor fix:** the owner reported that
the counterweight stayed fixed while the crane turned. KGS25's supplied
rear_box mesh had fallen through the converter's chassis-binding default.
Bind its complete assembly, collision body, rear lamp overlays and lamp
locators to BoneTurret_cdt in all three LODs. Check deformed vertices, rather
than relying on a rest screenshot. The corrected native build's 90/180-degree
slew captures confirm that the rear assembly turns with the upperworks.

This rig also needed clearance over a fixed cab during a half-turn: the rear
housing was refitted above the cab and connected with rotating sills. The
2.78 m floor and 0.70 height fit belong to this model, not to every crane.
Evidence: native-build-009 / build-run-010, tools/create_models.py,
reports/counterweight-articulation.json (all LODs) and
reports/runtime/supports-review.json. The project validator checks the
selected body binding, collision binding and fixed-cab clearance. A universal
counterweight-to-turret rule is premature because assembly names and native
body hierarchies differ. Retail saved-vehicle behavior remains open.

