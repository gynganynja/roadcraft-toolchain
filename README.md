# RoadCraft Toolchain

Create new RoadCraft mods and modify existing ones using shared project setup,
source and package inspection, authoring checks, pinned builds, installation,
rollback and evidence review. Findings from D11, the buggy, Warthog and other
projects are retained in the [modding library](library/README.md). Choose the
rules relevant to the current mod and their evidence grade.

The toolchain is shared software; each mod owns its registry, source, machine
configuration, recipes, jobs and receipts. D11 is an explicitly selected
[case study](docs/case-studies/d11.md). Its historical files and pins remain
available, and are never the implicit baseline for another project.

Python 3.12+ is required. Install with `python -m pip install -e .` in a dedicated
environment, or set `PYTHONPATH` to this checkout's `src` and run
`python -B -m roadcraft`. Core workflows use the standard library.

## Create a new mod

```text
roadcraft mod-init --directory path/to/trail_mod --name trail_mod --kind vehicle
roadcraft mod-init --directory path/to/material_mod --name material_mod --kind material
```

Kinds are `general`, `vehicle`, `material` and `tuning`. Vehicle starters include
BRO and compiled-model checks; other kinds use an adaptable prepare/package
workflow without truck requirements. The starter creates the project contract,
agent instructions and a project launcher. Supply the actual art/settings and
reviewed build scripts; it does not create a playable vehicle or invent SDK
commands. `vehicle-init` / `vehicle-recipe` remain compatible with `vehicle.json`.

## Modify an existing mod

For sources without toolchain configuration:

```text
roadcraft mod-adopt --directory path/to/existing_sources --name trail_mod --kind vehicle
```

Adoption preserves source files, Git history and README content. It appends the
shared instructions and ignore rules, and refuses existing workflow or machine
configuration files before writing. If a project already uses the toolchain,
select its registry and use its adapters; do not reinitialize it.

For a package to inspect or modify in a separate workspace:

```text
roadcraft mod-init --directory path/to/mod_edit --name mod_edit --kind general --package path/to/original.pak
roadcraft inspect path/to/original.pak --hash-members --json
```

The original is pinned as the unreviewed `imported` candidate and left intact.
Obtain usable source or a reviewed adapter for the specific change. A compiled
package is not a recovered Blender/source project. Preserve archive member
occurrences and compare the output against the original:

```text
roadcraft verify --baseline path/to/original.pak --candidate path/to/edited.pak --allowed-path "material_instances/*" --json
```

`onboard` remains available for drafting only a registry, including imported
package pins. [The workflow guide](library/mod-workflow.md) covers source edits,
package-only inputs, acceptance and how to reuse findings.

## Select the mod

Project selection is `--registry PATH`, then `ROADCRAFT_REGISTRY`, then the
nearest `project.json` in the current folder or its parents. Searching stops at
the shared toolchain checkout. A project command with no selected mod reports
how to select one. The toolchain root's historical `project.json` is explicit-only.

Machine configuration is `--config PATH`, then `ROADCRAFT_CONFIG`, then the
selected mod's `local/machine.json`. Relative document paths resolve beside
the JSON file declaring them. Use generated `tools/roadcraft.py` from any working
folder to select that launcher’s own mod; `ROADCRAFT_TOOLCHAIN` selects the
shared checkout, otherwise its `local/toolchain.json` does.

```text
roadcraft status --registry path/to/mod/project.json --json
roadcraft doctor --registry path/to/mod/project.json --json
roadcraft verify --project --registry path/to/mod/project.json --json
```

File inspection, archive comparison and the library work without selecting a
project. `verify --project` checks declared pins; an empty project has no identity
to verify and cannot pass that check. No discovered hash becomes accepted merely
to make verification pass.

## Author, build and test

1. Search the library and inspect existing source/retail examples before writing
   a helper. Declare the actual source route and retain original inputs.
2. List inputs in `mod.json` `sourceFiles`, globally or per step in
   `recipe-template.json`. Include scripts, art, configuration and SDK dependencies.
3. Supply reviewed commands, expected output files, complete output trees where
   needed, and test/inspection steps appropriate to the changed resources.
4. Pin a new recipe and preflight it before authorized execution:

```text
roadcraft mod-recipe --project path/to/mod --output path/to/mod/recipes/build-001.json
roadcraft build --recipe path/to/mod/recipes/build-001.json --incremental --json
roadcraft build --recipe path/to/mod/recipes/build-001.json --incremental --apply --json
roadcraft test --recipe path/to/mod/recipes/test-001.json --json
roadcraft jobs-summary --registry path/to/mod/project.json --json
```

Recipe job folders default to the recipe's project root, including when invoked
from another mod. `--jobs-root` overrides this explicitly. `jobs-status` and
`jobs-summary` use the selected mod. Recipes are immutable snapshots; changed
source/shared runtime requires a new recipe. New recipes pin the shared runtime
and project configuration and run subprocesses in that mod's context.

