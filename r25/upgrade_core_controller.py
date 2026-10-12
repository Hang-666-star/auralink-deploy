#!/usr/bin/env python3
"""Reviewed V1 -> V2 Core controller installation, never an application release.

The private approval and candidate bundle must be delivered separately after
review. This program does not issue approvals, discover acceptable old hashes,
or accept a caller-selected installation root. Recovery restores the old
controller/policy pair only while CURRENT and the application are unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = 'R25_CORE_CONTROLLER_UPGRADE_APPROVAL_V1'
JOURNAL_SCHEMA = 'R25_CORE_CONTROLLER_UPGRADE_TRANSACTION_V1'
# A controller candidate never chooses additional destinations. AI controllers,
# credentials and database/media files are not here. Lifecycle/launcher changes
# are derived below from the exact V1 byte overlay, never arbitrary new source.
PUBLISHER_FILES = tuple(sorted((
    'control_overlay.py', 'core_acceptance.py', 'core_asset_sandbox.py', 'core_business.py', 'core_publish.py',
    'core_release_guard.py', 'core_runtime.py', 'core-release-candidate.py',
    'publisher_transaction.py', 'r25_storage.py', 'upgrade_core_controller.py',
    'verify-r25-artifact.py',
)))
NEW_FILES = {'core_asset_sandbox.py', 'core_business.py', 'upgrade_core_controller.py'}
OVERLAY_CONTROLLERS = {'lifecycle_adapter.py', 'r25-production-java-launch.py'}
PRESERVED = {'release-jar', 'preview-jar', 'manifest', 'application', 'current'}
PHASES = {'PREPARING', 'PREPARED', 'WATCHDOG_STOP_INTENT', 'INSTALL_INTENT',
          'VERIFY_INTENT', 'INSTALLED', 'RECOVERY_REQUIRED', 'RESTORED'}


def reject_bundle_bytecode(folder):
    """Run before controller imports: -B alone still accepts existing .pyc."""
    folder = Path(folder)
    cache = folder / '__pycache__'
    if cache.is_symlink():
        raise ValueError('controller_bundle_bytecode_cache')
    for name in PUBLISHER_FILES:
        source = folder / name
        candidates = {source.with_suffix('.pyc'), source.with_suffix('.pyo')}
        if cache.exists():
            candidates.update(cache.glob(source.stem + '.*.pyc'))
            candidates.update(cache.glob(source.stem + '.*.pyo'))
        for optimization in ('', '1', '2'):
            candidates.add(Path(importlib.util.cache_from_source(str(source), optimization=optimization)))
        if any(path.exists() or path.is_symlink() for path in candidates):
            raise ValueError('controller_bundle_bytecode_cache')


if __name__ == '__main__':
    try:
        reject_bundle_bytecode(Path(__file__).absolute().parent)
    except ValueError:
        print(json.dumps({'outcome': 'CONTROLLER_UPGRADE_REFUSED',
                          'reason': 'controller_bundle_bytecode_cache'}), file=sys.stderr)
        raise SystemExit(65)
    sys.dont_write_bytecode = True

import core_business
import control_overlay
import core_release_guard as guard
from core_runtime import CoreRuntime, LIVE_FILES, LOCK, env_values, load_module, must, replace_env


class ControlUpgradeRuntime(CoreRuntime):
    """Controller recovery must validate the lease before policy is consistent.

    This adapter is private to the controller installer. Application publication
    keeps CoreRuntime's policy-bound guard. All application/control identities
    still undergo separate, exact approved before/after verification here.
    """
    def require_lease(self):
        import fcntl
        must(type(self.fd) is int and self.fd >= 3, 'upgrade_lease_required')
        self.identity(LOCK)
        opened, named = os.fstat(self.fd), LOCK.lstat()
        must((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'upgrade_lease_inode')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            from publisher_transaction import Refused
            raise Refused('shared_publication_busy') from error

    def require_terminal_component_transactions(self):
        # This installer owns CONTROL_UPGRADE_ACTIVE and validates it against
        # its exact approval separately. Core/AI transactions still interlock.
        self.require_terminal_application_transactions()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def immutable_bytes(rt, path, raw):
    if path.exists():
        return rt.identity(path, expected_sha256=digest(raw))
    return rt.storage.atomic_write_bytes(path, raw)


def immutable_copy(rt, source, target, expected, **kwargs):
    if target.exists():
        return rt.identity(target, expected_sha256=expected)
    return rt.storage.atomic_copy_file(source, target, expected, **kwargs)


def private_bytes(rt, path, expected):
    return guard.read_file(path, owner=rt.storage.owner, expected=expected)


def approval_path():
    return guard.STORE / 'CONTROL_UPGRADE_APPROVAL.json'


def transaction_path(approval_sha):
    return guard.STORE / 'controller-upgrades' / guard.digest_value(approval_sha)


def active_path():
    return guard.STORE / 'CONTROL_UPGRADE_ACTIVE.json'


def require_active(rt, approval_sha, *, recover_phase=None):
    path = active_path()
    if not path.exists():
        must(recover_phase in {None, 'PREPARING'}, 'upgrade_active_marker_missing')
        return None
    observed = rt.identity(path)['sha256']
    active = rt.read(path, observed)
    must(set(active) == {'schema', 'approval_sha256'} and
         active['schema'] == 'R25_CORE_CONTROLLER_UPGRADE_ACTIVE_V1', 'upgrade_active_marker_schema')
    previous_sha = guard.digest_value(active['approval_sha256'])
    if previous_sha != approval_sha:
        must(recover_phase is None, 'upgrade_recovery_not_active')
        previous = journal_at(rt, transaction_path(previous_sha), previous_sha)
        must(previous['phase'] in {'INSTALLED', 'RESTORED'}, 'previous_controller_upgrade_recovery_required')
    return observed


def source_path(plan):
    return guard.ROOT / 'operations/r25-controller-candidates' / plan['deploy']['commit_sha']


def owner(value):
    must(type(value) is list and len(value) == 2 and
         all(type(item) is int and item >= 0 for item in value), 'upgrade_owner_identity')
    return tuple(value)


def validate_plan(plan):
    must(type(plan) is dict and set(plan) == {
        'schema', 'deploy', 'evidence_id', 'current_release', 'preserved',
        'controller_owner', 'old_controllers', 'new_controllers', 'old_policy_sha256',
        'new_policy_sha256', 'old_handoff_sha256', 'new_handoff_sha256',
        'old_guard_sha256', 'publisher_files'}, 'upgrade_approval_fields')
    must(plan['schema'] == SCHEMA, 'upgrade_approval_schema')
    identity = plan['deploy']
    must(type(identity) is dict and set(identity) == {
        'repository', 'ref', 'commit_sha', 'run_id', 'run_attempt'} and
        identity['repository'] == 'Hang-666-star/auralink-deploy' and
        identity['ref'] == 'refs/heads/release', 'upgrade_deploy_identity')
    guard.digest_value(identity['commit_sha'], 40)
    for name in ('run_id', 'run_attempt'):
        must(type(identity[name]) is str and re.fullmatch('[1-9][0-9]{0,19}', identity[name]),
             'upgrade_deploy_run')
    must(type(plan['evidence_id']) is str and re.fullmatch('[A-Za-z0-9_.-]{1,128}', plan['evidence_id']),
         'upgrade_review_evidence')
    release = plan['current_release']
    must(type(release) is dict and set(release) == {
        'commit_sha', 'artifact_sha256', 'accepted_record_sha256'}, 'upgrade_current_release')
    for name, value in release.items():
        guard.digest_value(value, 40 if name == 'commit_sha' else 64)
    must(type(plan['preserved']) is dict and set(plan['preserved']) == PRESERVED,
         'upgrade_preserved_allowlist')
    for value in plan['preserved'].values():
        guard.digest_value(value)
    owner(plan['controller_owner'])
    for side in ('old_controllers', 'new_controllers'):
        must(type(plan[side]) is dict and set(plan[side]) == OVERLAY_CONTROLLERS,
             'upgrade_controller_allowlist')
        for value in plan[side].values():
            guard.digest_value(value)
    must(plan['old_controllers'] == {
        'lifecycle_adapter.py': control_overlay.V1_LIFECYCLE_SHA256,
        'r25-production-java-launch.py': control_overlay.V1_LAUNCHER_SHA256}, 'upgrade_audited_v1_controls')
    for name in ('old_policy_sha256', 'new_policy_sha256', 'old_handoff_sha256',
                 'new_handoff_sha256', 'old_guard_sha256'):
        guard.digest_value(plan[name])
    files = plan['publisher_files']
    must(type(files) is dict and set(files) == set(PUBLISHER_FILES), 'upgrade_publisher_allowlist')
    for name, record in files.items():
        must(type(record) is dict and set(record) == {'before_sha256', 'after_sha256'},
             'upgrade_publisher_identity')
        guard.digest_value(record['after_sha256'])
        if record['before_sha256'] is None:
            must(name in NEW_FILES, 'upgrade_required_existing_module')
        else:
            guard.digest_value(record['before_sha256'])
    return plan


def read_plan(rt, approval_sha):
    guard.digest_value(approval_sha)
    return validate_plan(rt.read(approval_path(), approval_sha))


def file_plan(plan):
    """All paths derive from trusted constants; none come from approval strings."""
    result = []
    control_owner = owner(plan['controller_owner'])
    for name in PUBLISHER_FILES:
        entry = plan['publisher_files'][name]
        result.append((name, guard.ROOT / 'operations/r25-publisher' / name,
                       entry['before_sha256'], entry['after_sha256'], None, 0o600))
    for name in sorted(OVERLAY_CONTROLLERS):
        result.append((name, guard.ROOT / 'operations' / name,
                       plan['old_controllers'][name], plan['new_controllers'][name], control_owner, 0o700))
    result.extend((
        ('operation-guard', guard.ROOT / 'operations/core_release_guard.py',
         plan['old_guard_sha256'], plan['publisher_files']['core_release_guard.py']['after_sha256'],
         control_owner, 0o700),
        ('policy', guard.STORE / 'POLICY.json', plan['old_policy_sha256'],
         plan['new_policy_sha256'], None, 0o600),
        ('handoff', LIVE_FILES['handoff'], plan['old_handoff_sha256'],
         plan['new_handoff_sha256'], None, 0o600),
    ))
    return result


def require_preserved(rt, plan):
    rt.require_lease()
    rt.require_terminal_component_transactions()
    must(asdict(rt.current()) == plan['current_release'], 'upgrade_current_release_changed')
    for name, expected in plan['preserved'].items():
        target = guard.STORE / 'CURRENT.json' if name == 'current' else LIVE_FILES[name]
        rt.identity(target, expected_sha256=expected)


def verify_files(rt, plan, state):
    for _, path, before, after, uid, mode in file_plan(plan):
        # New modules retained by recovery are inert under the old policy. They
        # are never removed or trusted with unknown contents on a later retry.
        if before is None and not path.exists():
            must(state != 'after', 'upgrade_new_module_missing')
            rt.storage.validate_target(path, exists=False)
            continue
        expected = {after} if state == 'after' else ({before, after} if state == 'mixed' else {before})
        if before is None:
            expected = {after}
        observed = rt.identity(path, expected_owner=uid, expected_mode=mode)['sha256']
        must(observed in expected, 'upgrade_foreign_file_drift')


def validate_policy_pair(rt, plan, old_raw, new_raw):
    old_policy, new_policy = guard.strict_json(old_raw), guard.strict_json(new_raw)
    must(digest(old_raw) == plan['old_policy_sha256'] and
         digest(new_raw) == plan['new_policy_sha256'], 'upgrade_policy_bytes')
    must(old_policy.get('schema') == guard.POLICY_SCHEMA, 'upgrade_requires_v1_policy')
    core_business.validate_policy(new_policy)
    must(new_policy['legacy_policy'] == old_policy and
         new_policy['legacy_policy_sha256'] == plan['old_policy_sha256'], 'upgrade_legacy_policy_binding')
    must(new_policy['upgrade']['baseline_release'] == plan['current_release'],
         'upgrade_policy_baseline_binding')
    must(new_policy['installation']['controller_owner'] == plan['controller_owner'] and
         owner(new_policy['installation']['private_owner']) == rt.storage.owner,
         'upgrade_installation_owner_binding')
    controllers = dict(plan['new_controllers'])
    controllers['core_release_guard.py'] = plan['publisher_files']['core_release_guard.py']['after_sha256']
    must(new_policy['controllers'] == controllers, 'upgrade_new_controller_binding')
    expected_modules = {name: plan['publisher_files'][name]['after_sha256']
                        for name in PUBLISHER_FILES}
    must(expected_modules == new_policy['runtime_modules'], 'upgrade_runtime_module_binding')
    return new_policy


def prepare(rt, plan, approval_sha, folder):
    previous_marker_sha = require_active(rt, approval_sha)
    require_preserved(rt, plan)
    verify_files(rt, plan, 'before')
    rt.verify_current(rt.current())
    rt.require_no_active_work()
    source = source_path(plan)
    # Review pins source bytes independently from the installed files. Private
    # source ownership uses the installation runtime's storage contract.
    for name, record in plan['publisher_files'].items():
        rt.identity(source / name, expected_sha256=record['after_sha256'])
    must(digest(Path(control_overlay.__file__).read_bytes()) ==
         plan['publisher_files']['control_overlay.py']['after_sha256'], 'upgrade_overlay_source_binding')
    rt.identity(source / 'POLICY.next.json', expected_sha256=plan['new_policy_sha256'])
    rt.identity(guard.STORE / 'POLICY.json', expected_sha256=plan['old_policy_sha256'])
    old_raw = private_bytes(rt, guard.STORE / 'POLICY.json', plan['old_policy_sha256'])
    new_raw = private_bytes(rt, source / 'POLICY.next.json', plan['new_policy_sha256'])
    new_policy = validate_policy_pair(rt, plan, old_raw, new_raw)
    # Evaluate the approved deployment inputs before creating a journal or
    # stopping the watchdog. Installing a controller is not a way to defer
    # discovery of unusable assets, incompatible PG access or configuration.
    core_business.render_configuration(private_bytes(rt, LIVE_FILES['application'],
                                                     plan['preserved']['application']), new_policy)
    core_business.verify_assets(new_policy)
    core_business.verify_compatibility(new_policy,
        lambda sql: core_business.readonly_query(new_policy, sql, rt.fd))
    process = rt.engine().active('java', 19080)
    must(type(process) is dict and type(process.get('pid')) is int and
         str(process.get('ticks', '')).isdecimal(), 'upgrade_current_process_identity')
    # A private approval does not turn a root process into a read-only service.
    # Establish the actual current identity before installing its V2 policy.
    core_business.verify_process(new_policy, process['pid'], int(process['ticks']),
                                 LIVE_FILES['application'], require_isolated=False)
    before_controls = {name: guard.read_file(guard.ROOT / 'operations' / name,
                       owner=owner(plan['controller_owner']), mode=0o700,
                       expected=plan['old_controllers'][name]) for name in OVERLAY_CONTROLLERS}
    rendered = control_overlay.render_business_controls(before_controls['lifecycle_adapter.py'],
                                                        before_controls['r25-production-java-launch.py'])
    control_bytes = {'lifecycle_adapter.py': rendered.lifecycle,
                     'r25-production-java-launch.py': rendered.launcher}
    must({name: digest(raw) for name, raw in control_bytes.items()} == plan['new_controllers'],
         'upgrade_rendered_controls_binding')
    handoff = private_bytes(rt, LIVE_FILES['handoff'], plan['old_handoff_sha256'])
    must(digest(handoff) == plan['old_handoff_sha256'], 'upgrade_handoff_bytes')
    values = env_values(handoff)
    must(values.get('R25_CORE_RELEASE_POLICY_SHA256') == plan['old_policy_sha256'] and
         values.get('R25_CORE_RELEASE_GUARD_SHA256') == plan['old_guard_sha256'] and
         values.get('R25_CORE_RELEASE_GUARD') == str(guard.ROOT / 'operations/core_release_guard.py'),
         'upgrade_old_handoff_binding')
    after_handoff = replace_env(handoff, {
        'R25_CORE_RELEASE_POLICY_SHA256': plan['new_policy_sha256'],
        'R25_CORE_RELEASE_GUARD_SHA256': plan['publisher_files']['core_release_guard.py']['after_sha256'],
        'R25_LIFECYCLE_ADAPTER_SHA256': plan['new_controllers']['lifecycle_adapter.py'],
    })
    must(digest(after_handoff) == plan['new_handoff_sha256'], 'upgrade_new_handoff_binding')
    for path in (guard.STORE / 'controller-upgrades', folder, folder / 'before', folder / 'after'):
        rt.storage.mkdir_private(path)
    journal = {'schema': JOURNAL_SCHEMA, 'approval_sha256': approval_sha, 'phase': 'PREPARING'}
    rt.write(folder / 'journal.json', journal)
    immutable_copy(rt, approval_path(), folder / 'approval.json', approval_sha)
    rt.storage.atomic_write_json(active_path(), {
        'schema': 'R25_CORE_CONTROLLER_UPGRADE_ACTIVE_V1', 'approval_sha256': approval_sha},
        replace=previous_marker_sha is not None, expected_existing_sha256=previous_marker_sha)
    for name, path, before, after, uid, mode in file_plan(plan):
        if before is not None:
            immutable_copy(rt, path, folder / 'before' / name, before,
                           source_owner=uid, source_mode=mode)
        if name == 'handoff':
            immutable_bytes(rt, folder / 'after' / name, after_handoff)
        elif name in control_bytes:
            immutable_bytes(rt, folder / 'after' / name, control_bytes[name])
        else:
            incoming = (source / 'POLICY.next.json' if name == 'policy' else
                        source / ('core_release_guard.py' if name == 'operation-guard' else name))
            immutable_copy(rt, incoming, folder / 'after' / name, after)
    journal['phase'] = 'PREPARED'
    rt.write(folder / 'journal.json', journal)
    return journal


def saved_engine(rt, plan, folder):
    """Use the approved V1 backup even after installing V2 lifecycle bytes."""
    path = folder / 'before/lifecycle_adapter.py'
    module = load_module(path, 'controller_upgrade_lifecycle', plan['old_controllers'][path.name],
                         owner=rt.storage.owner, mode=0o600)
    os.environ['R25_ROOT'] = str(guard.ROOT)
    os.environ['ARTLIVE_R25_HANDOFF_CONFIG'] = str(LIVE_FILES['handoff'])
    engine = module.production(rt.fd)
    before = folder / 'before/handoff'
    rt.identity(before, expected_sha256=plan['old_handoff_sha256'])
    engine.v = env_values(private_bytes(rt, before, plan['old_handoff_sha256']))
    engine.kind = engine.v.get('R25_LIFECYCLE_RELEASE_KIND')
    return engine


def journal_at(rt, folder, approval_sha):
    journal = rt.read(folder / 'journal.json')
    must(set(journal) == {'schema', 'approval_sha256', 'phase'} and
         journal['schema'] == JOURNAL_SCHEMA and journal['approval_sha256'] == approval_sha and
         journal['phase'] in PHASES, 'upgrade_journal_binding')
    return journal


def upgrade(rt, approval_sha):
    plan = read_plan(rt, approval_sha)
    folder = transaction_path(approval_sha)
    if (folder / 'journal.json').exists():
        journal = journal_at(rt, folder, approval_sha)
        if journal['phase'] == 'INSTALLED':
            require_active(rt, approval_sha, recover_phase='INSTALLED')
            require_preserved(rt, plan)
            verify_files(rt, plan, 'after')
            rt.verify_current(rt.current())
            return {'outcome': 'CONTROLLER_UPGRADE_ALREADY_INSTALLED', 'java_restarted': False}
        must(journal['phase'] in {'PREPARING', 'PREPARED', 'RESTORED'},
             'controller_upgrade_incomplete_use_recover')
    journal = prepare(rt, plan, approval_sha, folder)
    engine = saved_engine(rt, plan, folder)
    try:
        journal['phase'] = 'WATCHDOG_STOP_INTENT'
        rt.write(folder / 'journal.json', journal)
        engine.watchdog_stop_locked()
        require_preserved(rt, plan)
        verify_files(rt, plan, 'before')
        journal['phase'] = 'INSTALL_INTENT'
        rt.write(folder / 'journal.json', journal)
        for name, path, before, after, uid, mode in file_plan(plan):
            observed = rt.identity(path, expected_owner=uid, expected_mode=mode)['sha256'] if path.exists() else None
            must(observed == before or (before is None and observed == after), 'upgrade_install_compare_and_swap')
            if observed == after:
                continue
            rt.storage.atomic_copy_file(folder / 'after' / name, path, after,
                                        target_owner=uid, mode=mode, replace=observed is not None,
                                        expected_existing_sha256=observed)
        journal['phase'] = 'VERIFY_INTENT'
        rt.write(folder / 'journal.json', journal)
        require_preserved(rt, plan)
        verify_files(rt, plan, 'after')
        rt.verify_current(rt.current())
        activated = rt.engine()
        activated.watchdog_start_locked()
        must(activated.watchdog_identity() is not None, 'upgrade_watchdog_identity')
        journal['phase'] = 'INSTALLED'
        rt.write(folder / 'journal.json', journal)
        return {'outcome': 'CONTROLLER_UPGRADED', 'approval_sha256': approval_sha,
                'java_restarted': False, 'application_release_changed': False}
    except BaseException:
        journal['phase'] = 'RECOVERY_REQUIRED'
        rt.write(folder / 'journal.json', journal)
        # Recovery is explicit. A blind retry must never restart an interrupted
        # install, especially when the last durable write acknowledgement was lost.
        raise


def recover(rt, approval_sha):
    folder = transaction_path(approval_sha)
    journal = journal_at(rt, folder, approval_sha)
    recorded = folder / 'approval.json'
    plan = (validate_plan(rt.read(recorded, approval_sha)) if recorded.exists() else
            read_plan(rt, approval_sha))
    require_active(rt, approval_sha, recover_phase=journal['phase'])
    require_preserved(rt, plan)
    must(journal['phase'] != 'INSTALLED', 'installed_controller_upgrade_not_recoverable')
    if journal['phase'] in {'PREPARING', 'PREPARED', 'RESTORED'}:
        verify_files(rt, plan, 'before')
        rt.verify_current(rt.current())
        if not recorded.exists():
            immutable_copy(rt, approval_path(), recorded, approval_sha)
        if not active_path().exists():
            rt.storage.atomic_write_json(active_path(), {
                'schema': 'R25_CORE_CONTROLLER_UPGRADE_ACTIVE_V1', 'approval_sha256': approval_sha})
        journal['phase'] = 'RESTORED'
        rt.write(folder / 'journal.json', journal)
        return {'outcome': 'CONTROLLER_UPGRADE_UNCHANGED_VERIFIED', 'java_restarted': False}
    # Verify every file before touching any file. Unknown external edits remain
    # intact and keep the operation explicitly recoverable, never adopted.
    verify_files(rt, plan, 'mixed')
    for name, _, before, after, _, _ in file_plan(plan):
        if before is not None:
            rt.identity(folder / 'before' / name, expected_sha256=before)
        rt.identity(folder / 'after' / name, expected_sha256=after)
    journal['phase'] = 'RECOVERY_REQUIRED'
    rt.write(folder / 'journal.json', journal)
    saved_engine(rt, plan, folder).watchdog_stop_locked()
    require_preserved(rt, plan)
    verify_files(rt, plan, 'mixed')
    for name, path, before, after, uid, mode in file_plan(plan):
        if before is None:
            continue
        observed = rt.identity(path, expected_owner=uid, expected_mode=mode)['sha256']
        must(observed in {before, after}, 'upgrade_recovery_foreign_drift')
        if observed != before:
            rt.storage.atomic_copy_file(folder / 'before' / name, path, before,
                                        target_owner=uid, mode=mode, replace=True,
                                        expected_existing_sha256=observed)
    verify_files(rt, plan, 'before')
    rt.verify_current(rt.current())
    restored = rt.engine()
    restored.watchdog_start_locked()
    must(restored.watchdog_identity() is not None, 'upgrade_watchdog_identity')
    journal['phase'] = 'RESTORED'
    rt.write(folder / 'journal.json', journal)
    return {'outcome': 'CONTROLLER_UPGRADE_RESTORED', 'java_restarted': False,
            'application_release_changed': False}


@contextmanager
def upgrade_lease(rt):
    """Same publication lock, including recovery while controllers are mixed."""
    import fcntl
    must(rt.fd is None, 'nested_runtime_lease')
    rt.identity(LOCK)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW)
    try:
        opened, named = os.fstat(fd), LOCK.lstat()
        must((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'upgrade_lease_inode')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            from publisher_transaction import Refused
            raise Refused('shared_publication_busy') from error
        rt.fd = fd
        yield
    finally:
        rt.fd = None
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('upgrade', 'recover'))
    parser.add_argument('--approval-sha256', required=True)
    args = parser.parse_args()
    rt = ControlUpgradeRuntime()
    try:
        with upgrade_lease(rt):
            recorded = transaction_path(args.approval_sha256) / 'approval.json'
            plan = (validate_plan(rt.read(recorded, args.approval_sha256))
                    if args.command == 'recover' and recorded.exists() else
                    read_plan(rt, args.approval_sha256))
            # Run only the independently reviewed source bundle, not installed
            # modules which this transaction replaces partway through recovery.
            must(Path(__file__).absolute() == source_path(plan) / 'upgrade_core_controller.py',
                 'upgrade_trusted_bundle_location')
            rt.identity(Path(__file__), expected_sha256=plan['publisher_files'][Path(__file__).name]['after_sha256'])
            result = upgrade(rt, args.approval_sha256) if args.command == 'upgrade' else recover(rt, args.approval_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'outcome': 'CONTROLLER_UPGRADE_REFUSED_OR_RECOVERY_REQUIRED',
                          'failure_class': type(error).__name__,
                          'reason': str(error) if re.fullmatch('[a-z0-9_]+', str(error)) else 'private_diagnostic_required'},
                         sort_keys=True), file=sys.stderr)
        return 65


if __name__ == '__main__':
    raise SystemExit(main())
