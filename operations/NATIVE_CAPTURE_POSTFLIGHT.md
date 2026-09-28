# Read-only AAA capture postflight

`python -m roadcraft.native_capture_postflight` checks one completed full D11
AAA capture against an **externally pinned no-write plan**. It never launches
an editor, changes a package, or upgrades a failed run. A zero exit requires
the accepted baseline to be restored, the candidate and installed package
hashes to match, all 383 planned output paths to match the exact D11 layout,
and the outer receipt to hash every required file except itself. The three
nested reports must pin 45 valid PNGs and 45 partial pre-screenshot links.

The postflight replays each partial link against its exact scene, helper,
camera, pre-read, capture transport, copied image, and six consecutive runner
actions. It checks the ordered editor/engine PID snapshots, all 135 transport
request IDs for uniqueness, each variant's partial-link digest, and the
reviewed runner, helper-source, and linker-source hashes. An output or source
change, missing file, failed action, failed rollback, or historical receipt
without this schema returns nonzero. The plan SHA-256 must come from the
reviewed `--plan` result; calculating a new hash for an unreviewed plan is not
an independent check.

Use exact paths and SHA-256 values from the reviewed run:
The current plan pins the Steam source mirror's `RoadCraftToolchain/src`
modules, so set `PYTHONPATH` to that exact `src` directory when invoking the
module. Importing an otherwise identical copy from the dedicated Git checkout
does not satisfy this plan's source-path check.

```text
python -m roadcraft.native_capture_postflight --capture-receipt ABSOLUTE_PATH_TO_candidate_capture_RUNID.json --run-id RUNID --candidate-package ABSOLUTE_PATH_TO_CANDIDATE_PAK --candidate-sha256 EXPECTED_CANDIDATE_SHA256 --installed-package ABSOLUTE_PATH_TO_INSTALLED_PAK --baseline-sha256 EXPECTED_ACCEPTED_BASELINE_SHA256 --installed-sha256 EXPECTED_INSTALLED_SHA256 --capture-plan ABSOLUTE_PATH_TO_REVIEWED_PLAN.json --capture-plan-sha256 REVIEWED_PLAN_SHA256
```

`--expected-capture-receipt-sha256` is optional when first sealing a new outer
receipt; supply it if that receipt was independently pinned already. Without
it, the result reports the observed digest and verifies the receipt's internal
chain, but does not independently authenticate that outer receipt.

`captureIntegrityPassed` is a file and self-reported action consistency
result. It is **not** a comparable baseline/candidate pair or visual,
campaign, or release acceptance. The transport and PID records are runner
observations, not independent proof of editor origin. The source scene hash
does not prove which scene was loaded. Camera up, complete runtime lighting,
renderer state, and an exact screenshot trigger instant remain absent. The
result therefore always keeps `pairProtocolEligible`,
`captureProcessAuthenticated`, `loadedSceneVerified`, `visualReviewed`, and
`campaignAccepted` false. The old failed AAA receipt remains failed even
though its rollback restored the accepted package.
