# Build pipeline and SDK tools



Vehicle SDK stages and their observed traps. The shared create/edit entry point

for all mod types is [mod-workflow.md](mod-workflow.md).

The mod projects (`<project>/tools/build.py`, `prepare.py`, `create_models.py`, `truck_bro.py`,

`validate.py`, `install.py`, `toolchain.py`) historically follow one layout. New

workspaces use `mod-init`; reuse an existing adapter only after reviewing its

vehicle-specific assumptions. Every step is bound to a toolchain recipe (`run build|test --apply`, `pin`), so a

candidate carries receipts for what built and checked it.



## Stages



| Stage | Tool | Success check | Grade |

|---|---|---|---|

| Textures | `tools/bin/TextureConverter/TextureConverter.exe <tga> <pct> --usage <MD, MNM, MSCRGHAO, MD+MT, MH>` with `converter.config.ps` = the descriptor | output exists; header mip count | Build |

| Models | Blender 5.0 in the background (`--factory-startup`) builds the body and wheel `.blend` files (rig, LODs, collision, locators) | the script's completion marker | Build |

| Import | `tools/bin/editor_build_tools/asset_importer/asset_importer.exe -p <project> -s <blend> --output <mods_source>/models/mods --exp_opt export_options.ps --blender_exe <blender>` | log line `Asset importing successfully finished` | Build |

| Classes | the batch editor (a private copy of IntegrationStudio with a batch plug-in, hidden) generates `autogen_dw/...` from the BROs | `Task <name> was successfully finished`, generated files present, not the exit code | Build |

| Package | `tools/bin/ModPakBuilder/mod_pak_builder.exe --project <p> --resource-roots-file <roots> --output <pak> --mod_file <mod>` | exit 0 and the pak exists | Build |

| Retail export | the editor package's `autogen_dw/` brands re-exported as the flattened `ssl/<brand>_<suffix>` brands the retail game discovers (the Mod Manager's export naming) | the export audit | Build, Game (the mods appear in the store) |

| Install | copy to `<game>/root/mods/<mod>.pak`; game and editor closed; keep the previous bytes and a receipt | hash of the installed file | Build |



A project for the tools is a relocatable SDK project folder (`.project` referencing the game's

`root/.project`, `mods-dir`, configs); build into it, never into the editor's own working copy.



## Traps



| Trap | Grade |

|---|---|

| The undocumented CLI tools (`pct_resource_gen`, `tpl_asset_import`, ...) open a modal crash dialog on wrong arguments: do not probe them with `--help` | Build |

| Batch class generation can fail with `ModelDisallowedTypeException` (class database refresh race); retrying with the previous generated files left in place succeeds, sometimes only after several attempts (each gets further; allow five with a pause); check the success line, not the exit code | Build |

| The hidden batch steps refuse to run while an IntegrationStudio session of the owner's is open | Build |

| An editor run started within about 40 s of class generation hot-reloads the fresh classes and the engine asserts; wait about three minutes | Build (Roamer 105) |

| The generator accepts unknown or incomplete settings silently (e.g. a suspension collection without its flag): read the compiled class (`lint-bro --class`) | Build |

| `mod_pak_builder` resolves references only inside the mod project: copy any shipped resource the mod uses into it under a mod name | Build (Roamer 105) |

| The SDK asset exporter hangs on meshes without a UV map (the EX5600 source had 614 such objects): the builds refuse a mesh without exactly one UV map, and drop colour attributes | Build |

| Blender's "Cannot change old file (file saved with @)": a stale `<file>.blend@` blocked the rename after a save; delete it and save again, with retries | Build (Roamer 105) |

| The editor's Documents folder may be OneDrive-redirected: its working copy and built mods live there, and sync is a suspect in file-lock failures | Build |

| Blender: the SDK accepts 4.5 / 5.0; a community guide reports 5.1 breaking armatures; do not point the SDK at 5.2 | SDK, community |

| The toolchain's native-process gate matches any process with "blender" in its name, including MCP helpers; headless build steps are declared `native: false` and check for the game and editor themselves | Build |

| Class generation launches IntegrationStudio (hidden): it counts as an editor run, so it waits until the owner is not using the PC (queue it for when the game closes) | Owner's instruction |



## Checks before installing



The shared recipe helper `roadcraft.vehicle_workflow.enhance_recipe` now wires

source, compiled and final checks into the adapter pipeline. New projects can

start with `roadcraft mod-init --kind vehicle`, fill their explicit source/adapter contract,

and use `mod-recipe` to generate a new pinned recipe. The older vehicle commands

remain compatible. It is a workflow

starter; source art and vehicle-specific rig generation still belong to the project.



Reviewed isolated steps can opt into `--incremental` with complete output

trees for compiler sidecars. Receipt hashes and existing output bytes must

verify before reuse. The first successful incremental build establishes the

cache; shared checks continue running. `jobs-summary` reports actual elapsed

times and reused stages. These commands do not establish driving acceptance.



**Build:** When adding or merging a CLI dependency, include its shared module

in `vehicle_workflow.RUNTIME_FILES`, even if a vehicle build does not call its

subcommand: importing the CLI loads it. The onboarding integration required

adding `onboard.py`. The regression test

`VehicleWorkflowTests.test_new_cli_dependency_change_requires_recipe_regeneration`

checks that a change to that module rejects the old recipe before execution.

Generate a new pinned recipe after shared runtime changes; passing preflight

does not mean the vehicle has been rebuilt or driven.



1. `roadcraft lint-bro <bro> --class <auto_mod.cls> --tpl <body.tpl>`: no errors.

2. The project's rig audit on the exported model (bone positions, parents, axes).

