"""Synthetic success and failure chains for the read-only AAA capture postflight."""

from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import native_capture_postflight as postflight  # noqa: E402


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
        self.candidate_sha = self.write_bytes(self.candidate, b"candidate")
        self.baseline_sha = self.write_bytes(self.installed, b"baseline")
        self.backup = self.native / f"cat_d11t_before_{self.baseline_sha[:12]}_{self.run_id}.pak"
        self.write_bytes(self.backup, b"baseline")
        self.receipt = self.native / f"candidate_capture_{self.run_id}.json"
        self.make_receipts()

    @staticmethod
    def write_bytes(path: Path, data: bytes) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return sha256(data).hexdigest()

    @staticmethod
    def write_json(path: Path, data: dict) -> str:
        return NativeCapturePostflightTests.write_bytes(
            path, json.dumps(data, sort_keys=True).encode("utf-8"))

    def make_receipts(self) -> None:
        pins = {"source.usf": sha256(b"source").hexdigest()}
        variants = []
        for variant in postflight.VARIANTS:
            run = self.native / "runs" / f"aaa_{variant}_{self.run_id}{variant[:2]}"
            views = []
            for view in postflight.VIEWS:
                image = run / f"cab_{view}.png"
                probe = run / f"camera_{view}.json"
                views.append({
                    "view": view,
                    "path": str(image),
                    "sha256": self.write_bytes(image, postflight.PNG_SIGNATURE +
                                                f"{variant}-{view}".encode()),
                    "cameraProbeSha256": self.write_json(probe, {"status": "captured"}),
                })
            nested = {
                "status": "D11_AAA_NATIVE_CAPTURES_READY",
                "variant": variant,
                "run": str(run),
                "candidatePackageSha256": self.candidate_sha,
                "sourcePins": pins,
                "viewSpecs": {name: [[0, 0, 0], [1, 0, 0]] for name in postflight.VIEWS},
                "views": views,
            }
            report = run / "report.json"
            variants.append({"variant": variant, "views": len(views),
                             "report": str(report),
                             "reportSha256": self.write_json(report, nested)})
        self.outer = {
            "status": "NATIVE_CAPTURES_READY_BASELINE_RESTORED",
            "runId": self.run_id,
            "prototype": False,
            "candidatePackage": str(self.candidate),
            "candidateSha256": self.candidate_sha,
            "installedPackage": str(self.installed),
            "baselineSha256": self.baseline_sha,
            "capturePlan": {"fullCapture": True, "variants": list(postflight.VARIANTS),
                            "viewsPerVariant": list(postflight.VIEWS)},
            "sourcePins": pins,
            "rollback": {"status": "BASELINE_RESTORED", "backup": str(self.backup),
                         "sha256": self.baseline_sha},
            "variants": variants,
        }
        self.write_json(self.receipt, self.outer)

    def validate(self) -> dict:
        return postflight.validate(
            self.receipt, run_id=self.run_id,
            candidate_package=self.candidate, candidate_sha256=self.candidate_sha,
            installed_package=self.installed, baseline_sha256=self.baseline_sha,
            installed_sha256=self.baseline_sha)

    def test_complete_chain_passes_without_acceptance_claim(self) -> None:
        report = self.validate()
        self.assertTrue(report["captureIntegrityPassed"], report)
        self.assertEqual(report["checkedViews"], 45)
        self.assertEqual(report["checkedCameraProbes"], 45)
        self.assertFalse(report["visualReviewed"])
        self.assertFalse(report["campaignAccepted"])

    def test_failed_capture_stays_failed_after_restoration(self) -> None:
        self.outer["status"] = "FAIL_ROLLBACK_PENDING"
        self.write_json(self.receipt, self.outer)
        report = self.validate()
        self.assertFalse(report["captureIntegrityPassed"])
        self.assertIn("did not complete", report["error"])

    def test_missing_view_fails(self) -> None:
        report_path = Path(self.outer["variants"][1]["report"])
        nested = json.loads(report_path.read_text())
        nested["views"].pop()
        self.outer["variants"][1]["reportSha256"] = self.write_json(report_path, nested)
        self.write_json(self.receipt, self.outer)
        self.assertIn("exactly fifteen views", self.validate()["error"])

    def test_nested_receipt_tampering_fails(self) -> None:
        report_path = Path(self.outer["variants"][0]["report"])
        with report_path.open("ab") as stream:
            stream.write(b" ")
        self.assertIn("SHA-256 mismatch", self.validate()["error"])

    def test_image_tampering_fails(self) -> None:
        image = self.native / "runs" / f"aaa_worn_{self.run_id}wo" / "cab_rear.png"
        image.write_bytes(postflight.PNG_SIGNATURE + b"changed")
        self.assertIn("wrong hash", self.validate()["error"])

    def test_installed_package_change_fails(self) -> None:
        self.installed.write_bytes(b"unexpected")
        self.assertIn("Installed package", self.validate()["error"])

    def test_external_receipt_pin_detects_outer_receipt_change(self) -> None:
        original = sha256(self.receipt.read_bytes()).hexdigest()
        self.outer["untrustedAddition"] = "changed"
        self.write_json(self.receipt, self.outer)
        report = postflight.validate(
            self.receipt, run_id=self.run_id,
            candidate_package=self.candidate, candidate_sha256=self.candidate_sha,
            installed_package=self.installed, baseline_sha256=self.baseline_sha,
            installed_sha256=self.baseline_sha,
            expected_capture_receipt_sha256=original)
        self.assertFalse(report["captureIntegrityPassed"])
        self.assertIn("external pin", report["error"])

    def test_cli_uses_nonzero_exit_for_failure(self) -> None:
        self.outer["status"] = "FAIL_ROLLBACK_PENDING"
        self.write_json(self.receipt, self.outer)
        argv = ["--capture-receipt", str(self.receipt), "--run-id", self.run_id,
                "--candidate-package", str(self.candidate),
                "--candidate-sha256", self.candidate_sha,
                "--installed-package", str(self.installed),
                "--baseline-sha256", self.baseline_sha,
                "--installed-sha256", self.baseline_sha]
        with redirect_stdout(io.StringIO()) as stream:
            code = postflight.main(argv)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stream.getvalue())["captureIntegrityPassed"])


if __name__ == "__main__":
    unittest.main()
