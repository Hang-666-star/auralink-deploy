"""Real Linux storage/flock/CAS exercised; process, SQL, assets and HTTP are fixtures.

The temp installation uses the executing test account, never a production UID.
No fixture approval is a real release authorization. No production root is used.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import upgrade_core_controller as upgrade
import core_runtime
from publisher_transaction import Refused, Release
from r25_storage import R25Storage, StorageRefused


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


SAVED_ENGINE = upgrade.saved_engine


class Runtime(upgrade.ControlUpgradeRuntime):
    def __init__(self, root):
        self.storage = R25Storage([str(root)], os.geteuid(), os.getegid())
        self.fd = None
        self.events = []
        self.interlock = False
        self.owner_conflict = False
        self.fail_verified = False
        self.engine_value = SimpleNamespace(
            active=lambda *_: {'pid': 999, 'ticks': 123},
            watchdog_stop_locked=lambda: self.events.append('watchdog-stop'),
            watchdog_start_locked=lambda: self.events.append('watchdog-start'),
            watchdog_identity=lambda: {'pid': 999, 'ticks': 123})

    def identity(self, path, **kwargs):
        return self.storage.file_identity(path, **kwargs)

    def read(self, path, expected=None):
        return self.storage.read_private_record(path, expected_sha256=expected)

    def write(self, path, document):
        old = self.identity(path)['sha256'] if path.exists() else None
        return self.storage.atomic_write_json(path, document, replace=old is not None,
                                              expected_existing_sha256=old)

    def require_terminal_component_transactions(self):
        self.require_lease()
        if self.interlock:
            raise Refused('ai_recovery_required_before_core_publication')

    def current(self):
        return Release(**self.read(upgrade.guard.STORE / 'CURRENT.json')['release'])

    def require_no_active_work(self):
        self.events.append('readonly-idle-check')

    def verify_current(self, _):
        if self.owner_conflict:
            raise Refused('sole_frontend_owner_conflict')
        if self.fail_verified and 'watchdog-stop' in self.events:
            self.fail_verified = False
            raise Refused('fixture_http_acceptance_failure')
        values = upgrade.env_values(upgrade.LIVE_FILES['handoff'].read_bytes())
        self.identity(upgrade.guard.STORE / 'POLICY.json',
                      expected_sha256=values['R25_CORE_RELEASE_POLICY_SHA256'])
        self.identity(upgrade.guard.ROOT / 'operations/core_release_guard.py',
                      expected_sha256=values['R25_CORE_RELEASE_GUARD_SHA256'],
                      expected_mode=0o700)
        self.events.append('verify-current')

    def engine(self):
        return self.engine_value


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux descriptor/fsync/flock tests')
class ControllerUpgradeTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory(prefix='core-controller-upgrade-')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        runtime = Runtime(root)
        store = root / 'runtime/core-publications'
        live = {
            'release-jar': root / 'release/backend.jar',
            'preview-jar': root / 'preview/backend.jar',
            'manifest': root / 'release/MANIFEST.json',
            'application': root / 'runtime/config/application.yml',
            'handoff': root / 'runtime/handoff-control.env',
        }
        folders = [root / 'runtime', store, root / 'release', root / 'preview', root / 'runtime/config',
                   root / 'operations', root / 'operations/r25-publisher',
                   root / 'operations/r25-controller-candidates',
                   root / 'operations/r25-controller-candidates' / ('d' * 40)]
        for folder in folders:
            runtime.storage.mkdir_private(folder)
        source = folders[-1]
        for name, path in live.items():
            if name != 'handoff':
                runtime.storage.atomic_write_bytes(path, ('preserved fixture ' + name).encode())
        release = Release('a' * 40, sha(live['release-jar'].read_bytes()), 'c' * 64)
        runtime.storage.atomic_write_json(store / 'CURRENT.json',
                                         {'schema': 'R25_CORE_CURRENT_V1', 'release': asdict(release)})
        runtime.storage.atomic_write_bytes(root / 'shared.lock', b'fixture-lock')
        runtime.storage.atomic_write_bytes(root / 'media.bin', b'existing retained media bytes')
        runtime.storage.atomic_write_bytes(root / 'database.fixture', b'existing huaniao retained fixture')
        historical = Path(__file__).parent / 'fixtures'
        v1 = upgrade.control_overlay.render_controls(
            (historical / 'lifecycle_adapter.py.snapshot').read_bytes(),
            (historical / 'r25-production-java-launch.py.snapshot').read_bytes())
        v2 = upgrade.control_overlay.render_business_controls(v1.lifecycle, v1.launcher)
        control = {}
        for name, raw in {'lifecycle_adapter.py': v1.lifecycle,
                          'r25-production-java-launch.py': v1.launcher,
                          'core_release_guard.py': b'old core_release_guard.py'}.items():
            runtime.storage.atomic_write_bytes(root / 'operations' / name, raw, mode=0o700)
            control[name] = sha(raw)
        files = {}
        for name in upgrade.PUBLISHER_FILES:
            before, after = ('old publisher ' + name).encode(), ('new publisher ' + name).encode()
            if name == 'control_overlay.py':
                after = Path(upgrade.control_overlay.__file__).read_bytes()
            if name not in upgrade.NEW_FILES:
                runtime.storage.atomic_write_bytes(root / 'operations/r25-publisher' / name, before)
            runtime.storage.atomic_write_bytes(source / name, after)
            files[name] = {'before_sha256': None if name in upgrade.NEW_FILES else sha(before),
                           'after_sha256': sha(after)}
        legacy = {
            'schema': upgrade.guard.POLICY_SCHEMA, 'repository': upgrade.guard.REPOSITORY,
            'baseline_sha256': release.artifact_sha256, 'baseline_commit': release.commit_sha,
            'payload_fingerprint': '1' * 64,
            'application_configuration_sha256': sha(live['application'].read_bytes()),
            'controllers': control,
        }
        runtime.storage.atomic_write_json(store / 'POLICY.json', legacy)
        old_policy_sha = sha((store / 'POLICY.json').read_bytes())
        ownership = [os.geteuid(), os.getegid()]
        policy = {
            'schema': upgrade.core_business.SCHEMA, 'repository': upgrade.guard.REPOSITORY,
            'legacy_policy': legacy, 'legacy_policy_sha256': old_policy_sha,
            'controllers': {'lifecycle_adapter.py': v2.lifecycle_sha256,
                            'r25-production-java-launch.py': v2.launcher_sha256,
                            'core_release_guard.py': files['core_release_guard.py']['after_sha256']},
            'runtime_modules': {name: record['after_sha256'] for name, record in files.items()},
            'installation': {
                'controller_owner': ownership, 'private_owner': ownership,
                'service': {'account': 'fixture_service', 'uid': 2345, 'gid': 2345, 'groups': [2345],
                            'isolation': 'nonroot-posix'},
                'postgres': {'psql': str(root / 'psql'), 'psql_sha256': '1' * 64,
                             'psql_owner': ownership, 'psql_mode': 0o755, 'host': '127.0.0.1',
                             'port': 55489, 'database': 'fixture_db', 'user': 'fixture_user',
                             'pgpass': str(root / 'app.pgpass'), 'credential_account': 'fixture_credential',
                             'credential_uid': 2345, 'credential_gid': 2345,
                             'native_configuration_path': str(root / 'native.json'),
                             'native_configuration_sha256': '2' * 64},
            },
            'upgrade': {
                'capability': 'knowledge-read-v1', 'release_profile': 'map-enabled', 'baseline_release': asdict(release), 'web_commit': 'e' * 40,
                'candidate': {'repository': upgrade.guard.REPOSITORY, 'commit_sha': 'b' * 40,
                              'artifact_sha256': '3' * 64, 'artifact_bytes': 100,
                              'payload_fingerprint': '2' * 64, 'github_run_id': '123', 'github_run_attempt': '1'},
                'configuration': {'before_sha256': legacy['application_configuration_sha256'],
                                  'after_sha256': '4' * 64,
                                  'knowledge': {'snapshot-root': str(root / 'assets'), 'graph-sha256': '5' * 64,
                                                'stats-sha256': '6' * 64, 'map-enabled': True, 'china-sha256': '7' * 64}},
                'assets': {'manifest_path': str(root / 'asset-manifest.json'), 'manifest_sha256': '8' * 64,
                           'owner_uid': os.geteuid(), 'owner_gid': os.getegid()},
                'compatibility': {'retention_manifest_path': str(root / 'retention.json'),
                                  'retention_manifest_sha256': '9' * 64},
                'evidence': {'review_id': 'synthetic_review_fixture', 'compatibility_sha256': 'a' * 64,
                             'acceptance_sha256': 'b' * 64, 'map_permission_sha256': 'c' * 64},
            },
        }
        runtime.storage.atomic_write_json(source / 'POLICY.next.json', policy)
        policy_sha = sha((source / 'POLICY.next.json').read_bytes())
        handoff = (f'R25_CORE_RELEASE_GUARD={root}/operations/core_release_guard.py\n'
                   f'R25_CORE_RELEASE_POLICY_SHA256={old_policy_sha}\n'
                   f'R25_CORE_RELEASE_GUARD_SHA256={control["core_release_guard.py"]}\n'
                   f'R25_LIFECYCLE_ADAPTER_SHA256={v1.lifecycle_sha256}\n'
                   'R25_FRONTEND_OWNER=c5ea\nR25_CRITIC_POLICY=configured-provider\n').encode()
        runtime.storage.atomic_write_bytes(live['handoff'], handoff)
        next_handoff = upgrade.replace_env(handoff, {
            'R25_CORE_RELEASE_POLICY_SHA256': policy_sha,
            'R25_CORE_RELEASE_GUARD_SHA256': files['core_release_guard.py']['after_sha256'],
            'R25_LIFECYCLE_ADAPTER_SHA256': v2.lifecycle_sha256})
        plan = {
            'schema': upgrade.SCHEMA, 'deploy': {'repository': 'Hang-666-star/auralink-deploy',
                'ref': 'refs/heads/release', 'commit_sha': 'd' * 40, 'run_id': '456', 'run_attempt': '1'},
            'evidence_id': 'synthetic_fixture_not_authorization', 'current_release': asdict(release),
            'preserved': {name: sha(path.read_bytes()) for name, path in live.items() if name != 'handoff'},
            'controller_owner': ownership,
            'old_controllers': {name: control[name] for name in upgrade.OVERLAY_CONTROLLERS},
            'new_controllers': {'lifecycle_adapter.py': v2.lifecycle_sha256,
                                'r25-production-java-launch.py': v2.launcher_sha256},
            'old_policy_sha256': old_policy_sha, 'new_policy_sha256': policy_sha,
            'old_handoff_sha256': sha(handoff), 'new_handoff_sha256': sha(next_handoff),
            'old_guard_sha256': control['core_release_guard.py'], 'publisher_files': files,
        }
        plan['preserved']['current'] = sha((store / 'CURRENT.json').read_bytes())
        runtime.storage.atomic_write_json(store / 'CONTROL_UPGRADE_APPROVAL.json', plan)
        plan_sha = sha((store / 'CONTROL_UPGRADE_APPROVAL.json').read_bytes())
        targets = [patch.object(upgrade.guard, 'ROOT', root), patch.object(upgrade.guard, 'STORE', store),
                   patch.object(core_runtime, 'ROOT', root), patch.object(core_runtime, 'STORE', store),
                   patch.object(upgrade, 'LIVE_FILES', live), patch.object(upgrade, 'LOCK', root / 'shared.lock'),
                   patch.object(upgrade.core_business, 'render_configuration', lambda *_: b'fixture config after'),
                   patch.object(upgrade.core_business, 'verify_assets', lambda *_: {'fixture_assets': True}),
                   patch.object(upgrade.core_business, 'verify_compatibility', lambda *_: {'fixture_pg': True}),
                   patch.object(upgrade.core_business, 'readonly_query', lambda *_: 'fixture readonly query'),
                   patch.object(upgrade.core_business, 'verify_process', lambda *_a, **_k: {'fixture_process': True}),
                   patch.object(upgrade, 'saved_engine', lambda *_: runtime.engine_value)]
        for target in targets:
            target.start()
        self.addCleanup(lambda: [target.stop() for target in reversed(targets)])
        return runtime, plan, plan_sha, root

    def run_upgrade(self, runtime, plan_sha):
        with upgrade.upgrade_lease(runtime):
            return upgrade.upgrade(runtime, plan_sha)

    def run_recover(self, runtime, plan_sha):
        with upgrade.upgrade_lease(runtime):
            return upgrade.recover(runtime, plan_sha)

    def test_valid_upgrade_preserves_application_data_and_repeated_operation_is_noop(self):
        runtime, plan, plan_sha, root = self.fixture()
        before = {path: path.read_bytes() for path in
                  [*upgrade.LIVE_FILES.values(), root / 'media.bin', root / 'database.fixture']}
        result = self.run_upgrade(runtime, plan_sha)
        self.assertEqual(result['outcome'], 'CONTROLLER_UPGRADED')
        self.assertFalse(result['java_restarted'])
        for path, raw in before.items():
            if path != upgrade.LIVE_FILES['handoff']:
                self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(runtime.current(), Release(**plan['current_release']))
        events = runtime.events[:]
        self.assertEqual(self.run_upgrade(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_ALREADY_INSTALLED')
        self.assertEqual(runtime.events, events + ['verify-current'])
        self.assertEqual(runtime.events.count('watchdog-stop'), 1)
        with self.assertRaisesRegex(Refused, 'not_recoverable'):
            self.run_recover(runtime, plan_sha)

    def test_live_copy_failure_before_and_after_every_target_requires_explicit_recovery(self):
        for index in range(len(upgrade.PUBLISHER_FILES) + 5):
            for edge in ('before', 'after'):
                with self.subTest(index=index, edge=edge):
                    runtime, plan, plan_sha, _ = self.fixture()
                    fail_path = upgrade.file_plan(plan)[index][1]
                    copy = runtime.storage.atomic_copy_file
                    failed = False
                    def fault(source, target, expected, **kwargs):
                        nonlocal failed
                        inject = target == fail_path and not failed
                        if inject and edge == 'before':
                            failed = True
                            raise OSError('synthetic controller write failure')
                        result = copy(source, target, expected, **kwargs)
                        if inject:
                            failed = True
                            raise OSError('synthetic acknowledgement loss')
                        return result
                    with patch.object(runtime.storage, 'atomic_copy_file', fault):
                        with self.assertRaises(OSError):
                            self.run_upgrade(runtime, plan_sha)
                    with self.assertRaisesRegex(Refused, 'use_recover'):
                        self.run_upgrade(runtime, plan_sha)
                    self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_RESTORED')
                    self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_UNCHANGED_VERIFIED')
                    self.assertEqual(self.run_upgrade(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADED')

    def test_preparing_interruption_recovers_without_missing_backup(self):
        runtime, _, plan_sha, _ = self.fixture()
        copy = runtime.storage.atomic_copy_file
        def fault(source, target, expected, **kwargs):
            if target.parent.name == 'before':
                raise OSError('synthetic prepare failure')
            return copy(source, target, expected, **kwargs)
        with patch.object(runtime.storage, 'atomic_copy_file', fault):
            with self.assertRaises(OSError):
                self.run_upgrade(runtime, plan_sha)
        self.assertNotIn('watchdog-stop', runtime.events)
        self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_UNCHANGED_VERIFIED')
        self.assertEqual(self.run_upgrade(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADED')

    def test_refuses_bad_approval_source_permissions_and_unknown_preexisting_module(self):
        runtime, plan, plan_sha, root = self.fixture()
        with self.assertRaises(StorageRefused):
            self.run_upgrade(runtime, 'f' * 64)
        source = upgrade.source_path(plan) / 'core_business.py'
        source.chmod(0o644)
        with self.assertRaisesRegex(StorageRefused, 'file_mode'):
            self.run_upgrade(runtime, plan_sha)
        source.chmod(0o600)
        target = root / 'operations/r25-publisher/core_business.py'
        runtime.storage.atomic_write_bytes(target, b'unknown foreign contents')
        with self.assertRaisesRegex(Refused, 'foreign_file_drift'):
            self.run_upgrade(runtime, plan_sha)
        self.assertEqual(target.read_bytes(), b'unknown foreign contents')
        self.assertNotIn('watchdog-stop', runtime.events)

    def test_lock_and_component_or_lifecycle_owner_conflicts_do_not_mutate(self):
        runtime, _, plan_sha, root = self.fixture()
        import fcntl
        with (root / 'shared.lock').open('rb') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(Refused, 'shared_publication_busy'):
                self.run_upgrade(runtime, plan_sha)
        runtime.interlock = True
        with self.assertRaisesRegex(Refused, 'ai_recovery_required'):
            self.run_upgrade(runtime, plan_sha)
        runtime.interlock = False
        runtime.owner_conflict = True
        with self.assertRaisesRegex(Refused, 'sole_frontend_owner_conflict'):
            self.run_upgrade(runtime, plan_sha)
        self.assertNotIn('watchdog-stop', runtime.events)

    def test_failed_acceptance_recovers_pair_but_foreign_drift_and_changed_current_refuse(self):
        runtime, plan, plan_sha, root = self.fixture()
        runtime.fail_verified = True
        with self.assertRaisesRegex(Refused, 'fixture_http_acceptance_failure'):
            self.run_upgrade(runtime, plan_sha)
        target = root / 'operations/r25-publisher/core_business.py'
        approved = target.read_bytes()
        target.write_bytes(b'foreign drift')
        with self.assertRaisesRegex(Refused, 'foreign_file_drift'):
            self.run_recover(runtime, plan_sha)
        self.assertEqual(target.read_bytes(), b'foreign drift')
        target.write_bytes(approved)
        current = upgrade.guard.STORE / 'CURRENT.json'
        unchanged = current.read_bytes()
        document = runtime.read(current)
        document['release']['commit_sha'] = 'f' * 40
        runtime.write(current, document)
        with self.assertRaisesRegex(Refused, 'current_release_changed'):
            self.run_recover(runtime, plan_sha)
        current.write_bytes(unchanged)
        self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_RESTORED')
        self.assertEqual(runtime.read(upgrade.guard.STORE / 'POLICY.json')['schema'], upgrade.guard.POLICY_SCHEMA)

    def test_real_controller_lease_and_interlocks_work_during_policy_handoff_mismatch(self):
        runtime, plan, plan_sha, root = self.fixture()
        # Use the actual CoreRuntime interlock code as well as the actual
        # ControlUpgradeRuntime lease. Only the process/HTTP boundary is a stub.
        with patch.object(runtime, 'require_terminal_component_transactions',
                          lambda: upgrade.ControlUpgradeRuntime.require_terminal_component_transactions(runtime)):
            copy = runtime.storage.atomic_copy_file
            def fault(source, target, expected, **kwargs):
                result = copy(source, target, expected, **kwargs)
                if target == upgrade.guard.STORE / 'POLICY.json':
                    raise OSError('policy written before handoff interrupted')
                return result
            with patch.object(runtime.storage, 'atomic_copy_file', fault):
                with self.assertRaises(OSError):
                    self.run_upgrade(runtime, plan_sha)
            values = upgrade.env_values(upgrade.LIVE_FILES['handoff'].read_bytes())
            self.assertEqual(values['R25_CORE_RELEASE_POLICY_SHA256'], plan['old_policy_sha256'])
            self.assertEqual(sha((upgrade.guard.STORE / 'POLICY.json').read_bytes()), plan['new_policy_sha256'])
            # Any policy-bound guard call here would fail on the mixed state.
            # The updater must independently validate only its held fixed lock.
            with patch.object(upgrade.guard, 'production', side_effect=AssertionError('mixed policy evaluated')):
                self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_RESTORED')
        self.assertEqual((root / 'database.fixture').read_bytes(), b'existing huaniao retained fixture')

    def test_cache_refusal_checks_adjacent_prefixed_and_symlink_bytecode(self):
        runtime, plan, _, _ = self.fixture()
        folder = upgrade.source_path(plan)
        upgrade.reject_bundle_bytecode(folder)
        cached = folder / 'core_business.pyc'
        cached.write_bytes(b'not executable fixture bytes')
        with self.assertRaisesRegex(ValueError, 'controller_bundle_bytecode_cache'):
            upgrade.reject_bundle_bytecode(folder)
        cached.unlink()
        cache_folder = folder / '__pycache__'
        cache_folder.mkdir(mode=0o700)
        (cache_folder / 'core_runtime.cpython-312.pyc').write_bytes(b'fixture bytes')
        with self.assertRaisesRegex(ValueError, 'controller_bundle_bytecode_cache'):
            upgrade.reject_bundle_bytecode(folder)

    def test_recovery_uses_immutable_approval_and_blocks_new_approval_over_interruption(self):
        runtime, plan, plan_sha, _ = self.fixture()
        runtime.fail_verified = True
        with self.assertRaisesRegex(Refused, 'fixture_http_acceptance_failure'):
            self.run_upgrade(runtime, plan_sha)
        # A newly delivered approval cannot replace the unfinished transaction.
        other = dict(plan, evidence_id='different_review_fixture')
        runtime.write(upgrade.approval_path(), other)
        other_sha = sha(upgrade.approval_path().read_bytes())
        with self.assertRaisesRegex(Refused, 'previous_controller_upgrade_recovery_required'):
            self.run_upgrade(runtime, other_sha)
        self.assertEqual(self.run_recover(runtime, plan_sha)['outcome'], 'CONTROLLER_UPGRADE_RESTORED')

    def test_process_contract_refusal_precedes_controller_or_journal_mutation(self):
        runtime, _, plan_sha, _ = self.fixture()
        with patch.object(upgrade.core_business, 'verify_process',
                          side_effect=upgrade.core_business.Refused('business_process_service_identity')):
            with self.assertRaisesRegex(upgrade.core_business.Refused, 'business_process_service_identity'):
                self.run_upgrade(runtime, plan_sha)
        self.assertFalse(upgrade.active_path().exists())
        self.assertFalse(upgrade.transaction_path(plan_sha).exists())
        self.assertNotIn('watchdog-stop', runtime.events)

    def test_asset_config_and_database_refusals_precede_all_controller_mutation(self):
        for function, reason in (
            ('verify_assets', 'business_asset_hash_mismatch'),
            ('render_configuration', 'business_configuration_after'),
            ('verify_compatibility', 'business_retention_mismatch'),
        ):
            with self.subTest(preflight=function):
                runtime, plan, plan_sha, _ = self.fixture()
                with patch.object(upgrade.core_business, function,
                                  side_effect=upgrade.core_business.Refused(reason)):
                    with self.assertRaisesRegex(upgrade.core_business.Refused, reason):
                        self.run_upgrade(runtime, plan_sha)
                self.assertFalse(upgrade.active_path().exists())
                self.assertFalse(upgrade.transaction_path(plan_sha).exists())
                self.assertNotIn('watchdog-stop', runtime.events)
                with upgrade.upgrade_lease(runtime):
                    upgrade.verify_files(runtime, plan, 'before')

    def test_actual_normal_publication_interlock_refuses_incomplete_controller_upgrade(self):
        runtime, _, plan_sha, _ = self.fixture()
        runtime.fail_verified = True
        with self.assertRaisesRegex(Refused, 'fixture_http_acceptance_failure'):
            self.run_upgrade(runtime, plan_sha)
        with upgrade.upgrade_lease(runtime):
            with self.assertRaisesRegex(Refused, 'controller_upgrade_recovery_required_before_publication'):
                core_runtime.CoreRuntime.require_terminal_component_transactions(runtime)
        self.run_recover(runtime, plan_sha)
        with upgrade.upgrade_lease(runtime):
            core_runtime.CoreRuntime.require_terminal_component_transactions(runtime)

    def test_partial_recovery_loads_exact_private_lifecycle_backup_not_changed_live_source(self):
        runtime, plan, plan_sha, _ = self.fixture()
        runtime.fail_verified = True
        with self.assertRaisesRegex(Refused, 'fixture_http_acceptance_failure'):
            self.run_upgrade(runtime, plan_sha)
        folder = upgrade.transaction_path(plan_sha)
        calls = []
        def load(path, name, expected, **kwargs):
            calls.append((path, expected, kwargs))
            runtime.identity(path, expected_sha256=expected, expected_owner=kwargs['owner'],
                             expected_mode=kwargs['mode'])
            return SimpleNamespace(production=lambda fd: runtime.engine_value)
        with upgrade.upgrade_lease(runtime), patch.object(upgrade, 'load_module', load), patch.dict(os.environ):
            engine = SAVED_ENGINE(runtime, plan, folder)
        self.assertIs(engine, runtime.engine_value)
        self.assertEqual(calls, [(folder / 'before/lifecycle_adapter.py',
                                 plan['old_controllers']['lifecycle_adapter.py'],
                                 {'owner': runtime.storage.owner, 'mode': 0o600})])
        self.assertEqual(engine.v['R25_LIFECYCLE_ADAPTER_SHA256'],
                         plan['old_controllers']['lifecycle_adapter.py'])


if __name__ == '__main__':
    unittest.main()
