"""The blade payload readback keeps exact paths and the export gate closed."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from roadcraft import blender_blade_payload as probe


BLENDER_SHA = next(sha for sha, version in probe.BLENDER_VERSION_PINS.items()
                   if version == "5.2.")
NATIVE_SHA = "a" * 64
SUMMARY_SHA = "b" * 64
HOST_SHA = "c" * 64


def expected_rows() -> list[dict]:
    return [{"leafName": leaf,
             "nativeExportPath": probe.NATIVE_PARENT + "|" + leaf,
             "repairedPath": probe.REPAIRED_PARENT + "|" + leaf,
             "equivalenceVerified": False} for leaf in probe.LEAVES]


def field_summary(field: str, digest: str) -> dict:
    value = {"elements": 4, "sha256": digest}
    if field in ("uvCoordinates", "packedColors"):
        value["sets"] = 1
    if field == "uvCoordinates":
        value["names"] = ["UVMap"]
    if field == "skinIndicesWeights":
        value["bonesPerVertex"] = 4
    return value


def worker_result() -> dict:
    rows = []
    for evidence in expected_rows():
        leaf = evidence["leafName"]
        fields = {}
        for field in probe.FIELD_NAMES:
            source = field_summary(field, "d" * 64)
            fields[field] = {"source": source, "native": deepcopy(source),
                             "repaired": deepcopy(source)}
        rows.append({
            **evidence, "sourceObject": leaf,
            "sourcePredictedPath": evidence["nativeExportPath"],
            "sourceParentBone": "BoneBlade_cdt", "fields": fields,
        })
    return {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "nativeExportUsfSha256": NATIVE_SHA,
        "worklistSha256": probe.WORKLIST_SHA256,
        "summarySha256": SUMMARY_SHA,
        "blenderSha256": BLENDER_SHA, "hostSha256": HOST_SHA,
        "bladeHostSha256": probe.BLADE_HOST_SHA256,
        "meshHostSha256": probe.MESH_HOST_SHA256,
        "blenderVersion": "5.2.0", "sceneFrame": 1,
        "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False, "sdkPackerGuarded": False,
        "cacheBeforeSourceMeshes": 0, "cacheAfterSourceMeshes": 100,
        "rows": rows,
    }


def interpret(result: dict) -> dict:
    return probe.interpret_readback(result, expected_rows(), BLENDER_SHA,
                                    NATIVE_SHA, SUMMARY_SHA, HOST_SHA)


class BladePayloadTests(unittest.TestCase):
    def test_complete_three_way_rows_still_do_not_verify_equivalence(self) -> None:
        result = worker_result()
        result["rows"][0]["fields"]["positions"]["repaired"]["sha256"] = "e" * 64
        checked = interpret(result)
        self.assertEqual(checked["status"], "SOURCE_BLADE_PAYLOAD_READBACK")
        self.assertEqual(checked["relocationRows"], 60)
        self.assertEqual(checked["fieldMatchRows"]["sourceNative"]["positions"], 60)
        self.assertEqual(checked["fieldMatchRows"]["nativeRepaired"]["positions"], 59)
        self.assertEqual(checked["fieldMatchRows"]["sourceRepaired"]["positions"], 59)
        self.assertFalse(checked["rows"][0]["equivalenceVerified"])
        self.assertFalse(checked["nativeBlendExportApproved"])
        self.assertFalse(checked["blendSaved"])
        self.assertFalse(checked["usfExported"])

    def test_rejects_missing_reordered_and_forged_relocation_paths(self) -> None:
        result = worker_result()
        result["rows"].pop()
        with self.assertRaisesRegex(probe.BladePayloadError, "coverage"):
            interpret(result)
        result = worker_result()
        result["rows"][0], result["rows"][1] = result["rows"][1], result["rows"][0]
        with self.assertRaisesRegex(probe.BladePayloadError, "path"):
            interpret(result)
        result = worker_result()
        result["rows"][0]["sourcePredictedPath"] = result["rows"][0]["repairedPath"]
        with self.assertRaisesRegex(probe.BladePayloadError, "source mapping"):
            interpret(result)
        result = worker_result()
        result["rows"][0]["equivalenceVerified"] = True
        with self.assertRaisesRegex(probe.BladePayloadError, "gate"):
            interpret(result)

    def test_rejects_no_write_and_sdk_guard_claim_changes(self) -> None:
        for field in ("blendSaved", "usfExported", "nativeBlendExportApproved",
                      "sdkPackerGuarded"):
            with self.subTest(field=field):
                result = worker_result()
                result[field] = True
                with self.assertRaisesRegex(probe.BladePayloadError, "gate"):
                    interpret(result)

    def test_rejects_invalid_or_incomplete_component_digests(self) -> None:
        result = worker_result()
        result["rows"][5]["fields"].pop("normals")
        with self.assertRaisesRegex(probe.BladePayloadError, "path"):
            interpret(result)
        result = worker_result()
        result["rows"][5]["fields"]["positions"]["native"]["sha256"] = "not-a-hash"
        with self.assertRaisesRegex(probe.BladePayloadError, "digest"):
            interpret(result)
        result = worker_result()
        result["rows"][5]["fields"]["uvCoordinates"]["repaired"]["names"] = []
        with self.assertRaisesRegex(probe.BladePayloadError, "UV names"):
            interpret(result)

    def test_parser_requires_one_bounded_marker(self) -> None:
        raw = worker_result()
        line = probe.RESULT_PREFIX + json.dumps(raw)
        parsed = probe.parse_result("Blender startup\n" + line, expected_rows(),
                                    BLENDER_SHA, NATIVE_SHA, SUMMARY_SHA, HOST_SHA)
        self.assertEqual(parsed["relocationRows"], 60)
        with self.assertRaisesRegex(probe.BladePayloadError, "one bounded"):
            probe.parse_result(line + "\n" + line, expected_rows(), BLENDER_SHA,
                               NATIVE_SHA, SUMMARY_SHA, HOST_SHA)


if __name__ == "__main__":
    unittest.main()
