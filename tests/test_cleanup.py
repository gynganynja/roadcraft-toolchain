from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from roadcraft.cleanup import TEMPLATE_NAMES, build_review, scan_template_copies


class CleanupReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.sdk = root / "sdk" / "Templates"
        self.run = root / "runs"
        self.copies = self.run / "one" / "editor_data" / "Templates"
        self.sdk.mkdir(parents=True)
        self.copies.mkdir(parents=True)
        for name in TEMPLATE_NAMES:
            data = (name + "-SDK").encode()
            (self.sdk / name).write_bytes(data)
            (self.copies / name).write_bytes(data)
        (self.copies / "source.blend").write_bytes(b"authored; keep")

    def test_selects_only_matching_templates(self) -> None:
        review = build_review([self.run], self.sdk)
        self.assertEqual(review["templateCopyCount"], 3)
        self.assertEqual({Path(x["path"]).name for x in review["templateCopies"]},
                         TEMPLATE_NAMES)
        self.assertGreater(review["templateAllocatedBytes"], 0)
        self.assertTrue(all(x["hardLinks"] == 1 for x in review["templateCopies"]))
        self.assertNotIn("source.blend", str(review["templateCopies"]))

    def test_changed_copy_fails_closed(self) -> None:
        (self.copies / "mod_scene_1x1.fct.zip").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SDK template mismatch"):
            scan_template_copies([self.run], self.sdk)

    def test_hardlinked_copy_fails_closed(self) -> None:
        candidate = self.copies / "mod_scene_2x2.fct.zip"
        sibling = self.copies / "another-name.zip"
        try:
            sibling.hardlink_to(candidate)
        except OSError as exc:
            self.skipTest(f"Hard links unavailable in test location: {exc}")
        with self.assertRaisesRegex(ValueError, "other hard links"):
            scan_template_copies([self.run], self.sdk)


if __name__ == "__main__":
    unittest.main()
