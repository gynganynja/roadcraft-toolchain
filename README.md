# RoadCraft Toolchain

This package records and checks D11 source, package, capture, and installed
identities, and holds the vehicle-authoring library in `library/`: what has
been learned building RoadCraft vehicle mods, with checks for truck BROs and
compiled models. Read-only inspection is the default. Recipe execution and package
transactions require an explicit `--apply` flag. Python 3.12 or newer is
required; the core has no runtime dependencies outside the standard library.

Install in a dedicated environment with `pip install -e .`, then use
`roadcraft doctor`, `roadcraft status`, `roadcraft inspect`, and
`roadcraft verify`. For direct source execution, set `PYTHONPATH` to this
folder's `src` directory and run `python -m roadcraft`.

## Configuration

The versioned `project.json` defaults to this folder. Override it with
`--registry` or `ROADCRAFT_REGISTRY`. The local `local/machine.json` defaults
to this folder; override it with `--config` or `ROADCRAFT_CONFIG`. Relative
paths resolve beside the JSON document that contains them. Do not infer an
accepted package from folder dates or the current installed package.

Example registry:

```json
{
  "schemaVersion": 1,
  "project": "D11",
  "accepted": {
    "package": {"path": "../artifacts/accepted.pak", "sha256": "<64 hex digits>"},
    "sourceManifest": {"path": "../assets/source-manifest.json", "sha256": "<64 hex digits>"},
    "authoringInventory": {"path": "../assets/authoring-inventory.json", "sha256": "<64 hex digits>"},
    "sourceRoot": "../assets"
  },
  "candidates": {
    "interior-trial": {"package": {"path": "../artifacts/interior-trial.pak", "sha256": "<64 hex digits>"}}
  },
  "variants": ["maroon", "nearnew", "worn"],
  "recipes": {}
}
```

Example local configuration:

```json
{
  "schemaVersion": 1,
  "sdkRoot": "C:/Path/To/Roadcraft Development Package",
  "installedPackage": "C:/Path/To/RoadCraft/root/mods/cat_d11t.pak",
  "tools": {
    "furnace": "C:/Path/To/Roadcraft Development Package/tools/bin/ResourceTools/furnace/furnace.exe"
  },
  "transactionReceipts": ["C:/Path/To/Capture/candidate_capture.json"],
  "transactionLocks": ["C:/Path/To/Capture/candidate_capture.lock.json"]
}
```

`status` hashes the accepted, candidate, and installed files independently.
An installed package matching no pinned identity is reported as `unrecognized`.
It never changes the registry's accepted identity. `verify --project` checks
all pinned files and the contents of pinned source and authoring manifests; a missing
SHA-256 is an unverified pin and fails that check. The optional
`accepted.sourceRoot` is the base for relative manifest rows.

Configured transaction receipts and locks appear in `status`. A failed
capture remains failed evidence even when rollback succeeded. The
`recoveryRequired` flag clears only when the receipt records baseline
restoration and the observed installed hash matches either that baseline
or a later registry accepted build, with no configured lock present. The
separate package transaction commands create their own receipts and restore
only packages they installed.

## Read-only commands

```text
roadcraft doctor --config local/machine.json --json
roadcraft status --registry project.json --config local/machine.json --json
roadcraft inspect candidate.pak --member models/mods/cat_d11t.tpl.asset/tpl/cat_d11t.tpl --occurrence 2 --hash-members --json
roadcraft verify --file candidate.pak --sha256 <64-hex-digits> --json
roadcraft verify --manifest source-manifest.json --base path/to/source --json
roadcraft verify --baseline accepted.pak --candidate candidate.pak --allowed-path 'models/mods/*.tpl.asset/*' --json
```

ZIP entries are compared by normalized path and one-based occurrence. The
comparison hashes decompressed member content and reports added, removed, and
changed occurrences. `--allowed-path` globs restrict all three kinds of
change. A manifest is an object with `files` rows containing `path` (or
`relativePath`), `sha256`, and optional `bytes`.

## Vehicle-authoring library

`library/README.md` indexes the articles (symptoms, frames, suspension and
wheels, visual IK rigs, truck settings, cockpit and lamps, textures and
materials, retail data, build pipeline, case studies, sources). Every rule
carries an evidence grade: seen in the game, read from retail data, from the
SDK, observed in a build, inferred, or open. The commands below read files
only; `retail` reads the game installation named by `--game` or the machine
configuration's `sdkRoot`.

```text
roadcraft library [topic] [--search REGEX]
roadcraft lint-bro truck.bro --class auto_truck.cls --tpl body.tpl --json
roadcraft suspension --sag 0.16 --share 0.205 --lift 0.06 --bump 0.16 --droop 0.20
roadcraft suspension --calibrate '[{"axle": {...}, "rest": 0.12, "wheels": 2}, ...]'
roadcraft tpl-nodes body.tpl --pattern "Wheel|IK" --json
roadcraft retail find "*armiger*"
roadcraft retail bro armiger_thunder_scout_new
roadcraft retail survey
```

