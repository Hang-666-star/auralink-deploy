#!/usr/bin/env python3
"""Bind an R25 build to its release commit; this grants no production authority.

The report is the existing packaged-artifact check, not PostgreSQL/HTTP
acceptance. This helper neither invokes nor rewrites the production writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

SCHEMA = "AURALINK_CORE_RELEASE_CANDIDATE_V1"
REPOSITORY = "Hang-666-star/auralink-core-api"
JAR_NAME = "auralink-backend-0.0.1-SNAPSHOT.jar"
REPORT_NAME = "r25-artifact-verification.json"
SCOPE = "packaged resource and bytecode contracts; not an HTTP/PG acceptance claim"
KEYS = {"schema", "repository", "ref", "commit_sha", "github_run_id",
        "github_run_attempt", "artifact", "verification", "production_approved"}


class Refused(ValueError):
    pass


def must(condition, reason):
    if not condition:
        raise Refused(reason)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            must(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def nonfinite(_):
        raise Refused("nonfinite_json")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Refused("invalid_json") from error
    must(type(value) is dict, "json_object_required")
    return value


def regular(path):
    path = Path(path).absolute()
    must(".." not in path.parts, "unsafe_path")
    must(not any(item.is_symlink() for item in (path, *path.parents)), "symlink_path")
    must(path.is_file(), "regular_file_required")
    return path


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_object(path):
    path = regular(path)
    must(path.stat().st_size <= 1024 * 1024, "json_size_limit")
    return strict_json(path.read_bytes())


def packaged_verifier():
    # Deploy's installed private bundle uses source bytes, not reusable .pyc.
    # The Core CI copy remains standalone; this server copy requires its guard.
    from core_release_guard import read_file, source_module
    path = regular(Path(__file__).with_name("verify-r25-artifact.py"))
    return source_module(path, 'core_packaged_contract', read_file(path))


def verified_inputs(jar, report):
    jar, report = regular(jar), regular(report)
    must(jar.name == JAR_NAME and report.name == REPORT_NAME, "artifact_filename")
    expected = packaged_verifier().verify(jar)
    observed = read_object(report)
    must(observed == expected, "verification_report_mismatch")
    must(observed.get("status") == "PASS" and observed.get("scope") == SCOPE,
         "verification_scope")
    return {
        "name": JAR_NAME, "sha256": expected["jar_sha256"],
        "bytes": expected["jar_bytes"],
    }, {"name": REPORT_NAME, "sha256": digest(report), "scope": SCOPE}


def create(jar, report, repository, ref, commit, run_id, attempt):
    must(repository == REPOSITORY, "repository_binding")
    must(ref == "refs/heads/release", "release_ref_required")
    must(re.fullmatch(r"[0-9a-f]{40}", commit or "") is not None, "commit_identity")
    for value in (run_id, attempt):
        must(type(value) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None,
             "github_run_identity")
    artifact, verification = verified_inputs(jar, report)
    return {"schema": SCHEMA, "repository": repository, "ref": ref,
            "commit_sha": commit, "github_run_id": run_id,
            "github_run_attempt": attempt, "artifact": artifact,
            "verification": verification, "production_approved": False}


def verify(manifest, jar, report, expected_commit, expected_run_id, expected_run_attempt):
    document = read_object(manifest)
    must(set(document) == KEYS and document.get("schema") == SCHEMA,
         "candidate_schema")
    must(document.get("production_approved") is False, "not_a_production_contract")
    must((document.get("commit_sha"), document.get("github_run_id"), document.get("github_run_attempt")) ==
         (expected_commit, expected_run_id, expected_run_attempt), "expected_workflow_identity_mismatch")
    expected = create(jar, report, document["repository"], document["ref"],
                      document["commit_sha"], document["github_run_id"],
                      document["github_run_attempt"])
    must(document == expected, "candidate_content_mismatch")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    make = modes.add_parser("create")
    for name in ("repository", "ref", "commit", "run-id", "run-attempt"):
        make.add_argument("--" + name, required=True)
    make.add_argument("--output", type=Path, required=True)
    check = modes.add_parser("verify")
    check.add_argument("--manifest", type=Path, required=True)
    for name in ("expected-commit", "expected-run-id", "expected-run-attempt"):
        check.add_argument("--" + name, required=True)
    for command in (make, check):
        command.add_argument("--jar", type=Path, required=True)
        command.add_argument("--verification", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "create":
            document = create(args.jar, args.verification, args.repository, args.ref,
                              args.commit, args.run_id, args.run_attempt)
            output = args.output.absolute()
            must(".." not in output.parts and
                 not any(item.is_symlink() for item in (output, *output.parents)),
                 "unsafe_output_path")
            raw = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
            with output.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            document = verify(args.manifest, args.jar, args.verification,
                              args.expected_commit, args.expected_run_id, args.expected_run_attempt)
        print(json.dumps({"outcome": "CANDIDATE_VERIFIED", "production_approved": False,
                          "commit_sha": document["commit_sha"],
                          "artifact_sha256": document["artifact"]["sha256"]}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"outcome": "REFUSED", "reason": str(error) if
                          isinstance(error, Refused) else type(error).__name__}), file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