3. The project's static validation: authored files current, compiled class carries the settings,

   package members equal the built files, textures and mips.

4. `roadcraft suspension --geometry measured --axle ... --share ...` for each axle: off the stops
   (`height + min`, `height + max`) in every case, including `measured`.

5. For a change to suspension, wheels, masses or joints: measure it against the installed version
   on the physics bench, with the owner's go-ahead ([physics-bench.md](physics-bench.md)).

6. Nothing above proves how it drives; the owner's drive is the acceptance.



## Testing in the editor (when the owner allows it)



The Roamer 105 project drove its candidates in the editor's play mode without the owner (its

`tools/WORKFLOW_TOOLS.md` describes the runner). What that taught (Build):



- Engine-side input override (the input `State` method) drives engine, parking brake, low range,

  pedal and steering; key presses went to the wrong window when the viewport lost focus.

- A connected wheel controller overrides the engine-side requests: keep it centred or unplugged.

- Re-assert the parking brake off with every input; a speed plateau was once a re-engaged brake.

- The suspension probe's `travel` / `maxTravel` are constants; use `liftAlongSuspensionMetres`.

- Screenshots come from the engine's `SaveScreenShot` (BMP under `root/bin/pc`); window grabs were

  refused or showed the editor.

- Editor play mode is not the retail campaign: lamps, store registration and saves still need a

  retail drive.

- `roadcraft bench` packages this for physics changes: an isolated copy of the project, variants
  applied from pristine files, fixed input schedules and a per-phase summary
  ([physics-bench.md](physics-bench.md), KGS-25 2026-10-02).



## Class-only repairs and maintained toolchain selection (Apoc, 2026-09-30)



**Build:** An existing adapter must follow ROADCRAFT_TOOLCHAIN or its machine-local selector,

including a preserved checkout's redirect, before importing shared code or editing the

library. Pin the selected runtime and add shared vehicle checks with `enhance_recipe`.

Migrate missing case findings with preimage checks; do not overwrite concurrent library work.



For a class-only build that reuses imported models, its prepare stage must be limited to

the changed BROs. Apoc's full prepare rewrites `.tpl.asset` descriptors and removes importer

metadata, which correctly failed the pinned-input check before packaging. Restore those

exact descriptors from the pinned candidate and use `prepare --only bro`; do not weaken

the pin guard or broaden the allowed package diff. The repaired build includes source and

compiled shared checks; test includes the final shared check plus the project's wheel audit.





## Lada first-build findings (2026-09-30)



**Build:** The Lada's fresh FBX route completed body and two wheel imports, BRO

generation, retail export and native packaging (candidate `lnv-first-drive-20260930`,

SHA-256 `df32b6f2f34cbbf2247504f06b8f5e630c17d2067904979c91fc2ecb4d4e79b0`).

The official packager emitted two byte-identical occurrences of each model markup.

Preserve ordered ZIP occurrences; reject conflicting duplicate bytes rather than

assuming every valid native package has unique member names. Lada validation records

each duplicate count and checks every occurrence's hash and archive CRC.



Two early Lada jobs failed while atomically updating receipts with Windows errors 32

and 5. `jobs._atomic_json` now retries only Windows errors 5/32/33 with a finite delay

(up to eight attempts), preserving the previous receipt until replacement succeeds.

`tests/test_job_receipt_retry.py` covers transient sharing errors, bounded permanent

failure, unchanged prior receipts, temporary cleanup and immediate unrelated-error

failure. The focused tests and existing job tests passed. This does not override

filesystem permission boundaries: the native importer's embedded runtime separately

needed execution with sufficient filesystem permissions.



For a first mod build, make a build-only recipe before compiled assets exist; add the

test phase after compilation so final-check input pins refer to real output files.

Recipe generation does not create those files. Native builds remain distinct from

live driving acceptance.





For an isolated interactive SDK launch, `--data-dir` is the native RESOURCE

root, not merely a folder of Profiles. Copy the SDK root resource files and

Docs/Icons/Templates/ModEditor folders into it; missing `xmodeditor.ps`

produced the Lada `Can't load XginePlugin plugin` dialog. Keep a separate

`--local-profiles-dir`. On restart after a diagnosed crash, the owned

historical crash-upload prompt may be deferred with its exact Later button.

A scenario echo after Play does not prove the current truck is ready: Play

can restart the engine and scene loading continued beyond the 25-second echo.

Confirm the current native truck identity and simulation state before inputs.





## Replacement terrain-layer brands and native report retries (Lada, 2026-09-30)



**Game/SDK:** Replacing a `layers.rock` section with copied `ground` fields requires explicit `__type = "ground"` when the original ground section relies on its dictionary key for type inference. Otherwise the isolated native scene aborted with `Can't load brand rock`. Preserve the failed launch and omit/regenerate only the copied game-material cache. The corrected Lada fixture loaded and reported `mud` under the overlay, while extrusion depth remained zero; material identification alone does not prove deep deformation. Evidence: Lada `runtime/rut_candidate/startup_failed1`, fixture correction receipt and `revisions/rut_contact_v4/fix_soil_fixture.py`. The fixture helper now writes the explicit type.



A native PowerShell report replacement also failed with access-denied code 5 wrapped in a method-invocation exception. The local contact probe now unwraps inner exceptions and bounds retries to Windows codes 5/32/33. It retains original evidence and never retries the vehicle-control action merely to rewrite its report. Subsequent contact captures completed. Shared Python job receipt retry already covers these native codes; a shared PowerShell transport rewrite is deferred because these are project-owned probes, not a shared toolchain module.



### Validate inherited trail fields and gate the actual retail process name



