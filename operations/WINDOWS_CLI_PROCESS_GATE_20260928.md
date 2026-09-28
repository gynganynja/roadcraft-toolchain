# Windows RoadCraft CLI process-gate repair — 2026-09-28

The real `roadcraft.exe doctor --json` command initially listed its own
`roadcraft.exe` console launcher under `activeAuthoringProcesses`. The native
job and recovery gates share that name-based process enumeration, so an
otherwise idle CLI could reject its own native preflight. A direct Python
invocation did not expose the same launcher. This was a false positive, not
evidence of a running game or editor.

`core._editor_processes` now excludes the current Python PID and traces its
Toolhelp parent chain. A venv Python shim can sit between that process and the
console launcher. When the entrypoint is `roadcraft`, it checks only the
closest `roadcraft.exe` ancestor with Windows
`PROCESS_QUERY_LIMITED_INFORMATION`, suppressing it only when its image is the
same file as the current console entrypoint. A failed image query or
file-identity check leaves it in the blocking list. Concurrent CLI launchers
with that same path also remain listed. This keeps the game's separate
`C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\root\bin\pc\Roadcraft.exe`
path distinct from the toolchain launchers. It does not exempt any
`ModEditor`, `IntegrationStudio`, Blender, Painter, Furnace or package-builder
process.

A Windows integration test starts the installed console entrypoint alongside
a suspended second invocation of that same executable. It requires successful
process enumeration, verifies that the current launcher's PID is absent, and
requires the second launcher's PID to remain listed. The focused
`tests.test_core` module passed in
the dedicated checkout. Real doctor invocations in both the Steam mirror and
dedicated checkout returned `activeAuthoringProcesses: []`,
`processInspectionError: null`, and `warnings: []`. The CLI and test source
SHA-256 values at this check were respectively
`967e1f077a53b4b3ac1b528675046f6bb3e7c88cddd9339861be4aff2a8d849f`
and `9fd68ae0bbda436f53b9d231c84b41dac40ee7b04c804942d221a7a98abb94f8`.

No game, editor, Painter project, package replacement or capture was run.
This removes a self-blocking preflight bug; it does not satisfy the native
capture's separate loaded-scene, PNG-origin, lighting or space gates.
