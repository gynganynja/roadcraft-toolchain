# Read-only AAA capture postflight

`python -m roadcraft.native_capture_postflight` validates one completed full
D11 AAA native capture after the legacy runner exits. It reads evidence and
package bytes only. A zero exit means the outer receipt says the full capture
completed, rollback says the baseline was restored, and the live installed PAK,
candidate PAK, rollback backup, three nested variant receipts, 45 screenshots,
and 45 camera probes match their expected paths and SHA-256 hashes. A failed
capture returns a nonzero exit even when its rollback restored the baseline.

Supply externally reviewed expected values. In particular, select the exact
new eight-character run ID; do not discover the newest receipt by directory
date. Run from the toolchain checkout with `src` on `PYTHONPATH`:

```text
python -m roadcraft.native_capture_postflight --capture-receipt ABSOLUTE_PATH_TO_candidate_capture_RUNID.json --run-id RUNID --candidate-package ABSOLUTE_PATH_TO_CANDIDATE_PAK --candidate-sha256 EXPECTED_CANDIDATE_SHA256 --installed-package ABSOLUTE_PATH_TO_INSTALLED_PAK --baseline-sha256 EXPECTED_ACCEPTED_BASELINE_SHA256 --installed-sha256 EXPECTED_INSTALLED_SHA256
```

The two expected baseline/installed hashes must agree for a restored run. The
optional `--expected-capture-receipt-sha256` verifies an outer receipt digest
that was pinned independently before this check. Without it, the tool reports
the observed outer digest for later sealing; the nested hashes establish
internal consistency but cannot independently authenticate an edited receipt.
The legacy runner currently chooses a random run ID, so this validator runs
after an exact receipt has been identified. A deterministic executable recipe
still needs a reviewed runner adapter and output contract.

The JSON result is a **technical capture integrity check**, not proof that an editor
session was safe to start, a build succeeded, a screenshot looks correct, or
baseline and candidate scenes match. It does not verify live source files,
lighting, resolution, protocol, numerical improvement, campaign behavior, or
visual acceptance. Run the source/package and regression gates separately;
record independent visual and campaign decisions. This validator neither
changes the older lighting runner's 14 GiB staging reserve nor authorizes
another `--execute` run. The captured editor crash in the latest full AAA run
still needs diagnosis before replay.
