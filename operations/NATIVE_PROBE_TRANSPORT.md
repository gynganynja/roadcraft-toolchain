# Scratch native runtime probe transport

`operations/probes/native_runtime_probe.ps1` is a separate, read-only
Automation/ExecSsl helper for the five exact SSL fragments in
`operations/probes/`. It has no arbitrary-script argument, no screenshot mode,
and no package-install path. The helper and Python verifier pin the five
fragment hashes, three validation-scene source hashes, the installed editor
executable hash, and both SDK transport DLL hashes. A changed byte fails
preflight. The helper derives the SDK root from `local/machine.json` or
`ROADCRAFT_CONFIG`.

Offline preflight is the default:

```powershell
$env:PYTHONPATH = 'C:\RC\RoadCraftDev\toolchain\src'
& 'C:\Users\Gynga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m roadcraft.native_probe_transport --kind weather_state --variant maroon
```

For a future disposable, already-open editor session, the explicit execution
shape is:

```powershell
& 'C:\Users\Gynga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m roadcraft.native_probe_transport --kind weather_state --variant maroon --execute --engine-pid <exact-editor-pid> --output C:\RC\RoadCraftDev\toolchain\local\native-probes\weather-maroon-001.json
```

Execution checks the PID's executable path, creation time, and pinned hash;
finds one Automation/ExecSsl listener in that PID's ConsoleTre client; verifies
its channel/workspace is unambiguous; and sends the selected exact fragment.
It hashes the exact in-memory SSL bytes before send and rejects raw replies
larger than 64 KiB before allocating for them.
It records the full request script and hash, GUID, process identity, workspace,
request/response UTC times, raw response bytes, decoded text, helper hash,
machine config hash, scene-source hash, and editor hash. The Python verifier
also checks the two SDK transport DLL hashes. Execution receipts must be new
plain JSON files directly under the ignored `local/native-probes/` directory;
the runner checks that the directory and its ancestors are not reparse points.
The Python verifier rejects failed transport, malformed bytes, compile-error
text, missing fields, non-finite values, wrong markers, inconsistent timestamps,
and altered pinned inputs or response bytes. It does not independently
authenticate who created a receipt or establish its freshness. Each
fragment is run separately so one failed native method does not suppress the
others. A new receipt path is required; no existing evidence is overwritten.

This helper was **not** executed against the editor when added. Its PowerShell
preflight and synthetic verifier tests passed offline. The scene pin describes
on-disk source bytes, **not** a verified loaded scene. The new `GetLevelName`
candidate may return a level label, but neither its signature nor its relation
to the loaded validation xscene has been tested. A matching level label still
does not prove the loaded scene bytes. Ordinary method-smoke receipts are labeled
`PARTIAL_RESPONSE_CONSISTENCY_VERIFIED`; the level-name diagnostic uses
`LEVEL_NAME_RESPONSE_CONSISTENCY_VERIFIED`. Both remain
`pairProtocolEligible: false`. The weather-preset name, ambient RGB, exposure,
tonemap, renderer mode, complete local-light roster, and fresh pre-screenshot
linkage remain unobserved. Do not feed these probe receipts to the matched
baseline/candidate gate.

## Complete offline matrix, 2026-09-28

At `2026-09-28T04:55:41Z`, all 15 combinations of the five allowlisted
fragments and three validation variants returned `PREFLIGHT_VERIFIED` with
`transportSent: false` and `pairProtocolEligible: false`. Each call used
`python -B -m roadcraft.native_probe_transport --kind KIND --variant VARIANT`
from the Steam source mirror, with `PYTHONPATH` set to that mirror's `src`.

| Fragment | Maroon | Nearnew | Worn |
| --- | --- | --- | --- |
| `weather_state` | passed | passed | passed |
| `camera_up` | passed | passed | passed |
| `sun_direction` | passed | passed | passed |
| `daytime` | passed | passed | passed |
| `level_name` | passed | passed | passed |

The same 15-command matrix passed from the dedicated checkout at
`2026-09-28T05:04Z`, with its `src` on `PYTHONPATH`. The dedicated checkout's
Python module, PowerShell helper, and ignored machine config matched the
hashes below. This is 15 passing combinations in each checkout, not 30
independent runtime method results.

The checked Python module SHA-256 was
`1b2e8f925279ea3ae4e9904817ac721fe4bbb36edb0f8d2aa7929569b2b9ca1e`;
the PowerShell helper SHA-256 was
`6f2f16c6781773ea6f68be4da6aaa4123b25b1b363200fcf67e69bbcf730e3f9`.
The ignored machine config matched SHA-256
`5c442e89f2e23fa7528da05e26b05f02b97f22a1c139535483a8d08d931e677d`
at the check. The interpreter was Python 3.12.14 and the helper used
PowerShell 7.6.5. The installed accepted PAK still matched
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.
No `--execute` flag, engine PID, output path, or installed-package swap was
supplied. This matrix verifies current pinned input availability and offline
transport preparation only; it does not prove the fragments compile or return
values in an editor session. Recheck pins and process state before any native
method smoke.
