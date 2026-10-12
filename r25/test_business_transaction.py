"""Actual Publisher/CoreRuntime/config-transform orchestration on fixture files.

Lifecycle, OS ownership and HTTP are explicit stubs, compatibility runs the real
validator on synthetic query output. Separate Linux storage, PostgreSQL and HTTP
checks exercise their boundaries; this is not a production process test.
"""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict
import json
from unittest.mock import patch
import unittest

import core_business as business
import core_release_guard as guard
import core_runtime as runtime
from publisher_transaction import Publisher, PublicationFailed
import test_core_runtime as runtime_fixture
from test_core_runtime import digest
from test_core_business import fixture_policy, encoded


class BusinessTransactionTests(unittest.TestCase):
    def setUp(self):
        self.h = runtime_fixture.RuntimeMethodTests('runTest')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        h = self.h
        self.rt = h.runtime
        self.policy = fixture_policy(h.root)
        up = self.policy['upgrade']
        up['baseline_release'] = asdict(h.old)
        up['candidate'].update(commit_sha=h.new.commit_sha, artifact_sha256=h.new.artifact_sha256,
            artifact_bytes=h.records[h.new.artifact_sha256]['artifact_bytes'])
        h.records[h.new.artifact_sha256].update(up['candidate'], schema=guard.BUSINESS_RECORD_SCHEMA)
        h.records[h.old.artifact_sha256].update(artifact_sha256=h.old.artifact_sha256,
            schema=guard.RECORD_SCHEMA, payload_fingerprint='b'*64)
        before = h.live['application'].read_bytes()
        up['configuration']['before_sha256'] = self.policy['legacy_policy']['application_configuration_sha256'] = digest(before)
        after = before + b'\n# R25 reviewed Knowledge configuration\n' + b''.join(
            ('auralink.knowledge.'+k+': '+json.dumps(up['configuration']['knowledge'][k])+'\n').encode()
            for k in business.CONFIG_KEYS)
        up['configuration']['after_sha256'] = digest(after)
        media = h.root/'retained-media.bin'; media.write_bytes(b'retained synthetic media')
        self.media = media
        retention = {'schema':'R25_CORE_RETAINED_DATA_V1', 'database':'fixture', 'port':25432, 'major':16,
            'versions':['V%03d'%n for n in range(1,14)],
            'tables':{t:{'rows':2,'md5':'a'*32} for t in business.TABLES},
            'media':[{'path':str(media),'bytes':len(media.read_bytes()),'sha256':digest(media.read_bytes())}]}
        path = h.root/'retention.json'; path.write_bytes(encoded(retention)); path.chmod(0o600)
        up['compatibility']['retention_manifest_sha256'] = digest(path.read_bytes())
        self.db_state = {k:v for k,v in retention.items() if k not in {'schema','media'}}
        self.db_state['active_work'] = 0
        self.rt.query = lambda sql: '0' if sql == runtime.IDLE_SQL else json.dumps(self.db_state)
        self.rt.lease = lambda: nullcontext()
        for change in (
            patch.object(guard,'policy',return_value=self.policy),
            patch.object(guard,'business_module',return_value=business),
            patch.object(guard,'payload_fingerprint',side_effect=lambda p:
                'e'*64 if digest(p.read_bytes()) == h.new.artifact_sha256 else 'b'*64),
            patch.object(business,'verify_assets',return_value={'service_readonly':True}),
            patch.object(business,'verify_process'),
            patch.object(self.rt,'verify_controls'),
            patch.object(self.rt,'acceptance',return_value={'gallery_total':123}),
        ):
            change.start(); self.addCleanup(change.stop)
        self.pub = Publisher(self.rt)

    def test_real_lifecycle_string_start_ticks_are_normalized_not_rejected(self):
        with patch.object(business, 'verify_process') as verify:
            self.rt.verify_process_contract({'pid':123,'ticks':'456'}, self.h.new)
        self.assertEqual(verify.call_args.args[1:3], (123,456))
        self.assertIs(verify.call_args.kwargs['require_isolated'], True)
        for bad in ('unknown', '-1', None, True):
            with self.subTest(ticks=bad), self.assertRaisesRegex(runtime.Refused,'start_ticks'):
                self.rt.verify_process_contract({'pid':123,'ticks':bad}, self.h.new)

    def test_valid_business_upgrade_repetition_and_compatible_rollback_preserve_data(self):
        h = self.h
        database_before = deepcopy(self.db_state)
        media_before = self.media.read_bytes()
        result = self.pub.publish(h.new)
        self.assertEqual(result.outcome, 'COMMITTED')
        self.assertEqual(self.rt.current(), h.new)
        self.assertEqual(digest(h.live['application'].read_bytes()), self.policy['upgrade']['configuration']['after_sha256'])
        self.assertEqual(self.pub.publish(h.new).outcome, 'CURRENT_VERIFIED_NOOP')
        self.assertEqual(self.pub.recover(result.transaction_id).outcome, 'COMMITTED_VERIFIED_NOOP')
        self.assertEqual(self.pub.rollback(result.transaction_id).outcome, 'RESTORED')
        for name, before in h.original.items(): self.assertEqual(h.live[name].read_bytes(), before)
        self.assertEqual(self.db_state, database_before)
        self.assertEqual(self.media.read_bytes(), media_before)
        self.assertEqual(self.pub.recover(result.transaction_id).outcome, 'RESTORED_VERIFIED_NOOP')

    def test_partial_application_install_restores_complete_pair_and_config(self):
        h = self.h
        original_copy = h.fs.atomic_copy_file
        failed = False
        def copy(source, target, *args, **kwargs):
            nonlocal failed
            if target == h.live['application'] and not failed:
                failed = True
                raise OSError('injected_application_copy_failure')
            return original_copy(source, target, *args, **kwargs)
        with patch.object(h.fs,'atomic_copy_file',side_effect=copy):
            with self.assertRaises(PublicationFailed) as error: self.pub.publish(h.new)
        self.assertTrue(error.exception.recovered)
        self.assertEqual(self.rt.current(), h.old)
        for name,before in h.original.items(): self.assertEqual(h.live[name].read_bytes(),before)
        self.assertEqual(self.pub.recover(error.exception.transaction_id).outcome, 'RESTORED_VERIFIED_NOOP')

    def test_data_drift_after_commit_refuses_rollback_without_deleting_records(self):
        result = self.pub.publish(self.h.new)
        self.db_state['tables']['catalog_source_records']['rows'] += 1
        before = deepcopy(self.db_state)
        with self.assertRaisesRegex(business.Refused, 'retained_data_drift'): self.pub.rollback(result.transaction_id)
        self.assertEqual(self.rt.current(), self.h.new)
        self.assertEqual(self.db_state, before)

    def test_unapproved_configuration_fails_before_owned_stop(self):
        self.h.live['application'].write_bytes(b'critic: changed\n')
        with self.assertRaisesRegex(business.Refused, 'configuration_before'): self.pub.publish(self.h.new)
        self.assertNotIn('java_stopped', self.h.events)
        self.assertEqual(self.rt.current(), self.h.old)

    def test_asset_missing_and_activity_refuse_before_any_live_write(self):
        with patch.object(business, 'verify_assets', side_effect=FileNotFoundError('synthetic')):
            with self.assertRaises(FileNotFoundError): self.pub.publish(self.h.new)
        self.db_state['active_work'] = 1
        with self.assertRaisesRegex(business.Refused, 'active_work'): self.pub.publish(self.h.new)
        for name,before in self.h.original.items(): self.assertEqual(self.h.live[name].read_bytes(),before)
        self.assertNotIn('java_stopped', self.h.events)

    def test_committed_business_rollback_does_not_require_assets_or_acceptance_session(self):
        result = self.pub.publish(self.h.new)
        database_before, media_before = deepcopy(self.db_state), self.media.read_bytes()
        accepted = []
        def acceptance(release, **_):
            accepted.append(release)
            if release == self.h.new:
                raise runtime.Refused('fixture_expired_acceptance_session')
            return {'gallery_total': 123}
        with patch.object(business, 'verify_assets', side_effect=FileNotFoundError('fixture_missing_assets')), \
             patch.object(self.rt, 'acceptance', side_effect=acceptance), \
             patch.object(business, 'verify_process') as process:
            self.assertEqual(self.pub.rollback(result.transaction_id).outcome, 'RESTORED')
        self.assertTrue(accepted)
        self.assertTrue(all(release == self.h.old for release in accepted))
        self.assertTrue(all(call.kwargs['require_isolated'] is False for call in process.call_args_list))
        self.assertEqual(self.rt.current(), self.h.old)
        self.assertEqual(self.db_state, database_before)
        self.assertEqual(self.media.read_bytes(), media_before)
        for name, before in self.h.original.items():
            self.assertEqual(self.h.live[name].read_bytes(), before)

    def test_business_rollback_refuses_foreign_jar_before_stopping_process(self):
        result = self.pub.publish(self.h.new)
        stopped = self.h.events.count('java_stopped')
        self.h.live['release-jar'].write_bytes(b'foreign unapproved jar')
        with self.assertRaisesRegex(runtime.Refused, 'foreign_live_file_drift'):
            self.pub.rollback(result.transaction_id)
        self.assertEqual(self.h.events.count('java_stopped'), stopped)
        self.assertEqual(self.h.live['release-jar'].read_bytes(), b'foreign unapproved jar')
        self.assertEqual(self.rt.current(), self.h.new)


if __name__ == '__main__': unittest.main()
