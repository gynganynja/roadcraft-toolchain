"""Synthetic contract checks for the pinned legacy AAA capture runner.

These tests import the review copy of the runner. They never launch an editor,
write an installed package, or perform a native capture.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


RUNNER = (Path(__file__).resolve().parents[1] / "operations" / "patches" /
          "capture_candidate_native.patched.py")


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

    def test_predeclares_exact_full_capture_without_writing(self) -> None:
        contract = self.contract()
        self.assertEqual(contract["runId"], "abcdef12")
        self.assertEqual(len(contract["expectedOutputFiles"]), 248)
        self.assertEqual(len(contract["optionalOutputFiles"]), 6)
        self.assertEqual(len(contract["transientPaths"]), 10)
        self.assertEqual(len(contract["screenshotSourceFiles"]), 45)
        self.assertEqual(len(contract["runtimeDirectoryRoots"]), 3)
        self.assertEqual(contract["lock"], str(self.runner.LOCK))
        self.assertEqual(len(set(contract["expectedOutputFiles"])), 248)
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
        self.assertEqual(len(plan["outputContract"]["expectedOutputFiles"]), 248)
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
        base = SimpleNamespace(processes=lambda: [
            {"ProcessId": 42, "ParentProcessId": 0,
             "Name": "IntegrationStudio.exe"},
            {"ProcessId": 43, "ParentProcessId": 42,
             "Name": "Roadcraft ModEditor.exe"},
        ])
        report = {}
        self.runner.timed_action(report, base, proc, 43, "SetCabRight", lambda: None)
        with self.assertRaisesRegex(ValueError, "lost engine"):
            self.runner.timed_action(report, base, proc, 43, "CaptureCabRight",
                                     lambda: (_ for _ in ()).throw(ValueError("lost engine")))
        passed, failed = report["actionEvents"]
        self.assertEqual((passed["status"], failed["status"]), ("PASS", "FAIL"))
        self.assertEqual(failed["editorExitCode"], -1)
        self.assertEqual([item["pid"] for item in failed["ownedProcessesAfter"]],
                         [42, 43])
        self.assertTrue(passed["startedUtc"] <= passed["finishedUtc"])

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
