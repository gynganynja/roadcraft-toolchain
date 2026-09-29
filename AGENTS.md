# RoadCraft Toolchain

This is shared tooling for creating and modifying RoadCraft mods. Select the
actual mod before identity, authoring, build, installation or evidence work.
D11, the buggy and Warthog are projects and case studies, not universal defaults.

## Shared checkout and project context

Use ROADCRAFT_TOOLCHAIN when set, otherwise a local/toolchain.json selector, to
locate the maintained toolchain. Preserve other checkouts' history and work.
The shared code/library checkout and the mod source directory are separate roles.

Read [the workflow skill](skills/roadcraft-workflow/SKILL.md) and
[the mod workflow](library/mod-workflow.md). Project selection uses --registry,
ROADCRAFT_REGISTRY or the nearest project.json above the working folder.
The shared checkout's historical root project.json is explicit-only. Machine
config is --config, ROADCRAFT_CONFIG or the selected mod's local/machine.json.
Inspect that mod's recipes, current jobs, transaction receipts and locks before
native work. Dated folders and historical README claims are not live evidence.

Use mod-init for a new workspace, mod-adopt for existing unconfigured sources,
and mod-recipe for pinned recipes. Existing configured projects keep their
adapters, registries and source declarations. Preserve original imported packages;
package bytes do not imply recoverable authoring source or acceptance. See
[components](docs/components.md) for shared versus specialist capabilities.

For vehicle rigs, suspension, wheel behavior, truck settings, lamps or model
checks, also read [the vehicle-authoring skill](skills/roadcraft-vehicle-authoring/SKILL.md)
and relevant subject articles. General/material/tuning mods need validation for
the changed resources, not mandatory truck or suspension settings.

## Integrate what you learn

Every agent must integrate new reusable RoadCraft knowledge into the maintained
toolchain during the same task before reporting completion. Follow
[learning.md](library/learning.md): search prior knowledge, update the relevant
article with scope, evidence grade and references, and turn supported recurring
faults or manual work into shared checks/helpers where practical. Wire them into
the applicable workflow and validate changed behavior. Include discoveries,
failed approaches, fixes, user feedback and corrected assumptions.

Chat or private memory alone does not satisfy this rule. Report what was
integrated and where; if blocked, preserve a handoff and state the reason.
Preserve corrected evidence and uncertainty. Do not manufacture findings or
expand execution, installation, publishing or acceptance authority.

## Build, identity and acceptance

build, test, capture and inspect-job preflight pinned recipes by default;
--apply executes a phase. install, rollback and recover also default to
preflight. Never describe preflight as a completed build, capture or install.
Use existing authorization, verified inputs, process checks and durable receipts.

Use per-mod jobs and transactions. Incremental reuse requires opted-in isolated
steps, complete declared inputs/outputs/dependencies, and verified successful
receipts and current bytes. Native-gated/capture steps cannot be cached; shared
vehicle checks always run. Use jobs-summary for measured timing, not inferred
speedup claims. Regenerate recipes after source or shared-runtime changes.

Keep accepted, candidate and installed identities separate. A first installation
requires explicit expected absence; updates require the reviewed installed hash
or an existing accepted pin. Neither installation nor rollback grants acceptance.
Do not write observed hashes into accepted entries just to make checks pass.
Preserve captured, numerical, visual and campaign acceptance as separate fields.

verify --project checks declared package, receipt, source manifest and authoring
inventory pins and declared source files. source-check compares source to its
pinned inventory. Neither command grants visual or campaign acceptance.

Keep source declarations explicit and ordered, preserve duplicate ZIP member
occurrences and pinned bytes, and retain originals, source/receipt files and Git
history. For repaired-USF inputs, historical .blend files cannot silently replace
export.usf until the asset-specific native-Blender parity gate passes. Apply that
condition to the declared source route, not every new native authoring project.

## Preserved cases and integrations

For D11 continuation or its specialized repair/capture probes, read
[the D11 case study](docs/case-studies/d11.md). Preserve its registry/evidence
pins, previous failed capture status and older repository work. Generalization
must not rewrite historical evidence or turn case-specific assumptions into rules.

The optional evidence MCP is read-only, has no package/native execution tools,
and keeps reports in memory. CLI reports use explicit output directories.
Storage review reports exact-file candidates and never deletes. Preserve these
boundaries. The separate bounded Blender scratch adapter retains its own gates.

Use verified Python 3.12+. For source execution set PYTHONPATH to this checkout's
src, and run focused tests with python -B -m unittest discover -s tests -p
"test_*.py" when behavior changes. Core is stdlib-only; optional MCP dependencies
are in requirements-mcp.txt. Test real SDK schemas when available and disclose
skips. Do not add tests that only assert documentation wording.

The skills-only plugin does not prove installation or connection health. Keep
machine credentials and installation state local. Both working skill files under
skills/ must remain byte-identical to their distributable copies under
plugin/roadcraft-workflow/skills/ when changed.
