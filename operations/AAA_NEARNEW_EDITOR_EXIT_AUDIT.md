# Historical AAA near-new editor exit audit

The 28 September 2026 `bd58bce0` AAA candidate capture failed because the
owned `Roadcraft ModEditor` engine process (PID 13444) exited between the
fourth view's camera-setting response and its screenshot request. **The cause
of that process exit is unknown.** This is a diagnostic of existing evidence;
it is not a new native run or candidate acceptance.

All paths below are relative to the RoadCraft Development Package SDK root.
The outer receipt is
`D11_Interior_AAA_20260928/native/candidate_capture_bd58bce0.json`
(SHA-256 `805689d11c4d7d9154559884fe17409da480c8d27756d45120f90d5a3078d915`).
It records `FAIL_ROLLBACK_PENDING`; its rollback field records
`BASELINE_RESTORED` with accepted PAK SHA-256
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.
The near-new variant report is
`D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/report.json`
(SHA-256 `c19ee92c3215ff0b4e3906489b42aa401c3f07a3f247fe07802ccf938717d6d7`).

| UTC time, 27 September 2026 | Observation |
| --- | --- |
| 23:20:09–23:20:18 | `front_seat`, `front_down`, and `right` each produced a camera response, capture response, and PNG; the variant report pins these three views. |
| 23:20:19.729 | `camera_right_down.transport.log` reports a successful `SetCabRightDown` response from engine PID 13444 (SHA-256 `a3de59fc3adbdbda3348d712d5ec91ca940aaa115b3eaaef13ead15c0892c48f`). |
| 23:20:20.693 | `stdout.log` records both debugger and game-editor connector disconnects for PID 13444. Wwise assertions appear after these lines. The log's SHA-256 is `4dd54782df304243365d0cd438d61ebda25e9fb40285d1d610ce28b6f9285d2b`. |
| By 23:20:22 | `capture_right_down.transport.log` shows `Get-Process -Id 13444` failed at `native_controls.ps1:788`, before the helper connected or sent `CaptureCabRightDown` (SHA-256 `c97dcfb70591a46eb8db19a2c3c68df13521df1afc6c0bb5302dfe915b7061bc`). Neither `capture_right_down.json` nor `cab_right_down.png` exists in this run. |

The `Shared Texture load problem: pointer` stderr message occurred at
23:19:59, before the three successful screenshots. The same message is present
in the completed maroon run of this attempt, so it does not identify this
near-new exit. The Wwise leak/assert lines are shutdown evidence, not proof
that Wwise initiated the exit. The runner's `delay 00:05:00` scenario had not
elapsed, and the `CaptureCabRightDown` helper failed its initial PID guard;
neither the planned scenario `Stop` nor that capture request explains the
earlier disconnect. The historical runner did not record the engine's exit
code or a crash dump.

A read-only Windows Event Log query on 28 September 2026 found no RoadCraft
Application crash/hang/WER or .NET event (`1000`, `1001`, `1002`, `1026`)
between 09:15 and 09:25 Brisbane time. System events in that window were
unrelated BITS service-start changes. This absence does not prove a clean exit.
The user CrashDumps directory was access denied; no WER conclusion is drawn
from it.

Before diagnosing the exact cause, a future authorized native run would need
to retain the engine process handle and exit code, capture any Windows crash
event/dump when available, and record timestamped parent/child process
transitions around each view. Until then, keep this candidate's capture failed
and its visual/campaign gates unpassed.

The guarded runner now contains a code-only diagnostic improvement for such a
future run. It attaches a Windows process handle to the observed child engine
before geometry and view actions, records that handle's exact unsigned exit
code if the process exits, and brackets every view and each camera-settle,
capture, and screenshot action with UTC timestamps and process snapshots.
Synthetic tests exercise an exit during the settle interval and a real
short-lived Windows child exit code. No editor was launched for this patch, so
the historical exit cause and missing crash-event/dump evidence remain open.
