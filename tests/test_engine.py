"""Windowless engine session (roadcraft.engine) against a fake engine; nothing of RoadCraft is launched.

The hub tests build integrations/consoletre-hub (dotnet) and run the SDK's own Saber.ConsoleTre
ConsoleServer/ConsoleClient from the SDK folder; tests/fake_engine.py joins it from the engine's side.
They skip when dotnet or the SDK assemblies are missing.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from roadcraft import engine as eng
from roadcraft import quiet

HERE = Path(__file__).resolve().parent
FAKE = HERE / "fake_engine.py"
SDK = Path(os.environ.get("ROADCRAFT_SDK_EDITOR_DIR") or eng.default_sdk_editor_dir())
HAVE_HUB = (sys.platform == "win32" and shutil.which("dotnet") is not None
            and (SDK / "Saber.ConsoleTre.dll").is_file() and (SDK / "Saber.Json.dll").is_file())
IDLE = lambda: ([], None)  # noqa: E731 - process check: nothing running


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        return False
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102  # WAIT_TIMEOUT: still running
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.layout = eng.plan_layout(self.tmp / "run", pak=self.tmp / "cand.pak", game_root=self.tmp / "game")

    def test_windowless_flags_in_editor_order(self):
        argv, sets = eng.build_command("C:/x/Roadcraft ModEditor.exe", channel=4242, layout=self.layout,
                                       adapter_id=1, width=800, height=600, timestep=1 / 60)
        self.assertEqual(argv[1], "--startup")
        joined = " ".join(argv)
        for fragment in ("--set /Config/Video/WindowSizeY 600 --set /Config/Video/WindowSizeX 800 "
                         "--set /Config/Debug/ConsoleChannel 4242 --set /Config/CONFIG/enableWindow false --editor "
                         "--cfg ../../config/editor/editor.cfg --set /Config/Video/API dx12 "
                         "--set /Config/Video/AdapterId 1",
                         f"--set /Config/ResourceManager/ModDirs/local {self.layout.mods.as_posix()}",
                         f"--set /Config/ResourceManager/ModDirs/pros {self.layout.mods_pros.as_posix()}",
                         f"--set /Config/external/ModsSourceLocal {self.layout.mods_source.as_posix()}",
                         "--set /Config/EDITOR/FPS/FIXED/playModeFixedFpsValue 60",
                         "--dont_send_crashdump --crashdump_directory"):
            self.assertIn(fragment, joined)
        for s in sets:  # every --set is documented and graded
            self.assertIn(s.grade, ("SDK", "Inferred"))
            self.assertTrue(s.why)
            self.assertIn(f"--set /Config/{s.path} {s.value}", joined)
        self.assertNotIn("AutomationMode", joined)  # prior ExecSsl runs used the default

    def test_run_root_never_in_owner_folders(self):
        game = self.tmp / "game"
        for bad in (game / "root" / "mods" / "x", game / "root" / "bin" / "pc", game):
            with self.assertRaises(eng.EngineRefused):
                eng.plan_layout(bad, game_root=game)
        with self.assertRaises(eng.EngineRefused):
            eng.plan_layout("relative/run", game_root=game)
        with self.assertRaises(eng.EngineRefused):  # a run folder containing the game folder
            eng.plan_layout(self.tmp, game_root=game)

    def test_moddirs_layout_holds_only_the_candidate(self):
        pak = self.tmp / "cand.pak"
        pak.write_bytes(b"PK\x05\x06" + bytes(18))
        layout = eng.prepare_layout(self.layout, pak=pak)
        self.assertEqual(sorted(p.name for p in layout.mods.iterdir()), ["cand.pak"])
        self.assertEqual(list(layout.mods_pros.iterdir()), [])
        self.assertEqual(list(layout.mods_source.iterdir()), [])
        self.assertEqual(pak.read_bytes(), layout.pak.read_bytes())
        with self.assertRaises(eng.EngineError):  # never reuse a folder
            eng.prepare_layout(self.layout, pak=pak)

    def test_project_copy_layout(self):
        project = self.tmp / "proj"
        (project / "mods_source" / "classes").mkdir(parents=True)
        (project / "mods_source" / "classes" / "a.cls").write_text("x", encoding="utf-8")
        layout = eng.plan_layout(self.tmp / "run2", strategy="project-copy", game_root=self.tmp / "game")
        eng.prepare_layout(layout, project=project)
        self.assertTrue((layout.mods_source / "classes" / "a.cls").is_file())
        self.assertEqual(list(layout.mods.iterdir()), [])

    def test_native_guid_text_matches_the_scripts(self):
        raw = uuid.UUID("12abcdef-abcd-4abc-8abc-abcdef123456").bytes_le  # .NET Guid.ToByteArray()
        self.assertEqual(eng.native_guid_text(raw), "{12ABCDEF-ABCD-4abc-8ABC-ABCDEF123456}")

    def test_screenshot_script(self):
        script = eng.screenshot_script(self.tmp / "a.png")
        self.assertEqual(script, f'SaveScreenshot(ScreenshotSaveTarget.FILE,"{(self.tmp / "a.png").as_posix()}",'
                                 f'false,ScreenshotFormat.PNG)')
        with self.assertRaises(eng.EngineError):
            eng.screenshot_script("a.png")
        with self.assertRaises(eng.EngineError):
            eng.screenshot_script(self.tmp / 'a"b.png')

    def test_wait_png_waits_for_a_complete_file(self):
        sys.path.insert(0, str(HERE))
        self.addCleanup(sys.path.remove, str(HERE))
        import fake_engine
        target = self.tmp / "shot.png"
        threading.Thread(target=fake_engine.write_png_slowly, args=(str(target),), daemon=True).start()
        result = eng.wait_png(target, timeout=10, poll=0.1)
        self.assertTrue(eng.png_complete(target))
        self.assertEqual(result["bytes"], len(fake_engine.png_bytes()))
        with self.assertRaises(eng.EngineTimeout):
            eng.wait_png(self.tmp / "never.png", timeout=0.5, poll=0.1)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        layout = eng.plan_layout(self.tmp / "run", game_root=self.tmp / "game")
        self.make = lambda **kw: eng.EngineSession(layout, game_root=self.tmp / "game", hub_port=free_port(),
                                                   engine_argv=[sys.executable, str(FAKE)], **kw)
        patcher = mock.patch.object(quiet, "start", side_effect=AssertionError("nothing may be launched"))
        self.start = patcher.start()
        self.addCleanup(patcher.stop)

    def test_refuses_without_owner_approval(self):
        for value in (None, "", "   ", 0):
            with self.assertRaises(eng.EngineRefused) as ctx:
                self.make(process_check=IDLE).start(owner_approved=value)
            self.assertIn("owner", str(ctx.exception))
        self.start.assert_not_called()

    def test_refuses_while_game_editor_or_engine_runs(self):
        for name in ("Roadcraft ModEditor.exe", "Roadcraft - Retail.exe", "IntegrationStudio.exe"):
            check = mock.Mock(return_value=([{"pid": 1234, "name": name}], None))
            with self.assertRaises(eng.EngineRefused) as ctx:
                self.make(process_check=check).start(owner_approved="owner said yes in chat")
            self.assertIn(name, str(ctx.exception))
            check.assert_called_once()
        self.start.assert_not_called()

    def test_refuses_when_the_process_list_cannot_be_read(self):
        with self.assertRaises(eng.EngineRefused):
            self.make(process_check=lambda: ([], "access denied")).start(owner_approved="yes")
        self.start.assert_not_called()

    def test_refuses_when_another_hub_holds_the_port(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            port = busy.getsockname()[1]
            session = eng.EngineSession(eng.plan_layout(self.tmp / "r2", game_root=self.tmp / "game"),
                                        game_root=self.tmp / "game", hub_port=port, process_check=IDLE,
                                        engine_argv=[sys.executable, str(FAKE)])
            with self.assertRaises(eng.EngineRefused):
                session.start(owner_approved="yes")
        self.start.assert_not_called()

    def test_guarded_names_are_matched(self):
        for name in ("Roadcraft ModEditor.exe", "Roadcraft - Retail.exe", "IntegrationStudio.exe"):
            self.assertTrue(any(token in name.lower() for token in eng.GUARDED_PROCESSES))
        rows = [{"pid": 7, "name": "Roadcraft ModEditor.exe"}]
        with mock.patch("roadcraft.core._editor_processes", return_value=(rows, None)) as probe:
            self.assertEqual(eng.running_guarded_processes(), (rows, None))
            self.assertEqual(probe.call_args.kwargs["tokens"], eng.GUARDED_PROCESSES)


@unittest.skipUnless(HAVE_HUB, "needs Windows, dotnet and the SDK's Saber.ConsoleTre.dll/Saber.Json.dll")
class FakeEngineHubTests(unittest.TestCase):
    """Real SDK hub (helper) + fake engine process launched through quiet.start."""

    @classmethod
    def setUpClass(cls):
        cls.hub_exe = eng.build_hub(SDK)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = self.tmp / "fake.jsonl"

    def session(self, *, mode: str = "", wall_clock: float = 120, startup_timeout: float = 60):
        port = free_port()
        env = dict(os.environ, RC_FAKE_HUB_PORT=str(port), RC_FAKE_LOG=str(self.log), RC_FAKE_MODE=mode)
        layout = eng.plan_layout(self.tmp / "run", game_root=self.tmp / "game")
        eng.prepare_layout(layout)
        return eng.EngineSession(layout, game_root=self.tmp / "game", sdk_editor_dir=SDK, hub_port=port,
                                 discovery=False, process_check=IDLE, env=env, wall_clock=wall_clock,
                                 startup_timeout=startup_timeout, engine_argv=[sys.executable, str(FAKE)],
                                 hub_argv=eng.hub_command(self.hub_exe, SDK, port=port, discovery=False))

    def fake_rows(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_registration_exec_round_trip_and_screenshot(self):
        with self.session() as session:
            target = session.start(owner_approved="unit test with a fake engine")
            self.assertEqual(target["workspace"], "RoadBuilder")
            self.assertEqual(target["channel"], f"Channel {session.channel}")
            self.assertTrue(session.exec_ssl("return GetFrameNmb()").startswith("FRAME "))
            self.assertEqual(session.exec_ssl("return 1"), "OK")
            shot = session.screenshot(self.tmp / "shot.png", timeout=15)
            self.assertTrue(eng.png_complete(self.tmp / "shot.png"))
            self.assertEqual(len(shot["sha256"]), 64)
            pids = session.engine.pids() | {session.engine.pid}
        result = session.record["result"]
        self.assertFalse(result["wallClockHit"])
        self.assertEqual(result["leakedWindows"], [])
        time.sleep(0.5)
        self.assertFalse(any(alive(pid) for pid in pids), "stop must kill the whole engine tree")
        argv = self.fake_rows()[0]["argv"]
        self.assertIn("--editor", argv)
        self.assertEqual(argv[argv.index("/Config/CONFIG/enableWindow") + 1], "false")
        scripts = [r["script"] for r in self.fake_rows() if r.get("event") == "exec"]
        self.assertIn(eng.screenshot_script(self.tmp / "shot.png"), scripts)
        events = [e["event"] for e in session.record["events"]]
        for name in ("hub-ready", "engine-started", "engine-registered", "execssl-attached", "stopped"):
            self.assertIn(name, events)

    def test_timeout_then_recovery(self):
        with self.session() as session:
            session.start(owner_approved="unit test")
            started = time.monotonic()
            with self.assertRaises(eng.EngineTimeout):
                session.exec_ssl("RC_FAKE_HANG", timeout=1.0)
            self.assertLess(time.monotonic() - started, 9)
            self.assertEqual(session.exec_ssl("return 2"), "OK")  # new reply GUID after the timeout
        guids = {r["guid"] for r in self.fake_rows() if r.get("event") == "exec"}
        self.assertEqual(len(guids), 2)

    def test_wall_clock_limit_kills_the_engine(self):
        session = self.session(mode="silent", wall_clock=3, startup_timeout=60)
        started = time.monotonic()
        with self.assertRaises(eng.EngineError) as ctx:
            session.start(owner_approved="unit test")
        self.assertIn("wall-clock", str(ctx.exception))
        self.assertLess(time.monotonic() - started, 30)
        self.assertTrue(session.wall_clock_hit)
        self.assertIsNotNone(session.record["result"]["engineExit"])

    def test_bench_run_and_smoke_through_the_real_hub(self):
        from roadcraft import bench_headless as bh
        import io
        port = free_port()
        env = dict(os.environ, RC_FAKE_HUB_PORT=str(port), RC_FAKE_LOG=str(self.log))

        def factory(layout, **kwargs):
            kwargs.update(sdk_editor_dir=SDK, hub_port=port, discovery=False, process_check=IDLE, env=env,
                          engine_argv=[sys.executable, str(FAKE)],
                          hub_argv=eng.hub_command(self.hub_exe, SDK, port=port, discovery=False))
            return eng.EngineSession(layout, **kwargs)

        scenario = self.tmp / "scenario.json"
        scenario.write_text(json.dumps({"name": "short", "durationSeconds": 3, "scene": {"settleSeconds": 0},
                                        "inputs": {"schedule": [{"at": 0, "phase": "rest", "handbrake": "On"},
                                                                {"at": 1, "phase": "pivot", "pedal": 0.3,
                                                                 "steer": 0.8}]},
                                        "probes": {"rateHz": 5}}), encoding="utf-8")
        pak = self.tmp / "cand.pak"
        pak.write_bytes(b"PK\x05\x06" + bytes(18))
        out = io.StringIO()
        code = bh.main(["run", str(scenario), "--pak", str(pak), "--out", str(self.tmp / "out"),
                        "--owner-approved", "unit test", "--game-root", str(self.tmp / "game")],
                       factory=factory, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(code, 0, report)
        summary = report["runs"][0]["summary"]
        self.assertGreaterEqual(summary["samples"], 5)
        self.assertEqual(summary["inputsApplied"], "3/3")
        self.assertTrue((self.tmp / "out" / "candidate" / "wheels.csv").is_file())
        out = io.StringIO()
        code = bh.main(["smoke", "--out", str(self.tmp / "smoke"), "--owner-approved", "unit test",
                        "--game-root", str(self.tmp / "game")], factory=factory, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(code, 0, report)
        smoke = report["runs"][0]
        self.assertTrue(smoke["framesAdvance"])
        self.assertTrue(eng.png_complete(smoke["screenshot"]["path"]))

    def test_startup_timeout_when_no_listener_registers(self):
        session = self.session(mode="silent", wall_clock=120, startup_timeout=2)
        with self.assertRaises(eng.EngineTimeout):
            session.start(owner_approved="unit test")
        self.assertIsNotNone(session.record["result"]["engineExit"])


if __name__ == "__main__":
    unittest.main()
