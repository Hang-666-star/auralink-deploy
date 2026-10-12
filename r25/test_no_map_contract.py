"""Profile binding with actual temporary asset bytes and explicit identity stubs.

These fixtures contain no inherited runtime data. Service lookup and effective
ancestor permissions are stubs; read_bound still checks actual file type, owner,
mode, bytes and SHA. Existing Linux asset isolation tests cover the OS boundary.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core_business as business
from test_core_business import fixture_policy, encoded


class NoMapContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r25-no-map-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = fixture_policy(self.root, 'poetry-only')
        self.assets = self.root / 'snapshot'
        self.assets.mkdir()
        self.manifest = {'schemaVersion': 2, 'releaseProfile': 'poetry-only', 'artifacts': []}
        for name, key in business.required_assets('poetry-only').items():
            raw = encoded({'fixture': name})
            path = self.assets / name
            path.write_bytes(raw)
            path.chmod(0o440)
            value = business.sha(raw)
            self.policy['upgrade']['configuration']['knowledge'][key] = value
            self.manifest['artifacts'].append({'filename': name, 'bytes': len(raw), 'sha256': value})
        self.assets.chmod(0o550)
        self.addCleanup(self.assets.chmod, 0o750)
        self.write_manifest()

    def write_manifest(self):
        path = self.root / 'assets.json'
        path.write_bytes(encoded(self.manifest))
        path.chmod(0o600)
        self.policy['upgrade']['assets']['manifest_sha256'] = business.sha(path.read_bytes())

    def verify(self):
        with patch.object(business, '_service', return_value=self.policy['installation']['service']), \
             patch.object(business, '_mode_access', return_value=5):
            return business.verify_assets(self.policy)

    def test_two_files_are_complete_without_map_permission_or_hash(self):
        receipt = self.verify()
        self.assertEqual(receipt['files'], 2)
        self.assertEqual(receipt['release_profile'], 'poetry-only')
        self.assertFalse((self.assets / 'china.json').exists())
        self.assertNotIn('china-sha256', self.policy['upgrade']['configuration']['knowledge'])
        self.assertNotIn('map_permission_sha256', self.policy['upgrade']['evidence'])

    def test_selected_configuration_is_literal_false_and_hash_bound(self):
        policy = fixture_policy(self.root, 'poetry-only')
        before = b'auralink:\n  critic:\n    policy: configured-provider\n'
        rendered = business.render_configuration(before, policy)
        self.assertIn(b'auralink.knowledge.map-enabled: false\n', rendered)
        self.assertNotIn(b'china-sha256', rendered)
        self.assertEqual(rendered.count(b'auralink.knowledge.'), 4)
        policy['upgrade']['configuration']['after_sha256'] = '0' * 64
        with self.assertRaisesRegex(business.Refused, 'configuration_after'):
            business.render_configuration(before, policy)

    def test_profile_configuration_and_evidence_mismatch_refuse(self):
        for change in ('profile', 'missing-profile', 'true', 'string-false', 'integer-zero', 'map-hash', 'map-evidence'):
            policy = deepcopy(self.policy)
            up = policy['upgrade']
            if change == 'profile': up['release_profile'] = 'map-enabled'
            elif change == 'missing-profile': del up['release_profile']
            elif change == 'true': up['configuration']['knowledge']['map-enabled'] = True
            elif change == 'string-false': up['configuration']['knowledge']['map-enabled'] = 'false'
            elif change == 'integer-zero': up['configuration']['knowledge']['map-enabled'] = 0
            elif change == 'map-hash': up['configuration']['knowledge']['china-sha256'] = '3' * 64
            else: up['evidence']['map_permission_sha256'] = '3' * 64
            with self.subTest(change=change), self.assertRaises(business.Refused):
                business.validate_policy(policy)

    def test_asset_manifest_profile_schema_names_duplicates_and_hashes_refuse(self):
        original = deepcopy(self.manifest)
        for change in ('profile', 'old-schema', 'map-entry', 'missing-entry', 'duplicate', 'wrong-hash'):
            self.manifest = deepcopy(original)
            if change == 'profile': self.manifest['releaseProfile'] = 'map-enabled'
            elif change == 'old-schema': self.manifest['schemaVersion'] = 1
            elif change == 'map-entry': self.manifest['artifacts'].append({'filename': 'china.json'})
            elif change == 'missing-entry': self.manifest['artifacts'].pop()
            elif change == 'duplicate': self.manifest['artifacts'][1] = deepcopy(self.manifest['artifacts'][0])
            else: self.manifest['artifacts'][0]['sha256'] = '0' * 64
            self.write_manifest()
            with self.subTest(change=change), self.assertRaises(business.Refused):
                self.verify()

    def test_required_file_missing_corrupt_wrong_mode_refuse_and_restore(self):
        self.assets.chmod(0o750)
        for filename in business.required_assets('poetry-only'):
            path = self.assets / filename
            original = path.read_bytes()
            for change in ('missing', 'corrupt', 'wrong-mode'):
                if change == 'missing': path.unlink()
                elif change == 'corrupt': path.chmod(0o640); path.write_bytes(b'corrupt')
                else: path.chmod(0o640)
                self.assets.chmod(0o550)
                with self.subTest(file=filename, change=change), self.assertRaises((business.Refused, OSError)):
                    self.verify()
                self.assets.chmod(0o750)
                if path.exists(): path.chmod(0o640)
                path.write_bytes(original)
                path.chmod(0o440)
                self.assets.chmod(0o550)
                self.assertEqual(self.verify()['files'], 2)
                self.assets.chmod(0o750)

    def test_extra_map_cannot_be_included_in_no_map_release_directory(self):
        self.assets.chmod(0o750)
        (self.assets / 'china.json').write_bytes(b'not a permitted release asset')
        self.assets.chmod(0o550)
        with self.assertRaisesRegex(business.Refused, 'asset_root_identity'):
            self.verify()

    def test_enabled_map_retains_three_files_hash_and_permission_requirements(self):
        self.policy = fixture_policy(self.root, 'map-enabled')
        self.manifest['releaseProfile'] = 'map-enabled'
        self.assets.chmod(0o750)
        path = self.assets / 'china.json'
        raw = b'{"type":"FeatureCollection","features":[]}'
        path.write_bytes(raw)
        path.chmod(0o440)
        self.manifest['artifacts'].append({'filename': path.name, 'bytes': len(raw), 'sha256': business.sha(raw)})
        for item in self.manifest['artifacts']:
            self.policy['upgrade']['configuration']['knowledge'][business.ASSETS[item['filename']]] = item['sha256']
        self.assets.chmod(0o550)
        self.write_manifest()
        self.assertEqual(self.verify()['files'], 3)
        self.policy['upgrade']['configuration']['knowledge']['china-sha256'] = '0' * 64
        with self.assertRaisesRegex(business.Refused, 'asset_manifest_binding'):
            self.verify()
        self.policy['upgrade']['configuration']['knowledge']['china-sha256'] = business.sha(raw)
        del self.policy['upgrade']['evidence']['map_permission_sha256']
        with self.assertRaisesRegex(business.Refused, 'review_evidence'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
