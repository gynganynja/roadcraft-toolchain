"""Asset-specific checks for the no-save D11 v2/v3 mesh readback."""

from __future__ import annotations

import copy
import hashlib
import unittest

from roadcraft import blender_mesh_inventory as base
from roadcraft import blender_mesh_variant_inventory as variant


PATHS = [f"|@root|D11T_Rig.005|mesh_{index:03d}_vis"
         for index in range(base.EXPECTED_GAP_ROWS)]


def _facts() -> dict:
    return {
        "rawVertices": 5, "rawPolygons": 3, "rawTriangles": 7,
        "evaluatedVertices": 5, "evaluatedPolygons": 3,
        "evaluatedTriangles": 7,
        "evaluatedMaterialNames": ["source"],
        "evaluatedUvNames": ["UVMap"],
        "evaluatedColorNames": [],
        "evaluatedCustomColorNames": [],
        "saberNormalsCount": None,
        "armatureModifierCount": 1,
        "firstArmatureTarget": "D11T_Rig.005",
        "firstArmaturePoseBoneCount": 384,
        "vertexGroupNames": ["BoneChassis_cdt"],
        "weightedRawVertices": 5,
        "sdkExpectedVertices": 21,
        "sdkExpectedFaces": 7,
        "sdkExpectedNormals": 21,
        "sdkExpectedUvSets": 1,
        "sdkExpectedColorSets": 0,
        "sdkExpectedMaterialSlots": 1,
        "sdkExpectedSkinEntries": 21,
        "sdkExpectedSkinBones": 384,
    }


def _gap(path: str, asset_name: str) -> dict:
    suffix = "_v2" if asset_name.endswith("_v2") else "_v3"
    return {
        "path": path,
        "missingMaterialLabels": [{"label": "required" + suffix,
                                   "count": 1}],
        "measurements": {"faces": {"repaired": 5, "nativeExport": 7}},
        "repairedMaterialSlots": 2,
        "nativeExportMaterialSlots": 1,
        "repairedSkinBoneUidCount": 381,
        "nativeExportSkinBoneUidCount": 384,
        "inverseBindMatricesDifferent": True,
    }


def _worklist(asset_name: str) -> dict:
    pins = variant.ASSET_PINS[asset_name]
    return {
        "schemaVersion": 1, "status": "RECONSTRUCTION_REQUIRED",
        "nativeBlendExportApproved": False,
        "inventorySha256": variant.INVENTORY_SHA256,
        "assets": [
            {
                "asset": "cat_d11t",
                "sourceAssetDigest": variant._BASE_ASSET_DIGEST,
                "blendSha256": base.BLEND_SHA256,
                "repairedUsfSha256": base.USF_SHA256,
                "nativeBlendExportApproved": False,
                "findings": {"changedMeshNodes": [{"path": path}
                                                   for path in PATHS]},
            },
            {
                "asset": asset_name,
                "sourceAssetDigest": pins["sourceAssetDigest"],
                "blendSha256": pins["blendSha256"],
                "repairedUsfSha256": pins["repairedUsfSha256"],
                "nativeBlendExportApproved": False,
                "findings": {"changedMeshNodes": [_gap(path, asset_name)
                                                   for path in PATHS]},
            },
        ],
    }


def _base_readback() -> dict:
    rows = [{
        "path": path, "sourceObject": f"mesh_{index:03d}_vis_LOD0",
        "predictedSdkPath": path,
        "mappingStatus": "SDK_PATH_RECONSTRUCTED",
        "parentObject": "D11T_Rig.005", "parentBone": "",
        "parentType": "OBJECT", "sourceVisible": True,
        "sourceFacts": _facts(), "gapFindings": {"base": True},
    } for index, path in enumerate(PATHS)]
    blender_sha = next(pin for pin, version in base.BLENDER_VERSION_PINS.items()
                       if version == "5.0.")
    return {
        "schemaVersion": 1, "status": "SOURCE_GAP_INVENTORY",
        "asset": "cat_d11t", "blendSha256": base.BLEND_SHA256,
        "repairedUsfSha256": base.USF_SHA256,
        "inventorySha256": variant.INVENTORY_SHA256,
        "worklistSha256": base.WORKLIST_SHA256,
        "workerSha256": base.WORKER_SHA256,
        "sceneFrame": 1, "sceneMeshObjects": 210,
        "mappedGapRows": 126, "unmappedGapRows": 0,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "sourceUnchanged": True, "sdkUnchanged": True,
        "blenderSha256": blender_sha, "blenderVersion": "5.0.1",
        "rowsDigestSha256": hashlib.sha256(base._canonical(rows)).hexdigest(),
        "rows": rows,
    }