Lada effects v5 (**SDK/Build**, 2026-09-30) extended its BRO schema evidence with the

shipped `ssl/game/truck/wheel/wheel_trail.cls` and `.sfx`. BRO-only field discovery

incorrectly rejected inherited `visuals.texture.nameTex`; the native actor explicitly

uses it, and the SFX inherits sfx_trail_base. Keep evidence hashes in the schema cache

instead of broadly allowing unknown fields. Object markup uses

`objSettings.settings.<object>`; a direct objSettings object map is invalid. An

unproven `lighting` field copied from an older helper was removed after schema review.



Exact `Get-Process Roadcraft` can miss `Roadcraft - Retail.exe`. Use the maintained

substring process scan (roadcraft/integrationstudio/modeditor), including for hidden

generation, and fail closed if tasklist cannot be read. The Lada live launcher blocked

retail overlap; its generation helper now uses the same gate. Do not terminate an

owner's process to clear it. Evidence: v5 launch output, native query, rc_native.py

gate and focused launch-prevention test. No broader process-management rewrite.





### Inline visibility brands and native startup evidence (Lada v6)



**Game/SDK:** compiled schema success is insufficient when object markup names a

resource brand without its dependency. V5's unresolved `invisible` visibility

crashed during scene load. Replacing only visibility with inline concrete

`tpl_markup_visibility_flags` restored Play; v6 audits those flags and compiled

point-exhaust anchors. Do not generalize this to banning valid external brands.

The optional unsupported geom-settings collision field was later removed but

was not necessary for the isolated startup fix. Evidence: Lada v5

native_diagnostic_result and v6 effects_result, build-007/test-008.



An automation echo may still run after a native crash. Require a successful

current-truck/simulation probe, inspect stderr/crashes, and preserve the fixture

seal. Lada v6 verified all 361 sealed files again after Play, then closed its

owned editor cleanly. Thumbnail generation timeouts were nonfatal to this run.

Keep build-time receipts immutable and attach later native evidence separately.

Local checks cover this model-specific visibility/emitter contract; extending

generic lint to all brand resolution is deferred pending schema/resource inputs.



### Utility-only builds preserve tested exterior bytes (Lada v7)



**Build, 2026-09-30:** for a gameplay-only edit, Lada's configure_workflow

`--gameplay-only` pins the existing model, texture, material and markup files as

inputs and runs prepare-BRO, source check, native generation, compiled check and

package. It does not re-export geometry. Shared vehicle checks still run. The

final package audit compares every existing exterior/collision/tyre asset byte

and non-utility compiled property with the reviewed v6 baseline. A reuse claim

therefore has actual input and output evidence rather than relying on file dates.

Full rebuild remains available. Pin Bro.Compiled.pak when a new authoring helper

reads stock scout definitions from it. Evidence: Lada build-008/test-011 and

tools/scout_utilities.py, audit_utilities.py, configure_workflow.py.







## Settle a source fixture before starting its native engine (Lada v8)



**Game, isolated editor:** a newly copied/generated fixture can be hot-reloaded

while the first native engine is starting. Logs show `Real Time Editing Reload

Brand`, followed by a request for nonexistent generated `.ssc.resource` files

(auto_truck_library, or auto_lada_niva_replicated after removing the aggregate).

The unchanged v7 baseline failed identically. Renaming the aggregate brand,

excluding installed mod directories, and enabling UseJsonBrands did not fix it.

Do not ship those speculative changes or strip required vehicle resources.



The Roamer autonomous_drive_test.ps1 already documented this fault on 2026-09-12:

launches within about 40 seconds failed; aged fixtures at 100+ seconds worked.

Reopening Lada's original sealed 362-file fixture with no source/config changes

worked and yielded live cockpit/wiper data. Lada launch_drive.ps1 now waits until

the newest source creation or write timestamp is at least 110 seconds old.

Creation time matters when copy tools preserve old write times. Count the seal

time instead when creation timestamps are not reliable. Waiting is bounded in

15-second chunks, and the actual engine/truck probe is still required: the

automation ready marker also appears after startup crashes. Thumbnail timeouts

are not by themselves proof that the gameplay engine failed.



Evidence: Lada runtime/interior_v8, r8baseline, r8fixed, r8isolated, r8clean,

r8json (failed hypotheses), and interior_v8_settled (successful original fixture).

This is a source-editor startup race, not a demonstrated retail package fault.

The guard is wired into Lada's launch adapter; timing remains SDK/machine scoped.



**Final guard verification (Lada v8):** the freshly copied `r8final` fixture used
the standard project config, waited through the new 110-second creation/write
timestamp guard, and reached native Play successfully. Its exact 362-file seal
was unchanged after cockpit/rain tests and a clean editor exit. See
`runtime/interior_v8_final/review.json`, build-012/test-014 and the v8 candidate
result. This verifies the guard on this SDK/machine without making speculative
brand/config edits part of the package. The generic Roamer BodyFrames probe also
illustrated an adapter limit: its postcondition requires JOINT lines, so a truck
with no such joint records can return useful data but be marked failed. Keep
that report failed, or author a vehicle-appropriate verifier before reuse.


## Zero-weight skins in fresh native authoring (L275, 2026-09-30)

**Build, native SDK import:** rendering a vehicle at rest does not establish
valid skinning. A vertex-group name alone is insufficient. The first L275 body
import failed with `Object with vertices with zero weight`; the visible Blender
model had looked correct. Explicit rigid cab binding, explicit chassis weight
transfer/normalization, and an audit of every skinned vertex after LOD generation
fixed the compiler rejection. The body and both wheels then imported successfully.
Require positive weights on existing bones, at most four influences, and a
normalized sum before export. Do not infer from this result that every evaluated
Blender mesh loses its weights.

