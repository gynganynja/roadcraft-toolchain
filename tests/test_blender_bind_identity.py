"""No-Blender tests for bounded bind identity and inverse comparisons."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.blender_bind_identity import (  # noqa: E402
    BLEND_SHA256, BLENDER_VERSION_PINS, MAPPER_WORKER_SHA256,
    USF_SHA256, WORKLIST_SHA256, BindIdentityError, compare_binds,
    interpret_readback,
)


def bind(identity: str, offset: float = 0.0) -> dict:
    inverse = [1.0 if row == col else 0.0
               for row in range(4) for col in range(4)]
    inverse[3] = offset
    return {"sourceId": identity, "inverse": inverse}


def readback() -> tuple[dict, list[dict], str]:
    blender_sha = next(iter(BLENDER_VERSION_PINS))
    gaps = [{"path": f"|@root|mesh_{i}",
             "nativeExportSkinBoneUidCount": 2,
             "repairedSkinBoneUidCount": 1} for i in range(126)]
    source = [bind("|rig|a"), bind("|rig|b")]
    native = compare_binds(source, copy.deepcopy(source))
    repaired = compare_binds(source, [bind("|rig|a")])
    rows = [{"path": gap["path"], "sourceObject": f"mesh_{i}",
             "sourceNative": copy.deepcopy(native),
             "sourceRepaired": copy.deepcopy(repaired),
             "nativeSelfMaxElementError": 0.0,
             "repairedSelfMaxElementError": 0.0}
            for i, gap in enumerate(gaps)]
    result = {
        "schemaVersion": 1, "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256, "repairedUsfSha256": USF_SHA256,
        "nativeExportUsfSha256": "b" * 64,
        "worklistSha256": WORKLIST_SHA256, "summarySha256": "c" * 64,
        "blenderSha256": blender_sha, "hostSha256": "a" * 64,
        "mapperWorkerSha256": MAPPER_WORKER_SHA256,
        "blenderVersion": BLENDER_VERSION_PINS[blender_sha] + "0",
        "sceneFrame": 1, "sourceSceneMeshCount": 210,
        "nativeExportRootName": "cat_d11t", "repairedRootName": "cat_d11t",
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False, "rows": rows,
    }
    return result, gaps, blender_sha


class BindIdentityTests(unittest.TestCase):
    def test_identity_order_and_missing_bone_are_distinct(self):
        source = [bind("|rig|a"), bind("|rig|b")]
        reordered = compare_binds(source, list(reversed(source)))
        self.assertFalse(reordered["orderedIdentityMatch"])
        self.assertEqual(reordered["sharedIdentityCount"], 2)
        self.assertEqual(reordered["missingFromUsf"], [])
        missing = compare_binds(source, [bind("|rig|a")])
        self.assertEqual(missing["missingFromUsf"], ["|rig|b"])
        self.assertEqual(missing["sharedIdentityCount"], 1)
        no_shared = compare_binds(source, [bind("|rig|c")])
        self.assertEqual(no_shared["sharedIdentityCount"], 0)
        self.assertFalse(no_shared["sharedInverseWithinTolerance"])

    def test_inverse_error_and_bad_matrix_fail_closed(self):
        source = [bind("|rig|a")]
        near = compare_binds(source, [bind("|rig|a", 0.000001)])
        self.assertTrue(near["sharedInverseWithinTolerance"])
        far = compare_binds(source, [bind("|rig|a", 0.001)])
        self.assertFalse(far["sharedInverseWithinTolerance"])
        with self.assertRaises(BindIdentityError):
            compare_binds(source, [bind("|rig|a"), bind("|rig|a")])
        corrupt = bind("|rig|a")
        corrupt["inverse"][0] = float("nan")
        with self.assertRaises(BindIdentityError):
            compare_binds(source, [corrupt])

    def test_complete_readback_recomputes_coverage_and_gates(self):
        data, gaps, blender_sha = readback()
        compact = interpret_readback(data, gaps, blender_sha=blender_sha,
                                     native_sha="b" * 64, summary_sha="c" * 64,
                                     host_sha="a" * 64)
        self.assertEqual(compact["mappedRows"], 126)
        self.assertEqual(compact["sourceNativeOrderedIdentityMatches"], 126)
        self.assertEqual(compact["sourceRepairedOrderedIdentityMatches"], 0)
        self.assertEqual(compact["sourceNativeInverseWithinTolerance"], 126)
        self.assertFalse(compact["nativeBlendExportApproved"])

    def test_partial_contradictory_or_gate_changed_readback_fails(self):
        data, gaps, blender_sha = readback()
        data["rows"].pop()
        with self.assertRaises(BindIdentityError):
            interpret_readback(data, gaps, blender_sha=blender_sha,
                               native_sha="b" * 64, summary_sha="c" * 64,
                               host_sha="a" * 64)
        data, gaps, blender_sha = readback()
        data["rows"][0]["sourceRepaired"]["sharedIdentityCount"] = 2
        with self.assertRaises(BindIdentityError):
            interpret_readback(data, gaps, blender_sha=blender_sha,
                               native_sha="b" * 64, summary_sha="c" * 64,
                               host_sha="a" * 64)
        data, gaps, blender_sha = readback()
        data["nativeBlendExportApproved"] = True
        with self.assertRaises(BindIdentityError):
            interpret_readback(data, gaps, blender_sha=blender_sha,
                               native_sha="b" * 64, summary_sha="c" * 64,
                               host_sha="a" * 64)


if __name__ == "__main__":
    unittest.main()
