"""Linux privilege reduction for an already provisioned read-only asset volume.

This is not an installer and creates no process, mount or filesystem writes.
The caller is the existing Java launcher child, never the coordinator. V1 of
this contract accepts only a dedicated tmpfs whose *superblock* is read-only;
a read-only bind of writable storage is insufficient because another namespace
or /proc alias could expose writable backing data. Disk/image-backed filesystems
need a separate reviewed backing-storage verifier and are deliberately refused.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import re


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
    status = {}
    for line in _read(Path(proc_root)/str(pid)/'status').splitlines():
        if ':' in line:
            key,value = line.split(':',1)
            status[key] = value.strip()
    for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
        must(key in status and re.fullmatch('[0-9a-fA-F]+',status[key]) and int(status[key],16)==0,
             'asset_sandbox_capabilities_remaining')
    must(status.get('NoNewPrivs')=='1', 'asset_sandbox_no_new_privileges_required')
    proof.update({'capability_sets_zero':True,'no_new_privileges':True})
    return proof


def prepare(snapshot_root):
    """Irreversibly reduce only this launcher process before its Java exec.

    All failures terminate the launcher; the unchanged privileged coordinator
    can then recover its verified baseline. Never catch and continue an error.
    No mount unshare/fork means the lifecycle PID/start-ticks contract is intact.
    """
    must(os.name=='posix' and Path('/proc/self/status').exists(), 'asset_sandbox_linux_required')
    proof = filesystem_proof(snapshot_root)
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
    verify(os.getpid(),snapshot_root)
    return proof
