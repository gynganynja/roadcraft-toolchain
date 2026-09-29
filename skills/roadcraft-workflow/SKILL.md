---
name: roadcraft-workflow
description: Create new RoadCraft mod workspaces, adopt and modify existing mods, and manage source identity, pinned builds, package changes, installation, rollback and evidence with the shared RoadCraft toolchain. Use for RoadCraft mod work across vehicles, machines, materials and settings.
---

# RoadCraft mod workflow

Locate the maintained toolchain using ROADCRAFT_TOOLCHAIN or local/toolchain.json.
A cached plugin directory is not the checkout, and the checkout is not necessarily
the mod project. Read library/mod-workflow.md and the articles relevant to the
requested change. Continue within the user's existing authorization; this skill
adds neither an approval ceremony nor authority for unrelated native execution.

## Select the project and starting point

Use --registry PATH, ROADCRAFT_REGISTRY or the nearest project.json above the
working folder. Configuration is --config PATH, ROADCRAFT_CONFIG or that mod's
local/machine.json. The shared checkout's historical registry is explicit-only.
Missing project/configuration information is a gap to resolve, not permission to
borrow another mod's baseline or installed package.

- New mod: mod-init --directory NEW --name MOD_ID --kind KIND. Kinds are general,
  vehicle, material and tuning. Supply real source and reviewed build adapters.
- Existing source without toolchain files: mod-adopt --directory EXISTING --name
  MOD_ID --kind KIND. Preserve originals/history and respect configuration conflicts.
- Existing configured mod: use its registry, sources and adapters; do not reinitialize.
- Package-only input: mod-init into a new workspace with --package ORIGINAL.pak,
  inspect members and establish usable source/adapter support for the requested
  change. Importing pins an unreviewed candidate; it does not reconstruct source.
- For vehicle rigs, wheels, physics, lamps or compiled truck checks, also read
  skills/roadcraft-vehicle-authoring/SKILL.md. Apply those checks to relevant work.

```text
python -m roadcraft status --registry path/to/mod/project.json --json
python -m roadcraft doctor --registry path/to/mod/project.json --json
python -m roadcraft verify --project --registry path/to/mod/project.json --json
python -m roadcraft jobs-status --registry path/to/mod/project.json --json
```

Use verified Python 3.12+ and the checkout's src on PYTHONPATH for direct source
execution. Read current transaction receipts and locks before native work.
Accepted, candidate and installed identities are separate; none is inferred
from folder dates, package size, a completed build or a successful installation.

## Source, authoring and builds

Declare ordered source files, scripts, SDK inputs, commands and complete outputs
in mod.json and recipe-template.json. mod-recipe writes a new pinned recipe;
vehicle.json and existing vehicle adapters remain supported. A starter supplies
workflow structure, not vehicle geometry or guessed SDK export commands.

Preserve original package members including duplicate occurrences. Scope allowed
added, removed and changed paths, and compare the result against the original.
verify --project verifies declared package/receipt/source-manifest/inventory pins
and source contents. source-check compares declared authoring source with its
pinned inventory; these checks cannot grant visual or campaign acceptance.

Keep the declared source route. For repaired-USF inputs, export.usf remains the
build input until an asset-specific native-Blender parity receipt covers the
required geometry/material/animation/compile/native-view checks. A historical
.blend is not silently substituted. Fresh native sources do not inherit a D11
repair assumption. Consult docs/case-studies/d11.md for that specific history.

build, test, capture and inspect-job default to preflight; --apply executes the
reviewed phase. Inspect commands, inputs, outputs, timeouts, disk and process gates.
Recipe names alone are not execution evidence. Jobs belong to the recipe's project
root unless --jobs-root is explicit. An interrupted native job may need recovery;
retain its lock until external state is verified.

Incremental builds reuse only opted-in isolated steps with complete declarations
and verified input/dependency/receipt/output bytes. Shared vehicle checks always
run. Native-gated/capture steps cannot be cached. Pin a new recipe after source or
shared-runtime changes. Use jobs-summary for observed timing; do not invent speedups.

## Installation and evidence

install uses a named candidate and the selected mod's configured installedPackage.
For a new slot use --expect-absent; for an existing slot use the reviewed current
--expect-installed-sha256, or its accepted package pin when present. No accepted
baseline is invented for an imported/new mod. The process and receipt gates remain.
Installation requires the game/editor closed and existing task authorization.

install, rollback and recover default to preflight and need --apply to mutate.
Per-mod transactions retain exact previous bytes, or previous absence. rollback
restores that state and refuses unknown live bytes; recover uses an exact receipt.
Preserve original receipts and do not promote acceptance to silence mismatches.

Captured evidence, numerical results, visual review and campaign acceptance remain
separate. Compare only matching build roles, variant, scene, camera, lighting,
resolution, protocol and metric units. Missing context supports a contact sheet or
observations, not a claimed comparison. Private editor tests do not establish
retail campaign behavior. A failed capture stays failed after successful rollback.

Use roadcraft.review for local reports in an explicit output directory, or the
read-only MCP evidence_report for in-memory output. Supply genuine receipt pins;
a new hash snapshot is not an earlier seal. Preserve unresolved findings.

## Integrate findings and preserve history

Follow library/learning.md in the same task for reusable discoveries, failures,
fixes, feedback, corrected assumptions and workflow lessons. Update the relevant
article with scope, evidence grade and references. Add shared checks/helpers and
wire them into the applicable workflow when supported; explain deferred automation
when premature. Preserve superseded/failed evidence and uncertainty.

Chat/private memory alone is insufficient. Report integration locations or an
explicit blocked handoff. No reusable finding means no forced entry. A learning
rule does not expand execution, publishing or acceptance authority.

Storage review emits exact-file evidence, never deletion authorization. Before
any separately authorized cleanup, recheck exact identity, active ownership and
retained originals. Never generalize a temporary-pack finding to Git objects or
ignored assets. Keep historical operations and case-specific pins intact.

The optional evidence MCP remains read-only with no build/install/recovery tools.
A plugin scaffold/configuration is not proof of an installed or healthy integration.
Check actual tool availability. Machine paths, credentials and installation state
belong in local configuration or receipts, not distributable skills.
