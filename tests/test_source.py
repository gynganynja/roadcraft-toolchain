"""Synthetic coverage for D11 source identity and authoring gates."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft.source import (  # noqa: E402
    ExportBlockedError,
    SourceError,
    capture_source_inventory,
    compare_source_baselines,
    require_export_allowed,
    validate_usf_no_edit_roundtrip,
)


def declared_assets() -> list[dict]:
    return [
        {"asset": "cat_d11t", "exportMethod": "repaired-usf", "files": [
            {"path": "models/cat_d11t/export.usf", "role": "build-usf"},
            {"path": "models/cat_d11t/export_options.ps", "role": "export-options"},
            {"path": "authoring/cat_d11t.blend", "role": "blend-reference"},
        ]},
        {"asset": "cat_d11t_v2", "exportMethod": "repaired-usf", "files": [
            {"path": "models/cat_d11t_v2/export.usf", "role": "build-usf"},
        ]},
    ]


def source_tree(root: Path) -> None:
    contents = {
        "models/cat_d11t/export.usf": b"repaired base source\x00",
        "models/cat_d11t/export_options.ps": b"weld_vtx=false\n",
        "authoring/cat_d11t.blend": b"old authored reference",
        "models/cat_d11t_v2/export.usf": b"repaired v2 source\x00",
    }
    for relative, data in contents.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def approved_receipt(inventory: dict) -> dict:
    first = inventory["assets"][0]
    return {
        "schemaVersion": 1,
        "status": "APPROVED",
        "asset": "cat_d11t",
        "sourceAssetDigest": first["assetDigest"],
        "baselineUsfSha256": first["files"][0]["sha256"],
        "reviewer": "D11 source parity review",
        "checks": {
            name: True for name in (
                "hierarchy", "transforms", "geometry", "normalsTangents",
                "uvColors", "materials", "skinning", "bindMatrices", "lods",
                "metadata", "animation", "compilation", "nativeViews"
            )
        },
    }


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="roadcraft-test-source-")
        self.addCleanup(self.temporary.cleanup)
        # Match the canonical paths returned by the source functions on Windows.
        self.root = Path(self.temporary.name).resolve()

    def test_inventory_preserves_order_and_survives_relocation(self) -> None:
        first_root = self.root / "first"
        second_root = self.root / "second"
        first_root.mkdir()
        source_tree(first_root)
        shutil.copytree(first_root, second_root)
        first = capture_source_inventory(first_root, declared_assets())
        second = capture_source_inventory(second_root, declared_assets())
        self.assertEqual([asset["asset"] for asset in first["assets"]],
                         ["cat_d11t", "cat_d11t_v2"])
        self.assertEqual([row["role"] for row in first["assets"][0]["files"]],
                         ["build-usf", "export-options", "blend-reference"])
        self.assertNotEqual(first["sourceRoot"], second["sourceRoot"])
        self.assertEqual(first["manifestDigest"], second["manifestDigest"])
        self.assertTrue(compare_source_baselines(first, second)["matches"])

    def test_source_change_and_file_order_are_visible(self) -> None:
        source_tree(self.root)
        before = capture_source_inventory(self.root, declared_assets())
        (self.root / "models/cat_d11t/export.usf").write_bytes(b"modified source")
        after = capture_source_inventory(self.root, declared_assets())
        changes = compare_source_baselines(before, after)["changes"]
        self.assertTrue(any(row["kind"] == "file-sha256" and row["asset"] == "cat_d11t"
                            for row in changes))
        with self.assertRaisesRegex(ExportBlockedError, "changed"):
            require_export_allowed(self.root, before, "cat_d11t", "repaired-usf")

        reordered = declared_assets()
        reordered[0]["files"].reverse()
        result = compare_source_baselines(after,
                                          capture_source_inventory(self.root, reordered))
        self.assertTrue(any(row["kind"] == "file-order" for row in result["changes"]))

    def test_inventory_rejects_paths_outside_tree(self) -> None:
        source_tree(self.root)
        for bad in ("../outside.usf", "C:\\outside.usf", "/outside.usf",
                    "models/./cat_d11t/export.usf"):
            with self.subTest(path=bad):
                declarations = declared_assets()
                declarations[0]["files"][0]["path"] = bad
                with self.assertRaises(SourceError):
                    capture_source_inventory(self.root, declarations)

    def test_inventory_rejects_linked_input(self) -> None:
        source = self.root / "actual.usf"
        source.write_bytes(b"outside")
        root = self.root / "root"
        root.mkdir()
        try:
            (root / "linked.usf").symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this host")
        declaration = [{"asset": "linked", "exportMethod": "repaired-usf",
                        "files": [{"path": "linked.usf", "role": "build-usf"}]}]
        with self.assertRaisesRegex(SourceError, "link or reparse"):
            capture_source_inventory(root, declaration)

    def test_native_blender_requires_complete_current_receipt(self) -> None:
        source_tree(self.root)
        inventory = capture_source_inventory(self.root, declared_assets())
        require_export_allowed(self.root, inventory, "cat_d11t", "repaired-usf")
        with self.assertRaisesRegex(ExportBlockedError, "parity receipt"):
            require_export_allowed(self.root, inventory, "cat_d11t", "native-blend")
        approved = approved_receipt(inventory)
        incomplete = {**approved, "checks": {**approved["checks"], "animation": False}}
        with self.assertRaisesRegex(ExportBlockedError, "parity receipt"):
            require_export_allowed(self.root, inventory, "cat_d11t", "native-blend",
                                   incomplete)
        stale = {**approved, "baselineUsfSha256": "0" * 64}
        with self.assertRaisesRegex(ExportBlockedError, "parity receipt"):
            require_export_allowed(self.root, inventory, "cat_d11t", "native-blend",
                                   stale)
        require_export_allowed(self.root, inventory, "cat_d11t", "native-blend", approved)

        (self.root / "authoring/cat_d11t.blend").write_bytes(b"new authored candidate")
        fresh = capture_source_inventory(self.root, declared_assets())
        with self.assertRaisesRegex(ExportBlockedError, "parity receipt"):
            require_export_allowed(self.root, fresh, "cat_d11t", "native-blend",
                                   approved)

    def test_inventory_digest_tampering_is_rejected(self) -> None:
        source_tree(self.root)
        inventory = capture_source_inventory(self.root, declared_assets())
        inventory["assets"][0]["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(SourceError, "digest"):
            compare_source_baselines(inventory, inventory)

    def test_no_edit_roundtrip_uses_scratch_and_reports_byte_parity(self) -> None:
        source = self.root / "export.usf"
        source.write_bytes(b"USF\x00payload")
        scratch = self.root / "scratch"
        scratch.mkdir()
        destinations: list[Path] = []

        def copy_writer(src: Path, dst: Path) -> None:
            destinations.append(dst)
            dst.write_bytes(src.read_bytes())

        equal = validate_usf_no_edit_roundtrip(source, copy_writer, scratch)
        self.assertTrue(equal["byteIdentical"])
        self.assertTrue(destinations[0].is_relative_to(scratch))
        self.assertFalse(destinations[0].exists())
        self.assertEqual(source.read_bytes(), b"USF\x00payload")

        def changing_writer(src: Path, dst: Path) -> None:
            dst.write_bytes(src.read_bytes() + b"normalized")

        changed = validate_usf_no_edit_roundtrip(source, changing_writer, scratch)
        self.assertFalse(changed["byteIdentical"])
        self.assertEqual(source.read_bytes(), b"USF\x00payload")

    def test_roundtrip_detects_source_mutation(self) -> None:
        source = self.root / "export.usf"
        source.write_bytes(b"original")
        scratch = self.root / "scratch"
        scratch.mkdir()

        def bad_writer(src: Path, dst: Path) -> None:
            src.write_bytes(b"mutated")
            dst.write_bytes(b"mutated")

        with self.assertRaisesRegex(SourceError, "source changed"):
            validate_usf_no_edit_roundtrip(source, bad_writer, scratch)


if __name__ == "__main__":
    unittest.main()
