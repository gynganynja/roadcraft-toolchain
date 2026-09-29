from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from roadcraft import cli, core, transaction as tx


class NewModTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.candidate = self.root / "candidate.pak"
        self.candidate.write_bytes(b"candidate mod")
        self.pin = {"path": str(self.candidate), "sha256": core.sha256_file(self.candidate)}
        (self.root / "mods").mkdir()
        self.target = self.root / "mods/trail_mod.pak"
        self.state = self.root / "local/transactions"

    def install(self, dry_run=False):
        return tx.install_package(None, self.pin, self.target, self.state, None,
                                  lambda: [], dry_run=dry_run, expect_absent=True)

    def test_first_install_dry_run_install_rollback_and_status_keep_acceptance_empty(self):
        preview = self.install(dry_run=True)
        self.assertTrue(preview["previousAbsent"])
        self.assertFalse(self.target.exists())
        self.assertFalse(self.state.exists())
        result = self.install()
        receipt = Path(result["receiptPath"])
        saved = json.loads(receipt.read_text())
        self.assertIsNone(saved["acceptedSha256"])
        self.assertIsNone(saved["previousSha256"])
        self.assertEqual(saved["schemaVersion"], 2)
        self.assertEqual(self.target.read_bytes(), b"candidate mod")
        self.assertFalse(Path(saved["backupPath"]).exists())
        tx.rollback_package(receipt, lambda: [], dry_run=True)
        self.assertTrue(self.target.exists())
        tx.rollback_package(receipt, lambda: [], dry_run=False)
        self.assertFalse(self.target.exists())
        self.assertEqual(tx.rollback_package(receipt, lambda: [], dry_run=False)["state"], "ROLLED_BACK")
        state = core.status({"project": "trail", "accepted": {}, "candidates": {}},
                            {"installedPackage": str(self.target), "transactionReceipts": [str(receipt)]})
        self.assertFalse(state["recoveryRequired"])
        self.assertIsNone(state["accepted"])
        self.assertEqual(self.candidate.read_bytes(), b"candidate mod")

    def test_imported_mod_update_needs_exact_existing_hash_and_preserves_original(self):
        self.target.write_bytes(b"unaccepted original")
        previous = core.sha256_file(self.target)
        result = tx.install_package(None, self.pin, self.target, self.state, previous,
                                    lambda: [], dry_run=False)
        self.assertEqual(self.target.read_bytes(), b"candidate mod")
        tx.rollback_package(result["receiptPath"], lambda: [], dry_run=False)
        self.assertEqual(self.target.read_bytes(), b"unaccepted original")

    def test_existing_target_and_active_game_block_first_install(self):
        with self.assertRaises(tx.TransactionBusyError):
            tx.install_package(None, self.pin, self.target, self.state, None,
                               lambda: ["RoadCraft.exe"], dry_run=False, expect_absent=True)
        self.target.write_bytes(b"unknown original")
        with self.assertRaises(tx.RecoveryRequiredError):
            self.install()
        self.assertEqual(self.target.read_bytes(), b"unknown original")
        self.assertFalse(self.state.exists())

    def test_target_appearing_at_atomic_creation_is_never_overwritten(self):
        original_link = tx.os.link
        def race(source, destination):
            Path(destination).write_bytes(b"another writer")
            original_link(source, destination)
        with mock.patch.object(tx.os, "link", side_effect=race):
            with self.assertRaises(FileExistsError):
                self.install()
        self.assertEqual(self.target.read_bytes(), b"another writer")
        receipt = next(self.state.glob("*/receipt.json"))
        with self.assertRaisesRegex(tx.RecoveryRequiredError, "unknown hash"):
            tx.recover_package(receipt, lambda: [], dry_run=False)

    def test_interruption_after_first_install_is_recoverable_to_absence(self):
        original = tx._advance
        def interrupt(path, data, state, detail):
            if state == "INSTALLED":
                raise OSError("interrupted after creating mod slot")
            original(path, data, state, detail)
        with mock.patch.object(tx, "_advance", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.install()
        receipt = next(self.state.glob("*/receipt.json"))
        self.assertTrue(self.target.exists())
        result = tx.recover_package(receipt, lambda: [], dry_run=False)
        self.assertEqual(result["state"], "ROLLED_BACK")
        self.assertFalse(self.target.exists())

    def test_unknown_bytes_block_rollback(self):
        result = self.install()
        self.target.write_bytes(b"later unknown package")
        with self.assertRaises(tx.RecoveryRequiredError):
            tx.rollback_package(result["receiptPath"], lambda: [], dry_run=False)
        self.assertEqual(self.target.read_bytes(), b"later unknown package")

    def test_cli_first_install_uses_mod_transaction_folder_without_changing_registry(self):
        registry = self.root / "project.json"
        registry.write_text(json.dumps({"schemaVersion": 1, "project": "trail", "accepted": {},
                                        "candidates": {"test": {"package": self.pin}}}))
        (self.root / "local").mkdir()
        (self.root / "local/machine.json").write_text(json.dumps({
            "schemaVersion": 1, "installedPackage": str(self.target), "tools": {}}))
        original = registry.read_bytes()
        with mock.patch.object(cli, "_transaction_process_check", return_value=[]):
            result, passed = cli.execute(cli.make_parser().parse_args([
                "install", "--registry", str(registry), "--candidate", "test", "--expect-absent", "--apply"]))
        self.assertTrue(passed)
        self.assertEqual(Path(result["receiptPath"]).parent.parent, self.state)
        self.assertEqual(registry.read_bytes(), original)
