"""Reject false complete-path claims in the no-save D11 diagnostic."""

from __future__ import annotations

import copy
import unittest

from roadcraft import blender_residual_bones as probe


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    return {
        "schemaVersion": 1, "status": "IN_MEMORY_STRUCTURAL_MATCH",
        "asset": "cat_d11t", "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "blenderSha256": blender_sha, "blenderVersion": "5.2.0 LTS",
        "sceneFrame": 1,
        "priorRepairStatuses": [
            "IN_MEMORY_PUSH_BRANCH_MATCH", "IN_MEMORY_BLADE_ROLL_MATCH",
            "IN_MEMORY_LADDER_MATCH"],
        "beforeSourceBoneCount": 392,
        "afterSourceBoneCount": 399,
        "sourceEmptyNodeCount": 1,
        "repairedStructuralCount": 400,
        "afterSharedPathCount": 400,
        "afterSourceOnlyPaths": [],
        "afterRepairedOnlyPaths": [],
        "afterChangedMatrixCount": 0,
        "afterMaxSharedMatrixError": 0.0,
        "targetMatrixErrors": [
            {"path": path, "maxElementError": 0.0}
            for path in probe._target_paths()],
        "sfxSourceKind": "bone-parented EMPTY",
        "sfxSourceMatrixError": 0.0,
        "sourceMeshCount": 210,
        "meshWorldError": 0.0,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class ResidualBonesValidationTests(unittest.TestCase):
    def test_complete_no_save_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(probe.validate_result(result, result["blenderSha256"]), result)

    def test_missing_target_path_cannot_report_match(self) -> None:
        result = copy.deepcopy(complete_result())
        result["targetMatrixErrors"].pop()
        with self.assertRaisesRegex(probe.ResidualBonesError, "target path roster"):
            probe.validate_result(result, result["blenderSha256"])

    def test_sfx_matrix_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["sfxSourceMatrixError"] = 0.01
        result["afterMaxSharedMatrixError"] = 0.01
        with self.assertRaisesRegex(probe.ResidualBonesError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_mesh_world_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["meshWorldError"] = 0.01
        with self.assertRaisesRegex(probe.ResidualBonesError, "contradicts"):
            probe.validate_result(result, result["blenderSha256"])

    def test_saved_blend_cannot_report_no_save_result(self) -> None:
        result = complete_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.ResidualBonesError, "no-write"):
            probe.validate_result(result, result["blenderSha256"])

    def test_source_empty_cannot_be_mislabeled_as_bone(self) -> None:
        result = complete_result()
        result["sfxSourceKind"] = "pose bone"
        with self.assertRaisesRegex(probe.ResidualBonesError, "identity"):
            probe.validate_result(result, result["blenderSha256"])


if __name__ == "__main__":
    unittest.main()
