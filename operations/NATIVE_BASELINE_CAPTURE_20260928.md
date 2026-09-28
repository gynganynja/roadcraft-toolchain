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
with the selected checkout's `src` on `PYTHONPATH` to print a no-write plan. Save
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
the no-swap contract, the accepted project and package, all required outputs,
the three native variant reports, the 45 partial-view links and their matching
action windows. A successful result is
`BASELINE_PARTIAL_CAPTURE_INTEGRITY_VERIFIED`, with `pairProtocolEligible`,
`loadedSceneVerified`, `captureProcessAuthenticated`, `technicalPassed`, and
`releaseReady` all `false`.

This adapter and postflight do not fill the current editor helper's missing
runtime observation fields or prove engine-origin scene/PNG bytes. The 45-view
pair protocol therefore remains blocked even if a baseline run and its partial
postflight pass. No native execution has been attempted for this adapter; its
current evidence is preflight only.
