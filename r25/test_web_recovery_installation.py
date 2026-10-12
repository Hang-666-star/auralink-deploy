"""One-off runbook execution in disposable files; synthetic V1 records/Next probe.

No production roots, process control or database. Existing R25Storage performs
real fsync/permission/CAS operations. Owner IDs are the CI user's fixture IDs.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from r25_storage import R25Storage

SOURCE=Path(__file__).parents[1]/'docs/knowledge/web_recovery_installation.py'


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        spec=importlib.util.spec_from_file_location('isolated_web_install',SOURCE)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        root=Path(self.tmp.name);self.m.R25=root/'r25';self.m.WEB=root/'web';self.m.STAGE=self.m.R25/'operations/install';self.m.CANDIDATE=self.m.R25/'operations/candidate'
        self.m.OWNER=(os.geteuid(),os.getegid())
        for path in (self.m.R25/'operations',self.m.R25/'runtime/core-publications/bootstrap',self.m.R25/'runtime/config',self.m.WEB/'runtime',self.m.WEB/'bin',self.m.CANDIDATE):
            path.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.before={n:('old '+n).encode() for n in self.m.BEFORE};self.after={n:('new '+n).encode() for n in self.m.AFTER}
        self.m.BEFORE={n:self.m.sha(v) for n,v in self.before.items()};self.m.AFTER={n:self.m.sha(v) for n,v in self.after.items()}
        for name,path in self.m.targets().items():
            if name!='handoff':self.put(path,self.before[name],0o700);self.put(self.m.CANDIDATE/name,self.after[name],0o700)
        policy=json.dumps({'schema':'R25_CORE_EQUIVALENT_PAYLOAD_POLICY_V1'}).encode()
        handoff=('R25_CORE_RELEASE_POLICY_SHA256='+self.m.sha(policy)+'\nR25_FRONTEND_COMMIT_HELPER_SHA256='+self.m.BEFORE['selection_commit.py']+'\nOTHER=unchanged\n').encode()
        self.put(self.m.targets()['handoff'],handoff)
        for key,path in self.m.context_paths().items():
            data=policy if key=='policy' else json.dumps({'phase':'INSTALLED','new_handoff_sha256':self.m.sha(handoff)}).encode() if key=='bootstrap' else b'fixed '+key.encode()
            self.put(path,data)
        self.put(self.m.WEB/'runtime/frontend-deployment.lock',b'')
        self.store=R25Storage([str(self.m.R25),str(self.m.WEB)],owner_uid=os.geteuid(),owner_gid=os.getegid(),private_roots=[str(self.m.STAGE),str(self.m.CANDIDATE)])
        self.calls=[];self.m.owned_next=lambda fd:self.calls.append(fd)

    @staticmethod
    def put(path,data,mode=0o600):path.write_bytes(data);path.chmod(mode)

    def prepare(self):
        with self.m.lease() as fd:return self.m.prepare(self.store,fd)['plan_sha256']

    def apply(self,digest,restore=False):
        with self.m.lease() as fd:return self.m.apply(self.store,fd,digest,restore)

    def test_prepare_records_pending_approval_without_live_changes(self):
        before={n:p.read_bytes() for n,p in self.m.targets().items()};digest=self.prepare()
        self.assertEqual(before,{n:p.read_bytes() for n,p in self.m.targets().items()})
        plan=self.store.read_private_record(self.m.STAGE/'plan.json',expected_sha256=digest)
        self.assertEqual(plan['status'],'PENDING_INDEPENDENT_APPROVAL');self.assertEqual(len(plan['files']),4)

    def test_install_and_restore_exact_four_files_and_repeat(self):
        before={n:p.read_bytes() for n,p in self.m.targets().items()};digest=self.prepare()
        self.assertEqual(self.apply(digest)['outcome'],'INSTALLED')
        self.assertEqual(self.apply(digest)['outcome'],'INSTALLED_VERIFIED_NOOP')
        for n in self.after:self.assertEqual(self.m.targets()[n].read_bytes(),self.after[n])
        self.assertEqual(self.apply(digest,True)['outcome'],'RESTORED')
        self.assertEqual(before,{n:p.read_bytes() for n,p in self.m.targets().items()})
        self.assertEqual(self.apply(digest,True)['outcome'],'RESTORED_VERIFIED_NOOP')

    def test_wrong_or_missing_approval_refuses(self):
        self.prepare()
        for value in (None,'0'*64):
            with self.assertRaises(ValueError):self.apply(value)

    def test_failure_after_first_write_requires_restore_not_replay(self):
        digest=self.prepare();original=self.store.atomic_copy_file;count=0
        def interrupted(*args,**kw):
            nonlocal count
            result=original(*args,**kw);count+=1
            if count==1:raise RuntimeError('injected_after_first_live_file')
            return result
        with patch.object(self.store,'atomic_copy_file',side_effect=interrupted),self.assertRaisesRegex(RuntimeError,'injected'):
            self.apply(digest)
        with self.assertRaisesRegex(ValueError,'partial_install_use_restore'):self.apply(digest)
        self.assertEqual(self.apply(digest,True)['outcome'],'RESTORED')
        for n in self.before:self.assertEqual(self.m.targets()[n].read_bytes(),self.before[n])

    def test_foreign_file_drift_refuses_restore(self):
        digest=self.prepare();self.apply(digest);self.put(self.m.targets()['deploy-web.sh'],b'foreign',0o700)
        with self.assertRaisesRegex(ValueError,'foreign_drift_refused'):self.apply(digest,True)
        self.assertEqual(self.m.targets()['deploy-web.sh'].read_bytes(),b'foreign')

    def test_no_bootstrap_or_v2_or_active_transaction_refuses(self):
        bootstrap=self.m.context_paths()['bootstrap'];original=bootstrap.read_bytes();self.put(bootstrap,b'{"phase":"PREPARED"}')
        with self.assertRaisesRegex(ValueError,'v1_bootstrap_not_installed'):self.prepare()
        self.put(bootstrap,original)
        active=self.m.R25/'runtime/core-publications/CONTROL_UPGRADE_ACTIVE.json';self.put(active,b'{}')
        with self.assertRaisesRegex(ValueError,'v2_has_begun'):self.prepare()
        active.unlink();active=self.m.R25/'runtime/core-publications/ACTIVE.json';self.put(active,b'{"transaction_id":"invalid"}')
        with self.assertRaisesRegex(ValueError,'transaction_identity'):self.prepare()

    def test_changed_current_context_blocks_later_restore(self):
        digest=self.prepare();self.apply(digest);self.put(self.m.context_paths()['current'],b'advanced')
        with self.assertRaisesRegex(ValueError,'baseline_context_changed'):self.apply(digest,True)

    def test_lock_conflict_refuses_without_replacing_inode(self):
        import fcntl
        lock=self.m.WEB/'runtime/frontend-deployment.lock';inode=lock.stat().st_ino
        with lock.open('rb') as holder:
            fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.prepare()
        self.assertEqual(lock.stat().st_ino,inode);self.assertFalse(self.m.STAGE.exists())


if __name__=='__main__':unittest.main()