`--incremental` reuses only explicitly cacheable isolated steps whose input,
command, environment, dependency, successful receipt and output hashes match.
Native-gated and capture steps cannot be cached; vehicle checks always run.
Omitted dependencies conservatively include all preceding steps. Declare finer
input scopes only when justified. `jobs-summary` reports observed times and reuse,
not an inferred percentage speedup.

`build`, `test`, `inspect-job` and `capture` default to read-only preflight.
`--apply` executes the selected phase. A phase name alone does not prove that its
recipe builds, tests or captures anything. Read its commands and outputs.

## Install and iterate

Pin the built package as a named candidate in the mod registry and configure its
`installedPackage` in that mod's `local/machine.json`. Keep source packages
separate from the live mod slot. Installation checks processes, input pins,
current slot identity and durable transaction state.

```text
roadcraft install --registry path/to/mod/project.json --candidate test-001 --expect-absent --json
roadcraft install --registry path/to/mod/project.json --candidate test-001 --expect-absent --apply --json
roadcraft install --registry path/to/mod/project.json --candidate test-002 --expect-installed-sha256 REVIEWED_CURRENT_SHA256 --json
roadcraft rollback --receipt path/to/mod/local/transactions/TRANSACTION_ID/receipt.json --json
roadcraft recover --receipt path/to/mod/local/transactions/TRANSACTION_ID/receipt.json --json
```

Use `--expect-absent` for a first installation into an empty `.pak` slot. It never
replaces a file that appears during the transaction. An update requires the
reviewed current hash, defaulting to an accepted package pin only if one exists.
A mod without accepted history can still be installed or updated without inventing
acceptance. Receipts retain previous bytes, or record previous absence for a new
slot. Rollback restores that exact previous state and refuses unknown live bytes.
Transactions default to the selected mod's `local/transactions`.

Keep the game and editor closed for installation. These commands default to
preflight; applying installation, rollback or recovery requires `--apply` and
existing task authorization. Installation, successful checks and rollback never
promote a candidate to accepted. Record the tested build and user observations.

## Shared findings and evidence

Agents must follow [learning.md](library/learning.md): integrate reusable findings,
failed approaches, fixes and feedback during the same task, with evidence and
scope. Add shared checks/helpers where justified and wire them into the workflow.
Chat or private agent memory alone is insufficient.

```text
roadcraft library
roadcraft library symptoms
roadcraft library --search axleController
roadcraft lint-bro truck.bro --class auto_truck.cls --tpl body.tpl --json
roadcraft tpl-nodes body.tpl --pattern "Wheel|IK" --json
roadcraft retail find "*scout*" --game path/to/RoadCraft
roadcraft retail tracks --game path/to/RoadCraft
roadcraft suspension --geometry measured --sag 0.16 --share 0.25 --lift 0.06
roadcraft bench compare bench/runs/c03_normal_161400 bench/runs/fix2_normal_163000
```

`roadcraft bench run` starts the Mod Editor on a copy of the mod to measure a handling
change before it is installed: ask the owner first ([physics bench](library/physics-bench.md)).

The library records Game, Retail, SDK, Build, Inferred and Open evidence grades.
General source/identity rules apply across mods; vehicle mechanics apply only to
relevant vehicle work. Preserve contradictory and failed evidence with corrections.

Source inventories retain explicit, ordered authoring declarations. Repaired USF
inputs stay authoritative until their asset-specific native-Blender parity gate
passes. That repair gate does not automatically apply to a fresh native source
project. `source-check` checks declared inventory pins and source changes.

Captured, numerical, visual and campaign acceptance remain separate. Use
`python -m roadcraft.review` for local reports from pinned evidence and
`python -m roadcraft.regression` for an explicitly configured evidence policy.
[Components and boundaries](docs/components.md) describes diagnostics, recovery,
source migration and storage tools. Historical probes retain their original scope.

## Integrations and development

The optional `roadcraft.mcp_server` exposes read-only inspection and evidence
operations for the selected mod. Pass `--registry` or configure
`ROADCRAFT_REGISTRY`; it has no default D11 context. The separate Blender scratch
adapter also selects its mod explicitly and retains its bounded source/parity
checks. Install `requirements-mcp.txt` only for these optional adapters.

The local plugin under `plugin/` contains both skills. Its presence does not prove
an integration is installed or healthy. Configure machine paths locally using
`.codex/config.toml.example`. Keep distributable skill copies identical.

```text
python -B -m unittest discover -s tests -p "test_*.py"
```

Run with this checkout's `src` on `PYTHONPATH`. Optional SDK and local native
fixture tests report skips when unavailable. Preserve D11 pins, evidence and
historical code when extending shared capabilities; the [D11 case study](docs/case-studies/d11.md)
records where those materials live.
