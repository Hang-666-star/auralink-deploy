"""Bound traversal exception; real disposable ACLs, never the host /root ACL.

The logical /root path and root inode ownership are mapped to a disposable
directory for unprivileged CI. ACL bytes, kernel round trips, fds, mode/ctime,
digest checks and the verifier itself remain real unless a test says otherwise.
"""
from copy import deepcopy
import errno
import os
from pathlib import Path
import pwd
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import core_business as business
from test_core_business import fixture_policy, encoded


def acl_bytes(uid, permission=1, extra=()):
    entries = [(1, 7, 0xffffffff), (2, permission, uid), *extra,
               (4, 0, 0xffffffff), (16, 1, 0xffffffff), (32, 0, 0xffffffff)]
    return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)


def metadata(info, **changes):
    values = {key: getattr(info, key) for key in
              ('st_dev', 'st_ino', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_gid')}
    values.update(changes)
    return SimpleNamespace(**values)


class TraversalAclTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r25-traversal-acl-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'synthetic-root'
        self.directory.mkdir()
        self.directory.chmod(0o710)
        self.policy = fixture_policy(self.root, 'poetry-only', 'sealed-memfd-capdrop')
        self.account = pwd.getpwnam('nobody')
        self.policy['installation']['postgres'].update(
            credential_account=self.account.pw_name, credential_uid=self.account.pw_uid,
            credential_gid=self.account.pw_gid)
        self.policy['upgrade']['configuration']['knowledge']['snapshot-root'] = '/root/synthetic-only/snapshot'
        self.raw = acl_bytes(self.account.pw_uid)
        self.policy['upgrade']['assets']['ancestor_traversal_acl'] = {
            'path': '/root', 'sha256': business.sha(self.raw),
            'credential_account': self.account.pw_name, 'credential_uid': self.account.pw_uid,
        }

    def verify(self, *, policy=None, raw=None, names=None, info_changes=None,
               fd_changes=None, after_changes=None):
        """Use real fd and directory; synthetic bytes only when raw is passed."""
        selected = self.policy if policy is None else policy
        business.validate_policy(selected)
        real_open, real_fstat = os.open, os.fstat
        root_info = metadata(self.directory.stat(), **{'st_uid': 0, 'st_gid': 0, **(info_changes or {})})
        calls = 0

        def open_logical(path, flags):
            self.assertEqual(path, Path('/root'))
            self.assertEqual(flags, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            return real_open(self.directory, flags)

        def fstat_logical(fd):
            nonlocal calls
            calls += 1
            return metadata(real_fstat(fd), **{'st_uid': 0, 'st_gid': 0, **(fd_changes or {}),
                            **((after_changes or {}) if calls == 2 else {})})

        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(business.os, 'open', side_effect=open_logical))
            stack.enter_context(patch.object(business.os, 'fstat', side_effect=fstat_logical))
            if raw is not None:
                stack.enter_context(patch.object(business.os, 'getxattr', return_value=raw))
            if names is not None:
                stack.enter_context(patch.object(business.os, 'listxattr', return_value=names))
            business._verify_parent_acl(selected, Path('/root'), root_info)

    def install_disposable_acl(self, name='system.posix_acl_access', raw=None):
        try:
            os.setxattr(self.directory, name, self.raw if raw is None else raw)
        except OSError as error:
            if error.errno in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS):
                self.skipTest('Filesystem does not support real POSIX ACL xattrs')
            raise

    def test_real_kernel_acl_roundtrip_accepts_bound_execute_only(self):
        self.install_disposable_acl()
        self.assertEqual(os.getxattr(self.directory, 'system.posix_acl_access'), self.raw)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o710)
        self.verify()

    def test_optional_binding_is_strict_and_only_sealed_root_ancestor(self):
        business.validate_policy(self.policy)
        edits = (
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(extra=True),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].pop('sha256'),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(path='/'),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(path='/root/snapshot'),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(credential_uid=True),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(credential_uid=0),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(credential_uid=self.account.pw_uid+1),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(credential_account='another'),
            lambda p: p['upgrade']['assets']['ancestor_traversal_acl'].update(sha256='unknown'),
            lambda p: p['upgrade']['assets'].update(ancestor_traversal_acl=None),
            lambda p: p['upgrade']['configuration']['knowledge'].update({'snapshot-root': '/root'}),
            lambda p: p['upgrade']['configuration']['knowledge'].update({'snapshot-root': '/elsewhere/snapshot'}),
            lambda p: p['installation']['service'].update(isolation='readonly-filesystem-capdrop'),
        )
        for edit in edits:
            with self.subTest(edit=edit):
                changed = deepcopy(self.policy)
                edit(changed)
                with self.assertRaises(business.Refused):
                    business.validate_policy(changed)
        for profile, isolation in (('poetry-only', 'nonroot-posix'),
                                   ('poetry-only', 'readonly-filesystem-capdrop'),
                                   ('map-enabled', 'nonroot-posix')):
            with self.subTest(profile=profile, isolation=isolation):
                changed = fixture_policy(self.root, profile, isolation)
                if isolation == 'readonly-filesystem-capdrop':
                    changed['installation']['service'] = {'account': 'root', 'uid': 0, 'gid': 0,
                                                          'groups': [0], 'isolation': isolation}
                changed['upgrade']['assets']['ancestor_traversal_acl'] = deepcopy(
                    self.policy['upgrade']['assets']['ancestor_traversal_acl'])
                with self.assertRaisesRegex(business.Refused, 'business_traversal_acl_mode'):
                    business.validate_policy(changed)

    def test_absent_binding_still_rejects_real_acl(self):
        self.install_disposable_acl()
        changed = deepcopy(self.policy)
        changed['upgrade']['assets'].pop('ancestor_traversal_acl')
        business.validate_policy(changed)
        with self.assertRaisesRegex(business.Refused, 'asset_acl_requires_review'):
            business._verify_parent_acl(changed, self.directory, self.directory.stat())

    def test_no_exception_for_asset_root_or_another_parent(self):
        self.install_disposable_acl()
        # A non-/root actual path remains rejected even with an approved /root ACL.
        with self.assertRaisesRegex(business.Refused, 'asset_acl_requires_review'):
            business._verify_parent_acl(self.policy, self.directory, self.directory.stat())

    def test_required_bound_acl_absent_and_default_acl_refuse(self):
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_attributes'):
            self.verify()
        self.install_disposable_acl()
        self.install_disposable_acl('system.posix_acl_default')
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_attributes'):
            self.verify()

    def test_extra_acl_attribute_refuses(self):
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_attributes'):
            self.verify(raw=self.raw, names=['system.posix_acl_access', 'system.posix_acl_unknown'])

    def test_wrong_digest_refuses_real_bytes(self):
        self.install_disposable_acl()
        changed = deepcopy(self.policy)
        changed['upgrade']['assets']['ancestor_traversal_acl']['sha256'] = '0'*64
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_digest'):
            self.verify(policy=changed)

    def test_reviewed_hash_does_not_permit_malformed_or_broader_acl(self):
        variants = [acl_bytes(self.account.pw_uid, permission=value) for value in (0, 3, 5, 7)]
        variants.extend((acl_bytes(self.account.pw_uid+1),
                         acl_bytes(self.account.pw_uid, extra=((2, 1, self.account.pw_uid+1),)),
                         struct.pack('<I', 1)+self.raw[4:], self.raw[:-1], self.raw+b'\0'))
        for raw in variants:
            with self.subTest(raw=raw.hex()):
                changed = deepcopy(self.policy)
                changed['upgrade']['assets']['ancestor_traversal_acl']['sha256'] = business.sha(raw)
                with self.assertRaisesRegex(business.Refused, 'traversal_acl_entries'):
                    self.verify(policy=changed, raw=raw, names=['system.posix_acl_access'])

    def test_directory_identity_and_midread_drift_refuse(self):
        self.install_disposable_acl()
        for changes in ({'st_ino': self.directory.stat().st_ino+1},
                        {'st_ctime_ns': self.directory.stat().st_ctime_ns+1}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(business.Refused, 'traversal_acl_directory_identity'):
                    self.verify(info_changes=changes)
        self.directory.chmod(0o750)
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_directory_identity'):
            self.verify()
        self.install_disposable_acl()
        for changes in ({'st_uid': 42}, {'st_gid': 42}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(business.Refused, 'traversal_acl_directory_identity'):
                    self.verify(fd_changes=changes)
        with self.assertRaisesRegex(business.Refused, 'traversal_acl_changed'):
            self.verify(after_changes={'st_ctime_ns': self.directory.stat().st_ctime_ns+1})

    def test_actual_credential_account_must_still_match(self):
        self.install_disposable_acl()
        foreign = SimpleNamespace(pw_uid=self.account.pw_uid+1, pw_gid=self.account.pw_gid)
        with patch.object(business.pwd, 'getpwnam', return_value=foreign):
            with self.assertRaisesRegex(business.Refused, 'traversal_acl_account_drift'):
                self.verify()
        with patch.object(business.pwd, 'getpwnam', side_effect=KeyError('synthetic missing account')):
            with self.assertRaisesRegex(business.Refused, 'traversal_acl_account_drift'):
                self.verify()

    def test_asset_verifier_dispatches_all_ancestors_and_keeps_file_acl_denial(self):
        policy = fixture_policy(self.root, 'poetry-only', 'sealed-memfd-capdrop')
        root = self.root / 'snapshot'
        root.mkdir()
        self.addCleanup(lambda: root.chmod(0o700))
        entries = []
        for filename, key in business.required_assets('poetry-only').items():
            raw = encoded({'synthetic': filename})
            path = root / filename
            path.write_bytes(raw)
            path.chmod(0o440)
            policy['upgrade']['configuration']['knowledge'][key] = business.sha(raw)
            entries.append({'filename': filename, 'sha256': business.sha(raw), 'bytes': len(raw)})
        manifest = encoded({'schemaVersion': 2, 'releaseProfile': 'poetry-only', 'artifacts': entries})
        (self.root / 'assets.json').write_bytes(manifest)
        (self.root / 'assets.json').chmod(0o600)
        policy['upgrade']['assets']['manifest_sha256'] = business.sha(manifest)
        service = {**policy['installation']['service'], 'uid': os.getuid(), 'gid': os.getgid(), 'groups': [os.getgid()]}
        root.chmod(0o550)
        with patch.object(business, '_service', return_value=service):
            with patch.object(business, '_verify_parent_acl', wraps=business._verify_parent_acl) as verify:
                receipt = business.verify_assets(policy)
                self.assertEqual(receipt['files'], 2)
                self.assertEqual([call.args[1] for call in verify.call_args_list], [root, *root.parents])
            for target, reason in ((root, 'asset_acl_requires_review'),
                                   (self.root, 'asset_acl_requires_review'),
                                   (root / 'poetry-graph.json', 'asset_file_permissions')):
                with self.subTest(target=str(target)):
                    def attributes(path):
                        return ['system.posix_acl_access'] if Path(path) == target else []
                    with patch.object(business.os, 'listxattr', side_effect=attributes):
                        with self.assertRaisesRegex(business.Refused, reason):
                            business.verify_assets(policy)


if __name__ == '__main__':
    unittest.main()
