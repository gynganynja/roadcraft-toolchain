# Physics report: the values the engine will use, and a donor comparison

A guessed physics parameter is often not the value the engine uses. When a key is absent, the engine
fills in its own default, the schema's default or a base class's value, and sometimes the field has
no effect at all. `roadcraft physics report` lists, for a built `.pak` or a mod source tree, the
effective value of every physics field the engine reads, with its source and evidence.
`roadcraft compare` puts a mod next to a retail donor truck (or another pak or tree), matched by
role, and adds the spread of each field over all retail trucks of the same kind. Both are read-only.
Code: `src/roadcraft/physics_report.py`. Tests: `tests/test_physics_report.py`.

Start here when a custom vehicle feels janky next to vanilla (a bouncy or jittering hull, odd
steering, sinking or skating tracks). Find the outliers first, change them towards the donor, and
then measure the change on the [physics bench](physics-bench.md) before installing it.

## Use

```text
roadcraft physics report <mod.pak | source tree> [--json] [--truck <text>] [--game-root <RoadCraft>]
roadcraft compare <mod.pak | source tree> --donor <"EPEC TC305" | other.pak | tree>
        [--json] [--fields softForceScale,friction.*.frictionValue] [--truck <text>] [--donor-truck <text>] [--all]
roadcraft physics inertia [--json [--rows]] [--cache <dir>] [--game-root <RoadCraft>]   (retail body inertia per role)
python -m roadcraft.physics_report report|compare ...        (the same commands, without the CLI wiring)
```

- **Inputs.** A source tree can be a `mods_source` folder, a staged project that contains one, or
  any folder laid out the same way. Only compiled classes are read (`ssl/**/*.cls`), with the model
  markup (`*.tpl_markup`, else `tpl/*.lods_base`) and the compiled model (`*.tpl`, for node positions).
  A tree with BRO files but no generated classes reports no trucks.
- **Which trucks.** Every class with `prop_truck_rb.wheelSlotWithDescs` is a truck, except
  preview classes. `--truck` filters them by path.
- **Donor names.** A donor name is matched to a retail truck by its words: `EPEC TC305` gives
  `epec_tc305_heavy_crane_new` and `Greenway HT500` gives `greenway_ht500_dozer_new`. Ties go to
  `_new`, then the shortest name.
- **Retail data.** The donor and the retail spread need the installed game (`--game-root`,
  `ROADCRAFT_GAME_ROOT` or the Steam path). Without it, a pak or tree donor still works, but no
  spread is shown, and schema defaults come from a built-in copy of the 2026-10-13 SDK schema.
- **Exit codes.** Both commands exit 0 whatever they find. Exit 2 means a tool error: an unreadable
  target, or no retail data for a donor given by name.
- **Run time.** A tracked comparison builds the 33 retail crawler reports in about 20 s, plus the
  time to hash the pak.

## Output

Every value is `{value, source, evidence}`, sometimes with a `note`. In the text form, the letter
after a value is its source:

| source | letter | meaning | evidence |
|---|---|---|---|
| explicit | E | set in this file | `file:keyPath` (`kgs25.pak!ssl/auto_kgs25_kgs25.cls:properties.prop_truck_track.tracks[0].section.height`) |
| inherited | I | set in a base class reached through `__type`; for a wheel slot's parent body, the nearest body above the slot in the model node tree | base file and keyPath, or the `.tpl` |
| engine-default | D | the engine's own value when the key is absent, confirmed from code | code address and the `physics_semantics.md` section |
| schema-default | S | the Mod Editor schema default (`roadcraft.schema`) | `schema <type>.<field>` |
| absent | - | not set, and no default applies (for example, a friction entry that is missing) | what is missing and what the engine then does |
| derived | ~ | computed here from other values | the inputs |

**Report.** For each truck, the report lists these entities:

- **truck:** drivetrain (`engine.*`, `gearbox.*` with the first, top, low-range and reverse gears),
  steering (`maxSteerSpeed`, `backSteerSpeed`, `pedalsResponsiveness`), the track-steering splines
  (`trackControls.*`), `softContactSettings.*`, `useFakeWheels`, and the physics step (60 Hz, 4 solver
  iterations, from editor.cfg).
