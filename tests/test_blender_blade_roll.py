"""Reject false blade-roll matches and incomplete no-save evidence."""

from __future__ import annotations

import copy
import unittest

from roadcraft import blender_blade_roll as probe


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    source, repaired = probe._residual_paths()
    return {
        "schemaVersion": 1, "status": "IN_MEMORY_BLADE_ROLL_MATCH",
        "asset": "cat_d11t", "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "blenderSha256": blender_sha, "blenderVersion": "5.2.0 LTS",
        "sceneFrame": 1, "beforeSourceBoneCount": 384,
        "afterSourceBoneCount": 385, "repairedStructuralCount": 400,
        "beforeSharedPathCount": 378, "afterSharedPathCount": 380,
        "afterChangedMatrixCount": 0, "afterMaxSharedMatrixError": 0.0,
        "afterSourceOnlyPaths": source,
        "afterRepairedOnlyPaths": repaired,
        "targetMatrixErrors": [
            {"path": path, "maxElementError": 0.0}
            for path in probe._target_paths()],
        "bladeMeshCount": 60, "beforeMeshWorldError": 0.0,
        "meshDriftBeforeRestore": 0.8908867835998535,
        "meshDriftAfterRestore": 0.0,
        "afterMeshWorldError": 0.0,
        "afterMeshLocalError": 0.0,
        "newBoneEditLength": 0.25, "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class BladeRollValidationTests(unittest.TestCase):
    def test_complete_no_save_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(probe.validate_result(result, result["blenderSha256"]), result)

    def test_missing_blade_path_cannot_report_match(self) -> None:
        result = copy.deepcopy(complete_result())
        result["targetMatrixErrors"].pop()
        with self.assertRaisesRegex(probe.BladeRollError, "target path roster"):
            probe.validate_result(result, result["blenderSha256"])

    def test_mesh_local_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["afterMeshLocalError"] = 0.01
        with self.assertRaisesRegex(probe.BladeRollError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_saved_blend_cannot_report_no_save_result(self) -> None:
        result = complete_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.BladeRollError, "no-write"):
            probe.validate_result(result, result["blenderSha256"])


if __name__ == "__main__":
    unittest.main()
