"""A later process with a reused PID cannot own a pre-existing lock."""
from datetime import datetime
import json,tempfile,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from roadcraft import jobs
class PidReuseTests(unittest.TestCase):
    lock={'pid':1234,'createdUtc':'2026-10-10T06:11:10+00:00'}
    def test_later_creation_proves_reuse(self):
        self.assertTrue(jobs._owner_pid_reused(self.lock,datetime.fromisoformat('2026-10-10T16:18:34+10:00')))
    def test_older_equal_unknown_naive_do_not_prove_exit(self):
        for date in ('2026-10-10T06:11:09+00:00','2026-10-10T06:11:10+00:00','2026-10-10T06:18:34'):
            self.assertFalse(jobs._owner_pid_reused(self.lock,datetime.fromisoformat(date)))
        self.assertFalse(jobs._owner_pid_reused(self.lock,None))
    def test_bad_lock_date_does_not_prove_exit(self):
        later=datetime.fromisoformat('2026-10-10T06:20:00+00:00')
        for lock in ({},{'createdUtc':None},{'createdUtc':'invalid'},{'createdUtc':'2026-10-10T06:11:10'}):
            self.assertFalse(jobs._owner_pid_reused(lock,later))
    def test_inspection_records_proof_without_mutating_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);lock=root/jobs.LOCK_NAME;data=dict(self.lock,runId='failed');lock.write_text(json.dumps(data));before=lock.read_bytes()
            with patch.object(jobs,'_pid_alive',return_value=True),patch.object(jobs,'_pid_created_utc',return_value=datetime.fromisoformat('2026-10-10T06:18:34+00:00')):
                result=jobs.inspect_jobs(root)
            self.assertFalse(result['ownerAlive']);self.assertTrue(result['ownerIdentity']['pidReused']);self.assertEqual(lock.read_bytes(),before)
    def test_unknown_identity_still_blocks_live_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/jobs.LOCK_NAME).write_text(json.dumps(dict(self.lock,runId='failed')))
            with patch.object(jobs,'_pid_alive',return_value=True),patch.object(jobs,'_pid_created_utc',return_value=None):result=jobs.inspect_jobs(root)
            self.assertTrue(result['ownerAlive']);self.assertNotIn('ownerIdentity',result)
if __name__=='__main__':unittest.main()
