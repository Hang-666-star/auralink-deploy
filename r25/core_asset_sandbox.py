"""Linux privilege reduction and immutable Knowledge asset delivery.

This is not an installer and creates no process, mount or persistent writes.
The caller is the existing Java launcher child, never the coordinator. V1 of
this contract accepts only a dedicated tmpfs whose *superblock* is read-only;
a read-only bind of writable storage is insufficient because another namespace
or /proc alias could expose writable backing data. Disk/image-backed filesystems
need a separate reviewed backing-storage verifier and are deliberately refused.
The separate poetry-only sealed-memfd mode binds anonymous immutable byte objects
to two inherited descriptors; it does not describe its durable source as read-only.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat

SEALED_FDS = {'poetry-graph.json': 198, 'poetry-stats.json': 199}
REQUIRED_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                  fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
MAX_ASSET_BYTES = 32 * 1024 * 1024


class Refused(RuntimeError):
    pass


def must(value, reason):
    if not value:
        raise Refused(reason)


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        chunks, size = [], 0
        while True:
            raw = os.read(fd, 65536)
            if not raw:
                break
            size += len(raw)
            must(size <= 4*1024*1024, 'asset_sandbox_proc_limit')
            chunks.append(raw)
        return b''.join(chunks).decode('utf-8')
    finally:
        os.close(fd)


def _unescape(value):
    # Linux mountinfo uses precisely these escapes; reject unknown ambiguous
    # sequences rather than matching a different operator-approved path.
    value = re.sub(r'\\(040|011|012|134)', lambda m: chr(int(m[1],8)), value)
    return value


def filesystem_proof(snapshot_root, *, pid=None, proc_root=Path('/proc')):
    root = Path(snapshot_root)
    must(root.is_absolute() and '..' not in root.parts and str(root) == str(snapshot_root),
         'asset_sandbox_fixed_root')
    pid = os.getpid() if pid is None else pid
    must(type(pid) is int and pid > 0, 'asset_sandbox_process_identity')
    entries = []
    for line in _read(Path(proc_root)/str(pid)/'mountinfo').splitlines():
        fields = line.split()
        must(len(fields) >= 10 and fields.count('-') == 1, 'asset_sandbox_mountinfo')
        separator = fields.index('-')
        must(separator >= 6 and len(fields) >= separator+4, 'asset_sandbox_mountinfo')
        mountpoint = _unescape(fields[4])
        if mountpoint == str(root):
            entries.append((fields,separator))
        # A writable nested mount could otherwise punch a hole in the volume.
        must(not mountpoint.startswith(str(root).rstrip('/')+'/'), 'asset_sandbox_nested_mount')
    must(len(entries) == 1, 'asset_sandbox_dedicated_mount_required')
    fields, separator = entries[0]
    must(_unescape(fields[3]) == '/' and fields[separator+1] == 'tmpfs',
         'asset_sandbox_unsupported_backing_storage')
    mount_options, super_options = set(fields[5].split(',')), set(fields[separator+3].split(','))
    must({'ro','nosuid','nodev','noexec'} <= mount_options and 'rw' not in mount_options and
         'ro' in super_options and 'rw' not in super_options,
         'asset_sandbox_readonly_superblock_required')
    return {'filesystem':'tmpfs','superblock_read_only':True,'mount_read_only':True,
            'nosuid':True,'nodev':True,'noexec':True,'dedicated_mount':True}


def verify(pid, snapshot_root, *, proc_root=Path('/proc')):
    proof = filesystem_proof(snapshot_root, pid=pid, proc_root=proc_root)
    proof.update(_verify_privileges(pid, proc_root=proc_root))
    return proof


def _verify_privileges(pid, *, proc_root=Path('/proc')):
    status = {}
    for line in _read(Path(proc_root)/str(pid)/'status').splitlines():
        if ':' in line:
            key,value = line.split(':',1)
            status[key] = value.strip()
    for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
        must(key in status and re.fullmatch('[0-9a-fA-F]+',status[key]) and int(status[key],16)==0,
             'asset_sandbox_capabilities_remaining')
    must(status.get('NoNewPrivs')=='1', 'asset_sandbox_no_new_privileges_required')
    return {'capability_sets_zero':True,'no_new_privileges':True}


def prepare(snapshot_root):
    """Irreversibly reduce only this launcher process before its Java exec.

    All failures terminate the launcher; the unchanged privileged coordinator
    can then recover its verified baseline. Never catch and continue an error.
    No mount unshare/fork means the lifecycle PID/start-ticks contract is intact.
    """
    must(os.name=='posix' and Path('/proc/self/status').exists(), 'asset_sandbox_linux_required')
    proof = filesystem_proof(snapshot_root)
    _drop_privileges()
    verify(os.getpid(),snapshot_root)
    return proof


def _drop_privileges():
    library = ctypes.CDLL(None,use_errno=True)
    def prctl(option, arg=0, third=0):
        result = library.prctl(ctypes.c_int(option),ctypes.c_ulong(arg),ctypes.c_ulong(third),
                               ctypes.c_ulong(0),ctypes.c_ulong(0))
        must(result==0, 'asset_sandbox_privilege_transition_refused')
    # Clear ambient capabilities; disable UID0's exec capability restoration,
    # lock that choice, and forbid privilege gains via later exec/setuid files.
    prctl(47,4)  # PR_CAP_AMBIENT / PR_CAP_AMBIENT_CLEAR_ALL
    prctl(28,3)  # PR_SET_SECUREBITS / SECBIT_NOROOT | SECBIT_NOROOT_LOCKED
    prctl(38,1)  # PR_SET_NO_NEW_PRIVS
    last = int(_read(Path('/proc/sys/kernel/cap_last_cap')).strip())
    must(0 <= last <= 255, 'asset_sandbox_capability_range')
    for capability in range(last+1):
        prctl(24,capability)  # PR_CAPBSET_DROP; effective SETPCAP remains until capset.
    class Header(ctypes.Structure):
        _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
    header = Header(0x20080522,0)
    values = (Data*2)()
    must(library.capset(ctypes.byref(header),ctypes.byref(values))==0, 'asset_sandbox_capset_refused')


def _sealed_spec(artifacts, *, include_raw=False):
    must(type(artifacts) is dict and set(artifacts) == set(SEALED_FDS),
         'asset_sandbox_sealed_file_set')
    specs = {}
    expected_keys = {'sha256', 'bytes', 'raw'} if include_raw else {'sha256', 'bytes'}
    for name, item in artifacts.items():
        must(type(item) is dict and set(item) == expected_keys and
             type(item['bytes']) is int and 0 < item['bytes'] <= MAX_ASSET_BYTES and
             type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']),
             'asset_sandbox_sealed_spec')
        if include_raw:
            must(type(item['raw']) is bytes and len(item['raw']) == item['bytes'] and
                 hashlib.sha256(item['raw']).hexdigest() == item['sha256'],
                 'asset_sandbox_sealed_source_identity')
        specs[name] = {'sha256': item['sha256'], 'bytes': item['bytes']}
    return specs


def verify_sealed_files(pid, artifacts, *, owner_uid, owner_gid, proc_root=Path('/proc')):
    """Prove actual immutable descriptor bytes, not a name or launcher receipt.

    The lifecycle caller binds PID/start ticks around this proof. Opening these
    proc descriptor links intentionally follows the kernel's magic link; each
    resulting object must itself be anonymous, sealed and hash/length bound.
    This also rejects an ordinary chmod-only file or a sealed lookalike name.
    """
    specs = _sealed_spec(artifacts)
    _sealed_owner(owner_uid, owner_gid)
    must(type(pid) is int and pid > 0, 'asset_sandbox_process_identity')
    files, identities = {}, set()
    for name, number in SEALED_FDS.items():
        try:
            fd = os.open(Path(proc_root)/str(pid)/'fd'/str(number), os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            raise Refused('asset_sandbox_sealed_descriptor_missing') from error
        try:
            info = os.fstat(fd)
            must(stat.S_ISREG(info.st_mode) and info.st_nlink == 0 and
                 stat.S_IMODE(info.st_mode) == 0o440 and
                 (info.st_uid, info.st_gid) == (owner_uid, owner_gid),
                 'asset_sandbox_sealed_object_type')
            identity = (info.st_dev, info.st_ino)
            must(identity not in identities, 'asset_sandbox_sealed_objects_not_distinct')
            identities.add(identity)
            try:
                seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            except OSError as error:
                raise Refused('asset_sandbox_sealed_proof_unavailable') from error
            must(seals & REQUIRED_SEALS == REQUIRED_SEALS, 'asset_sandbox_seals_incomplete')
            expected = specs[name]
            must(info.st_size == expected['bytes'], 'asset_sandbox_sealed_size')
            digest, size = hashlib.sha256(), 0
            while True:
                raw = os.read(fd, 65536)
                if not raw:
                    break
                size += len(raw)
                must(size <= expected['bytes'], 'asset_sandbox_sealed_size')
                digest.update(raw)
            must(size == expected['bytes'] and digest.hexdigest() == expected['sha256'],
                 'asset_sandbox_sealed_digest')
            files[name] = {'fd': number, 'bytes': size, 'sha256': expected['sha256'],
                           'seals': seals, 'owner_uid': owner_uid, 'owner_gid': owner_gid}
        finally:
            os.close(fd)
    return {'transport': 'sealed-memfd-v1', 'immutable_bytes': True, 'files': files}


def verify_sealed(pid, artifacts, *, owner_uid, owner_gid, proc_root=Path('/proc')):
    proof = verify_sealed_files(pid, artifacts, owner_uid=owner_uid, owner_gid=owner_gid, proc_root=proc_root)
    proof.update(_verify_privileges(pid, proc_root=proc_root))
    return proof


def _sealed_owner(owner_uid, owner_gid):
    # UID0 is the reviewed service identity for this mode. A different inode
    # owner prevents that root-identity process from chmod/chown after capdrop,
    # including adding execute permission on kernels predating MFD_NOEXEC_SEAL.
    must(type(owner_uid) is int and owner_uid > 0 and
         type(owner_gid) is int and owner_gid >= 0, 'asset_sandbox_sealed_owner')


def _create_sealed_files(artifacts, *, owner_uid, owner_gid):
    """Launcher-child internal step; never called by the coordinator."""
    specs = _sealed_spec(artifacts, include_raw=True)
    _sealed_owner(owner_uid, owner_gid)
    # Do not clobber inherited launcher/coordinator descriptors. This hook runs
    # before Java creates threads, so a new descriptor cannot race these slots.
    must(len(list(Path('/proc/self/task').iterdir())) == 1, 'asset_sandbox_single_thread_required')
    for target in SEALED_FDS.values():
        try:
            os.fstat(target)
        except OSError as error:
            must(error.errno == errno.EBADF, 'asset_sandbox_sealed_descriptor_probe')
        else:
            raise Refused('asset_sandbox_sealed_descriptor_occupied')
    created = set()
    try:
        for name, target in SEALED_FDS.items():
            try:
                fd = os.memfd_create('artlive-' + name, os.MFD_ALLOW_SEALING)
            except (AttributeError, OSError) as error:
                raise Refused('asset_sandbox_memfd_unavailable') from error
            created.add(fd)
            raw, offset = artifacts[name]['raw'], 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                must(written > 0, 'asset_sandbox_sealed_write')
                offset += written
            os.fchown(fd, owner_uid, owner_gid)
            os.fchmod(fd, 0o440)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, REQUIRED_SEALS)
            os.lseek(fd, 0, os.SEEK_SET)
            if fd != target:
                os.dup2(fd, target, inheritable=True)
                created.add(target)
                os.close(fd)
                created.remove(fd)
            else:
                os.set_inheritable(target, True)
        verify_sealed_files(os.getpid(), specs, owner_uid=owner_uid, owner_gid=owner_gid)
        return specs
    except BaseException:
        for fd in created:
            os.close(fd)
        raise


def prepare_sealed(artifacts, *, owner_uid, owner_gid):
    """Bind two sealed inherited objects and reduce this launcher before exec.

    Caller must terminate on any error, including a partially applied privilege
    transition. There is no fallback to source paths or unprotected descriptors.
    Same PID/start ticks and all existing lifecycle ownership remain unchanged.
    """
    must(os.name == 'posix' and Path('/proc/self/status').exists(), 'asset_sandbox_linux_required')
    specs = _create_sealed_files(artifacts, owner_uid=owner_uid, owner_gid=owner_gid)
    try:
        _drop_privileges()
        return verify_sealed(os.getpid(), specs, owner_uid=owner_uid, owner_gid=owner_gid)
    except BaseException:
        for fd in SEALED_FDS.values():
            os.close(fd)
        raise
