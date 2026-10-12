"""Phase-bound policy and exact legacy/candidate record dispatch."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core_business as business
import core_release_guard as guard
from test_core_business import fixture_policy, encoded


class BusinessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.store = self.root/'runtime/core-publications'
        (self.root/'runtime/config').mkdir(parents=True); self.store.mkdir()
        self.value = fixture_policy(self.root)
        self.before = b'auralink:\n  critic:\n    policy: configured-provider\n'
        self.after = business.render_configuration(self.before,self.value)
        self.application = self.root/'runtime/config/application.yml'; self.application.write_bytes(self.before)
        self.baseline = self.value['upgrade']['baseline_release']
        self.new = {key:self.value['upgrade']['candidate'][key] for key in ('commit_sha','artifact_sha256')}
        self.new['accepted_record_sha256'] = '9'*64
        self.write('CURRENT.json', {'schema':'R25_CORE_CURRENT_V1','release':self.baseline})
        for context in (patch.object(guard,'ROOT',self.root),patch.object(guard,'STORE',self.store),
                        patch.object(guard,'business_module',return_value=business),
                        patch.object(guard,'read_file',side_effect=self.read)):
            context.start(); self.addCleanup(context.stop)

    def read(self,path,expected=None,**_):
        raw=Path(path).read_bytes()
        if expected is not None: guard.must(business.sha(raw)==expected,'file_digest')
        return raw

    def write(self,name,value):
        path=self.store/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded(value));return path

    def active(self,phase):
        self.write('ACTIVE.json',{'transaction_id':'1'*32})
        return self.write('transactions/'+ '1'*32+'/journal.json',{'transaction_id':'1'*32,
            'phase':phase,'current':self.baseline,'candidate':self.new})

    def test_policy_phase_requires_correct_before_after_and_rejects_third_configuration(self):
        guard.validate_configuration_context(self.value)
        for phase, allowed in [('PREPARED',(self.before,)), ('START_INTENT',(self.after,)),
                               ('INSTALL_INTENT',(self.before,self.after)),
                               ('RECOVERY_REQUIRED',(self.before,self.after)),
                               ('RESTORE_INTENT',(self.before,self.after))]:
            self.active(phase)
            for raw in (self.before,self.after,b'foreign: true\n'):
                with self.subTest(phase=phase,raw=raw):
                    self.application.write_bytes(raw)
                    if raw in allowed: guard.validate_configuration_context(self.value)
                    else:
                        with self.assertRaisesRegex(guard.Refused,'configuration_state'):
                            guard.validate_configuration_context(self.value)
        self.active('UNKNOWN')
        with self.assertRaisesRegex(guard.Refused,'configuration_phase'):guard.validate_configuration_context(self.value)

    def test_completed_pointer_controls_configuration_and_foreign_release_refused(self):
        self.write('CURRENT.json',{'schema':'R25_CORE_CURRENT_V1','release':self.new})
        self.active('COMMITTED');self.application.write_bytes(self.after)
        guard.validate_configuration_context(self.value)
        self.application.write_bytes(self.before)
        with self.assertRaisesRegex(guard.Refused,'configuration_state'):guard.validate_configuration_context(self.value)
        self.write('CURRENT.json',{'schema':'R25_CORE_CURRENT_V1','release':{**self.new,'artifact_sha256':'0'*64}})
        with self.assertRaisesRegex(guard.Refused,'current_identity'):guard.validate_configuration_context(self.value)

    def test_exact_candidate_and_baseline_records_remain_distinct(self):
        policy_path=self.write('POLICY.json',self.value)
        candidate={**self.value['upgrade']['candidate'],'schema':guard.BUSINESS_RECORD_SCHEMA,
                   'policy_sha256':business.sha(policy_path.read_bytes())}
        path=self.write('releases/'+candidate['artifact_sha256']+'-'+candidate['commit_sha']+'/record.json',candidate)
        expected=business.sha(path.read_bytes())
        with patch.object(guard,'policy',return_value=self.value):
            self.assertEqual(guard.release_record(candidate['artifact_sha256'],expected,candidate['commit_sha']),candidate)
            candidate['github_run_attempt']='2';path.write_bytes(encoded(candidate))
            with self.assertRaisesRegex(business.Refused,'candidate_not_approved'):
                guard.release_record(candidate['artifact_sha256'],business.sha(path.read_bytes()),candidate['commit_sha'])
            old={'schema':guard.RECORD_SCHEMA,'repository':guard.REPOSITORY,
                 'artifact_sha256':self.baseline['artifact_sha256'],'commit_sha':self.baseline['commit_sha'],
                 'artifact_bytes':42,'payload_fingerprint':self.value['legacy_policy']['payload_fingerprint'],
                 'policy_sha256':self.value['legacy_policy_sha256']}
            path=self.write('releases/'+old['artifact_sha256']+'-'+old['commit_sha']+'/record.json',old)
            self.baseline['accepted_record_sha256']=business.sha(path.read_bytes())
            self.assertEqual(guard.release_record(old['artifact_sha256'],self.baseline['accepted_record_sha256'],old['commit_sha']),old)
            with self.assertRaises(guard.Refused):guard.release_record(old['artifact_sha256'],None,old['commit_sha'])


if __name__=='__main__':unittest.main()