**Second cause (WALL-E, 2026-10-04, Build):** since Blender 3.0 vertex-group names live on the mesh, so a
mesh copied after skinning (an LOD made from LOD0, a lit lamp copy) arrives with the group; skinning it
again adds `BoneChassis_cdt.001`, which takes the weights while the armature knows only the bone, and
tplexp reports zero-weight vertices. Clear `vertex_groups` (and old armature modifiers) before skinning,
delete loose vertices, and audit before saving: one group naming an existing bone, every vertex at weight 1.

Evidence: L275 `reports/import_zero_skin_failed.log`, `source_skin_audit.json`,
`build_import.json` and `tools/create_models.py`. Generic shared enforcement is
deferred because the BRO linter does not consume Blender deform layers; this
project's actual Blender build performs the audit. Gameplay controls and driving
remain separate, untested stages.

## Package dependency closure and bounded report locks (L275, 2026-09-30)

**Build, current SDK:** successful body/wheel import and class generation did
not establish complete package dependencies. L275's first package job
`20260930T091227Z-3e46ea489971` failed on
`res://pct/mod_tuz_119lynx_trails_hdetm.pct.resource`. Its trail TD referred to
sample nm/hdetm/mask PCT/TD resources absent from the isolated project. Copying
the 12 payload/descriptor files from the installed SDK sample, and pinning all
12 as recipe inputs, allowed build-005 and full revised build-007 to package.
Use the packager's actual resource failure to close the dependency graph; do
not add placeholders or assume imports prove package closure. The native
packager already enforces linked-resource presence, so another shared checker
is unnecessary for this observed fault. Evidence: L275 prepare.write_bro,
configure_workflow and the preserved failed/successful job receipts.

**Game evidence writer, Windows:** native v1 driving stopped on a transient
report replacement lock. File.Move surfaced nested access-denied code 5,
outside the helper's IOException-only 32/33 handling. The already proven
utility recorder pattern unwraps InnerException and retries only 5/32/33,
bounded at seven attempts; other errors still fail. Applying it to the three
scoped L275 recorders enabled drive02. Preserve drive01 and recorders_before.
This does not authorize retrying arbitrary permission failures or bypassing
filesystem authorization. Evidence: revisions/runtime_v1/fix_recorders.py,
runtime/native_v1/drive02 and review.json. No generic permission rule changed.

## L275 Blender materials v3 (2026-09-30)

**Blender background authoring/Build, machine scoped:** launch art tasks with
CREATE_NO_WINDOW and project-local CUDA_CACHE_PATH/OPTIX_CACHE_PATH. The first
OptiX attempt reported read-only AppData cache failures and made no completed
first channel after several minutes. The successful CUDA pass also replaced
repeated shader AO rays with curvature wear and a separate local AO bake.
Do not attribute the improvement to only the cache or only the backend: those
changes were coordinated. Ten final atlas sets took 334.48s
in total, with eight-sample bakes, four CPU threads and this GPU. Earlier failed
logs/recipe are retained. A review save failed while making a Blender backup;
save_version=0 then saved the separate review file successfully. These settings
do not authorize modifying source assets or terminating unrelated sessions.

Pin masters, raw/export maps, UV patches, CC0 references/receipts and refreshed
UI art before native import. L275 configure_workflow now wires these inputs
into full recipes. Its background static phase checks the real baked artifact
hashes/pixels, imported dimensions/mips and exported resources. Build-009 and
test-010 passed with 208 static checks and
954 export checks. This was material work: compiled gameplay
and physics were compared with v2 separately. No new game/editor runtime
fixture was launched under the owner's no-focus-tests restriction.

Evidence: L275 reports/art_* logs, material_bakes_v3.json, build_009_execution.json,
test_010_execution.json, revisions/materials_v3/before and v2_gameplay.cls,
reports/gameplay_preservation_v3.json. Exact native runtime evidence belongs
to the older v1 candidate, not this material/proportion revision.

## L275 final lighting and installation (2026-10-01)

**Build, installed transaction:** the first L275 install failed with Windows
error 5 replacing receipt.json at SWAP_READY, before the live mod slot was
created. Its durable journal remained STAGED_VERIFIED. The shared recover API
verified prior absence and marked NOT_INSTALLED; a new transaction then installed
the exact final hash. Preserve both receipts and do not bypass recovery or the
expected-absence check. No old package was overwritten.

The existing jobs._atomic_json already retries Windows 5/32/33. Applying the
same bounded eight-attempt exponential backoff (50ms up to 500ms) to
transaction._write_json fixes this shared journal gap, preserving fsync/atomic
replacement and failing on persistent permissions or other errors. It is wired
through the existing install/rollback/recover _advance path. Four new tests cover
transient locks preserving the old journal, bounded persistent failure, other
permission errors, and first installation at the actual SWAP_READY failure point.
All four plus seven first-install and nine transaction/rollback tests pass.
The sandbox run failed in temporary-directory setup before test execution;
normal Windows ACL execution passed. Do not generalize that setup error to an
installer defect or weaken filesystem authorization.

Evidence: shared src/roadcraft/transaction.py and tests/test_transaction_journal.py;
L275 reports/transaction_retry_patch_v4.json, transaction_journal_tests_v4.log,
recovery_v4_execution.json, install_v4_execution.json and preserved failed receipt
fe648c4731fd4f7ebeb4780110b804dd. A separate Roamer editor test correctly blocked
installation until it exited; it was not stopped. The local public-API transaction
adapter retains game/editor/import/package guards and every hash/lock check while
excluding idle Blender MCP helpers from the installed-package consumer scope.

