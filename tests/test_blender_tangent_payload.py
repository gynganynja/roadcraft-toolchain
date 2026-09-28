"""No-Blender checks for float32 tangent comparison and readback gates."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_tangent_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, MAPPER_WORKER_SHA256,
    PAYLOAD_WORKER_SHA256, USF_SHA256, WORKER_SHA256, WORKLIST_SHA256,
    TangentPayloadError, compare_tangents, interpret_readback,
)


def mesh(layers=None):
    if layers is None:
        layers = [[[1.0, 0.0, 0.0, -1.0],
                   [0.0, 1.0, 0.0, -1.0]]]
    length = len(layers[0]) if layers else 0
    return SimpleNamespace(vertices=[object() for _ in range(length)],
                           uvsets=SimpleNamespace(
                               uvs=[SimpleNamespace(co=[object() for _ in layer])
                                    for layer in layers], tangents=layers))


def readback():
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gaps = [{"path": f"|@root|mesh_{i}"} for i in range(126)]
    item = compare_tangents(mesh(), mesh())
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "tangents": copy.deepcopy(item)} for i, gap in enumerate(gaps)]
    data = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": "b" * 64,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": "c" * 64,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "workerSha256": WORKER_SHA256,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "payloadWorkerSha256": PAYLOAD_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0",
        "rows": rows,
    }
    return data, gaps, blender_sha


class TangentPayloadTests(unittest.TestCase):
    def test_float32_rounding_and_components(self):
        original = mesh()
        rounded = mesh()
        rounded.uvsets.tangents[0][0][0] = 1.0 + 1e-8
        same = compare_tangents(original, rounded)
        self.assertTrue(same["match"])
        changed = mesh()
        changed.uvsets.tangents[0][0][0] = 1.25
        changed.uvsets.tangents[0][1][3] = 1.0
        result = compare_tangents(original, changed)
        self.assertFalse(result["match"])
        self.assertEqual(result["differingValues"],
                         {"x": 1, "y": 0, "z": 0, "sign": 1})
        self.assertEqual(result["maxAbsoluteDifference"],
                         {"x": 0.25, "y": 0.0, "z": 0.0, "sign": 2.0})

    def test_invalid_shape_nonfinite_and_signed_zero(self):
        with self.assertRaises(TangentPayloadError):
            compare_tangents(mesh(), mesh([[[1, 0, 0, -1]]]))
        with self.assertRaises(TangentPayloadError):
            compare_tangents(mesh(), mesh([[[float("nan"), 0, 0, -1]]]))
        with self.assertRaises(TangentPayloadError):
            compare_tangents(mesh(), mesh([[[1, 0, 0]]]))
        original = mesh([[[0.0, 0.0, 0.0, 1.0]]])
        negative_zero = mesh([[[-0.0, 0.0, 0.0, 1.0]]])
        result = compare_tangents(original, negative_zero)
        self.assertEqual(result["differingValues"]["x"], 1)
        self.assertEqual(result["maxAbsoluteDifference"]["x"], 0.0)

    def test_full_result_counts_and_no_export_gate(self):
        data, gaps, blender_sha = readback()
        data["rows"][0]["tangents"] = compare_tangents(
            mesh(), mesh([[[1.25, 0, 0, -1], [0, 1, 0, 1]]]))
        result = interpret_readback(data, gaps, blender_sha, "b" * 64,
                                    "c" * 64, "a" * 64)
        self.assertEqual(result["mappedRows"], 126)
        self.assertEqual(result["matchingRows"], 125)
        self.assertEqual(result["differingValuesByComponent"],
                         {"x": 1, "y": 0, "z": 0, "sign": 1})
        self.assertFalse(result["nativeBlendExportApproved"])

    def test_partial_or_contradictory_worker_result_rejected(self):
        data, gaps, blender_sha = readback()
        data["rows"].pop()
        with self.assertRaises(TangentPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data, gaps, blender_sha = readback()
        data["rows"][0]["tangents"]["source"]["componentSha256"]["x"] = "d" * 64
        with self.assertRaises(TangentPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data, gaps, blender_sha = readback()
        data["nativeBlendExportApproved"] = True
        with self.assertRaises(TangentPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)


if __name__ == "__main__":
    unittest.main()
