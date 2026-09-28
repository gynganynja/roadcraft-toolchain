"""No-Blender shape, float32 and result gates for D11 variant tangents."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_animation_variants import VARIANTS  # noqa: E402
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST_SHA256,
)
from roadcraft.blender_tangent_variants import (  # noqa: E402
    BASE_HOST_SHA256, INPUT_HOST_SHA256, MAPPER_WORKER_SHA256,
    WORKER_SHA256, TangentVariantError, compare_tangent_arrays,
    interpret_readback,
)


def mesh(values=None, name="UVMap"):
    if values is None:
        values = [[1.0, 0.0, 0.0, -1.0], [0.0, 1.0, 0.0, -1.0]]
    return SimpleNamespace(
        vertices=[object() for _ in values],
        uvsets=SimpleNamespace(
            uvs=[SimpleNamespace(name=name,
                                 co=[object() for _ in values])],
            tangents=[values]))


def readback(asset: str) -> tuple[dict, str, list[str]]:
    pins = VARIANTS[asset]
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    paths = [f"|@root|mesh_{i:03d}" for i in range(126)]
    native_rows = []
    repaired_rows = []
    for index, path in enumerate(paths):
        source = mesh()
        native = mesh()
        if index < 3:
            native.uvsets.tangents[0][0][0] = 1.25
        repaired = mesh()
        if index < 9:
            repaired = mesh([[1.0, 0.0, 0.0, -1.0]])
        native_rows.append({
            "path": path, "sourceObject": f"mesh_{index:03d}",
            "comparison": compare_tangent_arrays(source, native),
        })
        repaired_rows.append({
            "path": path, "sourceObject": f"mesh_{index:03d}",
            "comparison": compare_tangent_arrays(source, repaired),
        })
    return {
        "schemaVersion": 1, "asset": asset,
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": pins["repairedSha256"],
        "nativeExportUsfSha256": pins["nativeSha256"],
        "summarySha256": pins["summarySha256"],
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "hostSha256": "a" * 64,
        "workerSha256": WORKER_SHA256,
        "inputHostSha256": INPUT_HOST_SHA256,
        "baseTangentHostSha256": BASE_HOST_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "repairedRootName": "cat_d11t",
        "nativeRootName": asset,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "1",
        "nativeRows": native_rows, "repairedRows": repaired_rows,
    }, blender_sha, paths


class TangentVariantTests(unittest.TestCase):
    def test_float32_tangent_and_signed_zero(self):
        rounded = mesh()
        rounded.uvsets.tangents[0][0][0] = 1.0 + 1e-8
        self.assertEqual(compare_tangent_arrays(mesh(), rounded)["status"],
                         "BITWISE_MATCH")
        signed_zero = mesh()
        signed_zero.uvsets.tangents[0][0][1] = -0.0
        result = compare_tangent_arrays(mesh(), signed_zero)
        self.assertEqual(result["status"], "TANGENT_DIFFERENCE")
        self.assertEqual(result["differingValues"]["y"], 1)
        self.assertEqual(result["maxAbsoluteDifference"]["y"], 0.0)

    def test_shape_gap_and_uv_name_are_distinct(self):
        shape = compare_tangent_arrays(
            mesh(), mesh([[1.0, 0.0, 0.0, -1.0]]))
        self.assertEqual(shape["status"], "SHAPE_MISMATCH")
        self.assertIsNone(shape["differingValues"])
        name = compare_tangent_arrays(mesh(), mesh(name="OtherUV"))
        self.assertEqual(name["status"], "UV_NAME_MISMATCH")
        self.assertEqual(name["differingValues"],
                         {"x": 0, "y": 0, "z": 0, "sign": 0})

    def test_both_variant_full_row_aggregation(self):
        for asset in sorted(VARIANTS):
            with self.subTest(asset=asset):
                result, blender_sha, paths = readback(asset)
                checked = interpret_readback(result, asset, blender_sha,
                                             "a" * 64, paths)
                self.assertEqual(checked["status"],
                                 "SOURCE_VARIANT_TANGENT_ARRAY_READBACK")
                self.assertEqual(checked["sideSummaries"]["native"]["matchingRows"],
                                 123)
                self.assertEqual(checked["sideSummaries"]["repaired"]["shapeMismatchRows"],
                                 9)
                self.assertTrue(checked["sourceProjectionConsistentAcrossSides"])

    def test_incomplete_rows_cross_side_drift_and_gate_rejected(self):
        result, blender_sha, paths = readback("cat_d11t_v2")
        bad = copy.deepcopy(result)
        bad["nativeRows"].pop()
        with self.assertRaises(TangentVariantError):
            interpret_readback(bad, "cat_d11t_v2", blender_sha, "a" * 64, paths)
        bad = copy.deepcopy(result)
        bad["repairedRows"][0]["comparison"]["source"]["sha256"] = "b" * 64
        with self.assertRaises(TangentVariantError):
            interpret_readback(bad, "cat_d11t_v2", blender_sha, "a" * 64, paths)
        bad = copy.deepcopy(result)
        bad["nativeBlendExportApproved"] = True
        with self.assertRaises(TangentVariantError):
            interpret_readback(bad, "cat_d11t_v2", blender_sha, "a" * 64, paths)


if __name__ == "__main__":
    unittest.main()
