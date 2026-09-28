"""Guard a no-save branch result against omitted paths and false success."""

from __future__ import annotations

import copy
import unittest

from roadcraft import blender_push_branches as probe


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    source_only, repaired_only = probe._residual_paths()
    return {
        "schemaVersion": 1, "status": "IN_MEMORY_PUSH_BRANCH_MATCH",
        "asset": "cat_d11t", "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "blenderSha256": blender_sha, "blenderVersion": "5.2.0 LTS",
        "sceneFrame": 1, "beforeSourceBoneCount": 384,
        "afterSourceBoneCount": 388, "repairedStructuralCount": 400,
        "beforeSharedPathCount": 378, "afterSharedPathCount": 386,
        "afterChangedMatrixCount": 0, "afterMaxSharedMatrixError": 0.0,
        "afterSourceOnlyPaths": source_only,
        "afterRepairedOnlyPaths": repaired_only,
        "targetMatrixErrors": [{"path": path, "maxElementError": 0.0}
                               for path in probe._target_paths()],
        "tiltPoseChanges": [
            {"side": side, "basePoseMatrixMaxChange": 0.0,
             "tipPoseMatrixMaxChange": 0.0} for side in ("left", "right")],
        "newBoneEditLength": 0.25, "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class PushBranchValidationTests(unittest.TestCase):
    def test_complete_no_save_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(probe.validate_result(result, result["blenderSha256"]), result)

    def test_missing_right_push_tip_cannot_report_match(self) -> None:
        result = copy.deepcopy(complete_result())
        result["targetMatrixErrors"] = [
            row for row in result["targetMatrixErrors"]
            if not row["path"].endswith("IK_push_arm_right_tip")]
        with self.assertRaisesRegex(probe.PushBranchesError, "target path roster"):
            probe.validate_result(result, result["blenderSha256"])

    def test_saved_asset_cannot_report_no_save_result(self) -> None:
        result = complete_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.PushBranchesError, "no-write"):
            probe.validate_result(result, result["blenderSha256"])


if __name__ == "__main__":
    unittest.main()
