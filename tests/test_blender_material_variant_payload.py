"""No-Blender coverage of v2/v3 material identity and row aggregation."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_material_payload as base  # noqa: E402
from roadcraft.blender_material_variant_payload import (  # noqa: E402
    ASSET_PINS, VariantMaterialPayloadError, _pins, interpret_readback,
)
from roadcraft.blender_mesh_inventory import (  # noqa: E402
    BLENDER_VERSION_PINS, WORKLIST_SHA256,
)


def _material(name: str):
    text = f'material = {{\n name = "{name}"\n}}\ntextureName = "texture_{name}"'
    return SimpleNamespace(mat=text, ver=0x10A, vc_usage=0)


def _summary(*names: str):
    mesh = SimpleNamespace(
        materials=SimpleNamespace(data=[_material(name) for name in names]),
        faces=[SimpleNamespace(material_index=0)],
    )
    return base.summarize_materials(mesh)


def _readback(asset_name: str):
    pins = ASSET_PINS[asset_name]
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gaps = [{"path": f"|@root|mesh_{i}"} for i in range(126)]
    source = _summary("base")
    repaired = _summary("base", "added")
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "source": copy.deepcopy(source), "native": copy.deepcopy(source),
             "repaired": copy.deepcopy(repaired)}
            for i, gap in enumerate(gaps)]
    raw = {
        "schemaVersion": 1, "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "blendSha256": pins["blendSha256"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportUsfSha256": pins["nativeUsfSha256"],
        "summarySha256": pins["summarySha256"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "baseMaterialHostSha256": base_host_sha(),
        "mapperWorkerSha256": base.MAPPER_WORKER_SHA256,
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": asset_name,
        "repairedUsfRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0",
        "rows": rows,
    }
    return raw, gaps, blender_sha


def base_host_sha():
    from roadcraft.blender_material_variant_payload import BASE_MATERIAL_HOST_SHA256
    return BASE_MATERIAL_HOST_SHA256


class VariantMaterialPayloadTests(unittest.TestCase):
    def test_both_variants_have_distinct_pins_and_complete_aggregation(self):
        self.assertNotEqual(_pins("cat_d11t_v2")["repairedUsfSha256"],
                            _pins("cat_d11t_v3")["repairedUsfSha256"])
        for asset_name in ASSET_PINS:
            raw, gaps, blender_sha = _readback(asset_name)
            result = interpret_readback(raw, gaps, asset_name,
                                        blender_sha, "a" * 64)
            self.assertEqual(result["mappedRows"], 126)
            self.assertEqual(result["sourceNativeExactMaterialRows"], 126)
            self.assertEqual(result["sourceNativeFaceMappingRows"], 126)
            self.assertEqual(result["sourceRepairedExactMaterialRows"], 0)
            self.assertEqual(result["repairedOnlyMaterialLabelOccurrences"], 126)
            self.assertEqual((result["sourceSlots"], result["nativeSlots"],
                              result["repairedSlots"]), (126, 126, 252))
            self.assertFalse(result["nativeBlendExportApproved"])

    def test_variant_native_mutation_is_detected_despite_equal_blend_pin(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        raw["rows"][0]["native"] = _summary("different")
        result = interpret_readback(raw, gaps, "cat_d11t_v2",
                                    blender_sha, "a" * 64)
        self.assertEqual(result["sourceNativeExactMaterialRows"], 125)
        self.assertEqual(result["sourceNativeOrderedNameRows"], 125)
        self.assertEqual(result["sourceNativeTextureReferenceRows"], 125)

    def test_wrong_variant_identity_or_partial_rows_fail_closed(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v2")
        with self.assertRaises(VariantMaterialPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)
        raw["rows"].pop()
        with self.assertRaises(VariantMaterialPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v2", blender_sha,
                               "a" * 64)
        with self.assertRaises(VariantMaterialPayloadError):
            _pins("cat_d11t")

    def test_contradictory_slots_or_export_gate_fail_closed(self):
        raw, gaps, blender_sha = _readback("cat_d11t_v3")
        raw["rows"][0]["native"]["slots"][0]["name"] = "forged"
        with self.assertRaises(base.MaterialPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)
        raw, gaps, blender_sha = _readback("cat_d11t_v3")
        raw["nativeBlendExportApproved"] = True
        with self.assertRaises(VariantMaterialPayloadError):
            interpret_readback(raw, gaps, "cat_d11t_v3", blender_sha,
                               "a" * 64)


if __name__ == "__main__":
    unittest.main()
