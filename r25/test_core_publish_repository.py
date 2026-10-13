"""Actual stage/manifest identity checks with isolated files and fixture runtime.

JAR bytecode verification, ownership/lease, assets and PostgreSQL are stubs here;
candidate repository checking, policy matching and staged record creation are real.
"""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import core_business as business
import core_publish as publish
import core_release_guard as guard
from publisher_transaction import Refused
from test_core_business import fixture_policy, encoded
from test_core_candidate_repository import C
from test_core_runtime import FileFixture


class CoreStageRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='core-stage-repository-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.incoming, self.store = self.root / 'incoming', self.root / 'store'
        self.policy = fixture_policy(self.root)
        self.policy['repository'] = self.policy['upgrade']['candidate']['repository'] = business.CURRENT_REPOSITORY
        self.identity = self.policy['upgrade']['candidate']
        self.jar_raw = b'synthetic transport bytes; not a runnable Java artifact'
        self.identity['artifact_sha256'] = hashlib.sha256(self.jar_raw).hexdigest()
        self.identity['artifact_bytes'] = len(self.jar_raw)
        self.folder = self.incoming / (self.identity['commit_sha'] + '-1234-1')
        self.folder.mkdir(parents=True)
        (self.store / 'releases').mkdir(parents=True)
        self.jar = self.folder / C.JAR_NAME
        self.jar.write_bytes(self.jar_raw)
        self.report = self.folder / C.REPORT_NAME
        self.report.write_bytes(b'{}')
        self.manifest = self.folder / 'core-release-candidate.json'
        self.artifact = {'name': C.JAR_NAME, 'sha256': self.identity['artifact_sha256'], 'bytes': len(self.jar_raw)}
        self.verification = {'name': C.REPORT_NAME, 'sha256': hashlib.sha256(b'{}').hexdigest(), 'scope': C.SCOPE}
        self.files = FileFixture(self.root)
        self.verified_releases = []
        self.rt = SimpleNamespace(storage=self.files, identity=self.files.file_identity,
            read=self.files.read_private_record, lease=lambda: nullcontext(),
            verify_candidate=self.verified_releases.append,
            require_terminal_component_transactions=lambda: None, query=None)

    def stage(self, repository, *, legacy=False, payload='e' * 64):
        policy = deepcopy(self.policy)
        if legacy:
            policy = {'schema': guard.POLICY_SCHEMA, 'repository': guard.REPOSITORY,
                      'payload_fingerprint': 'e' * 64}
        (self.store / 'POLICY.json').write_bytes(encoded(policy))
        document = {'schema': C.SCHEMA, 'repository': repository, 'ref': 'refs/heads/release',
                    'commit_sha': self.identity['commit_sha'], 'github_run_id': '1234',
                    'github_run_attempt': '1', 'artifact': self.artifact,
                    'verification': self.verification, 'production_approved': False}
        self.manifest.write_bytes(encoded(document))
        with ExitStack() as stack:
            for context in (
                patch.object(publish, 'INCOMING', self.incoming), patch.object(guard, 'STORE', self.store),
                patch.object(guard, 'read_file', side_effect=lambda p, **_: Path(p).read_bytes()),
                patch.object(guard, 'source_module', return_value=C),
                patch.object(guard, 'policy', return_value=policy),
                patch.object(guard, 'business_module', return_value=business),
                patch.object(guard, 'payload_fingerprint', return_value=payload),
                patch.object(C, 'verified_inputs', return_value=(self.artifact, self.verification)),
                patch.object(business, 'verify_assets', return_value={'fixture': True}),
                patch.object(business, 'verify_compatibility', return_value={'fixture': True}),
            ):
                stack.enter_context(context)
            return publish.stage(self.rt, self.identity['commit_sha'], '1234', '1')

    def record(self, release):
        path = self.store / 'releases' / (release.artifact_sha256 + '-' + release.commit_sha) / 'record.json'
        return json.loads(path.read_text())

    def test_business_stage_keeps_actual_verified_current_repository(self):
        release = self.stage(business.CURRENT_REPOSITORY)
        record = self.record(release)
        self.assertEqual(record['repository'], business.CURRENT_REPOSITORY)
        self.assertEqual(record['schema'], guard.BUSINESS_RECORD_SCHEMA)
        self.assertEqual(record['candidate_manifest_sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        business.candidate_matches(self.policy, record)
        self.assertEqual(self.verified_releases, [release])

    def test_business_stage_supports_explicitly_approved_historical_repository(self):
        self.policy['repository'] = self.identity['repository'] = guard.REPOSITORY
        release = self.stage(guard.REPOSITORY)
        self.assertEqual(self.record(release)['repository'], guard.REPOSITORY)

    def test_manifest_cannot_choose_repository_or_relabel_itself_before_staging(self):
        for repository in (guard.REPOSITORY, 'fork/auralink-core-api'):
            with self.subTest(repository=repository), self.assertRaisesRegex(C.Refused, 'expected_repository_mismatch'):
                self.stage(repository)
            self.assertEqual(list((self.store / 'releases').iterdir()), [])
            self.assertEqual(self.files.copy_count, 0)

    def test_v1_remains_historical_only_and_rejects_changed_payload(self):
        with self.assertRaisesRegex(C.Refused, 'expected_repository_mismatch'):
            self.stage(business.CURRENT_REPOSITORY, legacy=True)
        with self.assertRaisesRegex(Refused, 'executable_change_requires_new_reviewed_acceptance_contract'):
            self.stage(guard.REPOSITORY, legacy=True, payload='f' * 64)
        self.assertEqual(list((self.store / 'releases').iterdir()), [])
        release = self.stage(guard.REPOSITORY, legacy=True)
        record = self.record(release)
        self.assertEqual(record['repository'], guard.REPOSITORY)
        self.assertEqual(record['schema'], guard.RECORD_SCHEMA)


if __name__ == '__main__':
    unittest.main()
