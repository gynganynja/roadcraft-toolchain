import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from roadcraft import pak_build, quiet


def _game(root: Path) -> Path:
    packer = root / pak_build.PACKER
    packer.parent.mkdir(parents=True)
    packer.write_bytes(b"fake packer")
    return root


def _project(root: Path) -> Path:
    project = root / "p"
    (project / "mods_source" / "ssl").mkdir(parents=True)
    (project / ".project").write_text("references: []\n", encoding="utf-8")
    return project


def _mod(root: Path, scenes: str = "[]") -> Path:
    mod = root / "demo.mod"
    mod.write_text('title: "Demo"\ndescription: "x"\nscenes: ' + scenes + "\nassets:\n- ssl/a.sso.resource\n"
                   "- ssl/b.sso.resource\n", encoding="utf-8")
    return mod


def _fake_packer(log_text: str, write: bool = True, code: int = 0):
    def run(argv, *, log=None, **_):
        out = Path(argv[argv.index("--output") + 1])
        if write:
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
                z.writestr("ssl/a.sso", b"payload")
                z.writestr("demo.mod", b"title: Demo\n")
        log.write(log_text.encode())
        return quiet.QuietResult(code, None, None, False, "test", 1, [], [], [], 0.1)
    return run


class PakBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = _game(self.root / "game")
        self.project = _project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_roots_come_from_the_mod_file(self):
        p = pak_build.plan(self.project, _mod(self.root), self.root / "out.pak", game_root=self.game)
        self.assertEqual(p.problems, [])
        self.assertEqual(p.roots, ["res://ssl/a.sso.resource", "res://ssl/b.sso.resource"])

    def test_preflight_refuses_blank_roots_scenes_and_existing_output(self):
        roots = self.root / "roots.txt"
        roots.write_text("res://ssl/a.sso.resource\n\n", encoding="utf-8")
        out = self.root / "out.pak"
        out.write_bytes(b"old")
        p = pak_build.plan(self.project, _mod(self.root, "[xscenes/a.scn]"), out, roots_file=roots,
                           game_root=self.game)
        text = " ".join(p.problems)
        self.assertIn("blank", text)
        self.assertIn("scenes", text)
        self.assertIn("exists", text)

    def test_missing_blob_fails_although_the_packer_exits_zero(self):
        p = pak_build.plan(self.project, _mod(self.root), self.root / "out.pak", game_root=self.game)
        log = "[-] x [ERROR] There isn't blob 'res://pct/x.pct' in layers.\n"
        with mock.patch.object(quiet, "run", _fake_packer(log)):
            receipt = pak_build.build(p)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["log"]["missingBlobs"], ["res://pct/x.pct"])
        self.assertFalse((self.root / "out.pak").exists())
        self.assertTrue((p.work / "build.json").is_file())

    def test_successful_build_is_normalized_and_repeatable(self):
        hashes = []
        for n in range(2):
            p = pak_build.plan(self.project, _mod(self.root), self.root / f"out{n}.pak", game_root=self.game)
            with mock.patch.object(quiet, "run", _fake_packer("Duplicate name: 'a'\n")):
                receipt = pak_build.build(p)
            self.assertTrue(receipt["ok"], receipt["failures"])
            self.assertEqual(receipt["log"]["duplicateNames"], 1)
            hashes.append(receipt["output"]["sha256"])
            saved = json.loads((p.work / "build.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["output"]["sha256"], receipt["output"]["sha256"])
            self.assertEqual((saved["candidate"], saved["packageSha256"], saved["accepted"]),
                             (f"out{n}", receipt["output"]["sha256"], False))
        self.assertEqual(hashes[0], hashes[1])

    def test_baseline_check_lists_changes_and_enforces_allowed_globs(self):
        p = pak_build.plan(self.project, _mod(self.root), self.root / "out.pak", game_root=self.game)
        with mock.patch.object(quiet, "run", _fake_packer("")):
            receipt = pak_build.build(p)
        installed = self.root / "installed.pak"
        with zipfile.ZipFile(installed, "w") as z:
            z.writestr("ssl/a.sso", b"patched in the package")
            z.writestr("demo.mod", b"title: Demo\n")
            z.writestr("pct/only_installed.pct", b"x")
        check = pak_build.baseline_check(receipt, p.work, installed)
        self.assertEqual(check["counts"], {"changed": 1, "removed": 1})
        self.assertTrue(receipt["ok"])
        pak_build.baseline_check(receipt, p.work, installed, ["ssl/*"])
        self.assertFalse(receipt["ok"])
        self.assertIn("outside --allow-change", receipt["failures"][-1])

    def test_nonzero_exit_and_no_output_fail(self):
        p = pak_build.plan(self.project, _mod(self.root), self.root / "out.pak", game_root=self.game)
        with mock.patch.object(quiet, "run", _fake_packer("", write=False, code=3)):
            receipt = pak_build.build(p)
        self.assertFalse(receipt["ok"])
        self.assertTrue(any("exit code 3" in f for f in receipt["failures"]))
        self.assertTrue(any("no package" in f for f in receipt["failures"]))

    def test_mod_file_wrapped_description(self):
        mod = self.root / "wrapped.mod"
        mod.write_text("title: K\ndescription: KGS-25 crane. Original model,\n  native tracks.\nscenes: []\n"
                       "assets:\n- ssl/a.sso.resource\n", encoding="utf-8")
        data = pak_build.read_mod_file(mod)
        self.assertEqual(data["description"], "KGS-25 crane. Original model, native tracks.")
        self.assertEqual(data["assets"], ["ssl/a.sso.resource"])

    def test_unstaged_autogen_classes_are_refused(self):
        (self.project / "mods_source" / "autogen_dw" / "trucks" / "auto_k").mkdir(parents=True)
        (self.project / "mods_source" / "autogen_dw" / "trucks" / "auto_k" / "auto_k.cls").write_text("x")
        mod = self.root / "autogen.mod"
        mod.write_text("title: K\nscenes: []\nassets:\n- autogen_dw/trucks/auto_k/auto_k.sso.resource\n",
                       encoding="utf-8")
        p = pak_build.plan(self.project, mod, self.root / "out.pak", game_root=self.game)
        self.assertTrue(any("not staged" in problem for problem in p.problems))
        staged = pak_build.plan(self.project, _mod(self.root), self.root / "out2.pak", game_root=self.game)
        self.assertEqual(staged.problems, [])

    def test_mod_file_flow_lists(self):
        mod = self.root / "flow.mod"
        mod.write_text("title: T\nscenes: []\nassets: [ssl/a.sso.resource, 'ssl/b.sso.resource']\n", encoding="utf-8")
        self.assertEqual(pak_build.read_mod_file(mod)["assets"], ["ssl/a.sso.resource", "ssl/b.sso.resource"])


if __name__ == "__main__":
    unittest.main()