`lint-bro` exits 1 when it finds an error-level pitfall. The library reads the
checkout's `library/` folder, so use a source checkout or an editable install.
The Python modules are `roadcraft.ps_format`, `tpl_reader`, `vehicle`,
`bro_lint`, `retail` and `library`. The skill is
`skills/roadcraft-vehicle-authoring/SKILL.md`.

## Pinned workflow commands

`project.json` records the accepted package, source manifest and authoring
inventory. `local/machine.json` records this machine's editor paths and
installed package. `source-check` rehashes the ordered files declared for the
three D11 variants and compares them to the pinned inventory.

```text
roadcraft source-check --json
python operations/configure_local_recipe.py
roadcraft inspect-job --recipe local/recipes/d11_toolchain_checks.json --jobs-root jobs --json
roadcraft test --recipe local/recipes/d11_toolchain_checks.json --jobs-root jobs --json
roadcraft build --recipe path/to/reviewed-build-recipe.json --jobs-root jobs --json
roadcraft capture --recipe path/to/reviewed-capture-recipe.json --jobs-root jobs --json
roadcraft jobs-status --jobs-root jobs --json
roadcraft jobs-recover --jobs-root jobs --run-id <run-id> --expected-lock-sha256 <sha256> --expected-receipt-sha256 <sha256> --expected-installed-sha256 <sha256> --expected-registry-sha256 <sha256> --expected-config-sha256 <sha256> --json
roadcraft install --candidate aaa-20260928 --json
roadcraft rollback --receipt local/transactions/<id>/receipt.json --json
roadcraft recover --receipt local/transactions/<id>/receipt.json --json
```

Without `--apply`, recipe and package commands only preflight. A recipe is
`schemaVersion: 1` with a name, a `phases` object containing ordered `build`,
`inspect`, `test`, or `capture` steps, and each step's absolute executable
argv, cwd, pinned inputs, expected outputs, timeout and minimum free space.
`roadcraft.jobs` runs commands without a shell and records durable receipts,
logs and locks. Native steps refuse active RoadCraft or authoring processes.
Interrupted native work retains a lock for inspection. Recipe dry runs do not
create a jobs directory.

`jobs-recover` is also a dry run unless given `--apply`. Use it only for a
terminal failed or interrupted native job after reviewing its receipt and the
external package/editor state. In PowerShell, from the toolchain root, prepare
the five reviewed pins and run the preview first:

```powershell
$run = 'reviewed-run-id'
$lockSha = (Get-FileHash 'jobs/.roadcraft-jobs.lock' -Algorithm SHA256).Hash.ToLowerInvariant()
$receiptSha = (Get-FileHash "jobs/$run/receipt.json" -Algorithm SHA256).Hash.ToLowerInvariant()
$installedSha = (Get-Content 'project.json' -Raw | ConvertFrom-Json).accepted.package.sha256
$registrySha = (Get-FileHash 'project.json' -Algorithm SHA256).Hash.ToLowerInvariant()
$configSha = (Get-FileHash 'local/machine.json' -Algorithm SHA256).Hash.ToLowerInvariant()
roadcraft jobs-recover --jobs-root jobs --run-id $run --expected-lock-sha256 $lockSha --expected-receipt-sha256 $receiptSha --expected-installed-sha256 $installedSha --expected-registry-sha256 $registrySha --expected-config-sha256 $configSha --registry project.json --config local/machine.json --json
roadcraft jobs-recover --jobs-root jobs --run-id $run --expected-lock-sha256 $lockSha --expected-receipt-sha256 $receiptSha --expected-installed-sha256 $installedSha --expected-registry-sha256 $registrySha --expected-config-sha256 $configSha --registry project.json --config local/machine.json --apply --json
```

Run the second command only if the preview returns `ready` and its state is
still the reviewed state. Recovery checks the owner's process, active authoring
processes, the installed accepted package, and every configured transaction
receipt and lock. An applied recovery writes `job_recovery_<id>.json` in the
run directory before removing only the shared job lock. Its `released` status
and returned SHA-256 document the release; `jobs-status` should then show
`lockPresent: false`. The original failed job receipt and installed package
remain unchanged. A `verified_release_pending` recovery receipt after a crash
is ambiguous: inspect the lock's current presence before any further action.

`install` names a candidate from the registry and verifies the expected live
hash, source archives and process state before writing. Applied installs
retain exact prior package bytes for `rollback`; `recover` only acts on known
hashes. None of these commands changes a candidate into the accepted
baseline. The AAA candidate currently has a failed native capture even though
its rollback restored the accepted installed package.