**Audit correction:** test-012 expected intermediate .pct files in a retail PAK
that ships .pct.resource plus _N.pct_mip, and compared a native pre-export class
against renamed retail IDs. Those were checker faults, not missing lights or
changed drivetrain. Test-013 compares matching retail roles and actual emission
mip payloads; only prop_blueprints and sfx changed. Both UI mip payloads match v3
byte-for-byte, applying the Lada's asset-preservation finding without restoration.

## Copied native projects retain absolute bindings (Roamer scout, 2026-10-01)

**Build, current installed SDK:** a copied `.project` and editor/thumbnail
configuration still pointed at an earlier Roamer build. ModPakBuilder exited
zero, but its package contained the earlier ALWAYS differential classes and
rewrote those 22 class files in the scratch copy. The byte audit correctly failed
job `20260930T153039Z-4b8778fd62e4`; no package was installed from that job.
Selecting the scratch path in `--project` alone did not relocate the bindings.

The project adapter now initializes each copied environment, then checks its
documents-dir and ModsSourceLocal against the actual isolated scratch root.
The durable source is sealed independently. Audit the resulting PAK against
reviewed expected resource bytes, including byte-identical duplicate members,
instead of treating packager exit zero as proof of the selected source.
The corrected final package SHA-256 is
`8a340adc5a3a47c77e4629758a7d93b82acdeccaa3a27526852d2595d5723263`.
All 2498 unique resource bytes match reviewed expectations. Only the 22
gameplay/preview differential leaves differ from the native-tested lamp candidate.
Final_diff04 confirmed actual physical off/on selection, motion and four contacts;
all 2884 fixture files retained their pre-run seal and the editor exited zero.

Evidence: Roamer `campaign/scout_20260930_01/repacked/`, the failed job receipt,
`reports/scout_pending_recovery_review.json`, `tools/port_config.py` and
`tools/scout_rebuild.py`. The first failed lock and a later output-bookkeeping lock were each released
only after explicit user approval and exact stopped-owner/process/package/receipt
checks. Original lock bytes and failed receipts remain preserved. A shared recovery extension was rejected
by automatic approval review and was not applied; this finding grants no new
recovery or acceptance authority.

### Preserve successful package proof when workflow bookkeeping fails

**Build, Roamer 2026-10-01:** job 20260930T231942Z-76b9e702aa27 generated the
correct final package, exited zero and passed every resource-byte comparison.
Its recipe still declared the earlier output directory, and a resource-loop
variable shadowed the phase name used for the report filename. The workflow
therefore correctly retained a failed receipt and recovery lock for missing
declared outputs. Correct both the adapter's variable and the recipe contract;
preserve the original failed receipt instead of rewriting it as a passed job.
The successful misplaced report remains retained, and final test-009 passed.
The second lock release had separate explicit user approval and verification;
the rejected shared recovery-policy extension was never applied.

**Native recorder, Windows:** the first final_diff04 motion trial stopped on
Move-Item -Force reporting an existing destination during replacement of its
own report. Reusing the Lada/L275 `[IO.File]::Move(tmp,path,true)` writer plus
bounded retries for nested Windows 5/32/33 enabled motion_final02. Other errors
still fail; original reports and pre-change helpers are preserved. This changes
only task report persistence, not simulation payloads or permissions.
Evidence: tools/native_ssl_{physics_probe,input_override}.ps1, acceptance_ssl.ps1,
iterations/report_writers_before_final and native_final_review.json. Native
final_diff04 completed all ten scenario commands and exited zero; Wwise allocator
assertions appeared after Stop/exit and remain recorded, with sound bytes unchanged.



### An automation-ready echo can precede the actual Play scene

**Game diagnostic, Roamer 2026-10-01:** the short winch-fit trial emitted its
ready echo at 00:43:56 UTC, connected the replacement Play engine at 00:44:14,
and completed scene loading at 00:47:09. The first visual and smoke probes
timed out while loading; no driving inputs ran. Four minutes after a fixed
25-second delay left no useful measurement window. Preserve the raw failed
probes and do not mark their engine as tested. Wait for the replacement engine's
actual scene loading and a successful live truck response, then start controls;
allow a bounded sufficient hold for the planned measurements. A post-Play
scene-loading wait plus eight-minute hold is the scoped repeat configuration;
the echo alone remains insufficient. Evidence: Roamer
winch_fit_20261001_01/runtime/winchfit01/startup_review.json and raw logs.


### Freeze a local runtime when concurrent work changes pinned shared code

**Build, Roamer 2026-10-01:** job `20261001T012127Z-dd35d51f0ef9` passed preparation
but stopped before native packaging when concurrent work changed the pinned
maintained `src/roadcraft/bro_lint.py`. Its failed receipt is preserved and
`recoveryRequired` is false. Waiting for consumers does not freeze shared source.
This is a provenance conflict, not a reason to relax pin validation or close
another project's native session.

The project copied a bounded whitelist of runtime/library/schema files to
`D:\Program Files (x86)\Steam\steamapps\common\RoadCraft\port_roamer105\campaign\winch_fit_20261001_02\toolchain-runtime`, compared all 129 files with the maintained bytes,
and generated a fresh recipe using that snapshot's runtime and input paths.
The workflow dispatch and specialist utility imports both select the same copy.
The consumer gate still enumerates real SDK/game processes and waits for them
to close; no maintained runtime or recovery policy was modified. Snapshot
provenance is in `runtime_snapshot.json`, and the completed recipe is
`recipes/winch-owner-test-build-005.json`. Future fixes need a new verified
snapshot/recipe rather than edits to this build's pinned copy. Reusable learning
continues to be written to this maintained library.


