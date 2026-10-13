import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from roadcraft import class_staging, pak_build, quiet

T = "autogen_dw/trucks/auto_t"
P = "autogen_dw/trucks/preview/auto_t"


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _project(root: Path) -> Path:
    """A miniature editor project: generated classes under autogen_dw/, a library and a prefab nobody links."""
    project = root / "my project"
    mods = project / "mods_source"
    folded = str(project).replace("\\", "/").replace(" ", "\n  ", 1)          # a YAML line fold inside the path
    _w(project / ".project", "references:\n- project: C:/Game/root/.project\ndocuments-dir: " + folded +
       "\nmods-dir: $(documents-dir)/mods_source\n")
    _w(project / "config" / "editor.cfg", "external:\n  ModsSourceLocal: " + str(project).replace("\\", "/") +
       "/mods_source\n")
    _w(mods / T / "auto_t.cls", 'truck = {\r\n   wheels = "auto_wheel_t_front"\r\n   tpl = "t"\r\n}\r\n')
    _w(mods / T / "auto_t.cls.resource", "__type: res_desc_cls\ncls: auto_t.cls\nlinksDesc:\n"
       f"- res://{T}/auto_wheel_t_front.cls.resource\nlinksTpl:\n- res://models/mods/t.tpl.asset/t.tpl.asset\n")
    _w(mods / T / "auto_wheel_t_front.cls", 'radius = 0.4\n')
    _w(mods / T / "auto_wheel_t_front.cls.resource", "__type: res_desc_cls\ncls: auto_wheel_t_front.cls\n")
    _w(mods / T / "auto_t_replicated.sso", 'actor = "auto_t"\n__type = "ReplicatedEntity"\n')
    _w(mods / T / "auto_t_replicated.sso.resource", "brandName: AutoTReplicated\nlinksDesc:\n"
       f"- res://{T}/auto_t.cls.resource\nsso: auto_t_replicated.sso\n")
    _w(mods / T / "auto_t_truck_info.sso", 'info = { __type = "AutoTReplicated" }\nwheels = ["auto_wheel_t_front"]\n')
    _w(mods / T / "auto_t_truck_info.sso.resource", "brandName: AutoTTruckInfo\nlinksDesc:\n"
       f"- res://{T}/auto_t_replicated.sso.resource\n- res://ssl/game/truck/truck_details_info.sso.resource\n"
       "sso: auto_t_truck_info.sso\n")
    _w(mods / P / "auto_preview_t.cls", "preview = 1\n")
    _w(mods / P / "auto_preview_t.cls.resource", "cls: auto_preview_t.cls\n")
    _w(mods / P / "auto_preview_t_truck_preview_info.sso", 'truck = "auto_preview_t"\n')
    _w(mods / P / "auto_preview_t_truck_preview_info.sso.resource", "brandName: AutoPreviewTTruckPreviewInfo\n"
       f"linksDesc:\n- res://{P}/auto_preview_t.cls.resource\nsso: auto_preview_t_truck_preview_info.sso\n")
    _w(mods / T / "t_prefab.prefab", "prefab = 1\n")
    _w(mods / T / "t_prefab.prefab.resource", "prefab: t_prefab.prefab\n")
    _w(mods / "autogen_dw/trucks/auto_truck_library.sso", 'trucks = ["auto_t"]\n')
    _w(mods / "autogen_dw/trucks/auto_truck_library.sso.resource",
       f"links:\n- res://{T}/t_prefab.prefab.resource\nsso: auto_truck_library.sso\n")
    _w(mods / "models/mods/t.tpl.asset/t.tpl.asset", "tpl\n")
    _w(mods / "models/mods/t.tpl.asset/t.tpl_markup", "materialName = \"mod_t_body\"\n")
    (mods / "models/mods/t.blend").write_bytes(b"BLENDER binary")
    _w(mods / "mods/t.mod", "title: T\ndescription: test\nscenes: []\nassets:\n"
       f"- {T}/auto_t_replicated.sso.resource\n- {T}/auto_t_truck_info.sso.resource\n"
       f"- {P}/auto_preview_t_truck_preview_info.sso.resource\n")
    return project


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class ClassNameTest(unittest.TestCase):
    def test_editor_rule(self):
        self.assertEqual(class_staging.class_name("auto_kgs25_truck_info"), "AutoKgs25TruckInfo")
        self.assertEqual(class_staging.class_name("auto_kgs25_truck_info_kgs25"), "AutoKgs25TruckInfoKgs25")
        self.assertEqual(class_staging.class_name("auto_goli_d11_v3_replicated_gd11"), "AutoGoliD11V3ReplicatedGd11")
        self.assertEqual(class_staging.class_name("auto_r105_2_x"), "AutoR105_2X")   # digits meeting keep "_"
        self.assertEqual(class_staging.class_name("AUTO_ABC"), "AutoAbc")


class StageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = _project(self.root)
        self.mod = self.project / "mods_source/mods/t.mod"

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, name="staged", **kw):
        kw.setdefault("mod_file", self.mod)
        return class_staging.stage(self.project, self.root / name, "tt", **kw)

    def test_dry_run_writes_nothing_and_plans_the_renames(self):
        before = _tree(self.project)
        report = self.stage(dry_run=True)
        self.assertEqual(report["problems"], [])
        self.assertFalse((self.root / "staged").exists())
        self.assertEqual(_tree(self.project), before)
        moved = {r["from"]: r["to"] for r in report["renames"]}
        self.assertEqual(moved[f"{T}/auto_t.cls"], "ssl/auto_t_tt.cls")
        self.assertEqual(moved[f"{P}/auto_preview_t_truck_preview_info.sso.resource"],
                         "ssl/auto_preview_t_truck_preview_info_tt.sso.resource")
        self.assertEqual(len(moved), 12)                     # 6 reachable brands + their .resource files
        self.assertEqual(sorted(n["file"] for n in report["notStaged"]),
                         ["autogen_dw/trucks/auto_t/t_prefab.prefab", "autogen_dw/trucks/auto_truck_library.sso"])
        self.assertEqual(report["identifiers"]["AutoTTruckInfo"], "AutoTTruckInfoTt")
        self.assertNotIn("AutoT", report["identifiers"])     # .cls brands keep their class name (editor: .sso only)
        self.assertEqual(report["roots"][0], "res://ssl/auto_t_replicated_tt.sso.resource")

    def test_stage_rewrites_every_reference_and_keeps_the_source(self):
        before = _tree(self.project)
        report = self.stage()
        self.assertEqual((report["problems"], report["unmapped"]), ([], []))
        self.assertEqual(_tree(self.project), before)        # the source project is never written
        mods = self.root / "staged/mods_source"
        self.assertFalse((mods / T / "auto_t.cls").exists())
        self.assertEqual((mods / "ssl/auto_t_tt.cls").read_bytes(),
                         b'truck = {\r\n   wheels = "auto_wheel_t_front_tt"\r\n   tpl = "t"\r\n}\r\n')   # CRLF kept
        self.assertEqual((mods / "ssl/auto_t_truck_info_tt.sso.resource").read_text(),
                         "brandName: AutoTTruckInfoTt\nlinksDesc:\n- res://ssl/auto_t_replicated_tt.sso.resource\n"
                         "- res://ssl/game/truck/truck_details_info.sso.resource\nsso: auto_t_truck_info_tt.sso\n")
        self.assertEqual((mods / "ssl/auto_t_truck_info_tt.sso").read_text(),
                         'info = { __type = "AutoTReplicatedTt" }\nwheels = ["auto_wheel_t_front_tt"]\n')
        self.assertIn("- ssl/auto_t_truck_info_tt.sso.resource\n", (mods / "mods/t.mod").read_text())
        # the library still links the prefab through its unchanged folder named like a brand
        library = (mods / "autogen_dw/trucks/auto_truck_library.sso.resource").read_text()
        self.assertIn(f"res://{T}/t_prefab.prefab.resource", library)
        self.assertTrue((mods / T / "t_prefab.prefab").is_file())
        self.assertFalse((mods / "models/mods/t.blend").exists())
        self.assertEqual(report["skipped"], ["mods_source/models/mods/t.blend"])
        # the staged .project and cfg point at the copy, the fold included
        staged = str((self.root / "staged").resolve()).replace("\\", "/")
        self.assertIn("documents-dir: " + staged + "\n", (self.root / "staged/.project").read_text())
        self.assertIn(staged + "/mods_source", (self.root / "staged/config/editor.cfg").read_text())
        counts = {r["file"]: (r["paths"], r["identifiers"]) for r in report["rewritten"]}
        self.assertEqual(counts["mods_source/ssl/auto_t_truck_info_tt.sso.resource"], (1, 2))
        self.assertEqual(counts["mods_source/mods/t.mod"], (3, 0))

    def test_deterministic(self):
        self.stage("a")
        self.stage("b")
        # identical apart from the project files, which name their own staging folder
        self.assertEqual(_tree(self.root / "a/mods_source"), _tree(self.root / "b/mods_source"))
        self.assertEqual((self.root / "a/.project").read_text().replace(str((self.root / "a").resolve())
                                                                        .replace("\\", "/"), "<out>"),
                         (self.root / "b/.project").read_text().replace(str((self.root / "b").resolve())
                                                                        .replace("\\", "/"), "<out>"))
        a = self.stage("c", dry_run=True)
        b = self.stage("c", dry_run=True)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_refusals(self):
        (self.root / "busy").mkdir()
        (self.root / "busy/x").write_text("x")
        self.assertTrue(any("not empty" in p for p in self.stage("busy")["problems"]))
        self.assertTrue(any("suffix" in p for p in class_staging.stage(self.project, self.root / "s", "Bad-Suffix",
                                                                        mod_file=self.mod)["problems"]))
        inside = class_staging.stage(self.project, self.project / "staged", "tt", mod_file=self.mod)
        self.assertTrue(any("inside the project" in p for p in inside["problems"]))
        _w(self.project / "mods_source/ssl/auto_t_tt.cls", "taken\n")
        self.assertTrue(any("already exists" in p for p in self.stage(dry_run=True)["problems"]))

    def test_duplicate_brand_names_are_refused(self):
        other = self.project / "mods_source/autogen_dw/trucks/other"
        _w(other / "auto_t.cls", "x\n")
        _w(other / "auto_t.cls.resource", "cls: auto_t.cls\n")
        _w(self.project / "mods_source" / T / "auto_t_replicated.sso.resource",
           f"linksDesc:\n- res://{T}/auto_t.cls.resource\n- res://autogen_dw/trucks/other/auto_t.cls.resource\n")
        self.assertTrue(any("two generated brands" in p for p in self.stage(dry_run=True)["problems"]))

    def test_missing_generated_link_is_unmapped(self):
        _w(self.project / "mods_source" / T / "auto_t.cls.resource",
           f"linksDesc:\n- res://{T}/auto_wheel_t_rear.cls.resource\n")
        report = self.stage(dry_run=True)
        self.assertTrue(any(u["link"].endswith("auto_wheel_t_rear.cls.resource") for u in report["unmapped"]))

    def test_explicit_roots_and_external_mod(self):
        external = self.root / "t_release.mod"
        external.write_text(self.mod.read_text())
        report = class_staging.stage(self.project, self.root / "x", "tt", mod_file=external)
        self.assertEqual(report["unmapped"], [])
        self.assertEqual(Path(report["modFile"]["staged"]), (self.root / "x" / "t_release.mod").resolve())
        roots = class_staging.stage(self.project, self.root / "y", "tt", roots=[f"res://{T}/auto_t.cls.resource"],
                                    dry_run=True)
        self.assertEqual(roots["roots"], ["res://ssl/auto_t_tt.cls.resource"])
        self.assertEqual(len(roots["renames"]), 4)           # the main class and its wheel


