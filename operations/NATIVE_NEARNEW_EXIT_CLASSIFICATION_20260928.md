# Retained nearnew editor-exit classification (2026-09-28)

The historical `bd58bce0` nearnew capture lost selected engine PID **13444**
after the fourth view's `SetCabRightDown` reply and before its
`CaptureCabRightDown` SSL request. This classifies the immediate failure as an
unavailable engine process identity at the helper's PID precheck. It does not
identify why that process vanished.

All paths below are relative to the Steam RoadCraft Development Package SDK
root. The outer `D11_Interior_AAA_20260928/native/candidate_capture_bd58bce0.json`
records `FAIL_ROLLBACK_PENDING`; its rollback subrecord says
`BASELINE_RESTORED` with accepted PAK SHA-256
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.
The nearnew `native/runs/aaa_nearnew_bd58bce0ne/report.json` records `FAIL`
and three completed earlier views.

| Retained evidence | SHA-256 | Observation |
| --- | --- | --- |
| `D11_Interior_AAA_20260928/native/candidate_capture_bd58bce0.json` | `805689d11c4d7d9154559884fe17409da480c8d27756d45120f90d5a3078d915` | Outer failure and restoration record. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/report.json` | `c19ee92c3215ff0b4e3906489b42aa401c3f07a3f247fe07802ccf938717d6d7` | Three completed views; fourth view absent. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/camera_right_down.json` | `16e74a06255a1e04b879b4daa07626928cae336ec67dcb978ba23ca6bc48edb6` | `SetCabRightDown` returned `status=pass`, `stage=response_received`, PID 13444 at **2026-09-27 23:20:19.7295212 UTC**. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/camera_right_down.transport.log` | `a3de59fc3adbdbda3348d712d5ec91ca940aaa115b3eaaef13ead15c0892c48f` | Confirms the same successful camera reply. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/stdout.log` | `4dd54782df304243365d0cd438d61ebda25e9fb40285d1d610ce28b6f9285d2b` | Lines 352–353: debugger and game-editor connectors disconnected from PID 13444 at **2026-09-28 09:20:20.693 Brisbane**, or **2026-09-27 23:20:20.693 UTC**. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/capture_right_down.transport.log` | `c97dcfb70591a46eb8db19a2c3c68df13521df1afc6c0bb5302dfe915b7061bc` | The helper's line 788 `Get-Process -Id 13444` could not find that PID. |
| `D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne/native_controls.ps1` | `5ebbd6a9a390810cf36e079fc7dd4fe2789fb1b181d9688561ae69c96142dc0e` | Lines 787–810 place the PID guard before report creation, transport connection and SSL send. |

`capture_right_down.json` and `cab_right_down.png` are absent. The archived
pre-guard runner at `RoadCraftToolchain/operations/patches/capture_candidate_native.base_b3670ff3.py`
(SHA-256 `b3670ff30afeb06e94301f68e12bf62d3857c5f21f1958ccc982ced2fb04831d`)
shows a 1.5-second sleep between camera and capture probes at lines 468–475.
The disconnect is consistent with that camera-to-capture gap, but the old
receipt does not pin a runner SHA or bracket the sleep. Its exact subphase
cannot be proved. The immediate fourth-view failure was neither a transport
timeout nor a screenshot-source failure: the PID guard failed before either
stage. The same earlier `Shared Texture load problem: pointer` appeared in the
completed maroon 15-view run, so it does not distinguish this exit.

Read-only checks on 28 September found no matching Application crash/hang/WER
or .NET events (IDs 1000, 1001, 1002, 1026), Security process-termination
event 4689, or WER-Diag, WER-PayloadHealth or WerKernel events in the
09:19:30–09:21:00 Brisbane window. Accessible WER ReportArchive and
ReportQueue had no RoadCraft/ModEditor/IntegrationStudio name matches. The
user CrashDumps directory was access denied, so no dump conclusion follows.
These negative checks cannot distinguish a crash from clean exit, termination,
or restart.

The current guarded runner at
`D11_Interior_AAA_20260928/capture_candidate_native.py` (SHA-256
`78e2f3634cbfde8d2b64b15652275474646338efe7f1f25a760a2140cfdc73dc`)
now records action boundaries and retains an engine process handle, but this
change has not been exercised in a native run. The available offline evidence
is exhausted for the exit cause. A future separately authorized native run
would need that handle's exit code and any associated crash record; the failed
historical capture remains failed.