### Verify unaccepted candidate sources and retain a verified receipt chain


**Installed diagnostic, Roamer 2026-10-01, preserved runtime scope:** the current
`source-check` CLI requires `accepted.authoringInventory` and `sourceRoot`;
`verify --project` checks candidate package/receipt pins but ignores the custom
candidate `sourceRoute`. Do not create an accepted entry to satisfy these APIs.
The Roamer adapter instead verifies the candidate inventory's registered hash
and every declared source byte, plus the audit and validation pins. It records
the unsupported CLI attempt separately from the successful candidate check.

The status command also initially marked the earlier INSTALLED receipt as
needing recovery after a verified successor installation, although no lock was
present and the live package matched the new candidate. The adapter checked
both terminal receipts, identical target paths, the successor's previous hash
against the earlier candidate, both exact backups and the preserved candidate
bytes. Only then did it retain the old receipt/backup pins in explicit machine
history and select the current receipt for active status. Original receipt bytes,
the registry's historical receipt pins, previous machine config and initial
verification report remain unchanged. This is a reviewed successful transaction
chain, not authority to hide failed, pending or unrecognized receipts. The final
project status has no recovery flag; acceptance remains empty.

The optional read-only rollback preflight was blocked by a later unrelated
IntegrationStudio PID 29880. Its raw error is preserved; no rollback or process
termination occurred. Exact backup/current bytes and receipt are verified.
Intentional rollback still requires closed native consumers. Evidence:
winch_fit_20261001_02/source_check_cli_attempt.json, source_check.json,
project_verify_initial.json, project_verify.json, previous_machine.json,
owner_ready_audit.json and rollback_preflight.log; tools/winch_owner_ready_audit.py.

## L275 front-end feedback and supplied texture update (2026-10-01)

**Build, bounded text-class update:** When the owner explicitly prohibits Mod Editor, do not invoke hidden IntegrationStudio for class generation. L275 retained its generated main/preview classes and added one terminal visual HINGE2 by cloning the existing typed HINGE2 constraint. Pin the complete original classes as source inputs, reparse the result, remove the added entry in a copy and require exact semantic equality to the original. Keep official command-line model import, texture conversion, package building, source/compiled vehicle checks and final export audits. The recipe's historical `generate` stage ID can call this reviewed patch adapter; it is **not native regeneration** and must not be reported as such. This does not establish a general compiler substitute or runtime proof.

Evidence: L275 tools/patch_compiled_ik.py, configure_workflow.py, revisions/front_end_v5/auto_*_before.cls and reports/front_end_v5/compiled_patch.json. Preserve failed/preflight and superseded recipes; an assets-only vehicle recipe was refused because the shared workflow requires ordered prepare/generate steps. The owner tests the resulting PAK in the retail game.


## Lamp-graph sync into an existing generated class (L275 v6, 2026-10-01)

**Build:** the native class generator copies a truck BRO's blueprint
(`blueprint.blueprints.<name>`) and its effect list (`effects.propSfx.list`)
verbatim into the main class (`properties.prop_blueprints.blueprints.<name>`,
`properties.sfx.list`): the L275 v5 class and BRO parse identical for
`L275ExteriorLights` and all six lamp effects. Under the owner's no-Mod-Editor
rule, a lamp-graph or lamp-effect change can therefore be made by regenerating
the BRO and copying those two sections into the class. Audit that the sections
equal the BRO, that every graph reference resolves, and that all other parsed
class data is unchanged. Run it inside the recipe's `generate` stage, so the
shared compiled-class check that follows sees the final class, and exclude the
synced sections from any earlier whole-class patch audit (L275's IK patch
compared the whole class to its v5 copy). This covers only sections the
generator copies; it is not a compiler substitute for derived data.

**Build, Blender 5.0.1:** joining a mesh into another merges UV maps by name.
The L275 tray-side objects (tray, toolbox doors, lamps) use `UVMap` and the cab
objects `map1`; joining a `map1` piece into a `UVMap` lamp object left two UV
channels with the piece's first channel empty. Rename the piece's channel first
and check one UV channel per exported mesh. A face attribute and a UV map with
the same name clash (Blender drops one); and reading `uv_layers[...].data` on a
freshly joined mesh crashed Blender, where `attributes[name].data.foreach_get
("vector", ...)` worked.

Evidence: L275 `tools/patch_compiled.py`, `patch_compiled_lamps.py`,
`patch_compiled_ik.py`, `configure_workflow.py`, `accessories.py`;
reports/accessories_v6/compiled_lamps.json; build-019 / test-020, final build-021 /
test-022 (audit_exterior: class changes since v5 confined to prop_blueprints and sfx).

## One material per texture in an exported object (L275 v8, 2026-10-01)

