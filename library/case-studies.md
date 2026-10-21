# Case studies



Each mod built so far, what its drives showed and what that taught. Newest first. "Not driven"

means no report from the game yet: its rules are graded Build or Inferred, not Game. The owner

installs or approves each candidate, drives it in the retail game and reports what they see.



## Apocalypse Buggy (2026-09-29)



Source: one FBX mesh skinned to a Unity-style vehicle rig (upper/lower wishbones, hubs, coil-overs,

driveshafts, steering rods), centimetres tagged as inches, facing +X; textures without metal or

roughness maps. Tandem two-seater with a central steering wheel.



| Build | Report | Cause | Lesson |

|---|---|---|---|

| 1 `apb-first` | "The suspension is collapsed" (nose low in the screenshot) | `height` 0 read as the rest position (min -0.15, strength 0.014 / 0.016) | height is the spring's neutral offset; `roadcraft suspension` |

| 1 | "Brake calipers on the outside of one set of wheels"; "the suspension doesn't animate correctly" | left wheels showed the wheel model's inner face (identity slots show the model unchanged on both sides); right knuckles and arm ends hung under the slots were thrown outside the wheels; nothing drove the slots | per-side wheel models; see build 2 |

| 2 `apb-rig-soft` | "The suspension isn't rigged at all. It doesn't move with the wheels" | follower chains pinned to wheel slots that never move without the axle controller | wheel slot joints move only under `axleControllerSettings` |

| 2 | "Feels like there is a collision mesh underneath it" | soft springs ("super soft and flexxy", asked after build 1) bottomed the low belly; hull floors at the lowest parts | lift the rest, limit bump, floor the hulls |

| 3 `apb-axles` | not driven | the retail ZiKZ pattern: axle controller and steering rack, chains pinned to the slots, stance +6 cm, hull floor 0.26 m; designed at beta 58, so at the measured 105 it rests about 13 cm high | |



