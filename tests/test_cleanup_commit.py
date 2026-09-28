import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from roadcraft import cleanup, core
from roadcraft.cleanup_commit import CleanupBlocked, commit_template_cleanup


class CleanupCommitTests(unittest.TestCase):
    def fixture(self, root: Path):
        originals = root / "sdk" / "Templates"
        originals.mkdir(parents=True)
        for name in cleanup.TEMPLATE_NAMES:
            (originals / name).write_bytes(name.encode())
        runs = root / "old" / "runs"
        candidate = runs / "one" / "editor_data" / "Templates" / "mod_scene_1x1.fct.zip"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(candidate.name.encode())
        review = cleanup.build_review([runs], originals)
        manifest = root / "review.json"
        manifest.write_text(json.dumps(review), encoding="utf-8")
        return manifest, core.sha256_file(manifest), candidate, originals

    def test_dry_run_and_exact_apply_leave_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, digest, candidate, originals = self.fixture(root)
            journal = root / "journal"
            plan = commit_template_cleanup(manifest, digest, journal)
            self.assertTrue(plan["dryRun"])
            self.assertEqual(plan["candidateCount"], 1)
            self.assertFalse(journal.exists())
            with patch("roadcraft.cleanup_commit.core._editor_processes", return_value=([], None)):
                result = commit_template_cleanup(manifest, digest, journal, apply=True)
            self.assertEqual(result["state"], "COMPLETE")
            self.assertEqual(result["deletedCount"], 1)
            self.assertFalse(candidate.exists())
            self.assertTrue((originals / candidate.name).exists())
            self.assertTrue(Path(result["receiptPath"]).exists())

    def test_changed_file_or_manifest_hash_blocks_every_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, digest, candidate, _ = self.fixture(root)
            with self.assertRaises(CleanupBlocked):
                commit_template_cleanup(manifest, "0" * 64, root / "journal", apply=True)
            candidate.write_bytes(b"changed")
            with self.assertRaises(CleanupBlocked):
                commit_template_cleanup(manifest, digest, root / "journal", apply=True)
            self.assertTrue(candidate.exists())
            self.assertFalse((root / "journal").exists())

    def test_painter_does_not_block_old_roadcraft_template_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, digest, candidate, _ = self.fixture(root)
            with patch("roadcraft.cleanup_commit.core._editor_processes",
                       return_value=([{"name": "Adobe Substance 3D Painter.exe", "pid": 1}], None)):
                result = commit_template_cleanup(manifest, digest, root / "journal", apply=True)
            self.assertEqual(result["deletedCount"], 1)
            self.assertFalse(candidate.exists())

    def test_roadcraft_editor_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest, digest, candidate, _ = self.fixture(root)
            with patch("roadcraft.cleanup_commit.core._editor_processes",
                       return_value=([{"name": "IntegrationStudio.exe", "pid": 2}], None)):
                with self.assertRaises(CleanupBlocked):
                    commit_template_cleanup(manifest, digest, root / "journal", apply=True)
            self.assertTrue(candidate.exists())


if __name__ == "__main__":
    unittest.main()
