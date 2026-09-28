# Scratch native runtime probe transport

`operations/probes/native_runtime_probe.ps1` is a separate, read-only
Automation/ExecSsl helper for the four exact SSL fragments in
`operations/probes/`. It has no arbitrary-script argument, no screenshot mode,
and no package-install path. The helper and Python verifier pin the four
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
on-disk source bytes, **not** a verified loaded scene; the helper has no native
scene getter. Even a consistent method-smoke receipt is labeled
`PARTIAL_RESPONSE_CONSISTENCY_VERIFIED` and remains
`pairProtocolEligible: false`. The weather-preset name, ambient RGB, exposure,
tonemap, renderer mode, complete local-light roster, and fresh pre-screenshot
linkage remain unobserved. Do not feed these probe receipts to the matched
baseline/candidate gate.