def _game(root: Path) -> Path:
    packer = root / pak_build.PACKER
    packer.parent.mkdir(parents=True)
    packer.write_bytes(b"fake packer")
    return root


class PakBuildStagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = _game(self.root / "game")
        self.project = _project(self.root)
        self.mod = self.project / "mods_source/mods/t.mod"

    def tearDown(self):
        self.tmp.cleanup()

    def test_unstaged_project_is_still_refused_without_a_suffix(self):
        p = pak_build.plan(self.project, self.mod, self.root / "out.pak", game_root=self.game)
        self.assertTrue(any("--stage-classes --suffix" in problem for problem in p.problems))
        p = pak_build.plan(self.project, self.mod, self.root / "out.pak", game_root=self.game, stage_classes=True)
        self.assertTrue(any("needs --suffix" in problem for problem in p.problems))

    def test_build_stages_into_work_and_packs_from_there(self):
        p = pak_build.plan(self.project, self.mod, self.root / "out.pak", game_root=self.game,
                           stage_classes=True, suffix="tt")
        self.assertEqual(p.problems, [])
        self.assertEqual(p.roots[1], "res://ssl/auto_t_truck_info_tt.sso.resource")
        self.assertFalse((p.work / "staged").exists())       # preflight plans only
        seen = {}

        def run(argv, *, log=None, **_):
            seen["argv"] = argv
            with zipfile.ZipFile(argv[argv.index("--output") + 1], "w") as z:
                z.writestr("ssl/auto_t_tt.cls", b"x")
            log.write(b"ok\n")
            return quiet.QuietResult(0, None, None, False, "test", 1, [], [], [], 0.1)

        with mock.patch.object(quiet, "run", run):
            receipt = pak_build.build(p)
        self.assertTrue(receipt["ok"], receipt["failures"])
        staged = (p.work / "staged").resolve()
        argv = seen["argv"]
        self.assertEqual(Path(argv[argv.index("--project") + 1]), staged)
        self.assertEqual(Path(argv[argv.index("--mod_file") + 1]), staged / "mods_source/mods/t.mod")
        self.assertEqual(receipt["staging"]["suffix"], "tt")
        self.assertEqual(len(receipt["staging"]["renames"]), 12)
        self.assertEqual(receipt["inputs"]["sourceProject"], str(self.project.resolve()))
        self.assertTrue((p.work / "staging.json").is_file())
        roots = (p.work / "roots.txt").read_text().splitlines()
        self.assertTrue(all(r.startswith("res://ssl/") for r in roots))


if __name__ == "__main__":
    unittest.main()
