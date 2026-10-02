import tempfile
import unittest
import zipfile
from pathlib import Path

from roadcraft import pak_patch

CLASS = "ssl/auto_kgs25_kgs25.cls"
MARKUP = "models/mods/kgs25.tpl.asset/kgs25.tpl_markup"


def package(path: Path) -> None:
    """A retail-export-shaped package: deflated text, a stored blob, the markup twice."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo(CLASS, (2026, 10, 2, 12, 34, 4)),
                   "suspensionAxleCollection = [\r\n   {\r\n      max = 0.22\r\n   }\r\n]\r\n", zipfile.ZIP_DEFLATED)
        z.writestr(zipfile.ZipInfo("models/mods/kgs25.tpl.asset/tpl/kgs25.tpl_data", (2026, 10, 2, 12, 34, 4)),
                   bytes(range(256)) * 8, zipfile.ZIP_STORED)
        for _ in range(2):
            info = zipfile.ZipInfo(MARKUP, (2026, 10, 2, 12, 34, 4))
            z.writestr(info, "mass = 2500\r\n", zipfile.ZIP_DEFLATED)


class PakPatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.src = self.dir / "kgs25.pak"
        package(self.src)

    def test_patches_every_occurrence_and_copies_the_rest(self):
        out = self.dir / "fix" / "kgs25.pak"
        report = pak_patch.patch_text_members(self.src, out, {
            CLASS: lambda t: t.replace("max = 0.22", "max = 0.4"),
            MARKUP: lambda t: t.replace("2500", "7500")})
        self.assertEqual(report["changedMembers"], sorted([CLASS, MARKUP]))
        self.assertEqual([c["member"] for c in report["changes"]], [CLASS, MARKUP, MARKUP])
        with zipfile.ZipFile(out) as z:
            infos = z.infolist()
            self.assertEqual([i.filename for i in infos].count(MARKUP), 2)
            self.assertTrue(all(z.open(i).read() == b"mass = 7500\r\n" for i in infos if i.filename == MARKUP))
            self.assertIn(b"max = 0.4\r\n", z.read(CLASS))
        src_entries, _ = pak_patch.read_entries(self.src)
        out_entries, _ = pak_patch.read_entries(out)
        blob = [(a, b) for a, b in zip(src_entries, out_entries) if a["name"].endswith(b"tpl_data")]
        self.assertEqual(blob[0][0]["raw"], blob[0][1]["raw"])     # raw bytes, not recompressed

    def test_refuses_no_op_missing_member_wrong_source_and_overwrite(self):
        with self.assertRaises(pak_patch.PakPatchError):
            pak_patch.patch_text_members(self.src, self.dir / "a.pak", {CLASS: lambda t: t})
        with self.assertRaises(pak_patch.PakPatchError):
            pak_patch.patch_text_members(self.src, self.dir / "b.pak", {"ssl/missing.cls": lambda t: t + "x"})
        with self.assertRaises(pak_patch.PakPatchError):
            pak_patch.patch_text_members(self.src, self.dir / "c.pak", {CLASS: lambda t: t + "x"},
                                         expected_source_sha256="0" * 64)
        with self.assertRaises(pak_patch.PakPatchError):
            pak_patch.patch_text_members(self.src, self.src, {CLASS: lambda t: t + "x"})


if __name__ == "__main__":
    unittest.main()
