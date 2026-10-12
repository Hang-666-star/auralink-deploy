"""Synthetic /proc parser tests. Kernel privilege tests run separately in a
throwaway Linux namespace, never in the unittest/coordinator process.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core_asset_sandbox as sandbox


class AssetSandboxProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='asset-sandbox-proof-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proc = self.root/'proc'; (self.proc/'4312').mkdir(parents=True)
        self.assets = self.root/'assets'
        self.mount = '72 26 0:51 / '+str(self.assets)+' ro,nosuid,nodev,noexec,relatime - tmpfs tmpfs ro,size=16384k\n'
        self.status = ''.join(key+': 0000000000000000\n' for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))+'NoNewPrivs: 1\n'
        self.files()

    def files(self):
        (self.proc/'4312/mountinfo').write_text(self.mount)
        (self.proc/'4312/status').write_text(self.status)

    def test_dedicated_global_readonly_tmpfs_and_every_capability_set_required(self):
        proof = sandbox.verify(4312,self.assets,proc_root=self.proc)
        self.assertTrue(proof['superblock_read_only'])
        self.assertTrue(proof['no_new_privileges'])
        self.assertTrue(proof['capability_sets_zero'])

    def test_readonly_bind_of_writable_superblock_fails_closed(self):
        self.mount = self.mount.replace('tmpfs tmpfs ro,','tmpfs tmpfs rw,')
        self.files()
        with self.assertRaisesRegex(sandbox.Refused,'readonly_superblock_required'):
            sandbox.verify(4312,self.assets,proc_root=self.proc)

    def test_disk_backed_readonly_and_nonroot_bind_are_not_approved_tmpfs(self):
        good = self.mount
        for invalid in (good.replace(' - tmpfs tmpfs ',' - squashfs /dev/loop0 '), good.replace('0:51 / ','0:51 /snapshot ')):
            self.mount=invalid;self.files()
            with self.assertRaisesRegex(sandbox.Refused,'unsupported_backing_storage'):
                sandbox.verify(4312,self.assets,proc_root=self.proc)

    def test_child_mount_or_missing_security_flags_or_duplicate_mounts_refuse(self):
        good = self.mount
        for invalid in (good + good.replace(str(self.assets),str(self.assets/'nested')), good.replace('nodev,',''), good+good):
            self.mount=invalid;self.files()
            with self.assertRaises(sandbox.Refused): sandbox.verify(4312,self.assets,proc_root=self.proc)

    def test_no_mount_is_not_a_readonly_volume(self):
        self.mount='';self.files()
        with self.assertRaisesRegex(sandbox.Refused,'dedicated_mount_required'):
            sandbox.verify(4312,self.assets,proc_root=self.proc)

    def test_each_remaining_capability_or_no_new_privileges_absence_refuses(self):
        good=self.status
        for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
            self.status=good.replace(key+': 0000000000000000',key+': 0000000000000001');self.files()
            with self.subTest(key=key),self.assertRaisesRegex(sandbox.Refused,'capabilities_remaining'):
                sandbox.verify(4312,self.assets,proc_root=self.proc)
        self.status=good.replace('NoNewPrivs: 1','NoNewPrivs: 0');self.files()
        with self.assertRaisesRegex(sandbox.Refused,'no_new_privileges_required'):
            sandbox.verify(4312,self.assets,proc_root=self.proc)

    def test_proc_seq_file_short_reads_are_collected_until_eof(self):
        path = self.proc/'4312/mountinfo'
        with patch.object(sandbox.os,'read',side_effect=[b'first short block',b' second block',b'']):
            self.assertEqual(sandbox._read(path),'first short block second block')

    def test_privilege_transition_refuses_unprovisioned_assets_before_prctl(self):
        with patch.object(sandbox,'filesystem_proof',side_effect=sandbox.Refused('fixture_not_provisioned')):
            with patch.object(sandbox.ctypes,'CDLL') as library:
                with self.assertRaisesRegex(sandbox.Refused,'fixture_not_provisioned'): sandbox.prepare(self.assets)
                library.assert_not_called()


if __name__=='__main__':
    unittest.main()
