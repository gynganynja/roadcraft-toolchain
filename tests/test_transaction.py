"""Synthetic package installation, rollback, and interruption tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import transaction as tx  # noqa: E402


class PackageTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="roadcraft-transaction-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.accepted = self._write("archives/accepted.pak", b"accepted-package")
        self.candidate = self._write("archives/candidate.pak", b"candidate-package")
        self.installed = self._write("game/mods/d11.pak", b"previous-test-package")
        self.state = self.root / "local/transactions"
        self.expected = tx._sha(self.installed)
        self.accepted_pin = {"path": self.accepted, "sha256": tx._sha(self.accepted)}
        self.candidate_pin = {"path": self.candidate, "sha256": tx._sha(self.candidate)}
        self.clear = lambda: []

    def _write(self, relative: str, data: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _install(self, *, dry_run: bool = False) -> dict:
        return tx.install_package(
            self.accepted_pin, self.candidate_pin, self.installed, self.state,
            self.expected, self.clear, dry_run=dry_run
        )

    def test_dry_run_verifies_all_inputs_without_mutation(self) -> None:
        before = self.installed.read_bytes()
        result = self._install(dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["previousSha256"], self.expected)
        self.assertEqual(self.installed.read_bytes(), before)
        self.assertFalse(self.state.exists())
        self.assertEqual(self.candidate.read_bytes(), b"candidate-package")
        self.assertEqual(self.accepted.read_bytes(), b"accepted-package")

    def test_install_and_exact_rollback_preserve_archives_and_backup(self) -> None:
        result = self._install()
        self.assertEqual(result["state"], "INSTALLED")
        self.assertEqual(self.installed.read_bytes(), b"candidate-package")
        receipt_path = Path(result["receiptPath"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        backup = Path(receipt["backupPath"])
        self.assertEqual(backup.read_bytes(), b"previous-test-package")
        self.assertEqual(receipt["previousSha256"], self.expected)
        self.assertEqual(receipt["acceptedSha256"], tx._sha(self.accepted))
        self.assertFalse((self.state / "package.lock").exists())

        preview = tx.rollback_package(receipt_path, self.clear)
        self.assertTrue(preview["dryRun"])
        self.assertEqual(self.installed.read_bytes(), b"candidate-package")
        rolled = tx.rollback_package(receipt_path, self.clear, dry_run=False)
        self.assertEqual(rolled["state"], "ROLLED_BACK")
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")
        self.assertEqual(backup.read_bytes(), b"previous-test-package")
        self.assertEqual(self.candidate.read_bytes(), b"candidate-package")
        self.assertEqual(self.accepted.read_bytes(), b"accepted-package")

    def test_unknown_installed_hash_and_active_process_block_install(self) -> None:
        with self.assertRaisesRegex(tx.RecoveryRequiredError, "unexpected hash"):
            tx.install_package(self.accepted_pin, self.candidate_pin,
                               self.installed, self.state, "0" * 64, self.clear,
                               dry_run=False)
        with self.assertRaisesRegex(tx.TransactionBusyError, "active"):
            tx.install_package(self.accepted_pin, self.candidate_pin,
                               self.installed, self.state, self.expected,
                               lambda: ["RoadCraft.exe"], dry_run=False)
        self.assertFalse(self.state.exists())
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")

    def test_changed_candidate_pin_blocks_install(self) -> None:
        self.candidate.write_bytes(b"changed")
        with self.assertRaisesRegex(tx.PackageTransactionError, "hash differs"):
            self._install()
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")

    def test_interrupted_install_before_swap_is_marked_safe_on_recovery(self) -> None:
        original_replace = tx.os.replace

        def fail_swap(source: str | Path, destination: str | Path) -> None:
            if Path(destination) == self.installed:
                raise OSError("synthetic swap interruption")
            original_replace(source, destination)

        with mock.patch.object(tx.os, "replace", side_effect=fail_swap):
            with self.assertRaisesRegex(OSError, "swap interruption"):
                self._install()
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")
        receipts = list(self.state.glob("*/receipt.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())["state"], "SWAP_READY")
        preview = tx.recover_package(receipts[0], self.clear)
        self.assertEqual(preview["action"], "mark-not-installed")
        result = tx.recover_package(receipts[0], self.clear, dry_run=False)
        self.assertEqual(result["state"], "NOT_INSTALLED")
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")

    def test_interrupted_install_after_swap_restores_previous_bytes(self) -> None:
        original_advance = tx._advance

        def fail_final_receipt(path: Path, data: dict, state: str, detail: str) -> None:
            if state == "INSTALLED":
                raise OSError("synthetic receipt interruption")
            original_advance(path, data, state, detail)

        with mock.patch.object(tx, "_advance", side_effect=fail_final_receipt):
            with self.assertRaisesRegex(OSError, "receipt interruption"):
                self._install()
        self.assertEqual(self.installed.read_bytes(), b"candidate-package")
        receipt = next(self.state.glob("*/receipt.json"))
        self.assertEqual(tx.recover_package(receipt, self.clear)["action"],
                         "restore-previous")
        result = tx.recover_package(receipt, self.clear, dry_run=False)
        self.assertEqual(result["state"], "ROLLED_BACK")
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")

    def test_interrupted_rollback_can_be_resumed_with_new_staging_file(self) -> None:
        installed = self._install()
        receipt = Path(installed["receiptPath"])
        original_replace = tx.os.replace

        def fail_rollback(source: str | Path, destination: str | Path) -> None:
            if (Path(destination) == self.installed and
                    ".rollback-" in Path(source).name):
                raise OSError("synthetic rollback interruption")
            original_replace(source, destination)

        with mock.patch.object(tx.os, "replace", side_effect=fail_rollback):
            with self.assertRaisesRegex(OSError, "rollback interruption"):
                tx.rollback_package(receipt, self.clear, dry_run=False)
        self.assertEqual(json.loads(receipt.read_text())["state"], "ROLLBACK_READY")
        self.assertEqual(self.installed.read_bytes(), b"candidate-package")
        result = tx.recover_package(receipt, self.clear, dry_run=False)
        self.assertEqual(result["state"], "ROLLED_BACK")
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")

    def test_rollback_rejects_unknown_live_bytes_and_corrupt_backup(self) -> None:
        installed = self._install()
        receipt = Path(installed["receiptPath"])
        self.installed.write_bytes(b"unknown package")
        with self.assertRaisesRegex(tx.RecoveryRequiredError, "unknown or corrupted"):
            tx.rollback_package(receipt, self.clear, dry_run=False)
        with self.assertRaisesRegex(tx.RecoveryRequiredError, "unknown hash"):
            tx.recover_package(receipt, self.clear, dry_run=False)
        self.installed.write_bytes(b"candidate-package")
        backup = Path(json.loads(receipt.read_text())["backupPath"])
        backup.write_bytes(b"corrupted backup")
        with self.assertRaisesRegex(tx.RecoveryRequiredError, "unknown or corrupted"):
            tx.rollback_package(receipt, self.clear, dry_run=False)
        self.assertEqual(self.installed.read_bytes(), b"candidate-package")

    def test_orphaned_lock_is_archived_only_after_owner_check(self) -> None:
        self.state.mkdir(parents=True)
        lock = self.state / "package.lock"
        lock.write_text(json.dumps({"transactionId": "a" * 32,
                                    "installedPath": str(self.installed.resolve()),
                                    "pid": 12345}), encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionBusyError, "still active"):
            tx.archive_orphaned_lock(self.state, self.installed, self.clear,
                                     lambda _: True, dry_run=False)
        preview = tx.archive_orphaned_lock(self.state, self.installed, self.clear,
                                           lambda _: False)
        self.assertTrue(preview["dryRun"])
        self.assertTrue(lock.exists())
        archived = tx.archive_orphaned_lock(self.state, self.installed, self.clear,
                                            lambda _: False, dry_run=False)
        self.assertFalse(lock.exists())
        self.assertTrue(Path(archived["archivedPath"]).is_file())
        self.assertEqual(self.installed.read_bytes(), b"previous-test-package")


if __name__ == "__main__":
    unittest.main()
