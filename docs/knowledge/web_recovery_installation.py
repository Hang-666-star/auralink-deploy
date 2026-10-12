#!/usr/bin/env python3
"""Reviewed one-off post-V1/pre-V2 four-file procedure; NOT EXECUTED in production.

No service activation, database access, new lifecycle owner or policy relaxation.
Prepare creates private before/after images; install/restore require a separately
approved plan digest. Do not derive approval from the plan's own printed hash.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import types

R25 = Path('/root/autodl-tmp/artlive-r25-native-pg16/handoff-production-20260923T062101Z')
WEB = Path('/root/autodl-tmp/auralink-web-deploy')
STAGE = R25/'operations/c5ea-recovery-installation-20261012'
CANDIDATE = R25/'operations/c5ea-recovery-candidate-20261012'
STORAGE_SHA = 'c0eb0f7c07f725b7218782f20e5e68768e39bf971f654bdd632f4b681085332c'
OWNER = (0, 0)
BEFORE = {'selection_commit.py':'25fe045b7de4d99bbe6b004c3961e3af1154b0cc765225d1272a6538d9c97cd4',
          'serialized_deploy_web.py':'1963c48dc821b5a771e2ce74dfdc1c3c445383da1a4a5b3d507a9caf6614f70b',
          'deploy-web.sh':'d6e8e522b85106790da3b5537a86330b305feef8caa2a4ced1c22739d79b8cdd'}
AFTER = {'selection_commit.py':'f96d2f885d1c099a20bdef031e03a3debc81ad01e0ae29e40066a0309dc7fd3d',
         'serialized_deploy_web.py':'d00cfd26d2f39b84cc944effdb1c35c3cd4823b3fa86cc54a37e4d9e167eb3a5',
         'deploy-web.sh':'ab1335aa5a655b4891f73fa5f2702af71bf50f7e6bb20ec7593ab01fe530d17e'}


def must(value, reason):
    if not value:raise ValueError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def file(path, mode=0o600, expected=None):
    must(all(not p.is_symlink() for p in (path,*path.parents)), 'symlink_path')
    s=path.lstat();must(stat.S_ISREG(s.st_mode) and (s.st_uid,s.st_gid,s.st_mode&0o777)==(*OWNER,mode),'file_identity')
    raw=path.read_bytes();must(len(raw)<=1024*1024,'metadata_size')
    if expected is not None:must(sha(raw)==expected,'file_hash')
    return raw


def settings(raw):
    values={}
    for line in raw.decode().splitlines():
        if not line or line.startswith('#'):continue
        must('=' in line,'handoff_syntax');k,v=line.split('=',1);must(k not in values,'handoff_duplicate');values[k]=v
    return values


def targets():return {**{name:WEB/'bin'/name for name in BEFORE},'handoff':R25/'runtime/handoff-control.env'}


def context_paths():
    return {'policy':R25/'runtime/core-publications/POLICY.json',
            'current':R25/'runtime/core-publications/CURRENT.json',
            'bootstrap':R25/'runtime/core-publications/bootstrap/journal.json',
            'selection':R25/'runtime/config/frontend-selection.json',
            'reference':R25/'runtime/config/frontend-selection.reference',
            'next_state':WEB/'runtime/production.state'}


def context():return {key:sha(file(path)) for key,path in context_paths().items()}


def phase_gate():
    c=context_paths();bootstrap=json.loads(file(c['bootstrap']));must(bootstrap.get('phase')=='INSTALLED','v1_bootstrap_not_installed')
    policy=file(c['policy']);must(json.loads(policy).get('schema')=='R25_CORE_EQUIVALENT_PAYLOAD_POLICY_V1','v1_policy_required')
    values=settings(file(targets()['handoff']));must(values.get('R25_CORE_RELEASE_POLICY_SHA256')==sha(policy),'v1_policy_binding')
    control=R25/'runtime/core-publications/CONTROL_UPGRADE_ACTIVE.json'
    must(not control.exists() and not control.is_symlink(),'v2_has_begun')
    for component in ('core','ai'):
        store=R25/'runtime'/f'{component}-publications';active=store/'ACTIVE.json'
        if active.exists() or active.is_symlink():
            identity=json.loads(file(active)).get('transaction_id');must(type(identity)is str and re.fullmatch('[0-9a-f]{32}',identity),'transaction_identity')
            journal=json.loads(file(store/'transactions'/identity/'journal.json'))
            must(journal.get('transaction_id')==identity and journal.get('phase') in {'COMMITTED','RESTORED'},'component_transaction_unfinished')
    for stage in (WEB/'runtime').glob('frontend-selection-transition-*'):
        state=json.loads(file(stage/'state.json'));must(state.get('state') in {'COMMITTED','BASELINE_RETAINED'},'web_transaction_unfinished')


def owned_next(fd):
    values=settings(file(targets()['handoff']));selector=R25/'operations/frontend_lifecycle_selector.py'
    must(values.get('R25_FRONTEND_SELECTOR')==str(selector),'selector_binding')
    expected=values.get('R25_FRONTEND_SELECTOR_SHA256','');must(re.fullmatch('[0-9a-f]{64}',expected),'selector_hash_binding')
    # The existing selector's separately verified script identity is numeric1000:1000/0700 at this site.
    s=selector.lstat();must(all(not p.is_symlink() for p in (selector,*selector.parents)) and (s.st_uid,s.st_gid,s.st_mode&0o777)==(1000,1000,0o700),'selector_identity')
    must(sha(selector.read_bytes())==expected,'selector_hash')
    selection=context_paths()['selection'];digest=sha(file(selection))
    result=subprocess.run(['/root/miniconda3/bin/python3','-B',str(selector),'status','--selection',str(selection),
                           '--selection-sha',digest,'--lease-fd',str(fd)],pass_fds=(fd,),
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,
                          env={'PATH':'/root/miniconda3/bin:/usr/bin:/bin','LANG':'C.UTF-8'})
    must(result.returncode==0,'owned_next_refused')


@contextmanager
def lease():
    path=WEB/'runtime/frontend-deployment.lock';file(path)
    original=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    fd=fcntl.fcntl(original,fcntl.F_DUPFD_CLOEXEC,10);os.close(original)
    try:
        a,b=os.fstat(fd),path.lstat();must((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'lock_inode')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        a,b=os.fstat(fd),path.lstat();must((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'lock_inode_after_acquisition')
        yield fd
    finally:os.close(fd)


def storage():
    source=R25/'operations/r25-publisher/r25_storage.py';raw=file(source,expected=STORAGE_SHA)
    module=types.ModuleType('reviewed_r25_storage');exec(compile(raw,str(source),'exec',dont_inherit=True),module.__dict__)
    return module.R25Storage([str(R25),str(WEB)],private_roots=[str(STAGE),str(CANDIDATE)])


def journal(store, phase, approved):
    path=STAGE/'journal.json';old=store.file_identity(path)['sha256'] if path.exists() else None
    store.atomic_write_json(path,{'phase':phase,'plan_sha256':approved},replace=old is not None,expected_existing_sha256=old)


def prepare(store,fd):
    phase_gate();owned_next(fd)
    store.validate_target(CANDIDATE,exists=True,directory=True,expected_owner=OWNER,expected_mode=0o700)
    must(not STAGE.exists() and not STAGE.is_symlink(),'stage_must_be_new')
    live=targets();handoff=file(live['handoff'])
    bootstrap=json.loads(file(context_paths()['bootstrap']))
    must(sha(handoff)==bootstrap['new_handoff_sha256'],'post_v1_handoff_required')
    old=('R25_FRONTEND_COMMIT_HELPER_SHA256='+BEFORE['selection_commit.py']+'\n').encode()
    new=('R25_FRONTEND_COMMIT_HELPER_SHA256='+AFTER['selection_commit.py']+'\n').encode()
    must(handoff.count(old)==1,'handoff_exact_helper_binding')
    changes={name:file(CANDIDATE/name,0o700,AFTER[name]) for name in BEFORE}
    changes['handoff']=handoff.replace(old,new,1)
    before={name:file(path,0o600 if name=='handoff' else 0o700,BEFORE.get(name)) for name,path in live.items()}
    store.mkdir_private(STAGE)
    for side in ('before','after'):store.mkdir_private(STAGE/side)
    plan={'schema':'ARTLIVE_C5EA_FOUR_FILE_PLAN_V1','stage':str(STAGE),'status':'PENDING_INDEPENDENT_APPROVAL',
          'context':context(),'files':{}}
    for name,path in live.items():
        store.atomic_write_bytes(STAGE/'before'/name,before[name]);store.atomic_write_bytes(STAGE/'after'/name,changes[name])
        plan['files'][name]={'target':str(path),'mode':0o600 if name=='handoff' else 0o700,
                             'before_sha256':sha(before[name]),'after_sha256':sha(changes[name])}
    store.atomic_write_json(STAGE/'plan.json',plan)
    digest=store.file_identity(STAGE/'plan.json')['sha256'];journal(store,'PREPARED',digest)
    return {'outcome':'PREPARED_PENDING_INDEPENDENT_APPROVAL','plan_sha256':digest}


def load_plan(store, approved):
    must(type(approved)is str and re.fullmatch('[0-9a-f]{64}',approved),'independent_approved_plan_sha_required')
    plan=store.read_private_record(STAGE/'plan.json',expected_sha256=approved)
    must(plan.get('schema')=='ARTLIVE_C5EA_FOUR_FILE_PLAN_V1' and plan.get('stage')==str(STAGE),'plan_identity')
    must(set(plan['files'])==set(targets()),'fixed_four_file_allowlist')
    for name,path in targets().items():
        entry=plan['files'][name];must(entry['target']==str(path) and entry['mode']==(0o600 if name=='handoff' else 0o700),'fixed_target_identity')
        for side in ('before','after'):store.file_identity(STAGE/side/name,expected_sha256=entry[side+'_sha256'])
        if name in BEFORE:must(entry['before_sha256']==BEFORE[name] and entry['after_sha256']==AFTER[name],'reviewed_script_hashes')
    old=(STAGE/'before/handoff').read_bytes();new=(STAGE/'after/handoff').read_bytes()
    oldline=('R25_FRONTEND_COMMIT_HELPER_SHA256='+BEFORE['selection_commit.py']+'\n').encode()
    newline=('R25_FRONTEND_COMMIT_HELPER_SHA256='+AFTER['selection_commit.py']+'\n').encode()
    must(old.count(oldline)==1 and new==old.replace(oldline,newline,1),'handoff_single_binding_only')
    j=store.read_private_record(STAGE/'journal.json');must(j.get('plan_sha256')==approved,'journal_plan_binding')
    return plan,j


def apply(store,fd,approved,restore=False):
    plan,j=load_plan(store,approved);phase_gate();must(context()==plan['context'],'baseline_context_changed')
    terminal='RESTORED' if restore else 'INSTALLED';side='before' if restore else 'after'
    allowed={'PREPARED','INSTALLING','INSTALLED','RESTORING','RESTORED'} if restore else {'PREPARED','INSTALLED'}
    must(j.get('phase') in allowed,'partial_install_use_restore')
    live=targets();observed={name:store.file_identity(path,expected_mode=plan['files'][name]['mode'])['sha256'] for name,path in live.items()}
    for name,digest in observed.items():
        item=plan['files'][name]
        expected={item['before_sha256'],item['after_sha256']} if restore else {item['after_sha256'] if j['phase']=='INSTALLED' else item['before_sha256']}
        must(digest in expected,'foreign_drift_refused')
    if j['phase']==terminal:
        must(all(observed[n]==plan['files'][n][side+'_sha256'] for n in live),'terminal_file_disagreement')
        owned_next(fd);return {'outcome':terminal+'_VERIFIED_NOOP'}
    owned_next(fd);journal(store,'RESTORING' if restore else 'INSTALLING',approved)
    # Order keeps entry's digest refusal closed until all bindings agree. Restore is reverse order.
    order=list(live);order=order[::-1] if restore else order
    for name in order:
        item=plan['files'][name];target=item[side+'_sha256']
        if observed[name]!=target:
            store.atomic_copy_file(STAGE/side/name,live[name],target,mode=item['mode'],replace=True,
                                   expected_existing_sha256=observed[name],existing_mode=item['mode'])
        store.file_identity(live[name],expected_sha256=target,expected_mode=item['mode'])
    must(context()==plan['context'],'post_install_context_changed');owned_next(fd)
    journal(store,terminal,approved);return {'outcome':terminal,'services_restarted':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['prepare','install','restore'])
    parser.add_argument('--approved-plan-sha256');args=parser.parse_args()
    must(os.geteuid()==0,'root_operator');store=storage()
    with lease() as fd:
        result=prepare(store,fd) if args.mode=='prepare' else apply(store,fd,args.approved_plan_sha256,args.mode=='restore')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
