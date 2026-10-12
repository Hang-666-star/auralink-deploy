"""Synthetic /proc parser tests. Kernel privilege tests run separately in a
throwaway Linux namespace, never in the unittest/coordinator process.
Sealed descriptor tests use real anonymous kernel objects in disposable children;
they do not represent full root-Java privilege transition integration.
"""
from pathlib import Path
import errno
import fcntl
import hashlib
import json
import os
import pwd
import subprocess
import sys
import textwrap
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


class SealedAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sealed-asset-proof-')
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)/'proc'
        (self.proc/'4312/fd').mkdir(parents=True)
        self.status = ''.join(key+': 0000000000000000\n' for key in
            ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))+'NoNewPrivs: 1\n'
        (self.proc/'4312/status').write_text(self.status)
        self.artifacts = {name: {'raw': name.encode(), 'bytes':len(name),
            'sha256': hashlib.sha256(name.encode()).hexdigest()} for name in sandbox.SEALED_FDS}
        self.specs = {name:{k:v for k,v in item.items() if k!='raw'} for name,item in self.artifacts.items()}
        self.owner_uid = os.getuid() if os.getuid() else pwd.getpwnam('nobody').pw_uid
        self.owner_gid = os.getgid()
        self.fds = []
        self.addCleanup(self.close_fds)

    def close_fds(self):
        for fd in self.fds:
            os.close(fd)

    def objects(self, *, seals=sandbox.REQUIRED_SEALS):
        for name,number in sandbox.SEALED_FDS.items():
            fd = os.memfd_create('synthetic-' + name, os.MFD_ALLOW_SEALING)
            self.fds.append(fd)
            os.write(fd,self.artifacts[name]['raw'])
            os.fchown(fd,self.owner_uid,self.owner_gid)
            os.fchmod(fd,0o440)
            if seals:
                fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals)
            (self.proc/'4312/fd'/str(number)).symlink_to('/proc/self/fd/'+str(fd))

    def child(self, source):
        environment = dict(os.environ, PYTHONPATH=str(Path(sandbox.__file__).parent))
        result = subprocess.run([sys.executable,'-B','-c',textwrap.dedent(source)],
            env=environment,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_actual_seals_bytes_and_separate_objects_plus_process_privilege_proof(self):
        self.objects()
        proof = sandbox.verify_sealed(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)
        self.assertTrue(proof['immutable_bytes'])
        self.assertTrue(proof['capability_sets_zero'])
        self.assertEqual(set(proof['files']),set(self.artifacts))
        self.assertEqual([item['fd'] for item in proof['files'].values()],[198,199])

    def test_root_inode_owner_and_wrong_owner_binding_refuse(self):
        self.objects()
        with self.assertRaisesRegex(sandbox.Refused,'sealed_owner'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=0,owner_gid=self.owner_gid,proc_root=self.proc)
        with self.assertRaisesRegex(sandbox.Refused,'object_type'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid+1,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_real_unsealed_and_partial_seals_refuse(self):
        self.objects(seals=fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW)
        with self.assertRaisesRegex(sandbox.Refused,'seals_incomplete'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_same_sealed_object_in_both_slots_refuses(self):
        self.objects()
        second=self.proc/'4312/fd/199'
        second.unlink(); second.symlink_to('/proc/self/fd/'+str(self.fds[0]))
        with self.assertRaisesRegex(sandbox.Refused,'objects_not_distinct'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_hash_size_file_set_and_missing_slot_refuse(self):
        self.objects()
        name='poetry-graph.json'
        for key,value,reason in [('sha256','0'*64,'sealed_digest'),('bytes',1,'sealed_size')]:
            bad={n:dict(v) for n,v in self.specs.items()};bad[name][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(sandbox.Refused,reason):
                sandbox.verify_sealed_files(4312,bad,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)
        with self.assertRaisesRegex(sandbox.Refused,'sealed_file_set'):
            sandbox.verify_sealed_files(4312,{'poetry-graph.json':self.specs[name]},owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)
        (self.proc/'4312/fd/199').unlink()
        with self.assertRaisesRegex(sandbox.Refused,'descriptor_missing'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_ordinary_readonly_file_or_metadata_drift_is_not_proof(self):
        self.objects()
        os.fchmod(self.fds[0],0o400)
        with self.assertRaisesRegex(sandbox.Refused,'object_type'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)
        source=Path(self.tmp.name)/'ordinary';source.write_bytes(self.artifacts['poetry-graph.json']['raw']);source.chmod(0o440)
        slot=self.proc/'4312/fd/198';slot.unlink();slot.symlink_to(source)
        with self.assertRaisesRegex(sandbox.Refused,'object_type'):
            sandbox.verify_sealed_files(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_every_process_capability_and_no_new_privileges_are_still_required(self):
        self.objects()
        for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
            (self.proc/'4312/status').write_text(self.status.replace(key+': 0000000000000000',key+': 0000000000000001'))
            with self.subTest(key=key),self.assertRaisesRegex(sandbox.Refused,'capabilities_remaining'):
                sandbox.verify_sealed(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)
        (self.proc/'4312/status').write_text(self.status.replace('NoNewPrivs: 1','NoNewPrivs: 0'))
        with self.assertRaisesRegex(sandbox.Refused,'no_new_privileges_required'):
            sandbox.verify_sealed(4312,self.specs,owner_uid=self.owner_uid,owner_gid=self.owner_gid,proc_root=self.proc)

    def test_bad_source_refuses_before_descriptor_or_privilege_changes(self):
        self.artifacts['poetry-graph.json']['raw']=b'wrong'
        with patch.object(sandbox.os,'memfd_create') as create,patch.object(sandbox,'_drop_privileges') as drop:
            with self.assertRaisesRegex(sandbox.Refused,'sealed_source_identity'):
                sandbox.prepare_sealed(self.artifacts,owner_uid=self.owner_uid,owner_gid=self.owner_gid)
        create.assert_not_called();drop.assert_not_called()

    def test_occupied_slot_is_not_overwritten(self):
        result=self.child("""
            import os,json,hashlib,pwd
            import core_asset_sandbox as s
            fd=os.memfd_create('existing',os.MFD_ALLOW_SEALING);os.write(fd,b'keep')
            os.dup2(fd,198)
            data={n:{'raw':n.encode(),'bytes':len(n),'sha256':hashlib.sha256(n.encode()).hexdigest()} for n in s.SEALED_FDS}
            try:s.prepare_sealed(data,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid());raise AssertionError('must refuse')
            except s.Refused as e:assert str(e)=='asset_sandbox_sealed_descriptor_occupied'
            assert os.pread(198,4,0)==b'keep'
            try:os.fstat(199);raise AssertionError('second slot must remain absent')
            except OSError:pass
            print(json.dumps({'existing_unchanged':True}))
        """)
        self.assertTrue(result['existing_unchanged'])

    def test_creation_failure_closes_only_new_descriptors(self):
        result=self.child("""
            import os,json,hashlib,pwd
            from unittest.mock import patch
            import core_asset_sandbox as s
            real=os.memfd_create;count=0
            def create(*a,**k):
                global count
                count+=1
                if count==2:raise OSError('injected second allocation failure')
                return real(*a,**k)
            data={n:{'raw':n.encode(),'bytes':len(n),'sha256':hashlib.sha256(n.encode()).hexdigest()} for n in s.SEALED_FDS}
            with patch.object(s.os,'memfd_create',side_effect=create):
                try:s.prepare_sealed(data,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid());raise AssertionError('must refuse')
                except s.Refused as e:assert str(e)=='asset_sandbox_memfd_unavailable'
            for fd in (198,199):
                try:os.fstat(fd);raise AssertionError('new slot leaked')
                except OSError:pass
            print(json.dumps({'new_slots_closed':True}))
        """)
        self.assertTrue(result['new_slots_closed'])

    def test_privilege_transition_failure_leaves_no_new_descriptors(self):
        result=self.child("""
            import os,json,hashlib,pwd
            from unittest.mock import patch
            import core_asset_sandbox as s
            data={n:{'raw':n.encode(),'bytes':len(n),'sha256':hashlib.sha256(n.encode()).hexdigest()} for n in s.SEALED_FDS}
            with patch.object(s,'_drop_privileges',side_effect=s.Refused('injected_transition_failure')):
                try:s.prepare_sealed(data,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid());raise AssertionError('must refuse')
                except s.Refused as e:assert str(e)=='injected_transition_failure'
            for fd in (198,199):
                try:os.fstat(fd);raise AssertionError('new slot leaked')
                except OSError:pass
            print(json.dumps({'new_slots_closed':True}))
        """)
        self.assertTrue(result['new_slots_closed'])

    def test_real_seals_survive_exec_and_block_every_byte_mutation_path(self):
        # Actual kernel enforcement; no mocked seals or write calls. Privilege
        # drop is covered by the separate root integration, not this UID-neutral
        # primitive test. exec preserves the same PID and descriptor numbers.
        checker = """
import os,sys,json,hashlib,mmap,errno,pwd
import core_asset_sandbox as s
specs=json.loads(sys.argv[1]);assert os.getpid()==int(sys.argv[2])
proof=s.verify_sealed_files(os.getpid(),specs,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid())
fd=198;size=specs['poetry-graph.json']['bytes'];denied={}
for name,action in [('pwrite',lambda:os.pwrite(fd,b'x',0)),('shrink',lambda:os.ftruncate(fd,0)),('grow',lambda:os.ftruncate(fd,size+1)),('shared_mmap',lambda:mmap.mmap(fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_WRITE))]:
    try:action();raise AssertionError(name+' allowed')
    except OSError as e:assert e.errno==errno.EPERM;denied[name]=e.errno
# chmod does not remove kernel byte seals. Test an O_RDWR proc alias without
# relying on DAC0440 as the reason for denial, then restore required metadata.
os.fchmod(fd,0o600)
alias=os.open('/proc/self/fd/198',os.O_RDWR)
try:
    try:os.pwrite(alias,b'x',0);raise AssertionError('proc alias allowed')
    except OSError as e:assert e.errno==errno.EPERM;denied['proc_alias']=e.errno
finally:os.close(alias);os.fchmod(fd,0o440)
s.verify_sealed_files(os.getpid(),specs,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid())
print(json.dumps({'same_pid_exec':True,'denied':denied,'sealed_files':len(proof['files'])}))
"""
        setup = """
import os,sys,json,hashlib,pwd
import core_asset_sandbox as s
data={n:{'raw':n.encode(),'bytes':len(n),'sha256':hashlib.sha256(n.encode()).hexdigest()} for n in s.SEALED_FDS}
specs=s._create_sealed_files(data,owner_uid=(os.getuid() or pwd.getpwnam('nobody').pw_uid),owner_gid=os.getgid())
os.execv(sys.executable,[sys.executable,'-B','-c',CHECKER,json.dumps(specs),str(os.getpid())])
""".replace('CHECKER',repr(checker))
        result=self.child(setup)
        self.assertTrue(result['same_pid_exec'])
        self.assertEqual(result['sealed_files'],2)
        self.assertEqual(set(result['denied']),{'pwrite','shrink','grow','shared_mmap','proc_alias'})


if __name__=='__main__':
    unittest.main()
