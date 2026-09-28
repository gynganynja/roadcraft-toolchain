"""The blade readback must cover every path and retain the blocked export gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from roadcraft import blender_blade_relocation as probe


IDENTITY = [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]
MOVED = IDENTITY[:]
MOVED[3] = 0.25
SOURCE_COUNTS = {name: 0 for name in probe.SOURCE_FIELDS}
SOURCE_COUNTS.update(rawVertices=13, rawPolygons=22, rawTriangles=22,
                     evaluatedVertices=13, evaluatedTriangles=22,
                     materialSlots=1)
USF_COUNTS = {name: 0 for name in probe.MESH_FIELDS}
USF_COUNTS.update(vertices=66, faces=22, normals=66, materialSlots=1)
BLENDER_SHA = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                   if version == "5.0.")


def relocation_rows() -> list[dict]:
    return [{"leafName": leaf,
             "nativeExportPath": probe.NATIVE_PARENT + "|" + leaf,
             "repairedPath": probe.REPAIRED_PARENT + "|" + leaf,
             "equivalenceVerified": False} for leaf in probe.LEAVES]


def worker_result() -> dict:
    rows = []
    for evidence in relocation_rows():
        leaf = evidence["leafName"]
        rows.append({
            **evidence,
            "source": {"objectName": leaf, "objectType": "MESH",
                       "parentObject": "D11T_Rig.005", "parentType": "BONE",
                       "parentBone": "BoneBlade_cdt",
                       "sourcePredictedPath": evidence["nativeExportPath"],
                       "visible": True, "worldMatrixSaber": IDENTITY[:],
                       "mesh": SOURCE_COUNTS.copy()},
            "nativeExportNode": {"path": evidence["nativeExportPath"],
                                 "worldMatrixSaber": IDENTITY[:],
                                 "localMatrixSaber": IDENTITY[:],
                                 "mesh": USF_COUNTS.copy()},
            "repairedNode": {"path": evidence["repairedPath"],
                             "worldMatrixSaber": MOVED[:],
                             "localMatrixSaber": MOVED[:],
                             "mesh": USF_COUNTS.copy()},
        })
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "nativeExportUsfSha256": "a" * 64,
        "worklistSha256": probe.WORKLIST_SHA256,
        "summarySha256": "b" * 64,
        "blenderSha256": BLENDER_SHA, "blenderVersion": "5.0.1",
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False, "rows": rows,
    }


class BladeRelocationTests(unittest.TestCase):
    def test_complete_readback_retains_distinct_paths_and_gate(self) -> None:
        result = probe.interpret_readback(worker_result(), relocation_rows(),
                                          BLENDER_SHA, "a" * 64, "b" * 64)
        self.assertEqual(result["status"], "SOURCE_BLADE_RELOCATION_INVENTORY")
        self.assertEqual(result["relocationRows"], 60)
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertFalse(result["rows"][0]["equivalenceVerified"])
        self.assertEqual(result["rows"][0]["sourceNativeWorldMaxElementError"], 0.0)
        self.assertEqual(result["rows"][0]["sourceRepairedWorldMaxElementError"], 0.25)
        self.assertEqual(result["rows"][0]["nativeRepairedLocalMaxElementError"], 0.25)
        self.assertNotEqual(result["rows"][0]["nativeExportPath"],
                            result["rows"][0]["repairedPath"])

    def test_readback_rejects_missing_reordered_or_forged_rows(self) -> None:
        result = worker_result()
        result["rows"].pop()
        with self.assertRaisesRegex(probe.BladeRelocationError, "omitted"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)
        result = worker_result()
        result["rows"][0], result["rows"][1] = result["rows"][1], result["rows"][0]
        with self.assertRaisesRegex(probe.BladeRelocationError, "path or gate"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)
        result = worker_result()
        result["rows"][0]["equivalenceVerified"] = True
        with self.assertRaisesRegex(probe.BladeRelocationError, "path or gate"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)
        result = worker_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.BladeRelocationError, "no-write"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)

    def test_readback_rejects_wrong_source_parent_and_nonfinite_matrix(self) -> None:
        result = worker_result()
        result["rows"][0]["source"]["parentBone"] = "BoneBladeRoll_cdt"
        with self.assertRaisesRegex(probe.BladeRelocationError, "source hierarchy"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)
        result = worker_result()
        result["rows"][0]["nativeExportNode"]["worldMatrixSaber"][0] = float("nan")
        with self.assertRaisesRegex(probe.BladeRelocationError, "finite"):
            probe.interpret_readback(result, relocation_rows(), BLENDER_SHA,
                                     "a" * 64, "b" * 64)

    def test_summary_to_native_usf_identity_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native = root / "candidate.usf"
            native.write_bytes(b"retained native bytes")
            native_sha = hashlib.sha256(native.read_bytes()).hexdigest()
            blend = root / "source.blend"
            repaired = root / "repaired.usf"
            summary = root / "summary.json"
            summary_data = {
                "asset": "cat_d11t", "nativeBlendExportApproved": False,
                "blendSha256": probe.BLEND_SHA256,
                "baselineUsfSha256": probe.USF_SHA256,
                "candidateUsfSha256": native_sha,
                "baselineRootName": "cat_d11t",
                "candidateRootName": "cat_d11t",
                "blendPath": str(blend), "baselineUsfPath": str(repaired),
                "candidateUsfPath": str(native),
            }
            summary.write_text(json.dumps(summary_data), encoding="utf-8")
            summary_sha = hashlib.sha256(summary.read_bytes()).hexdigest()
            candidates = relocation_rows() + [
                {"leafName": f"other_{i}"} for i in range(6)]
            worklist = {
                "schemaVersion": 1, "status": "RECONSTRUCTION_REQUIRED",
                "nativeBlendExportApproved": False,
                "inventorySha256": probe.INVENTORY_SHA256,
                "assets": [{"asset": "cat_d11t", "sourceAssetDigest": "source",
                            "blendSha256": probe.BLEND_SHA256,
                            "repairedUsfSha256": probe.USF_SHA256,
                            "nativeBlendExportApproved": False,
                            "scratchNativeUsfSha256": native_sha,
                            "summaryPath": str(summary),
                            "summarySha256": summary_sha,
                            "findings": {"pathRelocationCandidates": candidates}}],
            }
            rows, native_path, observed_sha, summary_path, observed_summary_sha = (
                probe._rows_and_native(worklist, "source", blend, repaired))
            self.assertEqual(len(rows), 60)
            self.assertEqual(native_path, native)
            self.assertEqual(observed_sha, native_sha)
            self.assertEqual(summary_path, summary)
            self.assertEqual(observed_summary_sha, summary_sha)
            native.write_bytes(b"changed native bytes")
            with self.assertRaisesRegex(probe.LeftPushProbeError,
                                        "retained scratch native USF"):
                probe._rows_and_native(worklist, "source", blend, repaired)


if __name__ == "__main__":
    unittest.main()
