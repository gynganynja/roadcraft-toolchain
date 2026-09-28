"""Static armature parity: full-path matching and guarded no-save result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_armature_parity as probe  # noqa: E402
from roadcraft import blender_left_push_probe as left_probe  # noqa: E402


ROOT = probe.PATH_PREFIX
IDENTITY = [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def example_result() -> dict:
    source = {ROOT + "chassis": IDENTITY, ROOT + "chassis|tilt": IDENTITY}
    repaired = {ROOT + "chassis": IDENTITY,
                ROOT + "chassis|push|tilt": IDENTITY,
                ROOT + "chassis|push": IDENTITY}
    comparison = probe.compare_static_armature(source, repaired)
    return {"schemaVersion": 1, "asset": "cat_d11t",
            "blendSha256": probe.BLEND_SHA256,
            "repairedUsfSha256": probe.USF_SHA256,
            "blenderSha256": probe.BLENDER_SHA256,
            "blenderVersion": "5.2.0 LTS", "sceneFrame": 1,
            "classification": "all meshless nodes beneath USF armature; SDK bone affixes reported separately",
            "affixClassifiedUsfPaths": comparison["repairedStructuralPaths"],
            "unclassifiedMeshlessUsfPaths": [],
            "blendSaved": False, "usfExported": False,
            "nativeBlendExportApproved": False,
            "sourceWorldMatrices": source,
            "repairedWorldMatrices": repaired, **comparison}


class CompareStaticArmatureTests(unittest.TestCase):
    def test_covers_every_path_and_preserves_relocation_uncertainty(self) -> None:
        changed = IDENTITY.copy()
        changed[3] = 0.125
        result = probe.compare_static_armature(
            {ROOT + "a": IDENTITY, ROOT + "a|tilt": IDENTITY,
             ROOT + "b": IDENTITY},
            {ROOT + "a": changed, ROOT + "a|push": IDENTITY,
             ROOT + "a|push|tilt": IDENTITY, ROOT + "b": IDENTITY})
        self.assertEqual(result["status"], "STATIC_ARMATURE_DIFFERENT")
        self.assertEqual(result["sharedPathCount"], 2)
        self.assertEqual(result["changedMatrixCount"], 1)
        self.assertEqual(result["maxSharedMatrixError"], 0.125)
        self.assertEqual(result["sourceOnlyPaths"], [ROOT + "a|tilt"])
        self.assertEqual(result["repairedOnlyPaths"],
                         [ROOT + "a|push", ROOT + "a|push|tilt"])
        self.assertEqual(result["relocationCandidates"], [
            {"name": "tilt", "sourcePath": ROOT + "a|tilt",
             "repairedPath": ROOT + "a|push|tilt", "maxElementError": 0.0}])

    def test_finite_matrix_and_unique_path_checks(self) -> None:
        with self.assertRaisesRegex(probe.ArmatureParityError, "finite 4x4"):
            probe.compare_static_armature({ROOT + "a": [float("nan")] * 16},
                                          {ROOT + "a": IDENTITY})
        with self.assertRaisesRegex(probe.ArmatureParityError, "armature paths"):
            probe.compare_static_armature({"other|a": IDENTITY}, {})
        with self.assertRaisesRegex(probe.ArmatureParityError, "finite 4x4"):
            probe.compare_static_armature({ROOT + "a": IDENTITY,
                ROOT + "source_only": [float("inf")] * 16},
                {ROOT + "a": IDENTITY})

    def test_compact_diff_is_sorted_complete_and_bounded(self) -> None:
        full = example_result()
        full.update({"sourceUnchanged": True, "sdkUnchanged": True,
                     "workerSha256": "a" * 64,
                     "inventorySha256": probe.INVENTORY_SHA256})
        compact = probe.compact_result(full)
        self.assertEqual(compact["pathDiffRowCount"], 3)
        self.assertEqual([row["path"] for row in compact["pathDifferences"]],
                         sorted(row["path"] for row in compact["pathDifferences"]))
        self.assertEqual(compact["sourceBoneCount"], 2)
        self.assertEqual(compact["repairedStructuralCount"], 3)
        self.assertEqual(len(compact["structuralDigestSha256"]), 64)
        self.assertNotIn("sourceBonePaths", compact)
        unmatched_drift = json.loads(json.dumps(full))
        unmatched_drift["repairedWorldMatrices"][ROOT + "chassis|push"][3] = 0.01
        self.assertNotEqual(probe.compact_result(unmatched_drift)["structuralDigestSha256"],
                            compact["structuralDigestSha256"])
        too_many = full.copy()
        too_many["sourceOnlyPaths"] = [ROOT + f"n{i:03d}"
                                       for i in range(probe.MAX_DIFF_ROWS + 1)]
        with self.assertRaisesRegex(probe.ArmatureParityError, "row diagnostic bound"):
            probe.compact_result(too_many)


class ProbeGuardsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="roadcraft-armature-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.blend = self.root / "asset.blend"
        self.blend.write_bytes(b"blend")
        self.usf = self.root / "export.usf"
        self.usf.write_bytes(b"usf")
        self.blender = self.root / "blender.exe"
        self.blender.write_bytes(b"blender")
        self.sdk = self.root / "sdk"
        (self.sdk / "saber/blender/lib/usf").mkdir(parents=True)
        (self.sdk / "saber/blender/lib/usf/scene.py").write_bytes(b"sdk")
        inventory = self.root / "inventory.json"
        inventory_bytes = json.dumps({"sourceRoot": str(self.root)}).encode()
        inventory.write_bytes(inventory_bytes)
        self.registry = self.root / "project.json"
        self.registry.write_text(json.dumps({"accepted": {"authoringInventory": {
            "path": inventory.name, "sha256": digest(inventory_bytes)}}}))
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(probe, "INVENTORY_SHA256", digest(inventory_bytes)).start()
        mock.patch.object(probe, "BLEND_SHA256", digest(b"blend")).start()
        mock.patch.object(probe, "USF_SHA256", digest(b"usf")).start()
        mock.patch.object(probe, "BLENDER_SHA256", digest(b"blender")).start()
        mock.patch.object(probe, "BLENDER_VERSION_PINS", {
            digest(b"blender"): "5.2."}).start()
        mock.patch.object(probe, "PINNED_COUNTS", (2, 3, 3, 0)).start()
        mock.patch.object(left_probe, "SDK_PINS", {
            "saber/blender/lib/usf/scene.py": digest(b"sdk")}).start()
        mock.patch.object(probe, "_pinned_asset", return_value=(
            {}, self.root.resolve(), {}, self.blend, self.usf)).start()

    def _run(self, side_effect=None):
        result = example_result()
        completed = subprocess.CompletedProcess([], 0,
            stdout=probe.RESULT_PREFIX + json.dumps(result) + "\n", stderr="")
        with mock.patch.object(probe.subprocess, "run", side_effect=side_effect,
                               return_value=completed) as run:
            output = probe.run_probe(registry_path=self.registry,
                blender_executable=self.blender, sdk_script_root=self.sdk)
        return output, run

    def test_command_has_no_asset_write_or_export_argument(self) -> None:
        output, run = self._run()
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [str(self.blender.resolve()),
            "--background", "--factory-startup", "--disable-autoexec"])
        for forbidden in ("--run", "--scratch-root", "--candidate-usf",
                          "--result", "--output"):
            self.assertNotIn(forbidden, command)
        self.assertTrue(output["sourceUnchanged"])
        self.assertTrue(output["sdkUnchanged"])
        self.assertFalse(output["nativeBlendExportApproved"])

    def test_rejects_source_drift_before_launch(self) -> None:
        self.blend.write_bytes(b"different")
        with mock.patch.object(probe.subprocess, "run") as run:
            with self.assertRaisesRegex(Exception, "source Blend"):
                probe.run_probe(registry_path=self.registry,
                    blender_executable=self.blender, sdk_script_root=self.sdk)
            run.assert_not_called()

    def test_rejects_unreviewed_worker_before_launch(self) -> None:
        with (mock.patch.object(probe, "WORKER_SHA256", "0" * 64),
              mock.patch.object(probe.subprocess, "run") as run):
            with self.assertRaisesRegex(Exception, "armature worker"):
                probe.run_probe(registry_path=self.registry,
                    blender_executable=self.blender, sdk_script_root=self.sdk)
            run.assert_not_called()

    def test_rejects_source_drift_during_worker(self) -> None:
        def drift(*args, **kwargs):
            self.blend.write_bytes(b"different")
            return subprocess.CompletedProcess(args[0], 0,
                stdout=probe.RESULT_PREFIX + json.dumps(example_result()) + "\n",
                stderr="")
        with self.assertRaisesRegex(Exception, "source Blend after"):
            self._run(side_effect=drift)

    def test_rejects_partial_or_forged_matrix_report(self) -> None:
        partial = example_result()
        partial["sharedPathMatrixErrors"] = []
        with self.assertRaisesRegex(probe.ArmatureParityError,
                                    "do not cover every shared path"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(partial),
                               probe.BLENDER_SHA256)
        false_match = example_result()
        false_match["status"] = "STATIC_ARMATURE_MATCH"
        with self.assertRaisesRegex(probe.ArmatureParityError,
                                    "contradicts paths"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(false_match),
                               probe.BLENDER_SHA256)
        write_claim = example_result()
        write_claim["blendSaved"] = True
        with self.assertRaisesRegex(probe.ArmatureParityError, "no-write"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(write_claim),
                               probe.BLENDER_SHA256)

    def test_rejects_self_consistent_but_partial_readback(self) -> None:
        source = {ROOT + "chassis": IDENTITY}
        repaired = {ROOT + "chassis": IDENTITY,
                    ROOT + "chassis|push": IDENTITY}
        partial = example_result()
        partial.update(probe.compare_static_armature(source, repaired))
        partial.update({"sourceWorldMatrices": source,
                        "repairedWorldMatrices": repaired,
                        "affixClassifiedUsfPaths": sorted(repaired)})
        with self.assertRaisesRegex(probe.ArmatureParityError,
                                    "Pinned armature coverage differs"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(partial),
                               probe.BLENDER_SHA256)

    def test_rejects_version_and_unclassified_overlap(self) -> None:
        wrong_version = example_result()
        wrong_version["blenderVersion"] = "5.0.1"
        with self.assertRaisesRegex(probe.ArmatureParityError, "version"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(wrong_version),
                               probe.BLENDER_SHA256)
        overlap = example_result()
        overlap["unclassifiedMeshlessUsfPaths"] = [ROOT + "chassis"]
        with self.assertRaisesRegex(probe.ArmatureParityError, "classification"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(overlap),
                               probe.BLENDER_SHA256)
        forged_frame = example_result()
        forged_frame["sceneFrame"] = 2
        with self.assertRaisesRegex(probe.ArmatureParityError, "frame"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(forged_frame),
                               probe.BLENDER_SHA256)
        forged_matrix = example_result()
        forged_matrix["sourceWorldMatrices"][ROOT + "chassis|tilt"] = [2.0] + IDENTITY[1:]
        with self.assertRaisesRegex(probe.ArmatureParityError, "full static matrices"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(forged_matrix),
                               probe.BLENDER_SHA256)


if __name__ == "__main__":
    unittest.main()
