"""Quiet launcher: run native tools without stealing focus or showing dialogs.

library/quiet-launch.md explains use, evidence and limits.  The owner's main
complaint (2026-10) is that SDK tools and the engine take keyboard focus and
open error dialogs while they use the PC.  Every native tool the toolchain runs
should go through ``run`` (short tools) or ``start`` (long-lived processes such
as the engine).  Never use this module to interact with the user's windows: the
watchdog only reads window lists.

Why each measure (grades as in library/README.md):

* Private desktop (``desktop="private"``, default).  ``CreateDesktopW`` creates
  ``WinSta0\\roadcraft-quiet-<pid>`` once per toolchain process; children start
  there through ``STARTUPINFO.lpDesktop``.  A window on a desktop that is not
  the input desktop cannot become the user's foreground window, so even the
  engine's ungated MB_TOPMOST|MB_SETFOREGROUND boxes ("Saber Assert",
  "Need to RELOAD game") and the SDK CLI tools' modal crash dialogs on wrong
  arguments (library/build-pipeline.md) land out of sight.  Grade: Build for
  test windows, ShowWindow and SetForegroundWindow (tests/test_quiet.py);
  Inferred for the engine: the engine has no desktop logic of its own
  (C:\\RC_RE\\research\\focus_dialogs_native.md, static analysis), and D3D12 on
  a second WinSta0 desktop has not been run (Open).  Cost: a stuck dialog
  blocks invisibly, so always give a timeout; ``private_windows`` names it.
* Desktop access mask.  Children do not use our handle: they open the desktop
  through its DACL, which (lpsa=NULL) comes from our token's default DACL and
  grants the same user full access, which covers window creation, hooks for
  IMEs and D3D swap chains.  Our handle asks for DESKTOP_READOBJECTS |
  DESKTOP_ENUMERATE (to list the windows there) | DESKTOP_CREATEWINDOW (0x43):
  without CREATEWINDOW, CreateDesktopW fails with the misleading error 8
  "not enough memory" (Build: measured on Windows 11 Home 26200, each other
  bit tried alone).  The handle is kept open for the life of the process
  because a desktop is destroyed when its last handle closes.
  We never request DESKTOP_SWITCHDESKTOP, so the launcher cannot switch the
  user's screen.
* ``CREATE_NO_WINDOW``: console tools get no console window (on Windows 11 a
  console child of a GUI parent would otherwise open a Windows Terminal tab).
  ``STARTF_USESHOWWINDOW`` with SW_HIDE (or SW_SHOWNOACTIVATE) sets the first
  ShowWindow of a GUI child; ``STARTF_FORCEOFFFEEDBACK`` avoids the busy
  cursor.  Grade: SDK (Win32 documentation); Build for console tools here.
* Error mode.  ``SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX |
  SEM_NOOPENFILEERRORBOX)`` is set in the parent around CreateProcess (it is
  inherited unless CREATE_DEFAULT_ERROR_MODE, which we never pass) and then
  restored.  The engine sets SetErrorMode(3) itself at init (Inferred from the
  static analysis), this covers the loader and the SDK tools before that.
* Job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and
  JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION: a timeout or ``kill`` ends the
  whole tree (furnace and the venv python.exe redirector spawn children), and
  a crashing child exits instead of waiting on a WER dialog.  Grade: Build
  (tests: tree kill, unhandled access violation exits in seconds).  When the
  toolchain process exits, the job handle closes and the tree is killed.
* Environment: ``S3D_FORCE_SILENT_CRASH_REPORT=1`` selects the engine's silent
  error handler instead of its assert/error dialog (static analysis of
  ModEditor.exe, reader 0x143c40980; Inferred until observed in a run).  It is
  the only dialog-suppression variable the research found; ``crash_dump_dir``
  sets ``S3D_TOOLS_CRASHDUMP_DIR`` (dump location only).  Engine dialogs also
  need its own config switches (enableWindow false, Debug.AutomationMode, ...)
  which callers pass as arguments; see library/quiet-launch.md.
* Explicit handle inheritance (PROC_THREAD_ATTRIBUTE_HANDLE_LIST): a child
  inherits only its own stdin/stdout/stderr, so concurrent launches do not
  keep each other's pipes open.

Off Windows ``run``/``start`` fall back to plain subprocess in a new session.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Mapping, Sequence

SILENT_ENV = {"S3D_FORCE_SILENT_CRASH_REPORT": "1"}
WATCH_INTERVAL = 0.2
ORPHAN_GRACE = 0.5


class QuietError(OSError):
    """The quiet launch itself failed (desktop, job or process creation)."""


@dataclass
class QuietResult:
    returncode: int | None
    stdout: str | bytes | None
    stderr: str | bytes | None
    timed_out: bool
    desktop_name: str | None
    pid: int | None = None
    leaked_windows: list[dict[str, Any]] = field(default_factory=list)
    private_windows: list[dict[str, Any]] = field(default_factory=list)
    orphans_killed: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0


def _environment(env: Mapping[str, str] | None, crash_dump_dir: str | os.PathLike | None) -> dict[str, str]:
    merged = dict(os.environ if env is None else env)
    merged.update(SILENT_ENV)
    if crash_dump_dir is not None:
        merged["S3D_TOOLS_CRASHDUMP_DIR"] = os.fspath(crash_dump_dir)
    return merged


def _command_line(argv: Sequence[str] | str) -> str:
    if isinstance(argv, str):
        return argv
    return subprocess.list2cmdline([os.fspath(a) for a in argv])


def _decode(data: bytes | None, text: bool) -> str | bytes | None:
    if data is None or not text:
        return data
    return data.decode("utf-8", errors="replace")


if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)

    CREATE_SUSPENDED = 0x00000004
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    CREATE_NO_WINDOW = 0x08000000
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    STARTF_USESHOWWINDOW = 0x00000001
    STARTF_FORCEOFFFEEDBACK = 0x00000080
    STARTF_USESTDHANDLES = 0x00000100
    SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
    SEM_QUIET = 0x0001 | 0x0002 | 0x8000  # FAILCRITICALERRORS | NOGPFAULTERRORBOX | NOOPENFILEERRORBOX
    JOB_KILL_ON_CLOSE = 0x00002000
    JOB_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
    JobObjectBasicProcessIdList = 3
    JobObjectExtendedLimitInformation = 9
    PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_ENUMERATE = 0x0040
    DESKTOP_CREATEWINDOW = 0x0002
    DESKTOP_CREATE_ACCESS = DESKTOP_READOBJECTS | DESKTOP_CREATEWINDOW | DESKTOP_ENUMERATE  # see docstring
    HANDLE_FLAG_INHERIT = 0x1
    WAIT_OBJECT_0, WAIT_TIMEOUT, INFINITE = 0, 0x102, 0xFFFFFFFF
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5
    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
    OPEN_EXISTING = 3
    INVALID_HANDLE = wintypes.HANDLE(-1).value

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", wintypes.LPVOID),
                    ("bInheritHandle", wintypes.BOOL)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                    ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    def _fn(dll, name, restype, *argtypes):
        f = getattr(dll, name)
        f.restype, f.argtypes = restype, argtypes
        return f

    H, D, B = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
    _CreateProcessW = _fn(_k32, "CreateProcessW", B, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                          ctypes.c_void_p, B, D, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p,
                          ctypes.POINTER(PROCESS_INFORMATION))
    _CloseHandle = _fn(_k32, "CloseHandle", B, H)
    _OpenProcess = _fn(_k32, "OpenProcess", H, D, B, D)
    _QueryFullProcessImageNameW = _fn(_k32, "QueryFullProcessImageNameW", B, H, D, wintypes.LPWSTR,
                                      ctypes.POINTER(D))
    _ResumeThread = _fn(_k32, "ResumeThread", D, H)
    _WaitForSingleObject = _fn(_k32, "WaitForSingleObject", D, H, D)
    _GetExitCodeProcess = _fn(_k32, "GetExitCodeProcess", B, H, ctypes.POINTER(D))
    _TerminateProcess = _fn(_k32, "TerminateProcess", B, H, wintypes.UINT)
    _SetErrorMode = _fn(_k32, "SetErrorMode", wintypes.UINT, wintypes.UINT)
    _CreatePipe = _fn(_k32, "CreatePipe", B, ctypes.POINTER(H), ctypes.POINTER(H),
                      ctypes.POINTER(SECURITY_ATTRIBUTES), D)
    _SetHandleInformation = _fn(_k32, "SetHandleInformation", B, H, D, D)
    _CreateFileW = _fn(_k32, "CreateFileW", H, wintypes.LPCWSTR, D, D, ctypes.POINTER(SECURITY_ATTRIBUTES),
                       D, D, H)
    _GetCurrentProcess = _fn(_k32, "GetCurrentProcess", H)
    _DuplicateHandle = _fn(_k32, "DuplicateHandle", B, H, H, H, ctypes.POINTER(H), D, B, D)
    _CreateJobObjectW = _fn(_k32, "CreateJobObjectW", H, ctypes.c_void_p, wintypes.LPCWSTR)
    _SetInformationJobObject = _fn(_k32, "SetInformationJobObject", B, H, ctypes.c_int, ctypes.c_void_p, D)
    _QueryInformationJobObject = _fn(_k32, "QueryInformationJobObject", B, H, ctypes.c_int, ctypes.c_void_p,
                                     D, ctypes.POINTER(D))
    _AssignProcessToJobObject = _fn(_k32, "AssignProcessToJobObject", B, H, H)
    _TerminateJobObject = _fn(_k32, "TerminateJobObject", B, H, wintypes.UINT)
    _IsProcessInJob = _fn(_k32, "IsProcessInJob", B, H, H, ctypes.POINTER(B))
    _InitializeProcThreadAttributeList = _fn(_k32, "InitializeProcThreadAttributeList", B, ctypes.c_void_p, D, D,
                                             ctypes.POINTER(ctypes.c_size_t))
    _UpdateProcThreadAttribute = _fn(_k32, "UpdateProcThreadAttribute", B, ctypes.c_void_p, D, ctypes.c_size_t,
                                     ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p)
    _DeleteProcThreadAttributeList = _fn(_k32, "DeleteProcThreadAttributeList", None, ctypes.c_void_p)

    _CreateDesktopW = _fn(_u32, "CreateDesktopW", H, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, D, D,
                          ctypes.c_void_p)
    _OpenDesktopW = _fn(_u32, "OpenDesktopW", H, wintypes.LPCWSTR, D, B, D)
    _CloseDesktop = _fn(_u32, "CloseDesktop", B, H)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(B, wintypes.HWND, wintypes.LPARAM)
    _EnumDesktopWindows = _fn(_u32, "EnumDesktopWindows", B, H, _WNDENUMPROC, wintypes.LPARAM)
    _GetWindowThreadProcessId = _fn(_u32, "GetWindowThreadProcessId", D, wintypes.HWND, ctypes.POINTER(D))
    _GetClassNameW = _fn(_u32, "GetClassNameW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    # InternalGetWindowText never sends WM_GETTEXT, so it cannot hang on or disturb a window.
    _InternalGetWindowText = _fn(_u32, "InternalGetWindowText", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR,
                                 ctypes.c_int)
    _IsWindowVisible = _fn(_u32, "IsWindowVisible", B, wintypes.HWND)

    def _fail(what: str) -> QuietError:
        code = ctypes.get_last_error()
        return QuietError(code, f"{what} failed: {ctypes.FormatError(code).strip()} (Win32 error {code})")

    _desktop_lock = threading.Lock()
    _desktop: tuple[int, str] | None = None
    _error_mode_lock = threading.Lock()

    def private_desktop() -> str:
        """Create (once per process) and return ``WinSta0\\roadcraft-quiet-<pid>``."""
        global _desktop
        with _desktop_lock:
            if _desktop is None:
                name = f"roadcraft-quiet-{os.getpid()}"
                handle = _CreateDesktopW(name, None, None, 0, DESKTOP_CREATE_ACCESS, None)
                if not handle:
                    raise _fail("CreateDesktopW")
                _desktop = (handle, f"WinSta0\\{name}")  # kept open: closing it destroys the desktop
            return _desktop[1]

    def desktop_windows(desktop: str | int, pids: set[int] | None = None) -> list[dict[str, Any]]:
        """Top-level windows on a desktop (name or handle), optionally only those of ``pids``.  Read-only."""
        if isinstance(desktop, int):
            handle, owned = desktop, False
        else:
            handle, owned = _OpenDesktopW(desktop, 0, False, DESKTOP_READOBJECTS | DESKTOP_ENUMERATE), True
            if not handle:
                return []
        rows: list[dict[str, Any]] = []

        def visit(hwnd, _lparam):
            pid = D()
            _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pids is None or pid.value in pids:
                title, cls = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(256)
                _InternalGetWindowText(hwnd, title, 512)
                _GetClassNameW(hwnd, cls, 256)
                rows.append({"hwnd": int(hwnd or 0), "pid": pid.value, "title": title.value,
                             "class": cls.value, "visible": bool(_IsWindowVisible(hwnd))})
            return True

        try:
            _EnumDesktopWindows(handle, _WNDENUMPROC(visit), 0)
        finally:
            if owned:
                _CloseDesktop(handle)
        return rows

    def _inheritable_sa() -> SECURITY_ATTRIBUTES:
        return SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)

    def _pipe() -> tuple[int, int]:
        r, w = H(), H()
        sa = _inheritable_sa()
        if not _CreatePipe(ctypes.byref(r), ctypes.byref(w), ctypes.byref(sa), 0):
            raise _fail("CreatePipe")
        _SetHandleInformation(r, HANDLE_FLAG_INHERIT, 0)
        return r.value, w.value

    def _nul() -> int:
        sa = _inheritable_sa()
        h = _CreateFileW("NUL", GENERIC_READ | GENERIC_WRITE, 3, ctypes.byref(sa), OPEN_EXISTING, 0, None)
        if h == INVALID_HANDLE or not h:
            raise _fail("CreateFileW(NUL)")
        return h

    def _inheritable_copy(fileobj: BinaryIO) -> int:
        source = msvcrt.get_osfhandle(fileobj.fileno())
        dup = H()
        if not _DuplicateHandle(_GetCurrentProcess(), source, _GetCurrentProcess(), ctypes.byref(dup), 0, True, 2):
            raise _fail("DuplicateHandle")  # 2 = DUPLICATE_SAME_ACCESS
        return dup.value

    def _in_job() -> bool:
        result = B()
        return bool(_IsProcessInJob(_GetCurrentProcess(), None, ctypes.byref(result))) and bool(result.value)

    def _new_job() -> int:
        job = _CreateJobObjectW(None, None)
        if not job:
            raise _fail("CreateJobObjectW")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_KILL_ON_CLOSE | JOB_DIE_ON_UNHANDLED_EXCEPTION
        if not _SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info),
                                        ctypes.sizeof(info)):
            error = _fail("SetInformationJobObject")
            _CloseHandle(job)
            raise error
        return job

    def _job_pids(job: int) -> set[int]:
        count = 1024

        class LIST(ctypes.Structure):
            _fields_ = [("Assigned", D), ("InList", D), ("Ids", ctypes.c_size_t * count)]

        data = LIST()
        if not _QueryInformationJobObject(job, JobObjectBasicProcessIdList, ctypes.byref(data),
                                          ctypes.sizeof(data), None):
            return set()
        return {int(data.Ids[i]) for i in range(min(data.InList, count))}

    def _process_row(pid: int) -> dict[str, Any]:
        image = ""
        handle = _OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            buf, size = ctypes.create_unicode_buffer(1024), D(1024)
            if _QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                image = os.path.basename(buf.value)
            _CloseHandle(handle)
        return {"pid": pid, "image": image}

    def _create(cmdline: str, cwd, env: dict[str, str], flags: int, si: STARTUPINFOEXW) -> PROCESS_INFORMATION:
        block = "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())) + "\0"
        env_buf = (ctypes.c_wchar * len(block)).from_buffer_copy(block.encode("utf-16-le"))
        cmd_buf = ctypes.create_unicode_buffer(cmdline)
        pi = PROCESS_INFORMATION()
        with _error_mode_lock:
            previous = _SetErrorMode(SEM_QUIET)  # returns the old mode; keep its other bits too
            _SetErrorMode(previous | SEM_QUIET)
            try:
                ok = _CreateProcessW(None, cmd_buf, None, None, True, flags, env_buf,
                                     None if cwd is None else os.fspath(cwd), ctypes.byref(si), ctypes.byref(pi))
                error = ctypes.get_last_error()
            finally:
                _SetErrorMode(previous)
        if not ok:
            ctypes.set_last_error(error)
            raise _fail(f"CreateProcessW({cmdline[:200]})")
        return pi

    class QuietProcess:
        """A quietly started process tree (Popen-like: ``pid``, ``poll``, ``wait``, ``kill``, ``result``)."""

        def __init__(self, argv, *, cwd=None, env=None, desktop="private", capture=True, log=None,
                     show="hide", text=True, watch=True, crash_dump_dir=None, breakaway=False):
            if desktop not in ("private", "default"):
                raise ValueError("desktop must be 'private' or 'default'")
            if show not in ("hide", "noactivate"):
                raise ValueError("show must be 'hide' or 'noactivate'")
            self.args, self.text = argv, text
            self.desktop_name = private_desktop() if desktop == "private" else None
            self._started = time.monotonic()
            self._stdout: list[bytes] = []
            self._stderr: list[bytes] = []
            self._readers: list[threading.Thread] = []
            self._capture = capture and log is None
            self._closed = False
            self._done = threading.Event()
            self._leaked: dict[int, dict[str, Any]] = {}
            self._private: dict[int, dict[str, Any]] = {}
            self.returncode: int | None = None
            self.orphans_killed: list[dict[str, Any]] = []

            child_handles: list[int] = []
            parent_reads: list[int] = []
            try:
                stdin = _nul()
                child_handles.append(stdin)
                if log is not None:
                    out = err = _inheritable_copy(log)
                    child_handles.append(out)
                elif capture:
                    r1, out = _pipe()
                    r2, err = _pipe()
                    parent_reads += [r1, r2]
                    child_handles += [out, err]
                else:
                    out = err = stdin
                si = STARTUPINFOEXW()
                si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
                si.StartupInfo.dwFlags = STARTF_USESHOWWINDOW | STARTF_USESTDHANDLES | STARTF_FORCEOFFFEEDBACK
                si.StartupInfo.wShowWindow = SW_HIDE if show == "hide" else SW_SHOWNOACTIVATE
                desktop_buf = ctypes.create_unicode_buffer(self.desktop_name) if self.desktop_name else None
                si.StartupInfo.lpDesktop = ctypes.cast(desktop_buf, wintypes.LPWSTR) if desktop_buf else None
                si.StartupInfo.hStdInput, si.StartupInfo.hStdOutput, si.StartupInfo.hStdError = stdin, out, err
                inherit = sorted(set(child_handles))
                handles = (H * len(inherit))(*inherit)
                size = ctypes.c_size_t()
                _InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
                attrs = ctypes.create_string_buffer(size.value)
                if not _InitializeProcThreadAttributeList(attrs, 1, 0, ctypes.byref(size)):
                    raise _fail("InitializeProcThreadAttributeList")
                try:
                    if not _UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles,
                                                      ctypes.sizeof(handles), None, None):
                        raise _fail("UpdateProcThreadAttribute")
                    si.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
                    self._job = _new_job()
                    flags = (CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW
                             | EXTENDED_STARTUPINFO_PRESENT)
                    cmdline, merged = _command_line(argv), _environment(env, crash_dump_dir)
                    pi = None
                    if breakaway and _in_job():
                        try:  # only succeeds if the parent's job allows breakaway
                            pi = _create(cmdline, cwd, merged, flags | CREATE_BREAKAWAY_FROM_JOB, si)
                        except QuietError as exc:
                            if exc.errno != ERROR_ACCESS_DENIED:
                                raise
                    if pi is None:
                        pi = _create(cmdline, cwd, merged, flags, si)
                finally:
                    _DeleteProcThreadAttributeList(attrs)
            except BaseException:
                for h in child_handles + parent_reads:
                    _CloseHandle(h)
                if getattr(self, "_job", None):
                    _CloseHandle(self._job)
                raise
            for h in child_handles:
                _CloseHandle(h)
            self.pid, self._process = pi.dwProcessId, pi.hProcess
            if not _AssignProcessToJobObject(self._job, pi.hProcess):
                error = _fail("AssignProcessToJobObject")
                _TerminateProcess(pi.hProcess, 1)
                for h in (pi.hThread, pi.hProcess, self._job, *parent_reads):
                    _CloseHandle(h)
                raise error
            _ResumeThread(pi.hThread)
            _CloseHandle(pi.hThread)
            for handle, sink in zip(parent_reads, (self._stdout, self._stderr)):
                stream = open(msvcrt.open_osfhandle(handle, os.O_RDONLY), "rb", buffering=0)
                thread = threading.Thread(target=self._drain, args=(stream, sink), daemon=True)
                thread.start()
                self._readers.append(thread)
            self._watcher = None
            if watch:
                self._watcher = threading.Thread(target=self._watch, daemon=True)
                self._watcher.start()

        @staticmethod
        def _drain(stream, sink: list[bytes]) -> None:
            with stream:
                while chunk := stream.read(65536):
                    sink.append(chunk)

        def pids(self) -> set[int]:
            """Process ids currently in this launch's job (the whole tree)."""
            return set() if self._closed else _job_pids(self._job)

        def sweep(self) -> None:
            """Record windows of the tree on the user's desktop (leaks) and on the private desktop."""
            if self._closed:
                return
            pids = self.pids()
            if not pids:
                return
            for row in desktop_windows("Default", pids):
                self._leaked.setdefault(row["hwnd"], row)
            if self.desktop_name and _desktop:
                for row in desktop_windows(_desktop[0], pids):
                    self._private.setdefault(row["hwnd"], row)

        def _watch(self) -> None:
            while not self._done.wait(WATCH_INTERVAL):
                try:
                    self.sweep()
                except OSError:
                    pass

        @property
        def leaked_windows(self) -> list[dict[str, Any]]:
            return list(self._leaked.values())

        @property
        def private_windows(self) -> list[dict[str, Any]]:
            return list(self._private.values())

        def poll(self) -> int | None:
            if self.returncode is None and _WaitForSingleObject(self._process, 0) == WAIT_OBJECT_0:
                code = D()
                _GetExitCodeProcess(self._process, ctypes.byref(code))
                self.returncode = code.value
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.poll() is None:
                remaining = 0.1 if deadline is None else min(0.1, deadline - time.monotonic())
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(self.args, timeout)
                _WaitForSingleObject(self._process, max(1, int(remaining * 1000)))
            return self.returncode

        def kill(self, exit_code: int = 1) -> None:
            """Terminate the whole tree (the job), not only the first process."""
            if not self._closed:
                _TerminateJobObject(self._job, exit_code)

        terminate = kill

        def close(self, kill_tree: bool = True) -> None:
            """Stop watching; with ``kill_tree`` end any processes left in the job, then release handles."""
            if self._closed:
                return
            self._done.set()
            if self._watcher:
                self._watcher.join(2)
            if kill_tree:
                if self.poll() is not None:
                    # A console child's conhost.exe leaves on its own shortly after; give the tree a moment.
                    deadline = time.monotonic() + ORPHAN_GRACE
                    while (left := self.pids() - {self.pid}) and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.orphans_killed = [row for row in map(_process_row, sorted(left))
                                           if row["image"].lower() != "conhost.exe"]
                _TerminateJobObject(self._job, 1)
            else:  # keep the tree alive past the job handle: drop KILL_ON_JOB_CLOSE first
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_DIE_ON_UNHANDLED_EXCEPTION
                _SetInformationJobObject(self._job, JobObjectExtendedLimitInformation, ctypes.byref(info),
                                         ctypes.sizeof(info))
            for thread in self._readers:
                thread.join(5)
            self._closed = True
            _CloseHandle(self._job)  # KILL_ON_JOB_CLOSE ends whatever is left
            _CloseHandle(self._process)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.kill()
            self.close()

        def result(self, timeout: float | None = None, *, kill_tree: bool = True) -> QuietResult:
            """Wait (killing the tree on timeout), close, and return a QuietResult."""
            timed_out = False
            try:
                self.wait(timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.sweep()  # a hung dialog is still on screen now: record it before killing
                self.kill()
                self.wait(10)
            self.sweep()  # leftover children may still own windows
            self.close(kill_tree=kill_tree)
            out = b"".join(self._stdout) if self._capture else None
            err = b"".join(self._stderr) if self._capture else None
            return QuietResult(self.returncode, _decode(out, self.text), _decode(err, self.text), timed_out,
                               self.desktop_name or "inherited", self.pid, self.leaked_windows,
                               self.private_windows, self.orphans_killed,
                               round(time.monotonic() - self._started, 3))

else:  # POSIX fallback: plain subprocess, own session so kill reaches the tree.
    import signal

    def private_desktop() -> str:
        raise QuietError("private desktops exist only on Windows")

    def desktop_windows(desktop, pids=None) -> list[dict[str, Any]]:
        return []

    class QuietProcess:  # type: ignore[no-redef]
        def __init__(self, argv, *, cwd=None, env=None, desktop="private", capture=True, log=None,
                     show="hide", text=True, watch=True, crash_dump_dir=None, breakaway=False):
            self.args, self.text, self._started = argv, text, time.monotonic()
            self._capture = capture and log is None
            out = log if log is not None else (subprocess.PIPE if capture else subprocess.DEVNULL)
            self._p = subprocess.Popen(argv, cwd=cwd, env=_environment(env, crash_dump_dir),
                                       stdin=subprocess.DEVNULL, stdout=out,
                                       stderr=subprocess.STDOUT if log is not None else out,
                                       start_new_session=True, shell=isinstance(argv, str))
            self.pid, self.desktop_name = self._p.pid, None
            self.leaked_windows, self.private_windows, self.orphans_killed = [], [], []

        @property
        def returncode(self):
            return self._p.returncode

        def pids(self) -> set[int]:
            return {self.pid} if self._p.poll() is None else set()

        def sweep(self) -> None:
            pass

        def poll(self):
            return self._p.poll()

        def wait(self, timeout=None):
            return self._p.wait(timeout)

        def kill(self, exit_code: int = 1) -> None:
            try:
                os.killpg(self._p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        terminate = kill

        def close(self, kill_tree: bool = True) -> None:
            if kill_tree:
                self.kill()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.kill()
            self._p.wait()

        def result(self, timeout=None, *, kill_tree=True) -> QuietResult:
            timed_out = False
            try:
                out, err = self._p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.kill()
                out, err = self._p.communicate()
            self.close(kill_tree)
            out, err = (out, err) if self._capture else (None, None)
            return QuietResult(self._p.returncode, _decode(out, self.text), _decode(err, self.text), timed_out,
                               None, self.pid, [], [], [], round(time.monotonic() - self._started, 3))


def start(argv: Sequence[str] | str, *, cwd=None, env: Mapping[str, str] | None = None,
          desktop: str = "private", capture: bool = True, log: BinaryIO | None = None, show: str = "hide",
          text: bool = True, watch: bool = True, crash_dump_dir=None, breakaway: bool = False) -> QuietProcess:
    """Start a process tree quietly and return its handle (for long-lived processes such as the engine).

    ``log``: an open binary file receiving stdout and stderr (prefer this over ``capture`` for long runs).
    ``env``: the full environment (default: os.environ); the dialog-suppression variables are added.
    ``breakaway``: try CREATE_BREAKAWAY_FROM_JOB when this process is in a job (falls back if denied).
    Use as a context manager, or call ``result()``/``close()``: closing kills what is left of the tree.
    """
    return QuietProcess(argv, cwd=cwd, env=env, desktop=desktop, capture=capture, log=log, show=show,
                        text=text, watch=watch, crash_dump_dir=crash_dump_dir, breakaway=breakaway)


def run(argv: Sequence[str] | str, *, cwd=None, env: Mapping[str, str] | None = None,
        timeout: float | None = None, desktop: str = "private", capture: bool = True,
        log: BinaryIO | None = None, show: str = "hide", text: bool = True, watch: bool = True,
        crash_dump_dir=None, breakaway: bool = False, kill_tree: bool = True) -> QuietResult:
    """Run to completion; on timeout kill the whole tree and set ``timed_out``.

    With ``kill_tree`` (default) processes the tool left behind are killed when it exits and listed in
    ``orphans_killed``.  ``leaked_windows`` lists windows of the tree seen on the user's desktop;
    ``private_windows`` those on the private desktop (a hung crash dialog shows up there).
    """
    process = start(argv, cwd=cwd, env=env, desktop=desktop, capture=capture, log=log, show=show,
                    text=text, watch=watch, crash_dump_dir=crash_dump_dir, breakaway=breakaway)
    return process.result(timeout, kill_tree=kill_tree)
