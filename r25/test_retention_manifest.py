"""Real private files and complete synthetic media inventories; SQL is a fixture.

No production paths, credentials, runtime assets or database connections are used.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import core_business as business
from r25_storage import RECORD_LIMIT, R25Storage, StorageRefused
from test_core_business import encoded, fixture_policy


class RetentionManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r25-retention-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = fixture_policy(self.root, 'poetry-only')
        self.store = R25Storage([str(self.root)], owner_uid=os.getuid(), owner_gid=os.getgid())
        self.manifest = {
            'schema': 'R25_CORE_RETAINED_DATA_V1', 'database': 'fixture',
            'port': 25432, 'major': 16, 'versions': ['V%03d' % n for n in range(1, 14)],
            'tables': {name: {'rows': 3, 'md5': 'a' * 32} for name in business.TABLES},
            'media': [],
        }
        self.current = {k: deepcopy(v) for k, v in self.manifest.items() if k not in {'schema', 'media'}}
        self.current['active_work'] = 0
        self.query = Mock(return_value=json.dumps(self.current))

    def add_media(self, count):
        paths = []
        for index in range(count):
            path = self.root / ('retained-%05d-' % index + 'x' * 180 + '.bin')
            raw = ('synthetic media %05d' % index).encode()
            path.write_bytes(raw)
            path.chmod(0o600)
            self.manifest['media'].append({'path': str(path), 'bytes': len(raw), 'sha256': business.sha(raw)})
            paths.append(path)
        return paths

    def bind_manifest(self, raw=None):
        raw = encoded(self.manifest) if raw is None else raw
        path = self.root / 'retention.json'
        path.write_bytes(raw)
        path.chmod(0o600)
        self.policy['upgrade']['compatibility']['retention_manifest_sha256'] = business.sha(raw)
        return path

    def test_large_complete_inventory_delivered_and_every_media_entry_checked(self):
        media = self.add_media(9084)
        raw = encoded(self.manifest)
        self.assertGreater(len(raw), 3 * 1024 * 1024)
        self.assertLess(len(raw), business.RETENTION_MANIFEST_LIMIT)
        incoming = self.root / 'reviewed-retention.private'
        incoming.write_bytes(raw)
        incoming.chmod(0o600)
        target = self.root / 'retention.json'
        expected = business.sha(raw)
        copied = self.store.atomic_copy_file(incoming, target, expected, expected_bytes=len(raw))
        self.assertEqual(copied['sha256'], expected)
        self.assertEqual(target.read_bytes(), raw)
        self.policy['upgrade']['compatibility']['retention_manifest_sha256'] = expected
        result = business.verify_compatibility(self.policy, self.query)
        self.assertEqual(result['media_checked'], len(media))
        self.assertEqual(result['tables_checked'], 11)
        self.assertEqual(result['database_writes'], 0)
        self.query.assert_called_once_with(business.RETENTION_SQL)

        # A failure at the last item proves the accepted inventory was not
        # silently truncated to fit the old metadata bound.
        media[-1].write_bytes(b'changed last synthetic media')
        with self.assertRaisesRegex(business.Refused, 'business_file_digest'):
            business.verify_compatibility(self.policy, self.query)

        self.query.reset_mock()
        self.policy['upgrade']['compatibility']['retention_manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(business.Refused, 'business_file_digest'):
            business.verify_compatibility(self.policy, self.query)
        self.query.assert_not_called()

    def test_manifest_permissions_owner_and_links_still_refuse_before_query(self):
        self.add_media(1)
        path = self.bind_manifest()
        path.chmod(0o644)
        with self.assertRaisesRegex(business.Refused, 'business_file_mode'):
            business.verify_compatibility(self.policy, self.query)
        path.chmod(0o600)
        self.policy['installation']['private_owner'][0] += 1
        with self.assertRaisesRegex(business.Refused, 'business_file_owner'):
            business.verify_compatibility(self.policy, self.query)
        self.policy['installation']['private_owner'][0] -= 1
        hardlink = self.root / 'hardlink'
        os.link(path, hardlink)
        with self.assertRaisesRegex(business.Refused, 'business_file_identity'):
            business.verify_compatibility(self.policy, self.query)
        hardlink.unlink()
        source = self.root / 'source.json'
        path.rename(source)
        path.symlink_to(source)
        with self.assertRaises(OSError):
            business.verify_compatibility(self.policy, self.query)
        self.query.assert_not_called()

    def test_oversize_manifest_refuses_before_reading_json_or_querying(self):
        path = self.bind_manifest()
        # Sparse fixture exercises fstat refusal without allocating 64 MiB.
        with path.open('r+b') as target:
            target.truncate(business.RETENTION_MANIFEST_LIMIT + 1)
        with self.assertRaisesRegex(business.Refused, 'business_file_identity'):
            business.verify_compatibility(self.policy, self.query)
        self.query.assert_not_called()

    def test_ordinary_metadata_keeps_one_mib_limits(self):
        self.assertEqual(RECORD_LIMIT, 1024 * 1024)
        raw = b'x' * (RECORD_LIMIT + 1)
        path = self.root / 'ordinary-metadata.json'
        path.write_bytes(raw)
        path.chmod(0o600)
        with self.assertRaisesRegex(business.Refused, 'business_file_identity'):
            business.read_bound(path)
        with self.assertRaisesRegex(StorageRefused, 'record_size_limit'):
            self.store.atomic_write_bytes(self.root / 'not-created.json', raw)
        self.assertFalse((self.root / 'not-created.json').exists())
        with self.assertRaisesRegex(StorageRefused, 'file_size_limit|record_size_limit'):
            self.store.read_private_record(path)


if __name__ == '__main__':
    unittest.main()
