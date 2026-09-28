"""Synthetic contract checks for the pinned legacy AAA capture runner.

These tests import the review copy of the runner. They never launch an editor,
write an installed package, or perform a native capture.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import difflib
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


RUNNER = (Path(__file__).resolve().parents[1] / "operations" / "patches" /
          "capture_candidate_native.pretrigger_20260928.py")


def load_runner():
    spec = importlib.util.spec_from_file_location("reviewed_aaa_capture", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeCaptureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runner = load_runner()
        self.runner.NATIVE = self.root / "native"
        self.runner.RUNS = self.runner.NATIVE / "runs"
        self.runner.LOCK = self.runner.NATIVE / "candidate_capture.lock.json"
        self.runner.WORKSPACE = self.root / "sdk" / "workspace"
        self.runner.PROJECT = self.root / "candidate_project"
        workspace = self.root / "reviewed_helper_sources"
        self.runner.TOOLCHAIN_SRC = RUNNER.parents[2] / "src"
        self.runner.HELPER_SOURCE_FILES = {
            "nativeControlsTemplate": workspace / "D11_Final_Candidate_20260925" /
                                      "native_controls_template.ps1",
            "nativeAcceptance": workspace / "D11_Final_Candidate_20260925" /
                                "native_acceptance.py",
            "interiorCapture": workspace / "D11_Interior_Repair_20260926" /
                               "capture_interior.py",
            "cabSurvey": workspace / "D11_Interior_Repair_20260926" /
                         "capture_cab_survey.py",
            "syntaxCheck": workspace / "D11_All_Repairs_20260925" /
                           "handling/syntax_check.ps1",
        }
        for name, path in self.runner.HELPER_SOURCE_FILES.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"synthetic pinned {name}".encode("utf-8"))
        self.runner.LIVE = self.root / "installed" / "cat_d11t.pak"
        self.runner.LIVE.parent.mkdir()
        self.runner.LIVE.write_bytes(b"accepted baseline")
        self.runner.EXPECTED_BASE_SHA = sha256(b"accepted baseline").hexdigest()
        self.candidate = self.root / "candidate.pak"
        self.candidate.write_bytes(b"AAA candidate")
        self.candidate_sha = sha256(self.candidate.read_bytes()).hexdigest()
        self.package_receipt = self.root / "package_receipt.json"
        self.package_receipt.write_bytes(b"sealed package receipt")
        self.pins = {"source.usf": sha256(b"source").hexdigest()}
        self.camera_specs = {view: ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
                             for view in self.runner.VIEWS}
        for scene in self.runner.SCENES.values():
            path = self.runner.PROJECT / "mods_source/xscenes/mods" / scene
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(scene.encode("utf-8"))

    def contract(self):
        return self.runner.capture_contract(
            "abcdef12", tuple(self.runner.SCENES), self.runner.VIEWS,
            self.candidate, self.candidate_sha, self.pins, self.camera_specs,
            prototype=False, package_receipt=self.package_receipt,
            package_receipt_sha=self.runner.sha(self.package_receipt),
            package_receipt_status="D11_AAA_PACKAGE_AUDITED")

    def test_current_patch_and_archival_plan_have_distinct_runner_pins(self) -> None:
        operations = RUNNER.parents[1]
        archived_manifest = json.loads((RUNNER.parent /
                                        "capture_candidate_native.patch_manifest.json").read_text(
                                            encoding="utf-8"))
        archived = RUNNER.parent / "capture_candidate_native.patched.py"
        self.assertEqual(sha256(archived.read_bytes()).hexdigest(),
                         archived_manifest["patchedSha256"])
        manifest = json.loads((RUNNER.parent /
                               "capture_candidate_native.pretrigger_20260928.patch_manifest.json").read_text(
                                   encoding="utf-8"))
        self.assertEqual(sha256(archived.read_bytes()).hexdigest(), manifest["baseSha256"])
        self.assertEqual(sha256(RUNNER.read_bytes()).hexdigest(),
                         manifest["patchedSha256"])
        expected_diff = "".join(difflib.unified_diff(
            archived.read_text(encoding="utf-8").splitlines(keepends=True),
            RUNNER.read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile=f"capture_candidate_native.py@{manifest['baseSha256'][:8]}",
            tofile=f"capture_candidate_native.py@{manifest['patchedSha256'][:8]}"))
        self.assertEqual((RUNNER.parent / manifest["patch"]).read_text(
                             encoding="utf-8"), expected_diff)
        plan = json.loads((operations /
                           "d11_aaa_native_capture_plan_c0de2026.json").read_text(
                               encoding="utf-8"))
        self.assertEqual(plan["status"], "CAPTURE_OUTPUTS_DECLARED_NO_SWAP")
        self.assertEqual(plan["outputContract"]["runnerSha256"],
                         archived_manifest["patchedSha256"])
        self.assertNotEqual(plan["outputContract"]["runnerSha256"],
                            manifest["patchedSha256"])
        self.assertEqual(self.runner.canonical_sha256(plan["outputContract"]),
                         plan["outputContractSha256"])
        self.assertEqual(len(plan["outputContract"]["expectedOutputFiles"]), 383)

    def test_predeclares_exact_full_capture_without_writing(self) -> None:
        contract = self.contract()
        self.assertEqual(contract["runId"], "abcdef12")
        self.assertEqual(len(contract["expectedOutputFiles"]), 383)
        self.assertEqual(len(contract["optionalOutputFiles"]), 6)
        self.assertEqual(len(contract["transientPaths"]), 10)
        self.assertEqual(len(contract["screenshotSourceFiles"]), 45)
        self.assertEqual(len(contract["runtimeDirectoryRoots"]), 3)
        self.assertEqual(contract["lock"], str(self.runner.LOCK))
        self.assertEqual(len(set(contract["expectedOutputFiles"])), 383)
        self.assertEqual(contract["partialLinkerSource"], str(self.runner.TOOLCHAIN_SRC))
        self.assertEqual(contract["partialLinkerSourcePins"],
                         self.runner.partial_linker_source_pins())
        self.assertEqual(contract["helperSourcePins"],
                         self.runner.helper_source_pins())
        self.assertEqual(contract["sourcePinCount"], 1)
        self.assertFalse(contract["prototype"])
        self.assertEqual(contract["packageReceipt"], str(self.package_receipt))
        self.assertEqual(contract["packageReceiptSha256"],
                         self.runner.sha(self.package_receipt))
        self.assertTrue(contract["capturePlan"]["fullCapture"])
        for variant in self.runner.SCENES:
            context = contract["variantContexts"][variant]
            self.assertEqual(len(context["cameraSpecs"]), 15)
            self.assertEqual(context["plannedResolutionPixels"], {"status": "unknown"})
            self.assertEqual(context["runtimeLighting"], {"status": "unknown"})
            self.assertEqual(context["sceneSha256"],
                             self.runner.sha(Path(context["scene"])))
            run = Path(contract["variantRuns"][variant])
            expected = set(contract["expectedOutputFiles"])
            for view in self.runner.VIEWS:
                self.assertIn(str(run / f"pre_capture_{view}.json"), expected)
                self.assertIn(str(run / f"pre_capture_{view}.transport.log"), expected)
                self.assertIn(str(run / f"partial_{view}.json"), expected)
        self.assertFalse(self.runner.NATIVE.exists())
        self.assertEqual(self.contract(), contract)
        changed = self.runner.capture_contract(
            "abcdef12", tuple(self.runner.SCENES), self.runner.VIEWS,
            self.candidate, self.candidate_sha, {"source.usf": "0" * 64},
            self.camera_specs, prototype=False,
            package_receipt=self.package_receipt,
            package_receipt_sha=self.runner.sha(self.package_receipt),
            package_receipt_status="D11_AAA_PACKAGE_AUDITED")
        self.assertNotEqual(self.runner.canonical_sha256(changed),
                            self.runner.canonical_sha256(contract))
        prototype = self.runner.capture_contract(
            "abcdef12", tuple(self.runner.SCENES), self.runner.VIEWS,
            self.candidate, self.candidate_sha, self.pins, self.camera_specs,
            prototype=True, package_receipt=self.package_receipt,
            package_receipt_sha=self.runner.sha(self.package_receipt),
            package_receipt_status="D11_AAA_TEXTURE_PROTO_PACKAGE_AUDITED")
        self.assertNotEqual(self.runner.canonical_sha256(prototype),
                            self.runner.canonical_sha256(contract))

    def test_partial_linker_requires_reviewed_local_source(self) -> None:
        pins = self.runner.partial_linker_source_pins()
        module = self.runner.load_partial_linker(pins)
        self.assertEqual(Path(module.__file__).resolve(),
                         (self.runner.TOOLCHAIN_SRC / "roadcraft" /
                          "native_capture_partial.py").resolve())
        forged = dict(pins)
        forged["roadcraft/native_capture_partial.py"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "changed since the capture plan"):
            self.runner.load_partial_linker(forged)

    def test_partial_link_receipt_is_written_once_and_verified(self) -> None:
        target = self.root / "partial_front_seat.json"
        observed = []

        def verify(saved):
            observed.append(saved)
            return {"status": "PARTIAL_VIEW_LINKAGE_CONSISTENT",
                    "pairProtocolEligible": False}

        record = {"status": "PARTIAL_PRE_SCREENSHOT_CONTEXT",
                  "pairProtocolEligible": False}
        digest = self.runner.save_partial_link(
            target, record, SimpleNamespace(verify_partial_view=verify))
        self.assertEqual(digest, sha256(target.read_bytes()).hexdigest())
        self.assertEqual(observed, [record])
        with self.assertRaises(FileExistsError):
            self.runner.save_partial_link(
                target, record, SimpleNamespace(verify_partial_view=verify))

    def test_outer_output_digests_cover_exact_roster_except_self(self) -> None:
        outer = self.root / "candidate_capture_abcdef12.json"
        helper = self.root / "native_controls.ps1"
        image = self.root / "cab_front_seat.png"
        helper.write_bytes(b"helper")
        image.write_bytes(b"image")
        contract = {"outerReceipt": str(outer),
                    "expectedOutputFiles": [str(outer), str(helper), str(image)]}
        self.assertEqual(self.runner.required_output_digests(contract), {
            str(helper): sha256(b"helper").hexdigest(),
            str(image): sha256(b"image").hexdigest(),
        })
        image.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing or linked"):
            self.runner.required_output_digests(contract)
        image.write_bytes(b"image")
        with self.assertRaisesRegex(RuntimeError, "roster is inconsistent"):
            self.runner.required_output_digests({
                **contract,
                "expectedOutputFiles": contract["expectedOutputFiles"] + [str(helper)],
            })

    def test_variant_records_pre_capture_read_and_six_event_partial_link(self) -> None:
        run_id = "abcdef12ma"
        view = "front_seat"
        run = self.runner.RUNS / f"aaa_maroon_{run_id}"
        helper = run / "native_controls.ps1"
        probe_modes = []
        partial_calls = []
        pretrigger_calls = []
        proc = SimpleNamespace(pid=42, poll=lambda: None)

        def launch_editor(run_path, _scenario):
            (run_path / "stdout.log").write_text(
                f"D11_STANDALONE_READY_{run_id}\n", encoding="utf-8")
            (run_path / "stderr.log").write_text("", encoding="utf-8")
            return proc, None, None

        def probe(run_path, label, _helper, _pid, mode):
            probe_modes.append((label, mode))
            (run_path / f"{label}.json").write_text("{}", encoding="utf-8")
            (run_path / f"{label}.transport.log").write_text("ok", encoding="utf-8")

        def build_partial_view(**inputs):
            partial_calls.append(inputs)
            return {"pairProtocolEligible": False,
                    "loadedSceneVerified": False,
                    "nativePostflightVerified": False,
                    "status": "PARTIAL_PRE_SCREENSHOT_CONTEXT"}

        def check_pretrigger_view(**inputs):
            pretrigger_calls.append(inputs)
            return {"status": "PARTIAL_PRETRIGGER_CHECK_PASSED",
                    "loadedSceneVerified": False,
                    "captureProcessAuthenticated": False,
                    "pairProtocolEligible": False}

        def screenshot(_source, target, _proc):
            target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" +
                               (1920).to_bytes(4, "big") +
                               (1080).to_bytes(4, "big"))

        def snapshot(_base, _proc, _engine):
            return {"editorPid": 42, "editorExitCode": None, "enginePid": 43,
                    "engineExit": {"status": "running"},
                    "ownedProcesses": [{"pid": 43, "parentPid": 42,
                                        "name": "Roadcraft ModEditor.exe"}]}

        linker = SimpleNamespace(
            build_partial_view=build_partial_view,
            check_pretrigger_view=check_pretrigger_view,
            verify_partial_view=lambda _saved: {
                "status": "PARTIAL_VIEW_LINKAGE_CONSISTENT",
                "pairProtocolEligible": False,
            })
        engine = SimpleNamespace(pid=43, sample=lambda: {"status": "running"},
                                 close=lambda: None)
        base = SimpleNamespace(
            h=SimpleNamespace(launch_editor=launch_editor, probe=probe,
                              SDK=self.root / "sdk", EDITOR=self.root / "editor"),
            find_engine_pid=lambda _pid: 43,
            screenshot=screenshot)
        survey = SimpleNamespace(VIEWS={view: self.camera_specs[view]})
        pins = self.pins
        context = {"scene": str(self.runner.PROJECT / "mods_source/xscenes/mods" /
                                self.runner.SCENES["maroon"])}

        def controls(_base, _survey, run_path, _id):
            (run_path / "native_controls.ps1").write_text("helper", encoding="utf-8")
            return helper

        with ExitStack() as stack:
            stack.enter_context(patch.object(self.runner, "load_partial_linker",
                                             return_value=linker))
            stack.enter_context(patch.object(self.runner, "controls_with_geom_probe",
                                             side_effect=controls))
            stack.enter_context(patch.object(self.runner, "editor_mount",
                                             return_value={"status": "ok"}))
            stack.enter_context(patch.object(self.runner, "runtime_resource_mount",
                                             return_value={"status": "ok"}))
            stack.enter_context(patch.object(self.runner, "OwnedEngineHandle",
                                             return_value=engine))
            stack.enter_context(patch.object(self.runner, "owned_snapshot",
                                             side_effect=snapshot))
            stack.enter_context(patch.object(self.runner, "inspect_loaded_geom",
                                             return_value={"status": "ok"}))
            close = stack.enter_context(patch.object(self.runner, "close_owned_editor"))
            stack.enter_context(patch.object(self.runner, "project_pins",
                                             return_value=pins))
            stack.enter_context(patch.object(self.runner.time, "sleep"))
            stack.enter_context(patch.object(self.runner.shutil, "disk_usage",
                                             return_value=SimpleNamespace(free=10_000_000_000)))
            result = self.runner.capture_variant(
                base, survey, "maroon", run_id, self.runner.sha(self.runner.LIVE),
                pins, (view,), False, context, "a" * 64,
                self.runner.partial_linker_source_pins(),
                self.runner.helper_source_pins())
        report = json.loads((run / "report.json").read_text(encoding="utf-8"))
        close.assert_called_once_with(base, proc, (None, None), 43, engine)
        self.assertEqual(probe_modes, [
            ("camera_front_seat", "SetCabFrontSeat"),
            ("pre_capture_front_seat", "Read"),
            ("capture_front_seat", "CaptureCabFrontSeat"),
        ])
        self.assertEqual(len(pretrigger_calls), 2)
        self.assertEqual([row["phase"] for row in report["preTriggerChecks"]],
                         ["afterRead", "beforeCapture"])
        self.assertEqual([row["action"] for row in partial_calls[0]["action_events"]],
                         ["SetCabFrontSeat", "SettleCamera", "ScreenshotSourceGuard",
                          "ReadPreCapture", "CaptureCabFrontSeat",
                          "SaveScreenshot:front_seat"])
        self.assertEqual(partial_calls[0]["run_id"], "abcdef12")
        self.assertEqual(report["status"], "D11_AAA_NATIVE_TRIAGE_CAPTURES_READY")
        self.assertEqual(report["views"][0]["partialViewLinkPath"],
                         str(run / "partial_front_seat.json"))
        self.assertEqual(result["partialViewLinksSha256"],
                         self.runner.canonical_sha256([{
                             "view": view, "path": report["views"][0]["partialViewLinkPath"],
                             "sha256": report["views"][0]["partialViewLinkSha256"],
                         }]))

    def test_any_existing_run_artifact_refuses_id_reuse(self) -> None:
        contract = self.contract()
        paths = [Path(contract[key]) for key in
                 ("outerReceipt", "backup", "stage", "restore", "lock")]
        paths.extend((self.runner.NATIVE / "candidate_recovery_abcdef12.json",
                      Path(contract["variantRuns"]["nearnew"]),
                      Path(contract["transientPaths"][3]),
                      Path(contract["screenshotSourceFiles"][0])))
        for path in paths:
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                if path == Path(contract["variantRuns"]["nearnew"]):
                    path.mkdir()
                else:
                    path.write_bytes(b"earlier output")
                with self.assertRaisesRegex(RuntimeError, "existing outputs"):
                    self.contract()
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()

    def test_run_id_rejects_unsafe_or_malformed_names(self) -> None:
        for run_id in ("ABCDEF12", "123", "../a1234", "123456789", "1234abcd/other"):
            with self.subTest(run_id=run_id):
                with self.assertRaisesRegex(RuntimeError, "lowercase hexadecimal"):
                    self.runner.capture_contract(
                        run_id, tuple(self.runner.SCENES), self.runner.VIEWS,
                        self.candidate, self.candidate_sha, self.pins,
                        self.camera_specs, prototype=False,
                        package_receipt=self.package_receipt,
                        package_receipt_sha=self.runner.sha(self.package_receipt),
                        package_receipt_status="D11_AAA_PACKAGE_AUDITED")

    def test_owned_lock_allows_only_the_post_acquisition_recheck(self) -> None:
        contract = self.contract()
        self.runner.LOCK.parent.mkdir(parents=True)
        self.runner.LOCK.write_text("owned", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "existing outputs"):
            self.contract()
        rechecked = self.runner.capture_contract(
            "abcdef12", tuple(self.runner.SCENES), self.runner.VIEWS,
            self.candidate, self.candidate_sha, self.pins, self.camera_specs,
            prototype=False, package_receipt=self.package_receipt,
            package_receipt_sha=self.runner.sha(self.package_receipt),
            package_receipt_status="D11_AAA_PACKAGE_AUDITED", owned_lock=True)
        self.assertEqual(rechecked, contract)

    def test_real_plan_branch_is_no_write_and_requires_contract_pin(self) -> None:
        package_receipt = self.root / "package_receipt.json"
        package_receipt.write_text(json.dumps({
            "status": "D11_AAA_PACKAGE_AUDITED",
            "candidatePackageSha256": self.candidate_sha,
            "baselinePackageSha256": self.runner.EXPECTED_BASE_SHA,
            "candidatePackage": str(self.candidate),
        }), encoding="utf-8")
        self.runner.PACKAGE_RECEIPT = package_receipt
        base = SimpleNamespace(processes=lambda: [],
                               runner=SimpleNamespace(LOCK=self.root / "benchmark.lock"))
        survey = SimpleNamespace(VIEWS=self.camera_specs)
        argv = ["capture_candidate_native.py", "--candidate-pak", str(self.candidate),
                "--expected-candidate-sha", self.candidate_sha,
                "--run-id", "abcdef12", "--plan"]
        with (patch.object(self.runner, "old_helpers", return_value=(base, survey)),
              patch.object(self.runner, "project_pins", return_value=self.pins),
              patch.object(self.runner, "editor_mount", return_value={"status": "ok"}),
              patch.object(self.runner.shutil, "disk_usage",
                           return_value=SimpleNamespace(free=10_000_000_000)),
              patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as stream):
            self.runner.main()
        plan = json.loads(stream.getvalue())
        self.assertEqual(plan["status"], "CAPTURE_OUTPUTS_DECLARED_NO_SWAP")
        self.assertEqual(plan["outputContractSha256"],
                         self.runner.canonical_sha256(plan["outputContract"]))
        self.assertEqual(len(plan["outputContract"]["expectedOutputFiles"]), 383)
        self.assertFalse(self.runner.NATIVE.exists())
        self.assertEqual(self.runner.LIVE.read_bytes(), b"accepted baseline")

        argv = ["capture_candidate_native.py", "--candidate-pak", str(self.candidate),
                "--expected-candidate-sha", self.candidate_sha, "--execute"]
        with patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(RuntimeError, "require --run-id"):
                self.runner.main()
        argv = ["capture_candidate_native.py", "--candidate-pak", str(self.candidate),
                "--expected-candidate-sha", self.candidate_sha,
                "--expected-contract-sha256", "a" * 64]
        with patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(RuntimeError, "only valid with --execute"):
                self.runner.main()
        argv = ["capture_candidate_native.py", "--candidate-pak", str(self.candidate),
                "--expected-candidate-sha", self.candidate_sha,
                "--run-id", "abcdef12", "--execute",
                "--expected-contract-sha256", "0" * 64]
        with (patch.object(self.runner, "old_helpers", return_value=(base, survey)),
              patch.object(self.runner, "project_pins", return_value=self.pins),
              patch.object(self.runner, "editor_mount", return_value={"status": "ok"}),
              patch.object(self.runner.shutil, "disk_usage",
                           return_value=SimpleNamespace(free=10_000_000_000)),
              patch.object(sys, "argv", argv)):
            with self.assertRaisesRegex(RuntimeError, "contract changed since --plan"):
                self.runner.main()
        self.assertFalse(self.runner.NATIVE.exists())
        self.assertEqual(self.runner.LIVE.read_bytes(), b"accepted baseline")

    def test_exclusive_copy_cannot_replace_existing_artifact(self) -> None:
        target = self.root / "output.bin"
        target.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            self.runner.copy_exclusive(self.candidate, target)
        self.assertEqual(target.read_bytes(), b"old")

    def test_action_telemetry_keeps_owned_identity_and_failure(self) -> None:
        proc = SimpleNamespace(pid=42, poll=lambda: -1)
        engine = SimpleNamespace(pid=43, sample=lambda: {"status": "running"})
        base = SimpleNamespace(processes=lambda: [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            {"ProcessId": 43, "ParentProcessId": 42,
             "Name": "Roadcraft ModEditor.exe"},
        ])
        report = {}
        self.runner.timed_action(report, base, proc, engine, "SetCabRight",
                                 lambda: None, view="right")
        with self.assertRaisesRegex(ValueError, "lost engine"):
            self.runner.timed_action(
                report, base, proc, engine, "CaptureCabRight",
                lambda: (_ for _ in ()).throw(ValueError("lost engine")),
                view="right")
        passed, failed = report["actionEvents"]
        self.assertEqual((passed["status"], failed["status"]), ("PASS", "FAIL"))
        self.assertEqual((passed["view"], failed["view"]), ("right", "right"))
        self.assertEqual(failed["editorExitCode"], -1)
        self.assertEqual([item["pid"] for item in failed["ownedProcessesAfter"]],
                         [42, 43])
        self.assertTrue(passed["startedUtc"] <= passed["finishedUtc"])
        self.assertTrue(passed["ownedBefore"]["observedUtc"])
        self.assertEqual(failed["ownedAfter"]["engineExit"], {"status": "running"})

    def test_view_records_engine_exit_during_camera_settle(self) -> None:
        state = {"engineExited": False}
        engine = SimpleNamespace(
            pid=43, sample=lambda: (
                {"status": "exited", "exitCodeUnsigned": 0xC0000005,
                 "exitCodeHex": "0xc0000005"}
                if state["engineExited"] else {"status": "running"}))
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        base = SimpleNamespace(processes=lambda: [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            *([] if state["engineExited"] else [
                {"ProcessId": 43, "ParentProcessId": 42,
                 "Name": "Roadcraft ModEditor.exe"}]),
        ])
        report = {}

        def engine_exits() -> None:
            state["engineExited"] = True
            raise RuntimeError("engine disconnected during settle")

        with self.assertRaisesRegex(RuntimeError, "during settle"):
            with self.runner.view_boundary(report, base, proc, engine, "right_down"):
                self.runner.timed_action(report, base, proc, engine,
                                         "SetCabRightDown", lambda: None,
                                         view="right_down")
                self.runner.timed_action(report, base, proc, engine,
                                         "SettleCamera", engine_exits,
                                         view="right_down")
        view = report["viewEvents"][0]
        settle = report["actionEvents"][1]
        self.assertEqual(view["status"], "FAIL")
        self.assertEqual(settle["status"], "FAIL")
        self.assertEqual(settle["engineExitCode"], 0xC0000005)
        self.assertEqual(view["ownedAfter"]["engineExit"]["exitCodeHex"],
                         "0xc0000005")
        self.assertTrue(view["startedUtc"] <= view["finishedUtc"])

    def test_silent_engine_exit_during_settle_fails_that_action(self) -> None:
        state = {"engineExited": False}
        engine = SimpleNamespace(
            pid=43, sample=lambda: (
                {"status": "exited", "exitCodeUnsigned": 0xC0000005,
                 "exitCodeHex": "0xc0000005"}
                if state["engineExited"] else {"status": "running"}))
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        base = SimpleNamespace(processes=lambda: [])
        report = {}

        def silent_exit() -> None:
            state["engineExited"] = True

        with self.assertRaisesRegex(RuntimeError, "during SettleCamera"):
            self.runner.timed_action(report, base, proc, engine,
                                     "SettleCamera", silent_exit, view="right_down")
        event = report["actionEvents"][0]
        self.assertEqual(event["status"], "FAIL")
        self.assertEqual(event["engineExitCode"], 0xC0000005)
        self.assertIn("SettleCamera", event["error"])

    def test_pretrigger_guard_and_final_engine_sample_prevent_native_send(self) -> None:
        sent = []
        engine = SimpleNamespace(sample=lambda: {"status": "running"})
        with self.assertRaisesRegex(ValueError, "drifted Read"):
            self.runner.send_capture_after_pretrigger(
                lambda: (_ for _ in ()).throw(ValueError("drifted Read")),
                engine, lambda: sent.append(True))
        self.assertEqual(sent, [])
        exited = SimpleNamespace(sample=lambda: {"status": "exited"})
        with self.assertRaisesRegex(RuntimeError, "exited before CaptureCab"):
            self.runner.send_capture_after_pretrigger(
                lambda: None, exited, lambda: sent.append(True))
        self.assertEqual(sent, [])

    def test_action_refuses_command_if_retained_engine_already_exited(self) -> None:
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        engine = SimpleNamespace(pid=43, sample=lambda: {
            "status": "exited", "exitCodeUnsigned": 17,
            "exitCodeHex": "0x00000011"})
        base = SimpleNamespace(processes=lambda: [])
        invoked = []
        report = {}
        with self.assertRaisesRegex(RuntimeError, "not running before CaptureCabRight"):
            self.runner.timed_action(report, base, proc, engine, "CaptureCabRight",
                                     lambda: invoked.append(True), view="right")
        self.assertEqual(invoked, [])
        self.assertEqual(report["actionEvents"][0]["engineExitCode"], 17)
        self.assertEqual(report["actionEvents"][0]["status"], "FAIL")

    @unittest.skipUnless(os.name == "nt", "Windows process handle API")
    def test_retained_engine_handle_reports_exact_child_exit_code(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.2); raise SystemExit(17)"],
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            engine = self.runner.OwnedEngineHandle(child.pid)
            try:
                self.assertEqual(engine.sample(), {"status": "running"})
                self.assertEqual(child.wait(timeout=10), 17)
                self.assertEqual(engine.sample(),
                                 {"status": "exited", "exitCodeUnsigned": 17,
                                  "exitCodeHex": "0x00000011"})
            finally:
                engine.close()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)

    def test_early_cleanup_pins_and_rechecks_child_before_stop(self) -> None:
        rows = {
            42: {"ProcessId": 42, "ParentProcessId": 0,
                 "Name": "IntegrationStudio.exe"},
            43: {"ProcessId": 43, "ParentProcessId": 42,
                 "Name": "Roadcraft ModEditor.exe"},
        }
        events = []
        engine = SimpleNamespace(pid=43, close=lambda: events.append("close"))
        proc = SimpleNamespace(pid=42,
                               poll=lambda: None if 42 in rows else 0,
                               wait=lambda timeout: events.append("wait"))
        base = SimpleNamespace(
            processes=lambda: list(rows.values()),
            h=SimpleNamespace(PWSH=self.root / "pwsh.exe"))
        stream = io.BytesIO()

        def attach(pid):
            self.assertEqual(pid, 43)
            events.append("attach")
            return engine

        def stop(command, **_kwargs):
            script = command[-1]
            self.assertIn("attach", events)
            self.assertNotIn("close", events)
            pid = 43 if "Get-Process -Id 43 " in script else 42
            events.append(f"stop-{pid}")
            rows.pop(pid)
            return SimpleNamespace(returncode=0, stderr=b"")

        with patch.object(self.runner, "OwnedEngineHandle", side_effect=attach), \
             patch.object(self.runner.subprocess, "run", side_effect=stop):
            self.runner.close_owned_editor(base, proc, (stream,), None)
        self.assertEqual(events,
                         ["attach", "stop-43", "stop-42", "wait", "close"])
        self.assertTrue(stream.closed)

    def test_early_cleanup_fails_closed_if_child_handle_is_unavailable(self) -> None:
        rows = [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            {"ProcessId": 43, "ParentProcessId": 42,
             "Name": "Roadcraft ModEditor.exe"},
        ]
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        base = SimpleNamespace(processes=lambda: rows)
        stream = io.BytesIO()
        with patch.object(self.runner, "OwnedEngineHandle",
                          side_effect=OSError("OpenProcess denied")), \
             patch.object(self.runner.subprocess, "run") as stop:
            with self.assertRaisesRegex(OSError, "OpenProcess denied"):
                self.runner.close_owned_editor(base, proc, (stream,), None)
        stop.assert_not_called()
        self.assertTrue(stream.closed)

    def test_early_cleanup_rejects_unattached_orphan_child(self) -> None:
        rows = [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            {"ProcessId": 43, "ParentProcessId": 0,
             "Name": "Roadcraft ModEditor.exe"},
        ]
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        base = SimpleNamespace(processes=lambda: rows)
        stream = io.BytesIO()
        with patch.object(self.runner, "OwnedEngineHandle") as attach, \
             patch.object(self.runner.subprocess, "run") as stop:
            with self.assertRaisesRegex(RuntimeError,
                                        "parent is not the owned editor"):
                self.runner.close_owned_editor(base, proc, (stream,), 43)
        attach.assert_not_called()
        stop.assert_not_called()
        self.assertTrue(stream.closed)

    def test_early_cleanup_rechecks_identity_after_handle_attachment(self) -> None:
        census = [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            {"ProcessId": 43, "ParentProcessId": 42,
             "Name": "Roadcraft ModEditor.exe"},
        ]
        calls = []
        engine = SimpleNamespace(pid=43, close=lambda: calls.append("close"))

        def processes():
            calls.append("census")
            if calls.count("census") == 1:
                return census
            return [census[0], {**census[1], "ParentProcessId": 99}]

        base = SimpleNamespace(processes=processes)
        proc = SimpleNamespace(pid=42, poll=lambda: None)
        stream = io.BytesIO()
        with patch.object(self.runner, "OwnedEngineHandle",
                          return_value=engine), \
             patch.object(self.runner.subprocess, "run") as stop:
            with self.assertRaisesRegex(RuntimeError,
                                        "identity changed after handle attachment"):
                self.runner.close_owned_editor(base, proc, (stream,), None)
        stop.assert_not_called()
        self.assertEqual(calls, ["census", "census", "close"])
        self.assertTrue(stream.closed)

    def test_png_dimensions_are_observed_not_assumed(self) -> None:
        path = self.root / "capture.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" +
                         (1920).to_bytes(4, "big") + (1080).to_bytes(4, "big"))
        self.assertEqual(self.runner.png_dimensions(path), [1920, 1080])
        path.write_bytes(b"not a png")
        with self.assertRaisesRegex(RuntimeError, "PNG IHDR"):
            self.runner.png_dimensions(path)


if __name__ == "__main__":
    unittest.main()