Also learned: lamps by the CAT method work (headlights lit in build 1's screenshot); `dataDashboard`

drives the steering wheel and gauges (direction not yet seen); the skinned source must be evaluated in

its rest pose.



## M12 Warthog (2026-09-29)



Sketchfab FBX, metric, already facing -Y; built from the SDK Lynx sample's settings; turret on an

endless hinge worked by the right mouse button.



| Build | Report | Cause | Lesson |

|---|---|---|---|

| 1 `wh12-first` | "The wheels turn almost instantly, wheels are always on the ground, even if body is 2m in air" | steering / pedal speeds unset (default 1); suspension collection dropped (no `useSuspensionCollection`) | never copy the Lynx sample's truck settings |

| 2 `wh12-suspension-steer` | not driven; by the buggy's evidence it sat low, and its left wheels showed their inner face | height 0; identity slots | as the buggy |

| 3 `wh12-wheels-sag` | not driven | height = sag 0.15, per-side wheels | |

| 4 `wh12-axles` | not driven | axle controller (its arms and springs had never moved) and `useNamedChains`; designed at beta 58, so at 105 it rests about 7 cm high | |



## 994 Wheel Loader (2026-09-29)



An earlier build by another agent turned the steering, lift and bucket joints about the machine's

long axis (a donor's `childRotation` values on differently oriented bones), and its tests only read

joint angles. The rebuild with the grader's pipeline confirmed the hinge rule on engine body frames

and joint angles, and that the converter takes its mip count from the descriptor template. Not driven.

Adding the `level` joint broke loaders bought under the earlier build (the dump names it: sell and

buy again). Its wheel model uses the old "outer face -X" rule with identity slots, so its left wheels

are probably inside-out; the owner had not noticed (symmetric rims).



## CAT 16M3 motor grader (2026-09-28)



Driven after every candidate. The owner knows real graders: walkways moved onto the tandems ("the

walkway on the tandems usually moves with the tandem"); the blade lift range opened to the modelled

cylinders' whole stroke; the two lift cylinders became separate controls at the owner's request.

Hydraulic cylinders are `HINGE2 + PRISMATIC` chains. Renaming the lift joints killed the

grader in the owner's save (found in the script crash dump): sell and buy again after joint changes.



## CAT 793D haul truck (2026-09)



Lamps: the ChangeMaterial approach never rendered; show/hide of lit copies worked in the campaign

(RC20) for the engine lamps and strobes; the native brake / reverse states did not, and RC21 moves

them to show/hide (not yet confirmed). RC21 also heaps the payload.



## Roamer 105 (2026-08 to 2026-09-14)



A port of an Expeditions crawler, installed into the owner's editor (Mod Editor play mode, not

retail), with a 15-case acceptance ledger and an autonomous test runner. Most drivetrain and

suspension measurements in this library come from it.



| Report or finding | Cause | Lesson |

|---|---|---|

| Suspension bottomed, tiny travel | its own collection's +-0.018 m range; the TUZ reference runs with no collection at all | compare with a working vehicle's compiled class |

| Links stretched up to 36 mm | rigid links against real travel | telescoping links (owner's choice over reduced travel) |

| "Steering too quick", tie rod swings | steer speed default 1 | 0.03 / 0.045 (the source mod's values) |

| "Too much power and geared too high" | invented torque table; gears from a vehicle with bigger wheels | scale torque by power-to-weight and gears by wheel radius |

| Rolled back on a ramp after a stop | `neutralGearSwitchingDelay` 3 | 60 |

| "When turning it feels like the wheels physically aren't where they are visually" | the rack has no Ackermann (outer knuckle 30 degrees, wheel 24) and it understeered 8-10 % | accepted as an engine limit |

| "Too dark", then "made of plastic" | 8 % luminance paint; roughness 0 spec | x1.6 paint, spec targets (textures-and-materials.md) |

| Every session crashed at scene load | shader permutation not shipped (LOD crossfade + vertex compression) | no crossfade |

| Suspension sweep | height moves the ride height 1:1; sag ~ 1 / strength | beta about 105 (suspension-and-wheels.md) |



The owner rejected a full acceptance suite after every change as too slow: the loop became quick

build -> the owner drives -> report, with sign-off evidence gathered only at milestones.



## CAT D11T dozer, Hitachi EX5600



The D11T is where the toolchain's identities, captures and source parity began, and where the

`hkCenterOfMassOffset` rule was read from the engine. The EX5600 (never driven) first wrote down the

hinge-axis rule, the generic `Truck` joint controls, and the exporter's LOD and UV traps.



## Apoc buggy partial suspension motion and rear scraping, 2026-09-30



Baseline `apb-axles-20260929` (package `7ef2f935717c0b7d...`) was the installed candidate.

Owner report: “some of them move with the wheel but dont appear attached correctly. others

dont move at all”, plus apparent rear ground scraping without visible contact.



The controller-only fix did not resolve the reported problem. Offline geometry found up to

157 mm of unreachable upper-arm travel, lower-arm/upright attachment mismatch, link meshes

weighted only to hinge bones, insufficient tie-rod extension at droop plus lock, and a rear

convex hull bridging open space. These findings supersede the earlier unverified diagnosis

that increased ride height and the controller alone would resolve the symptoms.



Repair candidate `apb-link-clearance-20260930`: independent arm endpoint chains with two-bone

skinning; corrected damper attachment/pivots and spring overlap; explicit per-wheel controller

indices; tie-rod extension; 20 rear collider pieces replacing one broad hull. Physics tuning

and controllable joint names are retained. The existing generated classes were updated only

in IK and axle-controller properties without launching an editor.



Evidence: authoring geometry, exported collider/skin checks, analytical motion sweep, schema

and package checks (**Build**). The analytical steering sweep assumes a centred rack. Native

solver response, actual scraping, handling and campaign acceptance remain **Open** until a

drive of this candidate.



## Apoc buggy softer suspension and compact collision, 2026-09-30



After `apb-link-clearance-20260930`, the owner said the buggy feels stiff, requested softer

suspension, smaller body CDT to avoid bellying out, and more flex (**Game** report).

That report does not establish whether every previous linkage symptom was resolved.



Candidate `apb-soft-flex-20260930` reduces spring strengths by about 43% and damping by

39%, increases wheel travel from 0.36 to 0.58 m, enlarges linkage slider ranges and coil

overlap, and replaces 22 body collision pieces with four narrower, shorter, raised core

hulls. Chassis angular damping changes from 1.5 to 0.35; mass and COM target are preserved.

The existing main and preview native classes receive the same suspension collection.

The source and previous package are retained for rollback.



Analytical sweep, exported skin/collision audit, schema, native class and package checks

are **Build** evidence. Beta-based rest estimates are **Inferred**. No new retail drive

or measured rest height has been recorded; handling and campaign acceptance remain **Open**.



## Apoc phantom mud patch after the soft-flex repair, 2026-09-30



The owner drove `apb-soft-flex-20260930` and reported mud deformation from nothing visible,

clarifying that it was a wide patch underneath the back of the buggy (**Game**). This does

not establish acceptance of suspension feel or all earlier linkage fixes.



Diagnosis found two copied body VFX boxes, `BoxCapsule` and `BoxCapsule3`, enabling mud with

systems=26. With the buggy's identity native chassis transform, their lower bounds were

Y=-2.354 and -2.0925 m; the second was entirely below the modelled ground. Previous collision

audits did not cover this independent effect geometry (**Build**, SDK flag definition).



Candidate `apb-mud-proxy-20260930` replaces donor body environment boxes with four inset core

boxes. All wheel classes, physical collision, suspension and linkage settings are preserved.

Only the main truck class's VFX property may differ in the final archive; the model assets

are pinned and reused. Compiled-volume audit, schema and package checks remain **Build**;

elimination of the observed rear patch awaits the next retail drive (**Open**).



## Apoc rapid wheel chatter after the mud-volume fix, 2026-09-30



Owner report on `apb-mud-proxy-20260930`: the wheels bounce rapidly over some terrain and

the vehicle feels like a shopping trolley; mostly the wheels chatter and the body remains

fairly level (**Game**). This report does not explicitly confirm the previous mud fix.



Candidate `apb-damping-20260930` is a bounded damping trial: front 0.16 and rear 0.18,

both previously 0.085. Comparable retail scouts use 0.15-0.20. Spring strength, ride height,

58 cm travel, wheel definitions, physical model and corrected terrain-effect volumes are

preserved. Only damping in the main/preview suspension arrays may change in the archive.

Underdamped wheel hop is a working diagnosis, not a measured runtime result (**Inferred**).

Compiled/schema/package checks are **Build**; settling over the reported terrain still

requires the owner's drive (**Open**).



## Apoc continuous spring animation, 2026-09-30



While `apb-damping-20260930` was installed, the owner reported that the springs look like

two sliding meshes and requested actual spring animation (**Game**). This does not confirm

whether the earlier wheel-chatter or rear mud-deformation fixes are accepted.



`apb-coil-animation-20260930` replaces overlapping coil halves with connected, round-wire

helices on all four corners, with continuous two-end skinning and three matching LODs.

One close-wound turn at each seat stays attached while six active turns change pitch.

The mixed-weight piston parts are separately classified and follow the moving barrel mouth.

The existing IK bones drive the deformation; no controllable joints are renamed or added.

Package comparison permits only the four compiled body-model resources to change from

the damping candidate. Classes, suspension settings, wheel models, physical markup and

terrain-effect settings remain byte-identical (**Build**). Offline rendered poses, actual

mesh deformation checks and export validation support authorship, not retail acceptance.

The owner's next drive must confirm native animation (**Open**).



## Apoc complete handling audit after persistent wheel jitter, 2026-09-30



Installed report: `apb-coil-animation-20260930`, SHA starting `50eed7ee5d0b` still has wheel

jitter and an unconvincing vehicle feel (**Game**). Coasting versus powered jitter is

unknown. The report rejects the damping trial as a demonstrated fix; it does not explicitly

accept spring visuals or the earlier mud fix.



The audit checks wheel dimensions, native wheel settings, all eight wheel classes,

slot/controller IDs, steering and brakes, axle indices, body mass/COM and load shares,

predicted rest margins, collision/core clearances, rig/coil export, other-mod overrides,

drivetrain scaling, package identity and schema. Runtime telemetry is unavailable.

`apb-handling-audit-20260930` applies the bounded contact/inertia/torque/damping trial

documented in suspension-and-wheels.md and enables SDK visual wheel stabilization.

Only ten native gameplay/preview class members change; all model resources, compact

collision and mud volumes are retained. Dynamic cause, grip and native wheel/hub alignment

remain **Open**, even when all static checks pass.



The project's former hard-coded checkout missed a newer machine-local toolchain selector.

The adapter now follows the selector and wires `vehicle_workflow.enhance_recipe` into builds

and tests. Preserved damping, mud and coil findings were merged into the maintained library.

The new shared compiled-wheel helper has seven focused tests; the existing vehicle-library

suite has 23 passing tests. A sandbox fixture-write failure was rerun with required access.



## Apoc crawl range with fast-trail suspension, 2026-09-30



The owner requested a super-flex rock crawler, then clarified that normal gears should

retain useful speed and the suspension should work like a trophy truck. This is a design

request, not a drive verdict on `apb-handling-audit-20260930` (SHA prefix 39113f994519).



`apb-crawl-trophy-20260930` retains the six normal gears, high/reverse gearing, torque,

wheel contact/inertia settings and selectable AWD/differential lock. Low-range angular

velocity changes 0.25 to 0.025, including low reverse; neutral delay changes 3 to 60 s,

using the existing Roamer evidence without claiming its speed transfers to this buggy.

Spring strength drops about 22%, travel increases 31% to 0.76 m, design bump/droop becomes

0.32/0.44 m, and damping stays 0.22/0.24. Actual ride height/speed and transient response

are unmeasured. The initial test incorrectly expected a gameplay gearbox controller on

the store preview; it was corrected to check each native class's actual role.



The bounded package diff permits exactly the main/preview vehicle classes to change:

spring max/height/strength, IK slider maxima, low-range speed, neutral delay and the main

class's rear-most environment-box bottom. All model/physical markup and wheel classes

remain identical to the handling candidate (**Build**). Source, compiled, final, schema,

rig, export, handling, clearance and piston/coil checks cover the authored contract.

The same spring tune serves both ranges; no mode-switched or progressive suspension was

invented. Runtime crawler grip, high-speed absorption, wheel chatter and campaign

acceptance remain **Open** pending an owner drive.





## Lada Niva exterior-first scout (2026-09-30)



**Build:** User supplied `lada-niva.zip`, containing an FBX with 106 mesh objects,

42,078 source vertices and eight PBR sets. Wheel-centre measurements gave a 2.010 m

wheelbase; a uniform scale to the manufacturer's 2.200 m reference preserved the art.

Fresh native sources split the four source wheels from the body, use separate left

and right wheel assets, and attach the rear axle to a dependent axle controller.

Three raised core collision shapes, explicit COM, permanent four-wheel drive, five

forward gears, low range and gradual steering/pedal values form the first drive tune.

Supplied exterior materials are retained; cockpit controls and comprehensive lamp

behavior are deferred.



Candidate `lnv-first-drive-20260930` passed 61 compiled/static vehicle checks and

757 retail export checks; see the mod's `reports/validation.json`,

`reports/retail_export.json`, `reports/source_inspection.json`, and pinned build/test

job receipts. These do not establish dynamic handling or retail campaign acceptance.

Runtime observations, when available, belong in separate pinned drive reports.





### Lada live-test follow-up (2026-09-30)



Candidate v1's static pass did not catch the missing deformable `tire` object;

its native crash report identified the exact fault. Candidate v2

(`9b79616246c5b606680d863424b2aea596da01e2574b1ce391fcfd1c6fd7a642`)

fixed the meshes and passed 63 static checks. A controlled flat-pad drive

verified acceleration, braking and steering; a separate positive-throttle

reverse case measured -3.280 m/s. The initial moving-start run left the pad

and is excluded from acceptance evidence.



V2 front travel near zero led to an isolated limits-only trial, -0.22/+0.12

instead of -0.09/+0.19. That trial passed 28 telemetry checks, including

parked start, forward/reverse, service brake, both steering directions,

wheel contact and suspension reserve. It climbed the 30-degree ramp from

Y60 to Y64 with all four contacts in each sample and stopped at the summit.

The final source incorporates those tested limits. Compare its rebuilt

native assets/classes with the tested fixture before associating the final

package with this evidence. No owner retail acceptance is implied.





### Lada retail rut feedback and collision revision (2026-09-30)



The owner rejected the driving feel of v3 on worked mud: mirrored left wheels, slow direction changes, excessive upper gears, and stationary wheel shake/float. Preserve the v3 pad/ramp evidence but narrow its scope. A new native baseline measured opposite left/right rim-frame signs despite identity slots, correcting the library’s previous universal per-side-asset rule. The revision replaces three boxes with 54 source-fitted convex sections, keeps all controllable rig IDs, corrects wheel handedness, shortens native shift delays and reduces upper gearing. Build/runtime/install identities and acceptance remain separate; see the Lada `revisions/rut_contact_v4` folder and subsequent pinned candidate receipts. No retail cure is inferred from the new geometry checks.





### Lada v4 native result and its limits (2026-09-30)



Candidate `lnv-rut-contact-20260930-v4`, SHA-256 `1a2b7adf522448ce23a72792b89132b3420ffe0fbc4c1a314c51eec3f8afefbb`, passed 74 static/package checks, 757 retail export checks and 20 native protocol checks. Sustained fifth-gear samples settled at 40.64 km/h; first and low-range definitions were retained. Eight stationary samples before and eight after crawling/steering on the native `mud` material showed identical wheel heights within each series, all four contacts and matching visual/physical centres. Low-range steering samples measured about 0.66 and 0.43 m/s. This is **Game (isolated editor)** evidence, not owner campaign acceptance. Terrain extrusion-depth samples were zero: the original deep dozer-worked ruts were not reproduced, so a cure there remains **Open**. Exact evidence: `package/candidates/lnv-rut-contact-20260930-v4/driving_result.json`, build job `20260930T023507Z-8aa22b87b394`, test job `20260930T023909Z-009a9b35dc90`. The first speed run hit a fixture obstacle and lost a report to a Windows file-sharing error; it is excluded. The late empty screenshot is also excluded. The in-game wheel screenshot is heavily shadowed; final outer-face verification combines native rim-frame measurements and separate lit master-wheel renders rather than claiming a clear runtime rim close-up.



### Lada v5/v6 exterior effects after the v4 drive (2026-09-30)



The owner called v4 much better, then requested smaller correct tracks, working

lights and exhaust at the real outlet. V5 retained handling, rig IDs and collision,

authored source-derived tread, reduced soil coefficients and added exterior SFX.

Build-006/test-007 passed 117 static checks, with six shared trail-helper tests.

An initial live launch correctly refused to overlap Roadcraft - Retail. Earlier

exact-name process inspection had missed that name; native generation now uses

the substring-based retail/editor gate and fails closed on process-query failure.



After the owner closed the game, v5 failed native Play startup. An isolated

inline-visibility correction restored it. That trial exposed overly white rear

emission and no visible stock parent-area exhaust plume. Normal State input

triggered brake/reverse events; physical Debug overrides alone did not. These

failures and the original crash are preserved in native_diagnostic_result.json.

V5 was never installed and is superseded, not accepted.



V6 applies the concrete visibility fix, red emission tint and fitted point-source

exhaust, retaining all 57 compared non-effects components from v4. Build-007

passed eight stages (resource-sharing generation retries were required), and

test-008 passed 121 static/package and 817 retail-export checks. Candidate

`lnv-exterior-20260930-v6` SHA-256:

`8b611c1223e8d1b75e18f4dfb5cd2287d426b1d82613956db2e86e740047c368`.



**Game (isolated native editor):** daylight captures show on/off head lenses,

red tails, white reverse strips and smoke at the fitted pipe. Probes confirm

engine on/off, reverse and brake blueprint transitions, forward motion and four

settled contacts. All 361 sealed fixture files matched after the run and the

owned editor closed cleanly. Evidence: v6 candidate effects_result.json with

capture/probe/fixture hashes; build job 20260930T055447Z-f0edc20d7ad3 and test job

20260930T060146Z-3c959e513e6f. The package receipt remains the immutable build-time

snapshot; effects_result holds subsequent runtime evidence.



Limits: no night beam-range review, no retail campaign run, no measured rut-depth

improvement or clearly isolated new tread capture. The mud ridge pre-existed and

extrusion queries were zero. isMod=false in the editor does not exercise retail

mod descriptor reset. Retain exact owner-rut comparison and full acceptance as

open. Local transaction receipts separately identify installation and v4 backup;

installation does not grant acceptance.



### Lada v7 scout utilities (2026-09-30)



The owner called v6 perfect, then requested objective/terrain scanners, functional

winch, front/rear recovery connections and exploration radar. Preserve that

positive v6 feedback separately from acceptance of new features. V7 fixes absent

native controls, configures the scanners and radar, and uses the existing fitted

recovery sockets. No rig or exterior changes were needed. Utility-only build-008

pins existing model/material/texture bytes, regenerates gameplay and packages it.



Candidate `lnv-utilities-20260930-v7`, SHA-256

`c4b1eafff4120b7a3e2bdfe2b66004acee12460d531ebda7459eac421ca7b342`,

passes 134 static/package checks and 817 export checks. The original build-time

package receipt records 133 checks; supplemental test-011 adds the wired shared

utility contract and pins current verifier sources. Seven shared utility tests

pass. V6 exterior/collision/tyre assets match byte for byte, and all non-utility

compiled gameplay properties match. Test-009's audit-only failure (wrong

replication name expectation) is retained; no vehicle payload change was needed.



**Game (isolated editor):** objective pulse and terrain marker overlay were

captured and reviewed. Front and rear pulls shortened cable by 2.89/3.15 m,

moved the truck by over 2 m, and had rope endpoints at the correct sockets.

The original scene-placed radar cached an empty level name; a fresh post-load

spawn completed its 15 s scan, consumed one token and changed fog sampled at

200 m from 0.227451 to zero. Test token balance returned to its initial zero.

All 361 fixture files matched the seal after the run and the owned editor exited

cleanly. Campaign save migration and multiplayer are not inferred from this.



Exact evidence: v7 candidate utilities_result.json and runtime/utilities_v7;

build job 20260930T064152Z-d802c3f67864, build-008/test-010/test-011 receipts.

Installation/backup are separate local transaction receipts; v7 owner acceptance

is pending. The v6 positive owner feedback is in revisions/utilities_v7/request.json.







## Lada v7 owner feedback and v8 interior authoring (2026-09-30)



The owner replied "Perfect" after v7 utilities and requested animated interior

and wipers. This is positive owner feedback, without separate per-feature or

multiplayer certification; accepted identity is not inferred from the install.

V8 adds visual bones and native cockpit/wiper controllers. Collision/COM and

all non-interior compiled gameplay properties remain equal to v7. Static checks

pass 169 assertions. The full texture rebuild emitted 217 changed BC7 bytes in

the UI icon; the exact prior compiled icon was restored from the sealed v7

fixture. Build-011 pins those assets through prepare/generate/package. A

package-only vehicle recipe was rejected by the workflow and not used.

Test-012's audit-path mistakes are retained; test-013 checks the actual packaged

model path and `.tpl` clip metadata. No missing clip payload was found.

Native animation evidence and installed identity are in the v8 candidate review.



### Lada v8 final cockpit and automatic wipers

Final candidate `lnv-interior-20260930-v8`, SHA-256
`7c87c66e8dd2f4bb6f95966ff8a939f5c3a072b5b63ced93e51ecc56ac4c277e`:
build-012 (job `20260930T081932Z-8049d6504eb0`) and test-014
(`20260930T082533Z-2f5a006b67c2`), 172 package/static checks, 817 export checks,
and seven shared cockpit contract tests. Build-011/test-013 above were the
preliminary package, not the final candidate. Final refinement calibrated RPM,
restored the accelerator's idle rest, held duplicate wiper boundary keys and
moved the first-person eye back/down. No physical or controllable joints changed.
Collision/COM, non-interior gameplay props and 374 checked assets outside the
body animation payload remained equal to v7. Generation's five transient sharing
failures before success remain in its receipt.

**Game (isolated native editor):** all nine cockpit controls responded to normal
input state, both rain-driven wipers moved in phase and parked exactly, and the
first-person/inspection captures were reviewed. Initial fresh-source launches,
including unchanged v7, failed during hot reload. Aggregate renaming, isolated
mod paths, omitted catalogs and UseJsonBrands did not fix the cause. The existing
Roamer timing finding led to the 110-second launch guard; the original fixture
and then final freshly copied fixture both worked without speculative edits.
All 362 sealed files matched after the final run; the owned editor exited zero.

Evidence: `runtime/interior_v8_settled` (preliminary calibration),
`runtime/interior_v8_final/review.json` (final exact package), v8
`interior_result.json`, and immutable build/test/package receipts. Separate local
transaction records retain the previous v7 bytes. Retail campaign/multiplayer
and final owner acceptance remain open. The generic BodyFrames helper's JOINT
postcondition rejected this joint-free rig; its failed report is excluded from
successful cockpit evidence. A first supplemental evidence assertion used exact
float equality for +/-126 degrees; measured 125.999985/-125.999969 requires a
small numerical tolerance, not a vehicle change.

## L275 mine ute: functional conversion and 79 proportion correction

2026-09-30. Source route: preserved fitted UV Blender -> native authored
Blender body/wheels -> official SDK TPL/BRO -> retail export. Source remains
byte-identical. The zero-weight import and glass-template fixes are described
in build-pipeline and textures-and-materials. A missing 12-file sample trail
dependency closure caused first package job 20260930T091227Z-3e46ea489971 to
fail; build-005/test-006 passed after closure.

First candidate l275-first-proportions-20260930-v1, SHA-256
1f78529e0c9e69b365c1899e54abb29cbb9b8dbaff7f546907663e26f770b5b1,
is preserved. Its 461-file isolated fixture seal still matches, and review.json
records 28 native smoke checks: selectable AWD/diff lock, driving/low range,
ground contacts, both motorized doors, both winch sockets and all scanners.
drive01's transient report-lock failure remains separate from successful
drive02. The owned editor closed; no campaign was installed or loaded.

The owner then reported the tray too short and cab too high for a realistic
two-inch-lift single-cab 79. V2 extends the deck 2.098 -> 2.500 m and lowers
cab/tray 350/300 mm, with frame, fittings, door pivots, collision and locators
refitted. Toyota roof/WB and primary tray-builder measurements ground the
correction. Source render roof estimate is 2.0042 m; actual revised native
height/handling remain open. A first refitted bonnet hull failed tyre clearance;
its preserved report led to selecting the upper source panels.

Final candidate l275-79-two-inch-20260930-v2, SHA-256
318c4c8658d8ff81f917dfbabbe1c38009b6083f359983e37888c5d495802faf,
passed full build-007 (20260930T101719Z-180f8706d667), test-008
(20260930T102325Z-8a339c6fb1f1), 102 static checks and 1156 retail export checks.
Native generation/import succeeded. The owner requested no more tests that
take focus before v2 runtime launch; only background file checks completed.
Do not silently reuse earlier launch authorization against that restriction.
No v2 runtime, retail save/multiplayer, installation or owner acceptance is
claimed. Project README and candidate receipts identify the exact tested scope.

## L275 Blender materials v3 (2026-09-30)

The owner authorized a complete Blender shader/game-texture pass with downloads,
and explicitly excluded Substance. The previous restriction against tests
that take focus persisted. V3 retains the corrected 2.50m tray and authored
two-inch 79 stance, adds editable procedural shaders, repacks tray/doors into
four atlases and bakes ten texture sets. Official Poly Haven CC0 metal/dirt
references and studio HDRI are pinned. Both shader and actual baked-map Blender
renders were reviewed, including independently open toolboxes. No interactive
game/editor test, installation or publication was performed.

The first granular white finish was refined to smoother powdercoat with small
edge wear. The initial normal-unit check failed and led to normalization in
export, with raw images preserved. First OptiX/cache and Blender-backup save
failures remain in the logs; the successful path is documented in the subject
articles. Source art and original Blender file remain byte-identical. The
editable four-Blender-file package includes 61 PNG bakes, 30 game TGAs, UV pins,
CC0 provenance and receipts; its ZIP is CRC-checked.

Final unaccepted candidate l275-blender-materials-20260930-v3, SHA-256
65194d745b8cfbc67a19652b6134758862228b621214a42bc876c0cf692caa34, passes build-009/test-010,
208 static checks (including 106 material checks) and
954 retail export checks. Compiled gameplay/physics comparison
is in reports/gameplay_preservation_v3.json. Runtime acceptance, revised loaded
height/subjective feel, retail saves and multiplayer remain open. Prior v1
native functionality evidence is preserved and is not promoted to v3 evidence.

## L275 final lighting and installation (2026-10-01)

The owner asked to finish the mod and specifically pointed out the Lada findings.
Review found the textured L275 lenses had no engine-linked lighting. V4 reused
the proven Lada light graph/state approach with L275-specific source lens fitting,
preserved UVs and concrete hidden visibility. All requested winch/scanners,
selectable 4WD/diff lock, low range, physical doors and the corrected two-inch
79 geometry remain unchanged. Only light blueprints/SFX differ from v3; collision,
mass, COM, pivots and bones remain equal. No interactive runtime test was launched.

Final candidate l275-complete-20261001-v4, SHA-256
75fcc09dbd60a4c23b133d4357e95210f8134adc6f8622473ec79fccc1d73996, passed build-011 (20260930T135227Z-07cb6248970d)
and test-013 (20260930T140235Z-699f6ae637d6): 253 static checks, 1018 export checks.
Test-012's package-role/PCT-path audit mistakes were corrected without altering
the package; failed evidence is preserved. Day/night Blender reviews use the
native bakes; the night scene is only a lighting approximation. The release ZIP
contains the PAK, control guide, credits/provenance and previews.

A separate Roamer visibility test was left intact until it exited. The first
install then hit a pre-swap Windows journal lock; recovery recorded NOT_INSTALLED
and a fresh transaction installed the exact package with previous absence retained.
The shared journal fix passed 20 focused tests and is documented in build-pipeline.
Installed identity is verified; accepted remains empty. Retail discovery, final
loaded stance/handling, saves, multiplayer and owner acceptance remain open.
Evidence: L275 reports/completion_v4.json, release_v4.json, install_v4_execution.json,
recovery_v4_execution.json, ui_preservation_v4.json and transaction_retry_patch_v4.json.

## Roamer 105 scout finish (2026-10-01)

**Build/Game:** `scout_20260930_01` refines the installed eleven-colour underbody-v3
reference with Lada utility controls, radius/replication fixes, functional 30 m winch,
more controlled damping, faster direction timers, restrained deformation/trails
and a 0.035 low governor. Mass, torque, spring/travel geometry, physical rig,
paint, texture, sound and catalog identities stay pinned. The official package
has 2498 unique resources, 143 reviewed changes and no additions/removals.

Candidate02 measured four contacts, forward/reverse/steer and 2.84 km/h low crawl;
the uninterrupted final 30-degree climb reached `(12.035,64.151,9.315)` on the
upper pad with four contacts. The first interrupted climb rolled backward while
a harness stopped on a duplicate Add-Type definition; preserve that failed trial
and use guaranteed parking in motion harnesses. All eleven finishes spawned.
Radar consumed one isolated token and cleared a 200 m fog sample. Winch pulling,
objective/terrain scans, explicit lamp states and automatic rain wipers passed.
All 2884 fixture files matched their pre-run seal; candidate02 editor exited zero.
Final03 separately verified the proper signed-pedal brake/reverse path. These are
private native-editor results; retail/owner acceptance remains open.

Evidence: package/build_manifest, package_audit, validation, durable source_inventory,
runtime/candidate02 and runtime/final03 within the campaign folder. The source
route preserves matched native Blender/USF plus reviewed compiled overlays;
blindly regenerating the historical BRO would lose subsequent colour/lighting work.

### Roamer final differential, bookkeeping recovery and installation

**Build/Game/installed transaction, 2026-10-01:** the final package is
`8a340adc5a3a47c77e4629758a7d93b82acdeccaa3a27526852d2595d5723263`.
The corrected copied-project bindings produce exact reviewed resource bytes.
Only the physical differential mode differs from the earlier native lamp/scanner
candidate; all eleven colours, lights, materials and existing rig are preserved.
All 145 static checks and the shared final vehicle lint pass. Final_diff04 checks
actual differential off/on, signed AUTO forward/reverse, low crawl and full steer,
with four contacts throughout. Its repeated recorder trial completed after the
established Windows report writer fix; the failed first trial is retained.

The package succeeded but job 008 failed on the stale output contract and
shadowed report name. That receipt remains failed. Both recovery lock releases
were separately approved and verified; shared recovery policy is unchanged.
Final test-009 passed. The source seal remains 2884/2884 unchanged, editor exit
zero, and installation transaction 3f53d85bf0294d3e998cab9d51ae87af verified the
live final hash and retained exact previous `4e023b...` bytes for rollback.
This establishes scoped native/editor and installed-byte evidence, not retail
campaign, multiplayer, physical controller or owner-driving acceptance.

Evidence: campaign/scout_20260930_01/native_final_review.json, package_audit,
source_inventory, reports/scout_package.json, both approved_lock_release reports,
jobs/20260930T231942Z-76b9e702aa27, jobs/20260930T233034Z-e1ac63bb23d7,
and the per-mod transaction receipt. See build-pipeline.md and truck-settings.md.



### Roamer owner-reported front/rear winch placement correction

**User observation + Authoring/Build, 2026-10-01:** the owner reported unrealistic
front/rear points after the scout installation. The previous native side pull
proved functioning, not hardware fit. Source inspection confirms stale inherited
coordinates inside the truck. `winch_fit_20261001_01` retains the earlier source,
package and receipts and fits one front outlet to the existing central fairlead,
two rear points to the welded rear-bar loops, and preserves the two side points.
The tow ball is excluded. Hardware fit and per-property/package parity are
separate from the native front/rear endpoint and pulling review. All other scout
features retain their reviewed bytes. Evidence: hardware_components, hardware_fit,
front_fit/rear_fit, build_manifest and package_audit in the correction campaign.


### Dump Twuck supplied-asset UV repair

**Authoring/Build, 2026-10-01:** the supplied RAR retained both tracked and
big-tire versions. The tire variant was selected and all originals pinned.
An initial bake using its bounded UVMap lost the source palette; a new packed
layout tied to the original vertex/loop fingerprint restored it. Superseded bakes
and failed build receipts are retained. Evidence: dumptwuck_mod source/manifest,
history/overlapping_source_uv, material_bakes, tools/bake_source.py, create_models.py
and source previews. This entry establishes authoring repair, not native drive
or campaign acceptance. See textures-and-materials.md for the reusable rule.


### Roamer secondary-body recovery anchors

**Authoring/Build, 2026-10-01:** matched hardware inspection found the bars on
the spring-mounted BoneBody, with origin Z=0.878. The earlier static chassis-only
fit candidate is retained and was never installed. The final correction campaign
winch_fit_20261001_02 uses the hardware body's local offsets for front/rear points
and retains the side bindings. Its geometry check verifies full BoneBody weights
and the inverse-origin offset round trip. The first short native startup trial
is retained as incomplete: two probes timed out during loading and no control
inputs ran. A body recipe initially still referenced the preceding adapter;
its assertion stopped before any native command or job lock. A corrected new
recipe preserves that failed preflight. Package/geometry and live endpoint/pull
evidence remain separate; no accepted entry or shared recovery-policy exception
was created.


### Dump Twuck load controller startup dependency

**SDK/Native startup, 2026-10-01:** build-007 passed native model/class compilation,
shared vehicle lint and 603 retail resource/catalog checks. Its first private
scene launch failed because PropLoadVolumeController requires PropRouteFollowing.
The exact tested PAK, generated classes, fixture identity and crash evidence remain
in history/runtime_001_failed. The correction enables the Truck BRO's
aiRouteFollowingSettings. Shared RC033 and four scoped regression cases catch this
dependency before later launches; compile evidence remains separate from native
drive and unloading results. See truck-settings.md.


### Roamer corrected recovery points delivered for owner testing

**Authoring/Build/Installed, 2026-10-01:** the final `winch_fit_20261001_02`
package `ed0cf96fbf15d97930b973711f8f15cb512e93a672c8ef017859b4061160d39c` is installed with its exact previous package backed up and
an installation receipt. All eleven gameplay colours use one front fairlead,
two rear recovery loops and two retained side points. The front/rear points
bind to the hardware's spring-mounted `BoneBody_cdt`; the tow ball is excluded.
Only the winch point arrays in eleven CLS resources changed from the previous
installed scout; every other resource and class property is exact. Official
native packaging, shared source/compiled/final lint, 145 static scout checks,
source inventory checks and geometry/weight/offset fit checks passed.

The owner explicitly chose to conduct the new in-game test. The final body-bound
fixture and live pull harness were prepared but not launched. The earlier
chassis-only candidate was never installed; its short startup trial applied no
inputs and remains incomplete. Earlier scout lamp, motion and utility evidence
is retained under its original package identity. It does not prove front/rear
live endpoint fit for this package. `nativeTested` and `retailAccepted` remain
false and `accepted` remains empty. Current delivery notes specify a fresh
spawn, front/rear cable origins and hardware tracking over uneven ground.
Evidence: final package_audit.json, validation.json, winch_validation.json,
hardware_fit.json, source_inventory.json, install_receipt.json and NOTES.md.


### Roamer window glass lightening for owner testing (2026-10-13)

**Player report / offline diagnosis / Build, 2026-10-13:** a saber.games comment
(Venk88, 1 October 2026) reported the windscreen "too dark, makes driving
impossible". Diagnosed from the frozen source of the installed winch-fit package
`ed0cf96f...` without launching the editor or the game. The compiled model binds the window
mesh `r105_mod_105_glass` (windscreen, side and rear glass) to
`roamer105_glass_glass_2_mod` on the outer preset and its cab-facing twin
`r105_cabin_glass_inner` to `roamer105_cabin_glass_inner_mod` on the inner preset;
both still used the Expeditions masters' constant maps, which under RoadCraft
semantics are a black film at alpha 0.92 (opacity) and a spec of metalness 0.5 /
occlusion 0.5. The candidate `campaign/glass_20261013_01` adds two 32 x 32
constants, `mod_roamer105_window_film` (51, 51, 51, 115) and
`mod_roamer105_window_spec` (8, 41, 216); the outer instance gets them with the
SDK Lynx filter [127, 155, 151] at density 1 on the unchanged `vehicle_glass_outer`
preset, the inner instance gets them on the unchanged `vehicle_glass_inner` preset.
The official packager's resource audit proves every other member is byte-identical
to the installed package, nothing was dropped and no instance links a missing texture.

Attempt 001 of the campaign changed `roamer105_glass2_glass_mod` as "the windscreen"
from its name; the object list shows it is the lamp covers (`r105_mod_105_lightglass`).
The packager then dropped the lamp spec texture nothing linked any more and the
exact-resource audit refused the package; the failed native step's job lock was
released with `jobs-recover` after the registry's candidate pins were converted to
package receipts and the scout transaction receipt was enumerated (the other
sessions' packager and furnace processes had to exit first). The player report
establishes the symptom only; whether the retail film convention is light enough
for this cab is open until the owner drives. Evidence: tools/glass_fit.py
(`check_bindings`), package_audit.json, validation.json,
history/attempt_001_lamp_glass_misassigned (and attempt_002: the audit first rejected links to shipped game textures), reports/glass_jobs_recover_applied_scoped.json. Installed 2026-10-13 as `be7cb530...` over `ed0cf96f...` with transaction receipt `transactions/a3d6bfdb623245519b2c48e3dea88469`.


### Roamer cut-off proxies hidden from the class init (2026-10-13)

**Build / installed, not driven:** a second candidate for the dark-windscreen report, on top of the glass
fix. The maintained validator's RC074 (engine code analysis) shows markup `objSettings` visibility is applied
only with `exportedVersion` >= 2; no Roamer or retail truck markup sets it, so the two cut-off volume proxies
(`r105_mod_105_windshield`, 624 faces, a materialless copy of the window mesh; `r105_mod_105_cockpit`, a cab box)
were probably rendered. `campaign/proxies_20261013_02` adds a `HideCutoffProxies` show/hide node fired from the
existing `OnInit_1` to the source overlay and the eleven colour classes; only those eleven class members changed
and `roadcraft validate --baseline` reported no new findings. Setting `exportedVersion` was rejected because it
would also switch on 27 collision and the lighting entries. Installed as `1224b0f8...`, transaction
`transactions/a3097eb54c4342bfb1ba8a3ae4ca5046`. Which of the two candidates (film or proxies) fixes the report,
and whether the cut-off volume still works, is open until the owner drives.


### Dump Twuck: native behavior passes before camera review

**Native private fixture, 2026-10-01:** build-010 passed 603 package checks,
130 static checks and 32 native behavior checks. Forward/reverse, braking,
front steering, low range, loaded tire contact/travel, 50-degree powered tipping,
native sand discharge, return-down and hydraulic closure (under 0.0002 m) worked.
Visual review then found the cockpit view showing the platform/railing rather
than the dash, and the donor chase preset framing poorly. The numerical pass and camera failure are
preserved together in history/build_010_behavior_pass_camera_failed; that
package was not sealed or accepted. The runtime test now checks the actual eye
against authored cab bounds. See cockpit-and-lamps.md, truck-settings.md and
symptoms.md for fixture readiness and sand-settlement corrections.

## L275 front-end feedback and supplied texture update (2026-10-01)

**L275 owner follow-up:** On 2026-10-01 the owner supplied retail screenshots rejecting v4 headlights and showing a protruding radiator and displaced steering end. The earlier 253 static/1,018 export checks proved package structure, not visual acceptance. V5 addresses radiator fitting, dedicated sealed-beam lenses and the missing drag-link constraint. The owner then supplied L275_roadcraft.blend and UV-fitted PBR exports, explicitly requested installation, prohibited Mod Editor, and reserved in-game testing for themselves. Preserve v4 package/receipts, the screenshot feedback, user texture sources and their exact fit reference. New source/typed-class/packaging checks remain Build evidence; do not transfer v1 functional runtime evidence or mark the replacement accepted.

Project evidence: revisions/front_end_v5/, reports/front_end_v5/, tools/audit_front_end.py, tools/patch_compiled_ik.py and the v5 candidate receipt. Shared integration adds conservative RC014 plus focused regressions and updates IK, symptoms, materials and build guidance.


### Dump Twuck final candidate: native behavior and camera pass

**Native private fixture, 2026-10-01:** final PAK 4b6aff7f549156f007566e4bde0122f004b998548d5337bb1fd20f749b1f4ea7 passed 603 retail export checks, 130 static checks, 159 saved-Blender checks and 34 native checks. The corrected cockpit eye measured [2.65, 6.20, 3.563] in native body coordinates and is inside the cab; a settled native screenshot shows dashboard, steering wheel and forward road. The chase view shows the whole truck after removing donor interest points and widening the orbit. Camera screenshots/review are pinned separately from numerical behavior. Source: dumptwuck_mod/reports/native_review.json, visual_review.json, build-012/test-011 job receipts and the sealed dtw-20261001-v1 candidate.

The initialization guard also waits for at least 120 simulation frames, six wheel contacts and chassis speed below 0.15 m/s, bounded by 45 seconds. The post-load frame-3 drop remains preserved rather than weakening contact checks. Final seeded load was 87.685 m3 before tipping and 0.382 m3 afterward; observed settled carrying volume depends on pose/settlement. Retail campaign/refill/save/multiplayer and recipient acceptance remain untested. At that original seal the candidate was unaccepted and uninstalled; later authorized installation led to the owner feedback recorded below. Original 21 source files pass direct verify --manifest; source-check intentionally requires an accepted authoring inventory, so its unavailable gate was not bypassed or called a pass.



### Dump Twuck owner camera/sand follow-up

**Owner report/native private fixture, 2026-10-01:** after installing v1 the
owner reported a misplaced driving camera and spilling sand with the tray down.
The earlier 34-check pass and whole-truck screenshot did not test load retention
or usable driving framing. Build-013's fixed rear border held the entire load
but only discharged 3.7 percent; it remains rejected. Native stock dynamic-lid
control, a separate hidden closing joint and powered states corrected discharge.
Build-014's model/preview/import stages passed but generation hit six resource
file-lock races. Subsequent builds hash-verify those recorded art outputs and
rerun preparation, shared source/compiled checks, native generation and package
export. Overall failure is not reused as generation or package success.

An intermediate dynamic-lid package passed 46 native checks but its high camera
focus cropped the vehicle. The final focus/orbit revision passed 46 native
checks, 138 static checks, 159 saved-model checks and 603 retail export checks
plus separate fresh visual review. Full carrying volume stayed unchanged in
the bounded driving/braking sample; tipped remainder was 0.548963 m3.
The test fixture initially contained full sand; explicit clearing made empty
views meaningful, and native visibility confirmed the rear helper stayed hidden.

Evidence: dumptwuck_mod/history/revision_002_*, recipes/build-017-camera-framing.json,
test-017-final-framing.json and sealed dtw-20261001-v2, PAK `d1e02c4e93c67884a1536b3b2654400014b7349adc74edef0184dbf5091d91e4`.
Original 21 source files remain pinned/unchanged. Installation/activation receipts
stay machine local, acceptance stays empty, and retail refill/save/multiplayer
remain untested. The joint addition requires selling and buying a fresh truck.

The full seeded sand surface still has a flat edge slightly beyond the rear rim. The visual pass covers camera/cockpit and empty/returned tray; this full-load appearance observation remains separate from measured retention and unloading. Campaign refill appearance is unverified.

**Correction (owner report, 2026-10-01):** "slightly beyond the rear rim" understated the fault. The owner saw a flat slab far past the rear and sand hanging beneath the tray. Revision 3 below measures and fixes the causes; the v2 evidence above is kept as recorded.


### Dump Twuck revision 3: sand load rebuilt from scratch (takeover, 2026-10-01)

**Owner report / native captures re-measured / SDK shader / Build:** v2's full sand
was a flat slab past the rear and hung beneath the tray. The previous agent
assumed the engine applied the dump pivot twice, shifted the hidden volume
-3.677 m (builds 021/023) and lifted it 1 m; a small tan piece under the tray
remained and a late diagnostic was misread as not showing it (it does; it is
absent only when empty). The owner then asked for the dirt to be redone from
scratch and chose build-and-install without engine runs.

Diagnosis without new engine runs:

- Reprojection: the logged fly-camera eye/target plus wheel-hub calibration
  (F = 842 px at 1732 px wide, 6 px error) let Blender render the authored
  volume from each capture's camera. Best overlap for builds 020, 021 and 023:
  +0.25..1.0 m rearward, 0 vertical (IoU 0.70-0.84); the 3.677 m shift scored
  0.14-0.35. There is no pivot double-offset; the compensation pushed the dirt
  into the front wall. Retail Bowhead/Tayga keep `_load_volume` at the model
  origin with model-space vertices inside the tub.
- The SDK ships the sand shaders. They draw one height sheet over the grid
  rectangle with heights relative to its minimum (4 m range) and clip cells
  thinner than about 0.1 m, so the steep sheet between a thick cell and an
  empty one is visible. A curtain at the volume's rear edge matched the piece
  under the tray; a hypothetical side curtain would have been plainly visible
  in the same capture and is absent.
- Ray probes of the bed art: the tub is a ~1 cm thin shell, floor rising
  0.2437 m/m to an open tail lip, walls at +-3.99 m, rim 7.35 m. The old
  volume was 5.8 m wide; v2's box floor sat 1.6 m under the tail ramp, so
  partial loads were drawn below the visible floor.
- `sfxRefillLocalPosition` (0, 2, -1.5) without `sfxMovableDumpPositionBone`
  placed the refill stream 2 m off the ground under the tray.

Fix (build-025): `load_volume()` samples the bed's real floor by ray casts,
builds the convex hull between that floor (+0.06..0.16 m) and a concave heap
(crown 8.25 m, 6.95 m at the walls, 32 deg front and 30 deg rear slopes), so
the load meets the walls, thins to nothing at the inclined front wall and on
the tail ramp, and never passes below the steel (6,836 samples). 143.4 m3,
173 hull vertices, 3.79 m height range. Helpers stay at the model origin; no
offsets. Payload mass kept at the tested 93,032 kg. The refill stream follows
the volume 1.5 m above the crown. Shared RC035 now flags a truck-space refill
origin.

Evidence: dumptwuck_mod/reports/revision_003_refit/ (scripts, probes, shaders,
images), history/revision_003_build023_superseded/, recipes/build-025-fitted-load.json
and its job receipt, candidate dtw-20261001-v3. Not run in the native editor at
the owner's request; the owner's retail drive decides appearance, partial-load
and tipping behaviour. Unproven: the exact grid extent beyond the hull.

### Dump Twuck revision 4: the sand hung out of the back; lamps and effects (2026-10-01)

**Owner report (retail screenshots of revision 3):** the full heap looked right but a sand
curtain hung behind and below the tail; while tipping a flat slab stretched past the
tail; empty was clean. "yeah it hangs out the back. Can you also make all the features
such as lights and everything work". No engine runs, as before.

Diagnosis without engine runs: disassembling the load-volume setup in
`Roadcraft ModEditor.exe` (dumpbin; functions near 0x1405DC800-0x1405E0800) showed that
the height grid spans the four border meshes, not the volume, and that the back border is
composed with its parent's transform. Revision 3 (like every earlier revision) hung it
under the bed body, so the bed pivot applied twice and the grid ran to y 10.78 m, 3 m past
the tail lip; 295 cells beyond the heap dropped to the pivot height. An emulator of the
decoded rules reproduced the curtain and the slab; with the back border on the tail-lid
body the grid ends at y 7.10 with no such cells. Revision 3's "thick rear edge" theory
was a secondary effect, and the open question it left (how far the grid reaches beyond
the hull) is answered: as far as the borders.

Fix (build-026): the back border hangs from `BoneSandCap_cdt` as a sloped block covering
the rear corners; side and front border tops sit at the sand height beside them. The same
build adds beams on the artist's own light sockets, stop and reversing lamps, flashing
beacons, exhaust and haze sources with retail names, the shipped big-wheel effects module
and Baikal heavy-truck sounds (cockpit-and-lamps.md, Dump Twuck v4). Shared lint: RC036
(border parents), RC025 (effect parents), RC026 (undeclared effects; revision 3's class
fails it).

Evidence: dumptwuck_mod/reports/revision_004/ (grid_sim.py, grid_v3_back_wall_bug.json,
grid_v4.json, disassembly excerpts, install_verification.json), recipes/build-026-features.json,
test-026-static (171 checks), candidate dtw-20261001-v4 installed over the exact revision 3
file (transaction a76d9b7d75604d619315419d39c8046c). Not run in the engine; the owner's
drive decides.

## L275 v6 mine-spec accessories (2026-10-01)

**Owner request:** four reference photos (a mine-spec rear light bar with beacon
and reverse alarm, a whip flag, a 4.5 kg extinguisher in a vehicle bracket, two
wheel chocks in a holder), then "build all of that into the existing l275 mod".
The parts were modelled procedurally at real size (Blender bmesh), given one
2048 atlas with UV-space decals (generic labels) and textured in Substance
Painter with the cab's finishes and calibrated weathering. They mount on the
headboard tubes, the driver's-side headboard leg and the toolbox rear faces;
under-tray mounting was rejected because a box rail hides it. They enter the
build through `tools/accessories.py` called by the model stage, with their own
LOD0-3, chassis skin and joined lamp lenses.

The project's own budget check caught the first version: body LOD0 304,018
triangles against its 300,000 guard (quads count twice). Trimming invisible
density (spring coil, washers, button heads, chain links, U-bolts) brought the
accessories from 26.9k to 20.9k triangles in game. The owner started the retail
game during the build; the Painter launcher refused to start, so the re-texture
and installation waited for the game to close.

Evidence: L275 art/accessories_v6 (manifest, generator scripts), build-019 and
test-020 (all lamp checks passed; only the budget and one report-name check
failed), then build-021 / test-022 (LOD0 298,040 triangles, 319 static and 1,196
retail export checks) and installation over the exact v5 hash after the game
closed (transaction 88b80da8205b49cf88742b98cc0e7136). v7 then re-rendered the
shop card and icon, which still showed the v1/v2 ute (build-023 / test-024,
installed over the exact v6 hash, transaction 718cc72beef64353bc1cf7a94c120c43).
Appearance, beacon flashing and flood reach await the owner's drive.

## L275 v8 glass and beacon fixes (2026-10-01)

**Owner report after the v7 drive:** "The entire mesh appears then disappears for the beacon. Also, the glass isnt
transparent." The glass had never compiled as glass: windows and opaque lamp parts shared one atlas in one object,
and the exporter keeps one material per texture (build-pipeline.md). Retail and SDK glass maps were decoded to set
a clean film (textures-and-materials.md); the windows moved to their own outer / inner objects with the exterior
and interior presets; the model stage now refuses mixed presets on one texture. The beacon keeps its dome on the
light bar and flashes only a lit shell (cockpit-and-lamps.md). Shop card and icon re-rendered.

Evidence: L275 build-026 (`jobs/20261001T120331Z-ec372b44ce82`), test-027 (`jobs/20261001T120747Z-9ecbab91e8a3`): 336 static and 1202 retail export
checks, package `4381a152b71cfab2c379adfbd2c0f94727f49f37af9e3b89d96ef377baf2e8ea`; `reports/glass_beacon_v8/completion.json`. A first build-025 stopped because a pinned
tool was edited during the run (the workflow refuses changed inputs mid-build). Installed only with the game
closed, over the exact v7 hash; the owner's drive decides.

## L275 v9 lights the Lada way (2026-10-01)

**Owner report after v8:** "Thats great, I cant see the lights visible illuminate, or the beacon at all. Can you look
at how the lada does it as i really like that way." A side-by-side of the two projects found the graph, lamp
lights, rear emission values, emission-mask coverage, exporter flags and class layout equal; the L275 differed only
in hiding every lit copy in the markup (since v4) and in a restrained headlamp glow (12 / 1 against the Lada's
80 / 4). v9 removes the markup flags (the graph's init hides the copies) and uses the Lada's headlamp values.
The first build-028 run failed in the retail export with a transient permission error on a just-written descriptor
(written twice in a row); the unchanged recipe passed on the retry. Test-029 stopped on a name clash in the new
audit check (fixed). Evidence: build-028 (`jobs/20261001T131155Z-085f36751560`), test-030
(`jobs/20261001T131622Z-8d3292fa4df5`), 337 static and 1202 retail export checks, package `da8fbaabea0226b044d1de4d9d55fd90f85246ef6b272c449e06d8aae06bc8eb`; L275
`reports/lights_v9/completion.json`. The owner's drive decides.

## Strobes that blink out instead of glowing, fixed in the toolchain (2026-10-02)

**Owner reports:** the L275 v7 beacon ("the entire mesh appears then disappears"), no visibly lit L275 lamp
in v8, and the Dump Twuck v4 strobes ("dont emit when they strobe, the mesh itself disappears and
reappears ... a reoccuring problem"). Both projects had copied the Lada's lamp graph but hid the lit copies
in the model markup, and both strobes swapped the unlit lens with that copy. The owner asked to iron it out
in the toolchain: `roadcraft.lamps` now builds the Lada graph, beams, lamp materials and flashers that switch
only a lit overlay; `roadcraft.blender_lamps` makes lit copies, lit shells and joined accessory lenses;
`lint-bro` RC037-RC039 run in every shared vehicle check with the body markup. Read-only runs on 2026-10-02:
Dump Twuck v4 RC037 + RC039, L275 v7 package RC037 + RC039, L275 v9 and Lada clean. 15 focused tests
(`tests/test_lamps.py`). The Dump Twuck itself is not yet rebuilt; L275 v9 awaits the owner's drive.

**Dump Twuck v5, rebuilt with the kit (2026-10-02):** the owner asked to "fix Dump Twuck strobes and
lamps with the toolchain lamp kit", and for a tank of at least 4,000 L and a $1,150,000 price. The
project now imports `roadcraft.lamps` and `roadcraft.blender_lamps` (pinned as recipe inputs): per-LOD
lit copies of the head and tail lenses plus a stop copy, a lit shell 1 mm outside the beacon lenses
(all vertices moved outward), no lit copy hidden in the markup, the kit's Lada emission values, and the
Lada graph with the double-flash flasher on the engine-running branch. The shared compiled check now
runs RC037-RC039 against the markup: clean. Build-027 stopped in the package step because the
project's export preflight still expected `buyCost == 1`; build-028 passed, test-028 passed 177 static
checks, and dtw-20261002-v5 is installed over the exact v4 file (transaction
2a381207aa6c44079c3f8e9fe1d621c7). Not run in the engine; the owner's drive decides.


## Lada v9 original 4K interior restoration (2026-10-02)

The owner requested AI upscaling, then explicitly selected the original 4K
maps after two generated drafts changed markings and provided only 1254px.
Both original interior sets were 4096px while the installed v8 maps were 1024px.
V9 restores six full-resolution colour, normal and metal/roughness/AO textures,
retaining the original layout and tested normal convention. New packed inputs
live outside the immutable original source inventory.

**Build:** build-013 failed because the SDK normal descriptor requested only
ten mips. The corrected converter requests at least eleven for these maps.
Build-014 was pinned but never executed after the retail-mip audit was corrected;
build-015 (`20261002T000621Z-f09d37a86caf`) and test-015 (`20261002T001249Z-3a0e99e656a9`) passed 198 package/static and 829 export checks.
The exact v8 package comparison permits only six mip chains/resources and two
normal TD descriptors, including twelve new mip members. Native generator
file-sharing retries are retained in build evidence rather than omitted.

**Inspected Blender renders:** matching 1K/4K cockpit and cabin views show
sharper original gauge marks, trim and upholstery. No AI artwork is packaged.
Candidate `lnv-interior-4k-20261002-v9` is transactionally installed with a verified v8 backup.
Evidence: Lada `revisions/interior_4k_v9/`, `art/interior_4k_v9/preview/`,
`package/candidates/lnv-interior-4k-20261002-v9/texture_result.json`.
V8 runtime evidence remains historical; v9 has no native editor, retail,
performance or owner-acceptance claim. The new checks are wired into local
validation; see [textures-and-materials](textures-and-materials.md) for reusable
decisions and why the exact atlas/delta contracts remain asset-specific.


## Lada v10 native seated driver (2026-10-02)

The owner asked to place a driver in the 4K-interior Lada. Its BRO explicitly
hid the driver. V10 enables the shipped `driver_static_01`/`idle` setup and fits
it through the existing camera frame at native offset `[0.035,-0.62,0.08]`.
There is no custom hand/pedal IK and no geometry, texture or handling edit.

**Game, isolated diagnostic fixture:** side/cabin captures show the seated
driver facing forward with roof clearance; native first-person hides it and
third-person restores it. The owned editor exited 0. One premature probe targeted
the pre-Play engine, one timed out during loading, and an initial array literal
failed SSL compilation; those attempts remain distinct from passing probes.
The first skeletal landmark query was parent-local; `GetTransformObj` plus
truck inverse transform corrected it. Another mod's active batch editor was
preserved before launching this fixture.

**Build:** build-016 `20261002T004414Z-16b8538b2336` and test-016 `20261002T004742Z-71e3ad354621` passed
209 static and 829 export checks.
Final generated gameplay equals the trial after resolving only the omitted
stock driver-bone default, with 191 exact compiled-asset matches and all 362
fixture files unchanged. The retail PAK itself was not launched in that fixture.
`lnv-driver-20261002-v10` is installed with a verified v9 backup. Evidence:
Lada `runtime/driver_v10_trial/`, `revisions/driver_v10/native_parity.json`,
and `package/candidates/lnv-driver-20261002-v10/driver_result.json`.
The local driver audit is wired into validation and checks the exact v9 delta;
shared placement guidance is in [cockpit-and-lamps](cockpit-and-lamps.md).
No retail campaign, multiplayer or owner acceptance is inferred.

## KGS25 tracked crane conversion (2026-10-02)

**Build / SDK:** private user-supplied metric Blender/PBR/three-LOD artwork was
converted into six native assets with tracks and a five-body telescopic crane
chain. The first native import, gameplay generation and retail export passed
(job `20261002T003025Z-43b00a0d75ea`). Later static inspection caught stale TC305
movement-sound body/joint references; RC045 and its tests now check that class
of conversion fault. A subsequent pinned build correctly stopped when shared
compiler code changed, so the project uses a recorded compiler snapshot.
The owner deferred editor driving/lifting tests. Package/build evidence must
remain separate from crane stability, terrain behavior and retail acceptance.


## CAT 793D RC26: all exterior lamps through the toolchain kit (2026-10-02)

**Owner request / Build / installed candidate:** "Fix 793D strobes and all lamps with the
toolchain lamp kit." The baseline was verified installed RC25, with its shop icons and RC23
load repair retained. The retained RC23 body-model outputs matched it exactly. RC26 uses the
shared kit for head/work/marker/tail/brake/reverse states, fitted beam/glow anchors, green
double flashes and an amber shell flasher over the persistent lens. No hidden markup lamps
were found in RC25, so the recent L275/Dump Twuck markup diagnosis was not blindly applied.

The first native build failed on sandbox runtime extraction. The second official model import
completed, but its job's post-step input check failed because another task changed the shared
linter during compilation. Both original failed receipts remain failed; verified process/live
package checks and separate lock-release records retain the recovery history. The completed
model was explicitly pinned as an input to a fresh offline finalization recipe; build/test
receipts pass. This is an explicit artifact-input route, not incremental-cache reuse of a failed
job. The existing `jobs-recover` path assumes an accepted package and historical transaction
records; do not fabricate acceptance to recover an imported candidate's build. Generalizing
that recovery route remains a separate workflow change.

RC26 passed 1,275 package/model checks, 18 exported graph event checks and shared lint without
findings, then replaced the enabled slot with a hash-checked RC25 rollback backup. No retail
rendering or campaign acceptance is claimed. Evidence: `cat793d_thiess_fix/LAMPS_TOOLCHAIN_20261002.md`,
`cat_lamp26/{jobs,jobs-final,reports,local/transactions}` and the candidate/source seals under
`cat_lamp26/package`. Shared process-name regression tests now distinguish connector servers
from actual authoring processes. Existing lamp helpers and checks cover the repaired pattern.

## KGS25 candidate01 owner failure and native repair (2026-10-02)

The owner tested the first package and reported detached boom parts, unstable
tracks and flight; the installed hash matched the sealed candidate. PC testing
was then authorized, superseding the earlier editor-test deferral. Two native
startup faults were resolved before driving: incomplete donor sound graph links
and missing engine shaker definitions. A pad drive then reproduced violent
flight after reverse/braking, despite a stable initial rest and forward drive.

Inspection also found source child meshes displaced by sequential parent
freezing. The repair snapshots all source transforms, audits raw geometry bounds,
extends hidden piston overlap and replaces high-force track hinges with fixed
frames while retaining wheel contacts. Native-build-004 pins the repaired source.
The old failed builds, package and tests remain preserved. Final editor evidence
and retail acceptance must be recorded separately; no accepted pin is fabricated.


The fresh repair subsequently passed pad driving: 7.75 m forward, 6.43 m
reverse, 34.99 degrees of turning, zero parked drift. The incorrect rotated
native prism was caught by the first crane test and corrected separately.
Both full telescope strokes, luffing and slewing passed attachment checks;
the actual native crane UI/IK raise path was then measured. Full source/import/
generated-class/package identities are pinned by native-build-007, with the
full geometry generation chain preserved from native-build-004. This is native
editor evidence; retail campaign acceptance remains open.


## KGS25 native four-leg and rotating counterweight revision (2026-10-02)

The owner requested missing stabilizer legs and reported a stationary
counterweight. The converter's rear_box chassis fallback explained the binding
fault; all LODs, collision and attached lamps now follow the turret. Four
authored hydraulic supports use native sequential anchor controls and preserve
the prior 41,180 kg total authored body mass.

The first native session stalled at initial loading and was preserved as
supports01; a fresh session loaded successfully. The first deployment grounded
all feet and stayed stable, but never completed because a 0.40 m command stopped
near 0.379 m. The 0.37 m live trial completed. Native-build-009 / build-run-010
then rebuilt all six assets and fresh classes for the corrected candidate.
The final fresh native tests and reviewed captures are pinned by
reports/runtime/supports-review.json. They cover leg deployment/retraction,
90/180-degree slewing and normal HUD 7 anchor input. The owner then requested
finish-up without further tests; new driving and full-stroke regression checks
were deferred. Prior candidate02 drive/crane results remain prior-build evidence.
Earlier supports03 capture-focus and console-discovery failures are retained
separately; a numerical retry passed. The normal key initially had no effect
until the actual game viewport was focused. A foreground editor window alone
does not establish native input routing. These are observed adapter limits,
not demonstrated package faults or authority to weaken capture visibility guards.
The prior failures, candidates and source identities
remain retained; installation grants no retail campaign acceptance.


## KGS25 drive fix: measured on the editor bench (Claude, 2026-10-02)

The owner reported the installed crane lifting on one side and being pushed around while
driving. Fix 1 followed the toolchain's suspension formula and gave the 14 ground fakes
springs. The owner reported it worse ("bounces or wobbles"), and it was rolled back to
candidate 03 the same hour.

A read-only editor bench then measured the crane. It drives a patched copy of the mod in the
Mod Editor's automation scenario and samples every body and wheel at 10 Hz; Codex's project
was not touched.

- Fix 1's springs were 25-40 times softer than predicted, apparently scaled by the 2.5 t frame
  they hang on. **Superseded 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, F3 and the
  T4 correction): that run (`v1_155728`) was frozen, all 478 samples identical, so the figure is
  not evidence, and code shows no mass scaling of `strength`.
- Candidate 03's real fault: in pivot turns one track sinks up to 19 cm into a flat pad while
  its wheels still report contact, and the hull rolls 3-4 deg.

Single changes only halved the roll at best:

- the retail EPEC layout, with rigid real wheels at each track end: 2.0-2.3 deg
- a lower centre of mass: 2.0-2.7 deg
- heavier frames alone: worse, a track lifts

The EPEC layout together with 7.5 t frames (hull 9.9 t, total unchanged) and the hull centre
of mass at [0, -1, 0] held roll to 0.2 deg, kept the hull within 4 mm and turned 53 deg against
35-41 deg. In full-lock pivots both versions judder; fix 2 lifts less and settles at once.

Fix 2 patches only text members of Codex's candidate 03: both truck classes and the two
markup copies. The other 562 package members are byte-identical. It was installed 2026-10-02
16:55 (sha256 7d65d691...), with candidate 03 backed up in the drive-fix workspace. The
owner's drive is pending, and so is Codex's generator: `prepare_mod.py` still writes the old
values.

Integrated into the toolchain the same day: [tracked-vehicles.md](tracked-vehicles.md) (retail
layouts, the recipe, RC046-RC048 in `roadcraft.tracks`), [physics-bench.md](physics-bench.md)
(`roadcraft bench`, generalised from the KGS bench and checked against its runs) and
`roadcraft.pak_patch`. The bench's wheel positions also settled the suspension stop geometry
(stops at `height + min` / `height + max`), which corrected the design formula, RC005 and the
Lada sign reading (suspension-and-wheels.md "Stop geometry").

## WALL-E: store OBJ to a to-scale tracked scout without the editor (Claude, 2026-10-04)

**Request:** "Make Wall-e into a RoadCraft polished tracked vehicle to scale", and use it as a toolchain
study. Source: a store archive (OBJ, 39.5k triangles, 138 parts, four 2K PBR sets).

- **Scale:** Pixar's publicist gave 3 ft 4 in (1.016 m) ground to eye-top, 270 lb, 7.8 hp, 20 mph average,
  35 mph top; the model measured 1.037 units there, so S = 0.98. 122.5 kg in all.
- **Model fixes:** the head was posed 26 degrees to the side; it was turned back about its neck bolt so
  the eyes (the headlamps and the first-person camera) face the driving direction. The static tread mesh
  was dropped: one of its 34 links (45.5 mm pitch) became the five-bone section model.
- **Findings integrated:** track-section frame and height (tracked-vehicles.md); gear top speed =
  angularVelocity x gearRatio x rolling radius and the engine fields (truck-settings.md); the Blender 3
  vertex-group cause of zero-weight vertices and the editor-free new-vehicle route (build-pipeline.md);
  `.tpl` bounding boxes and the dropped `trackOverlay` (retail-data.md); measured normal-map conventions
  with the new `roadcraft.normal_maps` helper and the UI-icon `mipmap_level` rule (textures-and-materials.md).
- **Result:** candidate `walle-r1`, `walle.pak` sha256 `1f3745b3...`, 56.3 MB, package audit passed,
  `lint-bro` 0 errors / 0 warnings, installed 2026-10-04 to an empty slot with a toolchain receipt.
- **Owner's drive of r1 (Game):** "looks a bit fucked up, bounces around and rolls over without even doing
  anything" (screenshots: long cylinders sticking out of the tracks, WALL-E on his back).
- **Editor bench, about 30 runs:** the editor-form project (`tools/bench_project.py`: packaged classes renamed
  to the generator's form, a pad scene from the SDK template) let `roadcraft bench` measure a mod built with
  no editor. The probe gained engine state, centre of mass and wheel spin (physics-bench.md). Found, in order:
  the centre-of-mass markup forms (frames.md); hidden wheels near visible ones shaking the belt and a rigid
  middle wheel jittering; the up-scaled gear table starving the drive (truck-settings.md); a to-scale mass
  too light for the engine; soft contact tilting a two-size wheel layout; the low sideways friction starting
  too late for a small pivot (tracked-vehicles.md, symptoms.md). Two theories were disproved by retail data
  before they shipped: "wheels whose radius + section overlap mesh like gears" (Karelian road wheels overlap
  that way and drive).
- **Mistake recorded:** a screen capture of the editor's window rectangle caught another application in front
  of it. Captures were deleted and disabled; never copy screen areas without the owner's consent.
- **r2:** visible wheels are the real ones, 1400 kg, unscaled gears, hard contact. `walle.pak` sha256
  `dc3936a7...`, installed over r1 with a receipt. Bench: level and still at rest, under 0.6 deg roll in the
  harsh schedule, pivots 51-67 deg. **Open:** the owner's drive; steps (no hidden obstacle wheels).

## Dump Twuck public feedback audit (2026-10-08)

**Public user reports / Open reproduction:** the Saber page for `<213> Industrial
Dump Truck` contained five comments dated 5-7 October: four player posts and one
author request for video. Two players independently wanted all-wheel drive; one
reported the truck initially continuing its previous direction after stopping,
applying the handbrake and switching forward/reverse. One requested more power,
driving speed and tipping speed. Other remarks concern Xbox availability, price
and route clearance. Counts refer to posts, not likes; these remain reports, not
reproduced faults or validated fixes.

Evidence: [public mod page](https://saber.games/games/roadcraft/mods/213-industrial-dump-truck?s=New+mods);
Dump Twuck project `reports/public_comments_2026-10-08/audit.json`,
`comments_page_000.json` and `mod_metadata.json` (source hashes in audit.json).
The page's public comment endpoint returned total=5 and all five records. Its
published PC release is named Version 2; no package hash or lineage comparison
connects it to any historical local candidate. These comments do not establish
whether the owner's earlier cargo geometry, camera or bounce issues persist.

Integration: recorded here and in [symptoms.md](symptoms.md). Prioritize a
repeatable direction-change test and clarify intended driven axles before tuning
power. No validator was added: causes and reproducibility remain unverified.

### Public comments and author screenshot follow-up (2026-10-10)

**Open / user reports:** refresh returned all seven public comments (six players,
one author), adding two since the October 8 audit. AWD now has three independent
player posts; power/speed two. New reports describe poor mud/rock traction,
cumbersome turning, continual backward travel, bright headlights, unspecified
beacon errors and toy-like textures. Continual backward travel is not yet proven
to share the earlier stop-and-reverse report's cause.

The supplied zombie213 screenshot additionally requests interior camera, mass,
sand capacity, diff lock and engine-location adjustments. It reports a puddle
triggering a high-water warning; the claimed engine placement in the axles is
an unverified diagnosis. The author claims a new interior, digital speedometer
and fixed gauges; the pictured source archive was not supplied or inspected.
Capacity/mass targets and calibrated dimensions are absent. Interior-camera
feedback is distinct from the owner's earlier third-person camera report.

Evidence: Dump Twuck `reports/feedback_2026-10-10/assessment.json`, raw comments,
current page metadata and `author_feedback.png`, all source-pinned in the assessment.
No public/local/archive package lineage was verified. These reports do not prove
older cargo-geometry or bouncing problems fixed. Prioritize reversal/water/camera
checks, set mass/payload/drivetrain targets, then measure performance, steering
and dump time. No automatic rule is justified without reproduction. Documentation
integration only; no native run, repair, install or feedback post occurred.



### Dump Twuck revision 006: source admission and offline repair candidate (2026-10-10)

**Build / SDK; offline visual only; native Open:** after the earlier feedback audit, the author supplied `DumpTwuck_ModEditor_v2.rar`. `source/revision_006/manifest.json` now pins the selected primary `.blend`/FBX, README and markup; `generated_authoring_inventory.json` pins inspection with embedded scripts disabled. This supersedes the earlier statement that the new-cab archive had not been supplied or inspected. It does not establish lineage to the published Version 2 or to an owner's earlier gameplay screenshot.

The primary body source has 80 objects, 53 materials and zero images. Several new-cab material graphs are procedural, contradicting the README's flat-Principled claim. The offline route preserves source skin/control bones, makes fresh packed PBR/emission textures and fitted collisions/load hulls, retains tiny constant-finish labels by uniform-tile centre UVs, and corrects canonical absolute-head/local-COM conversion. The measured envelope is about 143.4133 m³; the agreed 1600 kg/m³ design gives about 229.46 t of material. The authoring design/audit covers 19 checks, including selected AWD/diff, direction-change state, fitted intake/camera/gauges, steering and empty/full suspension predictions; it explicitly states nativeTested=false and accepted=false.

A stock `DtwDigitalDash` BPN controller selects 30 separately named glyphs for zero-padded absolute km/h at 10 Hz. Five offline SDK-schema/synthetic-graph tests passed; this replaces Blender property drivers but does not yet prove native compilation or rendering. The first model pass selected red-glow triples below the analogue dials and left the main central dark `888`, showing that a valid graph and counted geometry are insufficient for semantic placement. The corrected actual driver-eye Blender view now shows central `000` unobscured (Visual, offline only). The actual central dark-panel foreground is removed by its measured 21-bar/756-vertex component guard while preserving the backing; 30 independent glyphs and authored `km/h` are fitted there. This supersedes the first placement, without establishing live speed updates or native pixels. Tiny-font filtering is suspected; the uniform-strip remedy is authored, but matched before/after captures were not sealed.

**Offline checkpoint / model-import Build:** `reports/revision_006/offline_checkpoint.json` records PASS_OFFLINE; checkpoint verification confirms 212 pinned files. `reports/blender_model_audit.json` passes 284/284 checks, and `reports/build_import.json` records four successful native CLI model imports. These establish saved-model and import artefacts, rather than BRO generation, a packaged mod or gameplay. Preserve the original `authoring_receipt.json`, which records an SDK log-directory permission failure at its first import step; subsequent explicit imports are separate evidence.

**Candidate 01 failed native generation:** attempts 1–2 stop in wheel/preview-wheel `SaveTo` with an IOException on a held `.sso.resource`; no digital graph error is identified. A preceding nonfatal VFX `boneOffset` fixed-array warning is separate: the SDK requires three floats and the authored offset already has three, while the glyph names are a dynamic string array. Preserve this failed build and warning; holder/conversion causes and recovery remain Open. A successful later candidate must have its own receipt.

Evidence: Dump Twuck manifest/inventory above, `build/physics.json`, `reports/gameplay_v6_audit.json`, `reports/preview_v6.json`, `tools/model_v6.py`, digital controller/model/probe and `tests/test_digital_dashboard.py`. Proposed shared integration: [cockpit-and-lamps.md](cockpit-and-lamps.md), [textures-and-materials.md](textures-and-materials.md), [frames.md](frames.md) and [symptoms.md](symptoms.md). Native compile, measured driving/reversal/AWD/diff/water behaviour, digits/needles, lighting, retained/unloaded sand, installation and owner acceptance require distinct final receipts. No complete BRO generation/package compile, runtime, campaign or public-release pass is asserted by this entry.


### Dump Twuck revision 006: owner rejects the broad mound preview (2026-10-10)

**Owner feedback / offline numeric Build; native Open:** after three failed native candidate generation iterations, the owner identified the prepared load as visually flat again. The pre-refinement authoring used the older broad paraboloid with a 4.8 cm longitudinal centreline drop over 2 m. Passing load-grid containment had not established the requested peaked silhouette. Preserve that source and the failed native receipts as the pre-refinement baseline; do not rewrite their outcome.

The maintained `blender_load.heap_top` gained an opt-in elliptic cone and eight passing pure numeric tests. Its default profile remains unchanged; finite positive cone dimensions/slopes are checked. The project-specific saved mound, containment, volume/density mass, offline preview and checkpoint are separate root-owned steps. This entry does not assert that those steps or any new native run succeeded. Evidence: Dump Twuck `history/revision_006_candidate03` and `reports/revision_006/mound_refinement`. The three earlier native attempts remain exhausted; compiled appearance, stationary retention, discharge and retail acceptance are open. See [truck-settings.md](truck-settings.md) and [symptoms.md](symptoms.md).


**Additional failed offline Build: border-only cells below a sloping floor.** The first pointed-load saved audit had no shared grid findings or pivot cells and an earlier hull-floor probe reported no under-floor hull. A direct audit of all 992 native grid sample positions against the measured steel nevertheless found four border-only rear-corner cells. At x=+/-3.874375 m and y=6.801352/7.086921 m, their lower/upper sheet height was 6.5 m while the steel was 6.667592-6.733335 m. The worst under-floor error was 0.233335 m. `grid_findings=[]` and a passing hull-only floor check cannot establish that the full drawn grid stays above the tray: cells outside the hull can use border heights.

Keep a separate saved-grid-versus-steel test at the engine's nudged sample positions, including both border and hull cells and both lower/upper sheet heights. The project audit rejects more than 5 mm below steel, requires a surveyed floor population, keeps the sheet below 4 m and uses a conservative 0.35 m edge-step ceiling (stricter than the shared 0.5 m finding threshold). Root corrected the intended rear border top back to its measured 6.62/6.86 m ramp while retaining the other lower border tops; a corrected configuration is not a completed source pass. Require the final matching saved-model report and completed pinned inspection receipt before claiming this correction verified.

Evidence: Dump Twuck `tools/audit_mound_v6.py` and preserved `reports/revision_006/mound_refinement/failed_lowered_rear_border/{mound_profile_saved.json,physics.json,receipt.json,inspect-041-v6-peaked-mound.json,saved-model-audit.log}`. The failed report/receipt stay failed. This is offline source geometry plus grid emulation; the newly pointed load has not completed native compilation or visual/retention/discharge acceptance. The three preceding candidate iterations remain exhausted; this refinement adds no fourth native attempt or implicit installation authority.

## Kanga 25 pick-and-carry crane from a finished asset (Claude, 2026-10-10)

Owner request: "make this into a fully polished roadcraft mod using the roadcraft toolchain", on a finished
Franna MAC25-4 asset (v2 game mesh with a BakeLow per-part split, skeletal FBX weights, 10 Painter sets exported as
RoadCraft TGAs). Owner choices: unbranded name "Kanga 25", **three real telescope joints**, **no engine runs**
(build, offline audits, install; the owner drives). Project `RoadCraft/kanga25_mod` (`mod-init --kind vehicle`).

* **Route (Build):** textures (supplied TGAs + badge overrides) -> Blender 5.0 model build from the BakeLow parts
  (per-part objects for free: lens split, cockpit controls, LODs by dropping small parts, convex hulls per part
  group) -> markup/BRO generator over a merged retail donor (Baikal 5916 crane + its chassis template + compiled class
  graphs) -> asset_importer -> hidden batch generation (4 attempts, file-lock race) -> mod_pak_builder + retail export
  (910 checks) -> test phase: shared vehicle check, rig audit (24), package audit (22). Recipes build-002 / test-002,
  candidate `kanga25-20261010-c1` (sha 2f7bde37...), first install with `--expect-absent`.
* **Articulation limited by the art (Build):** the modelled steering cylinders (barrel 0.54 m, rod 0.55 m behind its
  eye, pins 0.84 m apart) stroke only 0.58-1.05 m: +-30 degrees, not the asset rig's +-40 (the rod would leave the
  barrel at one lock and poke out of its back at the other). Measure cylinder strokes over the joint range before
  choosing limits ([articulated-steering.md](articulated-steering.md)).
* **Boom tail meets the rear deck (Build):** the art's tail sheave clears the rear module only up to 49 degrees luff
  straight ahead and 17 degrees at full articulation one way. Luff limited to 60; boom-vs-rear collision is disabled
  (shared collision group), so the remaining overlap is visual. Reported by `tools/audit_rig.py` as a known limit.
* **Art defect fixed:** the right headlight lens was mapped onto window-film pixels (renders as dark glass); its UVs
  now take the left lens's. Found by sampling the emissive map under every glass component.
* **Badge repaint without Painter:** re-ran the asset's own decal and texprep scripts with only the text changed,
  diffed the decal maps (only badge/plate/load-chart pixels changed: the projection is deterministic), inpainted the old
  lettering out of colour and spec (OpenCV Telea) and laid the new decal over with the old wear carried as a smooth
  multiplicative factor (`kanga25_mod/tools/badges.py`).
* **Render review traps (Build):** pin empties parented to bones of the same armature as constrained bones form a
  dependency cycle (cylinders froze); use helper bones. Blender 5.0 renamed the sky texture types (NISHITA silently
  failed inside a try) and its sun cast a long second shadow.
* **Toolchain job log rename (Build):** one test run failed with WinError 32 renaming `.rig-audit.log.partial`
  right after the Blender step; an immediate rerun passed. Treat as a transient file lock (Open: retry in `jobs.py`).
* Owner drive pending: articulation direction/feel, crane IK with the near-locked slew and three telescopes, hook
  stow/hide, lamps and beacons, mirrors, driver pose, sounds, handling (unbenched).

## Dump Twuck public and author feedback actioned (Claude, 2026-10-11)

Inputs: the seven Saber page comments (reversal after a stop, "constantly drives backwards",
no AWD x3, slow / stuck in a little mud and on rocks, slow tipping, too-bright headlamps,
beacon "errors", "a toy from a shop" textures, Xbox) and zombie213's list (cameras, mass, speed,
power, tipping, 362 t capacity, AWD, diff lock, puddle high-water warning). Codex's v6 (the
author's new cab, digital dash, front steering IK, peaked mound, camera eye, water sampler,
halved headlamps) and v7 (side-correct tyres) had been built but never installed.

| Build | Change | Why |
|---|---|---|
| v8 `dtw-20261011-v8` | 362 t payload over the 129 m3 hull; tare 240 t; torque 6.14 M (80% of the retail Baikal 65206's loaded force per kg; v5/v6 had a third); gears by `angularVelocity`, `gearRatio` back to RPM duty; reverse 0.11; `neutralGearSwitchingDelay` 0.5; AWD always on, diff lock switch (retail Tayga); Baikal tyre friction; tipping 12 deg/s; steering 0.04 / 0.08 | truck-settings.md "Heavy hauler drive" |
| v9 `dtw-20261011-v9` | Body re-unwrapped into a 4096 atlas (59 px/m, was 14) and wheels into 2048 atlases (~130 px/m) with baked AO, wear, dust and mud; beacon lit shell 1 -> 4 mm; store card and icon rendered from the new model; 86 MB package, 334 static checks | textures-and-materials.md "Weathering" |

Not driven yet; no Mod Editor runs (owner rule). Owner should sell and rebuy the truck after
installing (the rig changed since v5). Open: whether reverse lands near 13 km/h, whether the 362 t
load settles inside the suspension's predicted reserve, what the beacon "errors" were.

## L275 v10 tray cargo and tie-downs (2026-10-11)

**Owner request** (photo of the real tray): a SMAC compressor between the toolboxes, tool bags and equipment, toolbox
shelves, a tray vice and junk under a cargo net; mid-task "I want everything to look real" (sourcing allowed), then
"clear the tray of all the clutter except for the smac and vice. Add the ability to tie loads down". Result: custom
SMAC 40-D style compressor + hose reel, Poly Haven bench vice on a fabricated pedestal, shelves and scanned contents in
both toolboxes (deck junk and the cloth-simulated net were built and then dropped), and a retail `CargoConstraint`
cargo bed with a CONSTRAINT_CARGO toggle ("Cargo beds and tie-downs" in truck-settings.md). Body LOD0 298k -> 367k
(project guard raised to 400k). The project patches its generated class, so the IK patch's "unrelated data" audit had
to learn the cargo sync (first build-031 failed there). 352 static / 1,338 export checks; installed over the exact v9
file. Not driven.

## L275 v14 VDJ79 undercarriage (Claude, 2026-10-12)

**Owner request:** upgrade chassis, suspension, steering and brakes of the L275 to a detailed VDJ79 layout (front
coil live axle, rear leaf live axle) in headless Blender, keeping wheels, wheelbase, ride height, physics and the
rest of the vehicle. Result: parametric generator (C:/RC/l275_chassis, pinned in the mod's art/undercarriage_v14):
C-section ladder fitted to the owner's lowered cab/tray (body-drop rail line, rails notched over the rear seats),
radius arms, panhard, coils, shocks, stabiliser and RHD recirculating-ball steering with damper; rear
spring-under-axle 6+2 packs with shackles; 4-pot front / floating rear calipers, lines, hoses, ABS leads, park-brake
cables, propshafts. LOD0 121.8k tris in two 4096 atlases (frame 24.8k / gear 97.0k) replacing a 45k chassis; body
LOD0 447k (guard raised to 480k), LOD3 26.6k. Rig: kept chain names, moved bones, removed the Roamer rear four-link
and rear panhard, added shackle, stabiliser and damper chains (ik-visual-rigs.md "Live-axle linkages"). Integration:
`undercarriage.py` (strip source chassis, edit bones, author art), `undercarriage_rig.py` (BRO), `patch_compiled_uc.py`
(class chains, audited), validate checks (build-pipeline.md "Replacing running gear"). Toyota AU spec (via a
converter's PDF) confirmed vented discs front and rear; forum/vendor data say the stock rear is spring-under-axle.

**What went wrong on the way:** the review scenes read the mod's built model as context while a build rewrote it
(open failures; read it only after the build); a Blender save of a 300 MB review .blend failed its '@' rename
(retry helper added in create_models.py); a research sub-agent overwrote the main reference record (restored from
the copy pinned into the mod - pin early); pointiness-based edge wear blotched every low-poly plate
(textures-and-materials.md). Not driven: native IK motion of the new chains is for the owner's drive.

## L275 v15 physics accessories (2026-10-12; Build, not driven)

Owner: mount the new extinguisher and hose reel on the toolbox, the reel "on a shaft so it turns", physics on the reel,
mudflaps and mine flag. Result: swing-out reel bracket (rearward only: the compressor is 4 mm ahead; clearance sweep
-110..+4 deg, hinge -95..+3), rear mudflap hinges, whip flag as two ragdoll pole segments plus two hinged flag panels,
all as retail secondary bodies ([secondary-physics.md](secondary-physics.md)). Installed sha 7b4ecf18 over v14.
Lessons: (1) the joined tray's v3 UV patch is fingerprinted, so the flaps are tagged with a face attribute before the
join and split off after it; (2) editing a pinned toolchain source while a build runs fails the step ("changed pinned
input"), so make toolchain edits between builds; (3) a library .blend whose objects live outside any scene (v10 cargo
art) loses them when a script saves a copy: link them or set fake users first. Values unmeasured (owner: no editor runs).

Follow-up (same day, Game): owner "when you go to spawn in it, nothing happens ... after it loads the game wont save". Script dump: HUD `HandleOnCurrentTruckChanged` -> `GetToggleableActionReactive(30 = CONSTRAINT_CARGO)` on a null `cargoConstraint`. Cause: the v10 tie-down sync never added `TruckCargoConstraintUnit` to the replicated entity (since v10, not the v15 physics). `cargo_bed.py` now inserts it; validate checks it.

## L275 v17: reusing another mod's bullbar (2026-10-12; Build, not driven)

The Roamer 105's ARB bar fitted to the L275 79: (1) fit by matching guard width (x 0.90), face depth and the owner's
height cue ("just below the grill" = bumper-box top under the grille bottom); (2) re-bake instead of copying textures:
each face samples its source material at the source UV and bakes to new packed UVs (emission for albedo/spec, tangent
NORMAL bake for normals, DirectX <-> OpenGL flips), so 11 source materials become one atlas; (3) remove the factory
bumper by connected mesh component (pieces fully below the valance, reaching the bumper line, inside the guards), not by
a box (a box left the wrap-around ends; the owner also saw the end flares when the width limit stopped at .89 m);
(4) convex hulls of a wrap-around bar must stop short of the wheels: wing hulls reaching back to the guards filled the
space ahead of the tyres and failed the steering/travel clearance audit; (5) a transient PermissionError in the retail
export (pct.resource write) failed one package step; the gameplay-only rerun passed.

## L275 v24: radio handpiece and replacement tail lamps (Claude, 2026-10-12; Build, not driven)

Request: fit two standalone props, an APX O3 control head (C:/RC/apx_o3) in the cab and a three-section LED combination
tail lamp (C:/RC/combo_lamp) on the tray. Shipped inside the combined candidate l275-aocam-20261012-v23c (sha 03824384...,
447 static checks). Mod files: tools/radio_lamps.py, art/radio_lamps_v24, config v24 block, validate v24 checks.

- **Replacing lamps the light graph already switches** (grade: Build). Keep the graph's lamp objects (tail_lights,
  tail_lights_on, brake_lights_on, reverse_lights, reverse_lights_on) and swap only their contents. At every LOD,
  delete the old lens faces by material, join the new lens copy with the role's lit or unlit material, then drop the
  empty material slots. The graph, sfx anchors and accessory lenses stay valid. Move the light anchors to just
  outside the new lens fronts.
- **Mount points by ray cast against the built model** (grade: Build). Read the panel face behind each lamp and the
  dash patch on a 1 cm grid (a00_measure.py). Build the prop frame from the hit point plus a ±20 mm tangent and
  normal. Check the clearance to overhanging parts from the raw vertices (the tray beam bottomed 2.5 mm above
  the lamp).
- **Body LOD3 budget** (validate.py caps body LOD3 at 30k): an interior prop drops hard past LOD1, because it can't
  be seen from outside.
- **Headless Blender 5.0 (factory startup, -b) pitfalls** (grade: Build):
  - `bpy.ops.uv.smart_project` fails its poll. Use a per-part box projection instead.
  - An EXACT boolean slot cut on a simple extruded profile returned an empty mesh. Build slotted plates as
    outline prisms.
  - After a glTF import, every vertex is selected, so setting `polygon.select` and calling `mesh.separate` takes the
    whole mesh. Split by bmesh copies instead.
- **Process: concurrent agents on one mod tree** (grade: Observed). Editing a file another session's recipe pins
  (validate.py) fails that session's build ("Stale or missing input"). Two ship scripts that expect the same
  installed sha can't both install. Before editing a mod tree, check recipes/, revisions/ and jobs/ for activity in
  the last hour, and agree one combined build with the other session.

## L275 v25/v26 polish pass: audits, then patched-class retail parity (Claude, 2026-10-12; Build, not driven)

Owner request: "polish every little feature of this mod and make sure its not missing anything". Three read-only audits
ran in parallel (feature parity against the Lynx, Lada and Roamer; project consistency; texture quality), followed by a
headless render sweep. Shipped as v25 `b0422e64...` (463 checks) and v26 `f92b9953...` (472 checks). Mod tools:
cab_leftovers.py, cab_fit.py, lod_trim.py, material_tidy.py, patch_compiled_features.py, gauge_glow.py; art polish_v25/26.

- **Mirrored-interior leftovers** (grade: Build, renders). When an interior object is mirrored LHD -> RHD, interior bits
  in the cab BODY mesh stay behind and float: wheel-hub emblem, cluster bezels, stalk glyphs. Rule that isolated 240
  pieces without touching the shell: wholly inside the cabin box, < 12 cm, no mirror twin across x = 0, away from the
  centre stack, behind the cowl.
- **A patched (not regenerated) class misses BRO-only edits** (grade: Build). The v17 winch point existed in the BRO
  only, and the class kept v1's for seven versions. Validate the class against the config, not the config against itself.
- **Retail feature parity by copying the Lynx class verbatim** (grade: Build): shakers plus their Engine nodes, gear,
  low-range and moving-handbrake sounds, steering-wheel sound, winch force feedback, wheel particles, water blocks, towing,
  steering-wheel force feedback, effect list and class-resource links. A designer-wizard truck's graphs are subsets of
  the Lynx's, so node ids match. The tracker locator is remapped when the target bone is missing.
- **Idempotent patches against a persistent class** (grade: Build): every generate run re-patches the same class. An
  audit that compares against a fixed baseline must normalise each later patch's own blocks, or the second build fails
  (patch_compiled_ik "changed unrelated data"). Allow-lists must not be built from "what this run added", which is
  empty on a re-run.
- **Fuel station = four coordinated pieces** (grade: Build): prop_reserve_tank, the ReserveTank smart point,
  ReserveTankSavablePropDesc, FuelStationUnit, plus its replicated-resource link. Every replicated unit needs its
  linksDesc entry: all 42 retail trucks with TruckCargoConstraintUnit link truck_cargo_constraint_unit.sso.resource.
- **Exhaust smoke needs a real outlet** (grade: Build): the stock smoke emits from a parent area, and an empty locator
  has none. The Lada point-source override needs a modelled tailpipe, and the plume aims along the locator's local +Y
  (native -Z, 'z-').
- **Texture defects found by numbers, not looks** (grade: Build): unpadded black islands at 4096 outline every seam at
  range; (0,255,0) normal padding is an invalid direction; tangent-space texels with z < 0 shade inverted. AO baked with
  the LOD copies renderable gives medians of 3-40. All four are fixable at packing time (pad, flat refill, |z|, AO floor).
- **v27 wipers from existing geometry** (grade: Build, `anim_list.json` holds both clips): when a source cab already has
  static wiper arms (here inside the interior object), split them out by connected piece in a windscreen-base box. Put
  the pivot at the arm end that is lower and further forward (the spindle); the blade is centred on the other end.
  Remove the decimated copies from the LOD1-3 interior by distance (< 4 mm) to the LOD0 wiper surface. Add the pivot
  bones after authoring (edit mode on the rig is fine there). Pick the sweep sign so that the tip rises. Add the new
  bones to any fixed-baseline bone audit.
- **v28 "mud comes all inside the car"** (grade: Game report; fix Build): wheel-spray particles pass through any part of
  the cab that no collision hull covers. The L275's cab floor hull had been built from body-mesh points since v3, but
  the floor lives in the interior object, so the hull was a 14 mm sliver and the footwells were open. Check every
  region hull's volume: a volume near 0 means its source points were missing. The `cutoff_volume` the cockpit camera
  shows in first person (its `boundingVolumeObjectName`) must sit inside the shell, and it must carry a UV set: a
  hand-built hull without UVs crashed tplexp (return -1, no log).
- **Read cab textures before adding fittings:** the "missing" sun visors were flat liner-coloured panels in the interior
  mesh. A render reads them as headliner, so look at the source mesh pieces first.
- **Stopping a background ship script** (TaskStop) can leave its game-wait loop running. That loop later wrote
  recipes from a stale tree, and mod-recipe does not overwrite an existing output. Use a fresh recipe name for every
  attempt, and check for orphan processes.

## L275 v29-v30: a clean interior from the original part colours (Claude, 2026-10-13; Build, not driven)

Owner: "All the textures are a bit of a mess ... I need a clean interior". Shipped as v29 `b456af66...` and v30 `b2754f58...`.

- **Check what "the original" really is before re-baking** (grade: Build). The Sketchfab LC79 interior had no textures:
  it was flat-coloured parts. Every later map was a bake of a bake at about 0.24 px/mm. Matching each face of the
  game mesh to its source part by nearest surface (p99 0.8 mm, 0.06 % unmatched) lets the atlas be painted per part
  from a palette. Draw it at 2x and box-filter it down, so part edges are anti-aliased and sharp at any texel
  density. Use faint grain only. Per-part colour-family clean-ups (light / mid / dark) draw hard-edged blotches
  wherever the source has soft stains.
- **Labels live where the mesh put them** (grade: Build): tiny flat glyph pieces in a body mesh pick up the body
  atlas's density and smear. Move them to their own object on a solid swatch, so the geometry draws them.
- **Mirroring an interior LHD -> RHD** (grade: Build, renders) also mirrors any centre-stack controls whose labels
  live elsewhere, and real RHD vehicles keep the LHD stack. Mirror the stack pieces back (positions, face winding, and
  the custom corner normals with x negated), then check the knobs against their labels.
- **Install guard vs another session's SDK work** (grade: Observed): `asset_importer.exe` from another mod's build
  blocks the install (BLOCKED_PROCESS, nothing changed). Wait for every SDK tool to exit before the final install.
- **Long travel needs IK slide for the straight-line slot path** (grade: Build arithmetic; owner feedback Game). First
  drive (forklift tilt screenshot): "I want it to be able to flex here": droop 0.28 / 0.32 m left the lifted side's wheels
  hanging. v3 (`ccfb1d8c...`) droops 0.45 / 0.55 m. Independent axle frames move straight up and down, not on the
  A-arm's arc, so an arm aimed at its slot gets ~0.30 m longer at 0.45 m droop (lower A-arm, 0.69 m long); the old
  +-0.12 PRISMATIC range would have left the arm short of its upright. Compute each chain's length change over
  -bump..+droop before choosing slide ranges, and skin such links with rigid ends and a stretching middle rather than
  a hard split (a split opens a gap on extension).
- **More droop does nothing without preload** (grade: Game owner report; cause confirmed from code by the laptop,
  physics_semantics.md "Unloaded wheel rest", 2026-10-14). v3's droop 0.45 / 0.55 with height 0.153: owner "worse now ...
  wheels still don't droop" in the same forklift tilt. An unloaded wheel settles at the spring neutral (position =
  height), so a droop stop below the neutral is never reached. Retail scouts preload: Armiger height 0.275 / max -0.05,
  Minuteman 0.33 / -0.08, Invictus 0.38-0.30 / 0 (neutral at or past the droop stop). v4 (`87f431d1...`): neutral 0.02 past
  the droop stop (max -0.02), height 0.42 / 0.50, strength 0.0053 / 0.0050 for rest as modelled at beta 105, damping
  0.10 / 0.11. It rests on its bump stops if beta is nearer 58. **Open** until the next tilt and drive.
- **Softened for preload, re-balance the damping** (grade: Game owner report on v4; fix Build, Inferred). v4 fixed the flex
  ("That fixed it"), but "wheels feel like they have no weight and follow the road too perfectly ... dont bounce".
  Preloading cut strength ~2.7x while damping fell only 0.14 -> 0.10, so damping / strength rose to ~19 (retail Armiger
  ~10, Apoc buggy chatter at ~6.7). v5 (`fbc12bd8...`): damping 0.06 (~11x) and wheel mass 95 -> 130 kg (Armiger 125).
  When strength changes, scale damping with it; the ratio band 7-10 is an inference from three vehicles, not a law.

## WALL-E r2 stability investigation (2026-10-05)

Current status and the complete follow-up are in the [WALL-E stability case](../docs/case-studies/walle-stability.md). The notes below retain earlier checkpoints, including conclusions later rejected.


The owner reported tracks vibrating while resting and failure to drive straight, and
authorized autonomous repair. The installed package matched registered r2 (SHA-256
`dc3936a7d03bb090e41315dc30cb0eb60d56733058d1d9d2f855b08fb4aa5fa0`). A new isolated
bench copied the packaged classes/models and recorded member identity, rather than
assuming the existing experimental editor project matched the installed build.
Baseline forward drift was 2.04 m over 15.72 m settled displacement; native parked
captures reproduced belt deformation with stationary wheels. Terrain-contact telemetry
corrects the earlier WALL-E flat-pad claim. Failed parameter trials remain recorded.

Shared integration adds `straight`/`idle` bench schedules and phase stability metrics
with six regression tests (17 bench-related tests passed), and records the distinction
between rendered belt stability, wheel/chassis telemetry and retail acceptance.
The investigation record is `stability_20261005/` in the WALL-E project; candidate and
installation results will be appended when validated.

### Rejected damping-only package replay (2026-10-05)

**Game, isolated editor:** the first damping-100/tension-1 trial looked promising
(forward lateral 0.433 m), but exact r3 package replay produced 2.697 m forward lateral
error and 0.624 m reverse error. The five gameplay resource snapshots are semantically
identical, so the discrepancy is not a package/source mismatch. **r3 is rejected and was
not installed.** This corrects any provisional conclusion based on the first run.
Higher damping alone is not a reliable straight-driving fix; repeat tests before installing.
The tension-1 parked belt remedy remains supported independently. Lateral support plus
damping 100 improved straightness but weakened steering (17/27 deg in 4 s), so that setup
also remains experimental. Critical-collision quality alone and disabled wheel-spin impulse
triggers did not solve the wandering. Further steering/contact tests are in progress.
Evidence: WALL-E `stability_20261005/bench/runs/release_straight_051641`, input snapshots,
`critical_straight_052104`, `noimpulse_straight_052413`; candidate registry records rejection.

### Tension-1 conclusion corrected after driving (2026-10-05)

**Game, native framebuffer review:** `stable_rear_straight_00.png` and `_03.png`
still show the upper belt changing outline after the drive, despite stationary chassis
and wheels. The earlier tension-1 parked sequence looked steadier than r2/zero tension,
but it did **not** establish a complete belt fix. Do not release on telemetry alone.
Further belt-tension/geometry diagnosis continues. Rear-only lateral support plus
damping 100 produced two steadier sustained-drive trials (yaw ranges 7.16/5.52 and
8.33/8.97 deg forward/reverse), with wider powered turns. Stock-crawler brake strength
0.35 stopped initial wheel creep in the measured combined run. These remain experimental.
The correctly bounded compliant-axle attempt also stalled before viewport readiness;
no physical outcome is inferred from that startup failure. Steering-curve experiments
did not recover tight powered pivots. All records remain in WALL-E `stability_20261005/`.

### Rear-only support and critical-collision follow-up (2026-10-05)

**Game, isolated editor:** rear-only lateral support, damping 100, parking strength
0.35 and reverse wheel resistance disabled improved forward yaw across multiple runs,
but the longer reverse tests still showed 16-19 degrees settled heading range and
an initial direction kick. Removing engine jerking did not resolve this. The combined
critical-collision trial (`stable_final_straight_055545`, an exploratory name, not a
release) worsened forward deviation to 9.746 m / 34.90 degrees over 30.46 m; rejected.
The simpler `stable_candidate_straight_060258` measured 0.560 m / 6.33 degrees forward
and 0.486 m / 16.15 degrees reverse, with whole-phase reverse yaw -21.1 degrees.
This is not yet a complete fix. Both-end lateral support is being retested with
full-lock steering to assess the straightness/turning tradeoff.

Tension 10, independently, kept the parked belt outline steady in native captures
after sustained driving and coasting (`stable10_*`, `stable_candidate_straight_*`).
Tension 1's earlier post-drive failure remains recorded. Braking strength 0.35 does
not universally eliminate initial physical wheel creep: some fresh-spawn runs still
showed roughly 0.3 rad/s on one wheel while the chassis moved less than 1 mm. Distinguish
that from the large animated-belt deformation. Whole-phase metrics are retained beside
settled windows so launch yaw is not hidden. No successor package has been installed.


### r4 replay and remaining drift (2026-10-05)

**Game, native editor:** all four wheel slots with lateral support, tension 10, damping
100, reverse wheel resistance off and handbrake strength 0.35 produced steady belts and
lower yaw variation. Pre-package straight settled lateral/yaw: forward 0.067 m / 3.65°,
reverse 0.132 m / 8.40°. Exact r4 replay: forward 1.100 m / 7.96°, reverse 0.486 m / 7.39°.
Normal turns remained available (63.5/67.2° over 4 s, 2.35/2.34 m displacement), but
full-lock turns are wider. r4 is held for further tuning, not installed. It retained 333
of 337 archive member occurrences unchanged; source/BRO mirrors and all build checks passed.

Sideways friction 0.05 worsened both straight directions (2.790/1.310 m lateral). A neutral
steering curve ending at -1 did not recover tight zero-throttle pivots (11.8/14.8 m travelled
over 8 s); an automatic 1-to-2 shift occurred during the first turn. However, the r4 straight
drive stayed in first gear, so shifting does NOT explain its remaining drift. Brief wheel
spin spikes remain; lower torque with this support layout is the next hypothesis, not a fix.

Evidence: WALL-E `stability_20261005/bench/runs/stable_all_straight_060956`,
`stable_all_grip05_straight_061557`, `stable_all_neutral_straight_062136`, and
`release_r4_park_062837`. r4 SHA-256
`dc0432859804ea5eb67d218b46e55ade2922e9286fc2abc3427285203acd6e36`;
recipe `recipes/stability-r4-build-01.json`; build job `20261004T202639Z-985df53414af`.
Whole-phase output has a launch-kick regression; 18 bench and 9 workflow tests pass.


### r4 rejected after repeat (2026-10-05)

**Game, native editor:** the unchanged r4 repeat failed consistency: settled forward
1.404 m / 14.31° and reverse 2.282 m / 21.39°. It also fails the planned whole-phase
baseline-relative check (at least 25% lower lateral/displacement ratio and 50% lower yaw
range in both directions of every replay). r4 is now rejected and was not installed.
The original 1.100 m replay and all repeat results are retained, not cherry-picked.
Lower torque (7000) with the same four-wheel support improved forward lateral error to
0.110 m, but reverse yaw range grew to 12.98° and speed fell; it was not selected.
The belt remained visually steady at tension 10 throughout the reviewed parked sequences.

Next hypothesis is drivetrain topology: separate the differently sized powered front/rear
wheels into a driven rear sprocket and free front idler per side, with proportionate torque
and speed targets. This is experimental and not established as the cause. Retail EPEC
uses side-grouped real end wheels with isRear omitted, so neither interleaving slot order
nor blindly adding isRear flags is supported as a fix. Evidence is under WALL-E
`stability_20261005/bench/runs/release_r4_repeat_straight_064326` and
`stable_halfpower_straight_063619`; exact resources remain in the per-run snapshots.


### Rear sprocket tests did not solve straight driving (2026-10-05)

**Game, native editor; WALL-E only:** on the tension-10/all-lateral/damping-100
base, front idlers (`torqueType=none`) and rear drive, torque 7000 and half-speed
gear table stalled forward (1.60 m settled; one rear spun at 8–10 rad/s while
the other barely moved). Restoring the original gear table and locking the
differential in both RB and gearbox controller removed the stall (45.86 m
settled forward, 13.64 m reverse), but normal steering produced only 4.7/3.2
degrees and full-lock steering 2.0/0.5 degrees: rejected. Runtime diff-lock
was verified on. Those two changes were combined, so the cause of the recovered
forward drive is not isolated. Do not recommend permanent diff lock as a crawler
straightness fix without measuring steering.

SDK `PropRigidBodyStabilizer` changes solver deactivation/sleep only; its name
does not imply a heading controller. This inspection does not identify a new
fix. Evidence: `stability_20261005/bench/runs/rear_sprocket_straight_064931`
and `rear_sprocket_locked_straight_065525`; per-run source snapshots retained.


### WALL-E r5 owner follow-up (2026-10-05)

**Game (owner report):** after testing installed r5, the owner confirmed track
flapping was fixed and said the remaining wandering was not that bad. Flapping
was the principal complaint. The working version stays r5; the numerical
repeat failure remains historical evidence. Scope, exact package/transaction,
and prior failed experiments are in [the stability case](../docs/case-studies/walle-stability.md).


### KGS-25 current identity and WALL-E transfer review (2026-10-05)

**Build:** read-only inspection found installed KGS-25 matches the October3
curb repair, SHA-256 `bcb343c6bd5abe398d0c580b3c43fd3e78eee75fb9254e340223b8b430b87114`.
This supersedes historical statements that fix2 is still installed. The later
repair adds four raised ramp contacts and preserves the fix2 ground support.
It retains low belt tension and engine jerkingScale2. WALL-E suggests isolated
belt-tension and torque-pulse tests, plus separate visual/physical measurements;
none has yet been tested on this KGS build. See
[the scoped comparison](tracked-vehicles.md#applying-the-wall-e-findings-to-kgs-25-2026-10-05).


## WALL-E r6: head and eye animation without custom SSL (2026-10-11)

**Request:** "custom ssl script for a function for walle to turn his head around and look around and eyes
move". Custom SSL cannot ship (build-pipeline.md, 2026-10-05 probes), so the feature was built from the game's
data-driven animation route ([animated-parts.md](animated-parts.md)). The owner chose all four behaviours (wake
up / power down, a look-around key, idle glances, glances into turns), eye lamps following the eyes and a fixed
first-person camera.

- **Build:** head / eye bones and five clips in the body model (Blender Actions, `anim_on = True`); r5's class
  and markup tuning reproduced unchanged; the main class gains `prop_animation_controller` and a "Head"
  blueprint (54 nodes). Package `d1260fdb...`: only the body model's four compiled files and the main class and
  descriptor differ from r5; lint 0/0, package audit passed. Installed over r5 with a receipt.
- **Bench (Game, editor play mode):** asleep pose held at spawn and eased upright after engine start; clips
  played; turn rate measured in deg/s (the first threshold, 0.2, fired on straight-line jitter; set to 12);
  idle glances verified with a shortened wait. Blender renders of each pose caught an over-strong asleep
  pose (22 + 26 deg looked face-down; shipped 12 + 18).
- **Open:** the owner's view in the game, the Ctrl+K key, lamp beams following the eyes.

## Zukterra Jimny recovered as a native RoadCraft scout (2026-10-05)

**Build:** recovered the owner's compiled SnowRunner CombineXMesh assets into editable sources and rebuilt the Jimny body, stock bumpers and normalized BFG master wheel with the RoadCraft SDK and Blender 5.0. The first source importer left skinned running gear and the steering wheel detached; the corrected weighted bind reconstruction and summed duplicate influences are documented in [frames](frames.md#recovered-snowrunner-combinexmesh-bind-poses-jimny-2026-10-05). The donor Lynx BRO had `addToPreviewLibrary = False`; enabling it produced the two missing preview catalog roots. The first pack failed on the donor tyre-trail PCT references; copied the three SDK trail texture/descriptor families under `mod_jimny_trails_*` and regenerated the wheel classes. Native lamp-kit lens states and fitted beam anchors were authored, and the cockpit camera was placed on the right-hand-drive side.

Native package followed by the established Mod Manager brand export produced `f75d755e776583206251d763bfa6f5c74b087e33391590f3bd2ae8e4b2bf8ef6` (22709479 bytes). Package/retail checks: 2058 passed; saved-Blender checks: 477 passed; final rig checks: 30 passed; BRO/compiled lint: zero errors or warnings. Pinned test `20261005T112651Z-0626b985f399` passed against recipe `recipes/jimny-v2.json`. Evidence lives in [C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005](C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005), especially `reports/package.json`, `reports/retail_export.json`, `reports/source_inspection.json`, `reports/validation.json` and its test job receipt. The delivery ZIP contains the retail PAK and editor assets only. No installation, native driving capture, handling acceptance or campaign acceptance is claimed; `project.json.accepted` remains empty. The original recovered mod assets were retained.


### Jimny revision: 31-inch tyres and 4-inch lift (2026-10-05)

**User feedback:** the first wheels looked too large; requested realistic 31-inch tyres and a 4-inch lift. **Build:** replaced the first 34.6-inch setup with 31x10.5R15 geometry and matching compiled physical dimensions. The lift is 101.6 mm over an explicit stock-height reference, excluding the 59.7 mm gained from tyre radius. Reposed the axle-bound skin, fitted collision and cameras/emitters/winch anchors to the revised stance, and retained stable joint/catalog names. Revised wheel mass is 40 kg; suspension bump allowance is 0.13 m to retain modelled belly clearance. These are authored settings, not native handling measurements.

Candidate `jimny-31in-4in-v2`, PAK `469c1afda17f09631bea0f69ea75704b9f28d92b1b942fe2a4fda78e2d24d13f`, passed 2058 package checks, 481 saved-source checks and 36 final rig/physical-dimension checks, plus shared lint with no errors or warnings; test `20261005T114212Z-d1dec4be0149` passed. Previous PAK, editor ZIP, assembled Blender model, preview and reports were preserved under `Jimny_RoadCraft_20261005/revisions/jimny-v1`. New source/preview, delivery and receipts are in [C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005](C:/Program Files (x86)/Steam/steamapps/common/RoadCraft/Roadcraft Development Package/Jimny_RoadCraft_20261005); see [the dimension/lift lesson](suspension-and-wheels.md#requested-tyre-inches-and-lift-reference-jimny-revision-2026-10-05). No installation or driving acceptance was performed.


### Jimny recovered mod: polish pass, 2026-10-05

**User request:** retain realistic 31-inch tyres and a four-inch lift, check for a 90-degree chassis rotation, and polish/finalise the mod. **Build:** native chassis and axle bases were already identity, so the global rig was retained. Added orientation and sampled collision-clearance gates, steering-column alignment/native cockpit control, disjoint red tail/brake and white reverse emitters with rear-facing beams, clear Blender preview glass, four recovery points declared in the original XML, and tyre-track scale 1.0 instead of the donor's 1.8. All 498 saved-source, 53 final and 2,106 package checks pass; shared lint is clean. The package SHA-256 is a1f4618358bc0fc71ba79260ae0449e8abf63c2dd4913c0f0c1af15f962ddef3. Prior v2 bytes and reports are retained in revisions/jimny-31in-4in-v2.

An isolated editor fixture was prepared without launch. Owner go-ahead for focus-taking drive tests was requested and remains pending at this record; the candidate is not labelled Game-tested or accepted. Loaded suspension height, live axle/steering/lamp operation, driving/braking and retail acceptance stay Open. Static factory-plus-lift height is not a measurement of settled native stance. Evidence resides in Jimny_RoadCraft_20261005/reports and bench_ready; no retail installation was performed.


### Roamer 105 ute recovered conversion: 35-inch polish candidate (2026-10-05)

**User feedback:** tyres looked too large; requested realistic 35-inch tyres, four inches of lift, a correctly oriented chassis and a polished final mod. **Build:** preserved the supplied archive and previous package pins; fitted 35x12.5-inch mesh and physical wheel dimensions; normalised inherited chassis/body bases without rotating the visible truck; restored original suspension skin weights with 14 visual chains, solid axle controllers and source-specific steering names; added six gauges, paired animated wipers, native mirror materials, lamp show/hide states and single-mip shop icons. The export-order wiper failure and its parked-frame repair are recorded in cockpit-and-lamps.md. A donor gearbox would stall below its upshift thresholds on the smaller wheels; shifted targets now stay below each calculated gear top.

**Correction:** the preceding candidate equated suspension `height = 0.1016` with four inches of loaded lift. Height is the neutral spring offset, so the polish candidate includes explicit design sag plus the requested 101.6 mm target and measured-stop geometry. Actual loaded lift is still Open; these are authored estimates. The isolated previous-candidate bench and current-source test fixture are preserved separately. Owner go-ahead for focus-taking editor physics tests is pending; compilation/offline checks are not Game evidence, installation or acceptance. Evidence: project `Roamer105Ute_20261005`, source/fitment/mechanical manifests, native_validation and package audit/receipts.


**Build (Roamer ute clearance follow-up, 2026-10-05):** the recovered frame and front engine boxes overlapped tyre-cylinder samples at full front steering/bump (20 failing cases per saved file). Narrowing those convex boxes to 0.9 m and 1.0 m gave zero overlaps across 331,776 samples in each of the textured and native export sources, at the ideal lift, +/-30 degrees, 130 mm bump and 180 mm droop. Reverse beams were corrected to native -Z and separate 8/45-intensity tail/brake copies retained engine-idle and stop states. Final offline package audit passed 2448 checks; PAK SHA-256 `cb0c2424c639aa7274e2c7a5bfd231ce59b3e4cbbfc1768a04311627e02d46b1`. Evidence: `Roamer105Ute_20261005/polish_completion.json`, `native_validation/collision_clearance.json`, compiled frames and package audit. Settled lift, rolled axles, terrain contact and live lamps remain Open until the approved native run; no install or acceptance.


### Jimny owner-directed installation, 2026-10-06

**User request / Build:** the owner instructed “Just build it and install it”, superseding the pending bench-first sequence. The source/model rebuild passed; the first job (20261005T172856Z-b453d3e25b35) rejected a registry change made after recipe pinning, so preserve/update candidate metadata before pinning. The refreshed job (20261005T173125Z-f103ebb26143) passed prepare/source/import, then its native generator gate refused another project's active editor. That test was left running. Current BROs, both TPLs and the matching generated truck class were byte-verified against the archived polished-v3 source bundle. The unchanged generated classes were retained, the native assets repackaged, and the new pinned test 20261005T173702Z-518ae115b863 passed all three validation steps. No failed build receipt was relabelled successful.

After the editor closed, installation transaction 6736a3b3c7cc4c8391e6cf75bb59b361 installed package SHA-256 e6e88093a47864c7d04d79c0f32ddec07437736e2e276456ae6b09755472ba89 into the previously empty configured slot. Post-copy hash and ZIP CRC passed. Previous absence is retained for rollback; accepted remains empty. Evidence: Jimny_RoadCraft_20261005/reports/{installed_20261006.json,install_receipt_20261006.json,install_test_receipt_20261006.json} and the named transaction receipt. Driving, loaded stance and retail acceptance remain Open.


## Watcher Y61 final conversion (2026-10-06)

**User request / Build / Game, native editor:** owner requested conversion and installation, realistic 35-inch tyres, four-inch lift, and correction of the reported quarter-turned chassis. The final source retains a charcoal expedition accessory mix, 35x12.5R17 running tyres and matched spare, recovered CombineXMesh underbody/steering bindings, three LODs, fitted lamps and source-derived recovery sockets. The final native hinge is valid (-3/+3 degrees); blueprint imports and source-fixture wheel registration were repaired before testing. See frames.md, cockpit-and-lamps.md and suspension-and-wheels.md for bounded findings.

Native normal, harsh, unbraked-idle, 80-second one-surface drive, pad-to-terrain transition and matched lift-reference trials completed. The 1024 m pad prevented the earlier long drive from leaving its flat surface: 156.85 m forward and 70.26 m reverse, all tyres contacting, maximum roll 1.31 degrees and pitch 2.1 degrees. This establishes stability/responsiveness under those schedules, not perfect straightness; the forward whole-phase heading changed 4.3 degrees. The loaded lift measured 103.49 mm against the matched custom zero-extra-lift reference. Native functional checks cover headlight switching, brake/reverse states, cockpit camera/steering, drivetrain state toggles, horn/fuel/water presence and normal winch attachment/pulling/release. Eight FPS observations ranged 56.647-60, median 59.6715 in this capped editor run; no universal hardware or multiplayer performance claim.

Build 20261005T191440Z-2d37692c3fd7 passed exact package/source verification (1473 member occurrences, 1334 exact byte matches, 139 streamed texture descriptors, 98 nodes) and zero lint errors/warnings. Final PAK SHA-256 2f5fcdbe9986a95680bc526d31503953cf729685689a1483d3dfc86ffe46c121. Authorised install transaction e2f857cefece4ffdbcff52974bec1cdf preserved the prior d2d0e01248ac951437ad97019a21e67e6317029e304a019671d12de16a27dc0b PAK. Failed startup/fixture receipts remain preserved; no historical failed receipt was promoted to a pass. Campaign save/load, multiplayer and owner acceptance remain Open and accepted identities remain empty. Evidence: WatcherY61_Final reports/{final_build_job,final_native_verification,package_validation,final_install_result}.json and local transaction receipt.


### Roamer 105 ute native finalisation and installation (2026-10-06)

**User authorization / SDK/Game / Build / Install:** the owner explicitly authorized all tests and finalisation after the earlier install-only request. This supersedes the earlier pending-native entries without changing their historical receipts. Final PAK SHA-256 `28458332ba8d2f6b67b80ba92fcaff1dc357d64b1ba289b8c78cd884d6f22953` passed 2,448 package checks, all 83 native release gates and 648 configured shared tests (641 passed, seven skipped). Lint has zero errors and warnings; its generic suspension uncertainty info is complemented by actual native stop-margin/contact samples.

Native tyre dimensions are 0.889 m diameter / 0.3175 m width. Loaded axle means measured about 100.8/100.5 mm, with 102.7/105.2 mm additional lift against an independently calibrated zero stock-bind reference. The final four drive schedules recorded 2,727 samples, correct negative reverse velocity/gear, all four contacts and upright chassis. Normal-drive, full-throttle, unbraked-idle and harsh-steering/braking evidence uses deformable editor terrain, not a claimed perfectly flat static test surface. The missing drag-link terminal hinge, reflected dashboard text and direct headlight-service generator omission were repaired. Ordinary State controls confirmed reverse lamps/beams and service-brake overlays; debug controls alone bypassed those callbacks. The earlier positive-pedal reverse-labelled runs were actually forward and are excluded as reverse evidence.

Failures remain preserved: wrapped YAML redirected the first fixture, nested preview paths exceeded native path capacity, and the first default-current truck was Minuteman rather than the ute. Shared folded-path relocation and signed reverse schedules have regression tests. See physics-bench.md, ik-visual-rigs.md, cockpit-and-lamps.md, suspension-and-wheels.md and symptoms.md for scoped lessons.

The tested PAK replaced installed `cb0c2424c639aa7274e2c7a5bfd231ce59b3e4cbbfc1768a04311627e02d46b1` in transaction `60c1dc8bdc91478a90bb7d494f859525`, with exact prior bytes retained. The ZIP contains final PAK, packed Blender artwork, native project, README/checksum and helper licences. Evidence: Roamer105Ute_20261005/native_validation/final_native_report.json, loaded_lift_final.json, package/{audit,build_receipt,delivery_receipt}.json, polish_completion.json and R105Final_20261006/runs/sealed_final_suite_all_070751. Retail campaign shop/save acceptance and deep-water behavior remain Open; installation and native editor proof do not invent owner acceptance.


### Jimny native finalisation and installed release (2026-10-06)

**User authorization / SDK/Game / Build / Install:** owner requested all tests
and finalisation after explicitly authorizing installation. This supersedes the
pending-native entries above while retaining their historical receipts. Final
package `3bc1828f04777872234f6e809b4a9bbc671f552afa93e31b70c3404721c1532a` passed 2,106 package checks, 498 saved-source
checks, 59 final static checks, 439 native release checks and the configured
shared suite (645 passed, seven skipped; 652 run). New RC049 checks and four
regressions reject enabled deforming wheels without the required compiled tire
mesh. All four pinned release steps passed in `20261005T235201Z-15acf5228d88`.

Native final driving records 2,650 samples across ordinary normal/full-throttle,
unbraked idle and harsh steering/braking schedules. Full-throttle forward moved
196.88 m and reverse 52.59 m; actual gear -1 and negative wheel/forward velocities
establish reverse. Chassis stayed upright and springs retained stop margins;
rest had four contacts. Radius 0.393700004 m and width 0.2667 m match 31x10.5-inch
tyres. Loaded mean residual is about +0.58 mm and every wheel within 4.1 mm of
the authored four-inch reference. This is body-frame calibration on deformable
SDK terrain, not an independently measured stock vehicle or a perfectly flat
static pad. Source chassis and axle bases remain identity; native underside,
exterior and cockpit captures were reviewed separately from numerical gates.

Startup initially asserted `failed to find deforming geom obj with name 'tire'`
because recovered wheel objects had project-specific names. Native tire/rim
identities repaired this. Wrong editor data, unresolved paths and an assumed
joint requirement for a single-body rig were fixture faults, retained as failed
runs. Ordinary State/AUTO negative pedal fixed the debug-only reverse stall as
a test protocol correction; the gearbox was not changed on that inference.
Headlight service ownership and explicit recovery sockets were restored after
generator omissions. Winch attachment, pulling (7.950 to 3.956 m rope) and
release passed. First-person cockpit mode is necessary for live dashboard
steering updates. CSV vector transport repaired a PowerShell `-File` array
binding failure. An invalid trail object-reference equality gate was corrected
using the existing Lada lesson: both descriptors exist and their full compiled
values match; isMod=false editor runtime does not prove retail reset behavior.
Original failure reports and off-center recovery captures remain retained.

Transaction `a6a8c1052c8c4a329b59d4122485d3b5` replaced installed
`e6e88093a47864c7d04d79c0f32ddec07437736e2e276456ae6b09755472ba89`, preserving exact previous bytes. Installed
PAK hash/CRC and final delivery CRC/file parity pass. Delivery contains final
PAK, packed editable Blender/native sources, README, verification summary and
checksums. Accepted remains empty; campaign shop/save, multiplayer and deep
water remain Open, and original cockpit lacks authored gauges/wiper clips.
Source-check has no accepted inventory; saved-source checks and recipe pins
provide current-source verification without manufacturing an accepted baseline.

Evidence: `Jimny_RoadCraft_20261005/reports/{native_final_report,visual_review_final,
native_loaded_final,finalisation,final_install_receipt,delivery}.json`; final
drive `J31TestF_20261006/runs/final_all_092833`, services retry
`final_services_all_093912`, centered native views `final_views_all_094631`.
See physics-bench.md, suspension-and-wheels.md, cockpit-and-lamps.md and
symptoms.md for the integrated scoped findings.

### Jimny 2014 chassis reference and pending v7 detail (2026-10-06)

**Owner choices / primary reference / Build:** the owner requested full
suspension, brake-line and harness detail, red/gold hardware, 31-inch tyres and
a four-inch lift, referencing late-2014 Australian RHD hardware. The owner
explicitly retained the recovered approximately 2485 mm wheelbase rather than
the factory 2250 mm. The mod therefore remains a custom-proportion Jimny.

Suzuki Australia's October-2014 brochure establishes ladder frame/eight body
mounts, rigid axles, three-link suspension, separate springs/shocks and ABS/ESC.
Suzuki's November-2014 specifications establish recirculating-ball steering,
front stabilizer and disc-front/drum-rear brakes. The older SN413 factory manual
is the mechanical baseline, not proof of late ESC routing; genuine RHD ABS/ESP
FIG.503J supplies the brake-circuit reference. The 100 mm supplier kit listing
supports corrected arms, panhards and extended hoses. Exclude rear disc swaps,
coilovers, JB74 hardware and the non-ABS brake-balance bracket. Dimensions and
clip locations fitted to the custom source are recorded as adaptations.

Evidence: Jimny references/jb43_2014.json (primary links and adaptation manifest),
reports/suspension_assembly.json and saved-source checks. Existing installed v6
and its receipts remain preserved. Native v7 build/closure and installation
are pending; campaign acceptance remains empty. A sandbox profile-access failure
retained native job 20261006T051231Z-100f279ab248. Shared jobs-recover requires an
accepted package; this project's verified installed candidate does not qualify.
Automatic review rejected unapproved manual lock release. Do not fabricate an
accepted pin or remove the lock blindly. Candidate-only recovery currently
requires explicit owner approval and rechecks of exact bytes/closed processes.


### Jimny v7 installed for owner testing (2026-10-06)

**Build / SDK / Game:** The owner explicitly approved candidate-only recovery,
rebuild and installation. Recovery rechecked dead job ownership, closed native
processes, installed v6 hash, empty acceptance and transaction state, and kept
failure/recovery receipts before releasing only the exact abandoned locks.
The accepted-package recovery limitation was not bypassed without approval and
no accepted identity was fabricated. Initial profile permission and subsequent
package failures are retained. See the scoped atlas/closure findings above.

Full build job 20261006T074204Z-dff1b4564bb2 passed; pinned test recipe
jimny-suspension-v7-test-r8 passed saved-source, suspension, wheel-reference,
final vehicle and static checks. Native capture job
20261006T074623Z-85eace0321b0 passed an isolated normal-state drive, service,
steering-pose and brake protocol. The drive applied 9/9 controls, recorded
626 samples, moved forward/reverse and turned both ways while upright and
inside suspension stop margins. Native visual audit passed 437/439 checks;
full-lock drag-link gaps remain Open. The prior 652-test toolchain suite had
645 passes and seven skips; it is tooling evidence, not v7 campaign acceptance.

Candidate `jimny-suspension-v7-test`, package SHA-256
cb9dd34ab99f27830eee6ae931ea4fecde0bf062b8dc3fcbd9ddebcbbb048cd7,
was installed transactionally with v6 rollback bytes under transaction
31c9e648a6da4b20b97254c2ecad93db. Installed bytes were independently rehashed.
Reports: suspension_v7_test_candidate.json, suspension_v7_native_capture.json,
suspension_v7_install_receipt.json. Status is an installed test candidate with
open visual findings; it remains unaccepted pending the owner's retail drive.
Added steering joints warrant a newly purchased vehicle for a clean test.


### Owner quality rejection: Jimny and Roamer ute (2026-10-06)

**Owner feedback / Open:** The owner reports inverted wheels on one side,
incomplete lighting and incorrect rigging/animations in the Jimny/Roamer ute,
and materially better Lada quality. This supersedes any broad final/polished
assessment of these vehicles; prior bounded tests and package identities stay
preserved. No retail acceptance follows from successful compilation or counts.
Exact fault-to-vehicle allocation and root transforms still require reproduction.

**Build audit:** Jimny slot-position/radius assertions do not verify outward rim
facing; its Blender preview applies an assumed left half-turn. The existing
Lada native-frame lesson was therefore not enforced as a handedness check.
Roamer seal_native_release.py accepts any wiper tilt and image size >10,000
bytes, which do not establish correct sweep/park or visible feature quality.
Jimny v7 has 437/439 native visual checks passed and two real drag-link closure
failures (up to 63.2 mm). Jimny v6's absent gauge/wiper clips were documented,
and its source disables tplAnimation/truckRainSettings; missing features should
not be presented as complete animation support. Shared helper opt-in and broad
release wording allowed verified subsets to be mistaken for finished quality.

Evidence: Jimny reports/quality_feedback_20261006.json, tools/validate.py,
tools/preview.py, tools/build_bro.py, reports/suspension_native_checks.json;
Roamer seal_native_release.py, polish_completion.json. The Lada comparison is
the owner's assessment; this audit did not reproduce the reported retail faults.
Repair requires measured facing of all four native rims, an inventory of every
visible lamp/state, motion range/axis/park verification and attachment closure,
with visible review tied to the exact installed candidate. Asset-specific
regression checks must follow reproduced causes; no guessed handedness fix or
automatic shared threshold change was applied in this explanatory audit.

## KGS-25 v10: the ground-run radius (2026-10-22)

Owner's v9 verdict (Drive Queue): every handling check passed, but "idler wheels need to be bigger as objects can
get between and cause it to get stuck" and "gets covered in mud even when on concrete". Offline comparison against
the EPEC TC305 and Greenway HT500 found the one layout fact every earlier pass had kept: the KGS carried its weight on
hidden physics wheels of 0.27 m rolling radius, under half of any shipped crawler's (0.39-0.58 m), because its visible
road wheels were bigger than its physics wheels where vanilla does the reverse. v10 raised the 14 contact slot bones
0.22 m and set the contact radius to 0.42 m (ground line, art and belt unchanged; validate 0 new, lint 0 errors) and
added the retail wheel covering flag. The owner after the first drive: "What did you do? That made such a difference,
it feels so nice now" (Game). Lesson recorded in tracked-vehicles.md ("Vanilla ground run", recipe step 8). Still
open there: the shoe pitch overlap (0.175 m shoes on a 0.137 m pitch) and whether the covering flag cured the mud.
Evidence: kgs25 final `tools/raise_contacts.py`, `tools/ground_run.py`, `logs/validate_v10.json`, README "Tracks
against vanilla".
