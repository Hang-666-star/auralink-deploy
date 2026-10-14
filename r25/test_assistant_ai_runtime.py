"""Real AIRuntime file switching; process/HTTP/ownership boundary uses old fixture."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import ai_release_guard as guard
import ai_runtime as runtime
import test_ai_runtime as legacy

class AssistantSourceTransition(unittest.TestCase):
    def setUp(self):
        self.f=legacy.AdapterTests('runTest');self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f;old=f.files.file_identity(f.store/'POLICY.json')['sha256']
        policy=f.files.read_private_record(f.store/'POLICY.json')
        policy.update(schema='R25_AI_SOURCE_POLICY_V2',repository='bailangguihun/auralink-ai-service',source_paths=list(guard.ASSISTANT_PATHS),legacy_policy_sha256=old,source_owner=[1000,1000],review_evidence_sha256='a'*64)
        new=f.files.atomic_write_json(f.store/'POLICY.json',policy,replace=True,expected_existing_sha256=old)['sha256']
        (f.root/'runtime/handoff-control.env').write_text('R25_AI_RELEASE_POLICY_SHA256='+new+'\n')
        source={**f.source,**{name:b'# new reviewed assistant module\n' for name in set(guard.ASSISTANT_PATHS)-set(guard.SOURCE_PATHS)}}
        source['critic-service/app/main.py']+=b'# assistant router mounted\n'
        files=[{'path':name,'bytes':len(source[name]),'sha256':legacy.sha(source[name])} for name in guard.ASSISTANT_PATHS]
        ref={'commit_sha':'7'*40,'source_tree_sha256':legacy.sha(guard.canonical(files)),'record_sha256':'0'*64}
        folder=guard.release_folder(ref);(folder/'source').mkdir(parents=True)
        for name,raw in source.items():
            path=folder/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        record={'schema':'R25_AI_ACCEPTED_SOURCE_V2','repository':'bailangguihun/auralink-ai-service','commit_sha':ref['commit_sha'],
            'source_tree_sha256':ref['source_tree_sha256'],'files':files,'dependency_sha256':policy['dependency_sha256'],'policy_sha256':new}
        ref['record_sha256']=f.files.atomic_write_json(folder/'record.json',record)['sha256'];self.after=ref
        f.files.mkdir_private=lambda folder,**kw:Path(folder).mkdir(exist_ok=True)
        def remove(path,expected,**kw):
            f.files.file_identity(path,expected);Path(path).unlink()
        f.files.remove_bound_file=remove
        f.files.remove_empty_directory=lambda path,**kw:Path(path).rmdir()

    def test_added_exact_modules_publish_and_rollback_removes_only_added(self):
        f=self.f;result=runtime.publish(f.rt,self.after)
        self.assertEqual(result['outcome'],'AI_SOURCE_PUBLISHED')
        self.assertEqual(result['changed_roles'],['critic'])
        self.assertEqual(len(guard.verify_live(self.after)['files']),27)
        self.assertNotIn('stop:guide',f.events)
        with f.rt.core.lease():runtime.recover_locked(f.rt,result['transaction_id'])
        f.assert_original();self.assertFalse((f.root/'release/critic-service/app/assistant').exists())

    def test_partial_added_source_failure_restores_and_keeps_old_current(self):
        f=self.f;original=f.files.atomic_copy_file;failed=False
        def copy(source,target,expected,**kw):
            nonlocal failed
            if str(target).endswith('app/assistant/providers.py') and not failed:
                failed=True;raise OSError('synthetic one-shot copy failure')
            return original(source,target,expected,**kw)
        with patch.object(f.files,'atomic_copy_file',copy):result=runtime.publish(f.rt,self.after)
        self.assertEqual(result['outcome'],'AI_PUBLICATION_FAILED');self.assertTrue(result['restored'])
        f.assert_original();self.assertFalse((f.root/'release/critic-service/app/assistant').exists())

    def test_untracked_file_prevents_added_directory_cleanup(self):
        f=self.f;result=runtime.publish(f.rt,self.after)
        path=f.root/'release/critic-service/app/assistant/foreign.txt';path.write_text('operator data')
        with f.rt.core.lease(),self.assertRaises(OSError):runtime.recover_locked(f.rt,result['transaction_id'])
        self.assertEqual(path.read_text(),'operator data')

if __name__=='__main__':unittest.main()
