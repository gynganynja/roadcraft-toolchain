# Suspension and wheels

## Wheel slots

A wheel is a `wheelSlots` entry in the truck BRO (`truckSettings.wheelSlots`) whose `geomName` is a
joint (bone) in the body model. The wheel model itself is a separate model (`wheelPool` ->
`EditableWheel` -> wheel class -> wheel BRO -> wheel `.tpl`), placed by the game at the slot.

| Rule | Grade |
|---|---|
| The wheel sits with its centre on the slot joint as modelled; model the vehicle at its intended stance with the tyres touching z = 0 | Build, Game |
| Wheel BRO `truckWheel.radius = 1` with `width` and `rimRadius` as fractions of the radius; `wheelPool.<name>.scale` is the radius in metres (the generated wheel scales both) | Build |
| Several `EditableWheel` entries may share one wheel class with different scales (front/rear sizes) | Game (Warthog) |
| Retail slot joints are oriented differently per vehicle: Armiger identity, ZiKZ 605E local X forward on both sides, SDK Lynx sample rotated per side (local Z inboard) | Retail |
| **With identity-oriented slots the game shows the wheel model unchanged on both sides.** A model authored with its outer face toward -X is right on the right side and inside-out on the left | Game (buggy, 2026-09-29: left wheels showed the brake disc face) |
| Therefore give each side its own wheel model: left model outer face +X, right model outer face -X (a half turn about the vertical keeps the tread direction), four `EditableWheel` entries | Build; awaiting a drive |
| The SDK documentation's "outer face -X" rule goes with its sample's per-side joint orientation | SDK, Retail |
| Keep one source wheel's tyre, rim and brake disc together in the wheel model; calipers belong to the hub, not the wheel | Build |

## The axle controller: what moves the slot joints

**Wheel slot joints only follow their wheels when an axle controller names them.** Without it every
visual part hung on or pinned to a slot stays where it was modelled while the wheel moves. Every
retail vehicle that pins IK to wheel slots has the controller. (Game: the Warthog's and the buggy's
first builds, and the Roamer 105 in the editor's play mode, whose slot bones never moved, not even as
steering joints; Retail: all 84 trucks with the block.) `lint-bro` code `RC010` / `RC031`.

```text
axleControllerSettings = {
   isEnabled = True
   independentAxleSettings = [ { frameName = "BoneWheelFrontLeft", isIndependent = True }, ... ]
   axleSettings = [ { frameName = "BoneAxleFront" } ]                    solid axles: an axle frame
   steeringRackSettings = [ { frameName = "BoneRack", rightWheelFrameName = "BoneKnuckleFR",
                              leftWheelFrameName = "BoneKnuckleFL", rackHalfLength = 0.772 } ]
   __type = "AxlesControllerSettings"
}
```

It compiles to `prop_truck_axles_controller { independentAxles [ { frame, singleWheelID = -1 } ],
steeringRacks [ { frame, rightWheelFrame, leftWheelFrame, rackHalfLength } ] }` (Build, matches the
retail ZiKZ class). A slot that hangs under another moving rigid body (a rocker) moves with that body
and needs no entry (Retail: ZiKZ rear axles).

### Steering joints and racks

| Rule | Grade |
|---|---|
| `customSteeringJointObjName` on a steered slot names an identity-oriented joint on the wheel axis at the kingpin (0.23-0.29 m inboard of the wheel centre in retail) | Retail (Armiger `BoneRackLeft/Right`, ZiKZ `r_rack_01`) |
| That joint hangs under the wheel slot (ZiKZ) or under a solid-axle frame (Armiger); `steeringRackSettings` names it as a rack wheel frame | Retail |
| `rackHalfLength` = lateral distance from the rack centre to the steering joints (ZiKZ 0.928 = its kingpin x) | Retail |
| Tie-rod chains pin to the steering joint (Armiger `SteeringRod` -> `BoneRackRight`); the ZiKZ bases its steering-rod chains on bones that move with the rack | Retail |
| The rack has no per-side (Ackermann) settings, only its frames and `rackHalfLength`, and the wheel slot has none either: expect the outer knuckle and the outer wheel to disagree at full lock (Roamer 105: 30 against 24 degrees) | SDK (type description), Game (Roamer 105, editor play mode) |
| Without a steering rack, hubs hung under slots as steering joints ended up outside the wheels on one side | Game (buggy); cause not isolated (Open) |

## Suspension values

A suspension axle is a `SuspensionAxle` in `truckSettings.suspensionCollection` (named items, each
slot picks one with `suspensionCollectionItem`) or in `suspensionSet` (front / rear).

