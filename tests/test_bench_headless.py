"""Headless bench (roadcraft.bench_headless): scenario schema, SSL parity with the editor bench scripts,
DFT judder, CSV/summary, timetable, capture and the CLI's approval/dry-run behaviour.  Every engine is a
fake: an in-process session answering with tests/fake_engine.py's canned replies on a virtual clock."""

from __future__ import annotations

import csv
import io
import json
import os
import math
import random
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from roadcraft import bench_headless as bh
from roadcraft import engine as eng

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import fake_engine  # noqa: E402


class VirtualClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(0.0, seconds)


class FakeSession:
    """Stands in for engine.EngineSession: same calls, canned replies, no process."""
    instances: list["FakeSession"] = []
    clock: VirtualClock = VirtualClock()

    def __init__(self, layout, **kwargs):
        self.layout, self.kwargs = layout, kwargs
        self.scripts: list[str] = []
        self.approved = None
        self.record = {"fake": True}
        FakeSession.instances.append(self)

    def plan(self):
        argv, sets = eng.build_command("Roadcraft ModEditor.exe", channel=1, layout=self.layout,
                                       adapter_id=self.kwargs.get("adapter_id", 0),
                                       extra_sets=self.kwargs.get("extra_sets", ()))
        return {"engine": {"argv": argv}, "fake": True}

    def start(self, owner_approved=None):
        eng.check_gates(owner_approved, process_check=lambda: ([], None), hub_port=0)
        self.approved = owner_approved

    def exec_ssl(self, script, timeout=12.0):
        self.scripts.append(script)
        self.clock.sleep(0.03)  # a reply takes time
        if "GetBodyCount" in script:
            return fake_engine.probe_reply(self.clock.t)
        for marker, play in (("SSL_LOAD_REQUESTED", False), ("SSL_PLAY_REQUESTED", True)):
            if marker in script:  # synchronously: the clock is virtual
                fake_engine.load_scene(re.search(r'p\.name = "([^"]*)"', script).group(1), play, delay=0)
                return marker
        return fake_engine.answer(script)

    def screenshot(self, path, *, hud=False, timeout=20.0):
        self.scripts.append(eng.screenshot_script(path, hud))
        if not (fake_engine.STATE.sharing and fake_engine.STATE.level):  # as the gated fake engine
            raise eng.EngineTimeout(f"no complete PNG at {path}")
        Path(path).write_bytes(fake_engine.png_bytes())
        return eng.wait_png(path, 2, 0.01)

    # the "Game editor" connector, answered like tests/fake_engine.py FakeEngine.editor_message
    events: list
    sent: list

    def attach_editor(self, connector=eng.GAME_EDITOR, *, wait=120.0):
        self.events, self.sent = getattr(self, "events", []), getattr(self, "sent", [])
        return {"ok": True, "connected": True, "manager": True,
                "engineListener": [{"name": "Type", "value": connector, "absent": False}]}

    def editor_mark(self):
        return len(self.events)

    def send_editor(self, message, connector=eng.GAME_EDITOR):
        body = eng.check_message(message)
        self.sent.append(body)
        name, fields = message
        if name == "StartFrameSharing":
            fake_engine.STATE.sharing = True
            self.events.append({"event": "editor_message", "name": "FrameShared", "fields": ["1", fields[0][1], False]})
        elif name in ("LoadScene", "LoadScenePlay"):
            fake_engine.load_scene(fields[0][1], name == "LoadScenePlay", delay=0)
            self.events.append({"event": "editor_message", "name": "LoadingsState", "fields": ["Scene", 1, "Loaded"]})
        return {"ok": True, "bytes": sum(len(str(v)) for _, v in fields)}

    def wait_editor(self, predicate, timeout, since=0):
        return next((e for e in self.events[since:] if predicate(e)), None)

    def snapshot_clients(self, key="clients"):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def custom_scenario(**overrides):
    data = {"name": "pivot-test", "seed": 7, "timestep": 1 / 60, "durationSeconds": 12,
            "inputs": {"method": "Debug", "schedule": [
                {"at": 0, "phase": "rest", "handbrake": "On", "gear": "AUTO"},
                {"at": 2, "phase": "forward", "pedal": 0.35, "handbrake": "Off"},
                {"at": 5, "phase": "pivot", "pedal": 0.3, "steer": 0.8, "awd": "On", "difflock": "Off",
                 "controls": [{"controller": "PropTruckViewGraderController", "field": "bladeAngle", "value": -1}]},
                {"at": 9, "phase": "settle", "handbrake": "On"}]},
            "vehicle": {"hull": "BoneChassis_cdt", "restHeightModelled": 1.19,
                        "suspensionTravel": {"min": 0.1, "max": 0.5}},
            "probes": {"rateHz": 10, "items": ["engine", "bodies", "com", "wheels", "joints", "tracks"]},
            "capture": {"cameras": [{"name": "side", "offset": [5, 1.6, -3.5]}],
                        "states": [{"name": "lamps_on", "headlights": True}, {"name": "night", "dayTime": 23}]}}
    data.update(overrides)
    return data


