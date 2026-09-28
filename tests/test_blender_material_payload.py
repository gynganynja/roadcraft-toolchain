"""No-Blender tests for ordered D11 material text and face-slot comparison."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_material_payload import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, MAPPER_WORKER_SHA256,
    USF_SHA256, WORKLIST_SHA256, MaterialPayloadError,
    interpret_readback, summarize_materials,
)


def _text(name="paint", texture="body_base", tint="[255, 128, 64, 32]"):
    return ("material = {\n   name = \"" + name + "\"\n   type = 0\n}\n"
            "layers = [\n textureName = \"" + texture + "\"\n"
            " albedo_tint = " + tint + "\n]\n")


def _mesh(*texts, face_indices=(0,)):
    materials = [SimpleNamespace(mat=text, ver=0x10A, vc_usage=0)
                 for text in texts]
    return SimpleNamespace(
        materials=SimpleNamespace(data=materials),
        faces=[SimpleNamespace(material_index=index) for index in face_indices],
    )


def _readback():
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gaps = [{"path": f"|@root|mesh_{i}"} for i in range(126)]
    source = summarize_materials(_mesh(_text()))
    repaired = summarize_materials(_mesh(_text(), _text("new_paint", "other")))
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "source": copy.deepcopy(source), "native": copy.deepcopy(source),
             "repaired": copy.deepcopy(repaired)}
            for i, gap in enumerate(gaps)]
    data = {
        "schemaVersion": 1, "asset": "cat_d11t", "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256, "nativeExportUsfSha256": "b" * 64,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": "c" * 64,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedUsfRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0",
        "rows": rows,
    }
    return data, gaps, blender_sha


class MaterialPayloadTests(unittest.TestCase):
    def test_full_text_and_extracted_references_change_with_parameters(self):
        source = summarize_materials(_mesh(_text()))
        same = summarize_materials(_mesh(_text()))
        texture = summarize_materials(_mesh(_text(texture="different")))
        tint = summarize_materials(_mesh(_text(tint="[255, 1, 2, 3]")))
        self.assertEqual(source, same)
        self.assertNotEqual(source["slots"][0]["textureReferences"],
                            texture["slots"][0]["textureReferences"])
        self.assertNotEqual(source["slots"][0]["fullTextSha256"],
                            texture["slots"][0]["fullTextSha256"])
        self.assertNotEqual(source["slots"][0]["albedoTints"],
                            tint["slots"][0]["albedoTints"])
        self.assertNotEqual(source["orderedSlotsSha256"],
                            tint["orderedSlotsSha256"])

    def test_slot_order_and_face_mapping_are_significant(self):
        a, b = _text("a"), _text("b")
        first = summarize_materials(_mesh(a, b, face_indices=(0, 1, 0)))
        swapped = summarize_materials(_mesh(b, a, face_indices=(0, 1, 0)))
        remapped = summarize_materials(_mesh(a, b, face_indices=(1, 0, 1)))
        self.assertNotEqual(first["orderedSlotsSha256"],
                            swapped["orderedSlotsSha256"])
        self.assertEqual(first["orderedSlotsSha256"],
                         remapped["orderedSlotsSha256"])
        self.assertNotEqual(first["faceMaterialIndices"],
                            remapped["faceMaterialIndices"])

    def test_invalid_material_face_reference_fails_closed(self):
        with self.assertRaises(MaterialPayloadError):
            summarize_materials(_mesh(_text(), face_indices=(1,)))
        with self.assertRaises(MaterialPayloadError):
            summarize_materials(_mesh("layers = []"))

    def test_complete_readback_counts_payload_and_repaired_label_gap(self):
        data, gaps, blender_sha = _readback()
        result = interpret_readback(data, gaps, blender_sha, "b" * 64,
                                    "c" * 64, "a" * 64)
        self.assertEqual(result["mappedRows"], 126)
        self.assertEqual(result["sourceNativeExactMaterialRows"], 126)
        self.assertEqual(result["sourceNativeFaceMappingRows"], 126)
        self.assertEqual(result["sourceRepairedExactMaterialRows"], 0)
        self.assertEqual(result["repairedOnlyMaterialLabelOccurrences"], 126)
        self.assertFalse(result["textureBytesCompared"])
        self.assertFalse(result["nativeBlendExportApproved"])

    def test_partial_or_contradictory_readback_fails_closed(self):
        data, gaps, blender_sha = _readback()
        data["rows"].pop()
        with self.assertRaises(MaterialPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data, gaps, blender_sha = _readback()
        data["rows"][0]["native"]["slots"][0]["name"] = "forged"
        with self.assertRaises(MaterialPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)
        data, gaps, blender_sha = _readback()
        data["nativeBlendExportApproved"] = True
        with self.assertRaises(MaterialPayloadError):
            interpret_readback(data, gaps, blender_sha, "b" * 64,
                               "c" * 64, "a" * 64)


if __name__ == "__main__":
    unittest.main()
