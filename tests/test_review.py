"""Meaningful integrity, comparability and acceptance-boundary checks."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


MODULE = Path(__file__).resolve().parents[1] / "src" / "roadcraft" / "review.py"
SPEC = importlib.util.spec_from_file_location("roadcraft_review_under_test", MODULE)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def png(width=2, height=2, color=(30, 80, 120)):
    def chunk(name, data):
        return (struct.pack(">I", len(data)) + name + data +
                struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF))
    rows = (b"\0" + bytes(color) * width) * height
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = {"variant": "nearnew", "scene": "soft_lane_v1", "camera": {"eye": [1, 2, 3]},
                        "lighting": "day-fixed-v1", "resolution": [2, 2], "protocol": "straight-auto-v2"}

    def tearDown(self):
        self.temp.cleanup()

    def receipt(self, name, role="baseline", *, context=None, changes=None, value=10):
        image = self.root / f"{name}.png"
        image.write_bytes(png(color=(value, 50, 90)))
        data = {"role": role, "label": name, "context": copy.deepcopy(context or self.context),
                "captures": [{"path": image.name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                              "view": "driver"}],
                "metrics": [{"name": "tail speed", "value": value, "unit": "km/h"}]}
        if changes:
            data.update(changes)
        return self.write_receipt(name, data)

    def write_receipt(self, name, data):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return {"path": path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def report(self, sources, name="output"):
        return review.generate_report(sources, self.root / name)

    def test_matched_receipts_embed_images_and_compare_without_acceptance(self):
        result = self.report([self.receipt("before"), self.receipt("after", "candidate", value=15)])
        self.assertEqual(len(result["captureComparisons"]), 1)
        self.assertEqual(result["metricComparisons"][0]["delta"], 5)
        self.assertEqual(result["metricComparisons"][0]["percentChange"], 50)
        self.assertEqual(result["evidence"]["visual"]["state"], "not_assessed_by_report")
        self.assertEqual(result["evidence"]["campaign"]["state"], "not_assessed_by_report")
        html = Path(result["artifacts"]["html"]).read_bytes()
        self.assertIn(b"data:image/png;base64,", html)
        self.assertEqual(hashlib.sha256(html).hexdigest(), result["artifacts"]["htmlSha256"])
        self.assertEqual(json.loads(Path(result["artifacts"]["manifest"]).read_text()), result)

    def test_each_context_mismatch_prevents_comparison(self):
        for field in review.CONTEXT_FIELDS:
            with self.subTest(field=field):
                candidate = copy.deepcopy(self.context)
                if field == "resolution":
                    # Resolution declarations must agree with the actual bytes.
                    candidate[field] = [3, 2]
                    with self.assertRaisesRegex(review.ReviewError, "resolution"):
                        self.report([self.receipt("before"), self.receipt("after", "candidate", context=candidate)], field)
                    continue
                candidate[field] = "different"
                result = self.report([self.receipt("before"), self.receipt("after", "candidate", context=candidate)], field)
                self.assertEqual(result["captureComparisons"], [])
                self.assertEqual(result["metricComparisons"], [])

    def test_missing_context_allows_contact_sheet_only(self):
        context = copy.deepcopy(self.context)
        del context["lighting"]
        result = self.report([self.receipt("before", context=context),
                              self.receipt("after", "candidate", context=context)])
        self.assertEqual(len(result["captures"]), 2)
        self.assertFalse(result["captureComparisons"])
        self.assertIn("lighting", result["captures"][0]["missingContext"])

    def test_actual_different_image_resolution_does_not_compare(self):
        before = self.receipt("before")
        candidate_context = copy.deepcopy(self.context)
        candidate_context["resolution"] = [3, 2]
        after = self.receipt("after", "candidate", context=candidate_context)
        image = self.root / "after.png"
        image.write_bytes(png(width=3))
        data = json.loads(after["path"].read_text())
        data["captures"][0]["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
        after = self.write_receipt("after", data)
        result = self.report([before, after])
        self.assertFalse(result["captureComparisons"])
        self.assertFalse(result["metricComparisons"])

    def test_context_resolution_type_is_validated(self):
        context = copy.deepcopy(self.context)
        context["resolution"] = "2x2"
        with self.assertRaisesRegex(review.ReviewError, "resolution"):
            self.report([self.receipt("before", context=context)])

    def test_snapshot_hash_is_not_a_seal(self):
        before = self.receipt("before")
        after = self.receipt("after", "candidate")
        result = self.report([before["path"], after["path"]])
        self.assertTrue(all(not row["chainVerified"] for row in result["receipts"]))
        self.assertFalse(result["captureComparisons"])
        self.assertFalse(result["metricComparisons"])

    def test_tampered_receipt_or_capture_rejected_before_output(self):
        sealed = self.receipt("before")
        sealed["path"].write_text(sealed["path"].read_text() + " ")
        with self.assertRaisesRegex(review.ReviewError, "SHA-256 mismatch"):
            self.report([sealed])
        self.assertFalse((self.root / "output").exists())
        sealed = self.receipt("before")
        (self.root / "before.png").write_bytes(png(color=(1, 2, 3)))
        with self.assertRaisesRegex(review.ReviewError, "SHA-256 mismatch"):
            self.report([sealed])
        self.assertFalse((self.root / "output").exists())

    def test_native_aggregate_verifies_nested_report_hash(self):
        child = self.receipt("child")
        child_data = json.loads(child["path"].read_text())
        child_data["views"] = child_data.pop("captures")
        child = self.write_receipt("child", child_data)
        parent = self.write_receipt("parent", {"variants": [{"variant": "nearnew", "report": "child.json",
                                                              "reportSha256": child["sha256"]}]})
        result = self.report([parent])
        self.assertEqual(len(result["captures"]), 1)
        self.assertTrue(all(row["chainVerified"] for row in result["receipts"]))
        child["path"].write_text(child["path"].read_text() + " ")
        with self.assertRaisesRegex(review.ReviewError, "SHA-256 mismatch"):
            self.report([parent], "bad")

    def test_unpinned_parent_does_not_authenticate_children(self):
        child = self.receipt("child")
        parent = self.write_receipt("parent", {"variants": [{"report": "child.json", "reportSha256": child["sha256"]}]})
        result = self.report([parent["path"]])
        self.assertFalse(result["captures"][0]["receiptVerified"])

    def test_ambiguous_pair_and_different_units_are_not_compared(self):
        sources = [self.receipt("a"), self.receipt("b"), self.receipt("c", "candidate")]
        result = self.report(sources)
        self.assertFalse(result["captureComparisons"])
        self.assertFalse(result["metricComparisons"])
        candidate = self.receipt("c", "candidate", changes={"metrics": [{"name": "tail speed", "value": 2, "unit": "m/s"}]})
        result = self.report([sources[0], candidate], "units")
        self.assertTrue(result["captureComparisons"])
        self.assertFalse(result["metricComparisons"])

    def test_claims_remain_attributed_and_html_text_is_escaped(self):
        source = self.receipt("a", changes={"label": '<script>alert("bad")</script>',
                                           "status": "VISUAL_APPROVED",
                                           "acceptance": {"visual": {"status": "approved", "reviewer": "Tester"}}})
        result = self.report([source])
        self.assertEqual(result["evidence"]["campaign"]["claims"], [])
        self.assertEqual(result["evidence"]["visual"]["claims"][0]["claim"]["status"], "approved")
        html = Path(result["artifacts"]["html"]).read_text()
        self.assertNotIn('<script>alert(', html)
        self.assertIn('&lt;script&gt;', html)

    def test_missing_image_pin_and_existing_output_refused(self):
        source = self.receipt("a")
        data = json.loads(source["path"].read_text())
        data["captures"][0].pop("sha256")
        bad = self.write_receipt("bad", data)
        with self.assertRaisesRegex(review.ReviewError, "SHA-256 pin"):
            self.report([bad])
        self.report([source])
        with self.assertRaisesRegex(review.ReviewError, "already exists"):
            self.report([source])

    def test_zero_baseline_and_nonfinite_metric(self):
        result = self.report([self.receipt("a", value=0), self.receipt("b", "candidate", value=2)])
        self.assertIsNone(result["metricComparisons"][0]["percentChange"])
        source = self.receipt("bad", changes={"metrics": [{"name": "x", "value": float("nan"), "unit": "m"}]})
        with self.assertRaisesRegex(review.ReviewError, "Non-finite"):
            self.report([source], "nonfinite")

    def test_legacy_visual_review_is_not_campaign_acceptance(self):
        source = self.receipt("a")
        data = json.loads(source["path"].read_text())
        data.pop("context")
        data["status"] = "VISIBLE_TREADS_REVIEWED"
        data["observations"] = ["Tread bars visible on private soft lane"]
        legacy = self.write_receipt("legacy", data)
        result = self.report([legacy])
        self.assertEqual(len(result["evidence"]["visual"]["claims"]), 1)
        self.assertFalse(result["evidence"]["campaign"]["claims"])
        self.assertFalse(result["captureComparisons"])


if __name__ == "__main__":
    unittest.main()