class ScenarioTests(unittest.TestCase):
    def test_named_schedule_reuses_the_editor_bench(self):
        scenario = bh.load_scenario({"inputs": {"schedule": "normal"}})
        self.assertEqual(scenario["durationSeconds"], 64)
        self.assertEqual([s["phase"] for s in scenario["inputs"]["schedule"]][:4], ["rest", "forward", "stop", "pivot+"])
        self.assertEqual(scenario["probes"]["items"], ["engine", "bodies", "com", "wheels"])

    def test_custom_schedule_and_controls(self):
        scenario = bh.load_scenario(custom_scenario())
        self.assertEqual(scenario["seed"], 7)
        self.assertEqual(scenario["inputs"]["schedule"][2]["controls"][0]["literal"], "-1.000")

    def test_rejections(self):
        bad = [custom_scenario(extra=1),
               custom_scenario(inputs={"schedule": [{"at": 1}, {"at": 1}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "pedal": 2}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "gear": "TURBO"}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X); DeleteAll(", "field": "f", "value": 1}]}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X", "field": "f", "value": "1)\nDeleteAll("}]}]}),
               custom_scenario(probes={"items": ["bodies", "secrets"]}),
               custom_scenario(scene={"loadSsl": 'a"); Evil("'}),
               custom_scenario(durationSeconds=5),
               custom_scenario(seed=1.5)]
        for data in bad:
            with self.assertRaises(bh.ScenarioError, msg=json.dumps(data)[:120]):
                bh.load_scenario(data)


class SslParityTests(unittest.TestCase):
    """The headless bench sends the editor bench's own statements."""

    def test_probe_is_series_probe_ps1_verbatim(self):
        text = (ROOT / "integrations" / "physics-bench" / "series_probe.ps1").read_text(encoding="utf-8")
        reference = re.search(r"\$script=@'\n(.*?)\n'@", text.replace("\r\n", "\n"), re.S).group(1)
        self.assertEqual(bh.probe_script(["engine", "bodies", "com", "wheels"]), reference)

    def test_input_statements_come_from_input_override_ps1(self):
        text = (ROOT / "integrations" / "physics-bench" / "input_override.ps1").read_text(encoding="utf-8")
        body = text[text.index("function Build-InputScript"):text.index("if($Mode -eq 'ValidatePayload')")]
        literals = {m for m in re.findall(r"'([^']*)'", body) if "{0}" not in m and ("." in m or " " in m)
                    and not m.startswith(("Apply", "Release", "State", "Debug", "Unchanged", "On", "Off"))
                    and m not in ("Unsupported gear state $Gear",)}
        step = bh._step({"at": 0, "pedal": 1, "steer": -1, "handbrake": "Off", "gear": "LOW_GEAR",
                         "awd": "On", "difflock": "Off"}, 0, None)
        produced = "\n".join(bh.input_script(step, m) + "\n" + bh.input_script(None, m) for m in ("State", "Debug"))
        lines = set(produced.split("\n"))
        missing = sorted(lit for lit in literals if lit not in lines)
        self.assertEqual(missing, [])
        state_apply = bh.input_script(step, "State")
        for fragment in ("state.pedals.Set(1.000)", "state.steering.Set(-1.000)", "GearState.LOW_GEAR",
                         "state.isHandbrake.Set(false)", "isAwdOn.Set(true)", "isDifflockOn.Set(false)"):
            self.assertIn(fragment, state_apply)
        self.assertNotIn("dbg", state_apply)
        self.assertIn("viewController.dbgAccelerationOverride = 1.000", bh.input_script(step, "Debug"))

    def test_scripts_are_ascii(self):
        scenario = bh.load_scenario(custom_scenario())
        scripts = bh.scripts_for(scenario)
        flat = json.dumps(scripts)
        self.assertTrue(all(ord(c) < 128 for c in flat))
        self.assertIn("control0.GetState().bladeAngle.Set(-1.000)", scripts["inputs"]["02_pivot"])
        self.assertIn("state.isHeadlightsOn.Set(true)", scripts["capture"]["states"]["lamps_on"])
        self.assertIn("SetActiveCameraTransform(shot)", scripts["capture"]["cameras"]["side"])


