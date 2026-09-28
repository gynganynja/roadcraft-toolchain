"""Disposable no-save Blender runner with host resource cutoffs."""

import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def available() -> tuple[int, int, int]:
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return (status.ullAvailPhys, status.ullAvailPageFile,
            shutil.disk_usage(Path.cwd().anchor).free)


def main() -> int:
    blender, probe, log = map(Path, sys.argv[1:4])
    if len(sys.argv) != 4 or not blender.is_file() or not probe.is_file():
        raise ValueError("exact Blender, probe and log paths required")
    floors = (int(0.30 * 2**30), 6 * 2**30, 7 * 2**30)
    starting = available()
    if any(a <= floor for a, floor in zip(starting, floors)):
        raise RuntimeError("resource floor failed before Blender launch")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    lows = list(starting)
    reason = "child_exit"
    with log.open("wb") as output:
        child = subprocess.Popen(
            [str(blender), "--background", "--factory-startup",
             "--disable-autoexec", "--threads", "1", "--python-exit-code",
             "1", "--python", str(probe)],
            stdout=output, stderr=subprocess.STDOUT, env=env)
        while child.poll() is None:
            current = available()
            lows = [min(old, now) for old, now in zip(lows, current)]
            if any(now <= floor for now, floor in zip(current, floors)):
                reason = "resource_floor"
            elif time.monotonic() - started > 600:
                reason = "timeout"
            if reason != "child_exit":
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                break
            time.sleep(2)
    code = child.returncode
    print(json.dumps({"reason": reason, "exitCode": code,
                      "elapsedSeconds": round(time.monotonic() - started, 1),
                      "lowFreeGiB": [round(value / 2**30, 2) for value in lows],
                      "log": str(log)}, sort_keys=True), flush=True)
    return code if reason == "child_exit" else 2


if __name__ == "__main__":
    raise SystemExit(main())