- **bodies:** every markup physics body with all `tpl_markup_object_property_physics` fields and
  `effectiveMass`. It also gives the body's `joint.*`: the constraint to its parent, with limits and
  the motor's fields. Defaults are filled per missing key, and `joint.motor.ignoredKeys` lists keys
  the engine never reads, such as the D11's `spring` on a position motor. The heaviest root body is
  the **hull**. A non-hull body that carries track wheels is a **track frame**. Every body also gets
  the inertia fields (see "Body inertia" below).
- **axles:** each suspension axle a slot uses. This is either `axle[i]` from
  `suspensionAxleCollection`, or the `suspensionSet.front`/`.rear` fallback (rear only when
  `rearDiffers` and the slot `isRear`). Each axle lists all its fields and
  `travelRange = max - min`.
- **wheel classes** (`class:<pool key>`): every `prop_truck_wheel` field. The friction table is
  flattened as `friction.<surface>.<frictionValue|terrainDeformationFactor|substanceFriction|likeAsphalt>`
  over the nine retail surfaces and any extra surfaces the class has, plus `friction.entries`.
  Visual wheel classes are marked `visual` (no rigid body).
- **wheel slots** (`slot[i]`): class, side, `isRear`, `torqueType`, track membership (real or fake),
  `parentBody`, axle, and these derived values:
  - `physicalRadius` = radius - radiusOffset + section.height + extraPhysicalRadius;
  - `effectiveMass`: clamped to at least 0.1 kg, times `rearMassMultiplier` on rear slots;
  - `parentBodyMass`;
  - `massRatio` = wheel mass / parent body mass.
- **tracks:** `section.height` (0 means not tracked), `segmentLength`, `trackTensionDefault/Drive`,
  `parentTracker`, and the real, fake, physics and visual wheel counts.
- **derived:**
  - body, wheel and total mass, and the wheel share of the total;
  - physics wheels, in total and per track;
  - each track frame's share of the body mass (the RC047 measure in
    [tracked-vehicles.md](tracked-vehicles.md));
  - `trackWidth`: the left minus the right physics-wheel node X;
  - `boneOriginHeight` and its ratio to the track width (see Limits).

**Compare.** Roles are `truck`, `hull`, `track frame`, `track` (the first track),
`idler/drive wheel` and `contact wheel` (and their axles), `wheel` (wheeled vehicles), and
`derived`. A wheel class is a **contact wheel** if any track uses it as a fake wheel (`fakeWheelIds`).
Otherwise it is an **idler/drive wheel** (a belt-outline roller). An axle takes the role of the
track membership of most of its slots. When a role has several entities, all their distinct values
are listed (`0.55 | 0.75`).

The retail column is `min..max med [trucks with a value / trucks with the role]` for numbers. For
other values it is the count of distinct values and the most common one. The flags are:

| flag | meaning |
|---|---|
| `outside-retail` | a mod value is outside the retail min..max of that role and field |
| `missing` | the mod has no value, and every retail truck with that role has one |
| `absent-in-mod` | the mod has no value, but the donor has one (for example a friction entry such as `mud_sand`) |
| `unseen-in-retail` | a non-numeric value that no retail truck uses (for example a `fixed` track-frame joint; retail hinges them) |
| `differs` | the mod and donor values differ |

The text form prints three sections. The first is the outliers: every row flagged `outside-retail`,
`missing`, `absent-in-mod` or `unseen-in-retail`. The second is the key fields, printed even when
they are equal: wheel mass and mass ratio, the soft-contact and sideways-friction fields, friction
values and deformation per surface, section height, `parentTracker`, `trackTensionDefault`, the
track-steering splines, `joint.type`, axle `strength` and `damping`, and the masses. The third is
every other difference from the donor. `--all` prints every row, and `--fields` prints only the
fields that match. JSON (`--json`) always holds every row.

