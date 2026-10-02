from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from roadcraft import core, transaction as tx

def failure(code):
    error=PermissionError("simulated journal reader lock")
    if code is not None:error.winerror=code
    return error

class TransactionJournalTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.receipt=self.root/"receipt.json"
        self.receipt.write_text('{"state":"OLD"}')

    def test_transient_windows_locks_keep_prior_journal_until_atomic_publish(self):
        original=tx.os.replace;seen=[]
        errors=iter([5,32,33,None])
        def replace(source,target):
            code=next(errors);seen.append(json.loads(self.receipt.read_text()))
            if code is not None:raise failure(code)
            return original(source,target)
        with mock.patch.object(tx.os,"replace",side_effect=replace),mock.patch.object(tx.time,"sleep"):
            tx._write_json(self.receipt,{"state":"NEW"})
        self.assertEqual(seen,[{"state":"OLD"}]*4)
        self.assertEqual(json.loads(self.receipt.read_text()),{"state":"NEW"})
        self.assertEqual(list(self.root.glob("*.tmp-*")),[])

    def test_persistent_lock_is_bounded_and_preserves_original_journal(self):
        with mock.patch.object(tx.os,"replace",side_effect=failure(5)) as replace,mock.patch.object(tx.time,"sleep"):
            with self.assertRaises(PermissionError):tx._write_json(self.receipt,{"state":"NEW"})
        self.assertEqual(replace.call_count,8)
        self.assertEqual(json.loads(self.receipt.read_text()),{"state":"OLD"})
        self.assertEqual(list(self.root.glob("*.tmp-*")),[])

    def test_other_and_non_windows_permission_errors_are_not_retried(self):
        for code in [None,19]:
            with self.subTest(winerror=code),mock.patch.object(tx.os,"replace",side_effect=failure(code)) as replace,mock.patch.object(tx.time,"sleep") as sleep:
                with self.assertRaises(PermissionError):tx._write_json(self.receipt,{"state":"NEW"})
                self.assertEqual(replace.call_count,1);sleep.assert_not_called()
                self.assertEqual(json.loads(self.receipt.read_text()),{"state":"OLD"})

    def test_first_install_recovers_transient_swap_ready_journal_lock(self):
        candidate=self.root/"candidate.pak";candidate.write_bytes(b"new mod bytes")
        target=self.root/"mods/truck.pak";target.parent.mkdir()
        original=tx.os.replace;locked=False
        def replace(source,destination):
            nonlocal locked
            if Path(destination).name=="receipt.json" and json.loads(Path(source).read_text())["state"]=="SWAP_READY" and not locked:
                locked=True;raise failure(5)
            return original(source,destination)
        with mock.patch.object(tx.os,"replace",side_effect=replace),mock.patch.object(tx.time,"sleep"):
            result=tx.install_package(None,{"path":str(candidate),"sha256":core.sha256_file(candidate)},target,self.root/"transactions",None,lambda:[],dry_run=False,expect_absent=True)
        saved=json.loads(Path(result["receiptPath"]).read_text())
        self.assertTrue(locked);self.assertEqual(saved["state"],"INSTALLED")
        self.assertTrue(saved["previousAbsent"]);self.assertIsNone(saved["acceptedSha256"])
        self.assertEqual(target.read_bytes(),candidate.read_bytes())
