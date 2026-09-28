# RoadCraft workflow implementation plan

Status snapshot: 28 September 2026, Australia/Brisbane. This is a roadmap, not
an execution receipt. Recheck live hashes, jobs, processes, free space and
connection state before each dependent step. Existing authorization carries
forward; this document adds no blanket approval requirement.

## Locations, ownership and completion rules

- **Source toolchain:** `C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain`.
- **Dedicated toolchain:** `C:\RC\RoadCraftDev\toolchain`. Its dedicated
  environment and current checks pass. Git is initialized on `main`; `origin`
  is the private `https://github.com/gynganynja/roadcraft-toolchain.git`.
  The initial 96 maintained files were hash-compared after handoff. The code
  and Windows CI fixture fix have been pushed; keep this checkout and the
  Steam source mirror synchronized for subsequent edits.
- **Current assets:** the verified location in `project.json` remains
  authoritative: `C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\D11_Interior_Standalone_20260927\p`.
  The user chose to keep assets here. No migration is planned now;
  `C:\RC\RoadCraftDev\assets` is only a deferred option.
- **Historical repository:** `C:\RC\D11_Development`; retain its history,
  working files and uncommitted changes independently of the new code repo.
- **Implementation owner:** Codex/maintainer owns code, recipes, inventories,
  diagnostics and receipts. **Machine/account owner:** user owns any required
  project-trust UI action, account login and remote selection. **Acceptance
  owner:** user or designated reviewer owns visual/campaign decisions; the
  toolchain verifies those decisions and must not invent them.

A stage is done only when its exit evidence exists and its failure/rollback
checks pass. Configured, installed, connected, captured, numerically passed,
visually accepted and campaign accepted are different states.

## Current evidence

