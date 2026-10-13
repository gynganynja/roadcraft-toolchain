"""Quiet launcher: output, timeout tree kill, private desktop, foreground and crash dialogs.

Only the test interpreter itself is launched (never an SDK or RoadCraft executable).
The window tests create a small STATIC window in a child Python on the private desktop;
the positive control on the user's desktop uses an invisible window so nothing appears.
"""
import os
import subprocess
import sys
import time
import unittest
import uuid

from roadcraft import quiet

PY = sys.executable
WINDOWS = sys.platform == "win32"

WINDOW_CHILD = r"""
import ctypes, sys, time
from ctypes import wintypes
u = ctypes.WinDLL('user32', use_last_error=True)
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u.SetForegroundWindow.argtypes = [wintypes.HWND]
title, visible, hold = sys.argv[1], sys.argv[2] == '1', float(sys.argv[3])
style = 0x00CF0000 | (0x10000000 if visible else 0)   # WS_OVERLAPPEDWINDOW [| WS_VISIBLE]
hwnd = u.CreateWindowExW(0, 'STATIC', title, style, 100, 100, 320, 200, None, None, None, None)
print('hwnd', hwnd or 0, ctypes.get_last_error(), flush=True)
if visible:
    u.ShowWindow(hwnd, 5)                               # SW_SHOW
    print('foreground', u.SetForegroundWindow(hwnd), flush=True)
msg = wintypes.MSG()
end = time.time() + hold
while time.time() < end:
    while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        u.TranslateMessage(ctypes.byref(msg)); u.DispatchMessageW(ctypes.byref(msg))
    if visible:
        u.SetForegroundWindow(hwnd)
    time.sleep(0.05)
"""

# ctypes.string_at(0) is no good here: ctypes wraps foreign calls in SEH and raises OSError.
# A native thread started at address 0 faults outside any handler: a real unhandled exception.
CRASH_CHILD = r"""
import ctypes, time
k = ctypes.WinDLL('kernel32')
k.CreateThread.restype = ctypes.c_void_p
k.CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_uint32, ctypes.c_void_p]
k.CreateThread(None, 0, None, None, 0, None)
time.sleep(30)
"""


def _alive(pid):
    from roadcraft.jobs import _pid_alive
    return _pid_alive(pid)


class ConsoleTests(unittest.TestCase):
    def test_output_and_returncode(self):
        code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
        result = quiet.run([PY, "-c", code], timeout=60)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout.strip(), "out")
        self.assertEqual(result.stderr.strip(), "err")
        self.assertFalse(result.timed_out)
        self.assertEqual(result.leaked_windows, [])

    def test_silent_crash_environment_added(self):
        code = "import os; print(os.environ.get('S3D_FORCE_SILENT_CRASH_REPORT'))"
        result = quiet.run([PY, "-c", code], timeout=60, env={**os.environ, "S3D_FORCE_SILENT_CRASH_REPORT": "0"})
        self.assertEqual(result.stdout.strip(), "1")

    def test_timeout_kills_whole_tree(self):
        # The venv python.exe is a redirector, so the printed pid is a grandchild of the launch.
        code = "import os, time; print(os.getpid(), flush=True); time.sleep(60)"
        started = time.monotonic()
        result = quiet.run([PY, "-c", code], timeout=3)
        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - started, 20)
        self.assertNotEqual(result.returncode, 0)
        inner = int(result.stdout.split()[0])
        time.sleep(0.5)
        self.assertIsNot(_alive(inner), True)

    def test_leftover_children_are_killed_and_reported(self):
        if not WINDOWS:
            self.skipTest("job objects are Windows-only")
        code = ("import subprocess, sys; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
                "print(p.pid)")
        result = quiet.run([PY, "-c", code], timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.orphans_killed)
        time.sleep(0.5)
        self.assertIsNot(_alive(int(result.stdout.split()[0])), True)

    def test_log_file_receives_both_streams(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "step.log")
            with open(path, "wb") as log:
                result = quiet.run([PY, "-c", "import sys; print('a'); print('b', file=sys.stderr)"],
                                   timeout=60, log=log)
            self.assertIsNone(result.stdout)
            with open(path, "rb") as stream:
                self.assertEqual(sorted(stream.read().split()), [b"a", b"b"])

    def test_pipes_line_protocol_and_priority(self):
        code = ("import sys, os\n"
                "for line in sys.stdin:\n"
                "    sys.stdout.write(line.upper()); sys.stdout.flush()\n"
                "    if line.strip() == 'priority':\n"
                "        import ctypes\n"
                "        k = ctypes.WinDLL('kernel32') if os.name == 'nt' else None\n"
                "        if k:\n"
                "            k.GetCurrentProcess.restype = ctypes.c_void_p\n"
                "            k.GetPriorityClass.argtypes = [ctypes.c_void_p]\n"
                "        value = k.GetPriorityClass(k.GetCurrentProcess()) if k else os.nice(0)\n"
                "        sys.stdout.write(f'{value}\\n'); sys.stdout.flush()\n")
        process = quiet.start([PY, "-c", code], pipes=True, priority="below_normal")
        try:
            process.stdin.write(b"hello\npriority\n")
            process.stdin.flush()
            data = b""
            while data.count(b"\n") < 3:
                chunk = process.stdout.read(1)
                if not chunk:
                    break
                data += chunk
            lines = data.decode().split()
            self.assertEqual(lines[:2], ["HELLO", "PRIORITY"])
            if WINDOWS:  # the venv redirector's child inherits the class
                self.assertEqual(int(lines[2]), quiet.PRIORITY_CLASSES["below_normal"])
            process.stdin.close()
            self.assertEqual(process.wait(20), 0)
        finally:
            process.close()
        with self.assertRaises(ValueError):
            quiet.start([PY, "-c", "pass"], priority="realtime")

    def test_start_handle_poll_wait_kill(self):
        process = quiet.start([PY, "-c", "import time; time.sleep(60)"])
        try:
            self.assertIsNone(process.poll())
            with self.assertRaises(subprocess.TimeoutExpired):
                process.wait(0.5)
            process.kill()
            self.assertIsNotNone(process.wait(10))
        finally:
            process.close()


