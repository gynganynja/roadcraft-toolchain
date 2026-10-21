"""Keep the editor engine silent: mute its Windows audio sessions (per-app Volume Mixer mute, level 0).

The SDK editor has no mute or volume setting (its config's only audio key is ``SoundPerformancePreset``;
the debug-variable table has no volume control), so the bench mutes the process from outside through Core
Audio (``data/mute_audio.ps1``). Windows keeps a program's mixer level, so this also quietens later editor
launches. Owner request 2026-10-20: "mute the sound of the mod editor and make it always be muted".

    python -m roadcraft.audio_mute [--name "Roadcraft ModEditor"] [--pid N ...] [--wait 90]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

SCRIPT = Path(__file__).with_name("data") / "mute_audio.ps1"
EDITOR_PROCESS = "Roadcraft ModEditor"


def command(name: str | None = EDITOR_PROCESS, pids: Iterable[int] = (), wait: float = 90) -> list[str]:
    argv = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-WaitSeconds", str(int(wait))]
    if name:
        argv += ["-Name", name]
    pid_list = [str(int(p)) for p in pids]
    if pid_list:
        argv += ["-Pids", ",".join(pid_list)]
    return argv


def start_background(name: str | None = EDITOR_PROCESS, pids: Iterable[int] = (), wait: float = 120,
                     log: Path | None = None) -> subprocess.Popen | None:
    """Start the muter without waiting (it watches for the process's audio sessions for ``wait`` seconds).
    Returns None off Windows. Never raises: a failed mute must not fail a bench run."""
    if sys.platform != "win32":
        return None
    try:
        out = open(log, "ab") if log else subprocess.DEVNULL
        return subprocess.Popen(command(name, pids, wait), stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roadcraft.audio_mute", description=__doc__.splitlines()[0])
    ap.add_argument("--name", default=EDITOR_PROCESS, help="process name without .exe ('' for none)")
    ap.add_argument("--pid", type=int, action="append", default=[])
    ap.add_argument("--wait", type=float, default=10, help="seconds to keep watching for new sessions")
    args = ap.parse_args(argv)
    return subprocess.call(command(args.name or None, args.pid, args.wait), stdin=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