Name-valued fields (classes, bodies, axle ids, tpl names) get no retail spread. `parentTracker` is
compared by presence only. Keys the engine never reads (`gearbox.lowRangeMultiplier`,
`joint.motor.ignoredKeys`) are shown but never flagged.

## Body inertia

The engine derives a body's inertia from its cdt_ collision shapes and its mass, not from the mass alone
(physics_semantics.md Q2). A heavy body on a token shape is therefore free to twist: Mammoth RC68's 9 t
front wheel carriers sat on a 0.3 m cube (about 135 kg·m²), and the steering was "super janky", with a
front wheel almost rolling over (Game; suspension-and-wheels.md "First working series spring"). The
report estimates every body's inertia from its shapes, and validator rule RC080 flags outliers
(validator.md).

**Shapes.** The compiled `.tpl` holds a per-mesh bounds table (decoded 2026-10-14 on the RC68/RC69
models, whose boxes are known, and found in 2412 of 2415 retail models with a node table;
`tpl_reader.find_bounds`):

- a bitset of `ceil(nodes / 8)` bytes, bit i (LSB first) set when node i has a mesh;
- then one 89-byte record per set bit, in node order: `uint32 4`, one byte (mostly 0x0c), and 21
  `float32`: AABB min3 and max3, oriented-box origin3 (a corner), axes 3x3 (rows) and size3, all in
  the mesh node's own frame.

A body's shapes are the meshes named `cdt*` whose nearest markup body (itself or above it in the node
tree) is that body. When two parent-array candidates tie, the one that hangs the most cdt_ meshes
directly under markup bodies wins, then the one with more parents stored before their children (the
real array against its copy shifted by one entry). This resolved 7 retail models (the Aramatsu
harvesters and forwarder, the Baikal crane trucks, the Alces PL30C, the MTK 2006) and the kanga25 and
lada_niva mods, which before had no node tree in the report.

