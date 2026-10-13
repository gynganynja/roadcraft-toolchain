import io
import json
import os
import struct
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from roadcraft import pak_determinism as pd

MARKUP = "models/mods/x.tpl.asset/x.tpl_markup"
warnings.filterwarnings("ignore", "Duplicate name", UserWarning)  # duplicates are the point
SDK_ROOT = Path(os.environ.get("ROADCRAFT_GAME_ROOT",
                               r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft"))
JIMNY = SDK_ROOT / "Roadcraft Development Package" / "Jimny_RoadCraft_20261005" / "revisions"


def build(path: Path, stamp: tuple, attr: int, system: int, extra: bytes = b"") -> None:
    """An SDK-shaped pak: deflated and stored members, a duplicated markup, the .mod last."""
    members = [("ssl/auto_x.cls", b"mass = 1\r\n" * 50, zipfile.ZIP_DEFLATED),
               (MARKUP, b"markup\r\n" * 20, zipfile.ZIP_DEFLATED),
               ("models/mods/x.tpl.asset/tpl/x.tpl_data", bytes(range(256)) * 4, zipfile.ZIP_STORED),
               (MARKUP, b"markup\r\n" * 20, zipfile.ZIP_DEFLATED),
               ("pct/x_0.pct_mip", os.urandom(0) + b"\x01\x02" * 300, zipfile.ZIP_STORED),
               ("x.mod", b"title: x\n", zipfile.ZIP_DEFLATED)]
    with zipfile.ZipFile(path, "w", compresslevel=1) as archive:
        for name, data, method in members:
            info = zipfile.ZipInfo(name, stamp)
            info.compress_type = method
            info.external_attr = attr
            info.create_system = system
            info.extra = extra
            archive.writestr(info, data)


def ut_extra(seconds: int) -> bytes:
    return struct.pack("<HHBI", 0x5455, 5, 1, seconds)


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_two_rebuilds_become_byte_identical(self):
        a, b = self.dir / "a.pak", self.dir / "b.pak"
        build(a, (2026, 10, 5, 22, 3, 14), 0x81B60000, 0, ut_extra(1_760_000_000))
        build(b, (2026, 10, 6, 3, 36, 40), 0x81240000, 3, ut_extra(1_760_100_000))
        self.assertNotEqual(a.read_bytes(), b.read_bytes())
        self.assertFalse(pd.check(a)["normalized"])
        ra = pd.normalize(a, self.dir / "na.pak")
        rb = pd.normalize(b, self.dir / "nb.pak")
        self.assertEqual((self.dir / "na.pak").read_bytes(), (self.dir / "nb.pak").read_bytes())
        self.assertEqual(ra["outputSha256"], rb["outputSha256"])
        self.assertEqual(rb["patchedFields"], {"createSystem": 6, "dosTimestamp": 12, "externalAttr": 6,
                                               "timestampExtra": 12})
        self.assertTrue(pd.check(self.dir / "na.pak")["normalized"])

    def test_preserves_order_duplicates_sizes_and_content(self):
        src = self.dir / "src.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        report = pd.normalize(src, self.dir / "out.pak")
        self.assertEqual(report["duplicateOccurrences"], 1)
        self.assertEqual(src.stat().st_size, (self.dir / "out.pak").stat().st_size)
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(self.dir / "out.pak") as b:
            self.assertIsNone(b.testzip())
            ia, ib = a.infolist(), b.infolist()
            self.assertEqual([i.filename for i in ia], [i.filename for i in ib])
            self.assertEqual([i.filename for i in ib].count(MARKUP), 2)
            self.assertEqual(ib[-1].filename, "x.mod")
            for x, y in zip(ia, ib):
                self.assertEqual((x.CRC, x.compress_size, x.compress_type, x.header_offset),
                                 (y.CRC, y.compress_size, y.compress_type, y.header_offset))
                self.assertEqual(a.read(x), b.read(y))
                self.assertEqual(y.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(y.external_attr, pd.FILE_ATTR)

    def test_differences_are_limited_to_header_fields(self):
        src = self.dir / "src.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        pd.normalize(src, self.dir / "out.pak")
        before, after = src.read_bytes(), (self.dir / "out.pak").read_bytes()
        changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
        allowed = set()
        for row in pd.read_central_directory(src):
            allowed.update(range(row["localHeaderOffset"] + 10, row["localHeaderOffset"] + 14))
            allowed.update(range(row["centralOffset"] + 12, row["centralOffset"] + 16))
        self.assertTrue(changed)
        self.assertTrue(set(changed) <= allowed)

    def test_normalizing_a_normalized_pak_is_a_copy(self):
        src = self.dir / "src.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        pd.normalize(src, self.dir / "once.pak")
        report = pd.normalize(self.dir / "once.pak", self.dir / "twice.pak")
        self.assertEqual(report["patchedFields"], {})
        self.assertEqual((self.dir / "once.pak").read_bytes(), (self.dir / "twice.pak").read_bytes())

    def test_refuses_existing_output_and_leaves_it_untouched(self):
        src, dst = self.dir / "src.pak", self.dir / "dst.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        dst.write_bytes(b"keep")
        with self.assertRaises(pd.PakDeterminismError):
            pd.normalize(src, dst)
        self.assertEqual(dst.read_bytes(), b"keep")
        with self.assertRaises(pd.PakDeterminismError):
            pd.normalize(src, src)

    def test_corrupt_member_fails_verification_and_writes_nothing(self):
        src = self.dir / "src.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        blob = bytearray(src.read_bytes())
        row = next(r for r in pd.read_central_directory(src) if r["name"].endswith(".tpl_data"))
        blob[row["localHeaderOffset"] + 30 + len(row["rawName"]) + 5] ^= 0xFF
        src.write_bytes(bytes(blob))
        with self.assertRaises(pd.PakDeterminismError):
            pd.normalize(src, self.dir / "out.pak")
        self.assertEqual(list(self.dir.iterdir()), [src])

    def test_zip64_central_directory_is_patched_in_place(self):
        src = self.dir / "z64.pak"
        with zipfile.ZipFile(src, "w") as archive:
            for name in ("a.cls", "a.cls", "pct/b.pct_mip"):
                info = zipfile.ZipInfo(name, (2026, 1, 2, 3, 4, 6))
                with archive.open(info, "w", force_zip64=True) as stream:
                    stream.write(name.encode() * 10)
        blob = bytearray(src.read_bytes())
        # Rewrite the plain end record to point at ZIP64 records, the retail-pak layout.
        eocd = blob.rfind(b"PK\x05\x06")
        _, _, _, n, total, cd_size, cd_off, _ = struct.unpack_from("<IHHHHIIH", blob, eocd)
        z64 = struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0, n, total, cd_size, cd_off)
        locator = struct.pack("<IIQI", 0x07064B50, 0, eocd, 1)
        end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
        src.write_bytes(bytes(blob[:eocd]) + z64 + locator + end)
        with zipfile.ZipFile(src) as archive:
            self.assertEqual(len(archive.infolist()), 3)
        report = pd.normalize(src, self.dir / "out.pak")
        self.assertEqual(report["members"], 3)
        self.assertTrue(pd.check(self.dir / "out.pak")["normalized"])

    def test_main_check_and_normalize(self):
        src = self.dir / "src.pak"
        build(src, (2026, 9, 16, 17, 20, 40), 0x81B60000, 0)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(pd.main(["pak", "check", str(src)]), 1)
            self.assertEqual(pd.main(["normalize", str(src), str(self.dir / "n.pak")]), 0)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(pd.main(["check", str(self.dir / "n.pak")]), 0)
        self.assertIn('"normalized": false', out.getvalue())


@unittest.skipUnless((JIMNY / "jimny-polished-v3" / "jimny.pak").is_file() and
                     (JIMNY / "jimny-static-installed-v4" / "jimny.pak").is_file(),
                     "SDK Jimny rebuild pair (v3/v4) not present; set ROADCRAFT_GAME_ROOT")
class RealRebuildPairTests(unittest.TestCase):
    def test_jimny_rebuilds_normalize_to_identical_bytes(self):
        v3 = JIMNY / "jimny-polished-v3" / "jimny.pak"
        v4 = JIMNY / "jimny-static-installed-v4" / "jimny.pak"
        with tempfile.TemporaryDirectory() as tmp:
            a = pd.normalize(v3, Path(tmp) / "v3.pak")
            b = pd.normalize(v4, Path(tmp) / "v4.pak")
        self.assertNotEqual(a["sourceSha256"], b["sourceSha256"])
        self.assertEqual(a["outputSha256"], b["outputSha256"])
        self.assertEqual(a["members"], 854)
        self.assertEqual(set(a["patchedFields"]), {"dosTimestamp"})
        json.dumps(a)


if __name__ == "__main__":
    unittest.main()
