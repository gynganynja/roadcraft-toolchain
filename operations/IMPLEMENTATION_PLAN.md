# RoadCraft workflow implementation plan

Status snapshot: 29 September 2026, Australia/Brisbane. This is a roadmap, not
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

At `4ae7e978e24b550470417d7f634e4b74e1fc202c`, private `main` and
[Windows CI #53](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36420864676)
passed 368 synthetic tests (one hosted skip) and all three Painter write-gate
tests. The Steam mirror and dedicated checkout each passed 368 tests with four
machine-specific skips. Two pinned Blender versions agreed on the read-only
blade geometry result; a further pinned no-save readback isolated the stored
normal outliers to eight triangles and located the largest change in Blender's
SDK axis-conversion path. A no-save normal projection matched all 6,486
accepted repaired blade normals without changing the five other measured
payload fields. The native pre-trigger guard, `c0de2027` no-write
contract, schema-2 candidate-only receipt-link scaffold, guarded color
readbacks and blade readbacks are offline evidence only. The accepted PAK
remains installed; no native capture or Blender export ran in this checkpoint.

The later no-swap accepted-project baseline adapter and separate partial
postflight are in `NATIVE_BASELINE_CAPTURE_20260928.md`. The accepted project
already contains all three validation scenes with the same bytes as the AAA
project, while its model sources differ. Both checkouts' no-write baseline
preflights verified 1,576 project source pins and the exact 382-file / 45-view
output roster; the dedicated checkout passed 371 local tests with four skips.
No baseline run had been executed at that checkpoint. The current native Read
response still lacks the complete measured context and engine-origin scene/PNG
proof required by step 5.

After that snapshot, a separate one-view accepted-project baseline diagnostic
started the native editor but failed before its screenshot because C: fell
below the inner runner's 1.5 GB free-space guard. The failure receipt and logs
are retained, the editor and lock are gone, and the installed PAK remains the
accepted hash. The baseline preflight floor was raised to 16 GB to prevent a
repeat at the same starting free space. A fresh elevated read-only check of
the exact 23,604-file/5.93-GiB generated-export cleanup passed with zero
deletions; applying it awaits specific approval. See
`NATIVE_BASELINE_CAPTURE_20260928.md`. The next runner records timestamped
free-space low-water evidence in its outer receipt. Its diagnostic sampler and
the combined 373-test suite passed locally with four machine-specific skips;
no editor was launched by this change.

| Area | State at this snapshot | Evidence and limit |
|---|---|---|
| Core CLI, jobs and transactions | Implemented | `src/roadcraft/cli.py`, `jobs.py`, `transaction.py`. CLI job/transaction operations default to dry-run; `--apply` executes. A failed phase after native launch retains its lock; `jobs-recover` requires exact lock/receipt/installed/registry/config pins and verified terminal external state before release. No live job lock was released. |
| Local inspect and synthetic tests | Current local and hosted suite passed | At `b5526301c7ed55f44a15d7924aebc3d247d137ff`, both checkouts passed 264 tests with 4 machine-specific skips, and [Windows CI #27](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36385847707) passed 264 tests with 1 skip plus all 3 Painter write-gate tests. CI #26's Windows short-path test assertion was corrected before that passing run. Both checkouts also passed all 15 native-fragment offline preflights without editor transport. After the process-gate, mesh-payload and request-source changes, both checkouts passed the combined 274-test suite with 4 machine-specific skips; [Windows CI #28](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36388084875) passed 274 tests with 1 skip plus all 3 Painter write-gate tests. Earlier inspect/test receipts remain under `jobs/20260927T233929Z-cab582e7350c/receipt.json` and `jobs/20260927T234050Z-66e61f71fca5/receipt.json`. The tangent/bind additions passed 282 local tests with 4 machine-specific skips in both checkouts; [Windows CI #30](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36390051983) passed 282 tests with 1 skip plus all 3 Painter write-gate tests. After the postflight, material and animation additions, both checkouts passed 292 tests with 4 machine-specific skips; [Windows CI #32](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36392664391) passed 292 tests with 1 skip plus all 3 Painter write-gate tests. The v2/v3 material and animation checkpoint passed 299 tests with 4 local skips in both checkouts; [Windows CI #34](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36394726017) passed 299 tests with 1 skip plus all 3 Painter write-gate tests. The v2/v3 tangent and bind checkpoint passed 306 tests with 4 local skips in both checkouts; [Windows CI #35](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36396444128) passed 306 tests with 1 skip plus all 3 Painter write-gate tests. At `63ab04b629f5846cbfa2f9f9672b050d696fef20`, both checkouts passed 316 tests with 4 machine-specific skips; [Windows CI #38](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36402968228) passed 316 tests with 1 skip and the Painter write-gate step. At `0f93a29d80ca94b621130387777af4216ff0bae3`, both checkouts passed 359 tests with four machine-specific skips; [Windows CI #49](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36416806888) passed 359 tests with one skip and all three Painter write-gate tests. Disclose the skips. |
| Read-only diagnostic checks | Current local and hosted diagnostics passed | The fixed native-helper pin, metadata-only preview audit and base mesh inventory were published at `fb20cde`. The v2/v3 and blade diagnostics at `b552630` passed 264 tests with 4 machine-specific skips in each checkout and [Windows CI #27](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36385847707); dedicated pinned Blender readbacks reproduced their digests with source and SDK unchanged. The later mesh-payload and request-source additions passed the combined 274-test suite with 4 machine-specific skips in both checkouts; [Windows CI #28](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36388084875) passed 274 tests with 1 skip plus all 3 Painter write-gate tests. |
| Project verification | Current source and project checks passed | A fresh read-only target `verify --project` passed all 5 registry pins, the source manifest and authoring inventory; `source-check` matched the accepted digest with no changes. The source manifest covers 2,817 files. The older source `d11_verify_20260928.json` is a four-pin snapshot and does not replace the newer result. |
| Accepted vs AAA candidate | Installed accepted; no recovery required; AAA unaccepted | Post-change target status reports installed SHA-256 `3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`, relation `accepted`, `recoveryRequired: false`, and no candidate-capture lock. AAA's historical capture still reports `FAIL_ROLLBACK_PENDING`, with `BASELINE_RESTORED` rollback evidence. Refresh status before native work. |
| Project-local MCP and workflow plugin | Dedicated CLI ready; this desktop task cannot yet call the project-local tools | User approved trust for the dedicated checkout. Codex CLI `mcp list` there sees `roadcraft`, `substance_painter`, `roadcraft_blender_scratch` enabled. Local marketplace is registered and `roadcraft-workflow` installed/enabled. Real stdio inventories: RoadCraft 11, Painter 79, Blender 2. The RoadCraft read-only adapter now rejects direct and nested UNC/device paths, reserved names, alternate data streams, mapped network drives and existing reparse components before resolution; this is a checked preflight, not a race-free filesystem sandbox. This task is rooted at the Steam project, where no `.codex/config.toml` exists and none of those tools appears in its callable inventory. `MCP_DESKTOP_SCOPE_20260928.md` records the separate desktop verification step. Tool scopes differ across servers. |
| Dedicated environment | Installed and verified | RoadCraft, Painter MCP and PyYAML are installed in `C:\RC\RoadCraftDev\toolchain\.venv`; project-local config is parsed and loaded by Codex CLI. The maintained source handoff was hash-checked. |
| New code Git repo/private remote | Private main operational with a passing published checkpoint | The `27ab9b01961b2b87deb51e61a89e8cc327d6b875` source-only checkpoint was verified on private `main` and passed [CI #35](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36396444128). The earlier `d504d7478b548249a506fd18c5c830640b4909eb` documentation checkpoint passed [CI #31](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36390317374). The `63ab04b629f5846cbfa2f9f9672b050d696fef20` no-save RGBA probe checkpoint is on private `main` and passed [CI #38](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36402968228). The `0f93a29d80ca94b621130387777af4216ff0bae3` blade-geometry diagnostic is on private `main`, remote HEAD matched, and [CI #49](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36416806888) passed. Verify remote identity and hosted checks for each later push. |
| Asset migration/Git LFS | Deferred by user choice; keep verified assets in place | `d11_asset_migration_preflight_20260928.json` verified 2,817 files / 3,477,364,242 bytes but failed its space gate. No copy occurred. Future migration requires a new decision and a fresh space check. |
| Native build/test/capture recipes | Preflight-only checks and 383-file partial-view contract passed; execution blocked | The `capture` recipe dry run and no-write `--plan` passed after pinning the reviewed runner. The plan declares 383 required files, 45 screenshots and 45 pre-screenshot partial links, plus source/package/scene/camera inputs. The runner emits `ReadPreCapture`, per-view action and transport pins, and a full output hash map; postflight checks these against the reviewed plan. Early-failure child cleanup now retains and authenticates a process handle before stopping a child. Synthetic tests pass; no native capture ran. All 15 allowlisted runtime-fragment variants passed offline preflight in each checkout, reporting no transport and no pair eligibility. The historical failed receipt remains failed. `jobs-recover` is synthetic-tested, not applied to a live lock. Complete global lighting, camera up, renderer state, loaded-scene bytes and screenshot-origin authentication remain absent, so no baseline/candidate pair is comparable. The new level-name reply is diagnostic only. `RUNTIME_LIGHTING_API_AUDIT_20260928.md` and `NATIVE_LOADED_SCENE_PROOF_AUDIT_20260928.md` pin reproducible editor/SDK metadata checks; no demonstrated engine-loaded scene digest or completed-PNG acknowledgement exists. The separate lighting fixture needs over 14 GiB; the AAA runner has 4 GB start / 1.5 GB loop guards. The historical nearnew editor exit cause remains unknown. |
| Windows CLI process gate | Self-blocking false positive removed; native execution still blocked | The console `roadcraft.exe` launcher was listed as an active RoadCraft process during its own `doctor` call. Process inspection now excludes only the closest verified CLI ancestor in the current process tree, keeps concurrent CLI launchers visible, and fails closed if that identity cannot be read. A real console-entrypoint regression passed; both checkout doctors reported no active authoring processes or warnings. It does not exempt the game/editor or clear other native capture gates. See `WINDOWS_CLI_PROCESS_GATE_20260928.md`. |
| Native helper integrity and preview callback | Fixed helper pin passed offline; image callback remains only a lead | The Python probe host now rejects a changed PowerShell helper before scratch creation or subprocess launch. Nine focused tests and all 15 fragment/variant offline preflights passed with no editor transport. A pinned metadata audit found a path/Boolean `ImageResult` callback in the separate thumbnail preview flow; it does not authenticate D11 `SaveScreenshot` PNG bytes or the loaded scene. See `NATIVE_PROBE_TRANSPORT.md` and `NATIVE_PREVIEW_IMAGE_ACK_AUDIT_20260928.md`. |
| Pre-screenshot Read request source | Source checked; postflight now requires exact sent content; no native request verified | The read-only verifier pins the generator chain, empty-action Read SSL and full generated helper. Its no-helper check passed, and all five retained historical helpers matched. The preflight-only recipe declares the source check. Postflight now pins and invokes the verifier for all 45 sent Read transports; a resealed mutating-script fixture fails. No current `pre_capture_VIEW.json` exists, so this is a verified future gate, not native provenance. See `NATIVE_PRECAPTURE_REQUEST_AUDIT_20260928.md`. |
| Native pre-trigger guard | Exact Read and camera checks pass offline; native proof remains blocked | The runner now verifies the generated helper and actual sent `ReadPreCapture` script, matching camera/resolution, timing and owned engine liveness before `CaptureCab`; the six-event view receipt is preserved. A fresh `c0de2027` no-write plan declares 383 files and pins the changed source. The dedicated capture recipe returned `dry_run` with three ready steps and no writes. No editor or screenshot was run, and loaded-scene bytes and screenshot origin are still unproved. See `NATIVE_PRETRIGGER_GUARD_20260928.md`. |
| Historical nearnew editor disconnect | Selected PID disappeared before fourth-view SSL; cause unresolved | The retained `SetCabRightDown` reply passed for PID 13444, then editor connectors logged a disconnect and the next helper PID precheck failed before `CaptureCabRightDown` created a transport or screenshot. A transport timeout and screenshot-source failure are excluded for this view. The old receipt has no engine exit code or crash record, so it cannot distinguish crash, normal exit, restart or external termination. See `NATIVE_NEARNEW_EXIT_CLASSIFICATION_20260928.md`; no native replay occurred. |
| Candidate native receipt link | Schema-2 candidate-only consistency check; pair-wide proof blocked | External receipt and plan SHA pins, candidate postflight, and exact 45 image/Read transport/PID/timing links are required. Host-declared run/view/source/camera-spec fields are separate from raw editor measurements; each observation pins its unique Read transport and exact raw reply bytes. The current pinned Read response is multiline text and lacks full lighting, scene-byte and PNG-origin measurements, so an authentic current run cannot pass. Baseline and engine-origin adapters remain absent; pair-wide native evidence, technical and release gates stay false. See `BASELINE_CANDIDATE_CAPTURE_PROTOCOL.md`. |
| AAA regression | Failed; acceptance pending | `d11_aaa_interior_regression_result.json`: technical gate false, releaseReady false, zero matched capture pairs and 45 required views failing. Existing capture contexts omit lighting/protocol; visual and campaign approvals are pending. |
| Blender no-edit USF bridge | Three roundtrips passed; native Blend export different and blocked | No-edit USF roundtrips remain byte-identical. The scratch MCP requires the accepted `project.json` inventory and rehashes its 68 declared authoring files. Native SDK exports differ from each repaired USF by 133 repaired-only, 76 native-only and 132 changed matched paths; material, rig and animation parity is missing. All native-Blend export gates remain `BLOCKED`. A four-run controlled scratch probe held inputs fixed: two `--threads 1` exports matched byte for byte, while two default-thread exports differed only in tangent arrays of three meshes. Subsequent scratch diagnostics default to one thread. A pinned reconstruction worklist names per-asset relocation candidates and unresolved differences. A guarded, opt-in in-memory wiper repair passed a no-write dry run; no repaired scratch export has run. The retained left push-arm diagnostic passed again with an exact worker pin and no save. A new pinned, no-save full-armature readback in Blender 5.0.1 and 5.2.0 found 378 shared paths with identical static matrices, but 6 source-only and 22 repaired-only paths; two of six same-name relocation candidates differ in matrix. Its scope excludes binds, animation, meshes, materials and export. See `D11_FULL_ARMATURE_READBACK_20260928.md`. |
| D11 push-arm branch reconstruction | Both sides statically matched in memory; export blocked | Pinned no-save Blender 5.0.1 and 5.2.0 runs inserted four missing push-arm base/tip bones and reparented both tilt bases without changing the accepted Blend or USF. Shared exact hierarchy paths rose from 378 to 386; source-only/repaired-only paths fell from 6/22 to 2/14. All 386 shared world matrices were within `2.27e-6`, including the eight affected branch paths. This establishes only static path/transform reproducibility; edit-bone length is arbitrary, and skin/bind, animation, source persistence, exported USF and native behavior remain unproved. See `D11_PUSH_BRANCH_IN_MEMORY_20260928.md`. |
| D11 base source mesh inventory | Read-only source gaps classified; export remains blocked | A pinned, no-save Blender 5.0.1/5.2.0 readback mapped all 126 base changed-mesh paths to unique historical Blend objects with one identical result digest. It found 135 repaired-only material-label occurrences absent from source slots; all 126 source-derived material-slot and skin-bone counts and the nine recorded geometry count gaps matched the retained native export. These are source facts and SDK count predictions, not fresh export, geometry-payload, bind or material-payload parity. See `D11_SOURCE_MESH_READBACK_20260928.md`. |
| D11 base mesh payload | Six source/native components match on 126 paths; export remains blocked | A pinned, no-save Blender 5.0.1/5.2.0 readback projected each historical mesh through `UsfMesh.b_read` in memory and compared canonical semantic digests with the retained native scratch USF. All 126 rows matched positions, normals, face indices, UVs, packed colors and skin indices/weights at float32 precision; an independent 5.2 rerun matched. Tangents, material payload, bone identities/inverse binds, animation, repaired-USF parity and native behavior remain unproved. See `D11_SOURCE_MESH_PAYLOAD_READBACK_20260928.md`. |
| D11 base tangent payload | 123/126 source/native rows exact at float32; export blocked | Pinned no-save Blender 5.0.1/5.2.0 readbacks agreed across all 126 mapped paths. Only `Blade_vis`, `Ripper_vis` and its LOD1 differ in tangent x/y/z by at most `1.7881393432617188e-7`; handedness signs match. This is an in-memory SDK projection against a retained native USF, not a new serialized export or repaired-USF parity. See `D11_SOURCE_TANGENT_PAYLOAD_READBACK_20260928.md`. |
| D11 base skin identity and inverse binds | Source/native 126/126; repaired gap remains | A pinned no-save SDK projection in both Blender versions matched ordered source/native skin-bone identities and inverse matrices on all 126 mapped meshes. Source/repaired ordered identities match 0/126; only 3/126 have shared inverse matrices within `1e-5`, with zero-overlap rows excluded. Numeric UIDs, animation, hierarchy repair and in-game behavior remain unproved. See `D11_SOURCE_BIND_IDENTITY_READBACK_20260928.md`. |
| D11 base material payload | Source/native 126/126; repaired gap remains | Pinned no-save Blender 5.0.1/5.2.0 SDK projections agreed across all 126 mapped meshes and matched retained native USF ordered material text/struct metadata, labels, texture-name references and face-to-slot indices. No source/repaired material row matched; 135 repaired-only label occurrences remain. Texture bytes, graph semantics and rendered behavior were not compared. See `D11_SOURCE_MATERIAL_PAYLOAD_READBACK_20260928.md`. |
| D11 base wiper animation payload | Source/repaired sampled transforms match; native omits the animated node | Pinned no-save Blender 5.0.1/5.2.0 readbacks evaluated two source actions over 36 inclusive frames. The repaired USF has one wiper node with 36 translation/rotation/scale samples and agreed within `1e-5`; the retained native USF has matching clip metadata but zero animated nodes. New native export, interpolation between frames and in-game behavior remain unproved. See `D11_ANIMATION_PAYLOAD_READBACK_20260928.md`. |
| D11 v2/v3 material payload | Source/native 126/126 for each variant; repaired gap remains | Each variant's own accepted Blend opened in pinned, no-save Blender 5.0.1/5.2.0 SDK readbacks. All 126 mapped rows per variant matched retained native ordered material text, metadata, labels, texture-name references and face material indices; none matched the corresponding repaired material rows. Texture bytes, graph behavior and rendered appearance remain unverified. See `D11_VARIANT_SOURCE_MATERIAL_PAYLOAD_READBACK_20260928.md`. |
| D11 v2/v3 wiper animation payload | Source/repaired samples match; native tracks absent | Separate pinned, no-save Blender 5.0.1/5.2.0 readbacks evaluated both variant Blend paths across 36 inclusive frames. Each repaired USF had one matching wiper node with 36 transform samples, while its retained native USF had clip metadata but zero animated nodes. Fresh exporter behavior, runtime playback and native appearance remain unverified. See `D11_VARIANT_ANIMATION_PAYLOAD_READBACK_20260928.md`. |
| D11 v2/v3 tangent arrays | Native 123/126 exact; repaired 0/117 comparable | Separate pinned, no-save Blender 5.0.1/5.2.0 SDK projections compared each variant's own retained native and accepted repaired USF. Native differences remain confined to `Blade_vis` and two `Ripper_vis` paths, at most `1.7881393432617188e-7`; repaired has nine array-shape gaps and no exact row among 117 comparable paths. This does not prove exporter or native-view parity. See `D11_VARIANT_TANGENT_PAYLOAD_READBACK_20260928.md`. |
| D11 v2/v3 skin identity and inverse binds | Source/native 126/126; repaired identity gap remains | Separate pinned, no-save Blender 5.0.1/5.2.0 SDK projections matched each variant's own retained native ordered skin-bone identities and inverse matrices on all 126 mapped meshes. Source/repaired ordered identities matched 0/126; only 3/126 shared inverse comparisons were within `1e-5`, excluding three zero-overlap rows. Numeric UID identity, full hierarchy, exporter and native-view parity remain unproved. See `D11_VARIANT_SOURCE_BIND_READBACK_20260928.md`. |
| D11 v2/v3 source mesh inventory | Variant-specific gaps classified; export remains blocked | The accepted v2/v3 Blend paths have the same pinned bytes as base. A separate wrapper verified each variant's asset digest, repaired USF and 126 worklist paths, then interpreted a no-save base source readback against that variant's own gaps. Blender 5.0.1/5.2.0 produced matching per-variant digests; all 135 repaired-only label occurrences were absent from source slots, and all 126 source-derived slot/bone counts plus 36 recorded count gaps matched each retained native export. This is read-only prediction, not variant export or parity. See `D11_VARIANT_SOURCE_MESH_READBACK_20260928.md`. |
| D11 v2/v3 mesh payload | Five native components stable 126/126; v2/5.2 packed colors intermittent | Separate no-save Blender 5.0.1/5.2.0 SDK projections compared six source components with each variant's retained native USF. Both 5.0 variants and v3/5.2 matched 126/126; v2/5.2 matched packed colors on 125/126 in one fresh process and 126/126 on an immediate same-code repeat. The mismatch changed 2,650 `Ripper_vis_LOD1` packed values; stable v2/5.2 color parity is unproved. Repaired-side ordered digests are diagnostic only, and native export stays blocked. See `D11_VARIANT_SOURCE_MESH_PAYLOAD_READBACK_20260928.md`. |
| D11 v2/5.2 RGBA discriminant | Three bounded no-save runs did not reproduce the intermittent mismatch | An in-memory wrapper measured call-time RGBA, stateless packing and SDK returns on `Ripper_vis_LOD1`. All three runs matched 126/126 native color rows and 59,238/59,238 target colors; SDK and stateless packs agreed, with 9,060 cache hits each. The prior 2,650-value mismatch remains unexplained, and native export stays blocked. See `D11_V2_RGBA_DISCRIMINANT_READBACK_20260928.md`. |
| D11 SDK RGBA cache lifetime | Stale cached color reproduced in Blender 5.0.1 and 5.2.0; historical v2 cause still unproved | A pinned, no-save diagnostic created only disposable in-memory meshes. In both versions the SDK returned cached white for raw gray after temporary-mesh reuse; clearing only the process-local cache made the same gray input pack correctly. Separate receipts and an execution manifest are retained. This establishes a reachable SDK mechanism, not that it caused the prior 2,650-value v2 mismatch or that a native export is safe. See `D11_RGBA_CACHE_LIFETIME_20260928.md`. |
| D11 v2 live RGBA discriminator | SDK packed output diverged while live raw input matched native | Two fresh, no-save Blender 5.2 processes used unwrapped SDK color functions. The second reproduced a `Ripper_vis_LOD1` mismatch: 1,200/59,238 SDK packed values differed, while stateless packing of live raw RGBA matched the retained native values 59,238/59,238. The first process matched completely. The SDK packing path is implicated, consistent with the separately reproduced cache-lifetime fault, but no call-time cache key was recorded and this is not the historical 2,650-value sequence. Native export remains blocked. See `D11_V2_RGBA_LIVE_DISCRIMINANT_20260928.md`. |
| D11 scratch RGBA cache guard | Opt-in implementation prepared; no export run | The scratch authoring wrapper now has a pinned v2/Blender 5.2-only option that passes an immutable RGBA snapshot to the original SDK packer for the export call, then restores the method and clears the process-local cache. The installed SDK and default scratch command are unchanged. The host and helper attest the exact guard module, input pins and post-run state; the native-Blend export gate remains closed. Synthetic tests cover collision prevention and failure cleanup. A guarded scratch export would be a new exact invocation requiring review. See `D11_RGBA_CACHE_GUARD_IMPLEMENTATION_20260928.md`. |
| D11 guarded v2 color readback | Two pinned no-save runs matched native colors; export still blocked | In two fresh Blender 5.2 processes, one immutable-key guard context spanned all 126 SDK source projections. Each run matched the retained native packed colors on 126/126 rows and all 59,238 `Ripper_vis_LOD1` values, with 194,121 guarded pack calls; both restored the SDK packer and hook and retained input hashes. Distinct UTC intervals are in the manifest; the compact receipts have identical bytes because they omit invocation time. This verifies in-memory color projection only, not USF writer, repaired parity or native behavior. See `D11_V2_RGBA_GUARDED_READBACK_20260928.md`. |
| D11 blade collision relocation | Static hierarchy/transform target identified; export remains blocked | A pinned, no-save readback covered all 60 `cdt_blade_*` leaves under `BoneBlade_cdt`. Both Blender versions returned the same 60-row digest: source, retained native USF and repaired USF world matrices agree within `1e-5`, while all 60 native/repaired USF local matrices differ beneath the inserted `BoneBladeRoll_cdt` parent. Mesh-count maps and evaluated source/native face counts match. The differing paths are not marked equivalent. That static diagnostic did not compare payloads; binds, animation and native behavior remain untested. See `D11_BLADE_COLLISION_RELOCATION_READBACK_20260928.md`. |
| D11 blade-roll reconstruction | Pinned two-version no-save diagnostic and combined scratch preparation passed; export unexecuted | A no-save edit inserted `BoneBladeRoll_cdt`, reparented `BoneBlade_cdt`, then restored the 60 blade mesh world matrices in memory. The standalone command passed in Blender 5.0.1 and 5.2.0. A combined push/roll/normal no-save check then matched 388/400 repaired structural paths and installed all 60 accepted normal attributes with the original digest. The authoring wrapper's four-repair dry run passed without writing outputs; its exact scratch export remains unexecuted. This does not prove export, bind, animation or collision. See `D11_BLADE_ROLL_IN_MEMORY_20260929.md` and `D11_COMBINED_BLADE_REPAIR_PREP_20260929.md`. |
| D11 access-ladder reconstruction | Maintained two-version no-save diagnostic passed; scratch export unexecuted | A ladder shape probe found one unconstrained source bone with no child bones or bone-parented objects, versus four repaired meshless nodes. Three new edit bones and a relocated ladder matched all four repaired targets within `3.3527612686157227e-7` in Blender 5.0.1 and 5.2.0. After the existing push and blade-roll repairs, both versions matched 392/400 structural paths, with no source-only paths. Export, bind, animation and native behavior are unproved. See `D11_LADDER_IN_MEMORY_20260929.md`. |
| D11 blade mesh payload | Source/native six fields match 60/60; repaired exact positions/normals differ | Two pinned, no-save Blender versions produced the same 60-row digest. Repaired exact positions matched only 2/60 (`cdt_blade_49` and `50`) and exact normals 0/60; face indices, UVs, packed colors and skin indices/weights matched 60/60. The separate numeric diagnostic below bounds the position drift and isolates real stored-normal outliers. These ordered fields do not prove material/bone identity, tangents, animation or collision behavior. No export or accepted-asset change occurred; see `D11_BLADE_PAYLOAD_READBACK_20260928.md`. |
| D11 blade geometry and normals | Positions within tolerance; stored-normal gap remains | Two pinned, no-export Blender processes parsed 60 retained native/repaired USF leaves and 6,486 triangle corners. World matrices were identical and maximum local/world position difference was `4.815e-7` (all 60 rows within `1e-5`), explaining the 58 exact position-digest mismatches as low-bit drift. Twenty-four stored normals across five leaves differed by over 0.1°, maximum 13.24°; a 0.229 pairwise-dot change rules out a single rigid rotation for the worst leaf. Collision behavior and the cause of the normal change remain unproved. See `D11_BLADE_GEOMETRY_READBACK_20260928.md`. |
| D11 blade normal origin | Eight flat triangles isolated; repair origin unproved | A pinned, no-save SDK projection exactly reproduced all 24 native outlier corners. All eight source polygons are flat, have no custom-normal or `saber_normals` attribute, and have `has_custom_normals=false`. Blender 5.0.1/5.2.0 stage probes on three witnesses found the SDK axis transform changes corner normals while geometric face normals remain aligned. The accepted repaired normals mostly align with face normals, but their creation stage is unknown; no blanket recalculation or export is justified. See `D11_BLADE_NORMAL_ORIGIN_READBACK_20260928.md` and its pinned JSON receipt. |
| D11 blade normal projection | In-memory normal arrays matched; authored/export parity blocked | Pinned Blender 5.0.1/5.2.0 no-save processes temporarily assigned repaired USF corner normals to `saber_normals` on all 60 source blade meshes. Both SDK projections matched all 6,486 repaired normals exactly and retained source/native positions, face material/edge indices, UVs, packed colors and skin indices/weights on all rows. The source Blend and both USFs stayed unchanged. Persistence after a Blend save, fresh USF export, collision behavior and other asset parity remain unproved; the native-Blend export gate stays blocked. See `D11_BLADE_NORMAL_PROJECTION_READBACK_20260928.md` and its pinned two-run manifest. |
| D11 blade-normal scratch repair | Opt-in live-scene repair prepared; export unexecuted | A pinned installer left all 60 repaired normal attributes on a disposable in-memory scene in Blender 5.0.1 and 5.2.0. The authoring helper now checks all 60 candidate/repaired normal arrays after any separately authorized scratch export. A combined no-export push-arm/normal/wiper sequence and no-write wrapper dry run passed; no Blend was saved or USF exported. The native-Blend gate stays blocked. See `D11_BLADE_NORMAL_SCRATCH_REPAIR_PREP_20260929.md`. |
| Painter integration | Capabilities verified; scratch project deferred; write gate added | Real stdio probe listed 79 tools, connected to Painter 12.1.5/API 0.3.5 and called `get_capabilities` successfully while no project was open. Baking presets, auto-rebake control and skew-painting control are unavailable. The server now leaves 34 inspection/planning tools enabled and denies 45 authoring/output tools unless its local process has `SP_MCP_ALLOW_PROJECT_WRITES=1`; synthetic FastMCP dispatch tests cover all 45. The user intentionally ended the Painter session to avoid interference and chose to leave it closed; no `.spp` was created and no accepted asset changed. |
| Storage | First exact batch complete; expansion dry run passed but deletion unapproved | `STORAGE_REVIEW.md`: 159 template copies removed, 6.30 GiB freed, retained originals verified. The separate 23,604-file / 5.93 GiB expansion remains untouched. Its 33 MB raw manifest is local and a verified 1.6 MB gzip copy is versioned. A full sandboxed dry run verified every candidate and counterpart but reported `applyReady: false` because CIM process inspection was denied. A distinct elevated full dry run reported `applyReady: true` with zero active processes at its inspection time, 21 retained packages, 166 retained source files and zero deletions. Any future apply needs specific authorization and a fresh pinned preflight. Git temporary pack remains separate. |

## 1. Finish checkout handoff and retain verified local tools

**Owner:** maintainer. **Dependencies:** final source edits. User trust,
dedicated environment installation and local integration registration are done.

1. Sync only maintained code/docs/config examples into the dedicated checkout;
   preserve its `.venv`, local paths, jobs and receipts. Record the compared
   file list and hashes. Verify imports resolve from the dedicated checkout,
   not the earlier editable source installation.
2. Retain the completed target evidence: 249 tests with 4 skips, all 5 project
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

The Windows `roadcraft.exe` console launcher had appeared in its own
name-based authoring-process snapshot, which could reject a native preflight
even on an idle host. The inspector now suppresses only a process whose
queried image is the same file as the current CLI launcher; image-query
failure retains the process as a blocker. The real console-entrypoint test
and `doctor --json` in both checkouts confirmed no self-reporting. This
repair does not authorize a native run or weaken detection of the separate
RoadCraft game executable. See `WINDOWS_CLI_PROCESS_GATE_20260928.md`.

`capture_pair_protocol.py` now provides a read-only context validator for a
future baseline/candidate pair. It requires pinned raw editor observations
immediately before each image, equal actual camera/lighting/scene context and
measured image dimensions. Exact D11 3×15 coverage is required for
`pairComparable=true`. The validator also requires distinct run IDs and
one actual screenshot and observation file per view across the pair, and
rejects overlapping view intervals within a run. Identical image bytes in
separate files remain valid for A/A controls. Its output always keeps native
postflight, technical and release gates false. An optional candidate-only link
now requires external receipt and plan hashes, passing candidate postflight,
and exact 45-view image, Read-transport, PID and timing links. It is
preparatory: the pinned Read reply is multiline `D11T_SYSTEMS_OK` text while
the pair observation schema requires JSON, and no baseline adapter or
engine-origin proof exists. Pair-wide native evidence stays false. The current
runner does not emit the full observation schema, so no historical capture can
pass by inheriting proposed lighting/protocol labels. See
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
The Python host now pins the exact PowerShell helper hash and rejects drift
before scratch creation or a subprocess launch; focused regression tests passed.
All 15 allowlisted fragment/variant combinations passed offline preflight in
both the Steam mirror and dedicated checkout, with identical module, helper,
config and interpreter pins. Each reported `transportSent: false` and
`pairProtocolEligible: false`; no transport request was sent. A future
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

`NATIVE_LOADED_SCENE_PROOF_AUDIT_20260928.md` records reproducible,
metadata-only IL and signature checks for the pinned editor assemblies. They
show scene-name notifications and requests but no demonstrated engine-loaded
byte digest or completed-PNG acknowledgement. It separates a level
or actor label, a mounted on-disk source tree, and a consistent screenshot
receipt from actual runtime scene and producer authentication. The two proof
flags remain false until an engine-origin check tied to the capture interval
has been tested in a disposable editor and reviewed. The audit also records
why a future Windows FileIO trace would corroborate process/path/timing but
could not prove loaded bytes or rendered-image origin by itself. A future
engine-origin proof must bind the scene-buffer digest and completed PNG bytes
to the owned process, a nonce and the capture interval.

`NATIVE_PREVIEW_IMAGE_ACK_AUDIT_20260928.md` inspects the separate managed
thumbnail preview flow using pinned metadata only. Its `ImageResult` event
delivers a path and Boolean before managed code reads and deletes a temporary
PNG. The conditional process-ID check, `ThumbnailsScene` and
`TakeScreenshot` command do not establish that this callback applies to the
D11 SSL `SaveScreenshot` request. It reports no engine PNG digest or loaded
scene bytes, so both proof flags remain false.

`NATIVE_PARTIAL_VIEW_LINKAGE.md` defines a fail-closed handoff for
`ReadPreCapture` immediately before each screenshot request. The maintained
runner now emits one partial link per view, the 383-file contract declares its
files, and read-only postflight rechecks the exact action/transport/output
chain against an externally pinned plan. Synthetic tests pass. The link still
does not authenticate native origin, prove a loaded scene, or observe complete
lighting. The failed historical run cannot be upgraded.

`native_precapture_request.py` separately pins the current request-generator
sources and the exact empty-action `ReadPreCapture` SSL bytes. Its offline
check passed in both checkouts, and all five retained historical generated
helpers matched the reviewed normalized script. The preflight-only capture
recipe now declares this no-helper check before its existing full-capture
no-swap step; its updated three-step dry run passed without executing a
command. No guarded-runner `pre_capture_VIEW.json` is available, so no actual
sent request was verified. Postflight now pins the verifier source and
requires its helper/transport audit for all 45 Read records. The synthetic
complete-chain test passes; a consistently resealed transport containing a
setter fails the new content gate. The runner does not check during capture,
and this does not prove engine origin, loaded bytes or PNG acknowledgement.
See `NATIVE_PRECAPTURE_REQUEST_AUDIT_20260928.md`.

The read-only `python -m roadcraft.native_capture_postflight` check now
requires an externally pinned no-write plan, exact run ID,
candidate/baseline/installed hashes, successful rollback, all 383 planned
outputs, the three nested receipts' 45 partial image/probe links, and the
exact sent SSL in all 45 pre-capture Read transports. It rejected
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

The pinned, no-save `blender_armature_parity.py` readback then compared every
source pose-bone path and all meshless repaired USF structural paths at scene
frame 1. Blender 5.0.1 and 5.2.0 produced the same all-matrix static digest:
384 source bones, 400 repaired nodes, 378 exact shared paths with zero matrix
error, and 28 path-difference rows (6 source-only, 22 repaired-only). Of six
unique-leaf relocation candidates, the ladder and blade world matrices differ
by up to `0.8289909362792969` and `0.8908867835998535`; four tilt-node
matrices match. The diagnostic hash-pins its worker and source before/after,
then emits a bounded complete diff. It did not save or export, and the two
Blender versions' identical static readback does not establish exporter,
skin/bind, animation, mesh, material or native-view parity. Exact paths and
the command are in `D11_FULL_ARMATURE_READBACK_20260928.md`.

A follow-on pinned, no-save Blender 5.0.1/5.2.0 experiment inserted both
push-arm bases and tips in memory and reparented the existing tilt branches.
It resolved eight repaired structural paths and reduced the full static
hierarchy gap from 6/22 to 2/14 source-only/repaired-only paths, with all 386
shared matrices within `2.27e-6`. This is a reproducible repair direction,
not a saved authoring source or exported parity result. See
`D11_PUSH_BRANCH_IN_MEMORY_20260928.md`.

An opt-in `--push-branch-scratch-repair` is prepared in the scratch-only
authoring diagnostic. A source-, SDK- and module-pinned no-write dry run passed
on the accepted base asset. The helper's SDK-import/scene-open sequence also
passed no-export probes in Blender 5.0.1 and 5.2.0. The exact file-writing
scratch export remains
unexecuted pending its separate authorization; it cannot promote a native
Blend to build input. See `D11_PUSH_BRANCH_SCRATCH_REPAIR_PREP_20260929.md`.

The separate pinned `blender_mesh_inventory.py` readback inspected the base
historical Blend without saving or exporting. Both Blender 5.0.1 and 5.2.0
reconstructed all 126 changed-mesh worklist paths and produced the same
126-row digest. Their evaluated meshes had the same vertex and triangle
counts as the raw meshes for those objects; every raw vertex had a group and
all first armature modifiers targeted `D11T_Rig.005`. Source material-slot
and skin-bone counts matched the retained native export on all 126 rows;
135 repaired-only material-label occurrences were absent from the mapped
source material slots. The nine documented face/vertex/normal/skin-entry
count gaps also matched the retained native export when projected through
the pinned SDK rules. These observations localize count and naming gaps to
the historical source, but they do not compare geometry payloads, material
payloads, weights or inverse binds. No fresh SDK export was run. See
`D11_SOURCE_MESH_READBACK_20260928.md`; the native-Blend gate stays blocked.

The v2/v3 accepted Blend files have the same pinned bytes as base, but their
repaired USFs and material labels differ. `blender_mesh_variant_inventory.py`
keeps the base no-save worker unchanged, verifies each variant's separate
accepted source and 126-path worklist, then reinterprets the returned source
facts against that variant's repaired/native gaps. Four runs (two Blender
versions × two variants) produced stable per-variant digests: 126 mapped
paths each, 135 repaired-only label occurrences absent from source slots,
and source-derived slot/bone and count-gap values matching each retained
native export. It does not open the variant Blend path separately or export
a USF; the byte identity and independent before/after pins support reuse of
the source readback. See `D11_VARIANT_SOURCE_MESH_READBACK_20260928.md`.

The separate pinned `blender_mesh_payload.py` readback projected the same
126 base historical meshes through the reviewed SDK's `UsfMesh.b_read` in
memory and compared their canonical semantic digests with the retained native
scratch USF. Both Blender versions, plus an independent 5.2 rerun, matched
all 126 paths for positions, normals, face material/edge indices, UVs, packed
colors and skin indices/weights at float32 precision. This confirms those
source-to-native payload components, not literal serialized USF bytes or
source-to-repaired parity. Tangents, material payload, bone identities,
inverse binds and native behavior remain untested. No save or export ran.
See `D11_SOURCE_MESH_PAYLOAD_READBACK_20260928.md`.

The v2/v3 no-save mesh-payload diagnostic opened each accepted variant Blend
path and compared the same six SDK-projected components against its own
retained native USF. Both variants matched all 126 rows under Blender 5.0.1;
v3 also matched in two pinned 5.2 runs. V2 under 5.2 matched packed colors on
125/126 rows in one process and 126/126 on an immediate fresh-process repeat
with identical host, worker, Blender, source and SDK hashes. The mismatch
changed 2,650 `Ripper_vis_LOD1` packed values. The SDK's color-cache size
varied, but causality is unproved. Stable v2/5.2 packed-color parity and
fresh native export remain unverified. Repaired ordered digests describe
differences, not semantic equivalence across material slots and skin-bone
identities. See `D11_VARIANT_SOURCE_MESH_PAYLOAD_READBACK_20260928.md`.

A separate unwrapped v2/Blender 5.2 no-save discriminator reproduced an SDK
packed-color divergence in the second of two fresh processes. The 1,200
different `Ripper_vis_LOD1` values contrasted with a 59,238/59,238 match
between statelessly packed live RGBA and retained native colors. This narrows
that run's fault to the SDK packing path, with stale cache reuse consistent
with the independent cache-lifetime reproduction. No call-time cache key was
recorded; the prior 2,650-value run remains distinct. See
`D11_V2_RGBA_LIVE_DISCRIMINANT_20260928.md`.

The pinned, no-save `blender_material_payload.py` readback projected all 126
mapped base meshes through the SDK material builder in memory. Blender 5.0.1
and 5.2.0 produced the same 126-row digest. Ordered source/native full
material text, struct metadata, labels, nonempty texture-name references and
face material indices matched on every row; source/repaired full material rows
matched on none, with 135 repaired-only label occurrences. This narrows the
material gap to the historical source or later repair, but image bytes,
shader-graph semantics, the 84 other meshes and native rendering remain
unverified. It does not enable `native-blend` export. See
`D11_SOURCE_MATERIAL_PAYLOAD_READBACK_20260928.md`.

The separate pinned, no-save `blender_animation_payload.py` readback evaluated
the historical Blend's two wiper actions over their 36 inclusive frames and
decoded the retained repaired/native USF animation records. Both reviewed
Blender versions returned one identical record digest. The source transforms
matched the repaired USF's one wiper node and 36 samples per transform within
`1e-5`; the native USF kept clip metadata but had zero animated nodes. This
identifies the missing native wiper track without proving a fresh export will
retain it: the SDK's current baking loop is end-exclusive. Subframe motion,
compiled playback and native rendering remain unverified. The `usf-repair`
route and blocked `native-blend` gate remain. See
`D11_ANIMATION_PAYLOAD_READBACK_20260928.md`.

The v2/v3 material diagnostic opened each accepted variant Blend path and
projected its 126 mapped meshes through the pinned SDK in memory. Both Blender
versions matched each variant's retained native ordered material text,
metadata, labels, texture-name references and face material indices on all
126 rows, while no source/repaired full material row matched. Variant native
USFs use their variant root names; repaired USFs retain `cat_d11t`. The
diagnostic handles this distinction without assuming that identical Blend
hashes make the variant USF payloads interchangeable. Texture bytes, shader
graph behavior and rendering remain unverified. See
`D11_VARIANT_SOURCE_MATERIAL_PAYLOAD_READBACK_20260928.md`.

The v2/v3 animation diagnostic independently opened those accepted Blend
paths and evaluated the two wiper actions over the same 36 inclusive frames.
Each variant's source samples matched its repaired USF within `1e-5`; each
native variant USF retained clip metadata but no animated node. Blender 5.0.1
and 5.2.0 returned the same per-variant record digests. The current SDK's
end-exclusive bake, a fresh export, runtime playback and native appearance
remain unresolved. The `usf-repair` route and blocked `native-blend` gate
remain. See `D11_VARIANT_ANIMATION_PAYLOAD_READBACK_20260928.md`.

The v2/v3 tangent diagnostic separately opened both accepted Blend paths and
compared SDK-projected tangent arrays with each variant's own retained native
and accepted repaired USF. Both Blender versions agreed: 123/126 native rows
were exact; the same three `Blade_vis`/`Ripper_vis` paths differed by at most
`1.7881393432617188e-7`. Repaired comparisons had nine shape gaps and no
exact row among 117 comparable paths. Shape gaps are excluded from component
counts. The cause of native float32 drift, repaired mesh differences, exporter
behavior and game appearance remain unproved. See
`D11_VARIANT_TANGENT_PAYLOAD_READBACK_20260928.md`.

The v2/v3 bind diagnostic separately opened both accepted Blend paths and
matched each variant's retained native ordered skin-bone identities and
inverse matrices on all 126 mapped meshes. No source/repaired ordered
identity row matched; only 3/126 shared inverse comparisons were within
`1e-5`. Three zero-overlap blade rows are explicitly excluded from matrix
matches. Both Blender versions agreed. Numeric UIDs, complete hierarchy,
exporter and native behavior remain unproved. See
`D11_VARIANT_SOURCE_BIND_READBACK_20260928.md`.

The base blade-collision readback then examined all 60 same-leaf relocation
candidates under `BoneBlade_cdt`. Two Blender versions produced the same
60-row result digest. Their source, native scratch USF and repaired USF world
matrices matched within `1e-5`, while each native/repaired USF local matrix
differed after the repaired hierarchy inserted `BoneBladeRoll_cdt`. Retained
USF mesh-count maps and source/native evaluated face counts matched. This
narrows the hierarchy and transform work; it does not establish node,
geometry, bind, animation or game-view equivalence. No Blend save or USF
export ran. See `D11_BLADE_COLLISION_RELOCATION_READBACK_20260928.md`.

The subsequent source/native blade-payload readback matched six ordered fields
on all 60 relocated leaves. Native/repaired exact positions differed on 58
leaves and exact normals on all 60, while face indices, UVs, packed colors and
skin indices/weights matched. A separate pinned, read-only native/repaired USF
geometry comparison showed identical stored world matrices and maximum
local/world position drift of `4.815e-7` over 6,486 corners. Every leaf was
within the declared `1e-5` positional tolerance. Stored normals still differ:
24 corners on five leaves exceed 0.1°, and the worst reaches 13.24°; their
pairwise-dot invariant excludes a single rigid rotation as a full explanation.
This narrows positional work but does not establish normal provenance,
collision/physics behavior, binds, materials or native-view parity. The
subsequent no-save normal-origin and projection readbacks traced the outliers
and prepared an opt-in live-scene normal repair; a native-Blend export has not
run. See
`D11_BLADE_PAYLOAD_READBACK_20260928.md` and
`D11_BLADE_GEOMETRY_READBACK_20260928.md`.

A maintained, pinned no-save ladder diagnostic now reconstructs the repaired
access-ladder hierarchy in memory. Blender 5.0.1 and 5.2.0 matched all four
ladder paths within `3.353e-7`. After the maintained push and blade-roll
workers, the ladder worker left 392/400 repaired structural paths shared, no
source-only paths, and eight repaired-only paths. This is static evidence; the
scratch export command remains separately reviewed and unexecuted, and the
`native-blend` gate remains blocked. See `D11_LADDER_IN_MEMORY_20260929.md`.

The eight residual pose-bone paths include an existing source `sfx` Empty,
which the retained native USF exports at the repaired path and world matrix.
The other seven light and dash nodes are absent from both source Blend and
native USF. A two-version no-save experiment added those seven bones after
push, roll and ladder; counting the existing Empty, all 400 repaired
structural paths then matched within `2.269e-6`, with no mesh world drift.
The maintained, pinned no-save diagnostic reproduces the two-version result;
a separately authorized scratch export is still needed before native-Blend
parity can advance. See
`D11_RESIDUAL_STRUCTURAL_NODES_20260929.md`.

The accepted base, v2 and v3 repaired USFs have identical 400-path static
structural targets: world matrices, child rosters and animation-presence flags
match exactly in pinned Blender 5.0.1 and 5.2.0 read-only parses. Their Blend
references also have identical bytes. This narrows the variant hierarchy work
and is now rerunnable through a maintained, source-pinned no-save diagnostic,
but does not test variant-specific edits, export, mesh or material parity. See
`D11_VARIANT_STRUCTURAL_TARGETS_20260929.md`.

Separate pinned no-save experiments then opened the v2 and v3 historical Blend
paths, ran the existing four-stage structural reconstruction in memory, and
compared each scene with its own repaired USF. Both Blender 5.0.1 and 5.2.0
matched 400/400 paths with no missing paths or changed matrices and a maximum
matrix element error of `2.269e-6`. The edits still use the base USF as their
target; each variant USF is independently parsed for the final comparison.
This remains static evidence without a USF export or variant payload parity.
The variant-specific no-save check is now available as a maintained, pinned
command in both source trees. See
`D11_VARIANT_IN_MEMORY_RECONSTRUCTION_20260929.md`.

A pinned Blender 5.2.0 no-save composition check has now applied the base
push-arm, blade-roll, ladder, seven-bone and blade-normal repairs together,
then installed the wiper hook. The 400 repaired structural paths stayed
unchanged after the hook; 60 blade normal attributes were installed on the
reviewed mesh data. The hook did not bake animation because no export ran.
This narrows the combined-scene integration risk but does not change the
pending scratch export command or the blocked native-Blend gate. See
`D11_FULL_IN_MEMORY_REPAIR_COMPOSITION_20260929.md`.

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

1. Private `main`, remote commit comparison, and Windows CI run #53 at
   `4ae7e97` are complete. Keep later changes versioned and recheck CI after
   each push.
2. Use the registered, smoke-tested local integrations through their dedicated
   checkout, then confirm desktop tool visibility in a task rooted there. The
   current Steam-root task has no project-local MCP entries. Painter capability
   probing passed, but the app closed before disposable-project creation.
   Leave it closed until the user chooses to reopen Painter, then resume the prepared scratch check
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
