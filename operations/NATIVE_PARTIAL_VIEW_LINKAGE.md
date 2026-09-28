# Per-view partial native observation handoff

`roadcraft.native_capture_partial` defines a **partial** per-view handoff for
the maintained D11 AAA native runner. The runner, output contract and read-only
postflight now carry this schema. This integration is code-only: no editor,
package, scene, screenshot, or historical receipt was changed. Synthetic
tests do not prove a native run. The failed `bd58bce0` AAA capture
cannot be upgraded because it has neither a per-view `Read` transport nor the
six action windows this handoff requires.

The maintained runner performs `SetCab<view>`, settles the camera, checks that
the screenshot source is new, calls `ReadPreCapture`, then calls
`CaptureCab<view>` and copies `cab_<view>.png`. `CaptureCab` executes
`SaveScreenshot` **before** its shared editor response is constructed. The
`Read` transport declares `readOnly: true` and writes
`pre_capture_<view>.json`. This marker does not prove the SSL script lacks other
mutations; the generated request and its pinned helper template still need
review. After copying the PNG, the runner calls `build_partial_view` with the exact set-camera,
pre-read, and capture transport files plus the six ordered action events:

1. `SetCab<view>`
2. `SettleCamera`
3. `ScreenshotSourceGuard`
4. `ReadPreCapture`
5. `CaptureCab<view>`
6. `SaveScreenshot:<view>`

The builder accepts only the D11 AAA run/variant/view names, one shared engine
PID, matching helper and workspace identities, distinct request GUIDs,
response bytes that exactly decode from each transport's Base64 payload, and
ordered request/response times inside their action windows. It requires the
pre-read reply within ten seconds of the capture action start and checks that
its reported camera/window resolution matches the copied PNG. Set-camera,
pre-read and post-trigger camera transforms must agree. It pins the exact
scene-source, helper, transport, and image bytes by SHA-256. The capture request
must contain the exact `SaveScreenshot` target before its final return. The
target uses the historical runner's inner ID (`<outer eight-hex run ID>` plus
the variant's two-letter suffix, such as `a1b2c3d4ma`). The
saved JSON can be rechecked with `verify_partial_view`; that result is
`PARTIAL_VIEW_LINKAGE_CONSISTENT`, **not** native origin authentication.

The resulting record distinguishes `preScreenshotReported` from
`postTriggerReported`, preserving changes such as a truck work light switching
on during capture. Its `declaredTriggerWindow` starts at the runner's capture
action boundary and ends at the helper's response. The helper records
`requestSentUtc` after sending, so that timestamp is not a valid lower bound.
No exact screenshot trigger instant is invented. The scene hash is
for an on-disk `.scn`, not a measured loaded scene. Camera up, weather preset,
time of day, sun direction, ambient RGB, complete scene-light roster, exposure,
tonemap, and renderer mode are still absent. Every record states
`pairProtocolEligible: false`, `loadedSceneVerified: false`,
`captureProcessAuthenticated: false`, and `nativePostflightVerified: false`.
The baseline/candidate pair validator remains unchanged and cannot consume
this partial schema as its required complete `native-editor-response`.

The runner declares one `pre_capture_<view>.json`, its transport log, and one
`partial_<view>.json` per view. Nested reports pin them and all three probe
transport logs; the outer receipt pins each nested report and hashes the exact
required-output roster. The contract pins the partial-linker and helper
source. Read-only postflight checks the 45 linked records against the exact
action transcript and output roster. This still does not independently prove
the generated `Read` script is non-mutating or authenticate editor-origin
responses. The reviewed no-write plan and runner SHA must be regenerated
after code changes before any future native execution.
