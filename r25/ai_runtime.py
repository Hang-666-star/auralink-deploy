"""Fixed-host AI source publication with shared Core/Web lease and real adapter.

Only the 19 reviewed source files may change. No pip, database write, provider
request, JAR switch, frontend restart or tunnel restart is performed here.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
import stat
import re
import secrets
import shutil
import time
import urllib.error
import urllib.request

import ai_release_guard as guard
from core_acceptance import NoRedirect, verify_http
from core_runtime import CoreRuntime, must
from publisher_transaction import Release
from r25_storage import R25Storage

ROOT, STORE = guard.ROOT, guard.STORE
INCOMING = ROOT.parent / 'ai-release-incoming'
PORTS = {'guide': 19084, 'critic': 19085}
PHASES = guard.OLD_PHASES | guard.NEW_PHASES | {'INSTALL_INTENT', 'INSTALLED', 'RECOVERY_REQUIRED',
    'RESTORE_STOP_INTENT', 'RESTORE_STOPPED', 'RESTORE_INTENT'}


def role(path):
    return 'guide' if path.startswith('guide_service/') else 'critic'


def get_json(port, path, *, token=None, expected_status=200):
    must((port, path) in {(19084, '/health'), (19084, '/v1/guide/generate'),
                         (19085, '/health'), (19085, '/api/v1/readiness')}, 'ai_fixed_http_endpoint')
    headers = {'Accept': 'application/json'}
    if token is not None:
        must(port == 19085 and path == '/api/v1/readiness', 'ai_token_endpoint')
        headers['X-Auralink-Critic-Token'] = token
    probe_auth = (port, path) == (19084, '/v1/guide/generate')
    if probe_auth:
        must(token is None and expected_status == 401, 'guide_auth_probe_only')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers,
                                     data=b'{}' if probe_auth else None, method='POST' if probe_auth else 'GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=8)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(65537)
        must(response.status == expected_status and response.headers.get_content_type() == 'application/json'
             and len(raw) <= 65536, 'ai_http_contract')
    return guard.core.strict_json(raw)


def validate_health(guide, critic, ready):
    must(guide.get('status') == 'UP' and guide.get('providerConfigured') is True
         and guide.get('modelConfigured') is True, 'guide_not_configured')
    must(critic.get('status') == 'ok' and critic.get('model_configured') is True
         and critic.get('vision_capable') is True, 'critic_not_configured')
    must(ready.get('evaluation_available') is True and ready.get('execution_policy') == 'configured-provider'
         and ready.get('provider') == critic.get('provider') and ready.get('model') == critic.get('model'),
         'critic_not_ready')
    # Raw provider/model/detail bodies never enter Actions logs or receipts.
    return {'guide_configured': True, 'critic_configured': True, 'critic_ready': True,
            'provider_requests': 0, 'database_writes': 0}


class AIRuntime:
    def __init__(self):
        self.core = CoreRuntime()
        self.storage = R25Storage([str(ROOT), str(INCOMING)], private_roots=[str(STORE), str(INCOMING)])

    def identity(self, path, **kwargs):
        return self.storage.file_identity(path, **kwargs)

    def read(self, path, expected=None):
        return self.storage.read_private_record(path, expected_sha256=expected)

    def write(self, path, value):
        old = self.identity(path)['sha256'] if path.exists() else None
        return self.storage.atomic_write_json(path, value, replace=old is not None, expected_existing_sha256=old)

    def current(self):
        value = self.read(STORE / 'CURRENT.json')
        must(value.get('schema') == 'R25_AI_CURRENT_V1', 'ai_current_schema')
        return guard.reference(value.get('release'))

    def transaction(self, tx):
        must(type(tx) is str and re.fullmatch('[0-9a-f]{32}', tx), 'ai_transaction_id')
        return STORE / 'transactions' / tx

    def verify_candidate(self, ref):
        self.core.require_lease()
        record = guard.accepted(ref)
        for item in record['files']:
            self.identity(guard.release_folder(ref) / 'source' / item['path'],
                          expected_sha256=item['sha256'], expected_bytes=item['bytes'])
        return record

    def other_transactions_idle(self):
        if (ROOT / 'runtime/assistant-backups/assistant-daily-v1/ACTIVE.json').exists():
            backup = self.core.assistant_backup_module()
            must(backup is not None, 'assistant_backup_controller_required')
            backup.require_terminal(self.core)
        for store, schema in ((guard.core.STORE, 'R25_CORE_TRANSACTION_V1'), (STORE, 'R25_AI_TRANSACTION_V1')):
            try:
                active = guard.private_record(store / 'ACTIVE.json')
            except FileNotFoundError:
                continue
            tx = active.get('transaction_id')
            must(type(tx) is str and re.fullmatch('[0-9a-f]{32}', tx), 'other_transaction_identity')
            journal = guard.private_record(store / 'transactions' / tx / 'journal.json')
            must(journal.get('schema') == schema and journal.get('transaction_id') == tx
                 and journal.get('phase') in {'COMMITTED', 'RESTORED'}, 'unfinished_transaction_requires_recovery')

    def health(self, engine):
        # The already validated lifecycle handoff selects the existing token;
        # never accept a candidate-controlled credential path or emit its value.
        token_path = engine.v['R25_INTERNAL_TOKEN_FILE']
        must(token_path == str(ROOT / 'runtime/config/internal-token'), 'ai_fixed_token_path')
        token = guard.read_file(token_path, limit=256).decode().strip()
        must(re.fullmatch('[0-9a-f]{72}', token), 'ai_internal_token_format')
        result = validate_health(get_json(19084, '/health'), get_json(19085, '/health'),
                                 get_json(19085, '/api/v1/readiness', token=token))
        get_json(19085, '/api/v1/readiness', expected_status=401)
        get_json(19084, '/v1/guide/generate', expected_status=401)
        for name, port in PORTS.items():
            process = engine.active(name, port)
            must(process is not None, 'ai_owned_process_missing')
            result[name + '_pid'] = process['pid']
            result[name + '_start_ticks'] = process['ticks']
        return result

    def load(self, tx):
        journal = self.read(self.transaction(tx) / 'journal.json')
        must(journal.get('schema') == 'R25_AI_TRANSACTION_V1' and journal.get('transaction_id') == tx
             and journal.get('phase') in PHASES, 'ai_journal_schema')
        snapshot = self.read(self.transaction(tx) / 'snapshot.json', journal['snapshot_sha256'])
        must(snapshot.get('schema') == 'R25_AI_SNAPSHOT_V1' and snapshot.get('transaction_id') == tx
             and snapshot.get('current') == journal.get('current') and snapshot.get('candidate') == journal.get('candidate'),
             'ai_snapshot_binding')
        return journal, snapshot

    def record(self, tx, phase):
        self.core.require_lease()
        must(phase in PHASES, 'ai_phase')
        journal, _ = self.load(tx)
        journal['phase'] = phase
        journal['history'].append({'phase': phase, 'at_unix': int(time.time())})
        must(len(journal['history']) <= 200, 'ai_history_limit')
        self.write(self.transaction(tx) / 'journal.json', journal)

    def prepare(self, candidate):
        self.core.require_lease()
        self.other_transactions_idle()
        before_current_sha = self.identity(STORE / 'CURRENT.json')['sha256']
        before_current = self.read(STORE / 'CURRENT.json', before_current_sha)
        must(before_current.get('schema') == 'R25_AI_CURRENT_V1', 'ai_current_schema')
        current = guard.reference(before_current.get('release'))
        before = self.verify_candidate(current)
        after = self.verify_candidate(candidate)
        guard.verify_live(current)
        paired_core = self.core.current()
        self.core.verify_current(paired_core)
        engine = self.core.engine()
        health = self.health(engine)
        self.core.require_no_active_work()
        old = {item['path']: item for item in before['files']}
        new = {item['path']: item for item in after['files']}
        must(set(old) <= set(new) and set(new) in (set(guard.SOURCE_PATHS),set(guard.ASSISTANT_PATHS)), 'ai_inventory_transition')
        files = {name: {'before':old.get(name),'after':new[name]} for name in sorted(new)}
        new_directory = ROOT / 'release/critic-service/app/assistant'
        added = set(new)-set(old)
        if added:
            must(added == set(guard.ASSISTANT_PATHS)-set(guard.SOURCE_PATHS) and not new_directory.exists() and not new_directory.is_symlink(), 'ai_new_directory_must_be_absent')
        changed = sorted({role(name) for name, value in files.items() if value['before'] != value['after']})
        must(shutil.disk_usage(STORE).free > 64 * 1024 * 1024 + sum(x['before']['bytes'] for x in files.values() if x['before'] is not None) * 3,
             'ai_snapshot_disk_space')
        tx = secrets.token_hex(16)
        folder = self.transaction(tx)
        self.storage.mkdir_private(folder)
        self.storage.mkdir_private(folder / 'before')
        for name, value in files.items():
            if value['before'] is None:
                continue
            destination = folder / 'before' / name
            self.make_parents(destination.parent, folder / 'before')
            self.storage.atomic_copy_file(ROOT / 'release' / name, destination, value['before']['sha256'],
                                          source_owner=guard.source_owner(), expected_bytes=value['before']['bytes'])
        document = {'schema': 'R25_AI_SNAPSHOT_V1', 'transaction_id': tx, 'current': current, 'candidate': candidate,
                    'core': asdict(paired_core), 'before_current': before_current,
                    'minimum_total': self.core.last_http['gallery_total'], 'files': files, 'changed_roles': changed,
                    'before_health': health, 'created_directories': ['critic-service/app/assistant'] if added else [], 'source_owner':list(guard.source_owner())}
        self.identity(STORE / 'CURRENT.json', expected_sha256=before_current_sha)
        self.storage.atomic_write_json(folder / 'snapshot.json', document)
        self.storage.atomic_write_json(folder / 'journal.json', {'schema': 'R25_AI_TRANSACTION_V1',
            'transaction_id': tx, 'current': current, 'candidate': candidate, 'phase': 'PREPARED', 'history': [],
            'snapshot_sha256': self.identity(folder / 'snapshot.json')['sha256']})
        self.write(STORE / 'ACTIVE.json', {'schema': 'R25_AI_ACTIVE_V1', 'transaction_id': tx})
        return tx

    def make_parents(self, folder, base):
        must(folder.is_relative_to(base), 'ai_private_parent')
        for parent in reversed((folder, *folder.parents)):
            if parent == base or parent.is_relative_to(base):
                self.storage.mkdir_private(parent)

    def validate_recovery(self, tx):
        self.core.require_lease()
        journal, snapshot = self.load(tx)
        must(self.read(STORE / 'ACTIVE.json').get('transaction_id') == tx, 'ai_not_active_transaction')
        must(self.current() in (snapshot['current'], snapshot['candidate']), 'ai_current_drift')
        must(asdict(self.core.current()) == snapshot['core'], 'paired_core_changed')
        before = self.verify_candidate(snapshot['current'])
        after = self.verify_candidate(snapshot['candidate'])
        old={x['path']:x for x in before['files']}; new={x['path']:x for x in after['files']}
        must(set(old)<=set(new) and set(snapshot['files']) == set(new), 'ai_snapshot_inventory')
        expected={name:{'before':old.get(name),'after':new[name]} for name in sorted(new)}
        must(snapshot.get('source_owner',list(guard.source_owner())) == list(guard.source_owner()), 'ai_source_owner_drift')
        must(snapshot.get('created_directories',[]) == (['critic-service/app/assistant'] if set(new)-set(old) else []), 'ai_created_directory_binding')
        must(snapshot['files'] == expected, 'ai_snapshot_source_records')
        must(snapshot['changed_roles'] == sorted({role(p) for p, v in expected.items() if v['before'] != v['after']}),
             'ai_snapshot_roles')
        for path, value in expected.items():
            if value['before'] is not None:
                self.identity(self.transaction(tx) / 'before' / path, expected_sha256=value['before']['sha256'])
            target=ROOT/'release'/path
            if value['before'] is None and not target.exists():
                must(not target.is_symlink(),'ai_foreign_source_drift')
                continue
            actual=self.identity(target, expected_owner=guard.source_owner())
            allowed={value['after']['sha256']} | ({value['before']['sha256']} if value['before'] is not None else set())
            must(actual['sha256'] in allowed,'ai_foreign_source_drift')
        return journal, snapshot

    def partial_engine(self):
        engine = self.core.engine(partial_recovery=True)
        # partial Core recovery intentionally skips load(); AI PID validation
        # also needs the exact execution policy before an owned Critic stop.
        engine.load_execution_policy()
        return engine

    def quiesce(self, tx, *, recovering=False):
        _, snapshot = self.validate_recovery(tx)
        engine = self.partial_engine() if recovering else self.core.engine()
        engine.watchdog_stop_locked()
        engine.stop_role('java', 19080)
        self.core.require_no_active_work()
        # Unchanged services must retain the original owned PID/ticks.
        for name, port in PORTS.items():
            if name not in snapshot['changed_roles']:
                process = engine.active(name, port)
                must(process and process['pid'] == snapshot['before_health'][name + '_pid']
                     and process['ticks'] == snapshot['before_health'][name + '_start_ticks'], 'unchanged_ai_process_drift')
        return engine

    def stop_changed(self, tx, engine):
        _, snapshot = self.validate_recovery(tx)
        for name in snapshot['changed_roles']:
            engine.stop_role(name, PORTS[name])

    def copy_source(self, tx, *, restore=False):
        _, snapshot = self.validate_recovery(tx)
        owner=tuple(snapshot.get('source_owner',guard.source_owner()))
        for name in snapshot.get('created_directories',[]):
            target=ROOT/'release'/name
            if not restore:
                self.storage.mkdir_private(target,target_owner=owner)
        for name, value in snapshot['files'].items():
            if value['before'] == value['after']:
                continue
            target = ROOT / 'release' / name
            actual = self.identity(target, expected_owner=owner)['sha256'] if target.exists() else None
            if restore and value['before'] is None:
                if actual is not None:
                    self.storage.remove_bound_file(target,value['after']['sha256'],expected_owner=owner)
                continue
            item = value['before' if restore else 'after']
            source = self.transaction(tx) / 'before' / name if restore else guard.release_folder(snapshot['candidate']) / 'source' / name
            self.storage.atomic_copy_file(source, target, item['sha256'], expected_bytes=item['bytes'],
                target_owner=owner, replace=actual is not None, expected_existing_sha256=actual, existing_owner=owner)
        if restore:
            for name in reversed(snapshot.get('created_directories',[])):
                target=ROOT/'release'/name
                if target.exists():
                    self.storage.remove_empty_directory(target,expected_owner=owner)

    def start_changed(self, tx, *, restoring=False):
        _, snapshot = self.validate_recovery(tx)
        ref = snapshot['current' if restoring else 'candidate']
        guard.verify_live(ref)
        engine = self.core.engine()
        for name in snapshot['changed_roles']:
            if name == 'critic':
                engine.start_critic_locked()
            else:
                token = guard.read_file(engine.v['R25_INTERNAL_TOKEN_FILE'], limit=256).decode().strip()
                must(re.fullmatch('[0-9a-f]{72}', token), 'guide_token_format')
                environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(ROOT / 'runtime/home'),
                    'PYTHONPATH': str(ROOT / 'release'), 'AURALINK_ENV_FILE': engine.v['R25_PROVIDER_ENV'],
                    'AURALINK_GUIDE_SERVICE_HOST': '127.0.0.1', 'AURALINK_GUIDE_SERVICE_PORT': '19084',
                    'GUIDE_AI_SERVICE_URL': 'http://127.0.0.1:19084', 'AURALINK_GUIDE_INTERNAL_TOKEN': token,
                    'AURALINK_GUIDE_DIAGNOSTIC_DIR': str(ROOT / 'evidence/guide-attempts')}
                engine.start_role('guide', 19084, [engine.v['R25_GUIDE_PY'], '-B', '-m', 'guide_service'],
                                  environment, 'http://127.0.0.1:19084/health')
        health = self.health(engine)
        must(asdict(self.core.current()) == snapshot['core'], 'paired_core_changed')
        engine.start_java_locked(self.core.fd)
        http = verify_http(self.core.query, minimum_total=snapshot['minimum_total'])
        must(engine.active('java', 19080), 'restored_core_java_identity')
        engine.frontend('status', self.core.fd)
        engine.tunnel.status()
        engine.watchdog_start_locked()
        must(engine.watchdog_identity(), 'restored_watchdog_identity')
        self.write(self.transaction(tx) / ('restore-receipt.json' if restoring else 'acceptance.json'),
                   {'schema': 'R25_AI_HTTP_ACCEPTANCE_V1', 'ai': health, 'core': http, 'paired_core': snapshot['core'],
                    'source_tree_sha256': ref['source_tree_sha256'], 'provider_calls': 0})

    def commit(self, tx, *, restore=False):
        _, snapshot = self.validate_recovery(tx)
        target = snapshot['current' if restore else 'candidate']
        guard.verify_live(target)
        path = STORE / 'CURRENT.json'
        observed_sha = self.identity(path)['sha256']
        observed = self.read(path, observed_sha)
        allowed = (snapshot['current'], snapshot['candidate']) if restore else (snapshot['current'],)
        must(observed.get('schema') == 'R25_AI_CURRENT_V1' and observed.get('release') in allowed,
             'ai_current_compare_and_swap')
        value = snapshot['before_current'] if restore else {'schema': 'R25_AI_CURRENT_V1', 'release': target,
                                                           'previous': snapshot['current'], 'transaction_id': tx}
        self.storage.atomic_write_json(path, value, replace=True, expected_existing_sha256=observed_sha)

    def verify_restored_operational(self, snapshot):
        must(self.current() == snapshot['current'], 'ai_restored_current_binding')
        guard.verify_live(snapshot['current'])
        self.core.verify_current(Release(**snapshot['core']))
        engine = self.core.engine()
        self.health(engine)
        verify_http(self.core.query, minimum_total=snapshot['minimum_total'])
        must(engine.watchdog_identity(), 'restored_watchdog_not_running')


def recover_locked(rt, tx):
    journal, snapshot = rt.validate_recovery(tx)
    if journal['phase'] == 'RESTORED':
        rt.verify_restored_operational(snapshot)
        return
    if journal['phase'] == 'PREPARED':
        # Nothing was stopped or replaced. Abort this durable preparation only
        # after proving all live source and CURRENT remain the prior version.
        must(rt.current() == snapshot['current'], 'prepared_current_changed')
        rt.verify_restored_operational(snapshot)
        rt.record(tx, 'RESTORED')
        return
    rt.record(tx, 'RESTORE_STOP_INTENT')
    engine = rt.quiesce(tx, recovering=True)
    rt.stop_changed(tx, engine)
    rt.record(tx, 'RESTORE_STOPPED')
    rt.record(tx, 'RESTORE_INTENT')
    rt.copy_source(tx, restore=True)
    rt.record(tx, 'RESTORE_START_INTENT')
    rt.start_changed(tx, restoring=True)
    rt.commit(tx, restore=True)
    rt.record(tx, 'RESTORED')


def publish(rt, candidate):
    with rt.core.lease():
        tx = rt.prepare(candidate)
        try:
            _, snapshot = rt.load(tx)
            if snapshot['changed_roles']:
                rt.record(tx, 'QUIESCE_INTENT')
                engine = rt.quiesce(tx)
                rt.record(tx, 'QUIESCED')
                rt.record(tx, 'STOP_INTENT')
                rt.stop_changed(tx, engine)
                rt.record(tx, 'STOPPED')
                rt.record(tx, 'INSTALL_INTENT')
                rt.copy_source(tx)
                rt.record(tx, 'INSTALLED')
                rt.record(tx, 'START_INTENT')
                rt.start_changed(tx)
            else:
                # Exact byte identity is a provenance registration, explicitly
                # distinguishable from a real service restart/source upgrade.
                rt.record(tx, 'START_INTENT')
                rt.verify_restored_operational(snapshot)
            rt.record(tx, 'ACCEPTED')
            rt.record(tx, 'CURRENT_COMMIT_INTENT')
            rt.commit(tx)
            rt.record(tx, 'COMMITTED')
            return {'outcome': 'AI_SOURCE_PUBLISHED' if snapshot['changed_roles'] else 'AI_IDENTICAL_SOURCE_REGISTERED',
                    'transaction_id': tx, 'changed_roles': snapshot['changed_roles'], 'release': candidate}
        except BaseException as error:
            recovered = False
            try:
                rt.record(tx, 'RECOVERY_REQUIRED')
                recover_locked(rt, tx)
                recovered = True
            except BaseException as recovery_error:
                recovery_failure = type(recovery_error).__name__
                try:
                    rt.record(tx, 'RECOVERY_REQUIRED')
                except BaseException:
                    pass
            # Do not forward provider/config/error text into public CI logs.
            return {'outcome': 'AI_PUBLICATION_FAILED', 'transaction_id': tx,
                    'restored': recovered, 'failure_class': type(error).__name__,
                    'recovery_failure_class': None if recovered else recovery_failure}