| Rule | Grade |
|---|---|
| **`useSuspensionCollection = True` is required**: without it the generator drops the collection and compiles no `suspensionAxleCollection` | Build (class), Game (Warthog), Retail (all 41 retail collections set it; only the SDK samples do not) |
| With no suspension block the engine default is min 0, max 1 m, height 0, strength 0: the body rests on its bump stops and the wheels hang up to a metre when it lifts | SDK (type description), Game (Warthog) |
| Position is measured from the wheel's modelled place, + = lower (droop). `min` is the bump stop (negative), `max` the droop stop | Retail (every retail axle), Inferred |
| **`height` is the spring's neutral offset: a positive value raises the vehicle.** It is not the rest position; with height 0 the vehicle sinks by its whole static sag | Game (buggy sat low with height 0; Roamer 105 in the editor's play mode: the ride height followed height about 1:1) |
| Static sag is inversely proportional to `strength`: sag ~= share / (strength x beta), share = one wheel's fraction of the weight | Game (Roamer 105: sag ~ 1 / strength); that `strength` is relative to the vehicle's mass is Inferred (lowest scatter of three models over the retail scouts) |
| **beta is uncertain by a factor of about two.** The 4-wheel retail scouts under 6 t give a median of 58 *if they rest as modelled* (spread about +-40 %, log-sd 0.35). The one direct measurement gives about 105: the Roamer 105 (2.9 t) in the editor's play mode, front height 0.265 / strength 0.017 and rear 0.23 / 0.030, rested level 0.142 m above its modelled stance | Inferred (58, `roadcraft retail survey`), Game (105, `roadcraft suspension --calibrate`) |
| Retail designs often rest topped out on the droop stop (e.g. Armiger: rest above its max of -0.05) | Inferred |
| `damping` 0.12-0.25 on scouts; rigid axles use min = max = 0 with strength 0.25-1 | Retail |

### Designing an axle

```text
height   = sag + lift          lift: how much higher than modelled it should rest
min      = lift - bump         bump: travel up from rest
max      = lift + droop        droop: travel down from rest
strength = share / (sag x 58)
```

`roadcraft suspension --sag 0.16 --share 0.205 --lift 0.06 --bump 0.16 --droop 0.20` does this and
reports the rest and remaining travel at beta, at +-40 % and at the measured 105 (`measured`).

Design at 58, the default. If the truth is nearer 105 the vehicle rests higher and stiffer than
designed (the sag is about 0.55 of the design), which keeps it off its bump stops; designing at 105
when 58 is right would sink it by 1.8 times the design sag, the failure already seen on the buggy.
Check that the `measured` case still leaves droop travel. Keep the bump stop reachable at the soft
edge only if ground clearance allows it: clearance at rest minus bump travel should stay above
~0.1 m or the belly scrapes (Game, buggy).

### Calibrating from a drive

