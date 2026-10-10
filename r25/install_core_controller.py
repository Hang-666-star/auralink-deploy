#!/usr/bin/env python3
"""One-time, exact-baseline Core controller installation; never deploy a JAR.

Run this reviewed Deploy bundle from a root-owned private directory on R25.
The existing 60c5 Java process stays running. Only its owned watchdog pauses
while controls and handoff bindings change. Original controls are retained in
an immutable private backup and can be restored with recover-install.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

import core_release_guard as guard
from control_overlay import render_controls
from core_acceptance import IDLE_SQL, verify_http
from core_runtime import CoreRuntime, LIVE_FILES, LOCK, load_module, env_values, replace_env, must
from publisher_transaction import Release

OLD_LIFECYCLE = 'b89b0abbf127d8a2f0b959646c6eeff6ca986a8fac5e626349efae74a75b28cb'
OLD_LAUNCHER = '26daa88555f928079ac59b5374bd1ba2c9fd144cb6d944ca8e0e56fc8f8a462c'
OLD_HANDOFF = 'a2199027b187e862b227f28629700c4997d1b75c4084f4e9c1e7993e7935ef38'
OLD_MANIFEST = '6d9037ab9a74f2104f00671d132aeab06d4007a438a159a616a6a7c74fc51293'
BOOTSTRAP = guard.STORE / 'bootstrap'


def immutable_bytes(rt, path, raw):
    """Resume only the exact expected private object; never adopt unknown bytes."""
    digest = hashlib.sha256(raw).hexdigest()
    if path.exists():
        return rt.identity(path, expected_sha256=digest)
    return rt.storage.atomic_write_bytes(path, raw)


def immutable_json(rt, path, document):
    raw = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    return immutable_bytes(rt, path, raw)


def immutable_copy(rt, source, target, digest, **source_policy):
    if target.exists():
        return rt.identity(target, expected_sha256=digest)
    return rt.storage.atomic_copy_file(source, target, digest, **source_policy)


def old_engine(rt, source=None, partial=False):
    sys.path.insert(0, str(guard.ROOT / 'operations'))
    module = load_module(source or guard.ROOT / 'operations/lifecycle_adapter.py', 'bootstrap_lifecycle',
                         OLD_LIFECYCLE, owner=(0, 0) if source else (1000, 1000),
                         mode=0o600 if source else 0o700)
    os.environ['R25_ROOT'] = str(guard.ROOT)
    os.environ['ARTLIVE_R25_HANDOFF_CONFIG'] = str(guard.ROOT / 'runtime/handoff-control.env')
    engine = module.production(rt.fd)
    if partial:
        engine.v = env_values(guard.read_file(LIVE_FILES['handoff']))
    else:
        engine.load()
    return engine


def install(rt):
    previous = rt.read(BOOTSTRAP / 'journal.json') if (BOOTSTRAP / 'journal.json').exists() else None
    if previous and previous.get('phase') == 'INSTALLED':
        release = rt.current()
        rt.verify_current(release)
        return {'outcome': 'CONTROLLER_ALREADY_INSTALLED', 'release': asdict(release), 'java_restarted': False}
    if previous:
        must(previous.get('schema') == 'R25_CORE_CONTROL_INSTALL_V1' and
             previous.get('phase') in {'PREPARING', 'PREPARED', 'RESTORED'}, 'bootstrap_incomplete_use_recover_install')
    for name in ('release-jar', 'preview-jar'):
        rt.identity(LIVE_FILES[name], expected_sha256=guard.BASELINE)
    rt.identity(LIVE_FILES['handoff'], expected_sha256=OLD_HANDOFF)
    rt.identity(LIVE_FILES['manifest'], expected_sha256=OLD_MANIFEST)
    lifecycle = guard.ROOT / 'operations/lifecycle_adapter.py'
    launcher = guard.ROOT / 'operations/r25-production-java-launch.py'
    rt.identity(lifecycle, expected_sha256=OLD_LIFECYCLE, expected_owner=(1000, 1000), expected_mode=0o700)
    rt.identity(launcher, expected_sha256=OLD_LAUNCHER, expected_owner=(1000, 1000), expected_mode=0o700)
    rendered = render_controls(lifecycle.read_bytes(), launcher.read_bytes())
    engine = old_engine(rt)
    must(engine.backend == guard.BASELINE and engine.active('java', 19080), 'baseline_running_identity')
    for name, port in (('guide', 19084), ('critic', 19085)):
        must(engine.active(name, port), 'baseline_paired_service')
    engine.frontend('status', rt.fd)
    engine.tunnel.status()
    guard.production().legacy.require_backend_eligible(guard.BASELINE, rt.fd)
    must(rt.query(IDLE_SQL) == '0', 'baseline_active_work')
    health = verify_http(rt.query)
    for folder in (guard.STORE, guard.STORE / 'releases', guard.STORE / 'transactions', BOOTSTRAP):
        rt.storage.mkdir_private(folder)
    runtime_guard = Path(__file__).with_name('core_release_guard.py').read_bytes()
    new_guard_sha = hashlib.sha256(runtime_guard).hexdigest()
    controls = {'lifecycle_adapter.py': rendered.lifecycle_sha256,
                'r25-production-java-launch.py': rendered.launcher_sha256,
                'core_release_guard.py': new_guard_sha}
    if previous:
        must(previous.get('new_controls') == controls and previous.get('old_handoff_sha256') == OLD_HANDOFF,
             'bootstrap_resume_bundle_changed')
    journal = {'schema': 'R25_CORE_CONTROL_INSTALL_V1', 'phase': 'PREPARING',
                'old_lifecycle_sha256': OLD_LIFECYCLE, 'old_launcher_sha256': OLD_LAUNCHER,
                'old_handoff_sha256': OLD_HANDOFF, 'new_controls': controls}
    # This precedes every immutable backup/registry write. A failed prepare is
    # resumable and explicitly distinguishable from production mutation.
    rt.write(BOOTSTRAP / 'journal.json', journal)
    for source, name, owner, mode in ((lifecycle, 'lifecycle.before.py', (1000, 1000), 0o700),
                                      (launcher, 'launcher.before.py', (1000, 1000), 0o700),
                                      (LIVE_FILES['handoff'], 'handoff.before', (0, 0), 0o600)):
        identity = rt.identity(source, expected_owner=owner, expected_mode=mode)
        immutable_copy(rt, source, BOOTSTRAP / name, identity['sha256'], source_owner=owner, source_mode=mode)
    for name, raw in (('lifecycle.after', rendered.lifecycle), ('launcher.after', rendered.launcher),
                      ('guard.after', runtime_guard)):
        immutable_bytes(rt, BOOTSTRAP / name, raw)
    fingerprint = guard.payload_fingerprint(LIVE_FILES['release-jar'])
    policy = {'schema': guard.POLICY_SCHEMA, 'repository': guard.REPOSITORY,
               'baseline_sha256': guard.BASELINE, 'baseline_commit': guard.BASELINE_COMMIT,
               'payload_fingerprint': fingerprint, 'controllers': controls,
               'application_configuration_sha256': rt.identity(LIVE_FILES['application'])['sha256'],
               'scope': 'all executable payload bytes equivalent; future business changes require reviewed policy v2'}
    policy_sha = immutable_json(rt, guard.STORE / 'POLICY.json', policy)['sha256']
    baseline_dir = guard.STORE / 'releases' / (guard.BASELINE + '-' + guard.BASELINE_COMMIT)
    rt.storage.mkdir_private(baseline_dir)
    identity = immutable_copy(rt, LIVE_FILES['release-jar'], baseline_dir / 'backend.jar', guard.BASELINE)
    record = {'schema': guard.RECORD_SCHEMA, 'repository': guard.REPOSITORY,
              'commit_sha': guard.BASELINE_COMMIT, 'artifact_sha256': guard.BASELINE,
              'artifact_bytes': identity['bytes'], 'payload_fingerprint': fingerprint,
              'policy_sha256': policy_sha, 'scope': 'exact observed running 60c5 baseline; no invented Actions run'}
    record_sha = immutable_json(rt, baseline_dir / 'record.json', record)['sha256']
    release = Release(guard.BASELINE_COMMIT, guard.BASELINE, record_sha)
    immutable_json(rt, guard.STORE / 'CURRENT.json', {'schema': 'R25_CORE_CURRENT_V1',
                                                      'release': asdict(release), 'transaction_id': None})
    old_handoff = guard.read_file(LIVE_FILES['handoff'], expected=OLD_HANDOFF)
    new_handoff = replace_env(old_handoff, {'R25_LIFECYCLE_ADAPTER_SHA256': rendered.lifecycle_sha256})
    values = env_values(new_handoff)
    must(not any(key.startswith('R25_CORE_RELEASE_') for key in values), 'core_handoff_keys_already_exist')
    new_handoff += (f'R25_CORE_RELEASE_GUARD={guard.ROOT}/operations/core_release_guard.py\n'
                    f'R25_CORE_RELEASE_GUARD_SHA256={new_guard_sha}\n'
                    f'R25_CORE_RELEASE_POLICY_SHA256={policy_sha}\n').encode()
    immutable_bytes(rt, BOOTSTRAP / 'handoff.after', new_handoff)
    journal.update({'phase': 'PREPARED', 'new_handoff_sha256': hashlib.sha256(new_handoff).hexdigest(),
                    'baseline_http': health})
    rt.write(BOOTSTRAP / 'journal.json', journal)
    try:
        journal['phase'] = 'WATCHDOG_STOP_INTENT'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        engine.watchdog_stop_locked()
        journal['phase'] = 'INSTALL_INTENT'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        for source, target, digest, old_digest in (
            ('lifecycle.after', lifecycle, rendered.lifecycle_sha256, OLD_LIFECYCLE),
            ('launcher.after', launcher, rendered.launcher_sha256, OLD_LAUNCHER),
            ('guard.after', guard.ROOT / 'operations/core_release_guard.py', new_guard_sha, None)):
            if old_digest is None and target.exists():
                # A restored previous attempt may leave this inert helper. It
                # can be reused only byte-for-byte with this journal's plan.
                rt.identity(target, expected_sha256=digest, expected_owner=(1000, 1000), expected_mode=0o700)
                continue
            rt.storage.atomic_copy_file(BOOTSTRAP / source, target, digest, target_owner=(1000, 1000),
                                        mode=0o700, replace=old_digest is not None,
                                        expected_existing_sha256=old_digest)
        rt.storage.atomic_copy_file(BOOTSTRAP / 'handoff.after', LIVE_FILES['handoff'],
                                    journal['new_handoff_sha256'], replace=True, expected_existing_sha256=OLD_HANDOFF)
        journal['phase'] = 'VERIFY_INTENT'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        rt.verify_current(release)
        rt.engine().watchdog_start_locked()
        journal['phase'] = 'INSTALLED'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        return {'outcome': 'CONTROLLER_INSTALLED', 'release': asdict(release), 'java_restarted': False}
    except BaseException:
        journal['phase'] = 'RECOVERY_REQUIRED'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        try:
            recover_install(rt)
        except BaseException:
            pass
        raise


def recover_install(rt):
    journal = rt.read(BOOTSTRAP / 'journal.json')
    must(journal.get('schema') == 'R25_CORE_CONTROL_INSTALL_V1' and
         journal['phase'] in {'PREPARING', 'PREPARED', 'WATCHDOG_STOP_INTENT', 'INSTALL_INTENT',
                              'VERIFY_INTENT', 'RECOVERY_REQUIRED', 'RESTORED'}, 'install_recovery_phase')
    # Controller recovery is no longer eligible after any normal JAR release.
    for name in ('release-jar', 'preview-jar'):
        rt.identity(LIVE_FILES[name], expected_sha256=guard.BASELINE)
    rt.identity(LIVE_FILES['manifest'], expected_sha256=OLD_MANIFEST)
    if journal['phase'] in {'PREPARING', 'RESTORED'}:
        # PREPARING has no live mutations, even if backups are incomplete.
        # RESTORED can also be verified repeatedly without needing a backup
        # which a PREPARING interruption never finished creating.
        for path, digest, owner, mode in (
            (guard.ROOT / 'operations/lifecycle_adapter.py', OLD_LIFECYCLE, (1000, 1000), 0o700),
            (guard.ROOT / 'operations/r25-production-java-launch.py', OLD_LAUNCHER, (1000, 1000), 0o700),
            (LIVE_FILES['handoff'], OLD_HANDOFF, (0, 0), 0o600)):
            rt.identity(path, expected_sha256=digest, expected_owner=owner, expected_mode=mode)
        if journal['phase'] == 'RESTORED':
            engine = old_engine(rt)
            must(engine.active('java', 19080), 'restored_baseline_java_identity')
            guard.production().legacy.require_backend_eligible(guard.BASELINE, rt.fd)
            verify_http(rt.query)
            return {'outcome': 'CONTROLLER_RESTORED_VERIFIED_NOOP', 'java_restarted': False}
        journal['phase'] = 'RESTORED'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        return {'outcome': 'CONTROLLER_UNCHANGED_PREPARE_RECOVERED', 'java_restarted': False}
    rt.identity(BOOTSTRAP / 'lifecycle.before.py', expected_sha256=OLD_LIFECYCLE)
    files = (
        ('lifecycle.before.py', guard.ROOT / 'operations/lifecycle_adapter.py', OLD_LIFECYCLE,
         journal['new_controls']['lifecycle_adapter.py'], (1000, 1000), 0o700),
        ('launcher.before.py', guard.ROOT / 'operations/r25-production-java-launch.py', OLD_LAUNCHER,
         journal['new_controls']['r25-production-java-launch.py'], (1000, 1000), 0o700),
        ('handoff.before', LIVE_FILES['handoff'], OLD_HANDOFF, journal['new_handoff_sha256'], (0, 0), 0o600))
    for source, target, old_sha, new_sha, owner, mode in files:
        rt.identity(BOOTSTRAP / source, expected_sha256=old_sha)
        observed = rt.identity(target, expected_owner=owner, expected_mode=mode)['sha256']
        must(observed in {old_sha, new_sha}, 'install_recovery_foreign_drift')
    journal['phase'] = 'RECOVERY_REQUIRED'
    rt.write(BOOTSTRAP / 'journal.json', journal)
    engine = old_engine(rt, BOOTSTRAP / 'lifecycle.before.py', partial=True)
    engine.watchdog_stop_locked()
    for source, target, old_sha, new_sha, owner, mode in files:
        observed = rt.identity(target, expected_owner=owner, expected_mode=mode)['sha256']
        must(observed in {old_sha, new_sha}, 'install_recovery_foreign_drift')
        rt.storage.atomic_copy_file(BOOTSTRAP / source, target, old_sha, target_owner=owner, mode=mode,
                                    replace=True, expected_existing_sha256=observed)
    engine = old_engine(rt)
    must(engine.active('java', 19080), 'restored_baseline_java_identity')
    guard.production().legacy.require_backend_eligible(guard.BASELINE, rt.fd)
    verify_http(rt.query)
    engine.watchdog_start_locked()
    journal['phase'] = 'RESTORED'
    rt.write(BOOTSTRAP / 'journal.json', journal)
    return {'outcome': 'CONTROLLER_RESTORED', 'java_restarted': False}


def main():
    import fcntl
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'recover-install'])
    args = parser.parse_args()
    rt = CoreRuntime()
    rt.identity(LOCK)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW)
    try:
        opened, named = os.fstat(fd), LOCK.lstat()
        must((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'install_lease_inode')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rt.fd = fd
        print(json.dumps(install(rt) if args.command == 'install' else recover_install(rt), sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'outcome': 'INSTALL_REFUSED_OR_RECOVERY_REQUIRED',
                          'failure_class': type(error).__name__}), file=sys.stderr)
        return 65
    finally:
        rt.fd = None
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
