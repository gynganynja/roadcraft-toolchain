import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
from roadcraft import jobs
def locked():
    exc=PermissionError('simulated Windows sharing lock');exc.winerror=32;return exc
class ReceiptRetryTests(unittest.TestCase):
    def test_transient_replace_preserves_atomic_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'receipt.json';p.write_text('{"old":true}')
            original=jobs.os.replace;attempts=[]
            def replace(a,b):
                attempts.append(1)
                if len(attempts)<3:
                    self.assertEqual(json.loads(p.read_text()),{'old':True});raise locked()
                original(a,b)
            with patch.object(jobs.os,'replace',replace),patch.object(jobs.time,'sleep'):
                jobs._atomic_json(p,{'new':True})
            self.assertEqual(json.loads(p.read_text()),{'new':True});self.assertEqual(len(attempts),3);self.assertEqual(list(Path(t).iterdir()),[p])
    def test_permanent_lock_is_bounded_and_retains_previous(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'receipt.json';p.write_text('{"old":true}')
            with patch.object(jobs.os,'replace',side_effect=locked()) as op,patch.object(jobs.time,'sleep'):
                with self.assertRaises(PermissionError):jobs._atomic_json(p,{'new':True})
            self.assertEqual(op.call_count,8);self.assertEqual(json.loads(p.read_text()),{'old':True});self.assertEqual(list(Path(t).iterdir()),[p])
    def test_other_errors_fail_immediately(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'receipt.json'
            with patch.object(jobs.os,'replace',side_effect=OSError('disk failure')) as op,patch.object(jobs.time,'sleep') as pause:
                with self.assertRaises(OSError):jobs._atomic_json(p,{})
            self.assertEqual(op.call_count,1);pause.assert_not_called();self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
