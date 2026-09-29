---
name: roadcraft-vehicle-authoring
description: Create, modify, fix or review a RoadCraft vehicle or machine using shared rig, wheel, suspension, IK, truck-setting, lamp and material findings. Use for new source art and existing vehicle mods; the roadcraft-workflow skill handles project identity, builds, packages and evidence for all mod types.
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
- A new vehicle: use `roadcraft mod-init --directory PATH --name MOD_ID --kind vehicle` for the shared
  layout, then supply the vehicle-specific art/adapters and read
  `frames.md`, `suspension-and-wheels.md`, `ik-visual-rigs.md`, `truck-settings.md`.
- Existing vehicle: select its registry and preserve its source route, rig IDs,
  original package and acceptance history. Use `mod-adopt` only for an
  unconfigured source folder. Package-only inputs need usable source or a
  reviewed adapter; do not claim that importing a PAK reconstructs the vehicle.
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

Existing adapters should call `vehicle_workflow.enhance_recipe` so the source,
compiled and final checks run automatically. A new starter declares sources and
commands in `vehicle.json` and `recipe-template.json`; `vehicle-recipe --project
PATH --output NEW_RECIPE` pins them. Shared checks always run, including during
incremental builds. New `mod.json` projects use `mod-recipe`; `vehicle.json`
and `vehicle-recipe` remain supported. Recipe `cacheable` steps need complete explicit inputs,
outputs and dependencies; capture/native-gated steps cannot be cached. Use
`jobs-summary` to measure recorded time, and keep native speedup claims separate
from synthetic tests. Read a machine-local `local/toolchain.json` selector when
present; use its checkout for shared code and accumulated library knowledge.

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
- Diagnose the reported fault, explain the supported cause, and complete fixes,
  builds or installation within the owner's requested scope and existing authorization.
- Another agent may work on the same mod elsewhere: build in a folder of your own, leave theirs alone.
- When the named game is not installed, ask which game is meant.

## Recording what you learn

Follow the maintained checkout's `library/learning.md` whenever a task produces
reusable knowledge: a discovery, failed approach, fix, user feedback, corrected
assumption or workflow improvement. Integrate it during the same task before
reporting completion; do not leave it only in chat or private agent memory.

Update the subject article with the rule, scope, evidence grade and supporting
build/source/test reference. Add faults to `symptoms.md` and project/drive
history to `case-studies.md`. Correct contradicted rules while retaining their
earlier evidence. Turn supported, repeatable lessons into shared checks or
helpers and wire them into the relevant workflow; record why automation is
deferred when it is not yet justified. Validate behavior changes and preserve
existing receipt/recipe pins. Briefly report what was integrated and where,
or preserve a handoff and say why shared integration is blocked.

Calibrate suspension beta only from observed rests (`python -m roadcraft
suspension --calibrate`) and retain the measurement's scope. Keep hypotheses
distinct from proven behavior and acceptance; keep personal paths, account
details and installation state out of the shared library. No new finding
means no forced entry, and this rule adds no execution or installation authority.