**Build (compiled object list) / Game (owner):** the native asset exporter makes one split per texture in an
object and gives each split a single material. Materials of one object that share a base texture collapse into one
split carrying one of them (in L275 the one with the most faces, not the first slot). The L275 tray's nine
`vehicle_body` materials compiled as four splits, harmless because they were identical; the cab glass object
carried the windows (`vehicle_glass_outer`) and opaque lamp parts (`vehicle_body`) on one atlas, so every L275 build
(v1-v7, checked in each candidate's compiled tpl) gave the glass object only the opaque lamp material and the owner saw "the glass isnt transparent".

| Rule | Grade |
|---|---|
| Read `<model>.tpl.asset/tpl/obj_list.json` after import: `engine_objects` rows list `split_info[].material` (the texture) and `material_info[].maya_name` (the material kept) per object | Build |
| Inside one object, materials that share a texture must share the preset and parameters; give glass, lit or other different presets their own object or their own texture | Build, Game (L275 glass) |
| Guard it at the model stage: per mesh object, group materials by texture set and refuse two presets on one texture (L275 `create_models.py`, `build/glass.json` `mixedPresetTextures`) | Build |
| Shared helper: `roadcraft.lamps.material_conflicts(rows)` (pure), or `roadcraft.blender_lamps.material_conflicts(preset_of)` inside Blender over the export meshes (the base-colour image is the split key) | Build (tests/test_lamps.py) |
| Splits of one texture also appear when an object exceeds the vertex limit (L275 body 50,000 + 49,999 faces): two splits with the same texture are not an error by themselves | Build |

Evidence: L275 v7 `obj_list.json` (`L275_Glass`: splits `[mod_l275_glass]`, material `[l275_lights]`) against
its Blender source (`l275_glass` + `l275_lights`); v8 build-026 (`jobs/20261001T120331Z-ec372b44ce82`) compiles `L275_Windows`
(`l275_glass`), `L275_Windows_Inner` (`l275_glass_inner`) and `L275_Glass` (`l275_lights`) separately; test-027
(`jobs/20261001T120747Z-9ecbab91e8a3`). The owner's in-game check of v8 is still open.

## Shared checkout changing during a pinned mod build (KGS25, 2026-10-02)

**Build:** KGS25's rebuild stopped after texture conversion because a pinned
shared `core.py` changed during that stage. The completed native baseline and
failed receipt were retained; no changed hash was written into the old recipe.
For a long build alongside other toolchain work, copy the required maintained
source/library into an isolated project-local snapshot, verify copied bytes
against the source, record its origin/file hashes, then create a fresh recipe.
Keep learning integration in the maintained checkout and preserve the exact
snapshot used for the mod's receipts. Do not revert another task's changes.
Evidence: KGS25 `native-build-002.json`, job `20261002T005439Z-0e956d3fbaef`,
local toolchain snapshot manifest. This is isolation of compiler inputs,
not a bypass of the pin checks or a runtime performance claim. A universal
snapshot command is deferred pending another project's reuse.

## Complete donor blueprint dependencies before native startup (KGS25, 2026-10-02)

**SDK / Game:** a donor BRO's Engine graph can be a partial override. KGS25's
generated graph retained emitter callbacks to absent SetSoundParameter nodes;
native editor prefab loading asserted at ssl_desc.cpp:2989. Copying the complete
retail compiled Engine/ForceFeedback graphs closed the links, but engine start
then asserted "Shaker hasn't been found. (EngineStart)". The accompanying native
shaker definitions must be supplied through propTruckShakerController too.
Check event dependencies against the complete compiled graph and controller
definitions, then test startup and engine start; packaging alone proves neither.

roadcraft.blueprint_links.graph_link_report is an opt-in check for a fully
resolved graph. It verifies native destination strings in arrays, excluding
resource URIs and scalar labels. It is wired into KGS25's recipe validation;
three focused tests cover missing callbacks/inputs, valid cycles and nesting.
It is not a blanket rejection of partial BROs with valid inherited nodes.

Evidence: KGS25 runtime/baseline01 crash archive, baseline02_graph_fixed crash
archive, baseline03_graph_shakers successful startup/engine start, donor retail
class and tools/prepare_mod.py. Output-directory watcher locks also caused eight
failed regeneration attempts. Preserve prior autogen directories outside the
resource layer while all native processes are closed before a fresh generation;
the original failed logs remain retained. Do not overwrite accepted identities.

## Patching text members of a built package (KGS25, 2026-10-02)

**Build, Game:** the truck class, wheel classes and model markup inside a package are text the
game reads when the vehicle loads; masses, centre-of-mass offsets and constraints are in the
markup, not the compiled `.tpl`. KGS-25 fix 2 changed only those members of the installed
candidate and drove as measured on the bench. `roadcraft.pak_patch.patch_text_members(source,
output, {member: function})` writes such a package: it patches every occurrence of a member
(the SDK's package of KGS-25 held its markup twice), copies every other member's compressed bytes,
headers and order unchanged, refuses patches that change nothing and verifies the result
(`compare_archives`). It reproduces the fix-2 package byte for byte; `tests/test_pak_patch.py`.

Patch the editor sources the same way in the same change: a project generator that still writes
the old values reverts the fix at its next build (KGS-25: Codex's `tools/prepare_mod.py` writes the
suspension collection, wheel slots and hull mass). Install through the transaction workflow with
the expected prior hash; keep the patched package's source hash in its report.

## A new vehicle without the editor (WALL-E, 2026-10-04)

**Build:** a complete new tracked mod was produced with no Mod Editor run: Blender 5.0 builds the five
`.blend` sources from a store OBJ (`tools/blender_build.py`); the SDK exporter, `tplexp` and
`create_tpl_resource` compile them (generateCollisionData false, so no CDT step); textures go through
TextureConverter / `pct_resource_gen`; and `mod_pak_builder` packs a project whose `mods_source/ssl` holds
the flattened classes. The classes are **not native regeneration**: the generated classes of a working
crawler (KGS-25) are parsed with `roadcraft.ps_format` (byte-exact round trip of its 141 KB class),
re-targeted from a rig report and extended with a retail scout's modules (winch, towing, scanners, action
mapper, track particles) and the lamp kit's graph. `.cls.resource` link lists are the template's plus the
donor modules' links. An editor-side BRO is written from the same data so `lint-bro` runs (0 errors).
The package audit compares every class, descriptor, markup, model and material member with the project
byte for byte (352 members). Whether the game loads it, and how it drives, are open until the owner's
drive. Evidence: WALL-E project `tools/build_text.py`, `tools/build_bro.py`, `tools/package.py`,
`reports/package.json`, `reports/lint.json`.


### Registering an added WALL-E visual wheel (2026-10-05)

**SDK/Game, WALL-E native editor fixture:** a wheel alias in the truck's wheelPool
and the aggregate library alone was insufficient. The native live truckWheels
table lacked the new descriptor and the truck did not finish loading. Registering
the class in the vehicle-specific truck_wheel_info.sso, with the corresponding
resource dependencies, restored loading. Check the full reference chain when
adding wheels; distinguish resource startup failures from measured physics.
WheelsLibrary.Get uses the live truckWheels table. The exact progression and
native lookup probe are in the [WALL-E case](../docs/case-studies/walle-stability.md).
This loaded diagnostic still failed driving; registration success is not handling
validation. A shared universal check is deferred until descriptor loading paths
outside this fixture are surveyed.


### Fail background Blender scripts explicitly

**Build, WALL-E articulated diagnostic (2026-10-05):** Blender5.0.1 returned0
when an assertion in a background Python script stopped before saving. Use
`--python-exit-code 1` (or another nonzero value), and verify expected outputs
before continuing. Existing shared Blender adapters already use this flag;
the isolated WALL-E authoring/export commands were corrected to match. Failed
preparation/export logs remain in `articulated_probe/build/logs/*_failed01.log`.
A process exit code alone is insufficient evidence of a produced asset.


### Emit fixed decimal numbers in PS/BRO output

**Game, native editor loading; Build (WALL-E, 2026-10-05):** a class containing
`maxDeltaAngVel = 2e-05` asserted in ssl_desc.cpp(280), reporting an unsupported
`psARRAY` value. Replacing only that token with `0.00002` reached native Play;
all other snapshotted gameplay resources were byte-identical and the documents
were semantically identical to the Python parser. Python round-trip success is
therefore insufficient to establish native numeric syntax. This is a loading
defect, not evidence of a motor/handling failure.

The shared `ps_format.dumps` writer now emits finite floats in fixed decimal
form using the shortest round-tripping representation, including nested arrays
and integral floats. Historical exponent syntax remains readable; NaN and
infinities are refused explicitly. This writer is already used by authoring and
resource-edit workflows. `tests/test_ps_numeric_serialization.py` covers the
observed small value, exponent extremes, signed zero, float types and invalid
values. Evidence: WALL-E `stability_20261005/reports/ps_decimal_native.json`,
failed `crawl_delta00002_straight_165627` and loaded
`crawl_delta00002_decimal_straight_170306`. Native driving success is separate.


### SSL source loading is separate from distributable script output

**SDK/Game, isolated native editor probe (WALL-E, 2026-10-05):** register a new
SSL resource before calling `LoadSSLModule`. SDK sources
`ssl/autotest/global_autotest.ssl` and `game_editor_sequence.ssl` do this; a new
marker class failed without registration and returned its expected string after
`LoadInitialResourceTag` with local source loading. This proves source execution,
not package portability. Restoring normal `UseBinarySsl=true` asserted on the
missing `_debug.sslbin`, even with `BinaryModulesGenEnabled=true`. No reusable
compiled output was found. Preserve the resource/config/source identities and
verify normal binary loading before promising a custom script mod. The
[WALL-E case](../docs/case-studies/walle-stability.md) contains exact probe/log
identities. Global SDK settings were unchanged; no heading controller shipped.


### Separate authoring inputs from outputs (Y61, 2026-10-06)

**Build:** Y61 prepare changed its pinned .blend input and correctly failed after its source checks passed (job 20261005T120412Z-cc18c1c28b1c). Preserve the receipt and lock, and verify external state before recovery. Author edits must read immutable snapshots and write a different path; final compilation reads frozen authoring sources without rewriting them. Manually written recipes in a recipes/ subfolder must use absolute output paths, or normalize them before pinning: relative outputs were checked under recipes/project instead of the project root, retaining a second failure despite successful authoring (20261005T172754Z-a34930cbc10e). The repaired bind-authoring operation uses distinct immutable input/output paths and absolute outputs. No shared recovery policy or acceptance authority follows from a successful isolated authoring operation.


### Y61 source fixture registration and blueprint imports (2026-10-06)

**SDK/Game, isolated native editor:** WheelsLibrary's live truckWheels is populated by AutogenLibrariesCreator scanning `res://autogen_dw/trucks/auto_<truck>/auto_<truck>_truck_wheel_info.sso.resource` and the corresponding truck_info descriptor. Editing an aggregate auto_wheels_library SSO or only placing a flat mod suffix file did not populate this source fixture. Canonical descriptor aliases referring to the exact production SSO bytes fixed fixture startup. Production packaged-mod entries retain their .mod suffix identities; do not ship fixture aliases or alter the stock global library. The editor fixture registration is a different path from packaged-mod registration.

The Y61 ShowHideGeomObjects graph also required explicit class-resource imports for `ssl/game/truck/blueprint_node_show_hide_geom_objects.sso.resource` and `ssl/ssl/lib/blueprint/blueprint_time_library.ssolib.resource`. A graph present in class text can still fail because its native class is not imported. Shipped readable script sources are in `default_non_retail_resources.pak`; descriptors and compiled modules have separate storage. Evidence: WatcherY61_Final `native_tests/sdk_sources/autogen_libraries_creator.ssc`, `register_editor_entities.py`, `reports/lamp_dependency_fix.json`, failed jobs 20261005T181821Z-1ccb9e3c2f35 and 20261005T182203Z-3ed28c4d3af5, successful canonical job 20261005T182937Z-f6f617d26e50. Existing source-fixture checks remain project-specific because mod manifests use a distinct registration path.
