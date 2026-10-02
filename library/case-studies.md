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
  they hang on.
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
