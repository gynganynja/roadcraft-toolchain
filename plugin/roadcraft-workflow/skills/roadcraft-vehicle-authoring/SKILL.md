---
name: roadcraft-vehicle-authoring
description: Author, fix or review a RoadCraft vehicle mod (scout, truck or machine) with the vehicle-authoring library in RoadCraftToolchain - rig, wheels, suspension, IK linkages, truck settings, lamps, textures, build and install. Use when turning source art into a RoadCraft vehicle or when the game shows a vehicle fault; D11 identity, package and storage work belongs to roadcraft-workflow.
---

# RoadCraft vehicle authoring

The library in the checkout's `library/` folder is the memory of every vehicle built so far: how the
engine, the SDK generator and the retail vehicles behave, each rule with an evidence grade (Game,
Retail, SDK, Build, Inferred, Open; see `library/README.md`). Read it before deciding, and prefer a
Game or Retail rule over a guess. Locate the task's RoadCraftToolchain checkout; a cached plugin
directory is not the project.

## Start

- `python -m roadcraft library` lists the articles; `python -m roadcraft library --search REGEX`
  finds a rule. Direct source execution needs the checkout's `src` on `PYTHONPATH`.
- A fault seen in the game: `library/symptoms.md` first. When something *stopped* working, read the
  game's script crash dumps before the rig.
- A new vehicle: copy the newest mod project's layout (`library/build-pipeline.md`), then read
  `frames.md`, `suspension-and-wheels.md`, `ik-visual-rigs.md`, `truck-settings.md`.
- Unsure how something compiles: compare with shipped vehicles (`python -m roadcraft retail find
  "*name*"`, `retail bro`, `retail show`; `library/retail-data.md`).

## Rules that each cost a drive when missed

- A suspension collection needs `useSuspensionCollection = True`; `height` is the spring's neutral
  offset (design sag + lift), never 0. Design and check axles with `python -m roadcraft suspension`,
  keeping every case (including `measured`) off the stops.
- Set `maxSteerSpeed`, `backSteerSpeed` and `pedalsResponsiveness`; the defaults are instant.
- Wheel slot joints move only under `axleControllerSettings`: list every slot the rig hangs parts on
  or pins chains to; steered knuckles need a steering rack.
- Identity wheel slots show the wheel model unchanged on both sides: one wheel model per side.
- Do not copy the SDK TUZ Lynx sample's truck settings.
- Renaming, adding or removing a controllable joint breaks vehicles already in a save: tell the
  owner to sell and buy the vehicle again.

## Checks before handing over a candidate

```text
python -m roadcraft lint-bro <truck.bro> --class <auto_mod.cls> --tpl <body.tpl>
python -m roadcraft suspension --axle '<SuspensionAxle JSON>' --share <one wheel's weight share>
python -m roadcraft tpl-nodes <body.tpl> --pattern <bone regex>
```

Add the mod project's own rig audit and static validation. None of these proves how the vehicle
drives: the owner's drive is the acceptance, and a candidate stays unaccepted until then.

## Working with the owner

- The owner installs or approves each candidate, drives it in the retail game and reports. Never
  write an installed hash into `accepted`.
- Do not launch the editor (hidden class generation included) or the game while the owner is using
  the PC; say what is queued.
- Install only with the game and editor closed, keep the previous package and a receipt, and
  announce every install. Ask first unless the owner's request covers installing ("install it",
  "just fix it").
- "What is wrong with X" means: find the cause, say it in a line or two, then fix, build and install.
- Another agent may work on the same mod elsewhere: build in a folder of your own, leave theirs alone.
- When the named game is not installed, ask which game is meant.

## Recording what you learn

After each drive report, update the library in the same change as the fix: the rule and its grade
in the subject article, the symptom in `symptoms.md`, the build and the report in `case-studies.md`.
When a drive contradicts a rule, change the rule and its grade and say what replaced it; keep the
old evidence. Calibrate the suspension beta from observed rests (`python -m roadcraft suspension
--calibrate`) and record the result. Keep personal paths, account details and installation state
out of the library.
