# Quiet launch: native tools without focus theft or dialogs

The owner's main complaint (2026-10) is that SDK tools and the engine take keyboard focus and open
error dialogs while they use the PC (Windows 11 Home). `src/roadcraft/quiet.py` is the one launcher
every native tool should go through:

```python
from roadcraft import quiet
result = quiet.run([exe, *args], cwd=..., timeout=600)          # short tools
with quiet.start([engine, *args], log=log_file) as engine:       # long-lived (the engine)
    ...                                                          # engine.pid, poll(), wait(), kill()
    result = engine.result(timeout=...)
```

`QuietResult` has `returncode`, `stdout`, `stderr`, `timed_out`, `desktop_name`, `pid`,
`leaked_windows` (windows of the child tree seen on the user's desktop: they should always be
empty), `private_windows` (windows on the hidden desktop, where a stuck crash dialog shows up as
class `#32770`), `orphans_killed` (processes the tool left behind, killed when it exited) and
`seconds`. Use `log=<binary file>` instead of in-memory capture for long runs. Off Windows it falls
back to plain `subprocess`.

## What it does and how firmly it is established

| Measure | Why | Grade |
|---|---|---|
| Private desktop `WinSta0\roadcraft-quiet-<pid>` (`desktop="private"`, default), created once per toolchain process | A window on a desktop that is not the input desktop cannot take the user's foreground, so even the engine's ungated MB_TOPMOST/MB_SETFOREGROUND boxes and the SDK CLI tools' modal crash dialogs (see [build-pipeline.md](build-pipeline.md)) stay out of sight | **Build** for test windows: ShowWindow + SetForegroundWindow from a child there returns 0, the window never appears on the user's desktop, the user's foreground is unchanged (`tests/test_quiet.py`). **Open** for the engine: D3D12 on that desktop has not been run |
| Desktop access mask 0x43 (READOBJECTS, CREATEWINDOW, ENUMERATE) on our handle | Children open the desktop through its DACL (our token's default: full access for the same user), not through our handle. Without DESKTOP_CREATEWINDOW, CreateDesktopW fails with the misleading error 8 "not enough memory". DESKTOP_SWITCHDESKTOP is never requested, so the launcher cannot switch the user's screen | **Build** (Windows 11 Home 26200, every other bit tried alone) |
| `CREATE_NO_WINDOW`, `STARTF_USESHOWWINDOW` + SW_HIDE (or `show="noactivate"`), `STARTF_FORCEOFFFEEDBACK` | No console window or Windows Terminal tab for console tools; a GUI child's first ShowWindow is hidden; no busy cursor | **SDK** (Win32 documentation); **Build** for console tools |
| `SetErrorMode(FAILCRITICALERRORS, NOGPFAULTERRORBOX, NOOPENFILEERRORBOX)` in the parent around CreateProcess, then restored | Inherited by the child (we never pass CREATE_DEFAULT_ERROR_MODE): no loader "missing DLL", critical-error or GPF boxes before the tool sets its own mode | **SDK** |
| Job object, KILL_ON_JOB_CLOSE + DIE_ON_UNHANDLED_EXCEPTION | Timeout and `kill` end the whole tree (furnace spawns children; the venv `python.exe` is itself a redirector with a child); a crashing child exits at once instead of waiting on a WER dialog | **Build**: tree kill and orphan kill tests; a real unhandled access violation (native thread at address 0) exits 0xC0000005 in about 0.1 s with no dialog window |
| `S3D_FORCE_SILENT_CRASH_REPORT=1` always; `crash_dump_dir=` sets `S3D_TOOLS_CRASHDUMP_DIR` | Selects the engine's silent error handler instead of its assert/error dialog | **Inferred** (static analysis of ModEditor.exe, `C:\RC_RE\research\focus_dialogs_native.md`; not yet observed in a run). It is the only dialog-suppression variable the research found |
| Explicit handle inheritance (PROC_THREAD_ATTRIBUTE_HANDLE_LIST); stdin is NUL | Concurrent launches do not inherit each other's pipes (a classic cause of reads that never end) | **SDK** |
| Watchdog thread (every 0.2 s, and once more before a timeout kill) | Lists top-level windows of the job's processes on the `Default` desktop and on the private one. Read-only: InternalGetWindowText, never WM_GETTEXT; it never touches user windows | **Build** (positive control: an invisible window on the user's desktop is reported) |
| `priority="below_normal"` (or `"idle"`, `"normal"`) | Priority class passed to CreateProcess; the engine and the ConsoleTre hub run below normal so the owner's work keeps the CPU | **Build** (`tests/test_quiet.py` reads the class back in the child) |
| `pipes=True` | stdin and stdout become pipes the caller drives (`process.stdin`, `process.stdout`, binary, unbuffered) for line protocols such as the ConsoleTre hub helper; stderr goes to `log` or is captured; only the child's pipe ends are inheritable | **Build** (`tests/test_quiet.py`, `tests/test_engine.py`) |
| `breakaway=True` | Tries CREATE_BREAKAWAY_FROM_JOB when the toolchain itself runs in a job; falls back if the parent job refuses | **SDK**; untested here |