The authoring inventory declares repaired `export.usf` as the three variants'
build source. `roadcraft.source.require_export_allowed` blocks native `.blend`
export until an asset-specific approved parity receipt covers the required
geometry, material, animation, compile and native-view checks. The Blender
bridge tests no-edit USF serialization in temporary scratch and records a
receipt without replacing any source file.

`python -m roadcraft.review` makes a local HTML/JSON evidence report from
pinned receipt inputs. Comparisons require matching variant, scene, camera,
lighting, resolution and protocol; absent context produces a contact sheet
only. Numerical, visual and campaign acceptance stay distinct.

`python -m roadcraft.regression POLICY` evaluates a pinned source, package,
capture and metric evidence chain against explicit required views and numeric
thresholds. Technical results do not grant visual or campaign acceptance;
those stages require detached approvals from externally trusted reviewer keys.
Install the `review` extra (`python -m pip install -e ".[review]"`) to enable
Ed25519 verification. The CLI exit code covers the technical gate; inspect
`releaseReady` before any release decision. The current AAA interior policy
and replayable result are in `operations/`; the genuine reviewer handoff is
documented in `operations/REVIEWER_CLAIM_HANDOFF.md`.

## Asset and native preflight gates

The migration command verifies the pinned source and destination without
writing:

```text
python -m roadcraft.migrate --manifest PATH --manifest-sha256 SHA256 --source-root PATH --destination PATH --receipt PATH
```

`--run` starts a resumable copy only
when free space covers the remaining bytes **plus** the default 30 GiB
reserve. The current D11 dry run verified 2,817 files but failed that space
gate; the accepted source remains at the path in `project.json`.

`operations/d11_aaa_native_preflight_recipe.json` is deliberately limited to
the old AAA builder's `--check`, its existing-package audit, and the native
capture script **without** `--execute`. It can be passed to `roadcraft build`,
`roadcraft inspect-job`, or `roadcraft capture` for a declarative dry run.
Those phase names do not mean that this recipe builds a PAK or captures a
view. `operations/D11_NATIVE_RECIPE_REVIEW.md` lists the output-path,
rollback, process-ownership and disk-space work needed before admitting a
native execution recipe.

`python -m roadcraft.expansion_cleanup` checks the separately reviewed
retail-export candidates against an exact manifest SHA-256, live file
identities, retained PAK members, Git state and active processes. It defaults
to dry-run; `--sample-candidates N` is a labeled partial check that can never
apply. The eight-file sample checked eight files and removed none. A full
28 September dry run verified all 23,604 candidates and removed none. Its
sandboxed receipt remains blocked because CIM command-line inspection was
denied; a separate elevated, read-only full receipt passed the process gate
at its check time. `operations/STORAGE_EXPANSION_REVIEW_20260928.md` records
both receipts. Neither receipt authorizes deletion.

## MCP and local plugin

Install `requirements-mcp.txt` in a dedicated environment, then run
`python -m roadcraft.mcp_server`. Its 11 tools are read-only. The recovered
Substance Painter MCP source is under `integrations/SubstancePainterMCP` with
its archive provenance; its 79 tools require Painter to be running with
`--enable-remote-scripting`. The standalone skill and repo-local plugin
scaffold are under `skills/` and `plugin/`. The plugin supplies instructions;
MCP servers are configured separately in `.codex/config.toml` using the
provided example. Check actual MCP connection health before relying on them.

The separate `roadcraft.blender_mcp_server` has only `blender_status` and
`usf_roundtrip`. Configure its fixed Blender executable, its SHA-256 pin and
the SDK script root in `.codex/config.toml.example`; it uses the same optional
official MCP SDK in `requirements-mcp.txt`. `blender_status` checks the pinned
binary and reads its `--version` without opening a project. `usf_roundtrip`
requires an absolute authoring-inventory path, that inventory's SHA-256 pin,
and an asset name. The path and SHA-256 must match this checkout's
`project.json` `accepted.authoringInventory`; it rehashes the declared
authoring source under `accepted.sourceRoot` before either a dry run or native
roundtrip. It defaults to a no-write dry run. Set `run=true` for the
background, factory-startup USF parser/serializer check, with a maximum
900-second timeout. The serialized USF and helper result are disposed of in
`local/blender-mcp-scratch`; without `receipt_path`, the bridge receipt is
ephemeral too. A durable receipt is written only when the caller supplies a
new absolute `.json` path under `local/jobs`. The bridge never opens, saves,
or exports a `.blend` file, and its diagnostic does not approve native export.

For the separate scratch-only historical `.blend` export comparison, use
`python -m roadcraft.blender_authoring` with pinned inventory, Blender and SDK
paths. It records complete node/material/rig differences in a digest-linked
archive while keeping the generated USF under ignored `local/` scratch. See
`operations/D11_BLENDER_AUTHORING_PARITY_20260928.md` for the reproducible
command and current blocked results. This diagnostic never changes the
`native-blend` export approval gate.
