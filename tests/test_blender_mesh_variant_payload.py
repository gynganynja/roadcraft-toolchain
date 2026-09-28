"""No-Blender tests for v2/v3 ordered mesh-payload readback boundaries."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_mesh_payload as base  # noqa: E402
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    BLENDER_VERSION_PINS, WORKLIST_SHA256,
)
from roadcraft.blender_mesh_variant_payload import (  # noqa: E402
    ASSET_PINS, BASE_MESH_HOST_SHA256, COLOR_DETAIL_PATH,
    VariantMeshPayloadError, _pins, interpret_readback,
    summarize_color_detail,
)


def _mesh(x=1.0, normal_z=1.0, uv_u=0.25, color=0xFF123456):
    return SimpleNamespace(
        vertices=[[x, 2.0, 3.0]], normals=[[0.0, 0.0, normal_z]],
        faces=[SimpleNamespace(material_index=0, edge_index=0)],
        uvsets=SimpleNamespace(uvs=[SimpleNamespace(name="UVMap",
                                                  co=[[uv_u, 0.75]])]),
        colorsets=SimpleNamespace(sets=[SimpleNamespace(colors=[color])]),
        skin=SimpleNamespace(bones_per_vertex=0, skin=[]),
    )


def _readback(asset_name: str):
    pins = ASSET_PINS[asset_name]
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gaps = [{"path": COLOR_DETAIL_PATH if i == 0 else f"|@root|mesh_{i}"}
            for i in range(126)]
    source = base.summarize_mesh(_mesh())
    repaired = base.summarize_mesh(_mesh(1.25))
    fields = {name: {"source": value, "native": copy.deepcopy(value),
                     "repaired": repaired[name]}
              for name, value in source.items()}
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "fields": copy.deepcopy(fields)}
            for i, gap in enumerate(gaps)]
    color_detail = summarize_color_detail([[0xFF123456]], [[0xFF123456]])
    color_detail.update({"cacheAfterUsfReads": 0, "cacheBeforeTarget": 1,
                         "cacheAfterTarget": 2, "cacheAfterAll": 2})
    raw = {
        "schemaVersion": 1, "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": pins["nativeUsfSha256"],
        "summarySha256": pins["summarySha256"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "baseMeshHostSha256": BASE_MESH_HOST_SHA256,
        "mapperWorkerSha256": base.MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": asset_name,
        "repairedUsfRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0",
        "colorDetail": color_detail,
        "nativeColorMismatchDetails": [],
        "rows": rows,
    }
    return raw, gaps, blender_sha


class VariantMeshPayloadTests(unittest.TestCase):
    def test_variant_specific_pins_and_complete_aggregation(self):
        self.assertNotEqual(_pins("cat_d11t_v2")["nativeUsfSha256"],
                            _pins("cat_d11t_v3")["nativeUsfSha256"])
        for asset_name in ASSET_PINS:
            raw, gaps, blender_sha = _readback(asset_name)
            result = interpret_readback(raw, gaps, asset_name,
                                        blender_sha, "a" * 64)
            self.assertEqual(result["mappedRows"], 126)
            self.assertEqual(result["allComparedNativeFieldsMatchRows"], 126)
            self.assertEqual(result["matchingNativeRowsByField"],
                             {name: 126 for name in base.FIELD_NAMES})
            self.assertEqual(result["repairedOrderedDigestEqualRowsByField"]["positions"], 0)
            self.assertEqual(result["repairedSameElementCountRowsByField"]["positions"], 126)
            self.assertEqual(result["repairedPositionAlignedRows"], 0)
            self.assertFalse(result["repairedSemanticMeshParityClaimed"])
            self.assertFalse(result["nativeBlendExportApproved"])

    def test_normals_uv_and_colors_compared_only_when_positions_align(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        different = base.summarize_mesh(_mesh(
            normal_z=0.5, uv_u=0.5, color=0xFF654321))
        for name in ("positions", "normals", "uvCoordinates", "packedColors"):
            raw["rows"][0]["fields"][name]["repaired"] = different[name]
        result = interpret_readback(raw, gaps, "cat_d11t_v2",
                                    blender_sha, "a" * 64)
        self.assertEqual(result["repairedPositionAlignedRows"], 1)
        self.assertEqual(result["repairedComparableNormalsOnAlignedRows"], 1)
        self.assertEqual(result["repairedEqualNormalsOnAlignedRows"], 0)
        self.assertEqual(result["repairedComparableUvOnAlignedRows"], 1)
        self.assertEqual(result["repairedEqualUvOnAlignedRows"], 0)
        self.assertEqual(result["repairedComparableColorsOnAlignedRows"], 1)
        self.assertEqual(result["repairedEqualColorsOnAlignedRows"], 0)

    def test_bounded_color_detail_reports_actual_packed_values(self):
        detail = summarize_color_detail(
            [[0xFF123456, 0xFFABCDEF]], [[0xFF123456, 0xFFABCDEE]])
        self.assertEqual(detail["differentEntries"], 1)
        self.assertEqual(detail["source"]["elements"], 2)
        self.assertEqual(detail["firstDifferences"], [
            {"set": 0, "index": 1, "source": 0xFFABCDEF,
             "native": 0xFFABCDEE}])
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        raw["colorDetail"]["differentEntries"] = 1
        with self.assertRaises(VariantMeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v2", blender_sha,
                               "a" * 64)
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        path = raw["rows"][1]["path"]
        changed = summarize_color_detail(
            [[0xFF123456]], [[0xFF123457]], path)
        raw["rows"][1]["fields"]["packedColors"]["native"] = changed["native"]
        raw["nativeColorMismatchDetails"] = [changed]
        result = interpret_readback(raw, gaps, "cat_d11t_v2",
                                    blender_sha, "a" * 64)
        self.assertEqual(result["matchingNativeRowsByField"]["packedColors"], 125)
        self.assertEqual(result["nativeColorMismatchDetails"][0]["firstDifferences"],
                         [{"set": 0, "index": 0, "source": 0xFF123456,
                           "native": 0xFF123457}])

    def test_native_payload_mutation_is_detected_with_same_blend_pin(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        raw["rows"][0]["fields"]["positions"]["native"] = (
            base.summarize_mesh(_mesh(1.5))["positions"])
        result = interpret_readback(raw, gaps, "cat_d11t_v2",
                                    blender_sha, "a" * 64)
        self.assertEqual(result["matchingNativeRowsByField"]["positions"], 125)
        self.assertEqual(result["allComparedNativeFieldsMatchRows"], 125)

    def test_incomplete_or_wrong_variant_fails_closed(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        with self.assertRaises(VariantMeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)
        raw["rows"].pop()
        with self.assertRaises(VariantMeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v2", blender_sha,
                               "a" * 64)
        with self.assertRaises(VariantMeshPayloadError):
            _pins("cat_d11t")
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        raw["rows"][0]["sourceObject"] = ""
        with self.assertRaises(VariantMeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v2", blender_sha,
                               "a" * 64)

    def test_invalid_digest_and_unapproved_export_gate_fail_closed(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v3")
        raw["rows"][0]["fields"]["uvCoordinates"]["native"]["sha256"] = "x" * 64
        with self.assertRaises(base.MeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)
        raw, gaps, blender_sha = _readback("cat_d11t_v3")
        raw["nativeBlendExportApproved"] = True
        with self.assertRaises(VariantMeshPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)


if __name__ == "__main__":
    unittest.main()
