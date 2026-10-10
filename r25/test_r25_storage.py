"""Pure checks run everywhere; filesystem/durability fixtures require Linux.

These tests do not invoke R25 services, SSH, databases, or production paths.
A skipped Linux fixture is not evidence of onsite syscall acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from r25_storage import (R25Storage, StorageRefused, RECORD_LIMIT, linux_absolute,
                         mode_value, owner_value, sha256_value, strict_json)


class PureValidationTests(unittest.TestCase):
    def test_duplicate_keys_rejected_at_every_depth(self):
        for raw in ('{"a":1,"a":2}', '{"a":{"b":1,"b":2}}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(StorageRefused, "duplicate"):
                strict_json(raw)

    def test_nonfinite_json_including_overflow_rejected(self):
        for raw in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
                    '{"x":1e309}', '{"x":[1e309]}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(StorageRefused, "nonfinite"):
                strict_json(raw)

    def test_object_encoding_depth_and_size_policy(self):
        self.assertEqual(strict_json(b'{"ok":true,"value":1.5}'), {"ok": True, "value": 1.5})
        for raw in (b"[]", b"1", b"null", b'{"a":"\xff"}', b"{" + b" " * RECORD_LIMIT):
            with self.subTest(raw_type=type(raw)), self.assertRaises(StorageRefused):
                strict_json(raw)
        with self.assertRaises(StorageRefused):
            strict_json('{"x":' + "[" * 130 + "1" + "]" * 130 + "}")

    def test_linux_absolute_path_rejects_traversal_and_other_platforms(self):
        for raw in ("relative/file", "C:/root/file", "/", "//root/file",
                    "/root/../file", "/root/./file", "/root//file", "/root/file/",
                    "/root/file\n", "/root/back\\slash", "/root/file\0"):
            with self.subTest(raw=raw), self.assertRaises(StorageRefused):
                linux_absolute(raw)
        self.assertEqual(str(linux_absolute("/root/private/record.json")),
                         "/root/private/record.json")

    def test_allowed_root_boundary_and_private_root_scope(self):
        store = R25Storage(["/root/private"])
        self.assertEqual(str(store._target("/root/private/record.json")),
                         "/root/private/record.json")
        for path in ("/root/private-other/record.json", "/root/record.json",
                     "/root/private/../record.json"):
            with self.subTest(path=path), self.assertRaises(StorageRefused):
                store._target(path)
        for roots in ([], ["/root/a", "/root/a"]):
            with self.assertRaises(StorageRefused):
                R25Storage(roots)
        with self.assertRaises(StorageRefused):
            R25Storage(["/root/a"], private_roots=["/root/b"])

    def test_exact_owner_mode_and_digest_types(self):
        self.assertEqual(owner_value((1000, 1000)), (1000, 1000))
        self.assertEqual(mode_value(0o700), 0o700)
        self.assertEqual(sha256_value("a" * 64), "a" * 64)
        for owner in ((True, 0), (-1, 0), [0, 0], (0,)):
            with self.assertRaises(StorageRefused):
                owner_value(owner)
        for mode in (0o644, 0o755, True, "0o600"):
            with self.assertRaises(StorageRefused):
                mode_value(mode)
        for digest in ("a" * 63, "A" * 64, "$(id)", None):
            with self.assertRaises(StorageRefused):
                sha256_value(digest)

    def test_windows_io_is_refused_before_open(self):
        store = R25Storage(["/root/private"])
        with patch("r25_storage.sys.platform", "win32"), patch("r25_storage.os.open") as opened:
            with self.assertRaisesRegex(StorageRefused, "linux_storage_required"):
                store.validate_target("/root/private/record.json")
            opened.assert_not_called()

    def test_json_writer_rejects_nonfinite_before_filesystem(self):
        store = R25Storage(["/root/private"])
        with patch("r25_storage.os.open") as opened:
            for value in (float("nan"), float("inf")):
                with self.assertRaises(StorageRefused):
                    store.atomic_write_json("/root/private/record.json", {"value": value})
            opened.assert_not_called()

    def test_raw_bytes_writer_rejects_type_and_size_before_filesystem(self):
        store = R25Storage(["/root/private"])
        with patch("r25_storage.os.open") as opened:
            for raw in ("KEY=value", None, b"x" * (RECORD_LIMIT + 1)):
                with self.assertRaises(StorageRefused):
                    store.atomic_write_bytes("/root/private/handoff.env", raw)
            opened.assert_not_called()


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux fd/ownership/fsync fixtures; not run on Windows")
class LinuxStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="r25-storage-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.owner = (os.geteuid(), os.getegid())
        self.store = R25Storage([str(self.root)], owner_uid=self.owner[0], owner_gid=self.owner[1])

    def file(self, name, data=b"fixture", mode=0o600):
        path = self.root / name
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def test_atomic_json_roundtrip_and_exact_identity(self):
        target = self.root / "record.json"
        identity = self.store.atomic_write_json(target, {"schema": "FIXTURE", "ok": True})
        self.assertEqual(self.store.read_private_record(target, identity["sha256"]),
                         {"schema": "FIXTURE", "ok": True})
        self.assertEqual(self.store.file_identity(target), identity)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_atomic_raw_bytes_preserve_opaque_private_content(self):
        target = self.root / "handoff.env"
        raw = b"FIXTURE_KEY=not-a-real-secret\nOPAQUE_BYTES=\\xff\n"
        identity = self.store.atomic_write_bytes(target, raw)
        self.assertEqual(target.read_bytes(), raw)
        self.assertEqual(identity, self.store.file_identity(target))

    def test_immutable_and_unknown_target_are_never_overwritten(self):
        target = self.file("record.json", b'{"old":true}')
        original = target.read_bytes()
        with self.assertRaisesRegex(StorageRefused, "target_already_exists"):
            self.store.atomic_write_json(target, {"new": True})
        self.assertEqual(target.read_bytes(), original)
        with self.assertRaisesRegex(StorageRefused, "replacement_digest_required"):
            self.store.atomic_write_json(target, {"new": True}, replace=True)
        self.assertEqual(target.read_bytes(), original)

    def test_guarded_replace_and_wrong_expected_digest(self):
        target = self.file("record.json", b'{"old":true}')
        old_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        with self.assertRaisesRegex(StorageRefused, "existing_sha256_mismatch"):
            self.store.atomic_write_json(target, {"new": True}, replace=True,
                                         expected_existing_sha256="a" * 64)
        with patch("r25_storage.os.replace", wraps=os.replace) as replaced:
            identity = self.store.atomic_write_json(target, {"new": True}, replace=True,
                                                    expected_existing_sha256=old_digest)
            self.assertEqual(replaced.call_count, 1)
        self.assertEqual(self.store.read_private_record(target, identity["sha256"]), {"new": True})

    def test_copy_hash_size_and_byte_integrity(self):
        data = bytes(range(256)) * 1000
        source = self.file("incoming.jar", data)
        target = self.root / "installed.jar"
        digest = hashlib.sha256(data).hexdigest()
        identity = self.store.atomic_copy_file(source, target, digest, expected_bytes=len(data))
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(identity, self.store.file_identity(target, digest, len(data)))
        with self.assertRaisesRegex(StorageRefused, "source_equals_target"):
            self.store.atomic_copy_file(source, source, digest)

    def test_failed_copy_keeps_evidence_and_does_not_touch_unknown_temp(self):
        source = self.file("incoming.jar", b"actual")
        unknown = self.file(".r25-write-unknown.tmp", b"do not delete")
        target = self.root / "installed.jar"
        with self.assertRaisesRegex(StorageRefused, "copy_sha256_mismatch"):
            self.store.atomic_copy_file(source, target, "a" * 64)
        self.assertFalse(target.exists())
        self.assertEqual(unknown.read_bytes(), b"do not delete")
        self.assertGreaterEqual(len(list(self.root.glob(".r25-write-*.tmp"))), 2)

    def test_temp_collision_preserves_unknown_file(self):
        unknown = self.file(".r25-write-collision.tmp", b"do not delete")
        with patch("r25_storage.secrets.token_hex", return_value="collision"):
            with self.assertRaises(StorageRefused):
                self.store.atomic_write_json(self.root / "record.json", {"ok": True})
        self.assertEqual(unknown.read_bytes(), b"do not delete")
        self.assertFalse((self.root / "record.json").exists())

    def test_final_symlink_ancestor_symlink_and_fifo_are_refused(self):
        outside = self.file("outside.json", b'{"private":true}')
        leaf = self.root / "leaf.json"
        leaf.symlink_to(outside)
        with self.assertRaises(StorageRefused):
            self.store.read_private_record(leaf)
        ancestor = self.root / "linked"
        ancestor.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(StorageRefused):
            self.store.read_private_record(ancestor / "outside.json")
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        with self.assertRaisesRegex(StorageRefused, "regular_file_required"):
            self.store.file_identity(fifo)
        self.assertEqual(outside.read_bytes(), b'{"private":true}')

    def test_owner_mode_private_root_and_size_rejections(self):
        target = self.file("record.json", b'{"ok":true}', mode=0o644)
        with self.assertRaisesRegex(StorageRefused, "file_mode"):
            self.store.read_private_record(target)
        target.chmod(0o600)
        with self.assertRaisesRegex(StorageRefused, "file_owner"):
            self.store.file_identity(target, expected_owner=(self.owner[0] + 1, self.owner[1]))
        oversized = self.file("large.json", b"x" * (RECORD_LIMIT + 1))
        with self.assertRaisesRegex(StorageRefused, "file_size_limit"):
            self.store.read_private_record(oversized)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(StorageRefused, "directory_mode"):
            self.store.read_private_record(target)

    def test_legacy_755_parent_and_explicit_private_executable_identity(self):
        legacy = self.root / "operations"
        legacy.mkdir(mode=0o755)
        source = legacy / "old.sh"
        source.write_bytes(b"trusted operations fixture")
        source.chmod(0o700)
        legacy_store = R25Storage([str(legacy)], owner_uid=self.owner[0], owner_gid=self.owner[1],
                                  private_roots=())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        identity = legacy_store.file_identity(source, digest, expected_owner=self.owner,
                                               expected_mode=0o700)
        copied = legacy_store.atomic_copy_file(source, legacy / "new.sh", digest,
                    source_owner=self.owner, source_mode=0o700, target_owner=self.owner, mode=0o700)
        self.assertEqual(copied["mode"], "0o700")
        self.assertEqual(identity["sha256"], copied["sha256"])

    def test_mkdir_and_directory_fsync_acknowledgement_failure(self):
        directory = self.store.mkdir_private(self.root / "journal")
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.store.mkdir_private(directory)
        original_fsync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("simulated directory fsync acknowledgement failure")
            return original_fsync(fd)
        target = self.root / "record.json"
        with patch("r25_storage.os.fsync", side_effect=fail_directory):
            with self.assertRaises(StorageRefused):
                self.store.atomic_write_json(target, {"published_before_fsync_failure": True})
        # The caller's transaction must inspect the unknown commit outcome;
        # this layer neither deletes the published file nor claims rollback.
        self.assertTrue(target.exists())
        self.assertEqual(self.store.read_private_record(target),
                         {"published_before_fsync_failure": True})


if __name__ == "__main__":
    unittest.main()

