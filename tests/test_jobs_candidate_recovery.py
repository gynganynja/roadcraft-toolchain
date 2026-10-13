"""Installed review candidates remain unaccepted after abandoned-job recovery."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from roadcraft import jobs

class CandidateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.journal=self.root/'transactions';self.journal.mkdir()
        self.package=self.root/'candidate.pak';self.package.write_bytes(b'candidate')
        self.installed=self.root/'installed.pak';self.installed.write_bytes(b'candidate')
        self.sha=sha256(b'candidate').hexdigest();self.oldsha=sha256(b'old').hexdigest()
        self.package_receipt=self.root/'package_receipt.json'
        self.package_receipt.write_text(json.dumps({'candidate':'review','packageSha256':self.sha,'accepted':False}))
        self.registry=self.root/'project.json'
        self.registry.write_text(json.dumps({'schemaVersion':1,'accepted':{},'candidates':{
            'review':{'accepted':False,'package':{'path':str(self.package),'sha256':self.sha},
            'receipt':{'path':str(self.package_receipt),'sha256':sha256(self.package_receipt.read_bytes()).hexdigest()}}}}))
        self.history=[]
        for index,(prior,candidate,path) in enumerate([(sha256(b'baseline').hexdigest(),self.oldsha,self.root/'old.pak'),
                                                       (self.oldsha,self.sha,self.package)]):
            txid=f'transaction{index}';folder=self.journal/txid;folder.mkdir();receipt=folder/'receipt.json'
            receipt.write_text(json.dumps({'schemaVersion':2,'transactionId':txid,'transactionRoot':str(self.journal),
                'installedPath':str(self.installed),'candidatePath':str(path),'previousSha256':prior,
                'candidateSha256':candidate,'previousAbsent':False,'state':'INSTALLED',
                'events':[{'state':s,'at':f'2026-10-0{index+1}T00:00:0{n}+00:00'} for n,s in enumerate(
                    ['PREPARING','BACKUP_VERIFIED','STAGED_VERIFIED','SWAP_READY','INSTALLED'])]}))
            self.history.append(receipt)
        self.config=self.root/'machine.json';self.write_config()
        self.jobsroot=self.root/'jobs';self.runid='abandoned';run=self.jobsroot/self.runid;run.mkdir(parents=True)
        self.receipt=run/'receipt.json';self.receipt.write_text(json.dumps({'runId':self.runid,'status':'failed','recoveryRequired':True}))
        self.lock=self.jobsroot/jobs.LOCK_NAME;self.lock.write_text(json.dumps({'runId':self.runid,'pid':999999}))

    def write_config(self):
        self.config.write_text(json.dumps({'schemaVersion':1,'installedPackage':str(self.installed),
                                          'transactionReceipts':[str(p) for p in self.history]}))

    def pins(self):
        return dict(jobs_root=self.jobsroot,run_id=self.runid,expected_installed_sha256=self.sha,
            expected_lock_sha256=sha256(self.lock.read_bytes()).hexdigest(),
            expected_receipt_sha256=sha256(self.receipt.read_bytes()).hexdigest(),
            registry_path=self.registry,expected_registry_sha256=sha256(self.registry.read_bytes()).hexdigest(),
            config_path=self.config,expected_config_sha256=sha256(self.config.read_bytes()).hexdigest())

    def recover(self,**kw):
        with patch.object(jobs,'_pid_alive',return_value=False),patch.object(jobs,'editor_processes',return_value=([],None)):
            return jobs.recover_jobs(**self.pins(),**kw)

    def edit(self,path,fn):
        data=json.loads(path.read_text());fn(data);path.write_text(json.dumps(data))

    def test_candidate_preview_and_release_preserve_installed_registry_and_failed_receipt(self):
        before={p:p.read_bytes() for p in (self.installed,self.registry,self.receipt,*self.history)}
        preview=self.recover();self.assertEqual(preview['installedRelation'],'candidate:review')
        self.assertEqual(preview['candidateVerification']['candidateName'],'review')
        self.assertEqual(preview['transactionLocks'][0]['path'],str(self.journal/'package.lock'))
        self.assertTrue(self.lock.exists());self.assertFalse(preview['writesPerformed'])
        released=self.recover(dry_run=False);self.assertEqual(released['status'],'released')
        self.assertFalse(self.lock.exists())
        for path,contents in before.items():self.assertEqual(path.read_bytes(),contents)

    def test_unknown_candidate_is_rejected(self):
        self.edit(self.registry,lambda d:d.update(candidates={}))
        with self.assertRaisesRegex(jobs.JobError,'exact reviewed candidate'):self.recover()

    def test_changed_candidate_package_or_receipt_is_rejected(self):
        self.package.write_bytes(b'changed')
        with self.assertRaisesRegex(jobs.JobError,'pin is stale'):self.recover()
        self.package.write_bytes(b'candidate');self.package_receipt.write_text('{}')
        with self.assertRaisesRegex(jobs.JobError,'pin is stale'):self.recover()

    def test_semantically_wrong_pinned_package_receipt_is_rejected(self):
        self.edit(self.package_receipt,lambda d:d.update(packageSha256=self.oldsha))
        self.edit(self.registry,lambda d:d['candidates']['review']['receipt'].update(
            sha256=sha256(self.package_receipt.read_bytes()).hexdigest()))
        with self.assertRaisesRegex(jobs.JobError,'does not identify'):self.recover()

    def test_stale_or_discontinuous_install_history_is_rejected(self):
        self.edit(self.history[-1],lambda d:d.update(previousSha256='0'*64))
        with self.assertRaisesRegex(jobs.JobError,'discontinuous'):self.recover()

    def test_last_install_wrong_candidate_path_is_rejected(self):
        self.edit(self.history[-1],lambda d:d.update(candidatePath=str(self.root/'unknown.pak')))
        with self.assertRaisesRegex(jobs.JobError,'Last successful install'):self.recover()

    def test_pending_transaction_and_incomplete_success_journal_are_rejected(self):
        self.edit(self.history[-1],lambda d:d.update(state='SWAP_READY'))
        with self.assertRaisesRegex(jobs.JobError,'pending or nonterminal'):self.recover()
        self.edit(self.history[-1],lambda d:d.update(state='INSTALLED',events=d['events'][-1:]))
        with self.assertRaisesRegex(jobs.JobError,'verified swap journal'):self.recover()

    def test_unlisted_transaction_and_derived_lock_are_rejected(self):
        extra=self.journal/'unlisted';extra.mkdir();(extra/'receipt.json').write_text('{}')
        with self.assertRaisesRegex(jobs.JobError,'unlisted transaction'):self.recover()
        (extra/'receipt.json').unlink();(self.journal/'package.lock').write_text('pending')
        with self.assertRaisesRegex(jobs.JobError,'lock is still present'):self.recover()

    def test_candidate_or_backup_staging_is_rejected(self):
        staged=self.installed.parent/f'.{self.installed.name}.roadcraft-x.pending';staged.write_text('pending')
        with self.assertRaisesRegex(jobs.JobError,'staging files'):self.recover()
        staged.unlink();(self.history[-1].parent/'before.pak.pending').write_text('pending')
        with self.assertRaisesRegex(jobs.JobError,'backup staging'):self.recover()

    def test_late_candidate_change_retains_lock_and_failed_recovery_attempt(self):
        calls=0
        def process_check():
            nonlocal calls
            calls+=1
            if calls==2:self.package.write_bytes(b'changed after preflight')
            return [],None
        with patch.object(jobs,'_pid_alive',return_value=False),patch.object(jobs,'editor_processes',side_effect=process_check):
            with self.assertRaisesRegex(jobs.JobError,'External state'):
                jobs.recover_jobs(**self.pins(),dry_run=False)
        self.assertTrue(self.lock.exists())
        records=list(self.receipt.parent.glob('job_recovery_*.json'));self.assertEqual(len(records),1)
        self.assertEqual(json.loads(records[0].read_text())['status'],'release_failed')

if __name__=='__main__':unittest.main()