Measure where each axle rests in the game (a side screenshot: the wheel-to-arch gap against the
model's) and give every axle to the solver:

```text
roadcraft suspension --calibrate '[{"axle": {"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0221}, "rest": 0.12, "wheels": 2},
                                   {"axle": {"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0318}, "rest": 0.12, "wheels": 2}]'
```

`rest` is + when the body is higher than modelled. With every axle listed the weight shares come out
too (the Roamer's rests give beta 105.7, shares 0.221 front and 0.279 rear). An axle resting on a stop
is refused: it says nothing about its spring. Record each calibration here with its vehicle.

Weight share: with the centre of mass a distance `c` behind the front axle and wheelbase `L`, each
front wheel carries (1 - c / L) / 2 and each rear wheel (c / L) / 2.

### Retail scout values (for comparison)

| Vehicle | Mass (bodies) | Axle | min | max | height | strength | damping |
|---|---|---|---|---|---|---|---|
| Armiger Thunder scout | 1974 kg | Front / Rear | -0.42 | -0.05 | 0.275 / 0.295 | 0.016 / 0.018 | 0.16 |
| Don 71 | 1584 kg | Front / Rear | -0.28 | 0.45 | 0.15 | 0.015 / 0.02 | 0.15 |
| Minuteman K350 scout | 2800 kg | Front / Rear | -0.45 | -0.08 | 0.33 / 0.34 | 0.014 | 0.2 |
| Invictus Type A scout | 3600 kg | Front / Rear | -0.43 | 0 | 0.38 / 0.30 | 0.027 / 0.013 | 0.25 / 0.22 |

### Open

- beta: 58 (retail, assumed to rest as modelled) against about 105 (Roamer 105, measured). The buggy
  (`apb-axles-20260929`) and the Warthog (`wh12-axles-20260929`) were designed at 58; at 105 the buggy
  would rest about 0.13 m above its modelled stance instead of 0.06 and the Warthog about 0.07 m
  instead of 0, both stiffer than designed. Their next drives settle it (calibrate as above).
- The units of `strength` and `damping`, and whether `strength` really scales with the mass.
- Whether the steering rack also turns joints hung under an identity-oriented slot correctly on the
  right side (the buggy's v3 rig; awaiting a drive).

## Rig recipe for independent suspension (the retail ZiKZ 605E pattern)

1. Wheel slots as identity joints under the chassis at the wheel centres.
2. `axleControllerSettings.independentAxleSettings` for every slot.
3. Front: a steering joint per wheel under its slot at the kingpin; a rack bone at the steering rack;
   `steeringRackSettings` with `rackHalfLength` = kingpin x; `customSteeringJointObjName` on the slot.
   Rear: a plain hub joint under the slot. Hub / knuckle / caliper meshes on these joints.
4. IK chains pinned to the slot at their real points: upper wishbone (2 bones), lower wishbone +
   upright (3 bones, ending at the upper ball joint), dampers (hinge + prismatic), driveshafts. See
   [ik-visual-rigs.md](ik-visual-rigs.md).
5. Tie rods from the rack bone to the steering joint.
6. `lint-bro --class --tpl` before installing.

## Apoc buggy follow-up (2026-09-30)

The owner reported partial motion and detached parts after driving `apb-axles-20260929`.
The axle-controller presence checks passed, so presence alone does not validate attachment
or per-wheel response (**Game** symptom, **Build** checks). The follow-up candidate explicitly
sets `singleWheelID` to each slot's index, and removes the undocumented `isIndependent` field.
The mapping is supported by the SDK schema; improvement in this vehicle's runtime movement
remains **Open**. See the IK article for the independently verified reach/skin faults.

The repeated rear scraping report was not enough to establish spring bottoming as the sole
cause. A ray sample of the original rear hull showed collision in open space below the frame
and engine. The candidate decomposes the lower rear and retains two upper hulls, keeping the
existing suspension tune. Offline clearance checks include full bump and opposite-axle pitch,
with a 40 mm contact allowance. Terrain behavior still requires a drive.

## Apoc soft-flex revision (2026-09-30)

The owner reports stiff handling with the preceding linkage/collision candidate (**Game**).
The old 0.16 m design-sag tune is therefore not accepted as soft. Candidate
`apb-soft-flex-20260930` uses front/rear strengths 0.0126/0.0182, damping 0.085, stops
-0.18/+0.40 m and neutral height 0.36 m. Body angular damping decreases to 0.35.
These are authored **Build** settings, not measured runtime behavior.

The 0.28 m design sag plus 0.08 m lift keeps predicted rests off both stops at beta 34.8,
58, 81.2 and 105 (**Inferred**). There is no measured buggy rest height in this drive report,
so beta cannot be recalibrated honestly. The compact collision core excludes low rails and
side skirts to provide compression clearance. Full droop requires longer visual sliders
and coil overlap; recheck both endpoints after export. Softness, flex and terrain clearance
remain **Open** until the next drive.

## Apoc wheel-chatter damping trial (2026-09-30)

The owner drove `apb-mud-proxy-20260930` and reported rapid wheel chatter while the body
stayed fairly level (**Game**). The 0.085 damping inherited from the soft-flex tune is
therefore not accepted as controlled dynamic behavior. Reducing spring strength to obtain
compliance does not establish that damping should also be reduced; evaluate its transient
response separately (**Inferred**, supported by this report and retail comparison).

Candidate `apb-damping-20260930` changes only suspension damping: 0.085 to 0.16 front and
0.18 rear. Don 71 uses 0.15, Armiger scout 0.16 and Minuteman scout 0.20 (**Retail**, current
shipped BROs). The buggy retains strengths 0.0126/0.0182, stops -0.18/+0.40 m, height 0.36 m,
wheel-contact settings, compact CDT and corrected body mud volumes. More damping is intended
to settle wheel hop without removing slow articulation (**Inferred**). A static beta sweep
can verify rest margin but cannot validate chatter frequency, damping ratio or grip.
No measured buggy rest or dynamic trace was supplied, so beta is not recalibrated. Dynamic
improvement and handling acceptance remain **Open** until the next drive.
