# Per-view partial native observation handoff

`roadcraft.native_capture_partial` defines a **partial** per-view handoff for
the next D11 AAA native runner. It is code-only: no editor, package, scene,
screenshot, or historical receipt was changed while adding it. Its synthetic
tests do not prove a native run. The current failed `bd58bce0` AAA capture
cannot be upgraded because it has neither a per-view `Read` transport nor the
six action windows this handoff requires.

The maintained runner has a useful insertion point. It currently performs
`SetCab<view>`, settles the camera, checks that the screenshot source is new,
then calls `CaptureCab<view>` and copies `cab_<view>.png`. `CaptureCab` executes
`SaveScreenshot` **before** its shared editor response is constructed. A future
runner can insert a `ReadPreCapture` action at that point, using the existing
helper's `Read` mode, whose transport declares `readOnly: true`, and writing
`pre_capture_<view>.json`. This marker does not prove the SSL script lacks other
mutations; the generated request must be reviewed and pinned in the protocol. After
copying the PNG, it can call `build_partial_view` with the exact set-camera,
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
pre-read reply within ten seconds of the capture request and checks that its
reported camera/window resolution matches the copied PNG. It pins the exact
scene-source, helper, transport, and image bytes by SHA-256. The capture request
must contain the exact `SaveScreenshot` target before its final return. The
target uses the historical runner's inner ID (`<outer eight-hex run ID>` plus
the variant's two-letter suffix, such as `a1b2c3d4ma`). The
saved JSON can be rechecked with `verify_partial_view`; that result is
`PARTIAL_VIEW_LINKAGE_CONSISTENT`, **not** native origin authentication.

The resulting record distinguishes `preScreenshotReported` from
`postTriggerReported`, preserving changes such as a truck work light switching
on during capture. Its `declaredTriggerWindow` spans the capture request and
reply; it never invents an exact screenshot trigger instant. The scene hash is
for an on-disk `.scn`, not a measured loaded scene. Camera up, weather preset,
time of day, sun direction, ambient RGB, complete scene-light roster, exposure,
tonemap, and renderer mode are still absent. Every record states
`pairProtocolEligible: false`, `loadedSceneVerified: false`,
`captureProcessAuthenticated: false`, and `nativePostflightVerified: false`.
The baseline/candidate pair validator remains unchanged and cannot consume
this partial schema as its required complete `native-editor-response`.

Before integrating into a native run, revise the maintained patched runner
and regenerate its pinned runner SHA. Add one `pre_capture_<view>.json`, its
transport log, and one new `partial_<view>.json` to each view's required output
contract; pin the partial receipt SHA in the nested run report and outer
receipt chain. Review the helper's exact generated `Read` and `CaptureCab`
scripts and pin the helper/probe source in the protocol. Extend native
postflight to recheck every added per-view file and its report link. The
current reviewed dry-run plan pins the existing runner and file roster, so
that plan must be regenerated and reviewed before any execution. None of
these remaining edits have been made by this module.
