# RoadCraft modding library

Shared workflows and findings for creating and modifying mods. Vehicle findings
come from a CAT 793D, a D11T, a Hitachi EX5600, the
Roamer 105, a 16M3 grader, a 994 loader, an M12 Warthog and an Apocalypse Buggy: how the engine, the
SDK generator and the retail vehicles actually behave, and the code in this checkout that checks for
it.

Start with **[mod-workflow.md](mod-workflow.md)** to create or modify a mod. Use
**[symptoms.md](symptoms.md)** when something looks wrong in the game: it maps what you
see to the cause and the fix. Read the subject articles when authoring:

| Article | Subject |
|---|---|
| [mod-workflow.md](mod-workflow.md) | New mods, existing source/package edits, project selection, build and installation lifecycle |
| [learning.md](learning.md) | Required integration of discoveries, failures, fixes and feedback into shared knowledge and tools |
| [frames.md](frames.md) | Axes, units, bone frames, hinge axes, centre of mass, source-art conversion |
| [suspension-and-wheels.md](suspension-and-wheels.md) | Wheel slots, axle controller, steering racks, wheel models, suspension values |
| [ik-visual-rigs.md](ik-visual-rigs.md) | Visual IK chains: wishbones, uprights, dampers, cylinders, linkages |
| [truck-settings.md](truck-settings.md) | Truck BRO settings: steering, pedals, gearbox, controls, the SDK sample's gaps |
| [cockpit-and-lamps.md](cockpit-and-lamps.md) | Steering wheel and gauges (`dataDashboard`), lamps that work in the campaign |
| [textures-and-materials.md](textures-and-materials.md) | Texture sets, channel packing, material instances, interface images |
| [retail-data.md](retail-data.md) | Where the shipped vehicles' data lives and how to read it, including compiled models |
| [build-pipeline.md](build-pipeline.md) | SDK tools, class generation, packaging, installation, process rules |
| [case-studies.md](case-studies.md) | Each mod built so far: what went wrong and what it taught |
| [sources.md](sources.md) | Official documentation, the community guide, the unofficial route, support channels |

The [D11 case study](../docs/case-studies/d11.md) preserves its source-repair and
capture findings. [Components](../docs/components.md) distinguishes shared tooling
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
roadcraft lint-bro TRUCK.bro [--class auto_X.cls] [--tpl X.tpl]
                                                  known pitfalls (codes RC001..RC032, see bro_lint.py)
roadcraft suspension --sag 0.16 --share 0.25 [--lift 0.06 --bump 0.16 --droop 0.20]
roadcraft suspension --axle '{"min": -0.1, "max": 0.26, "height": 0.22, "strength": 0.0221}' --share 0.205
roadcraft suspension --calibrate '[{"axle": {...}, "rest": 0.12, "wheels": 2}, ...]'   beta from rests seen in the game
roadcraft tpl-nodes MODEL.tpl [--pattern REGEX]   node names, world transforms, parents of a compiled model
roadcraft retail find|show|bro|survey ...         the shipped game's own data (--game or sdkRoot)
```

Python: `roadcraft.ps_format` (read/write BRO and other PS text), `roadcraft.tpl_reader`,
`roadcraft.vehicle` (frames, hinge rotations, suspension model), `roadcraft.bro_lint`,
`roadcraft.retail`, `roadcraft.library`.
