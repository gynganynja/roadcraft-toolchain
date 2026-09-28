# D11 AAA native capture output contract (2026-09-28)

The guarded legacy runner now accepts an explicit eight-character lowercase
hexadecimal `--run-id`. `--execute` requires both that ID and the SHA-256 from
an earlier `--plan` result. The default invocation without `--execute` keeps
its original read-only preflight behavior. `--plan` runs the same source,
package, mount, disk, and process checks, then prints a deterministic JSON
contract without creating `native/`, `runs/`, a lock, a backup, or a screenshot.
The contract-hash flag is rejected outside `--execute`.

The [current no-write plan](d11_aaa_native_capture_plan_c0de2026.json) uses run ID
`c0de2026` and contract SHA-256
`8cd248a4ee027f8de22113dc653b18e7a08b04a288dbbd3ee2dd9619e2be5d33`.
The earlier [a1b2c3d4 plan](d11_aaa_native_capture_plan_a1b2c3d4.json)
is retained as historical evidence; its runner hash and contract hash no longer
authorize `--execute` after the exit-telemetry patch.
It declares 248 required evidence files, including the outer receipt, baseline
backup, three nested reports, 45 camera and 45 capture probe records with
transport logs, and 45 copied PNGs. Six hidden-geometry probe files are
optional because the editor API can reject that supplemental query. The
contract separately names three variant run directories, 45 engine screenshot
sources, ten transient lock/stage/temporary-receipt or directory paths, and the
reserved recovery-receipt name. It also names the per-variant editor-data,
temporary, and optional local-profile directory roots; their nested editor
byproducts are not pinned evidence. It pins the runner, candidate, baseline, prototype route,
and selected audited package receipt path, SHA-256, and status, plus a
canonical SHA-256 over 1,644 project-source pins. Each variant names the
validation scene and its SHA-256 and the 15 camera offsets. Planned pixel
resolution and runtime lighting are explicitly `unknown`; successful runs
record the actual PNG dimensions per image. Nothing is inferred for historical
captures.

The runner refuses any pre-existing outer receipt, backup, recovery receipt,
legacy lock, stage or restore file, temporary receipt, variant run directory,
or planned engine screenshot
source. It reserves the outer receipt exclusively and copies package artifacts
with exclusive file creation. A drifted contract hash stops before directories
or package writes. Incomplete stage and restore files stay in place for
inspection, and an unswapped run must still verify the accepted baseline
before clearing its lock. A run receipt carries the contract hash, and each nested
report carries the scene/camera context plus action start/end UTC timestamps,
editor and engine PIDs, observed owned-process identities, and process exit
states before and after each geometry, camera, screenshot-trigger, and copy
action. The runner retains a Windows handle to the observed child engine and
records its exact unsigned exit code and hexadecimal form if that object exits.
Each view also has a full start/end interval, including the 1.5-second camera
settle and screenshot-source guard, so an exit between camera response and
capture request is localized. A failed action is marked `FAIL` even if rollback
later restores the baseline. These are code and synthetic-test results, not a
new native capture or an explanation of the historical exit.

This is an **output identity and diagnostic step**, not a successful native
capture. The existing [`capture` recipe](d11_aaa_native_preflight_recipe.json)
remains preflight only and now pins the new runner SHA-256. It does not call
`--execute`. The failed historical capture remains failed; the accepted
installed package remains at SHA-256
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.

The job runner now retains its lock and sets `recoveryRequired` whenever a
phase fails after a native command starts, including nonzero exit and missing
outputs. A failure before native launch can release the job lock. Native replay
still needs a bounded editor-session recovery policy. The independent job-lock
recovery procedure is `roadcraft jobs-recover`: first inspect `jobs-status`,
the original job receipt, `roadcraft status`, and the legacy capture receipt.
Resolve any package recovery through its own transaction procedure; a failed
capture remains failed evidence even when its rollback is verified. Record the
exact SHA-256 values of the shared job lock, owner `receipt.json`, installed
package, `project.json`, and `local/machine.json`, then run `jobs-recover`
without `--apply` and review its `ready` result. Reuse those five hashes with
`--apply` only if the external state is still the reviewed state. The exact
PowerShell preview and apply commands are in the [toolchain README](../README.md#pinned-workflow-commands).
The command
refuses a live or unproven owner, active authoring process, unaccepted installed
package, pending transaction lock, or transaction receipt that needs review.
It writes a separate `job_recovery_<id>.json` and removes only the shared job
lock. Its `released` status and SHA-256 document the release; `jobs-status`
should then report `lockPresent: false`, while the original failed receipt
stays failed. A `verified_release_pending` recovery receipt after interruption
needs manual review of the lock's current presence. The legacy runner's
`finally` rollback is guarded, but a killed
process or power loss can bypass it. This contract does not solve the prior
editor disconnect or establish visual or campaign acceptance. Do not place
`--execute` in a job recipe until those gates are implemented and reviewed.

The [versioned patch manifest](patches/capture_candidate_native.patch_manifest.json)
records base SHA-256 `b3670ff30afeb06e94301f68e12bf62d3857c5f21f1958ccc982ced2fb04831d`
and patched SHA-256
`89fc71ee14751f77ba7b79a1c0714b0d6df85bee4c526955d312e23c234914da`.
The archived base, patched copy, and unified diff are adjacent to that manifest.
The synthetic contract tests import the patched copy; local verification also
checks that the live Steam runner has the same patched hash.
