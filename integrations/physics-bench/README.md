# Physics bench scripts

PowerShell side of `roadcraft bench` (`src/roadcraft/physics_bench.py`); read
[library/physics-bench.md](../../library/physics-bench.md) before using them.

- `launch_editor.ps1`: starts IntegrationStudio on a bench project with its play scenario, window
  hidden, answers the "send errors from past sessions" prompt with Later and writes `launch.json`
  (studio and engine PIDs). Refuses while the game or another editor runs.
- `series_probe.ps1`: read-only time series of the current truck's bodies and wheels through the
  editor's Automation/ExecSsl receiver.
- `input_override.ps1`: pedal, steering, handbrake and gear requests (from the Roamer 105 port).

Editor runs take the PC: get the owner's go-ahead first.
