"""Fail-closed checks for no-save D11 source mesh gap interpretation."""

from __future__ import annotations

import copy
import json
import unittest

from roadcraft import blender_mesh_inventory as mesh


def source_facts() -> dict:
    return {
        "rawVertices": 5, "rawPolygons": 3, "rawTriangles": 7,
        "evaluatedVertices": 5, "evaluatedPolygons": 3,
        "evaluatedTriangles": 7,
        "evaluatedMaterialNames": ["present", "other"],
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
        "sdkExpectedMaterialSlots": 2,
        "sdkExpectedSkinEntries": 21,
        "sdkExpectedSkinBones": 384,
    }


def gap(path: str = "|@root|D11T_Rig.005|sample_vis") -> dict:
    return {
        "path": path,
        "missingMaterialLabels": [
            {"label": "required", "count": 2},
            {"label": "present", "count": 1},
        ],
        "measurements": {
            "faces": {"repaired": 5, "nativeExport": 7},
            "skinEntries": {"repaired": 15, "nativeExport": 21},
        },
        "repairedMaterialSlots": 3,
        "nativeExportMaterialSlots": 2,
        "repairedSkinBoneUidCount": 381,
        "nativeExportSkinBoneUidCount": 384,
        "inverseBindMatricesDifferent": True,
    }


def readback_row(path: str = "|@root|D11T_Rig.005|sample_vis") -> dict:
    return {
        "path": path, "sourceObject": "sample_vis_LOD0",
        "predictedSdkPath": path,
        "mappingStatus": "SDK_PATH_RECONSTRUCTED",
        "parentObject": "D11T_Rig.005", "parentBone": "",
        "parentType": "OBJECT", "sourceVisible": True,
        "facts": source_facts(),
    }


def readback(rows: list[dict]) -> dict:
    blender_pin = next(pin for pin, version in mesh.BLENDER_VERSION_PINS.items()
                       if version == "5.0.")
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": mesh.BLEND_SHA256,
        "repairedUsfSha256": mesh.USF_SHA256,
        "worklistSha256": mesh.WORKLIST_SHA256,
        "blenderSha256": blender_pin,
        "blenderVersion": "5.0.1",
        "sceneFrame": 1, "sceneMeshObjects": 210,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "rows": rows,
    }


class MeshInventoryTests(unittest.TestCase):
    def test_worklist_requires_full_base_gap_and_blocked_gate(self):
        digest = "d" * 64
        paths = [f"|@root|mesh_{index:03d}" for index in range(126)]
        worklist = {
            "schemaVersion": 1, "status": "RECONSTRUCTION_REQUIRED",
            "nativeBlendExportApproved": False,
            "inventorySha256": mesh.INVENTORY_SHA256,
            "assets": [{
                "asset": "cat_d11t", "sourceAssetDigest": digest,
                "blendSha256": mesh.BLEND_SHA256,
                "repairedUsfSha256": mesh.USF_SHA256,
                "nativeBlendExportApproved": False,
                "findings": {"changedMeshNodes": [{"path": path} for path in paths]},
            }],
        }
        self.assertEqual(len(mesh._worklist_rows(worklist, digest)), 126)
        changed = copy.deepcopy(worklist)
        changed["assets"][0]["findings"]["changedMeshNodes"].pop()
        with self.assertRaises(mesh.MeshInventoryError):
            mesh._worklist_rows(changed, digest)
        changed = copy.deepcopy(worklist)
        changed["nativeBlendExportApproved"] = True
        with self.assertRaises(mesh.MeshInventoryError):
            mesh._worklist_rows(changed, digest)

    def test_source_count_derivations_are_checked(self):
        facts = source_facts()
        self.assertEqual(mesh._validate_facts(facts), facts)
        changed = copy.deepcopy(facts)
        changed["sdkExpectedFaces"] = 8
        with self.assertRaises(mesh.MeshInventoryError):
            mesh._validate_facts(changed)
        changed = copy.deepcopy(facts)
        changed["sdkExpectedSkinBones"] = 0
        with self.assertRaises(mesh.MeshInventoryError):
            mesh._validate_facts(changed)

    def test_gap_classification_separates_missing_source_from_exporter(self):
        findings = mesh._gap_findings(gap(), source_facts())
        self.assertEqual(findings["repairedOnlyLabelsAbsentFromSource"],
                         [{"label": "required", "count": 2}])
        self.assertEqual(findings["repairedOnlyLabelsPresentInSource"],
                         [{"label": "present", "count": 1}])
        self.assertEqual(findings["materialSlots"]["classification"],
                         "SOURCE_MATCHES_NATIVE")
        self.assertEqual(findings["skinBones"]["classification"],
                         "SOURCE_MATCHES_NATIVE")
        self.assertEqual(findings["recordedCountGaps"]["faces"]["classification"],
                         "SOURCE_MATCHES_NATIVE")
        self.assertFalse(findings["bindParityEvaluated"])
        changed = source_facts()
        changed["sdkExpectedFaces"] = 5
        findings = mesh._gap_findings(gap(), changed)
        self.assertEqual(findings["recordedCountGaps"]["faces"]["classification"],
                         "SOURCE_MATCHES_REPAIRED")

    def test_readback_rejects_partial_or_forged_source_mapping(self):
        original = readback([readback_row()])
        pin = original["blenderSha256"]
        result = mesh.interpret_readback(original, [gap()], pin)
        self.assertEqual(result["mappedGapRows"], 1)
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertEqual(len(result["rowsDigestSha256"]), 64)
        changed = copy.deepcopy(original)
        changed["rows"] = []
        with self.assertRaises(mesh.MeshInventoryError):
            mesh.interpret_readback(changed, [gap()], pin)
        changed = copy.deepcopy(original)
        changed["rows"][0]["predictedSdkPath"] = "|@root|elsewhere"
        with self.assertRaises(mesh.MeshInventoryError):
            mesh.interpret_readback(changed, [gap()], pin)
        changed = copy.deepcopy(original)
        changed["blendSaved"] = True
        with self.assertRaises(mesh.MeshInventoryError):
            mesh.interpret_readback(changed, [gap()], pin)

    def test_unmapped_path_never_receives_source_gap_classification(self):
        row = readback_row()
        row.update({"sourceObject": None, "predictedSdkPath": None,
                    "mappingStatus": "UNMAPPED", "facts": None})
        original = readback([row])
        result = mesh.interpret_readback(original, [gap()], original["blenderSha256"])
        self.assertEqual(result["mappedGapRows"], 0)
        self.assertIsNone(result["rows"][0]["gapFindings"])
        changed = copy.deepcopy(original)
        changed["rows"][0]["facts"] = source_facts()
        with self.assertRaises(mesh.MeshInventoryError):
            mesh.interpret_readback(changed, [gap()], original["blenderSha256"])

    def test_result_line_must_be_unique_and_bounded(self):
        original = readback([readback_row()])
        line = mesh.RESULT_PREFIX + json.dumps(original)
        pin = original["blenderSha256"]
        self.assertEqual(mesh.parse_result(line, [gap()], pin)["mappedGapRows"], 1)
        with self.assertRaises(mesh.MeshInventoryError):
            mesh.parse_result(line + "\n" + line, [gap()], pin)


if __name__ == "__main__":
    unittest.main()
