"""Synthetic source/package/capture/metric chains for the D11 release gate."""

from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import regression  # noqa: E402


def png(color: tuple[int, int, int]) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + name + data +
                struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\0" + bytes(color) * 2) * 2)) +
            chunk(b"IEND", b""))


class RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = {"variant": "nearnew", "scene": "lane", "camera": "driver",
                        "lighting": "fixed-day", "resolution": [2, 2], "protocol": "v1"}

    def write(self, name: str, value: bytes | dict) -> dict[str, str]:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, dict):
            content = json.dumps(value, sort_keys=True).encode()
        else:
            content = value
        path.write_bytes(content)
        return {"path": str(path), "sha256": sha256(content).hexdigest()}

    def fixture(self, *, candidate_context: dict | None = None, candidate_value: float = 11,
                candidate_status: str = "CAPTURE_READY", candidate_view: str = "driver",
                include_threshold: bool = True) -> dict:
        source_file = self.write("source.usf", b"source")
        source = self.write("source.json", {"status": "SOURCE_READY", "files": [
            {"path": "source.usf", "sha256": source_file["sha256"], "bytes": 6}]})
        baseline_package = self.write("baseline.pak", b"baseline")
        candidate_package = self.write("candidate.pak", b"candidate")
        package_receipt = self.write("package.json", {
            "status": "PACKAGE_AUDITED", "sourceSha256": source["sha256"],
            "baselinePackageSha256": baseline_package["sha256"],
            "candidatePackageSha256": candidate_package["sha256"],
        })
        before_image = self.write("before.png", png((20, 60, 100)))
        after_image = self.write("after.png", png((25, 65, 105)))
        baseline_capture = self.write("baseline_capture.json", {
            "status": "CAPTURE_READY", "context": self.context,
            "packageSha256": baseline_package["sha256"],
            "captures": [{"view": "driver", **before_image}],
        })
        candidate_capture = self.write("candidate_capture.json", {
            "status": candidate_status, "context": candidate_context or self.context,
            "packageSha256": candidate_package["sha256"],
            "acceptance": {"visual": {"status": "approved", "reviewer": "Unverified"}},
            "captures": [{"view": candidate_view, **after_image}],
        })
        baseline_metric = self.write("baseline_metric.json", {
            "status": "METRIC_READY", "context": self.context,
            "captureReceiptSha256": baseline_capture["sha256"],
            "metrics": [{"name": "yaw_per_m", "unit": "deg/m", "value": 10}],
        })
        candidate_metric = self.write("candidate_metric.json", {
            "status": "METRIC_READY", "context": candidate_context or self.context,
            "captureReceiptSha256": candidate_capture["sha256"],
            "metrics": [{"name": "yaw_per_m", "unit": "deg/m", "value": candidate_value}],
        })
        artifacts = {
            "source": {"kind": "source", "sourceFormat": "files-manifest",
                       "sourceRoot": str(self.root), **source},
            "baselinePackage": {"kind": "package", "role": "baseline", **baseline_package},
            "candidatePackage": {"kind": "package", "role": "candidate", **candidate_package},
            "packageReceipt": {"kind": "package-receipt", "allowedStatuses": ["PACKAGE_AUDITED"],
                               **package_receipt},
            "baselineCapture": {"kind": "capture", "role": "baseline",
                                "allowedStatuses": ["CAPTURE_READY"], **baseline_capture},
            "candidateCapture": {"kind": "capture", "role": "candidate",
                                 "allowedStatuses": ["CAPTURE_READY"], **candidate_capture},
            "baselineMetric": {"kind": "metric", "role": "baseline",
                               "allowedStatuses": ["METRIC_READY"], **baseline_metric},
            "candidateMetric": {"kind": "metric", "role": "candidate",
                                "allowedStatuses": ["METRIC_READY"], **candidate_metric},
        }
        links = [
            {"receipt": "packageReceipt", "field": "sourceSha256", "artifact": "source"},
            {"receipt": "packageReceipt", "field": "baselinePackageSha256", "artifact": "baselinePackage"},
            {"receipt": "packageReceipt", "field": "candidatePackageSha256", "artifact": "candidatePackage"},
            {"receipt": "baselineCapture", "field": "packageSha256", "artifact": "baselinePackage"},
            {"receipt": "candidateCapture", "field": "packageSha256", "artifact": "candidatePackage"},
            {"receipt": "baselineMetric", "field": "captureReceiptSha256", "artifact": "baselineCapture"},
            {"receipt": "candidateMetric", "field": "captureReceiptSha256", "artifact": "candidateCapture"},
        ]
        return {"schemaVersion": 1, "artifacts": artifacts, "links": links,
                "requiredViews": [{"view": "driver", "context": self.context}],
                "thresholds": ([{"name": "yaw_per_m", "unit": "deg/m", "context": self.context,
                                 "candidateMax": 12, "deltaMax": 2}]
                               if include_threshold else [])}

    def evaluate(self, policy: dict, *, trusted_keys: dict | None = None) -> dict:
        return regression.evaluate(policy, base_dir=self.root, trusted_keys=trusted_keys)

    def signed_policy(self) -> tuple[dict, dict, object]:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("cryptography Ed25519 verifier unavailable")
        policy = self.fixture()
        preliminary = self.evaluate(policy)
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        trusted = {"External reviewer": base64.b64encode(public).decode()}
        candidate = policy["artifacts"]["candidatePackage"]["sha256"]
        policy["approvals"] = {}
        for stage in ("visual", "campaign"):
            evidence = self.write(f"{stage}_review.md", (
                f"{stage} review of candidate {candidate}\n"
                "Observed evidence and accepted the result.\n").encode())
            claim = {"stage": stage, "decision": "approved", "reviewer": "External reviewer",
                     "signedAtUtc": "2026-09-28T00:00:00+00:00",
                     "candidatePackageSha256": candidate,
                     "gateDigest": preliminary["gateDigest"],
                     "evidence": {"path": f"{stage}_review.md", "sha256": evidence["sha256"]}}
            self.write_approval(policy, stage, claim, private)
        return policy, trusted, private

    def write_approval(self, policy: dict, stage: str, claim: dict,
                       private: object, *, signature: bytes | None = None) -> None:
        signed = signature if signature is not None else private.sign(regression._canonical(claim))
        policy["approvals"][stage] = self.write(f"{stage}_approval.json", {
            "schemaVersion": 1, "claim": claim,
            "signature": base64.b64encode(signed).decode(),
        })

    def test_pinned_chain_views_and_threshold_pass_but_acceptance_pending(self) -> None:
        result = self.evaluate(self.fixture())
        self.assertTrue(result["chain"]["passed"])
        self.assertEqual(result["matchedCapturePairs"], 1)
        self.assertEqual(result["matchedMetricPairs"], 1)
        self.assertTrue(result["views"][0]["passed"])
        self.assertTrue(result["thresholds"][0]["passed"])
        self.assertTrue(result["technicalPassed"])
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["state"], "pending")
        self.assertEqual(result["acceptance"]["campaign"]["state"], "pending")

    def test_context_and_required_view_fail_closed(self) -> None:
        context = {**self.context, "lighting": "other"}
        result = self.evaluate(self.fixture(candidate_context=context))
        self.assertFalse(result["views"][0]["passed"])
        self.assertFalse(result["thresholds"][0]["passed"])
        self.assertFalse(result["technicalPassed"])
        result = self.evaluate(self.fixture(candidate_view="rear"))
        self.assertFalse(result["views"][0]["passed"])

    def test_threshold_and_failed_capture_status_block_technical_pass(self) -> None:
        result = self.evaluate(self.fixture(candidate_value=20))
        self.assertFalse(result["thresholds"][0]["passed"])
        self.assertIn("candidateMax failed", result["thresholds"][0]["reason"])
        result = self.evaluate(self.fixture(candidate_status="FAIL_ROLLBACK_PENDING"))
        self.assertFalse(result["chain"]["passed"])
        self.assertFalse(result["technicalPassed"])

    def test_identical_scene_files_can_be_declared_equivalent(self) -> None:
        baseline_scene = self.write("baseline_scene.scn", b"same scene")
        candidate_scene = self.write("candidate_scene.scn", b"same scene")
        self.context = {**self.context, "scene": baseline_scene["path"]}
        candidate_context = {**self.context, "scene": candidate_scene["path"]}
        policy = self.fixture(candidate_context=candidate_context)
        self.assertFalse(self.evaluate(policy)["technicalPassed"])
        policy["sceneEquivalences"] = [{"sceneId": "lane-equal", "baseline": baseline_scene,
                                        "candidate": candidate_scene}]
        policy["requiredViews"][0]["context"]["scene"] = "lane-equal"
        policy["thresholds"][0]["context"]["scene"] = "lane-equal"
        result = self.evaluate(policy)
        self.assertTrue(result["technicalPassed"])
        candidate_scene_path = Path(candidate_scene["path"])
        candidate_scene_path.write_bytes(b"changed scene")
        with self.assertRaisesRegex(regression.RegressionError, "Scene equivalence changed"):
            self.evaluate(policy)

    def test_tampered_pin_and_broken_link_are_rejected_or_reported(self) -> None:
        policy = self.fixture()
        image = self.root / "after.png"
        image.write_bytes(png((1, 2, 3)))
        with self.assertRaisesRegex(regression.RegressionError, "SHA-256 mismatch"):
            self.evaluate(policy)
        policy = self.fixture()
        policy["links"][0]["field"] = "missingSourceSha256"
        result = self.evaluate(policy)
        self.assertFalse(result["chain"]["passed"])
        self.assertTrue(any("does not pin" in reason for reason in result["chain"]["reasons"]))

    def test_signed_visual_and_campaign_claims_bind_gate_candidate_and_evidence(self) -> None:
        policy, trusted, _private = self.signed_policy()
        self.assertFalse(self.evaluate(policy)["releaseReady"])
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertTrue(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["state"], "approved")
        self.assertEqual(result["acceptance"]["visual"]["evidence"]["path"],
                         str(self.root / "visual_review.md"))
        trusted["External reviewer"] = base64.b64encode(b"x" * 32).decode()
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["state"], "pending")

    def test_legacy_signed_claim_without_human_evidence_stays_pending(self) -> None:
        policy, trusted, private = self.signed_policy()
        receipt = json.loads((self.root / "visual_approval.json").read_text())
        claim = receipt["claim"]
        del claim["evidence"]
        self.write_approval(policy, "visual", claim, private)
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertTrue(result["technicalPassed"])
        self.assertFalse(result["releaseReady"])
        self.assertIn("does not pin human review evidence",
                      result["acceptance"]["visual"]["reason"])
        self.assertEqual(result["acceptance"]["campaign"]["state"], "approved")

    def test_missing_or_changed_human_evidence_stays_pending(self) -> None:
        policy, trusted, _private = self.signed_policy()
        visual = self.root / "visual_review.md"
        visual.write_text("A changed visual review", encoding="utf-8")
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertIn("SHA-256 mismatch", result["acceptance"]["visual"]["reason"])
        self.assertEqual(result["acceptance"]["campaign"]["state"], "approved")
        visual.unlink()
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertIn("Cannot read evidence", result["acceptance"]["visual"]["reason"])

    def test_forged_evidence_pointer_breaks_detached_signature(self) -> None:
        policy, trusted, private = self.signed_policy()
        receipt = json.loads((self.root / "campaign_approval.json").read_text())
        claim = receipt["claim"]
        forged = self.write("forged_campaign_review.md", b"No real campaign review\n")
        claim["evidence"] = {"path": "forged_campaign_review.md", "sha256": forged["sha256"]}
        old_signature = base64.b64decode(receipt["signature"])
        self.write_approval(policy, "campaign", claim, private, signature=old_signature)
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["state"], "approved")
        self.assertEqual(result["acceptance"]["campaign"]["reason"],
                         "Detached signature is invalid")

    def test_signed_empty_human_evidence_stays_pending(self) -> None:
        policy, trusted, private = self.signed_policy()
        receipt = json.loads((self.root / "visual_approval.json").read_text())
        claim = receipt["claim"]
        empty = self.write("empty_visual_review.md", b"  \n")
        claim["evidence"] = {"path": "empty_visual_review.md", "sha256": empty["sha256"]}
        self.write_approval(policy, "visual", claim, private)
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["reason"],
                         "Human review evidence is empty")

    def test_campaign_cannot_reuse_visual_review_evidence(self) -> None:
        policy, trusted, private = self.signed_policy()
        campaign = json.loads((self.root / "campaign_approval.json").read_text())["claim"]
        visual = json.loads((self.root / "visual_approval.json").read_text())["claim"]
        campaign["evidence"] = visual["evidence"]
        self.write_approval(policy, "campaign", campaign, private)
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["state"], "approved")
        self.assertEqual(result["acceptance"]["campaign"]["reason"],
                         "Campaign review evidence duplicates visual review evidence")

    def test_signed_claim_with_extra_unreviewed_field_stays_pending(self) -> None:
        policy, trusted, private = self.signed_policy()
        claim = json.loads((self.root / "visual_approval.json").read_text())["claim"]
        claim["unreviewed"] = True
        self.write_approval(policy, "visual", claim, private)
        result = self.evaluate(policy, trusted_keys=trusted)
        self.assertFalse(result["releaseReady"])
        self.assertEqual(result["acceptance"]["visual"]["reason"],
                         "Approval claim has unexpected fields")


if __name__ == "__main__":
    unittest.main()
