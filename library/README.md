# RoadCraft modding library

Shared workflows and findings for creating and modifying mods. Vehicle findings
come from a CAT 793D, a D11T, a Hitachi EX5600, the
Roamer 105, a 16M3 grader, a 994 loader, an M12 Warthog, an Apocalypse Buggy, a Lada Niva and a KGS-25 crawler crane: how the engine, the
SDK generator and the retail vehicles actually behave, and the code in this checkout that checks for
it.

Start with **[mod-workflow.md](mod-workflow.md)** to create or modify a mod. Use
**[symptoms.md](symptoms.md)** when something looks wrong in the game: it maps what you
see to the cause and the fix. Measure a handling change on the [physics bench](physics-bench.md)
before installing it. Read the subject articles when authoring:

| Article | Subject |
|---|---|
| [new-mod-creation.md](new-mod-creation.md) | Practical creation checkpoints from supplied art through driving, effects, utilities and cockpit verification |
| [mod-workflow.md](mod-workflow.md) | New mods, existing source/package edits, project selection, build and installation lifecycle |
| [learning.md](learning.md) | Required integration of discoveries, failures, fixes and feedback into shared knowledge and tools |
| [frames.md](frames.md) | Axes, units, bone frames, hinge axes, centre of mass, source-art conversion |
| [suspension-and-wheels.md](suspension-and-wheels.md) | Wheel slots, axle controller, steering racks, wheel models, suspension values and their measured stop geometry |
| [tracked-vehicles.md](tracked-vehicles.md) | Crawlers: the retail track layouts, track-frame masses, the KGS-25 fix, checks RC046-RC048 |
| [physics-bench.md](physics-bench.md) | Measuring a handling change in the Mod Editor before installing it (`roadcraft bench`) |
| [ik-visual-rigs.md](ik-visual-rigs.md) | Visual IK chains: wishbones, uprights, dampers, cylinders, linkages |
| [animated-parts.md](animated-parts.md) | Parts that move by themselves or on a key: model clips, `prop_animation_controller`, blueprint triggers; why custom SSL is not a mod route |
| [truck-settings.md](truck-settings.md) | Truck BRO settings: steering, pedals, gearbox, controls, the SDK sample's gaps |
| [cockpit-and-lamps.md](cockpit-and-lamps.md) | Steering wheel and gauges (`dataDashboard`), lamps that work in the campaign |
| [textures-and-materials.md](textures-and-materials.md) | Texture sets, channel packing, material instances, interface images |
| [retail-data.md](retail-data.md) | Where the shipped vehicles' data lives and how to read it, including compiled models |
| [build-pipeline.md](build-pipeline.md) | SDK tools, class generation, packaging, installation, process rules |
| [case-studies.md](case-studies.md) | Each mod built so far: what went wrong and what it taught |
| [sources.md](sources.md) | Official documentation, the community guide, the unofficial route, support channels |

The [D11 case study](../docs/case-studies/d11.md) preserves its source-repair and
capture findings. The [WALL-E stability case](../docs/case-studies/walle-stability.md)
preserves the miniature-crawler investigation, rejected trials and owner-confirmed r5 track fix. [Components](../docs/components.md) distinguishes shared tooling
from historical probes. Apply a case's rules only within their stated scope.

## Evidence grades

Every rule carries one of these, so a guess is never mistaken for a fact:

| Grade | Meaning |
|---|---|
| **Game** | Seen in the game while driving, with the build that showed it: the retail game (by the mod's owner) unless marked "editor play mode" (the Roamer 105's measured runs) |
| **Retail** | Read from the shipped game's own data (every relevant shipped vehicle agrees unless noted) |
| **SDK** | From the SDK's type descriptions, samples or official documentation |
| **Build** | Observed in our own generated classes, compiled models or tool output |
| **Inferred** | A model that fits all the evidence above but has not been confirmed directly |
| **Open** | Not known; what would settle it is stated |

When a later drive contradicts a rule, change the rule and its grade here, and add the drive to
[case-studies.md](case-studies.md). Do not delete the old evidence; say what replaced it.

Every agent must follow [learning.md](learning.md) for new reusable findings
from any RoadCraft task, including non-vehicle tooling work. Update the shared
library and applicable checks/helpers in the same task; private memory or chat
alone does not make the next project benefit.

## Code in this checkout

All read-only unless stated; standard library only.

```text
roadcraft library [topic] [--search REGEX]        these articles
roadcraft lint-bro TRUCK.bro [--class auto_X.cls] [--tpl X.tpl] [--markup X.tpl_markup]
                                                  known pitfalls (codes RC001..RC048, see bro_lint.py;
                                                  the markup beside --tpl's asset is read by default)
roadcraft lamps SPEC.json [--output X.bro]         exterior lens states, beams and flashing beacons
                                                  (roadcraft.lamps; cockpit-and-lamps.md "start here")
roadcraft suspension --sag 0.16 --share 0.25 [--lift 0.06 --bump 0.16 --droop 0.20]
roadcraft suspension --axle '{"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0221}' --share 0.205
roadcraft suspension --calibrate '[{"axle": {...}, "rest": 0.12, "wheels": 2}, ...]'   beta from rests seen in the game
roadcraft suspension ... --geometry measured      stops at height + min / height + max ("Stop geometry")
roadcraft tpl-nodes MODEL.tpl [--pattern REGEX]   node names, world transforms, parents of a compiled model
roadcraft retail find|show|bro|survey|tracks ...  the shipped game's own data (--game or sdkRoot)
roadcraft bench init|apply|run|batch|analyse|compare ...
                                                  physics bench: writes its own bench folder; run/batch
                                                  start the Mod Editor (ask the owner first)
```

Python: `roadcraft.ps_format` (read/write BRO and other PS text), `roadcraft.tpl_reader`,
`roadcraft.vehicle` (frames, hinge rotations, suspension model), `roadcraft.bro_lint`,
`roadcraft.lamps` (lamp graphs, beams, flashers, lamp materials and their checks; Blender side
`roadcraft.blender_lamps`), `roadcraft.load_volume` (dump-truck load volume, borders, native sand-grid
emulation RC040-RC044 and load settings; Blender side `roadcraft.blender_load`; truck-settings.md
"start here"), `roadcraft.tracks` (crawler track layouts, RC046-RC048), `roadcraft.native_suspension`
(measured stop geometry: stop positions, design, rest and calibration), `roadcraft.physics_bench`,
`roadcraft.pak_patch` (patch text members of a built package), `roadcraft.retail`, `roadcraft.library`.
