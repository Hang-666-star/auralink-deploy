"""Exact contract wiring negatives, independent from real PG rehearsal evidence."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch
import core_business as business
import core_release_guard as guard
import test_core_business as legacy

class AssistantContract(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.policy=legacy.fixture_policy(self.root,'poetry-only')
        p=self.policy;p['upgrade']['capability']='assistant-v1'
        p['runtime_modules'].update({name:'a'*64 for name in ('assistant_release.py','assistant_runtime.py','assistant_runtime_overlay.py','assistant_acceptance.py','assistant_backup.py','upgrade_assistant_controller.py')})
        knowledge=p['upgrade']['configuration']['knowledge']
        self.before=b'auralink:\n  critic:\n    policy: configured-provider\n'+b''.join(('auralink.knowledge.'+k+': '+json.dumps(v)+'\n').encode() for k,v in knowledge.items())
        values={'enabled':True,'history-only':False,'attachment-root':str(self.root/'attachments'),'execution.enabled':True,
            'execution.ai-base-url':'http://127.0.0.1:19085','execution.allow-loopback-http':True,
            'execution.internal-token-file':str(self.root/'token'),'execution.expected-config-sha256':'1'*64,
            'storage.quota-bytes':8192,'storage.draft-lifetime':'PT24H','storage.minimum-free-bytes':1024,'storage.cleanup-enabled':False}
        after=self.before+b'\n# R25 reviewed Assistant configuration\n'+b''.join(('auralink.assistant.'+k+': '+json.dumps(v)+'\n').encode() for k,v in sorted(values.items()))
        p['upgrade']['configuration']={'before_sha256':business.sha(self.before),'after_sha256':business.sha(after),'knowledge':knowledge,'assistant':values}
        p['upgrade']['assistant']={'policy_status':'PRODUCTION_REVIEWED','mode':'enabled','artifacts':{'core':{'sha256':p['upgrade']['candidate']['artifact_sha256']}},
            'configuration_sha256':business.sha(after),'compatible_recovery_jar_sha256':p['upgrade']['baseline_release']['artifact_sha256'],
            'attachment_root':values['attachment-root'],'storage_policy_sha256':business.sha(json.dumps({k:v for k,v in values.items() if k.startswith('storage.')},sort_keys=True,separators=(',',':')).encode()),'baseline_policy_sha256':'8'*64,'baseline_payload_fingerprint':'9'*64}
        # File-source loading and complete SQL inventory have their own tests;
        # this fixture isolates outer wiring without importing other repo files.
        pch=patch.object(business,'assistant_module',return_value=SimpleNamespace(validate_contract=lambda x:x));pch.start();self.addCleanup(pch.stop)

    def test_exact_core_configuration_keys_and_storage_policy_bound(self):
        raw=business.render_configuration(self.before,self.policy)
        self.assertIn(b'execution.expected-config-sha256',raw)
        self.assertIn(b'execution.allow-loopback-http: true',raw)
        self.policy['upgrade']['configuration']['assistant']['storage.quota-bytes']+=1
        with self.assertRaisesRegex(business.Refused,'storage_policy_binding'):business.render_configuration(self.before,self.policy)

    def test_baseline_business_record_remains_business_record(self):
        baseline=self.policy['upgrade']['baseline_release']
        record={'schema':guard.BUSINESS_RECORD_SCHEMA,'repository':'bailangguihun/auralink-core-api',
            'artifact_sha256':baseline['artifact_sha256'],'commit_sha':baseline['commit_sha'],'artifact_bytes':123,
            'policy_sha256':'8'*64,'payload_fingerprint':'9'*64}
        with patch.object(guard,'policy',return_value=self.policy),patch.object(guard,'private_record',return_value=record):
            self.assertEqual(guard.release_record(baseline['artifact_sha256'],baseline['accepted_record_sha256'],baseline['commit_sha']),record)
            record['schema']=guard.RECORD_SCHEMA
            with self.assertRaisesRegex(guard.Refused,'verified_v2_rollback'):guard.release_record(baseline['artifact_sha256'],baseline['accepted_record_sha256'],baseline['commit_sha'])

    def test_assistant_environment_and_cli_override_rejected(self):
        pid=self.root/'4321';pid.mkdir();(pid/'stat').write_text('4321 (java fixture) S '+'0 '*18+'123 0\n')
        (pid/'status').write_text('Uid: 65534 65534 65534 65534\nGid: 65534 65534 65534 65534\nGroups: 65534\nCapEff: 0000000000000000\n')
        config=str(self.root/'application.yml');args=('java\0--spring.config.additional-location=file:'+config+'\0').encode()
        (pid/'cmdline').write_bytes(args);(pid/'environ').write_bytes(b'AURALINK_ASSISTANT_ENABLED=false\0')
        with patch.object(business,'_service',return_value=self.policy['installation']['service']):
            with self.assertRaisesRegex(business.Refused,'configuration_override'):business.verify_process(self.policy,4321,123,config,proc_root=self.root)
            (pid/'environ').write_bytes(b'PATH=/usr/bin\0');(pid/'cmdline').write_bytes(args+b'--auralink.assistant.enabled=false\0')
            with self.assertRaisesRegex(business.Refused,'configuration_override'):business.verify_process(self.policy,4321,123,config,proc_root=self.root)

    def test_actual_adapter_rejects_test_only_policy_before_lease_or_mutation(self):
        import assistant_runtime
        for status in ('ISOLATED_TEST_ONLY',None):
            policy={'upgrade':{'assistant':{'policy_status':status}}}
            actual=deepcopy(self.policy);actual['upgrade']['assistant']['policy_status']=status
            with self.assertRaisesRegex(business.Refused,'isolated_policy_not_installable'):
                business.validate_policy(actual)
            rt=SimpleNamespace(require_lease=lambda:self.fail('test-only policy reached lease'))
            with patch.object(guard,'policy',return_value=policy), patch.object(assistant_runtime.release,'validate_contract',return_value=None):
                with self.assertRaisesRegex(assistant_runtime.release.Refused,'isolated_policy_not_installable'):
                    assistant_runtime._runtime(rt)

    def test_legacy_contract_rejects_assistant_sql_without_executing(self):
        policy=legacy.fixture_policy(self.root,'poetry-only')
        with patch.object(business,'acceptance_queries',return_value=frozenset()):
            with self.assertRaisesRegex(business.Refused,'readonly_sql_contract'):business.readonly_query(policy,business.ASSISTANT_LEDGER_SQL,7)
            with self.assertRaisesRegex(business.Refused,'readonly_sql_contract'):business.readonly_query(policy,business.ASSISTANT_IDLE_SQL,7)

if __name__=='__main__':unittest.main()
