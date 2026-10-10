"""Fault injection against the real installer, with an isolated filesystem.

The fake below replaces only OS ownership and live service/SQL operations. All
installer control flow, journal ordering, immutable-content checks and retry
decisions execute unchanged. Linux FD ownership is tested separately.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import install_core_controller as installer
from publisher_transaction import Refused


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FixtureStorage:
    def __init__(self, runtime):
        self.runtime = runtime

    def mkdir_private(self, path):
        path.mkdir(exist_ok=True)

    def atomic_write_bytes(self, path, raw, **_):
        if path.exists():
            raise Refused('immutable_exists')
        return self.write(path, raw)

    def atomic_copy_file(self, source, target, digest, *, replace=False,
                         expected_existing_sha256=None, **_):
        raw = source.read_bytes()
        if sha(raw) != digest:
            raise Refused('copy_digest')
        if target.exists():
            if not replace or sha(target.read_bytes()) != expected_existing_sha256:
                raise Refused('copy_existing')
        elif expected_existing_sha256 is not None:
            raise Refused('copy_expected_missing')
        return self.write(target, raw)

    def write(self, path, raw):
        self.runtime.events.append(('write', str(path)))
        self.runtime.hit(path, 'before')
        path.write_bytes(raw)
        self.runtime.hit(path, 'after')
        return self.runtime.identity(path)


class FixtureRuntime:
    fd = 42

    def __init__(self):
        self.storage = FixtureStorage(self)
        self.failure = None
        self.events = []
        self.engine_value = SimpleNamespace(
            backend=installer.guard.BASELINE, active=lambda *_: {'pid': 1},
            frontend=lambda *_: None, tunnel=SimpleNamespace(status=lambda: None),
            watchdog_stop_locked=lambda: self.events.append(('stop', 'watchdog')),
            watchdog_start_locked=lambda: self.events.append(('start', 'watchdog')))

    def hit(self, path, edge):
        if self.failure == (path, edge):
            self.failure = None
            raise OSError('injected_storage_failure')

    def identity(self, path, expected_sha256=None, **_):
        raw = path.read_bytes()
        if expected_sha256 is not None and sha(raw) != expected_sha256:
            raise Refused('identity_digest')
        return {'sha256': sha(raw), 'bytes': len(raw)}

    def read(self, path):
        return json.loads(path.read_bytes())

    def write(self, path, value):
        return self.storage.write(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())

    def query(self, _):
        return '0'

    def engine(self):
        return self.engine_value

    def verify_current(self, _):
        self.events.append(('verify', 'current'))

    def current(self):
        from publisher_transaction import Release
        return Release(**self.read(installer.guard.STORE / 'CURRENT.json')['release'])


class InstallerFaultTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        production = root / 'r25'
        production.mkdir()
        (production / 'operations').mkdir()
        (production / 'runtime').mkdir()
        store = production / 'runtime/core-publications'
        live = {}
        for name in ('release-jar', 'preview-jar', 'manifest', 'handoff', 'application'):
            live[name] = production / name
            live[name].write_bytes(b'jar' if name.endswith('-jar') else b'{}')
        lifecycle = production / 'operations/lifecycle_adapter.py'
        launcher = production / 'operations/r25-production-java-launch.py'
        lifecycle.write_bytes(b'old lifecycle')
        launcher.write_bytes(b'old launcher')
        live['handoff'].write_bytes(b'R25_LIFECYCLE_ADAPTER_SHA256=' + sha(b'old lifecycle').encode() + b'\n')
        runtime = FixtureRuntime()
        rendered = SimpleNamespace(lifecycle=b'new lifecycle', launcher=b'new launcher',
                                   lifecycle_sha256=sha(b'new lifecycle'), launcher_sha256=sha(b'new launcher'))
        def read_file(path, expected=None, **_):
            runtime.identity(path, expected_sha256=expected)
            return path.read_bytes()
        targets = [patch.object(installer.guard, 'ROOT', production),
                   patch.object(installer.guard, 'STORE', store),
                   patch.object(installer.guard, 'BASELINE', sha(b'jar')),
                   patch.object(installer, 'BOOTSTRAP', store / 'bootstrap'),
                   patch.object(installer, 'LIVE_FILES', live),
                   patch.object(installer, 'OLD_LIFECYCLE', sha(b'old lifecycle')),
                   patch.object(installer, 'OLD_LAUNCHER', sha(b'old launcher')),
                   patch.object(installer, 'OLD_HANDOFF', sha(live['handoff'].read_bytes())),
                   patch.object(installer, 'OLD_MANIFEST', sha(live['manifest'].read_bytes())),
                   patch.object(installer, 'render_controls', lambda *_: rendered),
                   patch.object(installer, 'old_engine', lambda *_a, **_k: runtime.engine_value),
                   patch.object(installer.guard, 'read_file', read_file),
                   patch.object(installer.guard, 'payload_fingerprint', lambda _: 'c' * 64),
                   patch.object(installer.guard, 'production', lambda: SimpleNamespace(legacy=SimpleNamespace(require_backend_eligible=lambda *_: None))),
                   patch.object(installer, 'verify_http', lambda _: {'gallery_total': 9553})]
        for target in targets:
            target.start()
        self.addCleanup(lambda: [target.stop() for target in reversed(targets)])
        runtime.engine_value.backend = installer.guard.BASELINE
        return runtime, store, lifecycle, launcher, live

    def test_prepare_failure_before_and_after_every_immutable_write_is_resumable(self):
        names = ['lifecycle.before.py', 'launcher.before.py', 'handoff.before',
                 'lifecycle.after', 'launcher.after', 'guard.after', 'handoff.after']
        for name in names:
            for edge in ('before', 'after'):
                with self.subTest(name=name, edge=edge):
                    runtime, store, _, _, _ = self.fixture()
                    runtime.failure = (store / 'bootstrap' / name, edge)
                    with self.assertRaises(OSError):
                        installer.install(runtime)
                    self.assertEqual(runtime.read(store / 'bootstrap/journal.json')['phase'], 'PREPARING')
                    self.assertNotIn(('stop', 'watchdog'), runtime.events)
                    self.assertEqual(installer.install(runtime)['outcome'], 'CONTROLLER_INSTALLED')

    def test_registry_and_initial_journal_ack_loss_are_resumable(self):
        for relative in ('bootstrap/journal.json', 'POLICY.json', 'CURRENT.json'):
            for edge in ('before', 'after'):
                with self.subTest(path=relative, edge=edge):
                    runtime, store, _, _, _ = self.fixture()
                    runtime.failure = (store / relative, edge)
                    with self.assertRaises(OSError):
                        installer.install(runtime)
                    self.assertEqual(installer.install(runtime)['outcome'], 'CONTROLLER_INSTALLED')

    def test_live_install_failure_restores_and_same_bundle_can_retry(self):
        for name in ('lifecycle_adapter.py', 'r25-production-java-launch.py', 'core_release_guard.py', 'handoff'):
            for edge in ('before', 'after'):
                with self.subTest(path=name, edge=edge):
                    runtime, store, lifecycle, launcher, live = self.fixture()
                    target = live['handoff'] if name == 'handoff' else lifecycle.parent / name
                    runtime.failure = (target, edge)
                    with self.assertRaises(OSError):
                        installer.install(runtime)
                    self.assertEqual(runtime.read(store / 'bootstrap/journal.json')['phase'], 'RESTORED')
                    self.assertEqual(lifecycle.read_bytes(), b'old lifecycle')
                    self.assertEqual(launcher.read_bytes(), b'old launcher')
                    self.assertEqual(installer.install(runtime)['outcome'], 'CONTROLLER_INSTALLED')

    def test_prepare_recover_needs_no_missing_backup_and_retry_preserves_unknown(self):
        runtime, store, _, _, _ = self.fixture()
        runtime.failure = (store / 'bootstrap/lifecycle.before.py', 'before')
        with self.assertRaises(OSError):
            installer.install(runtime)
        self.assertEqual(installer.recover_install(runtime)['outcome'], 'CONTROLLER_UNCHANGED_PREPARE_RECOVERED')
        self.assertEqual(installer.recover_install(runtime)['outcome'], 'CONTROLLER_RESTORED_VERIFIED_NOOP')
        unknown = store / 'bootstrap/lifecycle.before.py'
        unknown.write_bytes(b'unknown content')
        with self.assertRaisesRegex(Refused, 'identity_digest'):
            installer.install(runtime)
        self.assertEqual(unknown.read_bytes(), b'unknown content')
        self.assertNotIn(('stop', 'watchdog'), runtime.events)


if __name__ == '__main__':
    unittest.main()
