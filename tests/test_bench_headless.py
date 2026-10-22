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
        if "RB_FILTERS" in script or "RB_LOAD" in script:
            return fake_engine.answer(script)
        if "GetBodyCount" in script or 'StringFormat("F %i' in script:
            return fake_engine.probe_reply(self.clock.t, script)
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

    def test_call_control(self):
        scenario = bh.load_scenario(custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
            {"controller": "PropTruckConstraintView", "call": "SetConstraintTarget", "args": ["lift", 0.857, 0.08]}]}]}))
        control = scenario["inputs"]["schedule"][0]["controls"][0]
        self.assertEqual(control["literal"], '"lift", 0.857, 0.080')
        script = bh.input_script(scenario["inputs"]["schedule"][0])
        self.assertIn('control0.SetConstraintTarget("lift", 0.857, 0.080)', script)
        self.assertNotIn("control0.GetState()", script)

    def test_rejections(self):
        bad = [custom_scenario(extra=1),
               custom_scenario(inputs={"schedule": [{"at": 1}, {"at": 1}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "pedal": 2}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "gear": "TURBO"}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X); DeleteAll(", "field": "f", "value": 1}]}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X", "field": "f", "value": "1)\nDeleteAll("}]}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X", "call": "F", "args": ['a"); Evil("']}]}]}),
               custom_scenario(inputs={"schedule": [{"at": 0, "controls": [
                   {"controller": "X", "call": "F", "field": "f", "args": []}]}]}),
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
        # a slow trend with the band starting at 1 Hz: the peak sits on the band edge; refinement must not
        # leave the band or go negative (it returned -1.86 Hz on a KGS-25 run before the clamp)
        rng = random.Random(5)
        for seed in range(40):
            n = rng.randint(20, 60)
            ts = sorted(rng.uniform(0, 4) for _ in range(n))
            vs = [rng.gauss(0, 0.05) + 2 * math.sin(0.7 * x + seed) for x in ts]
            found = bh.dominant_frequency(ts, vs, fmin=1.0)
            if found:
                self.assertGreaterEqual(found["hz"], 1.0, seed)

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


CUBE = "AAAIAAwABgAAAAC/AAAAPwAAAD8="
PAD_SCENE = ("elements = {\n   course = {\n      childs = {\n         flat_pad = {\n            mesh = {\n"
             f'               data = "{CUBE}"\n               __type = "EditorMesh"\n            }}\n'
             "            transform = {\n               position = [ 0, 59.75, 0 ]\n               scale = [ 60, 0.5, 100 ]\n"
             "               rotation = [ 0, 0, 0 ]\n            }\n            __type = \"mesh\"\n         }\n      }\n   }\n"
             "   test_vehicle = {\n      transform = {\n         position = [ 0, 60.12, -18 ]\n      }\n"
             "      __type = \"k_prefab\"\n      desc = {\n         __type = \"auto_k\"\n      }\n   }\n}\n"
             "__type = \"scene_object\"\n")


class StepCourseTests(unittest.TestCase):
    """KGS-25 campaign additions: scene boxes, build readback, frame/wheel articulation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        FakeSession.instances = []
        FakeSession.clock = VirtualClock()

    def test_add_box_uses_the_scenes_cube_and_keeps_the_scene_valid(self):
        from roadcraft import physics_bench as pb
        text = pb.add_box(PAD_SCENE, "step_slab_030", [22.2, 60.15, -20], [2.6, 0.3, 20], 0)
        self.assertEqual(text.count(f'data = "{CUBE}"'), 2)
        self.assertIn("position = [ 22.2, 60.15, -20 ]\n               scale = [ 2.6, 0.3, 20 ]", text)
        self.assertLess(text.index("step_slab_030 = {"), text.index("flat_pad = {"))
        self.assertEqual(text.count("{"), text.count("}"))
        moved = pb.place_vehicle(text, "test_vehicle", [20, 60.12, -35])
        self.assertIn("position = [ 20, 60.12, -35 ]", moved)
        with self.assertRaises(pb.BenchError):
            pb.add_box(text, "step_slab_030", [0, 0, 0], [1, 1, 1])
        with self.assertRaises(pb.BenchError):
            pb.add_box("elements = {\n}\n", "b", [0, 0, 0], [1, 1, 1])

    def test_spawn_boxes_go_into_the_scene_text_sent_to_the_engine(self):
        project = self.tmp / "project"
        scene = project / "mods_source" / "xscenes/mods/pad/pad.scn"
        scene.parent.mkdir(parents=True)
        scene.write_text(PAD_SCENE, encoding="utf-8")
        scene.with_name("pad.scn.resource").write_text("__type: res_xscn_desc\n", encoding="utf-8")
        data = custom_scenario(scene={"file": "xscenes/mods/pad/pad.scn", "settleSeconds": 1},
                               spawn={"method": "scene", "scene": "xscenes/mods/pad/pad.scn", "vehicle": "test_vehicle",
                                      "position": [20, 60.12, -35],
                                      "boxes": [{"name": "slab", "position": [22.2, 60.15, -20], "scale": [2.6, 0.3, 20]}]},
                               probes={"rateHz": 10, "items": ["bodies", "wheels"], "readback": True},
                               capture=None)
        path = self.tmp / "s.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        out = io.StringIO()
        code = bh.main(["run", str(path), "--out", str(self.tmp / "o"), "--strategy", "project-copy", "--project",
                        str(project), "--owner-approved", "test", "--game-root", str(self.tmp / "game"), "--prune-copy"],
                       factory=FakeSession, clock=FakeSession.clock, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(code, 0, report)
        session = FakeSession.instances[0]
        load = next(m for m in session.sent if m["name"] == "LoadScenePlay")
        ps = load["fields"][1]["v"]
        self.assertIn("slab = {", ps)                               # the private copy, not the source file
        self.assertIn("position = [ 20.0, 60.12, -35.0 ]", ps)
        self.assertNotIn("slab", scene.read_text(encoding="utf-8"))  # the source project is never written
        run = report["runs"][0]
        self.assertFalse((self.tmp / "o" / "candidate" / "root" / "mods_source").exists())
        self.assertIn("prunedCopy", run)
        self.assertTrue((self.tmp / "o" / "candidate" / "readback.json").is_file())
        self.assertIn("readback", run["summary"])
        readbacks = [s for s in session.scripts if "RB_" in s]
        self.assertEqual(len(readbacks), len(bh.readback_scripts()))
        first_input = next(i for i, s in enumerate(session.scripts) if "ROAMER_INPUT_APPLIED" in s)
        self.assertLess(max(session.scripts.index(s) for s in readbacks), first_input)  # read back at rest
        rb = json.loads((self.tmp / "o" / "candidate" / "readback.json").read_text(encoding="utf-8"))["parsed"]
        self.assertEqual(rb["filters"]["bodies"]["BoneSuspFrontLeft_cdt"]["layer"], "constr_vhc")
        self.assertFalse(any(b["inNoSelfCollision"] for b in rb["filters"]["bodies"].values()))
        self.assertEqual(rb["load"]["maxMass"], 218000.0)

    def test_readback_parse_keeps_errors_apart(self):
        parsed = bh.parse_readback({
            "identity": "RB_IDENTITY\ntpl kgs25\nowner auto_kgs25_kgs25 #12\n",
            "wheels": "RB_WHEELS\nw 0.4000 0.0000\nw 0.2700 0.4000\n",
            "softForce": "Error: unknown member softForceScale",
            "constraints": "RB_CONSTRAINTS\nc TrackSusp_L 1 1\nc Weld 0 0\n",
            "motors": "RB_MOTORS\nm TrackSusp_L 3000000.0 3300000.0\n",
            "limits": "RB_LIMITS\nl TrackSusp_L -0.13963 0.13963\n"})
        self.assertEqual(parsed["identity"]["tpl"], "kgs25")
        self.assertEqual(parsed["wheelMaxTravel"], [0.0, 0.4])
        self.assertIn("softForce", parsed["errors"])
        self.assertNotIn("softForceScale", parsed)
        self.assertEqual(parsed["constraints"]["TrackSusp_L"],
                         {"angular": True, "motor": True, "spring": 3e6, "damping": 3.3e6, "limits": [-0.13963, 0.13963]})
        self.assertFalse(parsed["constraints"]["Weld"]["motor"])
        self.assertTrue(all(ord(c) < 128 for c in json.dumps(bh.readback_scripts())))

    def test_articulation_frame_pitch_and_wheel_travel_in_the_hull_frame(self):
        def body(name, pos, pitch_deg, roll_deg=0.0):
            p, r = math.radians(pitch_deg), math.radians(roll_deg)
            fwd = (0.0, math.sin(p), math.cos(p))
            up = (-math.sin(r) * math.cos(p), math.cos(r) * math.cos(p), -math.cos(r) * math.sin(p))
            return f"B {name} {pos[0]:.5f} {pos[1]:.5f} {pos[2]:.5f} {up[0]:.5f} {up[1]:.5f} {up[2]:.5f} " \
                   f"{fwd[0]:.5f} {fwd[1]:.5f} {fwd[2]:.5f}"
        lines = []
        for k in range(200):
            t = k / 10
            climb = 0.0 if t < 8 else min(1.0, (t - 8) / 4)       # the left frame noses up 4 deg, the idler 0.3 m
            lines.append(json.dumps({"i": k, "t": t, "r": "\n".join([
                f"F {k} 0.3 0.0 0.0", body("BoneChassis_cdt", (0, 1.0, 0.1 * t), 1.0),
                body("BoneTrackSusp_L_cdt", (1.4, 0.5, 0.1 * t), 1.0 + 4 * climb),
                body("BoneTrackSusp_R_cdt", (-1.4, 0.5, 0.1 * t), 1.0),
                f"W 0.0000 1.4 {0.7 + 0.3 * climb:.4f} {0.1 * t + 3:.4f} 1",
                f"W 0.0500 -1.4 0.7 {0.1 * t + 3:.4f} 1",
                f"J TrackSusp_L {0.07 * climb:.4f} 0.0000", "J TrackSusp_R 0.0000 0.0000"]) + "\n"}))
        (self.tmp / "series.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        scenario = bh.load_scenario({
            "durationSeconds": 20, "vehicle": {"hull": "BoneChassis_cdt", "wheelNames": ["kgs_L_drive0", "kgs_R_drive0"]},
            "inputs": {"schedule": [{"at": 0, "phase": "rest", "handbrake": "On"},
                                    {"at": 8, "phase": "climb", "pedal": 0.3, "handbrake": "Off"},
                                    {"at": 14, "phase": "stop", "handbrake": "On"}]},
            "analysis": {"articulation": {"wheels": ["kgs_L_drive0", 1], "joints": ["TrackSusp_L"]}}})
        summary = bh.analyse(self.tmp, scenario)
        art = summary["articulation"]
        self.assertEqual(art["frames"], ["BoneTrackSusp_L_cdt", "BoneTrackSusp_R_cdt"])  # guessed
        self.assertAlmostEqual(art["rest"]["frameDeg"]["BoneTrackSusp_L_cdt"], 0.0, delta=0.05)
        self.assertAlmostEqual(art["peak"]["frameDegMaxAbs"]["BoneTrackSusp_L_cdt"], 4.0, delta=0.1)
        self.assertAlmostEqual(art["peak"]["frameDegMaxAbs"]["BoneTrackSusp_R_cdt"], 0.0, delta=0.05)
        self.assertAlmostEqual(art["phases"]["01_climb"]["wheelMm"]["kgs_L_drive0"][1], 300, delta=15)
        self.assertAlmostEqual(art["peak"]["wheelMmMaxAbs"]["kgs_R_drive0"], 0.0, delta=1)
        self.assertEqual(art["phases"]["00_rest"]["springTravelM"]["kgs_R_drive0"], [0.05, 0.05])
        self.assertAlmostEqual(art["phases"]["02_stop"]["jointAngle"]["TrackSusp_L"][1], 0.07, delta=1e-4)
        self.assertAlmostEqual(art["rest"]["pitchDeg"], 1.0, delta=0.05)
        self.assertNotIn("articulation", bh.summarise(bh.pb.parse_series(self.tmp / "series.jsonl"),
                                                      bh.load_scenario({**{"durationSeconds": 20}, "inputs": {
                                                          "schedule": [{"at": 0}]}})))  # opt-in only

    def test_scenario_rejects_bad_boxes_wheels_and_articulation(self):
        spawn = {"method": "scene", "scene": "a.scn", "vehicle": "v", "position": [0, 0, 0]}
        for data in (custom_scenario(spawn={**spawn, "boxes": [{"name": "x y", "position": [0, 0, 0], "scale": [1, 1, 1]}]}),
                     custom_scenario(spawn={**spawn, "boxes": [{"name": "b", "position": [0, 0], "scale": [1, 1, 1]}]}),
                     custom_scenario(spawn={**spawn, "boxes": [{"name": "b", "position": [0, 0, 0], "scale": [1, 0, 1]}]}),
                     custom_scenario(vehicle={"wheelNames": ["ok", "no way"]}),
                     custom_scenario(analysis={"articulation": {"wheels": [-1]}}),
                     custom_scenario(analysis={"articulation": {"frames": "BoneX"}}),
                     custom_scenario(probes={"items": ["bodies"], "secret": True})):
            with self.assertRaises(bh.ScenarioError, msg=json.dumps(data)[:160]):
                bh.load_scenario(data)

    def test_library_scenarios_load(self):
        for path in sorted((ROOT / "library" / "bench-scenarios").glob("*.json")):
            with self.subTest(path.name):
                scenario = bh.load_scenario(path)
                if path.name.startswith("kgs25_"):
                    self.assertEqual(len(scenario["vehicle"]["wheelNames"]), 22)
                    self.assertTrue(scenario["probes"]["readback"])


class PakOverlayTests(unittest.TestCase):
    def test_overlay_swaps_generated_classes_for_the_paks_staged_ones(self):
        import zipfile
        from roadcraft import pak_overlay as po
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        project = tmp / "project"
        ms = project / "mods_source"
        gen = ms / "autogen_dw/trucks/auto_k"
        gen.mkdir(parents=True)
        (gen / "auto_k.cls").write_text("old class\n", encoding="utf-8")
        (gen / "auto_k.cls.resource").write_text("cls: auto_k.cls\n", encoding="utf-8")
        (gen / "auto_k_truck_info.sso").write_text('__type = "AutoKTruckInfo"\n', encoding="utf-8")
        (gen / "k_prefab.prefab").write_text('desc = {\n   __type = "auto_k"\n}\n', encoding="utf-8")
        (gen / "k_prefab.prefab.resource").write_text(
            "linksDesc:\n- res://autogen_dw/trucks/auto_k/auto_k.cls.resource\nprefab: k_prefab.prefab\n", encoding="utf-8")
        (ms / "autogen_dw/trucks/auto_truck_library.sso").write_text('__type = "AutoKTruckInfo"\n', encoding="utf-8")
        scene = ms / "xscenes/mods/pad/pad.scn"
        scene.parent.mkdir(parents=True)
        scene.write_text(PAD_SCENE.replace("auto_k", "auto_k"), encoding="utf-8")
        (ms / "xscenes/mods/pad/pad.scn.resource").write_text(
            "linksDesc:\n- res://autogen_dw/trucks/auto_k/k_prefab.prefab.resource\n", encoding="utf-8")
        (ms / "mods").mkdir()
        (ms / "mods/k.mod").write_text("assets:\n- autogen_dw/trucks/auto_k/auto_k_truck_info.sso.resource\n", encoding="utf-8")
        (ms / "textures").mkdir()
        (ms / "textures/big.tga").write_bytes(b"\0" * 64)
        markup = ('objectInfos = [\n   {\n      name = "BoneFrame_cdt"\n      properties = [\n         {\n'
                  '            mass = 7500\n            angularDamping = 1.5\n            linearDamping = 0.03\n'
                  '            __type = "tpl_markup_object_property_physics"\n         }\n      ]\n   }\n]\n')
        (project / ".project").write_text("documents-dir: C:/elsewhere/project\n", encoding="utf-8")
        (project / "config").mkdir()
        (project / "config/editor.cfg").write_text("external:\n  ModsSourceLocal: C:/elsewhere/project/mods_source\n",
                                                   encoding="utf-8")
        pak = tmp / "k.pak"
        with zipfile.ZipFile(pak, "w") as z:
            z.writestr("ssl/auto_k_x1.cls", "new class\n")
            z.writestr("ssl/auto_k_x1.cls.resource", "cls: auto_k_x1.cls\n")
            z.writestr("ssl/auto_k_truck_info_x1.sso", '__type = "AutoKTruckInfoX1"\n')
            z.writestr("ssl/auto_k_truck_info_x1.sso.resource",
                       "brandName: AutoKTruckInfoX1\nlinksDesc:\n- res://ssl/auto_k_x1.cls.resource\n"
                       "sso: auto_k_truck_info_x1.sso\n")
            z.writestr("models/k.tpl.asset/k.tpl_markup", markup)
            z.writestr("models/k.tpl.asset/k.tpl_markup", markup)       # packers write some members twice
            z.writestr("k.mod", "assets:\n- ssl/auto_k_truck_info_x1.sso.resource\n")
        before = {p: p.read_bytes() for p in ms.rglob("*") if p.is_file()}
        report = po.overlay(project, pak, tmp / "out",
                            markup_bodies={"BoneFrame_cdt": {"angularDamping": 0.05, "linearDamping": 0}})
        out = tmp / "out" / "mods_source"
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["suffix"], "x1")
        self.assertEqual({p: p.read_bytes() for p in ms.rglob("*") if p.is_file()}, before)   # source untouched
        self.assertFalse((out / "autogen_dw/trucks/auto_k/auto_k.cls").exists())
        self.assertEqual((out / "autogen_dw/trucks/auto_truck_library.sso").read_text(encoding="utf-8"),
                         '__type = "AutoKTruckInfoX1"\n')            # kept (engine looks the truck up there), retagged
        self.assertEqual((out / "ssl/auto_k_x1.cls").read_text(encoding="utf-8"), "new class\n")
        # the editor engine registers trucks by scanning autogen_dw/trucks/auto_<t>/: the info .sso stays there
        self.assertEqual((out / "autogen_dw/trucks/auto_k/auto_k_truck_info.sso").read_text(encoding="utf-8"),
                         '__type = "AutoKTruckInfoX1"\n')
        shim = (out / "autogen_dw/trucks/auto_k/auto_k_truck_info.sso.resource").read_text(encoding="utf-8")
        self.assertIn("brandName: AutoKTruckInfo\n", shim)
        self.assertIn("sso: auto_k_truck_info.sso", shim)
        self.assertIn("res://ssl/auto_k_x1.cls.resource", shim)
        self.assertIn('__type = "auto_k_x1"', (out / "autogen_dw/trucks/auto_k/k_prefab.prefab").read_text(encoding="utf-8"))
        self.assertIn("res://ssl/auto_k_x1.cls.resource",
                      (out / "autogen_dw/trucks/auto_k/k_prefab.prefab.resource").read_text(encoding="utf-8"))
        self.assertIn('__type = "auto_k_x1"', (out / "xscenes/mods/pad/pad.scn").read_text(encoding="utf-8"))
        self.assertIn("res://autogen_dw/trucks/auto_k/k_prefab.prefab.resource",
                      (out / "xscenes/mods/pad/pad.scn.resource").read_text(encoding="utf-8"))   # prefab kept
        self.assertIn("ssl/auto_k_truck_info_x1", (out / "mods/k.mod").read_text(encoding="utf-8"))
        self.assertFalse((out / "k.mod").exists())
        text = (out / "models/k.tpl.asset/k.tpl_markup").read_text(encoding="utf-8")
        self.assertIn("angularDamping = 0.05", text)
        self.assertIn("linearDamping = 0\n", text)
        self.assertNotIn("elsewhere", (tmp / "out" / "config/editor.cfg").read_text(encoding="utf-8"))   # any drive (desktop TEMP is E:)
        self.assertIn((tmp / "out" / "mods_source").resolve().as_posix(),
                      (tmp / "out" / "config/editor.cfg").read_text(encoding="utf-8"))
        written = {w["member"]: w for w in report["written"]}
        self.assertTrue(written["models/k.tpl.asset/k.tpl_markup"]["patched"])
        self.assertTrue((tmp / "out" / "overlay.json").is_file())
        with self.assertRaises(po.OverlayError):
            po.overlay(project, pak, tmp / "out")                      # never overwrites
        library = ('initialChunkTruckWheels   =   {\r\n   k   =   {\r\n      wheels   =   {\r\n         old   =   {\r\n'
                   '            __type   =   "TruckWheelDesc"\r\n         }\r\n      }\r\n'
                   '      __type   =   "AutoKTruckWheelInfoX1"\r\n   }\r\n}\r\n__type   =   "TrucksWheelsLibrary"\r\n')
        sso = ('wheels   =   {\r\n   old   =   {\r\n      __type   =   "TruckWheelDesc"\r\n   }\r\n'
               '   ramp   =   {\r\n      __type   =   "TruckWheelDesc"\r\n   }\r\n}\r\n__type   =   "TruckWheels"\r\n')
        synced, entries = po.sync_library(library, {"AutoKTruckWheelInfoX1": sso})
        self.assertEqual(entries, ["k"])
        self.assertIn('         ramp   =   {\r\n            __type   =   "TruckWheelDesc"', synced)
        self.assertIn('      __type   =   "AutoKTruckWheelInfoX1"\r\n   }\r\n}', synced)
        self.assertNotIn('"TruckWheels"\r\n   }', synced)
        self.assertEqual(synced.count("{"), synced.count("}"))
        self.assertEqual(po.sync_library(library, {}), (library, []))
        bad = tmp / "bad.pak"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("a.txt", "1")
            z.writestr("a.txt", "2")
        with self.assertRaises(po.OverlayError):
            po.read_members(bad)

    def test_overlay_keeps_identical_members_linked(self):
        import zipfile
        from roadcraft import pak_overlay as po
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        ms = tmp / "project" / "mods_source"
        (ms / "autogen_dw/trucks/auto_k").mkdir(parents=True)
        (ms / "autogen_dw/trucks/auto_k/auto_k.cls").write_text("old class\n", encoding="utf-8")
        (ms / "textures").mkdir()
        (ms / "textures/big.tga").write_bytes(b"\1" * 64)
        (ms / "textures/changed.tga").write_bytes(b"\1" * 64)
        pak = tmp / "k.pak"
        with zipfile.ZipFile(pak, "w") as z:
            z.writestr("ssl/auto_k_x1.cls", "new class\n")
            z.writestr("textures/big.tga", b"\1" * 64)        # same bytes as the project: stays a hard link
            z.writestr("textures/changed.tga", b"\2" * 64)
        report = po.overlay(tmp / "project", pak, tmp / "out")
        out = tmp / "out" / "mods_source"
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["keptLinked"], 1)
        self.assertTrue(os.path.samefile(out / "textures/big.tga", ms / "textures/big.tga"))
        self.assertFalse(os.path.samefile(out / "textures/changed.tga", ms / "textures/changed.tga"))
        self.assertEqual((ms / "textures/changed.tga").read_bytes(), b"\1" * 64)          # source untouched
        self.assertEqual((out / "textures/changed.tga").read_bytes(), b"\2" * 64)


class SeriesSpringTests(unittest.TestCase):
    """Mammoth series-spring bench additions: terrain and prismatic probes (checked at rest before use), wheel
    depth below the ground, sprung-body poses and joint limits, a screenshot at the end of a run, linked copies."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        FakeSession.instances = []
        FakeSession.clock = VirtualClock()
        fake_engine.STATE.__init__()
        self.project = self.tmp / "project"
        scene = self.project / "mods_source" / "xscenes/mods/pad/pad.scn"
        scene.parent.mkdir(parents=True)
        scene.write_text(PAD_SCENE, encoding="utf-8")
        scene.with_name("pad.scn.resource").write_text("__type: res_xscn_desc\n", encoding="utf-8")
        (self.project / "mods_source" / "big.bin").write_bytes(b"\0" * 4096)

    def scenario(self):
        return custom_scenario(
            durationSeconds=12, scene={"file": "xscenes/mods/pad/pad.scn", "settleSeconds": 1},
            inputs={"method": "Debug", "schedule": [{"at": 0, "phase": "parked", "handbrake": "On"}]},
            spawn={"method": "scene", "scene": "xscenes/mods/pad/pad.scn", "vehicle": "test_vehicle",
                   "position": [0, 60.3, -18]},
            vehicle={"hull": "BoneChassis_cdt", "wheelNames": ["FR", "FL", "RR", "RL"]},
            probes={"rateHz": 10, "items": ["bodies", "wheels", "joints", "terrain", "linear", "load"],
                    "readback": True},
            capture={"cameras": [{"name": "side", "offset": [12, 3, -6]}]},
            analysis={"groundHeight": 0.0, "sprung": {"bodies": {"BoneChassis_cdt": [0, 0, 0]},
                                                       "joints": {"SuspFrontLeft": [-0.05, 0.2]}}})

    def run_cli(self, *extra):
        path = self.tmp / "s.json"
        path.write_text(json.dumps(self.scenario()), encoding="utf-8")
        out = io.StringIO()
        code = bh.main(["run", str(path), "--out", str(self.tmp / "o"), "--strategy", "project-copy", "--project",
                        str(self.project), "--owner-approved", "test", "--game-root", str(self.tmp / "game"), *extra],
                       factory=FakeSession, clock=FakeSession.clock, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(code, 0, report)
        return report["runs"][0], FakeSession.instances[0]

    def test_probe_statements(self):
        script = bh.probe_script(["wheels", "terrain", "linear"])
        self.assertIn('StringFormat("H %i %.4f\\n", hi, GetTerrain().GetHeight(hinfo.transform.GetPosition()))', script)
        self.assertIn(" if lj.IsPositional()", script)
        self.assertIn("lj.GetCurrentPosition()", script)
        self.assertNotIn("GetTerrain", bh.probe_script(["wheels"]))
        self.assertIn("if plv != null", bh.probe_script(["load"]))
        self.assertNotIn("PropLoadVolume", script)
        self.assertTrue(all(ord(c) < 128 for c in script))
        self.assertIn("l.min, l.max", bh.readback_scripts()["limits"])

    def test_run_checks_probes_measures_depth_and_screenshots_at_the_end(self):
        run, session = self.run_cli("--link-copy")
        folder = self.tmp / "o" / "candidate"
        checks = json.loads((folder / "probe_checks.json").read_text(encoding="utf-8"))
        self.assertTrue(checks["items"]["terrain"]["ok"] and checks["items"]["linear"]["ok"])
        self.assertEqual(checks["kept"], ["bodies", "wheels", "joints", "terrain", "linear", "load"])
        for name in ("terrain.csv", "linear.csv", "wheels.csv", "load.csv"):
            self.assertTrue((folder / name).is_file(), name)
        summary = run["summary"]
        fr = summary["wheelGround"]["wheels"]["FR"]   # fake wheel: centre y 0.4, radius 0.6, terrain 0.05, pad 0
        self.assertAlmostEqual(fr["depthM"]["median"], 0.25, places=4)
        self.assertAlmostEqual(fr["depthBelowTerrainM"]["median"], 0.25, places=4)
        self.assertEqual(fr["sunkSamples"], fr["samples"])
        joint = summary["sprung"]["joints"]["SuspFrontLeft"]
        self.assertEqual(joint["unit"], "m")
        self.assertAlmostEqual(joint["oscillation"]["hz"], 1.0, delta=0.1)
        self.assertGreater(joint["atMinSamples"], 0)
        self.assertEqual(summary["sprung"]["joints"]["hinge_blade"]["unit"], "deg")
        self.assertAlmostEqual(summary["stillness"]["rollDeg"]["oscillation"]["hz"], 1.0, delta=0.1)
        self.assertIsNone(summary["stillness"]["settledAfterS"])
        self.assertAlmostEqual(summary["sprung"]["bodies"]["BoneChassis_cdt"]["upFromModelledM"]["max"], 0.0, places=4)
        shots = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
        self.assertTrue((folder / "as_loaded__side.png").is_file())
        self.assertNotIn("error", shots[0])
        last_probe = max(i for i, s in enumerate(session.scripts) if "GetBodyCount" in s)
        shot_at = [i for i, s in enumerate(session.scripts) if "SaveScreenshot(" in s and "as_loaded__side" in s]
        self.assertEqual(len(shot_at), 1)
        self.assertGreater(shot_at[0], last_probe)
        private = folder / "root" / "mods_source"
        self.assertTrue(os.path.samefile(private / "big.bin", self.project / "mods_source" / "big.bin"))
        self.assertIn("60.3", (private / "xscenes/mods/pad/pad.scn").read_text(encoding="utf-8"))
        self.assertNotIn("60.3", (self.project / "mods_source/xscenes/mods/pad/pad.scn").read_text(encoding="utf-8"))

    def test_a_rejected_probe_is_left_out_of_the_run(self):
        with mock.patch.dict(os.environ, {"RC_FAKE_NO_TERRAIN": "1"}):
            run, session = self.run_cli()
        folder = self.tmp / "o" / "candidate"
        checks = json.loads((folder / "probe_checks.json").read_text(encoding="utf-8"))
        self.assertFalse(checks["items"]["terrain"]["ok"])
        self.assertIn("error 2059", checks["items"]["terrain"]["reply"])
        self.assertNotIn("terrain", checks["kept"])
        probes = [s for s in session.scripts if "GetBodyCount" in s]
        self.assertTrue(probes and not any("GetTerrain" in s for s in probes))
        self.assertFalse((folder / "terrain.csv").exists())
        self.assertTrue((folder / "linear.csv").is_file())
        self.assertFalse(run["summary"]["wheelGround"]["terrainProbe"])     # the pad height alone
        self.assertAlmostEqual(run["summary"]["wheelGround"]["wheels"]["RL"]["depthM"]["median"], 0.2, places=4)
        self.assertFalse(os.path.samefile(folder / "root/mods_source/big.bin", self.project / "mods_source/big.bin"))

    def test_readback_parses_prismatic_positions_and_layers(self):
        parsed = bh.parse_readback({
            "limits": "RB_LIMITS\nl SuspRearRoll -0.06981 0.06981\n",
            "positional": "RB_POSITIONAL\np SuspFrontLeft -0.08500 -0.23000 0.20000\n",
            "layers": "RB_LAYERS\ny BoneChassis_cdt default 3\ny BoneSuspRear_cdt no_collision 3\n"})
        self.assertEqual(parsed["constraints"]["SuspFrontLeft"], {"position": -0.085, "linearLimits": [-0.23, 0.2]})
        self.assertEqual(parsed["constraints"]["SuspRearRoll"]["limits"], [-0.06981, 0.06981])
        self.assertEqual(parsed["bodyLayers"]["BoneSuspRear_cdt"], {"layer": "no_collision", "system": 3})

    def test_readback_filters_and_load(self):
        parsed = bh.parse_readback({
            "filters": "RB_FILTERS\ns constr_vhc 1\nf BoneChassis_cdt constr_vhc 1 0 0\nf BoneLid_cdt no_collision 1 0 1\n",
            "load": "RB_LOAD\nv 218000.0 218000.0 120.5000 120.5000\n"})
        self.assertEqual(parsed["filters"]["system"], {"layer": "constr_vhc", "system": 1})
        self.assertEqual(parsed["filters"]["bodies"]["BoneChassis_cdt"],
                         {"layer": "constr_vhc", "system": 1, "inDefault": False, "inNoSelfCollision": False})
        self.assertTrue(parsed["filters"]["bodies"]["BoneLid_cdt"]["inNoSelfCollision"])
        self.assertEqual(parsed["load"]["mass"], 218000.0)
        self.assertIsNone(bh.parse_readback({"load": "RB_LOAD\nnone\n"})["load"])
        scripts = bh.readback_scripts()
        # only the two names every subsystem table holds (an unknown name logs "subsystem %s doesnt exist")
        self.assertEqual(sorted(set(re.findall(r'IsInSubsystem\("([^"]+)"\)', scripts["filters"]))),
                         ["default", "no_self_collision"])
        self.assertIn("if lv == null", scripts["load"])

    def test_sprung_spec_is_validated(self):
        for bad in ({"bodies": {"x y": None}}, {"bodies": {"B": [0, 1]}}, {"joints": {"J": [0]}}, {"other": 1}):
            with self.assertRaises(bh.ScenarioError):
                bh.load_scenario(custom_scenario(analysis={"sprung": bad}))
        named = bh.load_scenario(custom_scenario(analysis={"sprung": {"joints": {"BoneA_cdt|BoneB_cdt": [-0.2, 0.2]}}}))
        self.assertIn("BoneA_cdt|BoneB_cdt", named["analysis"]["sprung"]["joints"])   # engine's child|parent names
        ok = bh.load_scenario(custom_scenario(analysis={"sprung": {"bodies": ["A", "B"]}, "groundHeight": 60}))
        self.assertEqual(ok["analysis"]["sprung"], {"bodies": {"A": None, "B": None}, "joints": {}})
        self.assertEqual(ok["analysis"]["groundHeight"], 60.0)


if __name__ == "__main__":
    unittest.main()
