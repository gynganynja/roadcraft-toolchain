# Creating and modifying mods

This is the shared entry point for RoadCraft mod work. Select the mod and the
change first; reuse the relevant library findings and tools. Vehicles, machines,
materials, textures and settings changes share identity/build/package workflows,
but do not all need a vehicle rig or the same validation.

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

Record results against the exact build and variant. Keep capture success,
numerical checks, visual review and campaign acceptance separate. Integrate
reusable discoveries according to [learning.md](learning.md) before reporting
completion; a project-specific failure can become a shared check only when the
underlying rule is supported and its scope is understood.
