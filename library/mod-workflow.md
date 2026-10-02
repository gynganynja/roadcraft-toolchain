# Creating and modifying mods

This is the shared entry point for RoadCraft mod work. Select the mod and the
change first; reuse the relevant library findings and tools. Vehicles, machines,
materials, textures and settings changes share identity/build/package workflows,
but do not all need a vehicle rig or the same validation.

For a new project, read [new-mod-creation](new-mod-creation.md) for the Lada
session's practical authoring and verification checkpoints. Apply its vehicle
sections to the requested features; its tuning values are not starter defaults.

## Choose an entry path

| Starting point | Shared command or action | Preserved inputs |
|---|---|---|
| New mod | `mod-init --directory NEW --name ID --kind general|vehicle|material|tuning` | Empty accepted identity; user-supplied art/settings become explicit sources |
| Existing source project without workflow files | `mod-adopt --directory EXISTING --name ID --kind KIND` | Existing source, Git history, README and agent guidance; conflicting workflow/config files abort adoption |
| Project already using the toolchain | Select its `project.json`; use its adapters and recipes | Existing registry, source declarations, receipts and accepted pins |
| Compiled package | `mod-init --directory NEW --name ID --package ORIGINAL.pak` then `inspect --hash-members` | Original archive pinned as an unreviewed candidate, never overwritten or promoted to accepted |
| Registry only | `onboard --project NAME [--package PATH] [--output NEW_JSON]` | Source and installation remain untouched; no build adapters are implied |

**Build (toolchain behavior):** These commands create contracts and record
identities. They do not synthesize a usable vehicle or reverse a PAK into its
original authoring sources. Find actual source or a reviewed adapter for the
resource being changed; record unresolved source ownership/lineage.

## Work inside the selected mod

Use `--registry`, `ROADCRAFT_REGISTRY` or the nearest project above the working
folder. Generated `tools/roadcraft.py` selects its own mod from any working
directory. Machine settings, job folders and transactions belong to that mod.
The shared checkout's historical root registry is explicit-only.

**Build:** `tests/test_project_context.py` and `tests/test_mod_workflow.py` cover
project selection, recipes launched from a different mod, non-vehicle builds,
unchanged source and imported package bytes, and adoption collisions. These are
offline toolchain checks, not proof that any candidate works in the retail game.

For an existing mod, establish a before-state from pinned original package/source
bytes and existing receipts. Record the requested change and allowed package
paths. Do not treat the installed file, newest folder or donor vehicle as an
accepted baseline without its supporting evidence. Keep package-only source
limitations visible in the project handoff.

## Reuse by subject

- Source/model/rig edits: [frames](frames.md), [visual rigs](ik-visual-rigs.md),
  [build pipeline](build-pipeline.md) and the project's actual source declarations.
- Vehicle physics and behavior: [suspension and wheels](suspension-and-wheels.md),
  [truck settings](truck-settings.md), [cockpit and lamps](cockpit-and-lamps.md).
- Material/texture edits: [textures and materials](textures-and-materials.md);
  constrain the changed resources and check compiled outputs and mips.
- Unknown engine behavior: [retail data](retail-data.md), [symptoms](symptoms.md)
  and [case studies](case-studies.md). Keep inferred rules distinct from tested ones.
- Source provenance, exact-byte evidence and native export parity: shared source
  APIs and [the D11 case study](../docs/case-studies/d11.md), when its repaired-USF
  route matches the task. D11's exact mesh names and probe pins are case-specific.

## Build, compare, test, record

Declare ordered source files, reviewed commands and complete outputs in `mod.json`
and `recipe-template.json`. `mod-recipe` pins the selected runtime, project context
and sources without executing them, and refuses invalid recipes or overwritten
recipe identities. `vehicle.json` and existing vehicle adapters remain supported.
Vehicle checks run after prepare/generate and before final tests; general mods
need validation suited to the actual change.

