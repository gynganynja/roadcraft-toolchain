"""Synthetic accepted-source migration and recovery checks."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import migrate  # noqa: E402


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="roadcraft-migrate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.files = {".project": b"project config",
                      "config/editor.cfg": b"editor config",
                      "mods_source/d11/export.usf": b"synthetic usf"}
        for relative, data in self.files.items():
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.manifest = self.root / "manifest.json"
        self._write_manifest()
        self.destination = self.root / "checkout/assets"
        self.receipt = self.root / "checkout/migration.json"

    def _write_manifest(self, *, reversed_order: bool = False) -> None:
        items = list(self.files.items())
        if reversed_order:
            items.reverse()
        manifest = {"schemaVersion": 1, "sourceRoot": str(self.source.resolve()),
                    "files": [{"path": path, "bytes": len(data),
                               "sha256": migrate._sha(self.source / path)}
                              for path, data in items]}
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest_sha = migrate._sha(self.manifest)

    def _run(self, *, dry_run: bool = True, minimum_free_bytes: int = 0) -> dict:
        return migrate.migrate_source_tree(
            self.manifest, self.manifest_sha, self.source,
            self.destination, self.receipt,
            minimum_free_bytes=minimum_free_bytes, dry_run=dry_run,
        )

    def test_default_space_reserve_blocks_real_copy_when_below_gate(self) -> None:
        with mock.patch.object(migrate, "_free_bytes", return_value=29 * migrate.GIB):
            preview = migrate.migrate_source_tree(
                self.manifest, self.manifest_sha, self.source,
                self.destination, self.receipt
            )
            self.assertFalse(preview["spaceGatePassed"])
            self.assertEqual(preview["minimumFreeBytes"], 30 * migrate.GIB)
            with self.assertRaises(migrate.InsufficientSpaceError):
                migrate.migrate_source_tree(
                    self.manifest, self.manifest_sha, self.source,
                    self.destination, self.receipt, dry_run=False
                )
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.receipt.exists())

    def test_dry_run_verifies_manifest_without_writing(self) -> None:
        preview = self._run()
        self.assertEqual(preview["expectedFiles"], 3)
        self.assertEqual(preview["filesRemaining"], 3)
        self.assertTrue(preview["spaceGatePassed"])
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.receipt.exists())

    def test_copy_is_independent_and_receipt_is_complete(self) -> None:
        result = self._run(dry_run=False)
        self.assertEqual(result["status"], "COMPLETE")
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(receipt["manifestSha256"], self.manifest_sha)
        self.assertEqual(receipt["verifiedFiles"], 3)
        self.assertEqual(receipt["verifiedBytes"], sum(map(len, self.files.values())))
        for relative, data in self.files.items():
            copied = self.destination / relative
            original = self.source / relative
            self.assertEqual(copied.read_bytes(), data)
            self.assertNotEqual((copied.stat().st_dev, copied.stat().st_ino),
                                (original.stat().st_dev, original.stat().st_ino))
        (self.destination / ".project").write_bytes(b"changed destination")
        self.assertEqual((self.source / ".project").read_bytes(), b"project config")

    def test_resume_after_interruption_verifies_and_skips_existing_copy(self) -> None:
        original_copy = migrate._copy_one
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic interruption")
            original_copy(*args, **kwargs)

        with mock.patch.object(migrate, "_copy_one", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "synthetic interruption"):
                self._run(dry_run=False)
        partial = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(partial["status"], "COPYING")
        self.assertEqual(partial["verifiedFiles"], 1)
        first = self.destination / ".project"
        first_stat = first.stat()
        preview = self._run()
        self.assertTrue(preview["resuming"])
        self.assertEqual(preview["verifiedExistingFiles"], 1)
        self.assertEqual(preview["filesRemaining"], 2)
        done = self._run(dry_run=False)
        self.assertEqual(done["status"], "COMPLETE")
        self.assertEqual((first.stat().st_dev, first.stat().st_ino),
                         (first_stat.st_dev, first_stat.st_ino))
        self.assertEqual(json.loads(self.receipt.read_text())["verifiedFiles"], 3)

    def test_nonempty_destination_without_matching_receipt_is_refused(self) -> None:
        self.destination.mkdir(parents=True)
        (self.destination / ".project").write_bytes(b"project config")
        with self.assertRaisesRegex(migrate.MigrationError, "needs a matching"):
            self._run()
        self.assertFalse(self.receipt.exists())

    def test_existing_directory_without_receipt_is_not_treated_as_empty(self) -> None:
        (self.destination / "config").mkdir(parents=True)
        with self.assertRaisesRegex(migrate.MigrationError, "needs a matching"):
            self._run()
        self.assertFalse(self.receipt.exists())

    def test_resumption_with_different_manifest_is_refused(self) -> None:
        self._run(dry_run=False)
        self._write_manifest(reversed_order=True)
        with self.assertRaisesRegex(migrate.MigrationError, "another source or manifest"):
            self._run()

    def test_changed_source_and_bad_manifest_pin_are_refused(self) -> None:
        with self.assertRaisesRegex(migrate.MigrationError, "differs from its pin"):
            migrate.migrate_source_tree(self.manifest, "0" * 64, self.source,
                                        self.destination, self.receipt)
        (self.source / ".project").write_bytes(b"altered")
        with self.assertRaisesRegex(migrate.MigrationError, "differs from pinned manifest"):
            self._run()
        self.assertFalse(self.destination.exists())

    def test_extra_destination_file_is_refused_on_resume(self) -> None:
        self._run(dry_run=False)
        (self.destination / "extra.bin").write_bytes(b"unlisted")
        with self.assertRaisesRegex(migrate.MigrationError, "unmanifested"):
            self._run()

    def test_second_applied_migration_cannot_acquire_same_lock(self) -> None:
        self.receipt.parent.mkdir(parents=True)
        with migrate._migration_lock(self.receipt):
            with self.assertRaisesRegex(migrate.MigrationError, "already active"):
                self._run(dry_run=False)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.receipt.exists())

    def test_symlink_source_is_refused(self) -> None:
        link = self.source / "config/editor.cfg"
        link.unlink()
        try:
            link.symlink_to(self.source / ".project")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this host")
        with self.assertRaisesRegex(migrate.MigrationError, "symlink or reparse"):
            self._run()


if __name__ == "__main__":
    unittest.main()