class VariantMeshInventoryTests(unittest.TestCase):
    def test_all_126_paths_and_variant_pins_must_match(self):
        for name in variant.ASSET_PINS:
            worklist = _worklist(name)
            digest = variant.ASSET_PINS[name]["sourceAssetDigest"]
            self.assertEqual(len(variant._variant_rows(worklist, name, digest)),
                             126)
            changed = copy.deepcopy(worklist)
            changed["assets"][1]["findings"]["changedMeshNodes"][0]["path"] = \
                "|@root|D11T_Rig.005|other_vis"
            with self.assertRaises(variant.VariantMeshInventoryError):
                variant._variant_rows(changed, name, digest)
            changed = copy.deepcopy(worklist)
            changed["assets"][1]["repairedUsfSha256"] = "0" * 64
            with self.assertRaises(variant.VariantMeshInventoryError):
                variant._variant_rows(changed, name, digest)
            changed = copy.deepcopy(worklist)
            changed["nativeBlendExportApproved"] = True
            with self.assertRaises(variant.VariantMeshInventoryError):
                variant._variant_rows(changed, name, digest)
            with self.assertRaises(variant.VariantMeshInventoryError):
                variant._variant_rows(worklist, name, "0" * 64)

    def test_variant_labels_are_interpreted_from_source_facts(self):
        base_result = _base_readback()
        for name in variant.ASSET_PINS:
            worklist = _worklist(name)
            gaps = variant._variant_rows(
                worklist, name, variant.ASSET_PINS[name]["sourceAssetDigest"])
            result = variant.interpret_variant(base_result, name, gaps)
            self.assertEqual(result["asset"], name)
            self.assertEqual(result["mappedGapRows"], 126)
            self.assertEqual(result["sourceFactsFromAsset"], "cat_d11t")
            self.assertTrue(result["sourceFactsFromByteIdenticalBlend"])
            self.assertFalse(result["nativeBlendExportApproved"])
            self.assertEqual(result["repairedOnlyMaterialLabelsAbsentFromSourceRows"],
                             126)
            first = result["rows"][0]["gapFindings"]
            self.assertEqual(first["repairedOnlyLabelsAbsentFromSource"][0]
                             ["label"], "required" + name[-3:])
            self.assertEqual(first["materialSlots"]["classification"],
                             "SOURCE_MATCHES_NATIVE")
            self.assertEqual(first["recordedCountGaps"]["faces"]
                             ["classification"], "SOURCE_MATCHES_NATIVE")

    def test_forged_or_partial_base_readback_fails_closed(self):
        name = "cat_d11t_v2"
        gaps = variant._variant_rows(_worklist(name), name,
                                     variant.ASSET_PINS[name]["sourceAssetDigest"])
        original = _base_readback()
        for mutation in (
            lambda item: item.update({"blendSaved": True}),
            lambda item: item.update({"rowsDigestSha256": "0" * 64}),
            lambda item: item["rows"].pop(),
            lambda item: item["rows"][0].update({"mappingStatus": "UNMAPPED"}),
            lambda item: item["rows"][0].update({"sourceVisible": False}),
            lambda item: item["rows"][0].update({"path": "|@root|wrong"}),
        ):
            changed = copy.deepcopy(original)
            mutation(changed)
            with self.subTest(mutation=mutation), self.assertRaises(
                    variant.VariantMeshInventoryError):
                variant.interpret_variant(changed, name, gaps)

    def test_non_variant_asset_is_rejected(self):
        with self.assertRaises(variant.VariantMeshInventoryError):
            variant._pins("cat_d11t")


if __name__ == "__main__":
    unittest.main()
