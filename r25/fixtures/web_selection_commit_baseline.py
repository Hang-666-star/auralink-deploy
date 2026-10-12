#!/usr/bin/env python3
"""Crash-reconcilable private selection/reference commit; no PID or DB writes.

The caller must hold the common frontend lease. Both saved old/new pairs are
verified before any live write. A caller-provided actual owned-Next check must
pass before commit/recovery. The reference is the LAST commit point; a partial
selection write fails closed in R25 rather than selecting an arbitrary release.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat

class Refused(RuntimeError):pass
def must(ok,reason):
    if not ok:raise Refused(reason)
def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):result.update(block)
    return result.hexdigest()
def guard(path,digest=None,kind='file'):
    must(all(not p.is_symlink() for p in [path,*path.parents]),'symlink_path')
    value=path.lstat()
    desired=stat.S_ISDIR if kind=='dir' else stat.S_ISREG
    must(desired(value.st_mode) and (value.st_uid,value.st_gid,value.st_mode&0o777)==(0,0,0o700 if kind=='dir' else 0o600),'private_identity')
    if digest:must(sha(path)==digest,'saved_pair_hash')
def atomic(path,data):
    temp=path.with_name(path.name+'.selection-ready')
    must(not temp.exists() and not temp.is_symlink(),'temporary_conflict')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    directory=os.open(path.parent,os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory)
    finally:os.close(directory)
def reference(data):
    config=json.loads(data)
    return ('schema=ARTLIVE_FRONTEND_SELECTION_REFERENCE_V1\nselection_sha256='+hashlib.sha256(data).hexdigest()+
            '\ncommit_sha='+config['commit_sha']+'\nbuild_id='+config['build_id']+'\n').encode()

class Commit:
    def __init__(self,selection,ref,stage):
        self.selection,self.ref,self.stage=selection,ref,stage
        self.journal=stage/'state.json'
    def record(self,state,extra=None):
        old=json.loads(self.journal.read_text()) if self.journal.exists() else {}
        old.update(state=state,selection=str(self.selection),reference=str(self.ref),stage=str(self.stage))
        if extra:old.update(extra)
        atomic(self.journal,(json.dumps(old,sort_keys=True)+'\n').encode())
    def capture(self):
        guard(self.selection);guard(self.ref)
        must(self.ref.read_bytes()==reference(self.selection.read_bytes()),'old_reference_binding')
        must(not self.stage.exists() and not self.stage.is_symlink(),'stage_not_fresh')
        self.stage.mkdir(mode=0o700)
        atomic(self.stage/'old.selection',self.selection.read_bytes())
        atomic(self.stage/'old.reference',self.ref.read_bytes())
        self.record('BASELINE_CAPTURED',dict(old_selection_sha=sha(self.stage/'old.selection'),old_reference_sha=sha(self.stage/'old.reference')))
    def bind_new(self,data):
        guard(self.stage,kind='dir');guard(self.journal)
        current=json.loads(self.journal.read_text())
        must(current['state']=='BASELINE_CAPTURED','bind_state')
        atomic(self.stage/'new.selection',data);atomic(self.stage/'new.reference',reference(data))
        self.record('PREPARED',dict(new_selection_sha=sha(self.stage/'new.selection'),new_reference_sha=sha(self.stage/'new.reference')))
    def verified(self):
        guard(self.stage,kind='dir');guard(self.journal)
        value=json.loads(self.journal.read_text())
        must(value['selection']==str(self.selection) and value['reference']==str(self.ref) and value['stage']==str(self.stage),'state_identity')
        for prefix in ['old','new']:
            for name in ['selection','reference']:guard(self.stage/(prefix+'.'+name),value[prefix+'_'+name+'_sha'])
            must((self.stage/(prefix+'.reference')).read_bytes()==reference((self.stage/(prefix+'.selection')).read_bytes()),'saved_reference_binding')
        return value
    def finish(self,check_owned_next):
        value=self.verified()
        must(value['state'] in {'PREPARED','CONFIG_INSTALLED','COMMITTED'},'commit_state')
        guard(self.selection);guard(self.ref)
        must(sha(self.selection) in {value['old_selection_sha'],value['new_selection_sha']} and
             sha(self.ref) in {value['old_reference_sha'],value['new_reference_sha']},'unknown_live_pair')
        must(not (sha(self.ref)==value['new_reference_sha'] and sha(self.selection)!=value['new_selection_sha']),'invalid_commit_order')
        check_owned_next(self.stage/'new.selection',value['new_selection_sha'])
        if sha(self.selection)!=value['new_selection_sha']:
            atomic(self.selection,(self.stage/'new.selection').read_bytes())
        self.record('CONFIG_INSTALLED')
        if sha(self.ref)!=value['new_reference_sha']:atomic(self.ref,(self.stage/'new.reference').read_bytes())
        must(sha(self.selection)==value['new_selection_sha'] and sha(self.ref)==value['new_reference_sha'],'final_pair_identity')
        self.record('COMMITTED')
