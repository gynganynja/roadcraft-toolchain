# Trailers and towing

How the shipped game attaches trailers, and what a mod trailer can and cannot do. All static (base-game SSL,
retail classes/markups, the decompiled generator), 2026-10-14; no drive yet. Full references:
`C:\RC_RE\research\vehicle_ui_trailers_semantics.md` (Q2).

## Rules

| Rule | Grade |
|---|---|
| There is **no hitch, fifth-wheel or ball coupling** between two vehicles. The script layer can create only a rope (`ConstraintKeepDistance`, the winch), a rigid joint (`ConstraintFixed`, addons/cargo) or a breakable joint; nothing creates a ball or hinge between actors at runtime. Whether native code could is Open | Code |
| Every retail trailer is **part of one vehicle**: one BRO, one class, one model; the trailer is a jointed body in the markup and its wheels are ordinary wheel slots of the same truck. Lynx scout trailer, Malamute scout transport, ZiKZ 605E heavy transporter and mobile scalper, Wayfarer ST7050 trailers and gas semitrailer (their models include the tractor) | Retail |
| Such a trailer cannot be unhitched. It is bought, spawned, saved and recovered as one truck | Code, Retail |
| Vehicle-to-vehicle connection is the **winch**: a rope from the master's `winchSourcePoints` to the target's `winchSockets` (`prop_winchable`), length = the distance at attach. No auto-coupling: the player aims (axis `TRY_ATTACH_WINCH`). A socket qualifies within about `maxLength - 0.5` m of the master's root; candidates are searched within `1.5 x maxLength + 2` m | Code |
| **Towing** (`TOGGLE_TOWING` on the master) makes the winched truck drive itself after the master: `prop_towing` copies handbrake and gear, sets its own pedal from the speed difference (`velocityPedalControl`) and steers towards the master's point (`steerScaleByAngle`, `steeringThreshold`), with a stuck boost. The towed truck needs an engine and driven wheels; an unpowered one is only dragged on the rope | Code; Retail (113 classes carry `prop_towing`, 21 have the action) |
| The BRO `towing` block is the towing tuning. The `Chassis*` keys `towingSteeringTreshold`, `towingWinchLenghtToPull`, `towingPedalTreshold`, `towingPedalScale` are dropped by the generator (RC075) | Code ([bro-passthrough](bro-passthrough.md)) |
| A transporter carries vehicles by **linking**, not jointing: `prop_transporter_recovery` takes the trucks inside a box (`linkedAreaSize` at `trackerBone` + `posOffset`) along when the transporter is recovered or teleported. ZiKZ 605E: 5 x 15 x 11 m at `BoneFriction_cdt` | Code, Retail |

## The joint, from two retail trailers

A markup constraint joins its body to the explicit `target`, otherwise to the nearest markup body above it in the
model tree (physics-semantics, Code). The parents below come from `tpl_reader` (parent array guessed, Inferred
for intermediate nodes).

**Lowboy: ZiKZ 605E heavy transporter** (model `heavy_transporter_res`). Fifth wheel = a ragdoll on the trailer
body, parent `BoneChassis_cdt` (20 t):

```
BoneTrailer_cdt  ragdoll  parentRotation [0, 0, 0]  coneAngle 90  planeMinAngle -30  planeMaxAngle 20
                 twistAngleMin -3  twistAngleMax 3        mass 10000  hkCenterOfMassOffset [0, -0.62, 0]
                 friction 0.2  restitution 0
```

Class: 8 tractor slots (`editableWheel "truck_wheel"`, `torqueType "defaults"`, lateral force on); 10 trailer slots
`r/l_wheel_trailer_01..05` (`"semitrailer_wheel"`, no torque type, no lateral force, no `parentFrame`: the wheel
hangs on the nearest body above it). Ramps are hinges with position motors driven by a `CONSTRAINT_CHAIN` action;
bed = `prop_cargo_constraint`; `prop_transporter_recovery` as above.

**Drawbar trailer with dolly: TUZ 119 Lynx scout trailer** (model `tuz_119lynx_scout_trailer_res`). Chain
`BoneTruck_cdt` -> `BoneLink_cdt` -> `BoneCart_cdt` -> `BoneTrailer_cdt` -> `BoneTrailerRear_cdt`:

```
BoneLink_cdt        ragdoll  childRotation [0, 90, 0]  coneAngle 58  plane -45..45  twist -45..45  limitTau 0.8
                    motors [ spring 500, damping 50000 ]                          mass 300   (drawbar ball)
BoneCart_cdt        hinge    childRotation [0, 90, 0]  limited -60..60            mass 800   (dolly turntable)
BoneTrailer_cdt     hinge    childRotation [-90, 0, 0] limited -80..80            mass 3000
                    angularDamping 1.5  linearDamping 0.05  hkCenterOfMassOffset [0, -0.5, -3]
BoneTrailerRear_cdt hinge    limited -2..2  spring 950000  damping 15000          mass 2000
```

BRO slots: `wheel_trailer_front_*` on `BoneCart_cdt` (suspension item `Trailer2`), middle/rear on
`BoneTrailer_cdt` (item `Trailer`), all `editableWheel "TrailerWheel"`, `isEnableLateralForceOverride True`, no
`torqueType`. Winch sources include two on `BoneTrailer_cdt` at (+-0.396, -0.402, -6.208), so it can winch from
the trailer's tail. All bodies are listed in the markup's `collisionGroups.truck`.

The ST7050 semitrailer (`highway_semitruck_sideboard`) adds a 200 kg `no_collision` `FifthWheel_cdt` with a
spring hinge to the frame and a second hinge `target = "Trailer_cdt"`, closing the loop (Retail).

## What a mod trailer needs

- **Built-in trailer (the retail way):** model the trailer under the tractor in one model; give it a ragdoll
  (fifth wheel, or drawbar ball) or ragdoll + hinge (drawbar and dolly) in the markup; add its wheels as slots with
  `parentFrame` on the trailer bodies, their own suspension items and no torque; put every body in the `truck`
  collision group; add winch sources/sockets on the trailer if wanted. It is one truck for the store
  ([new-mod-creation](new-mod-creation.md) "The files a new truck needs"). Frames and hinge axes:
  [frames](frames.md), [articulated-steering](articulated-steering.md).
- **Separate towed vehicle:** a second complete, powered truck with `winchSockets` and a `towing` block; the
  master needs a winch, the `TRY_ATTACH_WINCH` / pull / detach controls and `TOGGLE_TOWING`. The link is a rope.
- **Detachable hitched trailer:** not possible with the shipped scripts (Code); native support is Open.
