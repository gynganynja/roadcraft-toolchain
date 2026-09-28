---
name: roadcraft-workflow
description: Inspect and verify RoadCraft mod identities, source lineage, package changes, capture evidence and exact-file storage candidates with RoadCraftToolchain. Use for D11 continuation or workflow checks; not generic Blender modeling or unrelated game development.
---

# RoadCraft workflow

Locate the task's RoadCraftToolchain checkout. A cached plugin directory is
not the project. Use `ROADCRAFT_REGISTRY` / `ROADCRAFT_CONFIG` overrides when
set; otherwise read the checkout's `project.json` and `local/machine.json`.
Report missing configuration instead of inventing a source, build or tool path.
Continue within the user's existing authorization; this skill adds no approval
step or authority to change unrelated files.

## Establish identity

Use available RoadCraft MCP `project_status`, `project_doctor` and
`verify_project`, or the existing CLI equivalents:

```text
python -m roadcraft status --registry project.json --config local/machine.json --json
python -m roadcraft doctor --config local/machine.json --json
python -m roadcraft verify --project --registry project.json --config local/machine.json --json
python -m roadcraft source-check --registry project.json --json
```

Use a verified Python 3.12+ runtime; direct source execution requires the
checkout's `src` on `PYTHONPATH`. These commands inspect and hash files without
launching the editor. Read the configured transaction receipts and locks before
native work. `accepted`, `candidate` and `installed` are separate identities.
Never infer acceptance from an installation, folder date, successful build or
largest/newest package; never replace an expected hash with the observed hash
to silence a mismatch.

## Source and package checks

- `verify --project` verifies package, receipt and source-manifest pins, plus
  the `accepted.authoringInventory` pin and its declared source files.
  `source-check` verifies the inventory pin, then compares current source to
  that ordered baseline. For custom inventories use
  `roadcraft.source.capture_source_inventory` and `compare_source_baselines`.
- Current D11 inventories declare `usf-repair`: repaired `export.usf` is the
  build input, and historical `.blend` files are references. Call
  `require_export_allowed` for an export route. `native-blend` needs a complete
  externally reviewed parity receipt tied to the current asset digest and
  repaired USF hash, with every check required by `source.py` passed. Do not
  manufacture approval or change the declared method to bypass this gate.
- Inspect/compare PAKs through `core.inspect_path` / `compare_archives`, MCP
  `inspect_file` / `compare_archives`, or `roadcraft inspect` / `verify`.
  Preserve normalized path **and occurrence**; duplicate archive members are
  meaningful. Scope allowed additions, removals and changes explicitly.

## Jobs and package transactions

CLI `build`, `test`, `capture` and `inspect-job` take `--recipe PATH` and optional
`--jobs-root PATH`. They default to dry-run preflight; `--apply` executes the
selected phase (`inspect-job` selects the recipe's `inspect` phase). Inspect
the actual recipe, pinned inputs, output paths, process checks, disk requirement
and timeout before execution. `jobs-status --jobs-root PATH` reads durable lock
and receipt state. An interrupted native job may require recovery; do not clear
its lock until external package/editor state has been verified.

CLI `install --candidate NAME` uses the registry and machine configuration;
`rollback --receipt PATH` and `recover --receipt PATH` use an exact transaction
receipt. All three default to dry-run and require `--apply` to modify packages.
Install requires the live package to match `--expect-installed-sha256`, or the
accepted package pin when that option is omitted. Review planned paths and
identities, retain rollback bytes and honor process/lock checks. A dry-run is
not evidence of a completed installation, capture or test. Continue within
existing authorization without adding a separate approval ceremony.

The MCP adapter remains read-only: use CLI jobs/transactions for authorized
execution. Command availability does not prove a suitable recipe exists or a
native phase has run. Read the concrete runner and receipt chain before use.

## Evidence and acceptance

Use `roadcraft.review.generate_report` or `python -m roadcraft.review` for a
local HTML/JSON report; MCP `evidence_report` returns it in memory. Supply
expected receipt SHA-256 pins. A newly computed snapshot is not a previous
seal. Nested report/image hashes must verify before reporting those captures.
Comparison requires explicit baseline/candidate roles and matched variant,
scene, camera, lighting, actual resolution and protocol; numerical comparisons
also need matching metric names and units. Missing context means a contact
sheet or recorded measurements only, not an inferred comparison.

Keep four conclusions separate: captured evidence, numerical results, visual
review, and campaign acceptance. Rollback success does not turn a failed
capture into a successful run. Private editor tests do not establish campaign
handling, trail visibility, physical rut depth or shop-spawn behavior. Preserve
unresolved findings and identify the exact tested variant/protocol. The
`aaa-20260928` candidate's failed capture remains unaccepted; restoration of the
accepted package is rollback evidence only, not candidate acceptance.

## Storage and continuation

Use `cleanup.build_review` or MCP `storage_review` with explicit old-run roots
and retained SDK templates. Its output is an exact-file candidate manifest,
not deletion authorization. Before authorized cleanup, recheck identity,
hash, allocation/link count and active ownership; preserve retained originals,
source assets, receipts and history. Never generalize a temporary-pack finding
to normal Git packs or delete whole dated run folders by name.

A plugin scaffold or MCP entry does not prove connection health; check tools
before claiming an integration is available. Report verified results, failed
checks and remaining acceptance work without promoting a candidate
automatically.
