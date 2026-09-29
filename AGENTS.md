# RoadCraft Toolchain

If this checkout has `local/toolchain.json`, read its `path` first. When it
selects another checkout, use that checkout for toolchain code and library
work; retain this checkout's history and uncommitted work. Project adapters
use the same machine-local selector, with `ROADCRAFT_TOOLCHAIN` as an override.

## Integrate what you learn

Every agent must integrate new reusable RoadCraft knowledge into the maintained
toolchain during the same task, before reporting it complete. This includes
discoveries, failed approaches, fixes, user feedback, corrected assumptions and
workflow or performance improvements, not just drive reports. Follow
[the learning policy](library/learning.md): search existing knowledge first,
update the relevant library article with evidence and scope, and turn reliable
repeatable lessons into shared checks, helpers or recipes when practical.
Wire new checks into the workflow that needs them. Chat or private agent memory
alone does not satisfy this requirement. Briefly report what was integrated
and where; if integration is blocked, preserve a handoff and state the reason.
Do not invent a finding when nothing reusable was learned, treat an inference
as proven, or expand the user's execution/installation authorization.

## Workflow

For RoadCraft identity, source, package, evidence or storage work, read
[the workflow skill](skills/roadcraft-workflow/SKILL.md). Its working copy is
`skills/roadcraft-workflow/SKILL.md`; the identical file under
`plugin/roadcraft-workflow/skills/roadcraft-workflow/` is the distributable copy.
Keep those two files identical when changing the workflow.

For vehicle authoring (rigs, wheels, suspension, IK linkages, truck settings,
lamps, textures, mod builds), read [the vehicle-authoring
skill](skills/roadcraft-vehicle-authoring/SKILL.md) and the library in
`library/` (`python -m roadcraft library`). The skill's distributable copy under
`plugin/roadcraft-workflow/skills/roadcraft-vehicle-authoring/` must stay
identical to it. Every library rule carries an evidence grade
(`library/README.md`); when a drive contradicts a rule, change the rule and its
grade and record the drive in `library/case-studies.md` instead of deleting the
old evidence. Run `roadcraft lint-bro` on a truck BRO with its compiled class
before handing over a candidate.

New vehicle projects can use `vehicle-init` and `vehicle-recipe`; supply the
vehicle-specific authoring adapters and explicit input/output declarations.
Use `vehicle_workflow.enhance_recipe` in existing adapters for source,
compiled and final checks. `--incremental` only reuses opted-in isolated
steps after receipt, input, dependency and output verification. Shared vehicle
checks always run. Global config pins conservatively invalidate all stages;
never narrow input scopes merely to make a cache hit. Use `jobs-summary` for
observed timings; a synthetic cache test is not a native speedup measurement.

Read `project.json` for accepted and candidate pins and `local/machine.json`
for machine paths. Environment overrides are `ROADCRAFT_REGISTRY` and
`ROADCRAFT_CONFIG`. Do not write a discovered installed hash into the accepted
entry merely to make verification pass. Read current transaction receipts and
locks; dated directory names and historical README claims are not current
installation evidence.

CLI `build`, `test`, `capture` and `inspect-job` preflight a pinned recipe by
default; `--apply` executes that phase. CLI `install`, `rollback` and `recover`
also default to dry-run and require `--apply` for package transactions. Use
existing authorization, verified inputs, process checks and durable receipts;
never describe a preflight as a completed build, capture or installation.
Inspect `jobs-status` and transaction state before continuing native work.
The optional MCP adapter remains read-only and exposes no execution or package
mutation tools. The review CLI creates reports in an explicit output directory;
MCP reports stay in memory. Storage review emits exact-file evidence and never
deletes. Preserve these boundaries and the separate captured, numerical, visual
and campaign acceptance fields. The AAA candidate's failed capture remains
unaccepted even where rollback restored the accepted package.

`verify --project` covers the authoring-inventory pin and its declared source
files as well as package, receipt and source-manifest pins. `source-check`
compares current source to that pinned authoring inventory. Neither command
grants visual or campaign acceptance.

Keep source declarations explicit and ordered. Repaired `export.usf` files
remain build inputs until the native-Blender parity gate passes; a historical
`.blend` cannot silently replace them. Preserve duplicate ZIP member
occurrences, pinned byte identity, and existing source/receipt files. The
earlier repository at `C:\RC\D11_Development` has history and uncommitted work;
do not replace it with a new empty repository or infer that ignored assets are
disposable.

Use a verified Python 3.12+ interpreter. For source execution set `PYTHONPATH`
to this directory's `src`, and run focused tests with `python -B -m unittest
discover -s tests -p "test_*.py"` when package behavior changes. The core is
stdlib-only; the optional stdio adapter has `requirements-mcp.txt`. Test real
SDK schemas when that dependency is available, and disclose skipped tests.
Do not add tests that only assert documentation wording.

The repo-local plugin is a skills-only scaffold. Neither its presence nor an
MCP configuration file proves that any integration is installed, connected or
healthy. Check actual tool availability before using it. Keep machine-specific
credentials and installation state out of versioned skill/plugin files.