@unittest.skipUnless(WINDOWS, "desktops, foreground and WER are Windows-only")
class WindowsQuietTests(unittest.TestCase):
    def _hold_window(self, title, desktop, visible, hold=3.0):
        process = quiet.start([PY, "-c", WINDOW_CHILD, title, "1" if visible else "0", str(hold)], desktop=desktop)
        return process

    def _wait_for(self, predicate, seconds=20):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.1)
        return False

    def test_private_desktop_window_stays_off_user_desktop(self):
        title = f"rc-quiet-test-{uuid.uuid4().hex[:8]}"
        process = self._hold_window(title, "private", visible=True)
        try:
            # Non-vacuous: the window really exists, on the private desktop.
            seen = self._wait_for(lambda: (process.sweep(), any(w["title"] == title
                                                                for w in process.private_windows))[1])
            self.assertTrue(seen, "child window never appeared on the private desktop")
            on_default = [w for w in quiet.desktop_windows("Default") if w["title"] == title]
            self.assertEqual(on_default, [])
        finally:
            result = process.result(30)
        self.assertEqual(result.leaked_windows, [])
        self.assertTrue(result.desktop_name.startswith("WinSta0\\roadcraft-quiet-"))
        self.assertIn("foreground", result.stdout)

    def test_watchdog_reports_window_on_user_desktop(self):
        # Positive control with an invisible window: the watchdog must see it on the user's desktop.
        title = f"rc-quiet-control-{uuid.uuid4().hex[:8]}"
        result = quiet.run([PY, "-c", WINDOW_CHILD, title, "0", "2"], desktop="default", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(title, [w["title"] for w in result.leaked_windows])
        self.assertFalse(any(w["visible"] for w in result.leaked_windows if w["title"] == title))

    def test_set_foreground_window_does_not_take_user_foreground(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = wintypes.HWND

        def foreground_pid():
            hwnd = user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            if hwnd:
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value

        before = user32.GetForegroundWindow()
        title = f"rc-quiet-fg-{uuid.uuid4().hex[:8]}"
        process = self._hold_window(title, "private", visible=True, hold=3.0)
        stolen = []
        try:
            end = time.monotonic() + 3.0
            while time.monotonic() < end:
                pids = process.pids()
                if pids and foreground_pid() in pids:
                    stolen.append(foreground_pid())
                time.sleep(0.05)
        finally:
            result = process.result(30)
        self.assertIn("foreground", result.stdout, result.stderr)
        self.assertEqual(stolen, [])
        after = user32.GetForegroundWindow()
        # The user may switch windows during the test; only the child must never own the foreground.
        if after != before:
            self.assertNotIn(title, [w["title"] for w in quiet.desktop_windows("Default") if w["hwnd"] == after])

    def test_unhandled_access_violation_exits_without_dialog(self):
        started = time.monotonic()
        result = quiet.run([PY, "-c", CRASH_CHILD], timeout=25)
        self.assertFalse(result.timed_out, "child hung, probably on a crash dialog")
        self.assertLess(time.monotonic() - started, 15)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.leaked_windows, [])
        self.assertFalse([w for w in result.private_windows if w["class"] == "#32770"], result.private_windows)


if __name__ == "__main__":
    unittest.main()
