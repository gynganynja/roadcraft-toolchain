# AAA native capture failure analysis

Date: 28 September 2026, Australia/Brisbane. This is an evidence review of
run `bd58bce0`, not a successful capture or an explanation of the editor's
root cause.

The outer receipt
`D11_Interior_AAA_20260928/native/candidate_capture_bd58bce0.json`
(SHA-256 `805689d11c4d7d9154559884fe17409da480c8d27756d45120f90d5a3078d915`)
reports `FAIL_ROLLBACK_PENDING`. Its rollback subreceipt reports
`BASELINE_RESTORED` with installed hash
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.
The read-only postflight validator returns exit 1 and
`captureIntegrityPassed=false`. The maroon nested report records 15 views;
the failed nearnew report records only `front_seat`, `front_down`, and
`right`; worn was not started.

The nearnew run directory is
`D11_Interior_AAA_20260928/native/runs/aaa_nearnew_bd58bce0ne`.
Its report (SHA-256
`c19ee92c3215ff0b4e3906489b42aa401c3f07a3f247fe07802ccf938717d6d7`)
records engine PID 13444. The `camera_right_down` transport response passed
at 09:20:19 local time with that PID. The following
`capture_right_down` transport call failed by 09:20:22 because
`Get-Process -Id 13444` could no longer find it. The stdout log (SHA-256
`4dd54782df304243365d0cd438d61ebda25e9fb40285d1d610ce28b6f9285d2b`)
records debugger/editor disconnect at 09:20:20 followed by Wwise shutdown
assertions. The stderr log (SHA-256
`c0120e87defe05c625486c5dc15aa264a9c2dbe185c6068e55efec0bfea9e17b`)
contains a shared-texture pointer error before scene readiness. That same
shared-texture error appears in the successful maroon run, so this evidence
does not establish it as the cause of the nearnew exit. No matching Windows
Application/System crash event or WER artifact appeared in the checked
09:18–09:22/09:00–10:00 local windows; absence is not proof of a clean exit.

The exact process exit code, parent/child lifetime, GPU/memory state at exit,
and last successful native command are missing from the old receipt. The
next runner revision must seal action start/end times, owned process IDs and
poll/exit results, and predeclare one collision-free run ID and all outputs.
Only after those checks and rollback preflight pass should a scoped nearnew
triage run be considered. A triage result would not satisfy the required
three-variant, 45-view regression or visual/campaign acceptance.
