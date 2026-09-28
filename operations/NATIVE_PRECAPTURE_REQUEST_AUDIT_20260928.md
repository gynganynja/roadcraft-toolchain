# D11 pre-screenshot Read request audit (2026-09-28)

`native_capture_partial` currently accepts a transport's `readOnly: true`
classification and binds its script hash to a view. That classification does
not by itself establish what SSL was sent. This audit adds a separate,
read-only check for the exact current `ReadPreCapture` request content and its
source-generation chain. It did not start an editor or Painter, send SSL,
write a capture, or modify the accepted scene or package.

## Current pinned result

The maintained runner's `ReadPreCapture` action calls the generated
`native_controls.ps1` in mode `Read` between the screenshot-source guard and
`CaptureCab`. In the pinned `native_controls_template.ps1`, the common SSL
here-string contains one `__ACTION__` placeholder. Mode `Read` leaves
`$action=''`; the subsequent replacement inserts an empty string. The
remaining request reports truck systems, camera position/forward and
truck-local lights. Inspection of this exact request found no explicit engine
state setter or `SaveScreenshot` call. Local arrays and the `result` string are
built in the temporary request. This is a static observation of reviewed
bytes, not proof that every native getter is side-effect free.

| Reviewed item | SHA-256 or result |
| --- | --- |
| Template `D11_Final_Candidate_20260925/native_controls_template.ps1` | `9722e35723f75fd841f95e81848cdf1759261d9ef2141fd6948ac9e23ac60c0d` |
| Template generator `native_acceptance.py` | `89b1431099bacc00a3173ffbe46c9db929df949e40df11f580` |
| Survey bridge `capture_interior.py` | `dae524f24afad50e04902d8310775478577d5f48c8610fb3595e3b376ea8f19f` |
| View generator `capture_cab_survey.py` | `083652fc56cf6d0bcc54ab139c7100f126427f9a5d2da9df5fb29dbf3eeec2ef` |
| Maintained runner `capture_candidate_native.py` | `6449ddc08c81165231ee39f90e171b2f5a2c7fdecc9e2e21b1b2c1b2d4733585` |
| Empty-action Read SSL, LF-normalized UTF-8 | `61cd4d77e6441660f094bb86fa62eda0fa9a93c37c85aa7d31df5fac111b732e` |
| Entire generated helper after replacing its 20 run-ID tokens with `RUNID` and normalizing newlines | `44bf3dacc0fd2bb7fb163ea464da4ac117d0c3139e9667fa8a734dae85c1fda5` |

The generated-helper fingerprint matched all five retained maroon, nearnew
and worn helpers from historical `bd58bce0` and `1f365624` runs. The actual
maroon `bd58bce0` helper also passed the new verifier, with its raw SHA-256
`febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975`.
These are historical helper files, not new native responses. The current
runner/source pins passed the verifier in the Steam source tree.

The new `python -B -m roadcraft.native_precapture_request` command reads
`local/machine.json` to locate the SDK source root and fails if any of those
five source hashes or the derived Read SSL bytes change. With `--helper
<absolute-native_controls.ps1>` it also checks the exact generated helper's
full normalized fingerprint, variant/run identity, empty Read-mode action,
single replacement and single send. With both `--helper` and `--transport
<absolute-pre_capture_VIEW.json>` it requires a passing `Read` transport, the
helper SHA-256, and an exact match between the **sent** SSL script and the
reviewed request. A true `readOnly` marker with an added state setter fails.
No current `pre_capture_VIEW.json` exists for the guarded runner, so transport
verification is a future check, not a completed native test.

The preflight-only `capture` recipe now declares the no-helper source check
before its existing full-capture no-swap check; its dry run verifies the
command and inputs, while an applied preflight would execute the check.
The postflight now invokes the verifier on every one of the 45 required
`ReadPreCapture` transports. It first pins the verifier's own source bytes and
import location, then derives the SDK root from the reviewed template path.
For each view it requires the reviewed generator chain, full generated helper,
helper hash in the transport, and the exact sent empty-action SSL. A transport
whose `readOnly` marker stays true while its script adds a setter fails even
if its file and linked receipt hashes are consistently resealed. The recipe's
source-only check still does not verify a future generated helper or transport;
the postflight gate does so only after those files exist. The capture runner
does not invoke this verifier during capture.

The synthetic full-capture postflight fixture passed all 45 request checks and
a separate resealed-mutating-request case failed at the content check. All 18
postflight tests passed locally. No current `pre_capture_VIEW.json` exists,
so this remains a verified verifier path rather than a completed native check.
The preserved `d11_aaa_native_capture_plan_c0de2026.json` pins older source
bytes; generate and review a fresh no-write plan for a future run instead of
rewriting that historical artifact.
Five portable tests cover a passing exact request, source drift, a malicious
Read-mode action, unrelated generated-helper tampering, and a mutating sent
request that still declares `readOnly: true`. The current offline preflight
and retained-helper check both passed. This check makes request-content drift
visible, while native capture execution remains blocked by the separate
lighting, loaded-scene and screenshot-origin requirements.

The verifier always returns `loadedSceneVerified: false`,
`captureProcessAuthenticated: false`, `pairProtocolEligible: false` and
`nativePostflightVerified: false`. It cannot prove a loaded scene, complete
runtime lighting, native origin of a reply, or who produced a PNG. The failed
historical run remains failed; no baseline/candidate pair becomes comparable.
