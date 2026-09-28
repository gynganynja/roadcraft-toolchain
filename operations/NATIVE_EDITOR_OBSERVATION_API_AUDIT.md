# Native editor observation API audit (2026-09-28)

The current D11 AAA capture runner cannot produce the observation required by
[`capture_pair_protocol`](BASELINE_CANDIDATE_CAPTURE_PROTOCOL.md). This audit
uses only the shipped SDK/editor files and sealed historical responses. No
editor or game process was launched, and no package or historical receipt was
changed. The failed `bd58bce0` capture remains failed.

## Direct evidence

- `D11_Interior_Repair_20260926/capture_cab_survey.py` (SHA-256
  `083652fc56cf6d0bcc54ab139c7100f126427f9a5d2da9df5fb29dbf3eeec2ef`,
  lines 51–67) positions a fly camera from the `_cockpit_camera` seat
  transform. Its seat transform supports `GetPosition`, `GetForward`,
  `GetLeft`, and `GetUp`. This proves the basis used to *set* the camera;
  the helper does not currently report the active camera's up vector.
- The generated native helper
  `D11_Interior_AAA_20260928/native/runs/aaa_maroon_bd58bce0ma/native_controls.ps1`
  (SHA-256 `febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975`)
  reads `$sslEngineCtrl.GetVideoConfig().windowSizeX/Y` (line 56),
  `GetActivePlayCamera().GetScreenSize()` and active transform position/forward
  (lines 177–184). It enumerates the truck's Sfx groups and reports each
  `TryGetFxLight("light")` position, tangent, intensity, radius, cone, and
  `IsStarted()` state (lines 147–158). These are truck-local Sfx lights, not a
  proven complete scene-light roster.
- Its `SetCabFrontSeat` transport
  (`camera_front_seat.json`, SHA-256
  `fdb450f84c7f98b76c93bdc49caf95539111ac7b71c68567727750b90893b3b2`)
  reports 913×559 for both video window and active play camera, the camera
  position/forward, and the truck-local lights. Its `CaptureCabFrontSeat`
  transport (`capture_front_seat.json`, SHA-256
  `6618d44d7d9f5b77a19d8e5ba95e46d149ef7cd634b8b0e7deeaa2224f1da694`)
  reports the same camera and resolution, but several work-light `IsStarted`
  values change from false to true. The two replies therefore cannot be treated
  as one fixed lighting state. `CaptureCab` runs `SaveScreenshot` before the
  shared helper appends those light fields, so even its reply is not a
  pre-trigger observation.
- The selected maroon `.scn` file declares
  `initialDaytimeMin = initialDaytimeMax = 0.5`, `daytimeSpeed = 0`, and
  `initialWeatherCondition = "Initial"` (lines 275–280). Those are pinned
  source declarations. The available transport does not read the resulting
  runtime weather, time of day, sun direction, or ambient lighting.

The SDK's `predefined_types.ssl` is a short generic type prelude; it does not
declare renderer, weather, tonemap, or camera-query interfaces. Searches of
the available text scripts found no proven getters for runtime environment,
exposure, tonemap, or renderer mode. Absence from those text files does not
prove the native engine lacks an API; it means this workflow cannot claim one.

## Implemented read-only diagnostic

`python -m roadcraft.native_capture_observation <camera-or-capture.json>`
parses an existing, passing editor transport and reports only its raw measured
camera position/forward, two screen-size values, and truck-local light data.
It carries the transport mode, PID, timestamps, and hashes of the exact script
and response strings. It reports `PARTIAL_CONTEXT_ONLY` and
`pairProtocolEligible: false`. It does not rewrite a run or produce the
`native-editor-response` schema. A `CaptureCab` transport is explicitly a
post-trigger reply, while `SetCab` precedes a separate screenshot action.

The editor transport also lacks run/role/variant/view/protocol/loaded-scene
identity, camera basis/spec, screenshot trigger/copy timestamps, image SHA,
and actual image dimensions. Some can be bound from a future runner's pinned
inputs and PNG bytes, but they are absent from the present transport and must
be sealed with the native reply rather than reconstructed for old runs.

## Remaining native API and runner work

Before a matched baseline/candidate capture, verify a read-only native query
for the active camera's up vector and the complete renderer state: actual
weather, time of day, sun direction, ambient RGB, all relevant local lights,
exposure, tonemap, and renderer mode. The existing active-camera transform may
support `GetUp()` because the seat transform does, but that call has **not**
been tested on the active camera. Identify and smoke-test the global getters
in a disposable editor session. If any field is unavailable, keep the pair
gate blocked instead of filling it from `.scn` defaults or policy labels.

Then pin the exact query script and extend the future runner so every view
gets a raw editor reply immediately **before** its screenshot trigger, with
request/response/trigger UTC times, engine PID, loaded scene and protocol pins,
view offsets, and the PNG hash/dimensions. The runner must fail closed on a
missing or stale field. Both baseline and candidate require the same protocol,
variant scene bytes, camera transform, lighting, and resolution. The current
`D11_Interior_AAA_20260928/capture_candidate_native.py` only records the
`SetCab`/`CaptureCab` transports and PNG dimensions; it was not changed here.