## Engine arguments still needed

The launcher cannot switch off the engine's own windows and dialogs; pass these as arguments
(the recommended set from `C:\RC_RE\research\engine_protocol.md` §6.4, nested `--set` paths
**Inferred**): `--set /Config/CONFIG/enableWindow false --editor`,
`--set /Config/Video/WindowMode windowed`, `--set /Config/Debug/AutomationMode true` (or
`ErrorToConsoleOnly`, never all three of Automation/ErrorToConsoleOnly/AutoReport),
`--set /Config/VideoDriverVersionWarning/Show false`, `--set /Config/Video/LowCpuMemoryWarning/Ignored true`,
`--set /Config/Input/ClipCursorDisabled true`,
`--set /Config/Asserts/IntegrationStudio/RunAutomaticallyOnError false`.
`engine.build_command` passes this set (with `ErrorToConsoleOnly` rather than `AutomationMode`, the
default in the earlier ExecSsl runs) and grades each entry; see [headless-bench.md](headless-bench.md).

## Limits

- **Stuck dialogs block invisibly.** A modal dialog on the private desktop waits forever: always
  pass a timeout. `private_windows` (class `#32770`, its title) tells you what it was.
- **The user's desktop is not protected with `desktop="default"`.** A child of a foreground
  process may still take the foreground there; use it only when a tool provably fails on the private
  desktop, and read `leaked_windows`.
- **D3D12 on the private desktop is untested (Open).** The research expects the hardware adapter to
  work on a second WinSta0 desktop and Present to keep returning success when occluded; the first
  engine run must check the adapter in its log and a SaveScreenshot. A non-interactive window station
  (service, Session 0) has no GPU: do not run the launcher from one.
- **Real cursor and keyboard side effects are not contained.** SSL `SetMousePosInViewport` and the
  mouse camera call the real `SetCursorPos`; the profiler's `keybd_event(VK_CAPITAL)` marker injects
  a key into the session. A desktop does not isolate either; avoid triggering them.
- **Closing the handle kills the tree.** When the toolchain process exits, KILL_ON_JOB_CLOSE ends its
  children; `run(..., kill_tree=False)` / `close(kill_tree=False)` releases them on purpose.
- The `private_windows` list also contains the IME and text-input helper windows (`IME`,
  `MSCTFIME UI`, `CiceroUIWndFrame`) that every GUI process creates; they are harmless.
- The crash test shows the protected path is silent; whether this PC would show a WER dialog
  without the protections was not tested, because that would pop a dialog on the owner's screen.

## Switching existing launches over (proposed)

- `jobs.py` `_run_command`: `subprocess.run(..., creationflags=CREATE_NO_WINDOW)` becomes
  `quiet.run(step["command"], cwd=..., env={**os.environ, **step["env"]}, timeout=..., log=log)`;
  map `timed_out` to the existing `timed_out` row (it now kills the whole tree) and record
  `leaked_windows`/`private_windows`/`orphans_killed` in the step receipt.
- `physics_bench.py` `_ps`, `_ps_to_file` and the probe `Popen`: route through `quiet.run` /
  `quiet.start`. `launch_editor.ps1` starts IntegrationStudio with `Start-Process -WindowStyle Hidden`,
  which escapes the job and desktop; the editor launch should move into Python via `quiet.start`, and
  the `taskkill /T` cleanup becomes `kill()`. The editor's own WPF windows (splash, main window,
  about 190 dialog sites) are the largest remaining risk; run it on the private desktop.
- `native_utilities.py` launches no processes (it checks compiled CLS data) and needs no change.

Evidence: `tests/test_quiet.py` (2026-10-13, Windows 11 Home 10.0.26200, Python 3.12.14);
`C:\RC_RE\research\focus_dialogs_native.md`; `C:\RC_RE\research\engine_protocol.md` §6.
