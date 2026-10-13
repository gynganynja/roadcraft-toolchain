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
  offset (design sag + lift), never 0. The stops sit at `height + min` and `height + max`, so a
  negative `min` raises the top stop. Design and check axles with `python -m roadcraft suspension
  --geometry measured` (min = -(sag + bump), max = droop - sag), keeping every case (including
  `measured`) off the stops (suspension-and-wheels.md "Stop geometry").
- Set `maxSteerSpeed`, `backSteerSpeed` and `pedalsResponsiveness`; the defaults are instant.
- Wheel slot joints move only under `axleControllerSettings`: list every slot the rig hangs parts on
  or pins chains to; steered knuckles need a steering rack.
- Do not infer wheel handedness from identity slots alone. Measure the native rim/object frame: Lada adds a left-side half-turn. Author each asset for its final frame; see suspension-and-wheels.md.
- Do not copy the SDK TUZ Lynx sample's truck settings.
- Crawlers (tracked-vehicles.md, `python -m roadcraft retail tracks`; KGS-25 2026-10-13, bench and drives):
  - A track must not rest on stop fakes alone. Use a retail layout (EPEC TC305: rigid real wheels at
    ground level at each track end beside near-zero fakes). `fakeWheelIds` wheels are full physics
    wheels; only the belt is visual. A track `section.height` of 0 silently turns track steering off.
  - Hang each track frame on a sprung hinge, never a weld (RC047). The retail HT500 uses
    childRotation [0,90,0], +-5 deg, tpl_markup_spring_motor 1e7/1.1e7. Softer (3e6, +-8 deg) let
    the KGS idler conform to a step. Give the frame bodies retail damping (angular 0.05 /
    linear 0), not 1.5 / 0.03.
  - Track wheels: copy a retail crawler's friction tables (frictionValue 0.5-1.0, every surface
    including `default`, `asphalt` and `mud_sand`) and softForceScale (TC305 0.75, HT500 0.55). The
    default of 1 is rigid contact and was the "bouncy hull" cause.
  - Keep the steering curve's full-lock end at -1 like retail. -0.6 cut pivot yaw about 3x with no
    measured judder benefit.
  - Strength has no mass scaling and the sag law is unknown, so calibrate per vehicle.
- Measure a change to suspension, wheels, masses or joints before installing it, against the
  installed version. Use the windowless bench (`python -m roadcraft.bench_headless`,
  headless-bench.md), which needs the owner's go-ahead per run. At minimum run `physics report` and
  `compare --donor`. A formula-designed KGS-25 fix made the crane worse.
- Engine facts that silently waste a fix (validator.md, RC072-RC074):
  - markup objSettings per-object entries (visibility, collision, lighting) are ignored unless
    objSettings.exportedVersion is set, and no mod sets it. Hide parts by name prefix (cdt_,
    hidden_) or blueprint init.
  - A position motor's `spring` is never read; use tpl_markup_spring_motor {spring, damping}
    (N/m or N·m/rad). Position-motor tau is a relative stiffness: raise tau for loaded joints,
    since maxForce alone does nothing.
  - Wheel friction: a missing `default` entry gives 2.0, and a surface with no entry keeps the
    previous surface's friction. prop_truck_wheel bodyFriction/substanceFriction are overwritten at
    start; the real setting is frictionMaterialsList.<material>.frictionValue.
  - A hook or dangling part should hang on a ball-and-socket joint (massFactor 0, no collision). A
    ragdoll's twist axis can be the luff axis and hold the hook at the boom angle (Kanga c10,
    KGS-25).
- A dump truck's back load border hangs from the tail-lid body: the native sand grid spans the four
  borders and composes the back one with its parent's transform (RC036). Build the load and borders
  with `roadcraft.load_volume` / `blender_load` and run `grid_report` before export (truck-settings.md,
  "Dump truck loads ... start here").
- Copy a donor's SFX graph only with its effects (RC026). Stock exhaust and haze emit from rigid
  meshes named `sfx_exhaust_NN` / `sfx_radiator_haze`; look for the artist's light sockets before
  fitting lamp anchors (cockpit-and-lamps.md, Dump Twuck v4).
- Build exterior lamps with `roadcraft.lamps` (cockpit-and-lamps.md, "start here"). Lit `_on` copies stay
  default-visible in the markup and the graph's init hides them (RC037, RC038); a strobe or beacon
  flashes a lit overlay and never switches the unlit lens, or the mesh blinks out instead of glowing
  (RC039). Keep glass and opaque lamp parts off one texture in one object: the exporter keeps one
  material per texture.
- Renaming, adding or removing a controllable joint breaks vehicles already in a save: tell the
  owner to sell and buy the vehicle again.
- Articulated steering and cranes: articulated-steering.md and cranes.md (retail crane IK chains, a slew-less
  crane, multi-section telescopes, hook stow). Stroke the modelled cylinders over each joint range and sweep
  the boom against the chassis before choosing limits (Kanga 25: +-30 lock, 60 deg luff).

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
python -m roadcraft suspension --geometry measured --axle '<SuspensionAxle JSON>' --share <one wheel's weight share>
python -m roadcraft tpl-nodes <body.tpl> --pattern <bone regex>
python -m roadcraft pak build --project <p> --mod-file <mod> --output <new.pak> --stage-classes --suffix <s> --baseline <installed.pak> --candidate <name> --apply
python -m roadcraft validate <new.pak> --baseline <installed.pak> --json
python -m roadcraft physics report <new.pak> --json
python -m roadcraft compare <new.pak> --donor <retail truck> --json
python -m roadcraft schema show <Type.field>
python -m roadcraft retail tracks <truck> --game <sdkRoot>
python -m roadcraft.bench_headless run <scenario.json> --owner-approved "<who/when/why>"   # only after the owner says yes to this run
```

Do not hand over a candidate with a NEW validate error against the installed package. For any
handling change, compare against the closest retail donor before and after, and name the fields
that moved (softForceScale, wheel friction tables, wheel/body masses, track frame joints, steering
curves). Engine defaults and fields the engine ignores are in library/validator.md (RC072-RC074).

Add the mod project's own rig audit and static validation. None of these proves how the vehicle
drives: the owner's drive is the acceptance, and a candidate stays unaccepted until then.

## Working with the owner

- The owner installs or approves each candidate, drives it in the retail game and reports. Never
  write an installed hash into `accepted`.
- Do not launch the editor (hidden class generation included) or the game while the owner is using
  the PC; say what is queued. The windowless engine bench also needs the owner's go-ahead per run.
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
suspension --calibrate --geometry measured`) and retain the measurement's scope. Keep hypotheses
distinct from proven behavior and acceptance; keep personal paths, account
details and installation state out of the shared library. No new finding
means no forced entry, and this rule adds no execution or installation authority.
