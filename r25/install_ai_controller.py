#!/usr/bin/env python3
"""Install the AI registry after the reviewed shared Core controller is installed.

This registers only the observed 19-file baseline. No AI/Java process restart,
pip operation or release source replacement occurs during controller setup.
The owned watchdog pauses around the single handoff binding change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import ai_release_guard as guard
from ai_publish import immutable_bytes
from ai_runtime import AIRuntime, ROOT, STORE
from core_runtime import env_values, must

BOOTSTRAP = STORE / 'bootstrap'
HANDOFF = ROOT / 'runtime/handoff-control.env'
HOOK = ROOT / 'operations/ai_release_guard.py'


def immutable_json(rt, path, value):
    return immutable_bytes(rt, path, guard.core.encoded(value))


def recover_install(rt):
    journal = rt.read(BOOTSTRAP / 'journal.json')
    must(journal.get('schema') == 'R25_AI_CONTROL_INSTALL_V1', 'ai_install_journal')
    must(rt.current() == journal.get('baseline_release'), 'ai_install_restore_after_publication_refused')
    record = rt.read(guard.release_folder(rt.current()) / 'record.json', rt.current()['record_sha256'])
    for item in record['files']:
        rt.identity(ROOT / 'release' / item['path'], expected_sha256=item['sha256'], expected_owner=(1000, 1000))
    current = rt.identity(HANDOFF)['sha256']
    must(current in {journal['before_sha256'], journal['after_sha256']}, 'ai_install_handoff_drift')
    # The Core controller remains valid with either handoff. The AI hook is
    # fully installed and registered before it can appear in the handoff.
    # A just-bound hook can itself refuse startup (for example an untracked
    # old .pyc). Owned watchdog stop must remain possible during that failure;
    # the source/current and handoff before/after bindings were checked above.
    engine = rt.partial_engine()
    engine.watchdog_stop_locked()
    if current != journal['before_sha256']:
        rt.storage.atomic_copy_file(BOOTSTRAP / 'handoff.before', HANDOFF, journal['before_sha256'],
                                    replace=True, expected_existing_sha256=current)
    engine = rt.core.engine()
    engine.watchdog_start_locked()
    must(engine.watchdog_identity(), 'ai_install_restore_watchdog')
    journal['phase'] = 'RESTORED'
    rt.write(BOOTSTRAP / 'journal.json', journal)
    return {'outcome': 'AI_CONTROLLER_BINDING_RESTORED', 'services_restarted': False}


def install(rt):
    previous = rt.read(BOOTSTRAP / 'journal.json') if (BOOTSTRAP / 'journal.json').exists() else None
    if previous and previous.get('phase') == 'INSTALLED':
        guard.verify_live(rt.current())
        rt.health(rt.core.engine())
        return {'outcome': 'AI_CONTROLLER_ALREADY_INSTALLED', 'services_restarted': False}
    must(not previous or previous.get('phase') == 'RESTORED', 'ai_install_incomplete_use_recover_install')
    rt.other_transactions_idle()
    core = rt.core.current()
    rt.core.verify_current(core)
    rt.core.require_no_active_work()
    engine = rt.core.engine()
    health = rt.health(engine)
    raw_before = guard.read_file(HANDOFF)
    values = env_values(raw_before)
    must(not any(key.startswith('R25_AI_RELEASE_') for key in values), 'ai_controller_already_bound')
    baseline = guard.core.strict_json(Path(__file__).with_name('ai-baseline.json').read_bytes())
    must(baseline.get('schema') == 'R25_AI_OBSERVED_BASELINE_V1'
         and [x['path'] for x in baseline['files']] == list(guard.SOURCE_PATHS)
         and hashlib.sha256(guard.canonical(baseline['files'])).hexdigest() == baseline['source_tree_sha256'],
         'ai_baseline_contract')
    for item in baseline['files']:
        rt.identity(ROOT / 'release' / item['path'], expected_sha256=item['sha256'],
                    expected_bytes=item['bytes'], expected_owner=(1000, 1000))
    for folder in (STORE, STORE / 'releases', STORE / 'transactions', BOOTSTRAP):
        rt.storage.mkdir_private(folder)
    before_sha = immutable_bytes(rt, BOOTSTRAP / 'handoff.before', raw_before)['sha256']
    source = Path(__file__).with_name('ai_release_guard.py').read_bytes()
    hook_sha = hashlib.sha256(source).hexdigest()
    hashes = {x['path']: x['sha256'] for x in baseline['files']}
    deps = {name: hashes[name] for name in guard.DEPENDENCIES}
    policy = {'schema': 'R25_AI_SOURCE_POLICY_V1', 'repository': guard.REPOSITORY,
        'source_paths': list(guard.SOURCE_PATHS), 'dependency_sha256': deps,
        'scope': 'reviewed release source only; same dependency files and interpreter; provider credentials stay private'}
    policy_sha = immutable_json(rt, STORE / 'POLICY.json', policy)['sha256']
    ref = {'commit_sha': baseline['source_commit'], 'source_tree_sha256': baseline['source_tree_sha256'], 'record_sha256': '0' * 64}
    target = guard.release_folder(ref)
    rt.storage.mkdir_private(target)
    rt.storage.mkdir_private(target / 'source')
    for item in baseline['files']:
        path = target / 'source' / item['path']
        rt.make_parents(path.parent, target / 'source')
        if path.exists():
            rt.identity(path, expected_sha256=item['sha256'])
        else:
            rt.storage.atomic_copy_file(ROOT / 'release' / item['path'], path, item['sha256'], source_owner=(1000, 1000))
    record = {'schema': 'R25_AI_ACCEPTED_SOURCE_V1', 'repository': guard.REPOSITORY, 'commit_sha': baseline['source_commit'],
        'source_tree_sha256': baseline['source_tree_sha256'], 'files': baseline['files'], 'dependency_sha256': deps,
        'policy_sha256': policy_sha, 'scope': 'observed production source restored to Git; no invented Actions run'}
    ref['record_sha256'] = immutable_json(rt, target / 'record.json', record)['sha256']
    immutable_json(rt, STORE / 'CURRENT.json', {'schema': 'R25_AI_CURRENT_V1', 'release': ref, 'transaction_id': None})
    if HOOK.exists():
        rt.identity(HOOK, expected_sha256=hook_sha, expected_owner=(1000, 1000), expected_mode=0o700)
    else:
        rt.storage.atomic_write_bytes(HOOK, source, mode=0o700, target_owner=(1000, 1000))
    after = raw_before + (f'R25_AI_RELEASE_GUARD={HOOK}\nR25_AI_RELEASE_GUARD_SHA256={hook_sha}\n'
                         f'R25_AI_RELEASE_POLICY_SHA256={policy_sha}\n').encode()
    after_sha = immutable_bytes(rt, BOOTSTRAP / 'handoff.after', after)['sha256']
    journal = {'schema': 'R25_AI_CONTROL_INSTALL_V1', 'phase': 'PREPARED', 'before_sha256': before_sha,
               'after_sha256': after_sha, 'hook_sha256': hook_sha, 'baseline_health': health, 'baseline_release': ref}
    rt.write(BOOTSTRAP / 'journal.json', journal)
    try:
        journal['phase'] = 'WATCHDOG_STOP_INTENT'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        engine.watchdog_stop_locked()
        journal['phase'] = 'BIND_INTENT'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        rt.storage.atomic_copy_file(BOOTSTRAP / 'handoff.after', HANDOFF, after_sha, replace=True, expected_existing_sha256=before_sha)
        guard.verify_live(ref)
        engine = rt.core.engine()
        rt.core.verify_current(core)
        rt.health(engine)
        engine.watchdog_start_locked()
        must(engine.watchdog_identity(), 'ai_install_watchdog')
        journal['phase'] = 'INSTALLED'
        rt.write(BOOTSTRAP / 'journal.json', journal)
        return {'outcome': 'AI_CONTROLLER_INSTALLED', 'services_restarted': False, 'source_replaced': False}
    except BaseException:
        recover_install(rt)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'recover-install'])
    args = parser.parse_args(argv)
    try:
        rt = AIRuntime()
        with rt.core.lease():
            result = install(rt) if args.command == 'install' else recover_install(rt)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'outcome': 'AI_INSTALL_REFUSED', 'failure_class': type(error).__name__}), file=sys.stderr)
        return 65


if __name__ == '__main__':
    raise SystemExit(main())
