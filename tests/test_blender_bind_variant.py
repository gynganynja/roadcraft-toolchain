"""No-Blender tests for variant bind identity and root gating."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_bind_variant as variant  # noqa: E402
from tests.test_blender_bind_identity import readback  # noqa: E402


def sample(asset_name: str):
    result, gaps, blender_sha = readback()
    pins = variant.variants._pins(asset_name)
    result.update({
        "asset": asset_name,
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "repairedUsfSha256": pins["repairedUsfSha256"],
        "nativeExportRootName": asset_name,
    })
    inputs = {
        "assetDigest": pins["sourceAssetDigest"],
        "repairedSha256": pins["repairedUsfSha256"],
        "nativeSha256": "b" * 64,
        "summarySha256": "c" * 64,
        "gapRows": gaps,
    }
    return result, inputs, blender_sha


class VariantBindTests(unittest.TestCase):
    def test_both_variants_keep_own_asset_roots_and_blocked_gate(self):
        for asset in variant.variants.ASSET_PINS:
            with self.subTest(asset=asset):
                worker, inputs, blender_sha = sample(asset)
                result = variant.interpret_readback(worker, inputs, asset,
                                                    blender_sha, "a" * 64)
                self.assertEqual(result["asset"], asset)
                self.assertEqual(result["nativeExportRootName"], asset)
                self.assertEqual(result["repairedRootName"], "cat_d11t")
                self.assertEqual(result["mappedRows"], 126)
                self.assertEqual(result["sourceNativeOrderedIdentityMatches"], 126)
                self.assertFalse(result["nativeBlendExportApproved"])

    def test_variant_root_or_repaired_pin_cannot_be_relabelled(self):
        worker, inputs, blender_sha = sample("cat_d11t_v2")
        worker["nativeExportRootName"] = "cat_d11t"
        with self.assertRaises(variant.VariantBindError):
            variant.interpret_readback(worker, inputs, "cat_d11t_v2",
                                       blender_sha, "a" * 64)
        worker, inputs, blender_sha = sample("cat_d11t_v3")
        worker["repairedUsfSha256"] = "f" * 64
        with self.assertRaises(variant.VariantBindError):
            variant.interpret_readback(worker, inputs, "cat_d11t_v3",
                                       blender_sha, "a" * 64)

    def test_partial_rows_or_write_gate_fail_through_base_validator(self):
        worker, inputs, blender_sha = sample("cat_d11t_v2")
        worker["rows"].pop()
        with self.assertRaises(variant.base.BindIdentityError):
            variant.interpret_readback(worker, inputs, "cat_d11t_v2",
                                       blender_sha, "a" * 64)
        worker, inputs, blender_sha = sample("cat_d11t_v2")
        worker["rows"][0]["sourceObject"] = ""
        with self.assertRaises(variant.VariantBindError):
            variant.interpret_readback(worker, inputs, "cat_d11t_v2",
                                       blender_sha, "a" * 64)
        worker, inputs, blender_sha = sample("cat_d11t_v2")
        worker["nativeBlendExportApproved"] = True
        with self.assertRaises(variant.VariantBindError):
            variant.interpret_readback(worker, inputs, "cat_d11t_v2",
                                       blender_sha, "a" * 64)


if __name__ == "__main__":
    unittest.main()
