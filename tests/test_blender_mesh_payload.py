"""No-Blender unit tests for the pinned mesh-payload readback boundary."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_mesh_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, FIELD_NAMES,
    MAPPER_WORKER_SHA256, USF_SHA256, WORKLIST_SHA256,
    MeshPayloadError, interpret_readback, summarize_mesh,
)


def ns(**values):
    return SimpleNamespace(**values)


def mesh():
    return ns(
        vertices=[[1.0, 2.0, 3.0]], normals=[[0.0, 0.0, 1.0]],
        faces=[ns(material_index=2, edge_index=0)],
        uvsets=ns(uvs=[ns(name="UVMap", co=[[0.25, 0.75]])]),
        colorsets=ns(sets=[ns(colors=[0xFF123456])]),
        skin=ns(bones_per_vertex=4,
                skin=[ns(bone_idx=[1, 0, 0, 0],
                         weight=[1.0, 0.0, 0.0, 0.0])]),
    )


def readback():
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gap_rows = [{"path": f"|@root|mesh_{i}"} for i in range(126)]
    fields = {name: {"source": value, "native": copy.deepcopy(value), "match": True}
              for name, value in summarize_mesh(mesh()).items()}
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "fields": copy.deepcopy(fields)}
            for i, gap in enumerate(gap_rows)]
    data = {
        "schemaVersion": 1, "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256, "nativeExportUsfSha256": "b" * 64,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": "c" * 64,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "blendSaved": False,
        "usfExported": False, "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0", "rows": rows,
    }
    return data, gap_rows, blender_sha


class MeshPayloadTests(unittest.TestCase):
    def test_float32_wire_rounding_and_component_mutation(self):
        original = mesh()
        clone = copy.deepcopy(original)
        clone.vertices[0][0] = 1.0 + 1e-8  # rounds to 1.0 on the SDK wire
        self.assertEqual(summarize_mesh(original), summarize_mesh(clone))
        clone.uvsets.uvs[0].co[0][0] += 0.125
        comparison = summarize_mesh(clone)
        baseline = summarize_mesh(original)
        self.assertNotEqual(comparison["uvCoordinates"], baseline["uvCoordinates"])
        for field in FIELD_NAMES:
            if field != "uvCoordinates":
                self.assertEqual(comparison[field], baseline[field])

    def test_nonfinite_and_incomplete_payload_fail_closed(self):
        bad = mesh()
        bad.normals[0][0] = float("nan")
        with self.assertRaises(MeshPayloadError):
            summarize_mesh(bad)
        bad = mesh()
        bad.skin.skin[0].weight.pop()
        with self.assertRaises(MeshPayloadError):
            summarize_mesh(bad)

    def test_complete_readback_derives_counts_and_gates(self):
        data, gaps, blender_sha = readback()
        result = interpret_readback(data, gaps, blender_sha, "b" * 64,
                                    "c" * 64, "a" * 64)
        self.assertEqual(result["mappedRows"], 126)
        self.assertEqual(result["allComparedFieldsMatchRows"], 126)
        self.assertEqual(result["matchingRowsByField"],
                         {field: 126 for field in FIELD_NAMES})
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertFalse(result["tangentsCompared"])

    def test_partial_or_forged_readback_fails_closed(self):
        data, gaps, blender_sha = readback()
        data["rows"].pop()
        with self.assertRaises(MeshPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data, gaps, blender_sha = readback()
        data["rows"][0]["fields"]["positions"]["native"]["sha256"] = "d" * 64
        with self.assertRaises(MeshPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data["rows"][0]["fields"]["positions"]["match"] = False
        data["nativeBlendExportApproved"] = True
        with self.assertRaises(MeshPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)


if __name__ == "__main__":
    unittest.main()