Use a project test phase for rig/resource checks and package comparisons. Preserve
duplicate ZIP member occurrences; a path alone cannot identify a duplicated member.
Compare output against the original with explicit allowed paths. Pin generated
inputs in a new test recipe when validating an existing build. Shared checks and
package comparisons catch known faults; in-game behavior still requires evidence.

**Build:** First installations require an explicitly empty mod slot. Updates use
an explicit reviewed live hash, or the accepted hash when available. The selected
project's transaction receipts preserve previous bytes or previous absence.
`tests/test_new_mod_transactions.py` covers first install, rollback, interruption
recovery and a competing file appearing during creation. No test grants game
acceptance, and the authoring task alone does not authorize a live installation.

**Measure physics before installing (KGS-25, 2026-10-02):** fix 1 sized the crane's springs from
the library's formula and was installed unmeasured; the owner reported "it does it worse now". A
change to suspension, wheels, masses or joints goes over the physics bench first, against the
installed version and with the owner's go-ahead ([physics-bench.md](physics-bench.md)). The bench
does not replace the owner's drive.

Record results against the exact build and variant. Keep capture success,
numerical checks, visual review and campaign acceptance separate. Integrate
reusable discoveries according to [learning.md](learning.md) before reporting
completion; a project-specific failure can become a shared check only when the
underlying rule is supported and its scope is understood.

**Owner instruction (2026-10-02):** a ZIP for the recipient holds only the mod: the
installable PAK and the mod's editor files (`mods_source`: BROs, model assets with their
`.blend`, compiled TPL and markup, the material instances the models use, `pct`, `td`,
source textures, generated classes and the `.mod`). No install notes, build reports,
checksums, previews or agent write-ups; keep those with the sealed candidate. Evidence:
dumptwuck_mod `tools/deliver.py` (candidate dtw-20261002-v5).

## Local activation when the browser is unavailable

Installation and activation are separate. For a .pak already in the selected
retail game's `root/mods`, the optional
[Windows offline helper](../integrations/windows-offline-mods/README.txt) edits
the selected profile's packed enabled list with exact backups while the game
and editor are closed. See [retail data](retail-data.md#local-mod-activation-settings-2026-10-01)
for the codec and its evidence. Its offline checks do not prove retail startup,
campaign or multiplayer acceptance. An authoring or helper-build task does not
authorize changing the live profile; the user initiates that change in the GUI.

### Package transaction process scope (2026-10-01)

**Build:** install/rollback/recover block RoadCraft, ModEditor,
IntegrationStudio, Furnace and ModPakBuilder processes and fail closed when
inspection fails. DCC applications and their connector servers do not read an
installed PAK slot; an unrelated open Blender/Painter document no longer blocks
these pinned package transactions. The broader authoring process inventory is
unchanged for build/capture workflows. This does not permit installing while a
native editor or game is running.

Evidence: Dump Twuck's first-install preflight was blocked by eight Blender MCP
servers and a separate open Blender project while native game/editor processes
were absent. `tests/test_transaction_process_scope.py` covers DCC/connector
exclusion, native reader/builder refusal and process-inspection failure;
`tests/test_new_mod_transactions.py` covers exact bytes, receipts and absence.


### Native authoring gates and connector servers (2026-10-02)

**Build:** known console connector servers `blender-mcp.exe` and `mcp-for-blender.exe` do not
own Blender documents or native compiler state. The authoring gate now excludes these exact
names, case-insensitively. Real `blender.exe`, Painter, game/editor/compiler processes and
other matching workers remain blockers; inspection failure still fails closed. Do not exempt
all processes containing "mcp" or suppress a real DCC process to run a build. This extends the
earlier package-transaction scope correction to name classification in the authoring inventory.
Evidence: CAT 793D RC26 encountered seven connector servers with no open Blender; shared
`core._is_authoring_process`, `tests/test_authoring_process_names.py` (3 tests), and
`tests/test_core.py` (8 tests) pass. The lamp suite also passes (15 tests). The full core suite
needs the installed toolchain environment's console entry point; a bare interpreter without
`Scripts/roadcraft.exe` does not satisfy that environment test.
