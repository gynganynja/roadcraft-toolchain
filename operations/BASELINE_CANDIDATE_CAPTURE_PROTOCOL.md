# Baseline/candidate capture comparison protocol

The read-only `roadcraft.capture_pair_protocol` validator checks whether two
newly captured runs have the same **observed comparison context**. It does not
launch RoadCraft, install a package, change an image, or approve a release.
Call it with `python -m roadcraft.capture_pair_protocol PAIR.json` after setting
`PYTHONPATH` to the checkout's `src` directory. Exit code 0 means the pinned
context evidence is internally consistent; the JSON result still sets
`technicalPassed` and `releaseReady` to `false`.

The pair manifest is schema 1 and contains pinned `protocol`, `baseline` run,
and `candidate` run files:

```json
{
  "schemaVersion": 1,
  "protocol": {"path": "protocol.json", "sha256": "<64 lowercase hex>"},
  "runs": {
    "baseline": {"path": "baseline_run.json", "sha256": "<64 lowercase hex>"},
    "candidate": {"path": "candidate_run.json", "sha256": "<64 lowercase hex>"}
  }
}
```

The pinned protocol file names an ID, a pinned native runner, a pinned UTF-8
editor probe script, ordered `variants` and `views`, an exact image `resolution`,
a complete expected `lightingState`, and `maxObservationAgeSeconds` (1–60).
Each view specifies `camera.basis` and two three-coordinate seat-relative
`camera.spec` offsets. The lighting state must contain `environment` with
`weather`, numeric `timeOfDay`, `sunDirection`, and `ambientRgb`; a `localLights`
array with ID, enabled state, and intensity for each light; positive `exposure`;
`tonemap`; and `rendererMode`. The validator compares the canonical JSON digest
of this state to the response observed at **every** screenshot. A label such as
`"fixed-interior-lighting-v1"` by itself is insufficient.

Each run receipt is schema 1 with `status: "CAPTURE_READY"`, explicit `role` and
`runId`, the protocol and runner SHA-256s, a pinned package binary, UTC start
and finish times, and an ordered variant roster. Every variant has a pinned
validation scene, an engine PID, and the complete ordered view roster. The
baseline and candidate must have distinct `runId` values; their package bytes
may still match for an A/A control comparison. Each view has a pinned
screenshot, a pinned editor observation, and UTC
`triggeredUtc` and `copiedUtc` timestamps. The validator checks the PNG/JPEG
header's actual pixel dimensions against the protocol and the editor response.
Each screenshot and observation must be its own output file across the pair;
the same path or a hard link to the same file cannot fill another view slot.
Identical image *bytes* in distinct files remain valid. Within each run, the
next view's observation request cannot start before the preceding view's image
copy has finished, including across variant boundaries.
Scenes must have identical bytes between baseline and candidate for a given
variant. This deliberately blocks a changed validation scene from masquerading
as an image regression caused only by the package.

An observation is the native runner's record of a query issued immediately
before a screenshot. It contains the **exact pinned probe script text** in
`requestScript`, `probeScriptSha256`, UTC request/response timestamps,
`source: "native-editor-response"`, and `responseRaw`: the editor's raw JSON
reply, not an analyst-written context label. The reply must include
`status: "OBSERVED"`, `runId`, `role`, `variant`, `view`, `enginePid`,
`protocolSha256`, `loadedSceneSha256`, runtime `resolution`, full `lightingState`,
and a `camera` with basis, spec, position, forward, and up vectors. The
observation must fall inside the run and precede the screenshot trigger by no
more than the protocol's age limit. Every field is required for each view.

The validator verifies file hashes and content, then requires exact equality
of the observed camera transform, lighting state, resolution, protocol, variant,
view, and scene identity for each baseline/candidate pair. A generic partial
roster can return `contextComparable: true` for diagnostic use, but
`pairComparable` is true only for the exact D11 `maroon`, `nearnew`, `worn`
variant order and all 15 names in `native_capture_postflight.VIEWS` (45 pairs).
Even a complete roster is **context comparable only**. `pairComparable` does
not mean image quality passed, and neither field means visual or campaign
acceptance.

The current native runner does not emit this observation schema. Its planned
lighting and resolution are explicitly unknown; the prior AAA run ended in
`FAIL_ROLLBACK_PENDING`. No historical receipt is rewritten or promoted by
this validator. A future native adapter must query the renderer and camera at
capture time and seal these raw replies in the run receipt. The
`CAPTURE_READY` and `native-editor-response` strings are still self-declared
by that runner: this validator does **not** authenticate the editor process or
prove native postflight succeeded. Before technical acceptance, link the pair
to independently pinned native outer receipts, verify both roles with
role-appropriate postflight adapters, check that each image and observation is
present in its native receipt chain, and feed that result into the regression gate. The validator
reports `nativePostflightVerified: false`, `captureProcessAuthenticated: false`,
`technicalPassed: false`, and `releaseReady: false` until that separate work is
done. The existing regression policy's signed visual and campaign claims remain
separate gates.

**Current-run hard limit:** the pinned `ReadPreCapture` SSL emits a multiline
`D11T_SYSTEMS_OK` text response, including camera and light lines. The pair
schema instead requires a JSON `responseRaw` with `status: "OBSERVED"` and
complete capture-time camera, lighting, scene and protocol fields. Therefore
an authentic run of the current native runner cannot pass the optional link
check below. Its positive unit test uses a mocked postflight and synthetic
JSON transport to check future bridge logic; it is not a live or integrated
native pass. A new reviewed runner/probe and non-mocked postflight integration
are needed before this check can validate real captures.

An optional candidate-only receipt check is scaffolded for a future runner
that emits the complete observation in its `ReadPreCapture` transport. Add a
`candidateNativeReceipt` object to the pair manifest with exactly `receipt`,
`plan`, `candidatePackage`, and `installedPackage` path/SHA-256 pins plus
`baselineSha256`. Supply the **independent** outer-receipt and plan SHA-256s to
the API as `expected_candidate_native_pins` or to the CLI as
`--candidate-native-receipt-sha256` and `--candidate-native-plan-sha256`. Pins
inside `pair.json` alone never enable the check. It reruns the existing D11
candidate postflight and checks all 45 candidate images, source-scene pins,
engine PIDs, action intervals, the protocol runner path/SHA-256, and
pre-screenshot native transport files
against the pair records. Each candidate observation must include a
`nativeTransport` path/SHA-256 pin whose exact script, raw response, timestamps,
and PID match the native `ReadPreCapture` record. Changed or missing links
fail validation; success reports `candidateNativeReceiptLinked: true` and
`candidateNativePostflightVerified: true`.

That candidate-only result is a receipt-chain consistency check. The current
`native_capture_postflight` verifies a candidate run followed by baseline
restoration; it is **not** a verifier for a baseline capture run. There is no
baseline receipt adapter yet, and the current partial Read response cannot
provide the complete observation schema. Consequently
`nativeEvidenceLinked` and `nativePostflightVerified` remain false for the
pair, including when the candidate-only check passes. The check also cannot
prove which scene bytes the engine loaded or that it produced the PNG;
`captureProcessAuthenticated`, `technicalPassed`, and `releaseReady` remain
false. A baseline adapter, a full capture-time renderer observation, and
engine-origin scene/PNG proof are still required before native evidence can
support technical acceptance.

Focused synthetic tests cover reused screenshots, overlapping view intervals,
absent or changed lighting, camera transform,
runtime or PNG dimensions, protocol/probe identity, variant roster, stale
observations, tampered images, partial rosters, and the complete 45-view D11
roster. They do not create native evidence or a passing release receipt.
