"""Reject incomplete or writable D11 access-ladder diagnostics."""

from __future__ import annotations

import copy
import unittest

from roadcraft import blender_ladder as probe


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    source, repaired = probe._residual_paths()
    return {
        "schemaVersion": 1, "status": "IN_MEMORY_LADDER_MATCH",
        "asset": "cat_d11t", "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "blenderSha256": blender_sha, "blenderVersion": "5.2.0 LTS",
        "sceneFrame": 1, "pushAndRollPresent": False,
        "beforeSourceBoneCount": 384, "afterSourceBoneCount": 387,
        "repairedStructuralCount": 400,
        "beforeSharedPathCount": 378, "afterSharedPathCount": 382,
        "afterChangedMatrixCount": 0, "afterMaxSharedMatrixError": 0.0,
        "afterSourceOnlyPaths": source,
        "afterRepairedOnlyPaths": repaired,
        "targetMatrixErrors": [
            {"path": path, "maxElementError": 0.0}
            for path in probe._target_paths()],
        "sourceLadderBoneParentedObjectCount": 0,
        "newBoneEditLength": 0.25, "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class LadderValidationTests(unittest.TestCase):
    def test_complete_no_save_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(probe.validate_result(result, result["blenderSha256"]), result)

    def test_missing_ladder_path_cannot_report_match(self) -> None:
        result = copy.deepcopy(complete_result())
        result["targetMatrixErrors"].pop()
        with self.assertRaisesRegex(probe.LadderError, "target path roster"):
            probe.validate_result(result, result["blenderSha256"])

    def test_matrix_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["targetMatrixErrors"][0]["maxElementError"] = 0.01
        result["afterMaxSharedMatrixError"] = 0.01
        with self.assertRaisesRegex(probe.LadderError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_saved_blend_cannot_report_no_save_result(self) -> None:
        result = complete_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.LadderError, "no-write"):
            probe.validate_result(result, result["blenderSha256"])

    def test_combined_repair_has_exact_residual(self) -> None:
        result = complete_result()
        result.update({
            "beforeSourceBoneCount": 389, "afterSourceBoneCount": 392,
            "beforeSharedPathCount": 388, "afterSharedPathCount": 392,
            "pushAndRollPresent": True,
        })
        source, repaired = probe._residual_paths(True)
        result["afterSourceOnlyPaths"] = source
        result["afterRepairedOnlyPaths"] = repaired
        self.assertIs(probe.validate_result(
            result, result["blenderSha256"],
            push_and_roll_present=True), result)
        with self.assertRaisesRegex(probe.LadderError, "identity"):
            probe.validate_result(result, result["blenderSha256"])


if __name__ == "__main__":
    unittest.main()
