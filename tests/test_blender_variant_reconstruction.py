"""Reject unsupported success claims from the variant no-save diagnostic."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from roadcraft import blender_variant_reconstruction as probe


ASSET = "cat_d11t_v2"
BLEND = Path("C:/p/cat_d11t_v2.blend")


def complete_result() -> dict:
    blender_sha = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                       if version == "5.2.")
    return {
        "schemaVersion": 1,
        "asset": ASSET,
        "variantBlendPath": str(BLEND),
        "variantBlendSha256": probe.BLEND_SHA256,
        "baseRepairedUsfSha256": probe.USF_SHA256,
        "variantRepairedUsfSha256": probe.ASSET_USF_SHA256[ASSET],
        "blenderVersion": "5.2.0 LTS",
        "blenderSha256": blender_sha,
        "sourcePoseBoneCount": 399,
        "repairedStructuralCount": 400,
        "sharedPathCount": 400,
        "sourceOnlyPaths": [],
        "repairedOnlyPaths": [],
        "changedMatrixCount": 0,
        "maxSharedMatrixError": 2.2687017917633057e-6,
        "baseReconstructionStatus": "IN_MEMORY_STRUCTURAL_MATCH",
        "baseMeshWorldError": 0.0,
        "sfxSourceKind": "bone-parented EMPTY",
        "status": "IN_MEMORY_VARIANT_STRUCTURAL_MATCH",
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class VariantReconstructionValidationTests(unittest.TestCase):
    def check(self, result: dict) -> dict:
        return probe.validate_result(
            result, asset=ASSET, blend=BLEND,
            blender_sha256=result["blenderSha256"])

    def test_complete_no_save_variant_result_is_accepted(self) -> None:
        result = complete_result()
        self.assertIs(self.check(result), result)

    def test_other_variant_usf_cannot_report_match(self) -> None:
        result = complete_result()
        result["variantRepairedUsfSha256"] = probe.ASSET_USF_SHA256["cat_d11t_v3"]
        with self.assertRaisesRegex(probe.VariantReconstructionError, "identity"):
            self.check(result)

    def test_missing_path_cannot_report_match(self) -> None:
        result = copy.deepcopy(complete_result())
        result["sharedPathCount"] = 399
        result["repairedOnlyPaths"] = ["|@root|missing"]
        with self.assertRaisesRegex(probe.VariantReconstructionError, "coverage"):
            self.check(result)

    def test_matrix_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["maxSharedMatrixError"] = 0.01
        with self.assertRaisesRegex(probe.VariantReconstructionError, "contradicts"):
            self.check(result)

    def test_source_mesh_drift_cannot_report_match(self) -> None:
        result = complete_result()
        result["baseMeshWorldError"] = 0.01
        with self.assertRaisesRegex(probe.VariantReconstructionError, "contradicts"):
            self.check(result)

    def test_exported_usf_cannot_report_no_export(self) -> None:
        result = complete_result()
        result["usfExported"] = True
        with self.assertRaisesRegex(probe.VariantReconstructionError, "no-write"):
            self.check(result)


if __name__ == "__main__":
    unittest.main()