**Method.** Each shape is a solid box of its oriented size. The body mass is shared by volume, the box
tensors are summed about the shapes' centroid with the parallel-axis theorem, and the result is read on
the body bone's x/y/z axes. `hkCenterOfMassOffset` (added to the centroid) or, with `havokMassCenter =
False`, `boneCenterOfMassOffset` (from the bone) gives the centre of mass. That tensor moved to the
centre of mass is reported separately as `inertiaAboutCom.*`, and is **not** the value used: Havok keeps
the shapes' tensor when only the centre of mass moves (Inferred). RC68's carriers, with a 2.05 m COM
offset, behaved like their 135 kg·m² centroidal value, not like the 38,000 kg·m² the shifted reading
gives (Game). Boxes over-fill convex hulls, so the estimate is an upper bound on the shapes' own inertia.
Havok's `optimizeInertiasOfConstraintTree` (factor 1) may raise light chained bodies further (C). If a
markup body has an explicit inertia key, it is reported with source `explicit` instead. No retail markup
has one, and the research found no such field.

**Fields** (all `derived` unless explicit):

| field | meaning |
|---|---|
| `inertia.shapes`, `inertia.shapeVolume` | cdt_ meshes found and their box volume; the evidence says why when there are none |
| `inertia.x/y/z` | kg·m², about the body's axes through the shapes' centroid (absent mass: None) |
| `inertia.extent.x/y/z`, `inertia.extent` | extent of the boxes along each body axis, and the largest, L (m) |
| `inertiaPerMass.x/y/z`, `.min`, `.mid` | I/m (m²), the radius of gyration squared; `.mid` is the middle of the three |
| `inertiaRatio.x/y/z` | I/(m·L²), dimensionless (a solid cube gives 1/6) |
| `inertiaAboutCom.x/y/z`, `inertia.comFromCentroid` | the shifted reading and the COM offset length (see Method) |
| `wheels.count/.mass/.radius/.inertia` | the physics wheel slots whose `parentBody` is this body; `wheels.inertia` = sum of 0.5·m·r² |
| `inertiaToWheelInertia` | middle-axis body inertia / `wheels.inertia` |

Each body also carries `inertiaRole`. This is `hull`, `wheel carrier` (a non-hull body that wheel slots
hang on: a sprung carrier, an axle or a bogie body), `track frame`, `jointed body` (another non-root
body) or `other root`.

**Retail spread.** `roadcraft physics inertia` builds the spread of `inertiaPerMass.mid`,
`inertiaPerMass.min` and `inertiaToWheelInertia` per role (all masses and >= 1 t) over every retail truck
class. It takes about 40 s and is cached as JSON in `%LOCALAPPDATA%\roadcraft-toolchain\retail-cache`,
keyed by the retail paks' sizes and times (`--cache` to move it; never inside the game folder). On the
2026-10-14 install (124 classes, 1,840 bodies with shapes):

| role | n | `inertiaPerMass.mid` min / p5 / median (m²) | `inertiaToWheelInertia` min / median |
|---|---|---|---|
| hull | 115 | 0.072 / 1.06 / 2.69 | 6.5 / 76 |
| wheel carrier | 113 | 0.045 / 0.084 / 0.73 | 0.447 / 8.0 |
| track frame | 30 | 0.029 / 0.029 / 0.029 | 0.60 / 0.60 |
| jointed body, >= 1 t | 223 | 0.0067 / 0.029 / 0.58 | |

Mammoth RC68's front carriers give 0.015 m² and 0.018x, and RC69's 0.27 m² and 0.33x.

## Engine facts used (C:\RC_RE\research\physics_semantics.md, grade C unless noted)

- **Body defaults.** A body with a physics block but a missing key gets the value from the body
  constructor FUN_1430811e0. Restitution is 0.4, friction 0.5, angularDamping 0.05, linearDamping 0,
  `massFromDensity` True and density 600 kg/m^3 (F2a, Q2). A `massFromDensity` body weighs the
  density times its cdt_ convex volume (I).
- **Friction** (`prop_truck_friction_updater.ssc`, Q4):
  - With no `default` entry, the wheel's friction starts at 2.0.
  - A surface whose entry is missing keeps the previous surface's friction (it is sticky).
  - An entry without `frictionValue` uses 2.0 (the FrictionMaterial default).
  - An entry without `terrainDeformationFactor` uses 1.
- **Suspension.** `strength` and `damping` are the Havok soft-constraint tau and damping, with no
  mass scaling. Travel is measured from the bump stop, clamped to 0..max-min (T4, F3). The fake-wheel
  axle fields (`fakeStrength` and the fake damping fields) only matter with `useFakeWheels`, which
  no retail truck sets.
- **Tracks:**
  - The track section height is added to every track wheel's physical radius.
  - A height of 0 turns off track steering.
  - Fake wheels are full physics wheels.
  - `parentTracker` is the belt's reference frame (I).
  - `trackTension*` are probably visual (I) (T1, T2).
- **Track steering** (T3). When a spline is absent, the inner-track torque multiplier is 1 and
  there is no inner-track brake. Otherwise S0 below 0 brakes the inner track at velocity level.
- **Motors** (T5). Position and spring motors map 1:1 onto Havok motors. Keys a motor does not
  declare are never read.
- **Physics step** (Q7). 60 Hz and 4 iterations come from editor.cfg. No vehicle has its own value,
  and the retail game.cfg is unverified (U).

## Limits

- **No sag or spring rate.** The T4 sag law is withdrawn (F3). The report never predicts sag, rest
  height or natural frequency. Calibrate on the bench.
- **No mass for density bodies.** A `massFromDensity` body has no mass here. The `.tpl` bounds now tie
  a box to each mesh ("Body inertia"), but a box over-fills the convex hull, so its volume is not used
  for a mass. Body and total masses then carry the note "lower bound". Such a body still gets
  `inertiaPerMass`, but not `inertia`.
- **`boneOriginHeight` is not the centre of mass.** It is the mass-weighted height of the body bone
  origins and the wheel nodes, above the lowest wheel bottom. Havok puts a body's centre of mass at
  its hull centroid plus `hkCenterOfMassOffset`, and that centroid is not decoded. Compare it only
  between models built the same way. Retail values range from 0.27 to 1.40 m.
- **Laws not decompiled.** The soft-contact force law and the sideways-friction law are not
  decompiled, so their values are reported but not interpreted (T6, Q4).
- **The friction base table is not merged.** The `.prop` base table
  (`prop_truck_friction_updater.prop`: default 2.2, asphalt 3 likeAsphalt) is not merged into class
  tables. Q4 reads a missing `default` entry as 2.0. Whether the base table fills it is not proven.
- **Wheels without a `parentFrame`.** A wheel without a `parentFrame` hangs on the nearest body
  above it in the node tree. If the parent array of the model cannot be resolved, the parent body is
  `absent`. The KGS-25 model ties two candidate arrays, but its slots name `parentFrame`, so this
  does not matter there.
- **Retail spread.** The spread includes every retail truck class of the same kind, including the
  `base_` variants: 33 tracked and 91 wheeled on the 2026-10-13 install.

## Results on the owner's mods (Build/Retail, 2026-10-13)

Saved to `\\192.168.0.129\Downloads\roadcraft_laptop_research\compare\` as JSON and text.

**KGS-25 vs EPEC TC305, fixture build 5c4dd65d** ("feedback pass 2", from `roadcraft_fixtures`; the
build the desktop diffed). The tool reproduces each item of the desktop's offline diff:

- **Friction:** the contact wheel's friction is the 2.0 default (S) on every surface, against
  0.5-1.0 on the TC305. The KGS table has no `mud_sand` entry (`absent-in-mod`).
- **softForceScale:** 1 (S) against 0.75. This is outside the retail range 0.2-0.85.
- **Wheel masses:** 120 kg idler/drive wheels (outside the retail 200-1700) and 450 kg contact
  wheels, against 1700 kg.
- **terrainDeformationFactor:** 2.5 on grass and ground, against 0.2-0.5.
- **Track section height:** 0.07 against 0.2.
- **parentTracker:** set on the KGS, absent on the TC305.
- **trackTensionDefault:** 0.04 (S) against 0.045.
- **Track frames:** they are `fixed` (unseen in retail; retail hinges its 9 framed crawlers), with
  angular/linear damping 1.5/0.03 against 0.05/0 on every retail frame.
- **Steering splines:** identical to the TC305 in that build.

**KGS-25 installed build 93c5e889** (the candidate that copied the TC305 friction tables and
`softForceScale` 0.75, with S0(1) = -0.6):

- The friction and soft-contact differences are gone.
- What remains:
  - section height 0.07;
  - `parentTracker`;
  - `trackTensionDefault`;
  - 450 kg wheels (both roles) against 1700 kg;
  - contact-wheel radius 0.2 (outside the retail 0.208-0.494);
  - the fixed, damped track frames.
- The S0 spline `[0,1,0.5,0,1.005,-0.6]` is `unseen-in-retail`. This is the intended partial brake
  (T3 mitigation).

**Goliath D11 14b14597 vs Greenway HT500** (three truck variants; v1 and v3 have the same
outliers):

- **softForceScale:** 1 (S) on all wheels, against 0.55. Outside retail.
- **Engine torque:** 1300000 (v2: 3000000), against a retail maximum of 700000. v2 also has
  `brakesDelay` 0.15 against 0.5 on every retail truck, and a `slopeAngleFrictionMult` of 1.4 that
  no retail truck uses.
- **Track frames:** angular/linear damping 1.5/0.03 against 0.05/0. Spring-motor spring 15.6e6 and
  damping 17e6, above the HT500's 10e6 and 11e6, which are the retail maximum.
- **Contact-wheel friction:** sub_mud frictionValue 2.9 (retail maximum 2.2). sub_mud and mud_grass
  `terrainDeformationFactor` 1.25 (retail maximum 1).
- **Geometry:** `segmentLength` 0.366 and idler/drive radius 0.50-0.61, both above retail.
  `boneOriginHeight` 0.25 m against 1.30 m on the HT500 (a proxy; see Limits).
- **Matching the donor already:** wheel masses (200 and 600 kg), `parentTracker`,
  `trackTensionDefault`, sideways friction 0.1 and the steering splines.
