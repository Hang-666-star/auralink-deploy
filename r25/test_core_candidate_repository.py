"""Transport-binding tests; fixtures do not claim runnable R25 acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

import core_release_guard

SPEC = importlib.util.spec_from_file_location(
    "deploy_candidate_repository", Path(__file__).with_name("core-release-candidate.py"))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.jar, self.report = root / C.JAR_NAME, root / C.REPORT_NAME
        self.manifest = root / "core-release-candidate.json"
        self.jar.write_bytes(b"transport-only test fixture; not a Java artifact")
        self.actual = {"status": "PASS", "jar_sha256": hashlib.sha256(self.jar.read_bytes()).hexdigest(),
                       "jar_bytes": self.jar.stat().st_size, "profile_count": 11,
                       "profiles": {}, "scope": C.SCOPE}
        self.report.write_text(json.dumps(self.actual), encoding="utf-8")
        self.stub = types.SimpleNamespace(verify=lambda jar: self.actual)

    def create(self, **overrides):
        args = dict(jar=self.jar, report=self.report, repository=C.REPOSITORY,
                    ref="refs/heads/release", commit="a" * 40, run_id="123", attempt="1")
        args.update(overrides)
        return C.create(**args)

    def save_manifest(self, document):
        self.manifest.write_text(json.dumps(document), encoding="utf-8")

    def verify(self, **overrides):
        return C.verify(self.manifest, self.jar, self.report, "a" * 40, "123", "1", **overrides)

    def test_roundtrip_and_explicit_nonproduction_scope(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub) as verifier:
            document = self.create()
            self.save_manifest(document)
            self.assertEqual(self.verify(), document)
            self.assertEqual(verifier.call_count, 2)
        self.assertIs(document["production_approved"], False)
        self.assertEqual(document["repository"], "bailangguihun/auralink-core-api")

    def test_main_ref_and_fork_repository_are_refused_before_artifact_reads(self):
        for override in ({"ref": "refs/heads/main"}, {"repository": "fork/auralink-core-api"},
                         {"repository": C.HISTORICAL_REPOSITORY}):
            with self.subTest(override=override), patch.object(C, "packaged_verifier") as verifier:
                with self.assertRaises(C.Refused):
                    self.create(**override)
                verifier.assert_not_called()

    def test_historical_manifest_requires_explicit_independent_repository_and_remains_unchanged(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            document = self.create()
            # Represents an existing historical transport record, not a new
            # build permitted to claim the old repository after transfer.
            document["repository"] = C.HISTORICAL_REPOSITORY
            self.save_manifest(document)
            original = self.manifest.read_bytes()
            with self.assertRaisesRegex(C.Refused, "expected_repository_mismatch"):
                self.verify()
            self.assertEqual(self.verify(expected_repository=C.HISTORICAL_REPOSITORY), document)
            self.assertEqual(self.manifest.read_bytes(), original)

    def test_repository_mismatch_and_unknown_expected_repository_refused_before_artifact_reads(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            document = self.create()
        for declared, expected in ((C.REPOSITORY, C.HISTORICAL_REPOSITORY),
                                   (C.HISTORICAL_REPOSITORY, C.REPOSITORY),
                                   ("fork/auralink-core-api", "fork/auralink-core-api"),
                                   (C.REPOSITORY, None), (C.REPOSITORY, [])):
            self.save_manifest(dict(document, repository=declared))
            with self.subTest(declared=declared, expected=expected), patch.object(C, "packaged_verifier") as verifier:
                with self.assertRaisesRegex(C.Refused, "expected_repository_mismatch"):
                    self.verify(expected_repository=expected)
                verifier.assert_not_called()

    def test_malformed_commit_and_run_identity_refused(self):
        for override in ({"commit": "a" * 39}, {"commit": "$(uname)"}, {"run_id": "0"}, {"attempt": "1;exit"}):
            with self.subTest(override=override), self.assertRaises(C.Refused):
                self.create(**override)

    def test_stale_report_is_rejected_against_reexecuted_verifier(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            self.actual = dict(self.actual, jar_sha256="f" * 64)
            with self.assertRaisesRegex(C.Refused, "verification_report_mismatch"):
                self.create()

    def test_changed_artifact_digest_and_approval_flag_refused(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            for change in ("digest", "approval", "name"):
                document = self.create()
                if change == "digest": document["artifact"]["sha256"] = "f" * 64
                if change == "approval": document["production_approved"] = True
                if change == "name": document["artifact"]["name"] = "../../backend.jar"
                self.save_manifest(document)
                with self.subTest(change=change), self.assertRaises(C.Refused):
                    self.verify()

    def test_unknown_and_duplicate_fields_refused(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            document = self.create()
            document["extra"] = "unexpected"
            self.save_manifest(document)
            with self.assertRaises(C.Refused): self.verify()
        with self.assertRaisesRegex(C.Refused, "duplicate_json_key"):
            C.strict_json('{"schema":"one","schema":"two"}')

    def test_real_packaged_verifier_rejects_non_jar_fixture(self):
        # Repository files are not installed root:root0600 inputs; substitute
        # that file-identity read only, retaining the real packaged verifier.
        with patch.object(core_release_guard, 'read_file', side_effect=lambda p, **_: Path(p).read_bytes()), \
             self.assertRaises(zipfile.BadZipFile):
            self.create()

    def test_manifest_cannot_relabel_independently_expected_run_or_commit(self):
        with patch.object(C, "packaged_verifier", return_value=self.stub):
            for field, value in (("commit_sha", "b" * 40), ("github_run_id", "124"), ("github_run_attempt", "2")):
                document = self.create()
                document[field] = value
                self.save_manifest(document)
                with self.subTest(field=field), self.assertRaisesRegex(C.Refused, "expected_workflow_identity_mismatch"):
                    self.verify()


if __name__ == "__main__":
    unittest.main()