class AnalysisTests(unittest.TestCase):
    def test_dft_finds_1_hz_on_jittered_samples(self):
        rng = random.Random(3)
        times, t = [], 0.0
        while t < 12:
            times.append(t)
            t += 0.1 + rng.uniform(-0.02, 0.03)  # the editor bench sampled at an uneven 7-10 Hz
        values = [2.0 * math.sin(2 * math.pi * 1.0 * x) + 0.3 * x + rng.gauss(0, 0.05) for x in times]
        found = bh.dominant_frequency(times, values)
        self.assertAlmostEqual(found["hz"], 1.0, delta=0.03)
        self.assertAlmostEqual(found["amplitude"], 2.0, delta=0.4)
        fast = bh.dominant_frequency(times, [math.sin(2 * math.pi * 2.5 * x) for x in times])
        self.assertAlmostEqual(fast["hz"], 2.5, delta=0.05)
        self.assertIsNone(bh.dominant_frequency([0, 1, 2], [0, 1, 0]))

    def test_settle_time(self):
        rows = [{"t": t / 10, "roll": 3 * math.exp(-t / 10) * math.cos(t), "pitch": 0.0, "y": 1.0} for t in range(100)]
        settled = bh.settle_time(rows, {"rollDeg": 0.2, "pitchDeg": 0.2, "heightMm": 5})
        self.assertTrue(2.0 < settled < 4.0, settled)
        still = [{"t": t / 10, "roll": 0.0, "pitch": 0.0, "y": 1.0} for t in range(30)]
        self.assertEqual(bh.settle_time(still, {"rollDeg": 0.2, "pitchDeg": 0.2, "heightMm": 5}), 0.0)

    def test_drive_csv_and_summary_on_synthetic_1_hz_roll(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        scenario = bh.load_scenario(custom_scenario())
        FakeSession.clock = clock = VirtualClock()
        session = FakeSession(None)
        log = bh.drive(session, scenario, tmp, clock)
        self.assertEqual([e["step"] for e in log], [0, 1, 2, 3, "release"])
        self.assertTrue(all(e["ok"] for e in log))
        rows = (tmp / "series.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertTrue(100 <= len(rows) <= 125, len(rows))  # 12 s at 10 Hz
        summary = bh.analyse(tmp, scenario)
        for name in ("engine", "bodies", "com", "wheels", "joints", "tracks"):
            self.assertIn(f"{name}.csv", summary["csv"])
        with open(tmp / "wheels.csv", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header[:3], ["t", "wheel", "travel"])
        self.assertAlmostEqual(summary["judder"]["02_pivot"]["roll"]["hz"], 1.0, delta=0.1)
        self.assertEqual(summary["judderStrongest"]["axis"], "roll")
        self.assertAlmostEqual(summary["maxRollPivotDeg"], 2.0, delta=0.15)
        self.assertAlmostEqual(summary["rest"]["hullHeightM"], 1.2, delta=0.015)
        self.assertAlmostEqual(summary["rest"]["deltaVsModelledMm"], 10, delta=15)
        self.assertEqual(summary["stopHits"]["perWheel"][0]["low"], summary["samples"])  # wheel 0 sits on min
        self.assertEqual(summary["stopHits"]["perWheel"][3]["low"], 0)
        self.assertIn("03_settle", summary["settleSeconds"])
        self.assertEqual(summary["seed"], 7)
        self.assertAlmostEqual(summary["timestepS"], 1 / 60)
        self.assertAlmostEqual(summary["yaw"]["02_pivot"]["yawDeg"], 0.0, delta=0.5)
        self.assertGreater(summary["yaw"]["01_forward"]["movedM"], 1.0)
        self.assertEqual(summary["inputsApplied"], "5/5")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.scenario = self.tmp / "scenario.json"
        self.scenario.write_text(json.dumps(custom_scenario()), encoding="utf-8")
        self.pak = self.tmp / "cand.pak"
        self.pak.write_bytes(b"PK\x05\x06" + bytes(18))
        self.base = self.tmp / "base.pak"
        self.base.write_bytes(b"PK\x05\x06" + bytes(18))
        FakeSession.instances = []
        FakeSession.clock = VirtualClock()

    def main(self, *argv):
        out = io.StringIO()
        code = bh.main([*map(str, argv)], factory=FakeSession, clock=FakeSession.clock, stdout=out)
        return code, json.loads(out.getvalue())

    def test_dry_run_is_the_default_without_approval(self):
        out = self.tmp / "out"
        code, plan = self.main("run", self.scenario, "--pak", self.pak, "--baseline", self.base, "--out", out,
                               "--game-root", self.tmp / "game")
        self.assertEqual(code, 0)
        self.assertTrue(plan["dryRun"])
        self.assertIn("owner-approved", plan["reason"])
        self.assertFalse(out.exists(), "a dry run writes nothing")
        self.assertEqual([r["label"] for r in plan["runs"]], ["candidate", "baseline"])
        argv = plan["runs"][0]["session"]["engine"]["argv"]
        self.assertIn("--editor", argv)
        self.assertEqual(argv[argv.index("/Config/ResourceManager/ModDirs/local") + 1],
                         (out.resolve() / "candidate" / "root" / "mods").as_posix())
        self.assertIn("GetBodyCount", plan["scripts"]["probe"])
        self.assertEqual(FakeSession.instances[0].approved, None)
        self.assertEqual(sum(len(s.scripts) for s in FakeSession.instances), 0)
        code, plan = self.main("run", self.scenario, "--pak", self.pak, "--out", out, "--owner-approved", "  ",
                               "--game-root", self.tmp / "game")
        self.assertTrue(plan["dryRun"])

    def test_explicit_dry_run_with_approval_and_real_session_plan(self):
        out = io.StringIO()
        code = bh.main(["smoke", "--out", str(self.tmp / "s"), "--owner-approved", "yes", "--dry-run",
                        "--game-root", str(self.tmp / "game")], stdout=out)
        plan = json.loads(out.getvalue())
        self.assertEqual((code, plan["dryRun"], plan["reason"]), (0, True, "--dry-run"))
        engine_plan = plan["runs"][0]["session"]["engine"]
        self.assertEqual(engine_plan["priority"], "below_normal")
        self.assertIn("--set /Config/CONFIG/enableWindow false --editor", engine_plan["commandLine"])
        self.assertIn("SaveScreenshot(ScreenshotSaveTarget.FILE", plan["scripts"]["screenshot"])
        self.assertFalse((self.tmp / "s").exists())

    def test_missing_pak_is_a_tool_error(self):
        code, report = self.main("run", self.scenario, "--out", self.tmp / "o")
        self.assertEqual(code, 2)
        self.assertIn("--pak", report["message"])

    def test_approved_run_with_baseline_writes_csv_summary_and_comparison(self):
        out = self.tmp / "out"
        code, report = self.main("run", self.scenario, "--pak", self.pak, "--baseline", self.base, "--out", out,
                                 "--owner-approved", "owner: test only", "--game-root", self.tmp / "game")
        self.assertEqual(code, 0, report)
        self.assertEqual([s.approved for s in FakeSession.instances], ["owner: test only"] * 2)
        for label in ("candidate", "baseline"):
            folder = out / label
            for name in ("run.json", "session.json", "series.jsonl", "inputs.json", "summary.json", "bodies.csv"):
                self.assertTrue((folder / name).is_file(), f"{label}/{name}")
            expected = "cand.pak" if label == "candidate" else "base.pak"
            self.assertEqual([p.name for p in (folder / "root" / "mods").iterdir()], [expected])
        self.assertAlmostEqual(report["comparison"]["maxRollPivotDeg"], 0.0, delta=0.1)
        self.assertTrue((out / "comparison.json").is_file())

    def test_capture_writes_pngs_per_state_and_camera(self):
        out = self.tmp / "cap"
        code, report = self.main("capture", self.scenario, "--pak", self.pak, "--out", out,
                                 "--owner-approved", "owner: test only", "--game-root", self.tmp / "game")
        self.assertEqual(code, 0, report)
        shots = report["runs"][0]["capture"]
        self.assertEqual([(s["state"], s["camera"]) for s in shots], [("lamps_on", "side"), ("night", "side")])
        for shot in shots:
            self.assertTrue(eng.png_complete(shot["path"]))
        self.assertIn("Inferred", shots[1]["grades"]["dayTime"])


def make_scene(mods_source: Path, rel: str = "xscenes/mods/Example/Example.scn") -> Path:
    scene = mods_source / rel
    scene.parent.mkdir(parents=True, exist_ok=True)
    scene.write_text("elements = {\n   truck = {\n   }\n}\n__type = \"scene_object\"\n", encoding="utf-8")
    scene.with_name(scene.name + ".resource").write_text("__type: res_xscn_desc\nbrandName: example\n",
                                                         encoding="utf-8")
    return scene


class SceneTests(unittest.TestCase):
    """bench_headless scene: scene_play.md's recipe against the in-process fake (gated like smoke_003)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = self.tmp / "game"
        make_scene(self.game / "root" / "mods_source", "xscenes/mods/example/example.scn")
        FakeSession.instances = []
        FakeSession.clock = VirtualClock()
        saved = fake_engine.STATE
        self.addCleanup(setattr, fake_engine, "STATE", saved)
        fake_engine.STATE = fake_engine.State()
        fake_engine.STATE.sharing, fake_engine.STATE.level, fake_engine.STATE.truck = False, "", False
        fake_engine.STATE.trucks = 0

    def main(self, *argv):
        out = io.StringIO()
        code = bh.main([*map(str, argv)], factory=FakeSession, clock=FakeSession.clock, stdout=out)
        return code, json.loads(out.getvalue())

    def test_scene_load_data_and_messages_follow_the_editor(self):
        scene = make_scene(self.tmp / "ms")
        data = eng.scene_load_data("xscenes/mods/Example/Example.scn", self.tmp / "ms")
        self.assertEqual(data.name, "Example.scn")                        # ClassDocumentSource.Name
        self.assertEqual(data.res_tag, "res://xscenes/mods/example/example.scn.resource")  # lower case
        self.assertEqual(data.ps, scene.read_text(encoding="utf-8"))
        self.assertEqual(eng.scene_load_data(scene, self.tmp / "ms", ps="empty").ps, "")
        name, fields = eng.load_scene_message(data, play=True)
        self.assertEqual(name, "LoadScenePlay")
        self.assertEqual([k for k, _ in fields], ["str", "str", "str", "str", "bool", "str", "str"])
        self.assertEqual([v for _, v in fields][-3:], [False, "localhost", ""])
        name, fields = eng.load_scene_message(data, play=False, unloaded_blocks=["b1"])
        self.assertEqual((name, fields[5:]), ("LoadScene", [("int", 1), ("str", "b1")]))
        self.assertEqual(eng.play_message(data)[1][0], ("str", data.ps))   # Play carries no name
        self.assertEqual(eng.stop_message(data)[1][-1], ("int", 0))
        self.assertEqual(eng.start_frame_sharing_message(0, 10, 2000)[1],
                         [("int", 0), ("int", 64), ("int", 2000), ("int", 0), ("int", 0), ("int", 64), ("int", 2000),
                          ("bool", True)])
        with self.assertRaises(eng.EngineError):
            eng.check_message(("X", [("int", True)]))
        with self.assertRaises(eng.EngineError):
            eng.scene_load_data(self.tmp / "elsewhere.scn", self.tmp / "ms")
        (self.tmp / "ms" / "xscenes" / "mods" / "Example" / "Example.scn.resource").unlink()
        with self.assertRaises(eng.EngineError):
            eng.scene_load_data(scene, self.tmp / "ms")

    def test_dry_run_plans_messages_dbgvar_and_writes_nothing(self):
        out = self.tmp / "out"
        code, plan = self.main("scene", "--out", out, "--game-root", self.game, "--adapter-id", "1")
        self.assertEqual(code, 0, plan)
        self.assertTrue(plan["dryRun"])
        self.assertFalse(out.exists())
        argv = plan["runs"][0]["session"]["engine"]["argv"]
        self.assertEqual(argv[argv.index("/DbgVars/Game/Startup/Start at truck on scene") + 1], "true")
        self.assertEqual(argv[argv.index("/Config/Video/AdapterId") + 1], "1")
        self.assertEqual([m["name"] for m in plan["scenePlan"]["messages"]],
                         ["MinimizeEditorOnDeactivate", "StartFrameSharing", "LoadScenePlay"])
        self.assertEqual(plan["scenePlan"]["scene"]["resTag"], "res://xscenes/mods/example/example.scn.resource")
        self.assertIn("RC_ADAPTER", plan["scripts"]["adapter"])
        code, plan = self.main("scene", "--out", out, "--game-root", self.game, "--mode", "edit", "--via", "ssl")
        argv = plan["runs"][0]["session"]["engine"]["argv"]
        self.assertNotIn("/DbgVars/Game/Startup/Start at truck on scene", argv)
        self.assertIn("StartSceneLoading(p)", plan["scripts"]["load"])
        self.assertIn("GetOrCreateViewport(c.viewports, 0)", plan["scripts"]["frameSharing"])

    def test_play_via_editor_waits_for_truck_then_screenshots(self):
        out = self.tmp / "play"
        code, report = self.main("scene", "--out", out, "--game-root", self.game, "--owner-approved", "test")
        self.assertEqual(code, 0, report)
        run = report["runs"][0]
        steps = {s["step"]: s for s in run["steps"]}
        self.assertTrue(steps["frame-shared"]["ok"])
        self.assertTrue(steps["scene-loaded"]["ok"])
        self.assertTrue(run["ready"])
        self.assertIn("truck 1", steps["ready"]["reply"])
        self.assertTrue(eng.png_complete(run["screenshot"]["path"]))
        self.assertTrue((out / "candidate" / "scene.json").is_file())
        session = FakeSession.instances[0]
        self.assertEqual([m["name"] for m in session.sent],
                         ["MinimizeEditorOnDeactivate", "StartFrameSharing", "LoadScenePlay"])
        self.assertEqual(session.kwargs["extra_sets"], [eng.START_AT_TRUCK_ON_SCENE])
        order = [s for s in session.scripts if "SaveScreenshot" in s or "RC_READY" in s]
        self.assertIn("SaveScreenshot", order[-1])  # the shot comes after the ready polls

    def test_edit_via_ssl_loads_and_screenshots_without_truck(self):
        code, report = self.main("scene", "--out", self.tmp / "e", "--game-root", self.game, "--mode", "edit",
                                 "--via", "ssl", "--owner-approved", "test")
        self.assertEqual(code, 0, report)
        run = report["runs"][0]
        self.assertTrue(run["ready"])
        self.assertTrue(eng.png_complete(run["screenshot"]["path"]))
        scripts = FakeSession.instances[0].scripts
        self.assertTrue(any("SSL_FRAME_SHARING" in s for s in scripts))
        self.assertTrue(any("SSL_LOAD_REQUESTED" in s for s in scripts))

    def test_no_truck_is_reported_and_force_current_tried(self):
        patcher = mock.patch.dict(os.environ, {"RC_FAKE_TRUCKS": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        code, report = self.main("scene", "--out", self.tmp / "n", "--game-root", self.game, "--owner-approved", "t",
                                 "--ready-timeout", "5", "--force-current-truck")
        self.assertEqual(code, 0, report)
        run = report["runs"][0]
        self.assertFalse(run["ready"])
        steps = {s["step"]: s for s in run["steps"]}
        self.assertEqual(steps["force-current"]["reply"], "NO_TRUCKS")
        self.assertTrue(eng.png_complete(run["screenshot"]["path"]))  # a loaded level still renders


if __name__ == "__main__":
    unittest.main()
