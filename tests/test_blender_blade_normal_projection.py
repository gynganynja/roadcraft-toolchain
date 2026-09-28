"""The no-save normal projection needs exact 60-leaf receipt coverage."""

from __future__ import annotations

import json
import unittest

from roadcraft import blender_blade_normal_projection as probe


BLENDER_SHA = next(
    digest for digest, version in probe.BLENDER_VERSION_PINS.items()
    if version == "5.2.")
NATIVE_SHA = "a" * 64
HOST_SHA = "b" * 64


def expected_rows() -> list[dict]:
    return [
        {"leafName": leaf,
         "nativeExportPath": probe.NATIVE_PARENT + "|" + leaf,
         "repairedPath": probe.REPAIRED_PARENT + "|" + leaf}
        for leaf in probe.LEAVES
    ]


def worker_result() -> dict:
    others = set(probe.FIELD_NAMES) - {"normals"}
    rows = []
    for index, evidence in enumerate(expected_rows()):
        leaf = evidence["leafName"]
        triangles = 38 if index == len(probe.LEAVES) - 1 else 36
        rows.append({
            "leafName": leaf,
            "nativePath": evidence["nativeExportPath"],
            "repairedPath": evidence["repairedPath"],
            "triangleCount": triangles,
            "cornerCount": triangles * 3,
            "sourceHadCustomNormals": False,
            "projectedNormalsExactRepaired": True,
            "baselineFieldsExactNative": {
                field: True for field in probe.FIELD_NAMES},
            "projectedOtherFieldsUnchanged": {
                field: True for field in others},
            "baselineNormalSha256": "c" * 64,
            "repairedNormalSha256": "d" * 64,
            "projectedNormalSha256": "d" * 64,
            "baselineOtherFieldsSha256": "e" * 64,
            "projectedOtherFieldsSha256": "e" * 64,
        })
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "status": "IN_MEMORY_NORMAL_PROJECTION",
        "blendSha256": probe.BLEND_SHA256,
        "nativeUsfSha256": NATIVE_SHA,
        "repairedUsfSha256": probe.USF_SHA256,
        "worklistSha256": probe.WORKLIST_SHA256,
        "blenderSha256": BLENDER_SHA,
        "blenderVersion": "5.2.0 LTS",
        "workerSha256": probe.WORKER_SHA256,
        "hostSha256": HOST_SHA,
        "sourceWorkerSha256": probe.SOURCE_WORKER_SHA256,
        "bladeHostSha256": probe.BLADE_HOST_SHA256,
        "meshHostSha256": probe.MESH_HOST_SHA256,
        "sceneFrame": 1,
        "sourceSceneMeshCount": 210,
        "normalInputSpace": "saber",
        "leaves": len(probe.LEAVES),
        "triangles": probe.EXPECTED_TRIANGLES,
        "corners": probe.EXPECTED_CORNERS,
        "sourceUnchanged": True,
        "sdkUnchanged": True,
        "nativeUsfUnchanged": True,
        "repairedUsfUnchanged": True,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
        "equivalenceVerified": False,
        "rows": rows,
    }


def interpret(value: dict) -> dict:
    return probe.interpret_readback(
        value, expected_rows(), blender_sha=BLENDER_SHA,
        native_sha=NATIVE_SHA, host_sha=HOST_SHA)


class NormalProjectionTests(unittest.TestCase):
    def test_complete_receipt_still_keeps_export_gate_closed(self) -> None:
        result = interpret(worker_result())
        self.assertEqual(result["leaves"], 60)
        self.assertEqual(result["triangles"], 2162)
        self.assertEqual(result["corners"], 6486)
        self.assertEqual(len(result["rowsDigestSha256"]), 64)
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertFalse(result["equivalenceVerified"])

    def test_rejects_missing_reordered_or_short_corner_coverage(self) -> None:
        result = worker_result()
        result["rows"].pop()
        with self.assertRaisesRegex(probe.NormalProjectionError, "coverage"):
            interpret(result)
        result = worker_result()
        result["rows"][0], result["rows"][1] = (
            result["rows"][1], result["rows"][0])
        with self.assertRaisesRegex(probe.NormalProjectionError, "path"):
            interpret(result)
        result = worker_result()
        result["rows"][0]["cornerCount"] -= 1
        with self.assertRaisesRegex(probe.NormalProjectionError, "coverage"):
            interpret(result)

    def test_rejects_unproved_normal_or_changed_non_normal_field(self) -> None:
        for field, value in (
                ("projectedNormalsExactRepaired", False),
                ("sourceHadCustomNormals", True)):
            with self.subTest(field=field):
                result = worker_result()
                result["rows"][5][field] = value
                with self.assertRaisesRegex(probe.NormalProjectionError,
                                            "normals"):
                    interpret(result)
        result = worker_result()
        result["rows"][5]["projectedOtherFieldsUnchanged"]["positions"] = False
        with self.assertRaisesRegex(probe.NormalProjectionError,
                                    "non-normal"):
            interpret(result)
        result = worker_result()
        result["rows"][5]["projectedNormalSha256"] = "f" * 64
        with self.assertRaisesRegex(probe.NormalProjectionError, "digest"):
            interpret(result)

    def test_rejects_no_save_export_and_parser_marker_changes(self) -> None:
        for field in ("blendSaved", "usfExported",
                      "nativeBlendExportApproved", "equivalenceVerified"):
            with self.subTest(field=field):
                result = worker_result()
                result[field] = True
                with self.assertRaisesRegex(probe.NormalProjectionError,
                                            "gate"):
                    interpret(result)
        marker = probe.RESULT_PREFIX + json.dumps(worker_result())
        parsed = probe.parse_result(
            "Blender startup\n" + marker, expected_rows(),
            blender_sha=BLENDER_SHA, native_sha=NATIVE_SHA,
            host_sha=HOST_SHA)
        self.assertEqual(parsed["leaves"], 60)
        with self.assertRaisesRegex(probe.NormalProjectionError,
                                    "one bounded"):
            probe.parse_result(
                marker + "\n" + marker, expected_rows(),
                blender_sha=BLENDER_SHA, native_sha=NATIVE_SHA,
                host_sha=HOST_SHA)


if __name__ == "__main__":
    unittest.main()
