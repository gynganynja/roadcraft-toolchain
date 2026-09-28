"""Synthetic full AAA capture chains for the read-only postflight verifier."""

from __future__ import annotations

import base64
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from roadcraft import native_capture_partial, native_capture_postflight as postflight  # noqa: E402

MODULES = ("__init__.py", "native_capture_partial.py", "native_capture_observation.py",
           "native_capture_postflight.py", "review.py", "core.py")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical_sha(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def when(seconds: float) -> str:
    return (datetime(2026, 9, 28, tzinfo=timezone.utc) +
            timedelta(seconds=seconds)).isoformat()


def png() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + name + data +
                struct.pack(">I", zlib.crc32(name + data)))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\0\0\0\0\0")) + chunk(b"IEND", b""))


def response() -> str:
    return ("D11T_SYSTEMS_OK\npreviousResolution 1 1\n"
            "light d11_light pos 1 2 3 tangent 0 0 1 intensity 5 radius 30 cone 35\n"
            "spotStarted d11_light false\ncameraResolution 1 1\n"
            "cameraWorld pos 0.1 2 3 forward 0 0 1\n")


class NativeCapturePostflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.native = self.root / "native"
        self.native.mkdir()
        self.run_id = "abcdef12"
        self.candidate = self.root / "candidate.pak"
        self.installed = self.root / "installed.pak"
        self.candidate_sha = self.write(self.candidate, b"candidate")
        self.baseline_sha = self.write(self.installed, b"baseline")
        self.backup = self.native / f"cat_d11t_before_{self.baseline_sha[:12]}_{self.run_id}.pak"
        self.write(self.backup, b"baseline")
        self.receipt = self.native / f"candidate_capture_{self.run_id}.json"
        self.plan_path = self.root / "reviewed_plan.json"
        self.build()

    @staticmethod
    def write(path: Path, data: bytes) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return digest(data)

    def write_json(self, path: Path, value: dict) -> str:
        # Runner receipts preserve the declared output order; JSON key sorting
        # would reorder the hash roster before postflight can check it.
        return self.write(path, json.dumps(value).encode())

    def roster(self) -> list[Path]:
        paths = [self.receipt, self.backup]
        for variant in postflight.VARIANTS:
            run = self.native / "runs" / f"aaa_{variant}_{self.run_id}{variant[:2]}"
            paths.extend(run / name for name in (
                "native_controls.ps1", "probe.scenario", "stdout.log", "stderr.log",
                "report.json", "interior_geom.json", "interior_geom.transport.log"))
            for view in postflight.VIEWS:
                paths.extend(run / name for name in (
                    f"camera_{view}.json", f"camera_{view}.transport.log",
                    f"pre_capture_{view}.json", f"pre_capture_{view}.transport.log",
                    f"capture_{view}.json", f"capture_{view}.transport.log",
                    f"cab_{view}.png", f"partial_{view}.json"))
        self.assertEqual(len(paths), 383)
        return paths

    @staticmethod
    def snapshot(editor: int, engine: int) -> dict:
        return {
            "editorPid": editor, "enginePid": engine, "engineExit": {"status": "running"},
            "ownedProcesses": [
                {"pid": editor, "parentPid": 0, "name": "IntegrationStudio.exe"},
                {"pid": engine, "parentPid": editor, "name": "Roadcraft ModEditor.exe"}],
        }

    def event(self, label: str, editor: int, engine: int, start: float, end: float,
              view: str | None = None) -> dict:
        row = {"action": label, "status": "PASS", "editorPid": editor,
               "enginePid": engine, "startedUtc": when(start), "finishedUtc": when(end),
               "ownedBefore": self.snapshot(editor, engine),
               "ownedAfter": self.snapshot(editor, engine)}
        if view is not None:
            row["view"] = view
        return row

    def transport(self, path: Path, mode: str, engine: int, helper_sha: str,
                  sent: float, received: float, serial: int, script: str) -> str:
        answer = response()
        raw = answer.encode() + b"\0"
        return self.write_json(path, {
            "schema": 1, "status": "pass", "stage": "response_received",
            "mode": mode, "readOnly": mode == "Read", "engineProcessId": engine,
            "helperSha256": helper_sha, "workspace": "RoadBuilder",
            "requestId": f"{{{serial:08X}-ABCD-4abc-8ABC-ABCDEF123456}}",
            "requestSentUtc": when(sent), "receivedUtc": when(received),
            "script": script, "response": answer,
            "responseBase64": base64.b64encode(raw).decode(),
            "responseBytes": len(raw),
        })

    def build(self, repeat_pre_id: bool = False,
              reverse_second_view_time: bool = False) -> None:
        pins = {"source.usf": digest(b"source")}
        contexts, runs = {}, {}
        for variant in postflight.VARIANTS:
            run = self.native / "runs" / f"aaa_{variant}_{self.run_id}{variant[:2]}"
            runs[variant] = run
            scene_name = f"d11t_{variant}_validation"
            scene = (self.root / "p/mods_source/xscenes/mods" / scene_name /
                     f"{scene_name}.scn")
            contexts[variant] = {
                "scene": str(scene), "sceneSha256": self.write(scene, variant.encode()),
                "cameraSpecs": {view: [[0, 0, 0], [1, 0, 0]]
                                for view in postflight.VIEWS},
            }
        runner = self.root / "runner.py"
        runner_sha = self.write(runner, b"synthetic runner")
        helpers = {}
        for name in ("nativeControlsTemplate", "nativeAcceptance", "interiorCapture",
                     "cabSurvey", "syntaxCheck"):
            path = self.root / "helper_sources" / name
            helpers[name] = {"path": str(path), "sha256": self.write(path, name.encode())}
        required = self.roster()
        capture_plan = {"fullCapture": True, "variants": list(postflight.VARIANTS),
                        "viewsPerVariant": list(postflight.VIEWS)}
        contract = {
            "schemaVersion": 1, "runId": self.run_id, "runner": str(runner),
            "runnerSha256": runner_sha,
            "candidatePackage": str(self.candidate), "candidateSha256": self.candidate_sha,
            "installedPackage": str(self.installed), "baselineSha256": self.baseline_sha,
            "prototype": False, "capturePlan": capture_plan,
            "sourcePinCount": len(pins), "sourcePinsSha256": canonical_sha(pins),
            "variantContexts": contexts,
            "variantRuns": {variant: str(run) for variant, run in runs.items()},
            "outerReceipt": str(self.receipt), "backup": str(self.backup),
            "expectedOutputFiles": [str(path) for path in required],
            "partialLinkerSource": str(SRC),
            "partialLinkerSourcePins": {
                f"roadcraft/{name}": digest((SRC / "roadcraft" / name).read_bytes())
                for name in MODULES},
            "helperSourcePins": helpers,
        }
        self.contract_sha = canonical_sha(contract)
        self.plan = {"status": "CAPTURE_OUTPUTS_DECLARED_NO_SWAP",
                     "outputContract": contract,
                     "outputContractSha256": self.contract_sha}
        self.plan_sha = self.write_json(self.plan_path, self.plan)

        rows = []
        for variant_index, variant in enumerate(postflight.VARIANTS):
            run = runs[variant]
            editor, engine = 2000 + variant_index, 3000 + variant_index
            helper = run / "native_controls.ps1"
            helper_sha = self.write(helper, f"helper {variant}".encode())
            self.write(run / "probe.scenario", b"scenario")
            self.write(run / "stdout.log", b"stdout")
            self.write(run / "stderr.log", b"")
            self.write_json(run / "interior_geom.json", {"status": "pass"})
            self.write(run / "interior_geom.transport.log", b"geometry log")
            actions = [self.event("InspectInteriorGeom", editor, engine, 0, 1)]
            boundaries, views = [], []
            for index, view in enumerate(postflight.VIEWS):
                t = 5 if reverse_second_view_time and index == 1 else 10 + index * 10
                mode = view.title().replace("_", "")
                labels = (("SetCab" + mode, 0, .8),
                          ("SettleCamera", .8, 1.5),
                          ("ScreenshotSourceGuard", 1.5, 1.6),
                          ("ReadPreCapture", 1.6, 2.2),
                          ("CaptureCab" + mode, 2.3, 3.2),
                          ("SaveScreenshot:" + view, 3.3, 4))
                view_actions = [self.event(label, editor, engine, t + start, t + end, view)
                                for label, start, end in labels]
                actions.extend(view_actions)
                boundaries.append({"view": view, "status": "PASS",
                                   "startedUtc": when(t - .1),
                                   "finishedUtc": when(t + 4.1),
                                   "ownedBefore": self.snapshot(editor, engine),
                                   "ownedAfter": self.snapshot(editor, engine)})
                serial = (variant_index * len(postflight.VIEWS) + index) * 3 + 1
                pre_serial = 2 if repeat_pre_id and variant_index == 0 and index == 1 \
                    else serial + 1
                camera = run / f"camera_{view}.json"
                pre = run / f"pre_capture_{view}.json"
                capture = run / f"capture_{view}.json"
                camera_sha = self.transport(camera, "SetCab" + mode, engine, helper_sha,
                                            t + .1, t + .2, serial, "return result")
                pre_sha = self.transport(pre, "Read", engine, helper_sha,
                                         t + 1.8, t + 2, pre_serial, "return result")
                trigger = (f'SaveScreenshot(ScreenshotSaveTarget.FILE,'
                           f'"d11_cab_{self.run_id}{variant[:2]}_{view}",'
                           'false,ScreenshotFormat.PNG)\nreturn result')
                capture_sha = self.transport(capture, "CaptureCab" + mode, engine,
                                             helper_sha, t + 2.5, t + 3,
                                             serial + 2, trigger)
                camera_log_sha = self.write(run / f"camera_{view}.transport.log", b"camera log")
                pre_log_sha = self.write(run / f"pre_capture_{view}.transport.log", b"pre log")
                capture_log_sha = self.write(run / f"capture_{view}.transport.log", b"capture log")
                image = run / f"cab_{view}.png"
                image_sha = self.write(image, png())
                partial = native_capture_partial.build_partial_view(
                    run_id=self.run_id, variant=variant, view=view, engine_pid=engine,
                    scene=Path(contexts[variant]["scene"]), helper=helper,
                    camera_transport=camera, pre_transport=pre,
                    capture_transport=capture, image=image, action_events=view_actions)
                partial_path = run / f"partial_{view}.json"
                partial_sha = self.write_json(partial_path, partial)
                views.append({
                    "view": view, "path": str(image), "sha256": image_sha,
                    "resolutionPixels": [1, 1],
                    "cameraProbeSha256": camera_sha,
                    "cameraTransportLogSha256": camera_log_sha,
                    "preCaptureProbeSha256": pre_sha,
                    "preCaptureTransportLogSha256": pre_log_sha,
                    "captureProbeSha256": capture_sha,
                    "captureTransportLogSha256": capture_log_sha,
                    "partialViewLinkPath": str(partial_path),
                    "partialViewLinkSha256": partial_sha,
                })
            nested = {
                "status": "D11_AAA_NATIVE_CAPTURES_READY", "variant": variant,
                "run": str(run), "scene": contexts[variant]["scene"],
                "candidatePackageSha256": self.candidate_sha,
                "sourcePins": pins, "outputContractSha256": self.contract_sha,
                "captureContext": contexts[variant], "helperSha256": helper_sha,
                "editorPid": editor, "enginePid": engine,
                "viewSpecs": contexts[variant]["cameraSpecs"],
                "views": views, "actionEvents": actions, "viewEvents": boundaries,
            }
            report = run / "report.json"
            report_sha = self.write_json(report, nested)
            links = [{"view": row["view"], "path": row["partialViewLinkPath"],
                      "sha256": row["partialViewLinkSha256"]} for row in views]
            rows.append({"variant": variant, "views": len(views), "report": str(report),
                         "reportSha256": report_sha,
                         "partialViewLinksSha256": canonical_sha(links)})
        hashes = {str(path): digest(path.read_bytes()) for path in required[1:]}
        self.assertEqual(len(hashes), 382)
        self.outer = {
            "status": "NATIVE_CAPTURES_READY_BASELINE_RESTORED",
            "runId": self.run_id, "prototype": False,
            "candidatePackage": str(self.candidate), "candidateSha256": self.candidate_sha,
            "installedPackage": str(self.installed), "baselineSha256": self.baseline_sha,
            "capturePlan": capture_plan, "sourcePins": pins,
            "outputContractSha256": self.contract_sha,
            "requiredOutputSha256": hashes,
            "rollback": {"status": "BASELINE_RESTORED", "backup": str(self.backup),
                         "sha256": self.baseline_sha},
            "variants": rows,
        }
        self.write_json(self.receipt, self.outer)

    def validate(self, *, plan_sha: str | None = None,
                 receipt_sha: str | None = None) -> dict:
        return postflight.validate(
            self.receipt, run_id=self.run_id,
            candidate_package=self.candidate, candidate_sha256=self.candidate_sha,
            installed_package=self.installed, baseline_sha256=self.baseline_sha,
            installed_sha256=self.baseline_sha,
            capture_plan=self.plan_path, capture_plan_sha256=plan_sha or self.plan_sha,
            expected_capture_receipt_sha256=receipt_sha)

    def reseal_nested(self, index: int, nested: dict) -> None:
        row = self.outer["variants"][index]
        path = Path(row["report"])
        report_sha = self.write_json(path, nested)
        row["reportSha256"] = report_sha
        self.outer["requiredOutputSha256"][str(path)] = report_sha
        self.write_json(self.receipt, self.outer)

    def test_complete_chain_passes_without_acceptance_claim(self) -> None:
        report = self.validate()
        self.assertTrue(report["captureIntegrityPassed"], report)
        self.assertEqual(report["checkedViews"], 45)
        self.assertEqual(report["checkedCameraProbes"], 45)
        self.assertEqual(report["checkedPartialViews"], 45)
        self.assertEqual(report["checkedRequiredOutputs"], 382)
        self.assertFalse(report["pairProtocolEligible"])
        self.assertFalse(report["captureProcessAuthenticated"])
        self.assertFalse(report["visualReviewed"])
        self.assertFalse(report["campaignAccepted"])

    def test_failed_capture_stays_failed_after_restoration(self) -> None:
        self.outer["status"] = "FAIL_ROLLBACK_PENDING"
        self.write_json(self.receipt, self.outer)
        self.assertIn("did not complete", self.validate()["error"])

    def test_missing_view_fails(self) -> None:
        path = Path(self.outer["variants"][1]["report"])
        nested = json.loads(path.read_text())
        nested["views"].pop()
        self.reseal_nested(1, nested)
        self.assertIn("exactly fifteen views", self.validate()["error"])

    def test_nested_receipt_tampering_fails(self) -> None:
        path = Path(self.outer["variants"][0]["report"])
        path.write_bytes(path.read_bytes() + b" ")
        self.assertIn("wrong hash", self.validate()["error"])

    def test_image_tampering_fails(self) -> None:
        image = self.native / "runs" / f"aaa_worn_{self.run_id}wo" / "cab_rear.png"
        image.write_bytes(postflight.PNG_SIGNATURE + b"changed")
        self.assertIn("wrong hash", self.validate()["error"])

    def test_missing_or_changed_partial_fails(self) -> None:
        partial = self.native / "runs" / f"aaa_nearnew_{self.run_id}ne" / "partial_right.json"
        original = partial.read_bytes()
        partial.unlink()
        self.assertIn("missing", self.validate()["error"])
        partial.write_bytes(original + b" ")
        self.assertIn("wrong hash", self.validate()["error"])

    def test_replayed_request_id_fails(self) -> None:
        self.build(repeat_pre_id=True)
        self.assertIn("repeats a transport request ID", self.validate()["error"])

    def test_interleaved_action_transcript_fails_after_resealing(self) -> None:
        path = Path(self.outer["variants"][0]["report"])
        nested = json.loads(path.read_text())
        nested["actionEvents"][1], nested["actionEvents"][7] = (
            nested["actionEvents"][7], nested["actionEvents"][1])
        self.reseal_nested(0, nested)
        report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"], report)
        self.assertRegex(report["error"], "chronology|consecutive")

    def test_cross_view_reversed_utc_timestamps_fail(self) -> None:
        self.build(reverse_second_view_time=True)
        report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"], report)

    def test_malformed_view_boundary_utc_fails_after_resealing(self) -> None:
        path = Path(self.outer["variants"][0]["report"])
        nested = json.loads(path.read_text())
        nested["viewEvents"][0]["startedUtc"] = "0"
        nested["viewEvents"][0]["finishedUtc"] = "zzzz"
        self.reseal_nested(0, nested)
        report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"], report)

    def test_invalid_view_boundary_process_snapshot_fails(self) -> None:
        path = Path(self.outer["variants"][0]["report"])
        nested = json.loads(path.read_text())
        nested["viewEvents"][0]["ownedBefore"]["engineExit"]["status"] = "exited"
        self.reseal_nested(0, nested)
        report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"], report)

    def test_imported_partial_linker_must_be_the_pinned_source(self) -> None:
        other = self.root / "unreviewed" / "native_capture_partial.py"
        other.parent.mkdir()
        other.write_bytes((SRC / "roadcraft/native_capture_partial.py").read_bytes())
        with mock.patch.object(native_capture_partial, "__file__", str(other)):
            report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"], report)

    def test_plan_hash_and_contract_roster_tamper_fail(self) -> None:
        original = self.plan_sha
        self.plan["unreviewedAddition"] = True
        self.write_json(self.plan_path, self.plan)
        self.assertIn("SHA-256 mismatch", self.validate(plan_sha=original)["error"])
        del self.plan["unreviewedAddition"]
        self.plan["outputContract"]["expectedOutputFiles"].pop()
        changed_sha = self.write_json(self.plan_path, self.plan)
        self.assertIn("output contract SHA-256 mismatch",
                      self.validate(plan_sha=changed_sha)["error"])
        self.plan["outputContractSha256"] = canonical_sha(self.plan["outputContract"])
        changed_sha = self.write_json(self.plan_path, self.plan)
        self.assertIn("required output roster", self.validate(plan_sha=changed_sha)["error"])

    def test_non_view_required_output_tamper_fails(self) -> None:
        log = self.native / "runs" / f"aaa_maroon_{self.run_id}ma" / "stdout.log"
        log.write_bytes(b"modified stdout")
        self.assertIn("wrong hash", self.validate()["error"])

    def test_installed_package_change_fails(self) -> None:
        self.installed.write_bytes(b"unexpected")
        self.assertIn("Installed package", self.validate()["error"])

    def test_external_receipt_pin_detects_change(self) -> None:
        original = digest(self.receipt.read_bytes())
        self.outer["untrustedAddition"] = "changed"
        self.write_json(self.receipt, self.outer)
        self.assertIn("external pin", self.validate(receipt_sha=original)["error"])

    def test_cli_uses_nonzero_exit_for_failure(self) -> None:
        self.outer["status"] = "FAIL_ROLLBACK_PENDING"
        self.write_json(self.receipt, self.outer)
        argv = ["--capture-receipt", str(self.receipt), "--run-id", self.run_id,
                "--candidate-package", str(self.candidate),
                "--candidate-sha256", self.candidate_sha,
                "--installed-package", str(self.installed),
                "--baseline-sha256", self.baseline_sha,
                "--installed-sha256", self.baseline_sha,
                "--capture-plan", str(self.plan_path),
                "--capture-plan-sha256", self.plan_sha]
        with redirect_stdout(io.StringIO()) as stream:
            code = postflight.main(argv)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stream.getvalue())["captureIntegrityPassed"])


if __name__ == "__main__":
    unittest.main()
