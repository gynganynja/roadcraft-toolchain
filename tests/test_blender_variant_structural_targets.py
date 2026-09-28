"""Reject false identical-target claims from the no-save D11 comparison."""

from __future__ import annotations

import copy
import unittest

from roadcraft import blender_variant_structural_targets as probe


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    rows = [{
        "asset": name, "repairedUsfSha256": sha,
        "structuralCount": 400, "sharedWithBase": 400,
        "baseOnlyPaths": [], "variantOnlyPaths": [],
        "matrixDifferentPathsOver1e5": [],
        "maxMatrixElementError": 0.0,
        "animationOrChildRosterDifferentPaths": [],
        "structuralDigest": probe.EXPECTED_DIGEST,
    } for name, sha in probe.ASSET_USF_SHA256.items()]
    return {
        "schemaVersion": 1,
        "status": "REPAIRED_VARIANT_STRUCTURES_IDENTICAL",
        "blendSha256": probe.BLEND_SHA256,
        "blenderVersion": "5.2.0 LTS",
        "blenderSha256": blender_sha,
        "rows": rows,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class VariantStructuralValidationTests(unittest.TestCase):
    def test_complete_three_asset_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(probe.validate_result(result, result["blenderSha256"]), result)

    def test_missing_variant_cannot_report_identical(self) -> None:
        result = complete_result()
        result["rows"].pop()
        with self.assertRaisesRegex(probe.VariantStructuralError, "roster"):
            probe.validate_result(result, result["blenderSha256"])

    def test_matrix_drift_cannot_report_identical(self) -> None:
        result = copy.deepcopy(complete_result())
        result["rows"][1]["maxMatrixElementError"] = 0.01
        result["rows"][1]["matrixDifferentPathsOver1e5"] = ["|@root|changed"]
        with self.assertRaisesRegex(probe.VariantStructuralError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_animation_drift_cannot_report_identical(self) -> None:
        result = copy.deepcopy(complete_result())
        result["rows"][2]["animationOrChildRosterDifferentPaths"] = [
            "|@root|changed"]
        with self.assertRaisesRegex(probe.VariantStructuralError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_unreviewed_digest_cannot_report_identical(self) -> None:
        result = copy.deepcopy(complete_result())
        result["rows"][1]["structuralDigest"] = "0" * 64
        with self.assertRaisesRegex(probe.VariantStructuralError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_exported_usf_cannot_report_no_export(self) -> None:
        result = complete_result()
        result["usfExported"] = True
        with self.assertRaisesRegex(probe.VariantStructuralError, "no-write"):
            probe.validate_result(result, result["blenderSha256"])


if __name__ == "__main__":
    unittest.main()
