"""Synthetic safety and comparison checks for native authoring diagnostic."""

from __future__ import annotations

import json
import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_authoring as authoring  # noqa: E402
from roadcraft.blender_parity_evidence import package_evidence  # noqa: E402
from roadcraft.blender_parity_diff import compare_node_rows  # noqa: E402
from roadcraft.source import capture_source_inventory, file_sha256  # noqa: E402


class BlenderParityDiffTests(unittest.TestCase):
    def test_complete_node_and_material_rig_differences(self) -> None:
        baseline = {
            "|root|BoneChassis_cdt|BoneBladeRoll_cdt": {"childCount": 1},
            "|root|Body_vis": {"mesh": {"materialNames": ["old"],
                                           "skinEntries": 4}},
        }
        candidate = {
            "|root|Body_vis": {"mesh": {"materialNames": ["new"],
                                           "skinEntries": 0}},
            "|root|New_vis": {"mesh": {"faces": 3}},
        }
        diff = compare_node_rows(baseline, candidate)
        self.assertEqual(diff["missingRigNodePaths"],
                         ["|root|BoneChassis_cdt|BoneBladeRoll_cdt"])
        self.assertEqual(diff["extraNodePaths"], ["|root|New_vis"])
        self.assertEqual(diff["changedFieldCounts"], {"mesh": 1})
        self.assertFalse(diff["matchesIndexedFields"])

    def test_equal_rows_remain_only_diagnostic(self) -> None:
        rows = {"|root": {"nodeVersion": 1}}
        self.assertTrue(compare_node_rows(rows, rows)["matchesIndexedFields"])


class BlenderAuthoringTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="roadcraft-authoring-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(authoring, "TOOLCHAIN_ROOT", self.root).start()
        source_root = self.root / "source"
        source_root.mkdir()
        self.blend = source_root / "asset.blend"
        self.blend.write_bytes(b"historical authoring document")
        self.usf = source_root / "export.usf"
        self.usf.write_bytes(b"repaired build file")
        inventory = capture_source_inventory(source_root, [{
            "asset": "test", "exportMethod": "usf-repair",
            "files": [
                {"path": "asset.blend", "role": "blend-reference"},
                {"path": "export.usf", "role": "build-usf"},
            ],
        }])
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps(inventory), encoding="utf-8")
        self.blender = self.root / "blender.exe"
        self.blender.write_bytes(b"synthetic blender binary")
        self.sdk = self.root / "sdk"
        lib = self.sdk / "saber/blender/lib/usf"
        lib.mkdir(parents=True)
        (lib / "export.py").write_text("# fixture\n", encoding="utf-8")
        converter = self.sdk / "saber/blender/blender_to_usf"
        converter.mkdir(parents=True)
        (converter / "name_convention_config.json").write_text("{}")
        (converter / "import_file.py").write_text("# fixture\n")
        self.scratch = self.root / "local/authoring"
        self.receipt = self.root / "operations/authoring.json"

    def _run(self, *, dry_run: bool = True):
        return authoring.run_authoring_probe(
            asset_name="test", inventory_path=self.inventory,
            inventory_sha256=file_sha256(self.inventory),
            blender_executable=self.blender,
            blender_sha256=file_sha256(self.blender),
            sdk_script_root=self.sdk, scratch_root=self.scratch,
            receipt_path=self.receipt, dry_run=dry_run,
        )

    def test_dry_run_verifies_pins_without_output(self) -> None:
        with mock.patch.object(authoring.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 0,
                                                           stdout="Blender 5.2.0 LTS\n")):
            result = self._run()
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertFalse(self.scratch.exists())
        self.assertFalse(self.receipt.exists())

    def test_mismatched_native_export_is_preserved_and_gate_blocked(self) -> None:
        def fake_blender(command, **kwargs):
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0,
                                                   stdout="Blender 5.2.0 LTS\n")
            candidate = Path(command[command.index("--candidate-usf") + 1])
            result_path = Path(command[command.index("--result") + 1])
            candidate.write_bytes(b"different native export")
            result_path.write_text(json.dumps({
                "blendSha256": file_sha256(self.blend),
                "baselineUsfSha256": file_sha256(self.usf),
                "candidateUsfSha256": file_sha256(candidate),
                "candidateUsfBytes": candidate.stat().st_size,
                "nativeBlendExportApproved": False,
                "baselineSemantic": {"nodes": 2},
                "candidateSemantic": {"nodes": 1},
                "nodeDiff": {"matchesIndexedFields": False,
                             "missingNodePaths": ["|root|Missing"]},
            }), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        with mock.patch.object(authoring.subprocess, "run", side_effect=fake_blender):
            result = self._run(dry_run=False)
        self.assertEqual(result["status"], "PARITY_DIFFERENT")
        self.assertEqual(result["exportGate"]["status"], "BLOCKED")
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertTrue((self.scratch / "candidate.usf").is_file())
        summary = json.loads(self.receipt.read_text())
        self.assertEqual(summary["status"], "PARITY_DIFFERENT")
        self.assertNotIn("diagnostic", summary)
        raw = (self.scratch / "full_receipt.json").read_bytes()
        archive = self.receipt.with_suffix(".json.gz").read_bytes()
        self.assertEqual(gzip.decompress(archive), raw)
        self.assertEqual(summary["fullRawSha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(summary["archiveSha256"], hashlib.sha256(archive).hexdigest())
        second = self.root / "second"
        package_evidence(json.loads(raw), summary_path=second / "summary.json",
                         archive_path=second / "summary.json.gz",
                         local_raw_path=second / "full.json")
        self.assertEqual(archive, (second / "summary.json.gz").read_bytes())

    def test_stale_blend_pin_rejects_before_running(self) -> None:
        self.blend.write_bytes(b"changed")
        with self.assertRaisesRegex(authoring.BlenderAuthoringError, "differs"):
            self._run()


if __name__ == "__main__":
    unittest.main()
