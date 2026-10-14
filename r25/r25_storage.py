"""Linux file safety for a trusted R25 adapter; no CLI or application actions.

Callers supply fixed allowed roots and hold the publication lease. This module
checks filesystem identity and atomic durability; it does not authorize a
release, interpret candidate paths, or implement CURRENT/business state.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import sys

RECORD_LIMIT = 1024 * 1024
FILE_LIMIT = 512 * 1024 * 1024


class StorageRefused(ValueError):
    pass


def must(condition, reason):
    if not condition:
        raise StorageRefused(reason)


def linux_absolute(path):
    """Pure validation; available on Windows without touching its filesystem."""
    raw = os.fspath(path)
    must(type(raw) is str and raw.startswith("/") and not raw.startswith("//"),
         "linux_absolute_path_required")
    must("\\" not in raw and not any(ord(c) < 32 or ord(c) == 127 for c in raw),
         "unsafe_path_characters")
    must(not any(part in {"", ".", ".."} for part in raw.split("/")[1:]),
         "unsafe_path_components")
    result = PurePosixPath(raw)
    must(result != PurePosixPath("/"), "filesystem_root_forbidden")
    return result


def sha256_value(value):
    must(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
         "sha256_identity")
    return value


def owner_value(value):
    must(isinstance(value, tuple) and len(value) == 2 and
         all(type(v) is int and v >= 0 for v in value), "owner_identity")
    return value


def mode_value(value):
    must(type(value) is int and value in {0o600, 0o700}, "private_file_mode")
    return value


def strict_json(raw, max_bytes=RECORD_LIMIT):
    must(type(max_bytes) is int and 0 < max_bytes <= RECORD_LIMIT, "record_size_policy")
    must(type(raw) in {str, bytes, bytearray}, "json_input_type")
    try:
        data = raw.encode("utf-8") if type(raw) is str else bytes(raw)
    except UnicodeError as error:
        raise StorageRefused("invalid_json_encoding") from error
    must(len(data) <= max_bytes, "record_size_limit")

    def pairs(items):
        result = {}
        for key, value in items:
            must(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise StorageRefused("nonfinite_json")

    def finite(value, depth=0):
        must(depth <= 128, "json_depth_limit")
        if type(value) is float:
            must(math.isfinite(value), "nonfinite_json")
        elif type(value) is dict:
            for item in value.values():
                finite(item, depth + 1)
        elif type(value) is list:
            for item in value:
                finite(item, depth + 1)

    try:
        result = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        must(type(result) is dict, "json_object_required")
        finite(result)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise StorageRefused("invalid_json") from error
    return result


class R25Storage:
    """Fixed roots, exact final-file policies, optional private directory roots.

    Defaults are root:root files and private root:root 0700 roots. For legacy
    R25 operations under a 0755 directory, explicitly pass private_roots=()
    and expected_owner/expected_mode for its trusted 1000:1000:0700 files.
    Every ancestor is still traversed using directory FDs and O_NOFOLLOW.
    """

    def __init__(self, allowed_roots, owner_uid=0, owner_gid=0, private_roots=None):
        self.owner = owner_value((owner_uid, owner_gid))
        self.allowed_roots = tuple(linux_absolute(root) for root in allowed_roots)
        must(bool(self.allowed_roots), "allowed_roots_required")
        must(len(set(self.allowed_roots)) == len(self.allowed_roots), "duplicate_allowed_root")
        roots = self.allowed_roots if private_roots is None else tuple(
            linux_absolute(root) for root in private_roots)
        must(all(any(root == allowed or root.is_relative_to(allowed)
                     for allowed in self.allowed_roots) for root in roots),
             "private_root_outside_allowed_roots")
        self.private_roots = tuple(roots)

    def _target(self, path):
        value = linux_absolute(path)
        must(any(value == root or value.is_relative_to(root)
                 for root in self.allowed_roots), "path_outside_allowed_roots")
        return value

    def _linux(self):
        must(sys.platform.startswith("linux"), "linux_storage_required")
        must(all(hasattr(os, name) for name in
                 ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "fchown")),
             "linux_storage_flags_required")

    def _directory(self, value, identity):
        must(stat.S_ISDIR(identity.st_mode), "directory_required")
        if any(value == root or value.is_relative_to(root) for root in self.private_roots):
            must((identity.st_uid, identity.st_gid) == self.owner, "directory_owner")
            must(stat.S_IMODE(identity.st_mode) == 0o700, "directory_mode")

    @contextmanager
    def _parent(self, path):
        value = self._target(path)
        self._linux()
        fd = None
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open("/", flags)
            current = PurePosixPath("/")
            for part in value.parts[1:-1]:
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                current /= part
                self._directory(current, os.fstat(fd))
            yield fd, value.name, value
        except OSError as error:
            raise StorageRefused("filesystem_" + type(error).__name__) from error
        finally:
            if fd is not None:
                os.close(fd)

    def _file_policy(self, identity, owner=None, mode=0o600, max_bytes=FILE_LIMIT):
        expected_owner = self.owner if owner is None else owner_value(owner)
        mode_value(mode)
        must(stat.S_ISREG(identity.st_mode), "regular_file_required")
        must((identity.st_uid, identity.st_gid) == expected_owner, "file_owner")
        must(stat.S_IMODE(identity.st_mode) == mode, "file_mode")
        must(type(max_bytes) is int and max_bytes >= 0, "file_size_policy")
        must(identity.st_size <= max_bytes, "file_size_limit")
        return expected_owner

    @contextmanager
    def _file(self, path, owner=None, mode=0o600, max_bytes=FILE_LIMIT):
        with self._parent(path) as (parent_fd, name, value):
            fd = None
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                             os.O_NONBLOCK, dir_fd=parent_fd)
                identity = os.fstat(fd)
                self._file_policy(identity, owner, mode, max_bytes)
                yield fd, identity, value
            finally:
                if fd is not None:
                    os.close(fd)

    @staticmethod
    def _unchanged(before, after):
        must((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
              before.st_ctime_ns, before.st_uid, before.st_gid, before.st_mode) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
              after.st_ctime_ns, after.st_uid, after.st_gid, after.st_mode),
             "file_changed_during_read")

    def validate_target(self, path, exists=None, directory=False,
                        expected_owner=None, expected_mode=None):
        must(exists is None or type(exists) is bool, "existence_policy")
        with self._parent(path) as (parent_fd, name, value):
            try:
                identity = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                must(exists is not True, "target_missing")
                return Path(str(value))
            must(exists is not False, "target_already_exists")
            must(not stat.S_ISLNK(identity.st_mode), "symlink_target")
            if directory:
                self._directory(value, identity)
                if expected_owner is not None:
                    must((identity.st_uid, identity.st_gid) == owner_value(expected_owner),
                         "directory_owner")
                if expected_mode is not None:
                    must(type(expected_mode) is int and stat.S_IMODE(identity.st_mode) ==
                         expected_mode, "directory_mode")
            else:
                self._file_policy(identity, expected_owner,
                                  0o600 if expected_mode is None else expected_mode)
            return Path(str(value))

    def file_identity(self, path, expected_sha256=None, expected_bytes=None,
                      expected_owner=None, expected_mode=0o600, max_bytes=FILE_LIMIT):
        if expected_sha256 is not None:
            sha256_value(expected_sha256)
        if expected_bytes is not None:
            must(type(expected_bytes) is int and expected_bytes >= 0, "byte_identity")
        with self._file(path, expected_owner, expected_mode, max_bytes) as (fd, before, value):
            digest = hashlib.sha256()
            total = 0
            for block in iter(lambda: os.read(fd, 1024 * 1024), b""):
                total += len(block)
                must(total <= max_bytes, "file_size_limit")
                digest.update(block)
            self._unchanged(before, os.fstat(fd))
            observed = digest.hexdigest()
            must(total == before.st_size, "file_size_changed")
            if expected_sha256 is not None:
                must(observed == expected_sha256, "file_sha256_mismatch")
            if expected_bytes is not None:
                must(total == expected_bytes, "file_bytes_mismatch")
            return {"path": str(value), "sha256": observed, "bytes": total,
                    "uid": before.st_uid, "gid": before.st_gid,
                    "mode": oct(stat.S_IMODE(before.st_mode))}

    def read_private_record(self, path, expected_sha256=None,
                            expected_owner=None, expected_mode=0o600):
        if expected_sha256 is not None:
            sha256_value(expected_sha256)
        with self._file(path, expected_owner, expected_mode, RECORD_LIMIT) as (fd, before, _):
            raw = bytearray()
            while True:
                block = os.read(fd, min(65536, RECORD_LIMIT + 1 - len(raw)))
                if not block:
                    break
                raw.extend(block)
                must(len(raw) <= RECORD_LIMIT, "record_size_limit")
            self._unchanged(before, os.fstat(fd))
            must(len(raw) == before.st_size, "file_size_changed")
            if expected_sha256 is not None:
                must(hashlib.sha256(raw).hexdigest() == expected_sha256,
                     "record_sha256_mismatch")
            return strict_json(raw)

    def mkdir_private(self, path, target_owner=None):
        owner = self.owner if target_owner is None else owner_value(target_owner)
        value = self._target(path)
        if any(value == root or value.is_relative_to(root) for root in self.private_roots):
            must(owner == self.owner, "private_directory_owner_policy")
        with self._parent(path) as (parent_fd, name, value):
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                return self.validate_target(value, exists=True, directory=True,
                                            expected_owner=owner, expected_mode=0o700)
            directory_fd = None
            try:
                directory_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY |
                                       os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                os.fchown(directory_fd, *owner)
                os.fchmod(directory_fd, 0o700)
                os.fsync(directory_fd)
                os.fsync(parent_fd)
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)
            return Path(str(value))

    def remove_bound_file(self, path, expected_sha256, *, expected_owner):
        """Remove only a transaction-created after-image, never an unknown file."""
        with self._parent(path) as (parent_fd,name,_):
            observed=self.file_identity(path,expected_sha256=expected_sha256,expected_owner=expected_owner)
            named=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            must(stat.S_ISREG(named.st_mode) and named.st_nlink==1,"remove_regular_file")
            # file_identity already uses no-follow descriptors; recheck inode before unlink.
            with self._file(path,owner=expected_owner,mode=0o600) as (fd, info, _value):
                must((named.st_dev,named.st_ino)==(info.st_dev,info.st_ino),"remove_inode_drift")
                os.unlink(name,dir_fd=parent_fd)
                os.fsync(parent_fd)

    def remove_empty_directory(self,path,*,expected_owner):
        with self._parent(path) as (parent_fd,name,_):
            self.validate_target(path,exists=True,directory=True,expected_owner=expected_owner,expected_mode=0o700)
            os.rmdir(name,dir_fd=parent_fd)  # Refuses nonempty/unknown additions.
            os.fsync(parent_fd)

    @staticmethod
    def _write(fd, data):
        remaining = memoryview(data)
        while remaining:
            written = os.write(fd, remaining)
            must(written > 0, "short_write")
            remaining = remaining[written:]

    def _existing(self, parent_fd, name, replace, expected, owner, mode):
        fd = None
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                         os.O_NONBLOCK, dir_fd=parent_fd)
        except FileNotFoundError:
            must(expected is None, "expected_existing_target_missing")
            return False
        try:
            must(replace, "target_already_exists")
            must(expected is not None, "replacement_digest_required")
            before = os.fstat(fd)
            self._file_policy(before, owner, mode)
            h = hashlib.sha256()
            total = 0
            for block in iter(lambda: os.read(fd, 1024 * 1024), b""):
                total += len(block)
                must(total <= FILE_LIMIT, "file_size_limit")
                h.update(block)
            self._unchanged(before, os.fstat(fd))
            must(total == before.st_size, "file_size_changed")
            must(h.hexdigest() == expected, "existing_sha256_mismatch")
            return True
        finally:
            os.close(fd)

    def _atomic(self, path, writer, mode=0o600, target_owner=None, replace=False,
                expected_existing_sha256=None, existing_owner=None, existing_mode=None):
        mode_value(mode)
        owner = self.owner if target_owner is None else owner_value(target_owner)
        old_owner = owner if existing_owner is None else owner_value(existing_owner)
        old_mode = mode if existing_mode is None else mode_value(existing_mode)
        must(type(replace) is bool, "replacement_policy")
        if expected_existing_sha256 is not None:
            sha256_value(expected_existing_sha256)
            must(replace, "replacement_policy")
        with self._parent(path) as (parent_fd, name, value):
            self._existing(parent_fd, name, replace, expected_existing_sha256,
                           old_owner, old_mode)
            temporary = ".r25-write-" + secrets.token_hex(16) + ".tmp"
            fd = None
            try:
                fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent_fd)
                os.fchown(fd, *owner)
                os.fchmod(fd, mode)
                result = writer(fd)
                os.fsync(fd)
                created = os.fstat(fd)
                named = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
                must((named.st_dev, named.st_ino) == (created.st_dev, created.st_ino)
                     and stat.S_ISREG(named.st_mode), "temporary_identity_changed")
                present = self._existing(parent_fd, name, replace,
                                         expected_existing_sha256, old_owner, old_mode)
                if present:
                    os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                else:
                    # Atomic no-clobber creation. Never overwrite a file which
                    # appeared after our preflight; unlink only our own temp.
                    os.link(temporary, name, src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd, follow_symlinks=False)
                    named = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
                    must((named.st_dev, named.st_ino) == (created.st_dev, created.st_ino),
                         "temporary_identity_changed")
                    os.unlink(temporary, dir_fd=parent_fd)
                os.fsync(parent_fd)
                return {"path": str(value), **result, "uid": owner[0], "gid": owner[1],
                        "mode": oct(mode)}
            finally:
                if fd is not None:
                    os.close(fd)
                # Failed writes retain their owned temporary file as evidence.
                # Never glob/remove stale temporary or unknown target files.

    def atomic_write_bytes(self, path, data, *, mode=0o600, target_owner=None,
                           replace=False, expected_existing_sha256=None,
                           existing_owner=None, existing_mode=None):
        must(type(data) in {bytes, bytearray}, "binary_input_type")
        raw = bytes(data)
        must(len(raw) <= RECORD_LIMIT, "record_size_limit")
        digest = hashlib.sha256(raw).hexdigest()

        def write(fd):
            self._write(fd, raw)
            return {"sha256": digest, "bytes": len(raw)}

        return self._atomic(path, write, mode=mode, target_owner=target_owner,
                            replace=replace,
                            expected_existing_sha256=expected_existing_sha256,
                            existing_owner=existing_owner, existing_mode=existing_mode)

    def atomic_write_json(self, path, document, *, replace=False,
                          expected_existing_sha256=None, target_owner=None,
                          existing_owner=None, existing_mode=0o600):
        must(type(document) is dict, "json_object_required")
        try:
            raw = (json.dumps(document, sort_keys=True, indent=2,
                              allow_nan=False) + "\n").encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            raise StorageRefused("invalid_json_document") from error
        strict_json(raw)
        digest = hashlib.sha256(raw).hexdigest()

        def write(fd):
            self._write(fd, raw)
            return {"sha256": digest, "bytes": len(raw)}

        return self._atomic(path, write, target_owner=target_owner, replace=replace,
                            expected_existing_sha256=expected_existing_sha256,
                            existing_owner=existing_owner, existing_mode=existing_mode)

    def atomic_copy_file(self, source, target, expected_sha256, *, expected_bytes=None,
                         source_owner=None, source_mode=0o600, target_owner=None,
                         mode=0o600, replace=False, expected_existing_sha256=None,
                         existing_owner=None, existing_mode=None):
        sha256_value(expected_sha256)
        must(self._target(source) != self._target(target), "source_equals_target")
        if expected_bytes is not None:
            must(type(expected_bytes) is int and expected_bytes >= 0, "byte_identity")
        with self._file(source, source_owner, source_mode) as (source_fd, before, _):
            def copy(fd):
                digest = hashlib.sha256()
                total = 0
                for block in iter(lambda: os.read(source_fd, 1024 * 1024), b""):
                    total += len(block)
                    must(total <= FILE_LIMIT, "file_size_limit")
                    digest.update(block)
                    self._write(fd, block)
                self._unchanged(before, os.fstat(source_fd))
                must(total == before.st_size, "file_size_changed")
                must(digest.hexdigest() == expected_sha256, "copy_sha256_mismatch")
                if expected_bytes is not None:
                    must(total == expected_bytes, "copy_bytes_mismatch")
                # Re-read the temp through its owned FD before publication.
                os.lseek(fd, 0, os.SEEK_SET)
                stored = hashlib.sha256()
                for block in iter(lambda: os.read(fd, 1024 * 1024), b""):
                    stored.update(block)
                must(stored.hexdigest() == expected_sha256, "copied_sha256_mismatch")
                return {"sha256": expected_sha256, "bytes": total}

            return self._atomic(target, copy, mode=mode, target_owner=target_owner,
                                replace=replace,
                                expected_existing_sha256=expected_existing_sha256,
                                existing_owner=existing_owner, existing_mode=existing_mode)

