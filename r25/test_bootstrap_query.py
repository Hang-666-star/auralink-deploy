"""First-install SQL dispatch without a registry; never connect to a database.

The actual BootstrapRuntime/ordinary dispatcher runs. File reads are real temp
bytes; lease, metadata and fixed legacy DB adapter are isolated boundary mocks.
"""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import core_runtime
import install_core_controller as installer


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class BootstrapQueryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='r25-bootstrap-query-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.live = {name: root / name for name in ('handoff','release-jar','preview-jar')}
        self.before = b'R25_BACKEND_SHA256=' + b'a'*64 + b'\n'
        self.live['handoff'].write_bytes(self.before)
        for name in ('release-jar','preview-jar'): self.live[name].write_bytes(b'baseline-jar')
        self.rt = object.__new__(installer.BootstrapRuntime)
        self.rt.fd = 42
        def identity(path, expected_sha256=None, **_):
            actual = sha(path.read_bytes())
            if actual != expected_sha256: raise core_runtime.Refused('fixture_file_digest')
            return {'sha256':actual}
        changes = [patch.object(installer,'LIVE_FILES',self.live),
                   patch.object(installer,'OLD_HANDOFF',sha(self.before)),
                   patch.object(installer.guard,'BASELINE',sha(b'baseline-jar')),
                   patch.object(installer.guard,'read_file',side_effect=lambda p: Path(p).read_bytes()),
                   patch.object(self.rt,'identity',side_effect=identity),
                   patch.object(self.rt,'require_lease')]
        for change in changes: change.start(); self.addCleanup(change.stop)

    def test_exact_unregistered_baseline_queries_without_reading_policy(self):
        with patch.object(installer.guard,'policy',side_effect=AssertionError('registry not installed')) as policy, \
             patch.object(self.rt,'_legacy_query',return_value='0') as query:
            self.assertEqual(self.rt.query(core_runtime.IDLE_SQL),'0')
        policy.assert_not_called()
        query.assert_called_once_with(core_runtime.IDLE_SQL)
        self.assertTrue(self.rt.require_lease.called)

    def test_foreign_handoff_or_either_jar_refuses_before_database(self):
        for target in self.live:
            with self.subTest(target=target):
                path = self.live[target];before=path.read_bytes();path.write_bytes(b'foreign')
                try:
                    with patch.object(self.rt,'_legacy_query') as query:
                        with self.assertRaises(core_runtime.Refused): self.rt.query(core_runtime.IDLE_SQL)
                        query.assert_not_called()
                finally: path.write_bytes(before)

    def test_registered_missing_or_invalid_policy_does_not_fall_back(self):
        self.live['handoff'].write_bytes(self.before+b'R25_CORE_RELEASE_POLICY_SHA256='+b'f'*64+b'\n')
        with patch.object(installer.guard,'policy',side_effect=FileNotFoundError('fixture missing policy')), \
             patch.object(self.rt,'_legacy_query') as query:
            with self.assertRaises(FileNotFoundError): self.rt.query(core_runtime.IDLE_SQL)
            query.assert_not_called()

    def test_registered_v2_uses_normal_business_dispatch(self):
        self.live['handoff'].write_bytes(self.before+b'R25_CORE_RELEASE_POLICY_SHA256='+b'f'*64+b'\n')
        policy={'schema':installer.guard.BUSINESS_POLICY_SCHEMA}
        module=SimpleNamespace(readonly_query=lambda p,sql,fd: 'business-result' if p is policy and fd==42 else None)
        with patch.object(installer.guard,'policy',return_value=policy), \
             patch.object(installer.guard,'business_module',return_value=module), \
             patch.object(self.rt,'_legacy_query') as legacy:
            self.assertEqual(self.rt.query(core_runtime.IDLE_SQL),'business-result')
            legacy.assert_not_called()

    def test_normal_runtime_missing_policy_still_refuses(self):
        rt=object.__new__(core_runtime.CoreRuntime)
        with patch.object(rt,'require_lease'), patch.object(installer.guard,'policy',side_effect=FileNotFoundError()), \
             patch.object(rt,'_legacy_query') as legacy:
            with self.assertRaises(FileNotFoundError):rt.query(core_runtime.IDLE_SQL)
            legacy.assert_not_called()


if __name__ == '__main__': unittest.main()