| Area | State at this snapshot | Evidence and limit |
|---|---|---|
| Core CLI, jobs and transactions | Implemented | `src/roadcraft/cli.py`, `jobs.py`, `transaction.py`. CLI job/transaction operations default to dry-run; `--apply` executes. A failed phase after native launch retains its lock; `jobs-recover` requires exact lock/receipt/installed/registry/config pins and verified terminal external state before release. No live job lock was released. |
| Local inspect and synthetic tests | Source mirror and dedicated checkout passed; latest hosted CI pending this commit | Both checkouts completed 231 offline tests with 4 machine-specific skips each after the native cleanup and retained Blender diagnostic changes. The 3 Painter dispatch-gate tests also passed locally. The fifth native probe's offline, no-send preflight passed. [Windows CI #20](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36377038549) passed on the previous commit `5edd2a4ce9396a4a121e3ca07cbf5eb0f1c57fb8`; check hosted CI for this commit before relying on its changes. Earlier inspect/test receipts remain under `jobs/20260927T233929Z-cab582e7350c/receipt.json` and `jobs/20260927T234050Z-66e61f71fca5/receipt.json`. Disclose the skips. |
| Project verification | Current source and project checks passed | A fresh read-only target `verify --project` passed all 5 registry pins, the source manifest and authoring inventory; `source-check` matched the accepted digest with no changes. The source manifest covers 2,817 files. The older source `d11_verify_20260928.json` is a four-pin snapshot and does not replace the newer result. |
| Accepted vs AAA candidate | Installed accepted; no recovery required; AAA unaccepted | Post-change target status reports installed SHA-256 `3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`, relation `accepted`, `recoveryRequired: false`, and no candidate-capture lock. AAA's historical capture still reports `FAIL_ROLLBACK_PENDING`, with `BASELINE_RESTORED` rollback evidence. Refresh status before native work. |
| Project-local MCP and workflow plugin | Dedicated CLI ready; this desktop task cannot yet call the project-local tools | User approved trust for the dedicated checkout. Codex CLI `mcp list` there sees `roadcraft`, `substance_painter`, `roadcraft_blender_scratch` enabled. Local marketplace is registered and `roadcraft-workflow` installed/enabled. Real stdio inventories: RoadCraft 11, Painter 79, Blender 2. This task is rooted at the Steam project, where no `.codex/config.toml` exists and none of those tools appears in its callable inventory. `MCP_DESKTOP_SCOPE_20260928.md` records the read-only comparison and the separate desktop verification step. RoadCraft remains read-only; tool scopes differ across servers. |
| Dedicated environment | Installed and verified | RoadCraft, Painter MCP and PyYAML are installed in `C:\RC\RoadCraftDev\toolchain\.venv`; project-local config is parsed and loaded by Codex CLI. The maintained source handoff was hash-checked. |
| New code Git repo/private remote | Private main and Windows CI operational | The private `main` was last verified at `5edd2a4ce9396a4a121e3ca07cbf5eb0f1c57fb8`; [CI #20](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36377038549) passed. The complete [CI #17](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36375506767) suite passed 218 core tests (one CI skip), 3 Painter dispatch tests and the Ed25519 dependency check. Verify hosted checks for later commits before relying on their changes. |
| Asset migration/Git LFS | Deferred by user choice; keep verified assets in place | `d11_asset_migration_preflight_20260928.json` verified 2,817 files / 3,477,364,242 bytes but failed its space gate. No copy occurred. Future migration requires a new decision and a fresh space check. |
| Native build/test/capture recipes | Preflight-only checks and 383-file partial-view contract passed; execution blocked | The `capture` recipe dry run and no-write `--plan` passed after pinning the reviewed runner. The plan declares 383 required files, 45 screenshots and 45 pre-screenshot partial links, plus source/package/scene/camera inputs. The runner emits `ReadPreCapture`, per-view action and transport pins, and a full output hash map; postflight checks these against the reviewed plan. Early-failure child cleanup now retains and authenticates a process handle before stopping a child. Synthetic tests pass; no native capture ran. The historical failed receipt remains failed. `jobs-recover` is synthetic-tested, not applied to a live lock. Complete global lighting, camera up, renderer state, loaded-scene proof and origin authentication remain absent, so no baseline/candidate pair is comparable. Five bounded runtime SSL probes are prepared but unexecuted; the new level-name reply is diagnostic only. `RUNTIME_LIGHTING_API_AUDIT_20260928.md` pins the editor/SDK method-table search; `NATIVE_LOADED_SCENE_PROOF_AUDIT_20260928.md` explains why OS FileIO trace would corroborate path/timing but not prove loaded bytes or screenshot origin. The separate lighting fixture needs over 14 GiB; the AAA runner has 4 GB start / 1.5 GB loop guards. The historical nearnew editor exit cause remains unknown. |
| AAA regression | Failed; acceptance pending | `d11_aaa_interior_regression_result.json`: technical gate false, releaseReady false, zero matched capture pairs and 45 required views failing. Existing capture contexts omit lighting/protocol; visual and campaign approvals are pending. |
| Blender no-edit USF bridge | Three roundtrips passed; native Blend export different and blocked | No-edit USF roundtrips remain byte-identical. The scratch MCP requires the accepted `project.json` inventory and rehashes its 68 declared authoring files. Native SDK exports differ from each repaired USF by 133 repaired-only, 76 native-only and 132 changed matched paths; material, rig and animation parity is missing. All native-Blend export gates remain `BLOCKED`. A four-run controlled scratch probe held inputs fixed: two `--threads 1` exports matched byte for byte, while two default-thread exports differed only in tangent arrays of three meshes. Subsequent scratch diagnostics default to one thread, with explicit `auto` and numeric overrides. A pinned read-only reconstruction worklist names per-asset relocation candidates and unresolved differences. A guarded, opt-in in-memory wiper repair has a passing no-write dry run; no repaired scratch export has run. The retained, hash-guarded Blender diagnostic reproduces the missing left push-arm bone's static hierarchy and matrix match in an unsaved process, without exporting or changing the source. Its result does not establish complete rig or asset parity. `D11_BLENDER_RECONSTRUCTION_WORKLIST_20260928.md`, `D11_WIPER_SCRATCH_REPAIR_20260928.md` and `D11_BLENDER_LEFT_PUSH_BONE_AUDIT_20260928.md` record the limits. |
| Painter integration | Capabilities verified; scratch project deferred; write gate added | Real stdio probe listed 79 tools, connected to Painter 12.1.5/API 0.3.5 and called `get_capabilities` successfully while no project was open. Baking presets, auto-rebake control and skew-painting control are unavailable. The server now leaves 34 inspection/planning tools enabled and denies 45 authoring/output tools unless its local process has `SP_MCP_ALLOW_PROJECT_WRITES=1`; synthetic FastMCP dispatch tests cover all 45. The user intentionally ended the Painter session to avoid interference and chose to leave it closed; no `.spp` was created and no accepted asset changed. |
| Storage | First exact batch complete; expansion dry run passed but deletion unapproved | `STORAGE_REVIEW.md`: 159 template copies removed, 6.30 GiB freed, retained originals verified. The separate 23,604-file / 5.93 GiB expansion remains untouched. Its 33 MB raw manifest is local and a verified 1.6 MB gzip copy is versioned. A full sandboxed dry run verified every candidate and counterpart but reported `applyReady: false` because CIM process inspection was denied. A distinct elevated full dry run reported `applyReady: true` with zero active processes at its inspection time, 21 retained packages, 166 retained source files and zero deletions. Any future apply needs specific authorization and a fresh pinned preflight. Git temporary pack remains separate. |

## 1. Finish checkout handoff and retain verified local tools

**Owner:** maintainer. **Dependencies:** final source edits. User trust,
dedicated environment installation and local integration registration are done.

1. Sync only maintained code/docs/config examples into the dedicated checkout;
   preserve its `.venv`, local paths, jobs and receipts. Record the compared
   file list and hashes. Verify imports resolve from the dedicated checkout,
   not the earlier editable source installation.
2. Retain the completed target evidence: 231 tests with 4 skips, all 5 project
   pins and 2,817 files verified, `source-check` passed, installed accepted,
   no recovery required. Run only checks warranted by subsequent changes;
   refresh live status before native work. Keep dated old receipts intact.
3. Check `.agents/plugins/marketplace.json` resolves the local plugin from
   the actual project root. Validate plugin and both identical skills after
   syncing. Check `.codex/config.toml` points to the dedicated interpreter,
   registry, config and cwd; local secrets/state remain ignored by Git.
4. Retain the completed user trust and Codex CLI loading evidence: all three
   local MCP entries enabled, local marketplace registered, workflow plugin
   installed/enabled. Do not request trust again merely because this plan
   previously listed it as pending.
5. Preserve real stdio smoke results: RoadCraft 11 tools; Painter 79 and live
   12.1.5/no project; Blender scratch 2 and ready/pinned 5.2.0. The current
   Steam-root desktop task has no project-local RoadCraft tools because their
   configuration is scoped to the separately trusted dedicated checkout.
   `MCP_DESKTOP_SCOPE_20260928.md` records both CLI inventories and the saved
   project root. Verify actual tool visibility from a task rooted at the
   dedicated checkout before relying on desktop MCP. CLI registration and
   subprocess smoke do not establish a desktop-agent call result. Keep
   RoadCraft inspection tools separate from Painter authoring and Blender
   scratch work.

**Exit evidence:** target source/import identity, passing tests and current
checks, official validation output, enabled local integrations and retained
stdio smoke results. Confirm actual tool visibility in the task that will use
them. Painter live connection is proven; project/export checks remain separate.

**Failure/rollback:** stop dependent native work on identity/config mismatch.
Restore the last known local config or disable only the new local integration;
retain diagnostics. These checks must not modify installed game packages.

## 2. Establish code Git history and a private remote

**Owner:** maintainer. **Dependencies:** final source handoff and test results.
Local `main`, origin and the verified private GitHub repository already exist;
asset migration is not required.

1. Retain the reviewed initial `d7ffa4a3` code commit in
   `C:\RC\RoadCraftDev\toolchain`. It includes code, tests, docs, workflow
   skill, plugin scaffold, CI and compact registry/evidence files. `.venv`,
   `local`, jobs, machine config, raw 33 MB expansion JSON, obsolete verify
   snapshot and generated builds remain excluded. The verified gzip copy of
   the expansion JSON is versioned. Recheck any later staging before each push.
2. Preserve the older `C:\RC\D11_Development` repository. Its earlier audit
   recorded 91 commits, `master` at
   `fadca63406efdaedf6601074b7efe40619c0f8e5`, tag
   `laptop-candidate06-baseline`, one worktree, no remotes, modified tracked
   files and substantial untracked work. Record fresh refs/status before any
   migration. A new code repo is not a replacement for that history.
3. Use the existing origin
   `https://github.com/gynganynja/roadcraft-toolchain.git`. Repository creation
   and its private lock icon were verified. The approved Git Credential Manager
   browser sign-in completed; `main` was pushed without force and its remote
   commit matched local HEAD. Verify future staged contents and compare IDs
   after subsequent pushes.
4. Run `.github/workflows/toolchain.yml` on the private remote and inspect its
   outcome. Its Windows/Python checks cover synthetic tests and MCP schemas;
   they do not validate native game rendering or machine-specific asset paths.

**Exit evidence:** initial code commit, clean intended status, verified private
remote, matching remote commit and successful CI. Independently preserve old
refs plus a recoverable copy of modified/untracked source before migration.

**Failure/rollback:** retain local commits if publication fails; correct remote
configuration without rewriting/deleting either repository. Preserve normal
Git packs and indexes. Never force-push the historical repository to simplify
the migration.

## 3. Preserve assets in place; keep migration as a deferred option

**Owner:** maintainer; user for any additional exact deletion scope or storage
location not already authorized. **Dependencies:** current space review and
pinned accepted source; native staging must respect the same space budget.
The user chose to keep assets at the current verified location. Do not run
migration, initialize a duplicate asset checkout or switch source-root pins as
part of current work. Storage review can continue within its existing scope.
The migration/LFS steps below apply only if that decision is later changed.

The migration gate is **30 GiB remaining reserve plus bytes still to copy**,
not merely 30 GiB free before starting. The recorded preflight had
12,931,457,024 bytes free (12.04 GiB), required 35,689,618,962 bytes (33.24 GiB),
and was short 22,758,161,938 bytes (21.20 GiB). These are dated measurements;
active builds/installations can change them. LFS object storage and native
staging need additional budget beyond the copy preflight.

1. Refresh free space and exact candidate state. Do not count the completed
   6.30 GiB cleanup twice. The expansion review establishes only 5.93 GiB,
   not a 15–20 GiB saving. Its elevated read-only preflight found no active
   owner at one instant; recheck immediately before any authorized apply.
2. For an authorized expansion batch, pin the reviewed manifest, establish
   process/job ownership, and recheck each file's retained counterpart,
   SHA-256, identity, exclusive allocation, link count and reparse ancestry.
   Preserve enclosing directories, accepted/AAA projects, captures, PAKs,
   logs, fixtures and source. The existing `cleanup_commit` executor is
   template-specific. The separate `expansion_cleanup` executor is implemented
   and defaults to dry-run; apply requires the exact manifest SHA-256 and a
   per-file durable journal. Review its full receipt and obtain authorization
   for this exact expansion batch before using its apply path.
3. Keep `C:\RC\D11_Development\.git\objects\pack\tmp_pack_vOMJaY` separate.
   Its recorded allocation is 4,014,342,144 bytes (3.74 GiB), one link, and Git
   classified it as garbage. The previous connectivity check passed, but
   does not prove the temp pack lacks recoverable unreferenced objects.
   Before any separately authorized removal: refresh refs, locks/processes,
   file identity/mtime/allocation, bounded connectivity and recovery/backup
   assessment. Never extend that finding to normal packs or perform gc/repack
   as a space shortcut while headroom is low.
4. For a future migration, if reviewed savings cannot meet the gate, evaluate
   an additional volume or explicit retained-data relocation plan. Keep the
   30 GiB reserve; do not lower it just to make preflight pass.
5. Only after a future migration decision, rerun `python -m roadcraft.migrate`
   with `--manifest`, its registry
   `--manifest-sha256`, accepted `--source-root`, new `--destination`, and
   `--receipt`. Without `--run` it is read-only. After the gate passes and
   within existing authorization, use `--run`; preserve the durable receipt
   for resume, and never replace/delete source bytes.
6. In the new asset checkout, verify Git LFS availability and configure
   reviewed binary patterns before adding assets (USF, Blend, authored
   textures and Painter project files as applicable). Track authoring inputs,
   not caches/redundant builds. Inspect pointers and `git lfs ls-files`, run
   LFS integrity checks, and verify a fresh checkout against the source
   manifest. Budget checkout plus LFS object-store allocation before copying.
7. Only after all 2,817 migrated files and authoring declarations verify,
   record a deliberate registry path handoff and new manifest pins if their
   content changes. Keep the accepted PAK hash unchanged. Do not rewrite old
   Git history into LFS until its refs and uncommitted/untracked work are
   independently recoverable and that migration scope is established.

**Current exit evidence:** existing source location retained, current manifest
and authoring checks pass, and no migration/source-root change performed.

**Future migration exit evidence:** fresh passing space preflight; completed migration receipt;
source/destination hash parity; LFS pointers and hydrated checkout verified;
registry checks pass from the new source root; old sources/history retained.

**Failure/rollback:** resume only from the matching durable migration receipt;
stop on mismatched existing destination files. Continue using original source
paths until verification passes. Deletion has no automatic undo: its retained
counterpart/backup and per-file receipt must support recovery before removal.

## 4. Prepare preflight-only native recipes; resolve execution blockers

**Owner:** maintainer. **Dependencies:** current source identity, sufficient
per-recipe disk budget, no conflicting native process/lock, known accepted
package and verified rollback source. Migration is not a prerequisite if the
current accepted source remains the reviewed input.

Native recipe preparation is **preflight-only**. The separate lighting fixture
needs more than 14 GiB and is below its guard. The AAA capture runner's 4 GB
start / 1.5 GB loop guards are different; its prior run failed after the editor
process vanished during nearnew view 4. The guarded runner now declares a
collision-free eight-hex-digit run ID and a digest-sealed output contract
before execution; its `--plan` is read-only. The reviewed
`d11_aaa_native_capture_plan_c0de2026.json` declares 383 required files,
six optional hidden-probe files, 45 screenshot source paths, transient paths
and opaque editor runtime roots. It pins the runner, installed and candidate
packages, audited package receipt, 1,644 source pins, partial-linker and
helper source hashes, and validation scene/camera inputs. The earlier
`a1b2c3d4` plan is archival because the
runner changed. Planned resolution and lighting remain unknown. See
`NATIVE_CAPTURE_OUTPUT_CONTRACT.md` and
`NATIVE_CAPTURE_FAILURE_ANALYSIS_20260928.md`. The subsequent
`AAA_NEARNEW_EDITOR_EXIT_AUDIT.md` pins the last successful camera reply,
editor disconnect, and failed PID precheck: the fourth screenshot request was
never sent, and no accessible crash record proves an exit cause. The guarded
runner now retains the owned engine process handle and records timestamped
camera, settle, pre-screenshot read, capture, screenshot and cleanup boundaries
with exit status;
this is code-only synthetic evidence until a future native run exercises it.
No new native build, installation or capture is claimed.

The job runner keeps its shared lock after any failure following native launch.
`jobs-recover` is a separate dry-run-first recovery command. It verifies the
dead job owner, terminal recovery-required job receipt, accepted installed
package, pinned registry/config, terminal configured transaction receipts,
absence of transaction locks and active authoring processes. Its apply path
records a distinct recovery receipt and clears only that shared job lock.
The code was synthetic-tested; no real retained lock was released.

`capture_pair_protocol.py` now provides a read-only context validator for a
future baseline/candidate pair. It requires pinned raw editor observations
immediately before each image, equal actual camera/lighting/scene context and
measured image dimensions. Exact D11 3×15 coverage is required for
`pairComparable=true`. The validator also requires distinct run IDs and
one actual screenshot and observation file per view across the pair, and
rejects overlapping view intervals within a run. Identical image bytes in
separate files remain valid for A/A controls. Its output always keeps native
postflight, technical and release gates false. The current native runner does
not emit this observation schema or link it to successful outer receipts, so
no historical capture can pass by inheriting the policy's proposed
lighting/protocol labels. See
`BASELINE_CANDIDATE_CAPTURE_PROTOCOL.md`.

The read-only `native_capture_observation.py` diagnostic extracted only camera
position/forward, 913×559 runtime screen size and truck-local Sfx light state
from sealed historical editor replies. In the maroon front-seat sequence,
enabled local lights changed from zero in `SetCab` to eight in `CaptureCab`;
the screenshot trigger occurred before the latter reply. Camera up and global
environment/exposure/tonemap/renderer state have no proven readback in the
available scripts. The result is `PARTIAL_CONTEXT_ONLY` and never eligible for
pair comparison. See `NATIVE_EDITOR_OBSERVATION_API_AUDIT.md`.

`NATIVE_EDITOR_RUNTIME_API_PROBE.md` pins a deeper local search. Shipped SSL
source proves `$weather_manager_sys.GetWeatherState()` and its rain fields;
the installed editor binary contains `GetCurrentSunDirection` and
`PresetSys.GetDayTime` names, but their SSL signatures are unverified. Five
independent scratch SSL fragments and a fail-closed parser are ready for a
future disposable editor smoke. They were not compiled or run, and cannot
fill missing exposure, tonemap, ambient color, renderer mode or complete light
state. Keep capture-pair eligibility false until actual readback and timing
linkage exist.

`NATIVE_PROBE_TRANSPORT.md` describes the separate bounded transport for those
five fragments. Its default offline preflight pins the fragment, scene source,
editor, helper, config and SDK transport DLLs without contacting the editor.
The weather and level-name maroon preflights passed; no transport request was sent. A future
exact-PID smoke would write a new ignored scratch receipt and can establish
only partial runtime readback, not a matched capture pair or loaded-scene proof.

The guarded legacy runner's current no-write `--plan --run-id c0de2026`
recheck passed with status
`CAPTURE_OUTPUTS_DECLARED_NO_SWAP` and contract SHA-256
`e4a61f0d585b1621bcc389e58edb496e671ef10922aaf01c5b9ec31fcb8020de`.
Its 383 required files and six optional files were declared without launching
the editor or changing the package. The runner now pins and rechecks an editor
child process handle before stopping it in the early-failure path, rejecting an
unowned or unavailable child. The normal attached cleanup path is unchanged;
the reviewed runner SHA-256 is
`6449ddc08c81165231ee39f90e171b2f5a2c7fdecc9e2e21b1b2c1b2d4733585`.

`NATIVE_LOADED_SCENE_PROOF_AUDIT_20260928.md` records the pinned editor's
candidate actor/editor scene-name bindings and the absence of a demonstrated
SSL getter for loaded scene bytes or screenshot origin. It separates a level
or actor label, a mounted on-disk source tree, and a consistent screenshot
receipt from actual runtime scene and producer authentication. The two proof
flags remain false until an engine-origin check tied to the capture interval
has been tested in a disposable editor and reviewed. The audit also records
why a future Windows FileIO trace would corroborate process/path/timing but
could not prove loaded bytes or rendered-image origin by itself.

`NATIVE_PARTIAL_VIEW_LINKAGE.md` defines a fail-closed handoff for
`ReadPreCapture` immediately before each screenshot request. The maintained
runner now emits one partial link per view, the 383-file contract declares its
files, and read-only postflight rechecks the exact action/transport/output
chain against an externally pinned plan. Synthetic tests pass. The link still
does not authenticate native origin, prove a loaded scene, or observe complete
lighting. The failed historical run cannot be upgraded.

The read-only `python -m roadcraft.native_capture_postflight` check now
requires an externally pinned no-write plan, exact run ID,
candidate/baseline/installed hashes, successful rollback, all 383 planned
outputs and the three nested receipts' 45 partial image/probe links. It rejected
`candidate_capture_bd58bce0.json` with
`captureIntegrityPassed=false` and exit 1 because the outer status remains
`FAIL_ROLLBACK_PENDING`. This is technical evidence only; it cannot make the
legacy runner safe to launch or satisfy visual/campaign acceptance. See
`NATIVE_CAPTURE_POSTFLIGHT.md`.

1. Audit existing D11 builders/capture runners and document each unsafe
   behavior with the required adapter/fix before allowing execution. Prepare
   explicit preflight-only build/test/capture phases with absolute executable
   argv/cwd, pinned inputs, output expectations, native flags, bounded timeout
   and realistic free-space requirements. Keep execution blocked until runner
   behavior, process ownership, installation/rollback boundaries and disk
   needs are verified. Do not invent successful output pins or weaken the job
   schema to accept unknown artifacts silently.
2. Review `build`, `test`, `capture` or `inspect-job --recipe PATH` dry-run
   output. `test` must identify whether it is a synthetic toolchain test or
   an actual native test. Do not use `--apply` on these native recipes now.
   After the documented runner fixes and space/process/source gates pass,
   execute only the intended reviewed phase and retain job logs and receipt.
3. Before package replacement, `install --candidate NAME` must match the
   expected current installed hash (accepted pin unless explicitly supplied).
   Review the dry-run, then use the transaction's retained prior bytes for
   `rollback --receipt PATH` or known-hash `recover --receipt PATH` if needed.
   Read each dry-run before any applied recovery. Keep legacy capture rollback
   journals distinct from new package-transaction receipts.
4. Pin the package receipt and audit allowed archive changes by normalized
   member path and occurrence. Seal native captures against the exact tested
   package/source/protocol. Record process exit, timeout and rollback outcome.

**Current exit evidence:** reviewed preflight output and explicit recorded
execution blockers, with no native/package mutation.

**Future execution exit evidence:** passed native job receipts, package/receipt hash chain,
expected scoped archive changes, all required views, and verified restoration
of the expected installed package. Synthetic job success alone is insufficient.

**Failure/rollback:** stop promotion immediately. Preserve native failure logs
and locks; verify external editor/package state before clearing a retained
lock. Unknown live hashes require investigation, not an unconditional copy.
Successful rollback does not make the failed capture successful.

## 5. Complete AAA regression, visual and campaign acceptance

**Owner:** maintainer for capture/metrics; designated reviewer for acceptance.
**Dependencies:** step 4 and a reproducible baseline/candidate protocol.

1. Keep `aaa-20260928` a candidate. Investigate its failed native capture and
   obtain a new successful sealed run; preserve the old failure receipt.
2. Capture all 15 required views for each of maroon, nearnew and worn for both
   baseline and candidate. Record actual variant, scene, camera, lighting,
   resolution and protocol at capture time. The existing policy's proposed
   lighting/protocol IDs are future requirements, not permission to fill
   missing metadata into historical evidence by assumption. Add the
   capture-time probe and outer-receipt links needed by
   `capture_pair_protocol.py`, then require its exact 45-view context result
   before considering images comparable. Its output alone never proves native
   postflight or release readiness.
3. Generate the HTML/JSON review from externally pinned receipts. Rerun
   `python -m roadcraft.regression` against the reviewed policy: require valid
   source/package/capture links, allowed capture statuses, 45 unique matched
   view pairs and no required-view failures. Define numerical thresholds and
   units before the run for any claimed metric improvement; the current
   interior policy has no handling/terrain/campaign thresholds.
4. Review the actual images and record visual decisions for the same candidate
   and gate digest. Perform campaign checks separately: shop spawn, handling,
   visible track/trail behavior and physical rut behavior require campaign
   evidence, not private-editor substitutes. Record exact variant/scenario
   and unresolved findings.
5. The implemented regression gate expects detached signed visual/campaign
   claims bound to the candidate hash and gate digest, plus an external
   reviewer-key trust store. The local `review` install extra declares
   `cryptography>=42`, and CI run #10 installed and imported it before the
   signed-claim tests. `REVIEWER_CLAIM_HANDOFF.md` documents the
   reviewer-controlled key and signature flow. The current code additionally
   requires each signed claim to pin its own nonempty human review file by
   policy-relative path and SHA-256. Missing, changed or duplicate stage
   evidence keeps acceptance pending. Actual visual notes, campaign play
   receipts, reviewer identities and decisions still must come from real
   reviewers; do not generate any of them on someone's behalf.
6. Update acceptance/registry pins only after technical, visual and campaign
   requirements are met and the acceptance decision is recorded. Preserve the
   prior accepted package and receipts for rollback.

**Exit evidence:** technicalPassed and releaseReady true under the intended
policy, verified image/metric reports, valid reviewer claims and recorded
campaign results. If a gate is out of scope, change scope explicitly rather
than reporting an unperformed check as passed.

**Failure/rollback:** keep the accepted pin and installed baseline; preserve
failed candidate evidence and address the specific missing/regressed checks.

## 6. Complete Blender authoring parity

**Owner:** asset maintainer and designated parity reviewer.
**Dependencies:** pinned source inventory and step 4 native verification.

The three completed Blender 5.2 USF read/write tests prove no-edit
serialization only. They do not prove historical `.blend` files reproduce the
repaired rig, animation, materials or triangle order. Direct diagnostic native
exports now show that all three historical `.blend` references are byte-identical
and all three exported USFs differ substantially from the repaired sources:
133 repaired-only paths, 76 native-only paths and 132 changed matched paths
per asset. The three actual export-gate calls returned `BLOCKED`. The SDK
importer cannot reconstruct material names, skin/bind data or animation into
a valid substitute `.blend`. Repeated exploratory exports also differed in
whole-file SHA-256, with cause unproven. See
`D11_BLENDER_AUTHORING_PARITY_20260928.md`; retain the `usf-repair` route.
The retained scratch pairs localize their byte differences to small tangent
float changes in `Blade_vis`, `Ripper_vis` and `Ripper_vis_LOD1`. A subsequent
three-way read-only comparison used outputs with the same helper, Blender and
`.blend` pins, although command arguments differed. A later four-run scratch
probe used the maintained `blender_authoring` diagnostic with the same pinned
inputs: two `--threads 1` exports were byte-identical; two default-thread
exports differed only in tangent arrays of those same three meshes. Blender
5.2.0 source offers a plausible parallel-accumulation mechanism, but the
runtime root cause remains unproven. The `game-dev` CLI was unavailable, so
the maintained diagnostic was called directly. Every native-Blend export gate
remained blocked. The scratch diagnostic now defaults to `--threads 1` to
reduce tangent-only byte drift; `--blender-threads auto` restores Blender's
default setting for comparison and numeric overrides remain available. This
changes diagnostic execution only, not the accepted source or export gate. See
`D11_SCRATCH_USF_TANGENT_DRIFT_20260928.md`.

The scratch Blender MCP now rejects a caller-supplied inventory unless its
path and SHA-256 match `project.json` `accepted.authoringInventory`; it also
rehashes the accepted inventory's declared source before Blender or scratch
creation. Eleven synthetic tests and a real read-only 68-file preflight passed.
This does not establish Blender authoring parity or permit a native export.

The read-only `blender_reconciliation.py` worklist verified the current
68-file authoring inventory, all three pinned parity archives and retained
scratch native USFs. Per asset it identifies 66 same-leaf path relocation
candidates that remain unverified, 67 unpaired repaired-only and 10 unpaired
native-export-only paths, 126 changed mesh nodes and a missing 36-key wiper
animation. Exact per-node material and skin/bind differences are in
`d11_blender_reconstruction_worklist_20260928.json`; the derivation and limits
are explained in `D11_BLENDER_RECONSTRUCTION_WORKLIST_20260928.md`. These
findings guide work on disposable authoring copies and do not change the
`native-blend` gate.

Read-only inspection of the pinned base Blend found that its wiper armature
has two existing actions but no active action, while the bundled SDK only
initializes bone animation when an action is bound. The SDK also omits each
action's final frame when baking. `blender_wiper_repair.py` now offers an
opt-in, source-pinned, in-memory repair for a future scratch-only export; it
requires the repaired USF's backward-then-forward action order and includes
both endpoint frames. Its exact unexecuted command and output paths are in
`D11_WIPER_SCRATCH_REPAIR_20260928.md`. Synthetic tests and the no-write dry
run passed. This is a repair hypothesis, not animation parity evidence, and
the native-Blend gate remains blocked. A read-only Blender check confirmed
the guarded action order and unchanged source hashes. Read-only parsing also
confirmed that actor animation metadata already matches between the retained
native scratch USF and repaired USF; the missing wiper splines remain the
specific animation gap. The helper cannot by itself reach full asset parity.

The retained hash-guarded Blender 5.2 no-save diagnostic reproduced the base
rig's missing `IK_push_arm_left_base` between `BoneBladeLift_cdt` and
`IK_tilt_left_base`. Its real rerun returned `IN_MEMORY_STATIC_PATH_MATCH`:
the new bone's world matrix matched the repaired USF within `3.58e-7`, while
the existing left base and tip pose matrices changed by at most `2.27e-6`.
It verified unchanged source and SDK hashes and made no Blend save or USF
export. `D11_BLENDER_LEFT_PUSH_BONE_AUDIT_20260928.md` records the pinned
inputs, invocation, and arbitrary edit-bone length. The repaired node also
has an `IK_push_arm_left_tip` child that this diagnostic does not reconstruct.
Skin, bind, animation and full asset parity remain unproved.

1. Keep the declared `usf-repair` route authoritative. Work on separate copies
   when reconciling native Blender authoring sources.
2. For each asset, establish hierarchy, transforms, geometry, normals/tangents,
   UV/colors, materials, skinning, bind matrices, LODs, metadata, animation,
   compilation and native-view parity required by `source.py`.
3. Create the reviewed parity receipt bound to that asset's current digest and
   repaired USF SHA-256, with every required check supported. Pass
   `require_export_allowed` before adopting `native-blend` as the export route.

**Exit evidence:** asset-specific reviewed parity receipts, gate success,
compiled/native evidence and an explicit source-inventory update.
**Failure/rollback:** retain repaired USF and the existing export method;
discard only disposable scratch outputs. Never overwrite authoritative USF
with an unverified generic Blender export.

## 7. Complete Painter project checks and controlled exports

**Owner:** maintainer; machine owner for app login/UI prerequisites.
**Dependencies:** step 1 transport/trust (complete), appropriate disposable
project/input assets, and space for verified backups/exports.

1. Retain the earlier live Painter 12.1.5 connection, 79-tool inventory and
   `get_capabilities` probe. No project was open then. The live API reported
   `baking_presets=false`, `auto_rebake_control=false` and
   `skew_painting_control=false`; see `PAINTER_CAPABILITIES_20260928.md`.
   The user intentionally closed Painter before disposable-project creation
   to avoid interference and chose to leave it closed for now. See
   `painter_disposable_probe_20260928.json`.
   Preserve any subsequently opened
   user project and recheck live status before authoring. The README's tested
   12.1.1 is not the observed runtime.
2. The scratch UV cube OBJ/MTL and guarded helper are prepared under ignored
   `local/painter-disposable-20260928`; the intended `.spp` does not exist.
   When Painter is available, recheck that no user project is open, use the
   narrow declared mesh/project roots, create only the disposable project,
   and run `get_project_info` plus read-only layer inspection. Record exact
   project identity. Existing health evidence does not establish successful
   project creation, bake or export.
3. Configure narrow `SP_MCP_EXPORT_ROOTS`, `SP_MCP_PROJECT_ROOTS`,
   `SP_MCP_MESH_ROOTS`, `SP_MCP_BAKE_MESH_ROOTS` and `SP_MCP_RESOURCE_ROOTS`
   only for the required workflow. The Painter MCP defaults to inspection;
   enable `SP_MCP_ALLOW_PROJECT_WRITES=1` only in a deliberately controlled
   local server session for a disposable or verified project copy. Keep
   arbitrary Python execution disabled.
   Start with a disposable project/copy and `plan_texture_export`; review
   channels, color space, bit depth, resolution, naming and conflicts against
   actual RoadCraft material requirements before an authorized export.
4. For a first controlled export, preserve a verified `.spp` copy, export into
   new scratch paths, verify output hashes/dimensions/channels, then compile
   and capture through the same source/package gates. Do not write directly
   over accepted source textures during the smoke test.

**Exit evidence:** app-visible MCP calls, recorded live capabilities, verified
backup/export receipt, and native material comparison where exports are used.
**Failure/rollback:** restore the verified project copy or retain the original
project; leave accepted textures/packages untouched. Remove/disable only the
new local integration config if transport cannot be made reliable.

## Immediate execution order

1. Git credential sign-in, private `main` push, remote commit comparison,
   and Windows CI run #17 at `152737c` are complete. Keep later changes
   versioned and recheck CI after each push.
2. Use the registered, smoke-tested local integrations through their dedicated
   checkout, then confirm desktop tool visibility in a task rooted there. The
   current Steam-root task has no project-local MCP entries. Painter capability
   probing passed, but the app closed before disposable-project creation.
   Resume the prepared scratch check when the user chooses to reopen Painter
   and its current project state is rechecked.
3. Keep assets in their verified current location. Continue exact storage
   review as authorized, preflight-only native recipe work and capture-protocol
   definition. Do not migrate assets now.
4. Resolve the historical editor disconnect, retained-lock recovery and
   baseline/candidate capture protocol; meet native staging space, process
   and source gates before any native execution. Only then produce new matched
   AAA evidence and perform visual/campaign acceptance checks.
5. Reconcile Blender hierarchy, materials, rig, skin and animation against
   the retained parity diff before seeking native export approval. Revisit
   LFS migration only if the user changes the in-place asset decision; retain
   its 30 GiB reserve gate. Keep accepted identity and historical evidence
   stable throughout.

For every completed item, append or link a dated receipt with command/runtime,
input pins, outputs, verification result and rollback outcome. Change this
plan's status only after that evidence exists.
