#!/usr/bin/env python3
"""Trusted AI controller CLI. Independent workflow SHA/run arguments are mandatory."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import signal
import sys
import zipfile

import ai_release_candidate as candidate
import ai_release_guard as guard
from ai_runtime import AIRuntime, INCOMING, STORE, publish, recover_locked
from core_runtime import must


def incoming_path(commit, run_id, attempt):
    candidate.provenance(candidate.REPOSITORY, candidate.REF, commit, run_id, attempt)
    return INCOMING / (commit + '-' + run_id + '-' + attempt)


def prepare_incoming(rt, commit, run_id, attempt):
    folder = incoming_path(commit, run_id, attempt)
    with rt.core.lease():
        rt.storage.mkdir_private(INCOMING)
        rt.storage.mkdir_private(folder)
    return {'outcome': 'AI_INCOMING_READY', 'path': str(folder)}


def immutable_bytes(rt, path, content):
    digest = hashlib.sha256(content).hexdigest()
    if path.exists():
        return rt.identity(path, expected_sha256=digest)
    return rt.storage.atomic_write_bytes(path, content)


def stage(rt, commit, run_id, attempt):
    folder = incoming_path(commit, run_id, attempt)
    with rt.core.lease():
        rt.storage.validate_target(folder, exists=True, directory=True, expected_owner=(0, 0), expected_mode=0o700)
        raw = guard.read_file(folder / candidate.MANIFEST)
        blob = guard.read_file(folder / candidate.ARCHIVE, limit=candidate.MAX_ARCHIVE)
        manifest = candidate.strict_json(raw)
        candidate.verify(manifest, blob, commit, run_id, attempt)
        policy = guard.policy()
        must(manifest['dependency_sha256'] == policy['dependency_sha256'], 'ai_dependency_upgrade_requires_new_environment')
        ref = {'commit_sha': commit, 'source_tree_sha256': manifest['source_tree_sha256'], 'record_sha256': '0' * 64}
        target = guard.release_folder(ref)
        rt.storage.mkdir_private(target)
        rt.storage.mkdir_private(target / 'source')
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for name in guard.SOURCE_PATHS:
                path = target / 'source' / name
                rt.make_parents(path.parent, target / 'source')
                immutable_bytes(rt, path, archive.read(name))
        # Store the exact manifest and archive as immutable evidence as well.
        immutable_bytes(rt, target / 'candidate.json', raw)
        # atomic_write_bytes deliberately caps metadata at 1 MiB; stream the
        # bounded source archive through the same descriptor-safe copier.
        archive_path = target / candidate.ARCHIVE
        if archive_path.exists():
            rt.identity(archive_path, expected_sha256=manifest['archive']['sha256'])
        else:
            rt.storage.atomic_copy_file(folder / candidate.ARCHIVE, archive_path, manifest['archive']['sha256'])
        record = {'schema': 'R25_AI_ACCEPTED_SOURCE_V1', 'repository': guard.REPOSITORY,
            'commit_sha': commit, 'github_run_id': run_id, 'github_run_attempt': attempt,
            'source_tree_sha256': manifest['source_tree_sha256'], 'files': manifest['files'],
            'dependency_sha256': manifest['dependency_sha256'], 'candidate_manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'archive_sha256': manifest['archive']['sha256'], 'policy_sha256': rt.identity(STORE / 'POLICY.json')['sha256'],
            'scope': 'source integrity and unchanged dependencies; live acceptance is required before CURRENT commit'}
        record_path = target / 'record.json'
        if record_path.exists():
            previous = rt.read(record_path)
            must(all(previous.get(key) == record[key] for key in ('schema', 'repository', 'commit_sha', 'source_tree_sha256',
                'files', 'dependency_sha256', 'archive_sha256', 'policy_sha256')), 'ai_immutable_record_conflict')
        else:
            rt.storage.atomic_write_json(record_path, record)
        ref['record_sha256'] = rt.identity(record_path)['sha256']
        rt.verify_candidate(ref)
        return ref


def main(argv=None):
    def interrupted(_signum, _frame):
        raise InterruptedError('ai_publication_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare-incoming', 'stage', 'publish'):
        command = modes.add_parser(name)
        for option in ('commit', 'run-id', 'run-attempt'):
            command.add_argument('--' + option, required=True)
    for name in ('recover', 'rollback'):
        modes.add_parser(name).add_argument('--transaction', required=True)
    modes.add_parser('status')
    args = parser.parse_args(argv)
    try:
        rt = AIRuntime()
        if args.command == 'prepare-incoming':
            result = prepare_incoming(rt, args.commit, args.run_id, args.run_attempt)
        elif args.command in {'stage', 'publish'}:
            ref = stage(rt, args.commit, args.run_id, args.run_attempt)
            result = {'outcome': 'AI_CANDIDATE_STAGED', 'release': ref} if args.command == 'stage' else publish(rt, ref)
        elif args.command in {'recover', 'rollback'}:
            with rt.core.lease():
                journal, _ = rt.validate_recovery(args.transaction)
                must(args.command != 'recover' or journal['phase'] != 'COMMITTED', 'committed_use_explicit_rollback')
                must(args.command != 'rollback' or journal['phase'] in {'COMMITTED', 'RESTORED'}, 'incomplete_use_recover')
                try:
                    recover_locked(rt, args.transaction)
                except BaseException:
                    rt.record(args.transaction, 'RECOVERY_REQUIRED')
                    raise
            result = {'outcome': 'AI_RESTORED', 'transaction_id': args.transaction}
        else:
            with rt.core.lease():
                ref = rt.current()
                guard.verify_live(ref)
                rt.core.verify_current(rt.core.current())
                rt.health(rt.core.engine())
                result = {'outcome': 'AI_CURRENT_VERIFIED', 'release': ref}
        print(json.dumps(result, sort_keys=True))
        return 70 if result['outcome'] == 'AI_PUBLICATION_FAILED' else 0
    except Exception as error:
        print(json.dumps({'outcome': 'AI_REFUSED', 'failure_class': type(error).__name__}), file=sys.stderr)
        return 65


if __name__ == '__main__':
    raise SystemExit(main())
