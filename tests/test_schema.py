"""Schema export (roadcraft.schema) and the editor-faithful PS reader it is built on.

The synthetic tests build a tiny SDK in a temporary folder.  The SDK-gated tests read the real meta descs of
the installed game (ROADCRAFT_GAME_ROOT or the Steam path) and are skipped, with the reason, when it is absent.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from roadcraft import ps_format, schema

META_DESC = """
iactor = {
   __family = ".cls"
   __type = "section"
   __members = {
      properties = { __type = "exclusiveCollection" __ptr = "prop_base" __family = ".prop" }
   }
}
prop_base = { __family = ".prop" __type = "section" }
tpl_markup = {
   __family = ".tpl_markup"
   __type = "section"
   __members = {
      version = { __type = "int" __defaultValue = 1 }
      materials = { __type = "collection" }
   }
}
"""
META_DESC_SSL = """
PropTruckWheel = {
   __type = "PropBase"
   __extraData = { __sslBrandName = "prop_truck_wheel" __sslBrandFamily = ".prop" }
   __members = {
      width = { __type = "float" __defaultValue = 1 __viewType = { __min = 0 __max = 5 __units = "m" __caption = "Tyre width" } }
      torqueType = { __type = "TorqueType" }
      deformEnable = { __type = "bool" __defaultValue = False }
   }
}
PropTruckWheelBig = {
   __type = "PropTruckWheel"
   __extraData = { __sslBrandName = "prop_truck_wheel_big" __sslBrandFamily = ".prop" }
   __defaultValue = { width = 2 }
   __members = { width = { __viewType = { __max = 9 } } }
}
PropBase = {
   __type = "section"
   __extraData = { __sslBrandName = "prop_base" __sslBrandFamily = ".prop" }
   __members = { enabled = { __type = "bool" __defaultValue = True } }
}
TorqueType = { __type = "enum" __items = [ "none", "defaults", "full" ] __defaultValue = "none" }
"""
META_DESC_BRO = """
TruckSettings = { __type = "section" __members = { useSuspensionCollection = { __type = "bool" __defaultValue = False } } }
"""
OVERRIDES = """
PropBase = { __members = { enabled = { __viewType = { __caption = "Enabled (override)" } } } }
"""


def make_sdk(root: Path) -> Path:
    meta = root / "root" / "prebuild" / "meta_descs"
    meta.mkdir(parents=True)
    (meta / "meta_desc.ps").write_text(META_DESC, encoding="utf-8")
    (meta / "meta_desc_ssl.ps").write_text(META_DESC_SSL, encoding="utf-8")
    (meta / "meta_desc_bro.ps").write_text(META_DESC_BRO, encoding="utf-8")
    editor = root / "tools" / "bin" / "ModEditor"
    editor.mkdir(parents=True)
    (editor / "meta_desc_ssl_overrides.ps").write_text(OVERRIDES, encoding="utf-8")
    return root


class EditorParserTests(unittest.TestCase):
    def test_quirks_match_the_editor(self) -> None:
        warnings = []
        doc = ps_format.editor_loads("a = [1e-05]\nb = .5\nc = .25\nd = No\ne = -.5\nf = 0.5\n",
                                     warn=lambda kind, line, detail: warnings.append((kind, line)))
        self.assertEqual(doc, {"a": [1, "e", -5], "b": 0.0, "c": 0.5, "d": False, "e": -0.5, "f": 0.5})
        self.assertEqual([w[0] for w in warnings],
                         ["number_followed_by_letters", "leading_dot_number", "leading_dot_number", "bare_bool_keyword"])
        self.assertEqual([w[1] for w in warnings], [1, 2, 3, 4])

    def test_exponent_outside_an_array_fails_with_its_line(self) -> None:
        with self.assertRaises(ps_format.EditorParseError) as caught:
            ps_format.editor_loads("x = 1\ny = 1e-05\n")
        self.assertEqual(caught.exception.line, 2)

    def test_duplicate_keys_and_brace_on_next_line_fail(self) -> None:
        for text in ("a = 1\na = 2\n", "a\n{\n}\n"):
            with self.assertRaises(ps_format.EditorParseError):
                ps_format.editor_loads(text)

    def test_sections_record_key_lines_and_keys_are_strings(self) -> None:
        doc = ps_format.editor_loads("// c\nx = {\n   2d = yes\n   name = \"No\"\n}\n")
        self.assertEqual(doc.lines["x"], 2)
        self.assertEqual(doc["x"].lines, {"2d": 3, "name": 4})
        self.assertEqual(doc["x"], {"2d": True, "name": "No"})


class YamlTests(unittest.TestCase):
    def test_descriptor_subset(self) -> None:
        text = ("__type: res_desc_mtl\nfile: a.mi\nlinks:\n- res://pct/a.pct.resource\n- 'b c'\nparents: []\n"
                "title: Long\n  folded text\ntypes:\n- name: t\n  refs:\n  - name: links\n    attrs:\n    - name: link\n"
                "      args: [texture, x]\n")
        doc = schema.yaml_loads(text)
        self.assertEqual(doc["links"], ["res://pct/a.pct.resource", "b c"])
        self.assertEqual(doc["parents"], [])
        self.assertEqual(doc["title"], "Long folded text")
        self.assertEqual(doc["types"][0]["refs"][0]["attrs"][0], {"name": "link", "args": ["texture", "x"]})


class SyntheticSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_sdk(Path(self.tmp.name))
        self.schema = schema.Schema(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_brand_registration_and_inherited_fields(self) -> None:
        self.assertEqual(self.schema.find("prop_truck_wheel", ".prop"), ".prop::prop_truck_wheel")
        info = self.schema.lookup("prop_truck_wheel_big", ".prop")
        self.assertEqual(info["chain"][:2], [".prop::prop_truck_wheel_big", ".prop::prop_truck_wheel"])
        width = info["fields"]["width"]
        self.assertEqual((width["default"], width["min"], width["max"], width["units"]), (2, 0, 9, "m"))
        self.assertEqual(width["default_from_type"], "prop_truck_wheel_big")
        self.assertEqual(info["fields"]["torqueType"]["enum_items"], ["none", "defaults", "full"])
        self.assertEqual(info["fields"]["torqueType"]["default"], "none")
        self.assertIn("enabled", info["fields"])                  # from the brand parent PropBase

    def test_overrides_are_merged(self) -> None:
        self.assertEqual(self.schema.field(".prop::prop_base", "enabled")["caption"], "Enabled (override)")

    def test_dump_is_deterministic_and_sorted(self) -> None:
        a, b = Path(self.tmp.name) / "a.json", Path(self.tmp.name) / "b.json"
        self.schema.dump(a)
        schema.Schema(self.root).dump(b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        doc = json.loads(a.read_text(encoding="utf-8"))
        self.assertEqual(list(doc), sorted(doc))
        self.assertEqual(doc["counts"]["types"], len(doc["types"]))
        self.assertNotIn("generated_utc", doc["meta"])

    def test_load_caches_in_process(self) -> None:
        self.assertIs(schema.load(self.root), schema.load(self.root))

    def test_show_and_search_cli(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = schema.main(["--game-root", str(self.root), "show", "prop_truck_wheel.width"])
        self.assertEqual(code, 0)
        shown = json.loads(out.getvalue())
        self.assertEqual(shown["default"], 1)
        self.assertIn("properties", shown["serialisedTo"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            schema.main(["--game-root", str(self.root), "search", "suspension"])
        self.assertEqual([r["key"] for r in json.loads(out.getvalue())], [".bro::TruckSettings.useSuspensionCollection"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(schema.main(["--game-root", str(self.root), "show", "nothing"]), 1)
            self.assertEqual(schema.main(["--game-root", str(Path(self.tmp.name) / "none"), "show", "x"]), 2)


@unittest.skipUnless(schema.sdk_present(), "RoadCraft SDK meta descs not installed (set ROADCRAFT_GAME_ROOT)")
class RealSdkSchemaTests(unittest.TestCase):
    """Counts of the research prototype C:/RC_RE/research/dump_schema.py on the 2026-10-13 SDK."""

    def test_counts_match_the_prototype(self) -> None:
        counts = schema.load().counts
        self.assertEqual(counts["types"], 24382)
        self.assertEqual(counts["fields_declared"], 27763)
        self.assertEqual(counts["fields_total"], 264406)
        self.assertEqual(counts["declared_with_default"], 12312)
        self.assertEqual(counts["declared_with_enum_items"], 745)
        self.assertEqual(counts.get("resource_desc_types"), 98)

    def test_known_vehicle_fields(self) -> None:
        s = schema.load()
        self.assertEqual(s.field(".ssl::TruckWheelSlot", "torqueType")["enum_items"],
                         ["none", "defaults", "connectable", "full"])
        self.assertEqual(s.field(".ssl::TruckWheelSlot", "deformingGeomName")["default"], "tire")
        self.assertIn("suspensionAxleCollection", s.member_names(".prop::prop_truck_rb"))


if __name__ == "__main__":
    unittest.main()
