#!/usr/bin/env python3
"""R25 normal Core CLI; install controller once before enabling release Actions.

All runtime paths are fixed. Incoming identity is passed independently by the
authenticated workflow; the manifest may not choose its own expected run/SHA.
No executable supplied by a candidate is imported or invoked by this program.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import signal
import sys

import core_release_guard as guard
from core_runtime import CoreRuntime, must
from publisher_transaction import Publisher, Release, PublicationFailed

INCOMING = Path('/root/autodl-tmp/auralink-core-deploy/incoming')


def incoming_path(commit, run_id, attempt):
    guard.digest_value(commit, 40)
    must(all(type(value) is str and re.fullmatch('[1-9][0-9]{0,19}', value)
             for value in (run_id, attempt)), 'github_run_identity')
    return INCOMING / (commit + '-' + run_id + '-' + attempt)


def prepare_incoming(rt, commit, run_id, attempt):
    path = incoming_path(commit, run_id, attempt)
    with rt.lease():
        rt.storage.mkdir_private(INCOMING)
        rt.storage.mkdir_private(path)
    return {'outcome': 'INCOMING_READY', 'path': str(path)}


def stage(rt, commit, run_id, attempt):
    folder = incoming_path(commit, run_id, attempt)
    with rt.lease():
        rt.storage.validate_target(folder, exists=True, directory=True,
                                   expected_owner=(0, 0), expected_mode=0o700)
        jar = folder / 'auralink-backend-0.0.1-SNAPSHOT.jar'
        report = folder / 'r25-artifact-verification.json'
        manifest = folder / 'core-release-candidate.json'
        for path in (jar, report, manifest):
            rt.identity(path)
        verifier_path = Path(__file__).with_name('core-release-candidate.py')
        verifier = guard.source_module(verifier_path, 'trusted_core_candidate', guard.read_file(verifier_path))
        candidate = verifier.verify(manifest, jar, report, commit, run_id, attempt)
        digest = candidate['artifact']['sha256']
        policy = guard.policy()
        fingerprint = guard.payload_fingerprint(jar)
        must(fingerprint == policy['payload_fingerprint'], 'executable_change_requires_new_reviewed_acceptance_contract')
        release_dir = guard.STORE / 'releases' / (digest + '-' + commit)
        rt.storage.mkdir_private(release_dir)
        target = release_dir / 'backend.jar'
        if target.exists():
            rt.identity(target, expected_sha256=digest, expected_bytes=candidate['artifact']['bytes'])
        else:
            rt.storage.atomic_copy_file(jar, target, digest, expected_bytes=candidate['artifact']['bytes'])
        document = {'schema': guard.RECORD_SCHEMA, 'repository': guard.REPOSITORY,
                    'commit_sha': commit, 'github_run_id': run_id, 'github_run_attempt': attempt,
                    'artifact_sha256': digest, 'artifact_bytes': candidate['artifact']['bytes'],
                    'candidate_manifest_sha256': rt.identity(manifest)['sha256'],
                    'policy_sha256': rt.identity(guard.STORE / 'POLICY.json')['sha256'],
                    'payload_fingerprint': fingerprint,
                    'scope': 'reviewed executable payload equivalence; live HTTP acceptance occurs before CURRENT commit'}
        record_path = release_dir / 'record.json'
        if record_path.exists():
            # A repeat workflow can submit the same independently verified
            # commit/JAR. Keep the first immutable run receipt for that pair.
            previous = rt.read(record_path)
            must(all(previous.get(key) == document[key] for key in (
                'schema', 'repository', 'commit_sha', 'artifact_sha256',
                'artifact_bytes', 'policy_sha256', 'payload_fingerprint')), 'release_record_conflict')
        else:
            rt.storage.atomic_write_json(record_path, document)
        release = Release(commit, digest, rt.identity(record_path)['sha256'])
        rt.verify_candidate(release)
        return release


def main(argv=None):
    def interrupted(_signum, _frame):
        raise InterruptedError('publication_interrupted')
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
        rt = CoreRuntime()
        if args.command == 'prepare-incoming':
            result = prepare_incoming(rt, args.commit, args.run_id, args.run_attempt)
        elif args.command in {'stage', 'publish'}:
            release = stage(rt, args.commit, args.run_id, args.run_attempt)
            result = ({'outcome': 'COMPATIBLE_CANDIDATE_STAGED', 'release': asdict(release)}
                      if args.command == 'stage' else asdict(Publisher(rt).publish(release)))
        elif args.command in {'recover', 'rollback'}:
            result = asdict(getattr(Publisher(rt), args.command)(args.transaction))
        else:
            with rt.lease():
                release = rt.current()
                rt.verify_current(release)
                result = {'outcome': 'CURRENT_VERIFIED', 'release': asdict(release)}
        print(json.dumps(result, sort_keys=True))
        return 0
    except PublicationFailed as error:
        print(json.dumps({'outcome': 'PUBLICATION_FAILED', 'transaction_id': error.transaction_id,
                          'restored': error.recovered, 'primary_failure': error.primary_failure,
                          'recovery_failure': error.recovery_failure}, sort_keys=True), file=sys.stderr)
        return 70
    except Exception as error:
        # Existing diagnostics remain private on-host. SQL/config/provider
        # exception text must not enter public Actions logs.
        print(json.dumps({'outcome': 'REFUSED', 'failure_class': type(error).__name__}), file=sys.stderr)
        return 65


if __name__ == '__main__':
    raise SystemExit(main())
