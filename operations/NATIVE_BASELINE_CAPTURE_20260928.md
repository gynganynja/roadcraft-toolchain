# Accepted-project baseline capture adapter — 2026-09-28

`roadcraft.native_baseline_capture` now declares a separate 45-view baseline
capture against the **accepted** D11 source project and the installed accepted
PAK. It reuses the reviewed SDK camera and screenshot routine with an explicit
accepted-project mount, a distinct `baseline_runs` tree and a baseline outer
receipt. It never stages or swaps a PAK. The adapter pins the accepted source
manifest and authoring inventory, the accepted and installed PAK hashes, all
1,576 referenced project files, the inner runner and helper sources, the editor
mount, three validation scenes, and the exact 382-file output roster. It
checks for active RoadCraft/editor processes and native locks before execution.

The three accepted validation `.scn` files are byte-identical to the AAA
candidate's corresponding files:

| Variant | SHA-256 |
| --- | --- |
| maroon | `9481bca1db96dd5c3c0c201f9d7f84e0b16fd7e683905c286060b16e9d53dfa1` |
| nearnew | `7bb6428240ecb1acf0d31674d855d8af6eebefe57f62d7f4956bf8d603b0a701` |
| worn | `a518939a52afa5dd946a480161545e257fa89c7d0968d489937a27adf5a1bd8c` |

The three accepted `export.usf` model sources differ from the AAA candidate.
Mounting the accepted project is therefore necessary: merely leaving the
accepted PAK installed while mounting the AAA source would not be a baseline.
The no-write preflight completed for run ID `a1b2c3d4`; it found 382 declared
outputs, the accepted editor mount and all three compiled interior nodes. No
editor was launched and no baseline capture was produced by this check.

Run `python -m roadcraft.native_baseline_capture --run-id <fresh-eight-hex-id>`
with the selected checkout's `src` on `PYTHONPATH` to print a no-write full
plan. `--variants maroon --views front_seat` makes a one-view diagnostic plan;
the resulting receipt remains triage evidence and cannot satisfy the 45-view
requirement. Save
that entire JSON to a new ignored `local` file and independently pin its
SHA-256. Only after reviewing that exact output contract, run the same command
with `--execute --expected-contract-sha256 <outputContractSha256>`. The runner
requires no active editor and reserves a new lock and outer receipt before
launching its own editor. Its installed-package identity is checked throughout;
an interrupted run retains its failure receipt and, when state is uncertain,
its lock for investigation. The inner routine's historical
`candidatePackageSha256` field is bound to the **accepted** PAK hash in a
baseline variant report; it is a legacy field name, not a candidate-package
claim.

`roadcraft.native_baseline_postflight` takes the saved plan and produced outer
receipt, plus **independently supplied** SHA-256 pins for both files. It checks
the no-swap contract, the accepted project and package, all declared outputs,
the selected native variant reports and partial-view links, and their matching
action windows. A full capture checks 382 declared outputs and 45 views; a
one-view diagnostic checks 16 declared outputs and one view. A successful result is
`BASELINE_PARTIAL_CAPTURE_INTEGRITY_VERIFIED`, with `pairProtocolEligible`,
`loadedSceneVerified`, `captureProcessAuthenticated`, `technicalPassed`, and
`releaseReady` all `false`.

This adapter and postflight do not fill the current editor helper's missing
runtime observation fields or prove engine-origin scene/PNG bytes. The 45-view
pair protocol therefore remains blocked even if a baseline run and its partial
postflight pass.

## One-view native diagnostic, failed before capture

The reviewed `b1c2d3e4` plan selected only `maroon/front_seat`, declared 16
outputs and no PAK swap, and had contract SHA-256
`93ad113a69682d64ccf812ad4931873387c4257b019fd26bf60657b471cd05c6`.
Its ignored local plan file hashes to
`d9e08fac5680521644e30764e8c491c97b26858ebff0e571062c23cc1b09583c`.
Hosted [CI #56](https://github.com/gynganynja/roadcraft-toolchain/actions/runs/36425332848)
passed before the diagnostic was launched. The runner did start its owned
Mod Editor against the accepted project. During scene startup, free C: space
fell below the inner runner's 1.5 GB safety floor; it stopped before any
`front_seat` screenshot. The outer receipt is `FAIL` (SHA-256
`44b43afd400faa6d22a3dedd6b7170821e9873072923a1a8b99ba5b36b3ec2f0`);
the maroon report is also `FAIL` (SHA-256
`af2ae06f4056bd57edcc2aa65bb55aa897489e69bda65beedffe0c9fd71184f0`).
The editor exited, its baseline lock was released, and the installed PAK
still hashes to the accepted
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.
The failed run and logs remain untouched as evidence.

The preflight floor is now 16,000,000,000 free bytes, above the approximately
10.9 GB available before that launch. This prevents another start under the
same observed disk condition; it is not a guarantee that every editor run fits.
Changing the runner invalidates the old contract, so a future diagnostic needs
a fresh run ID and reviewed plan. A separate read-only storage preflight after
the failure reverified the 23,604 exact generated export-copy candidates in
`storage_expansion_review_20260928.json` (SHA-256
`aa5aad369e601cf9bf076d11101fd3925f396de5898338fc150b4cfed69e7ec7`).
They total 6,368,972,800 allocated bytes; its new dry-run receipt hashes to
`d0339967e6337ac9f9c9cf6305a16a630518ae162815c9b8b75e2051d6d4bb52`.
It found 21 retained packages, 166 retained source files, no tracked
candidates, no active process owners, `applyReady: true`, and zero deletions.
That separate cleanup has not been authorized or applied.
