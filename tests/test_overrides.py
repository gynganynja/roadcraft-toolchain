import hashlib
import io
import json
import os
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from roadcraft import overrides

warnings.filterwarnings("ignore", "Duplicate name", UserWarning)  # duplicates are the point
SDK_ROOT = Path(os.environ.get("ROADCRAFT_GAME_ROOT",
                               r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft"))
SHARE = os.environ.get("ROADCRAFT_MODS_SHARE")

CFG = """ResourceManager:
  TagDirsToCache:
  - res://
  TagLayers:
  - PakName: client\\default\\second.pak
    Type: Pak
  - PakName: client\\default\\first.pak
    Type: Pak
  Other: 1
"""


def pak(path: Path, members) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, data in members:
            info = zipfile.ZipInfo("placeholder", (2026, 10, 1, 0, 0, 0))
            info.filename = name  # keep backslashes as some hand-built paks do
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return path


class OverrideManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.game = base / "game"
        paks = self.game / "root" / "paks" / "client" / "default"
        pak(paks / "first.pak", [("master_materials/combine_material_default.mm", b"retail mm"),
                                 ("ssl/shared.cls", b"retail cls")])
        pak(paks / "second.pak", [("ssl/shared.cls", b"retail cls")])
        pak(self.game / "root" / "paks" / "extra" / "zzz.pak", [("sounds/events/a.bnk", b"bank")])
        cfg = self.game / "root" / "config" / "editor" / "convert.cfg"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(CFG, encoding="utf-8")
        self.mods = base / "mods"
        self.mod_a = pak(self.mods / "alpha.pak", [
            ("Master_Materials\\Combine_Material_Default.mm", b"modded mm"),
            ("ssl/shared.cls", b"retail cls"),
            ("ssl/new.cls", b"new"),
            ("models/mods/a.tpl.asset/a.tpl_markup", b"m"),
            ("models/mods/a.tpl.asset/a.tpl_markup", b"m"),
            ("pct/lynx_0.pct_mip", b"same texture"),
            ("td/lynx.td", b"alpha td"),
            ("alpha.mod", b"title: alpha")])
        self.mod_b = pak(self.mods / "beta.pak", [
            ("pct/lynx_0.pct_mip", b"same texture"),
            ("td/lynx.td", b"beta td"),
            ("beta.mod", b"title: beta")])
        self.cache = base / "cache"

    def tearDown(self):
        self._tmp.cleanup()

    def rows(self, report, mod):
        found = next(m for m in report["mods"] if m["mod"] == mod)
        return {(r["member"], r["occurrence"]): r for r in found["rows"]}

    def test_retail_layer_order_follows_convert_cfg(self):
        self.assertEqual(overrides.retail_pak_order(self.game),
                         ["client/default/second.pak", "client/default/first.pak", "extra/zzz.pak"])

    def test_member_statuses_and_engine_effect(self):
        report = overrides.manifest([self.mods], self.game, cache_dir=self.cache)
        rows = self.rows(report, "alpha.pak")
        mm = rows[("Master_Materials\\Combine_Material_Default.mm", 1)]
        self.assertEqual(mm["status"], "shadows-retail")
        self.assertEqual(mm["tag"], "res://master_materials/combine_material_default.mm")
        self.assertEqual(mm["retail"]["target"],
                         "client/default/first.pak:master_materials/combine_material_default.mm")
        self.assertEqual((mm["effect"], mm["effectGrade"]), ("probably ignored", "Inferred"))
        shared = rows[("ssl/shared.cls", 1)]
        self.assertEqual(shared["status"], "identical-to-retail")
        self.assertEqual(shared["retail"]["pak"], "client/default/second.pak")
        self.assertEqual(shared["retail"]["otherRetailCopies"], 1)
        self.assertEqual(shared["effect"], "effective")
        self.assertEqual(rows[("ssl/new.cls", 1)]["status"], "new")
        self.assertEqual(rows[("models/mods/a.tpl.asset/a.tpl_markup", 2)]["status"], "new")
        tex = rows[("pct/lynx_0.pct_mip", 1)]
        self.assertEqual(tex["status"], "conflicts-with-mod")
        self.assertEqual(tex["modConflicts"], [{"mod": "beta.pak", "member": "pct/lynx_0.pct_mip",
                                                "identical": True}])
        self.assertEqual(tex["effect"], "order-dependent")
        self.assertFalse(rows[("td/lynx.td", 1)]["modConflicts"][0]["identical"])
        alpha = next(m for m in report["mods"] if m["mod"] == "alpha.pak")
        self.assertEqual(alpha["duplicateTags"], ["res://models/mods/a.tpl.asset/a.tpl_markup"])
        install = report["install"]
        self.assertEqual(install["conflictingTags"], 2)
        self.assertEqual(install["pairs"], [{"mods": ["alpha.pak", "beta.pak"], "tags": 2,
                                             "identical": 1, "different": 1}])

    def test_installed_paks_are_checked_without_rows(self):
        report = overrides.manifest([self.mod_a], self.game, installed=[self.mods])
        self.assertEqual([m["mod"] for m in report["mods"]], ["alpha.pak"])
        self.assertEqual(report["install"]["mods"], ["alpha.pak", "beta.pak"])

    def test_output_is_deterministic_and_cache_tracks_retail_changes(self):
        first = overrides.dumps(overrides.manifest([self.mods], self.game, cache_dir=self.cache))
        cached = overrides.retail_index(self.game, self.cache)
        self.assertTrue(cached["cache"]["hit"])
        self.assertEqual(first, overrides.dumps(overrides.manifest([self.mods], self.game, cache_dir=self.cache)))
        self.assertNotIn(str(self.cache), first)
        pak(self.game / "root" / "paks" / "client" / "default" / "first.pak",
            [("master_materials/combine_material_default.mm", b"modded mm")])
        self.assertFalse(overrides.retail_index(self.game, self.cache)["cache"]["hit"])
        rows = self.rows(overrides.manifest([self.mods], self.game, cache_dir=self.cache), "alpha.pak")
        self.assertEqual(rows[("Master_Materials\\Combine_Material_Default.mm", 1)]["status"],
                         "identical-to-retail")

    def test_cache_inside_the_game_folder_is_refused(self):
        with self.assertRaises(overrides.RoadcraftError):
            overrides.retail_index(self.game, self.game / "root" / "cache")

    def test_install_receipt_is_reported(self):
        txroot = Path(self._tmp.name) / "tx"
        receipt = txroot / "abc" / "receipt.json"
        receipt.parent.mkdir(parents=True)
        digest = hashlib.sha256(self.mod_b.read_bytes()).hexdigest()
        receipt.write_text(json.dumps({"transactionId": "abc", "installedPath": str(self.mod_b),
                                       "state": "INSTALLED", "candidateSha256": digest,
                                       "events": [{"at": "2026-10-13T00:00:00Z", "state": "INSTALLED"}]}))
        report = overrides.manifest([self.mods], self.game, transaction_root=txroot)
        self.assertEqual(report["install"]["receipts"]["beta.pak"]["currentBytesMatchCandidate"], True)
        self.assertNotIn("alpha.pak", report["install"]["receipts"])

    def test_main_prints_json_and_text(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(overrides.main(["pak", "manifest", str(self.mods), "--game", str(self.game),
                                             "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["install"]["conflictingTags"], 2)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(overrides.main([str(self.mod_a), str(self.mod_b), "--game", str(self.game)]), 0)
        self.assertIn("alpha.pak <-> beta.pak: 2 tags (1 identical, 1 different)", out.getvalue())


@unittest.skipUnless((SDK_ROOT / "root" / "paks").is_dir() and (SDK_ROOT / "root" / "mods").is_dir(),
                     "RoadCraft game folder with root/paks and root/mods not present; set ROADCRAFT_GAME_ROOT")
class InstalledModsIntegrationTests(unittest.TestCase):
    def test_installed_mods_manifest_is_deterministic(self):
        mods = SDK_ROOT / "root" / "mods"
        if not any(p.suffix.lower() == ".pak" for p in mods.iterdir()):
            self.skipTest("no installed mod paks")
        with tempfile.TemporaryDirectory() as cache:
            first = overrides.manifest([mods], SDK_ROOT, cache_dir=cache)
            second = overrides.manifest([mods], SDK_ROOT, cache_dir=cache)
        self.assertEqual(overrides.dumps(first), overrides.dumps(second))
        self.assertGreater(first["retail"]["tags"], 100000)
        for mod in first["mods"]:
            # SDK builds exclude retail tags from the resource graph, so they never shadow retail.
            self.assertNotIn("shadows-retail", mod["summary"], mod["mod"])


@unittest.skipUnless(SHARE and Path(SHARE).is_dir(), "mods share not available; set ROADCRAFT_MODS_SHARE")
class ShareIntegrationTests(unittest.TestCase):
    def test_dumptwuck_and_l275_share_identical_lynx_textures(self):
        paks = [Path(SHARE) / "dumptwuck.pak", Path(SHARE) / "l275_minespec.pak"]
        if not all(p.is_file() for p in paks):
            self.skipTest("dumptwuck.pak / l275_minespec.pak not on the share")
        report = overrides.manifest(paks, SDK_ROOT)
        self.assertEqual(report["install"]["pairs"], [{"mods": ["dumptwuck.pak", "l275_minespec.pak"],
                                                       "tags": 36, "identical": 36, "different": 0}])
        self.assertTrue(all("tuz_119lynx" in c["tag"] for c in report["install"]["conflicts"]))


if __name__ == "__main__":
    unittest.main()
