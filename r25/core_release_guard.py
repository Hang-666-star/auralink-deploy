"""Independent R25 normal-release start guard. No CLI, SQL writes or secrets output.

Version 1 permits repackaging the reviewed production application, with exactly
the same executable payload. A code/dependency/profile change requires a new
reviewed acceptance contract; a self-declared capability never grants access.
The original migration guard remains unchanged and is invoked only after this
independent equivalence proof, with its established 60c5 capability baseline.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path('/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z')
PREVIEW = Path('/root/autodl-tmp/artlive/backend-preview/r25-isolated-preview-7694f4069c83c06c')
BASELINE = '60c5b95529e027ec2cd3634cc6fe190fe43b42c48eb402e2d9ba0f1ce7caaecb'
BASELINE_COMMIT = '98af96843760f7a44627a7284cdb9ffccaf02aa2'
LEGACY_GUARD_SHA = 'f746354860fa422abffec67514791f08732aeb660145a6e7a66e7481f4bfe6f3'
STORE = ROOT / 'runtime/core-publications'
REPOSITORY = 'Hang-666-star/auralink-core-api'
POLICY_SCHEMA = 'R25_CORE_EQUIVALENT_PAYLOAD_POLICY_V1'
RECORD_SCHEMA = 'R25_CORE_COMPATIBLE_RELEASE_V1'
START_PHASES = {'START_INTENT', 'ACCEPTED', 'CURRENT_COMMIT_INTENT', 'COMMITTED',
                'RESTORE_INTENT', 'RESTORED'}


class Refused(RuntimeError):
    pass


def must(ok, reason):
    if not ok:
        raise Refused(reason)


def digest_value(value, size=64):
    must(type(value) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', value), 'digest_format')
    return value


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            must(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def invalid(_):
        raise Refused('nonfinite_json')
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    must(type(result) is dict, 'record_object')
    return result


def read_file(path, *, owner=(0, 0), mode=0o600, limit=1024 * 1024, expected=None):
    """Traverse every parent by descriptor; never follow a last-component link."""
    path = Path(path)
    must(path.is_absolute() and '..' not in path.parts, 'absolute_fixed_path')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        target = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            before = os.fstat(target)
            must(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                 (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode)) == (*owner, mode), 'file_identity')
            must(before.st_size <= limit, 'file_size_limit')
            chunks, size = [], 0
            while True:
                chunk = os.read(target, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                must(size <= limit, 'file_size_limit')
            after = os.fstat(target)
            must((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                 (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'file_changed')
            raw = b''.join(chunks)
            must(len(raw) == before.st_size, 'file_changed')
            if expected is not None:
                must(hashlib.sha256(raw).hexdigest() == digest_value(expected), 'file_digest')
            return raw
        finally:
            os.close(target)
    finally:
        os.close(descriptor)


def private_record(path, expected=None):
    return strict_json(read_file(path, expected=expected))


def payload_fingerprint(path):
    """Hash every executable/resource/dependency entry, independently of ZIP time.

    Only Maven's descriptive pom.properties/pom.xml and top manifest build
    labels may vary; all effective launcher attributes are included. Extra
    executable entries, class changes and library changes change this digest.
    """
    entries = {}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        must(len(infos) < 50000 and len({x.filename for x in infos}) == len(infos), 'jar_duplicate_or_excess_entries')
        total = 0
        for info in infos:
            name = info.filename
            must(not name.startswith('/') and '\\' not in name and '..' not in name.split('/'), 'jar_entry_path')
            if info.is_dir():
                continue
            must(info.file_size <= 128 * 1024 * 1024, 'jar_entry_size')
            total += info.file_size
            must(total <= 512 * 1024 * 1024, 'jar_expansion_limit')
            raw = archive.read(info)
            if name == 'META-INF/MANIFEST.MF':
                attributes = {}
                unfolded = raw.decode('utf-8').replace('\r\n ', '').replace('\n ', '')
                for line in unfolded.splitlines():
                    if not line:
                        continue
                    must(': ' in line, 'jar_manifest_syntax')
                    key, value = line.split(': ', 1)
                    must(key not in attributes, 'jar_manifest_duplicate')
                    attributes[key] = value
                # These labels have no runtime semantics; all other attributes
                # (including Main-Class, Start-Class and Class-Path) are bound.
                for key in ('Built-By', 'Build-Jdk', 'Build-Jdk-Spec', 'Created-By'):
                    attributes.pop(key, None)
                raw = encoded(attributes)
            elif name in {'META-INF/maven/com.auralink/auralink-backend/pom.properties',
                          'META-INF/maven/com.auralink/auralink-backend/pom.xml'}:
                continue
            entries[name] = hashlib.sha256(raw).hexdigest()
    must('BOOT-INF/classes/application-catalog-postgres-production.yml' in entries and
         'BOOT-INF/classes/com/auralink/Application.class' in entries,
         'jar_expected_application')
    return hashlib.sha256(encoded(entries)).hexdigest()


def policy():
    values = {}
    for line in read_file(ROOT / 'runtime/handoff-control.env').decode().splitlines():
        if not line or line.startswith('#'):
            continue
        must('=' in line, 'handoff_syntax')
        key, value = line.split('=', 1)
        must(key not in values, 'handoff_duplicate')
        values[key] = value
    result = private_record(STORE / 'POLICY.json', digest_value(values.get('R25_CORE_RELEASE_POLICY_SHA256')))
    must(result.get('schema') == POLICY_SCHEMA and result.get('baseline_sha256') == BASELINE and
         result.get('baseline_commit') == BASELINE_COMMIT and
         result.get('repository') == REPOSITORY, 'normal_policy_identity')
    digest_value(result.get('payload_fingerprint'))
    read_file(ROOT / 'runtime/config/application.yml',
              expected=digest_value(result.get('application_configuration_sha256')))
    return result


def release_record(artifact_sha, expected_record=None, commit=None):
    artifact_sha = digest_value(artifact_sha)
    commit = digest_value(commit, 40)
    record = private_record(STORE / 'releases' / (artifact_sha + '-' + commit) / 'record.json', expected_record)
    expected = policy()
    must(record.get('schema') == RECORD_SCHEMA and record.get('repository') == REPOSITORY and
         record.get('artifact_sha256') == artifact_sha and
         record.get('payload_fingerprint') == expected['payload_fingerprint'] and
         record.get('policy_sha256') == hashlib.sha256(read_file(STORE / 'POLICY.json')).hexdigest(),
         'release_capability_binding')
    must(record.get('commit_sha') == commit, 'release_record_commit')
    must(type(record.get('artifact_bytes')) is int and 0 < record['artifact_bytes'] < 512 * 1024 * 1024,
         'release_artifact_size')
    return record


def validate_backend_identity(root, backend):
    must(Path(root) == ROOT, 'fixed_root')
    digest_value(backend)
    current = private_record(STORE / 'CURRENT.json')
    reference = current.get('release')
    if not isinstance(reference, dict) or reference.get('artifact_sha256') != backend:
        active = private_record(STORE / 'ACTIVE.json')
        transaction_id = active.get('transaction_id')
        must(type(transaction_id) is str and re.fullmatch('[0-9a-f]{32}', transaction_id), 'active_transaction')
        journal = private_record(STORE / 'transactions' / transaction_id / 'journal.json')
        must(journal.get('phase') in START_PHASES and journal.get('transaction_id') == transaction_id,
             'active_start_phase')
        reference = journal.get('current') if journal['phase'].startswith('RESTORE') else journal.get('candidate')
        must(isinstance(reference, dict) and reference.get('artifact_sha256') == backend, 'active_release_binding')
        must(current.get('release') in (journal.get('current'), journal.get('candidate')), 'active_current_binding')
    record = release_record(backend, digest_value(reference.get('accepted_record_sha256')), reference.get('commit_sha'))
    must(record['commit_sha'] == reference.get('commit_sha'), 'release_commit_binding')
    return record


class Guard:
    def __init__(self, legacy):
        self.legacy = legacy
        self.lock = legacy.lock

    def is_registered_backend(self, backend):
        digest_value(backend)
        try:
            validate_backend_identity(ROOT, backend)
        except FileNotFoundError:
            return False
        return True

    def require_backend_eligible(self, backend, fd):
        record = validate_backend_identity(ROOT, backend)
        for path in (ROOT / 'release/artifacts/backend.jar', PREVIEW / 'release/backend.jar'):
            # No candidate-controlled import occurs: JAR is only parsed.
            raw = read_file(path, limit=512 * 1024 * 1024, expected=backend)
            must(len(raw) == record['artifact_bytes'], 'live_artifact_size')
            must(payload_fingerprint(path) == record['payload_fingerprint'], 'live_capability_payload')
        # This maps an independently verified byte-equivalent capability to the
        # original guard, preserving its authoritative PG/retention/media test.
        return self.legacy.require_backend_eligible(BASELINE, fd)


def source_module(path, name, raw):
    """Execute only the already verified source bytes, never a .pyc cache."""
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    module.__r25_source_sha256__ = hashlib.sha256(raw).hexdigest()
    return module


def reject_legacy_bytecode(path):
    """The unchanged legacy PG loader must have no reusable bytecode cache.

    This is a prerequisite check only; never delete production cache files.
    """
    path = Path(path)
    candidates = {path.with_suffix('.pyc'), path.with_suffix('.pyo')}
    cache = path.parent / '__pycache__'
    must(not cache.is_symlink(), 'legacy_postgres_bytecode_cache')
    if cache.exists():
        candidates.update(cache.glob(path.stem + '.*.pyc'))
        candidates.update(cache.glob(path.stem + '.*.pyo'))
    # cache_from_source honors a configured PYTHONPYCACHEPREFIX as well.
    for optimization in ('', '1', '2'):
        candidates.add(Path(importlib.util.cache_from_source(str(path), optimization=optimization)))
    must(not any(item.exists() or item.is_symlink() for item in candidates), 'legacy_postgres_bytecode_cache')


def production():
    must(os.geteuid() == 0, 'root_operator')
    path = ROOT / 'operations/huaniao_recovery_guard.py'
    raw = read_file(path, owner=(1000, 1000), mode=0o700, expected=LEGACY_GUARD_SHA)
    reject_legacy_bytecode(ROOT / 'operations/postgres_access.py')
    module = source_module(path, 'original_r25_huaniao_guard', raw)
    previous = sys.dont_write_bytecode
    try:
        # The original PG loader is retained, but must not create a cache that
        # would cause the next guard invocation to reject this same process.
        sys.dont_write_bytecode = True
        return Guard(module.production())
    finally:
        sys.dont_write_bytecode = previous
