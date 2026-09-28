import tempfile
import unittest
from pathlib import Path

from roadcraft.core import RoadcraftError
from roadcraft.manifest import capture_tree_manifest


class ManifestTests(unittest.TestCase):
    def test_explicit_inputs_leave_generated_logs_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "mods_source").mkdir()
            (root / "mods_source" / "a.usf").write_bytes(b"accepted")
            (root / "logs").mkdir()
            (root / "logs" / "latest.log").write_bytes(b"mutable")
            result = capture_tree_manifest(root, ["mods_source"])
            self.assertEqual([row["path"] for row in result["files"]],
                             ["mods_source/a.usf"])
            self.assertEqual(result["files"][0]["bytes"], 8)

    def test_overlap_and_escape_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source").mkdir()
            (root / "source" / "a").write_bytes(b"x")
            with self.assertRaises(RoadcraftError):
                capture_tree_manifest(root, ["source", "source/a"])
            with self.assertRaises(RoadcraftError):
                capture_tree_manifest(root, ["../outside"])


if __name__ == "__main__":
    unittest.main()
