"""Installed Knowledge V2 -> Assistant-capable V2 controller successor.

No bootstrap downgrade and no independent production launcher. This helper is
called through the reviewed controller installation procedure under the same
R25/c5ea lock. Approval is an existing private owner/delegated-review record;
tests do not create project approval. Fixed targets exclude DB/data/credentials.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import re
import sys

# Formal source bundle must not execute stale sibling bytecode.
if __name__ == "__main__":
    folder=Path(__file__).absolute().parent
    if any(folder.glob("*.pyc")) or any(folder.glob("*.pyo")) or (folder/"__pycache__").exists():
        raise SystemExit("ASSISTANT_CONTROLLER_REFUSED: bundle_bytecode")
    sys.dont_write_bytecode=True

import assistant_runtime_overlay as overlay
import core_business
import core_release_guard as guard
from core_runtime import LIVE_FILES, env_values, replace_env
from upgrade_core_controller import ControlUpgradeRuntime, upgrade_lease
from publisher_transaction import Refused

SCHEMA='R25_ASSISTANT_CONTROLLER_UPGRADE_V1'
FILES=('assistant_release.py','assistant_runtime.py','assistant_runtime_overlay.py','assistant_acceptance.py','assistant_backup.py','upgrade_assistant_controller.py',
       'core_business.py','core_runtime.py','core_release_guard.py','core_publish.py','publisher_transaction.py','r25_storage.py',
       'ai_release_candidate.py','ai_release_guard.py','ai_runtime.py','ai_publish.py')
OPERATIONAL=('guard','critic-wrapper','lifecycle','ai-guard','ai-policy','policy','handoff')
PHASES={'PREPARED','INSTALL_INTENT','INSTALLED','RESTORE_INTENT','RESTORED','RECOVERY_REQUIRED'}


def must(ok,why):
    if not ok: raise Refused(why)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def validate(plan):
    must(type(plan)is dict and set(plan)=={'schema','from_policy_schema','deploy','current_release','next_owner','controller_owner','private_owner','files','operational','review_evidence_sha256'},'assistant_upgrade_plan_fields')
    must(plan['schema']==SCHEMA and plan['from_policy_schema']=='R25_CORE_BUSINESS_POLICY_V2','assistant_upgrade_requires_installed_v2')
    must(set(plan['files'])==set(FILES) and set(plan['operational'])==set(OPERATIONAL),'assistant_upgrade_exact_inventory')
    must(plan['next_owner']=='c5ea','assistant_next_owner')
    identity=plan['deploy']
    must(set(identity)=={'repository','ref','commit','run_id','run_attempt'} and identity['repository']=='bailangguihun/auralink-deploy' and identity['ref']=='refs/heads/release','assistant_upgrade_formal_repository')
    must(re.fullmatch('[a-f0-9]{40}',identity['commit']) and all(re.fullmatch('[1-9][0-9]{0,19}',identity[x]) for x in ('run_id','run_attempt')),'assistant_upgrade_formal_identity')
    must(re.fullmatch('[a-f0-9]{64}',plan['review_evidence_sha256']),'assistant_upgrade_review_evidence')
    for name,entry in {**plan['files'],**plan['operational']}.items():
        must(set(entry)=={'before_sha256','after_sha256'},'assistant_upgrade_file_fields')
        for value in entry.values():
            must(value is None or (type(value)is str and re.fullmatch('[a-f0-9]{64}',value)),'assistant_upgrade_hash')
        must(entry['after_sha256']is not None,'assistant_upgrade_after_required')
        if name in OPERATIONAL:must(entry['before_sha256']is not None,'assistant_upgrade_installed_controls_required')
    for field in ('controller_owner','private_owner'):
        must(type(plan[field])is list and len(plan[field])==2 and all(type(x)is int and x>=0 for x in plan[field]),'assistant_upgrade_owner')
    return plan


def targets(plan):
    root=guard.ROOT
    result={name:(root/'operations/r25-publisher'/name,tuple(plan['private_owner']),0o600) for name in FILES}
    result.update(policy=(guard.STORE/'POLICY.json',tuple(plan['private_owner']),0o600),
        handoff=(LIVE_FILES['handoff'],tuple(plan['private_owner']),0o600),
        guard=(root/'operations/core_release_guard.py',tuple(plan['controller_owner']),0o700),
        **{'critic-wrapper':(root/'operations/r25-private-critic-env-policy-v2.py',tuple(plan['controller_owner']),0o700),
           'lifecycle':(root/'operations/lifecycle_adapter.py',tuple(plan['controller_owner']),0o700),
           'ai-policy':(root/'runtime/ai-publications/POLICY.json',tuple(plan['private_owner']),0o600),
           'ai-guard':(root/'operations/ai_release_guard.py',tuple(plan['controller_owner']),0o700)})
    return result


def entries(plan):return {**plan['files'],**plan['operational']}


def source(bundle,name):
    return bundle/({'policy':'POLICY.next.json','handoff':'HANDOFF.next.env','guard':'core_release_guard.py','critic-wrapper':'r25-private-critic-env-policy-v2.py','lifecycle':'lifecycle_adapter.py','ai-policy':'AI_POLICY.next.json','ai-guard':'ai_release_guard.py'}.get(name,name))


def verify(rt,plan,bundle,*,mixed=False,after=False):
    validate(plan);rt.require_lease();rt.require_terminal_application_transactions()
    must(asdict(rt.current())==plan['current_release'],'assistant_upgrade_current_drift')
    must(bundle==guard.ROOT/'operations/r25-controller-candidates'/plan['deploy']['commit'],'assistant_upgrade_fixed_bundle')
    for name,entry in entries(plan).items():
        rt.identity(source(bundle,name),expected_sha256=entry['after_sha256'])
        target,owner,mode=targets(plan)[name]
        if not target.exists():
            must(entry['before_sha256']is None and not after and not target.is_symlink(),'assistant_upgrade_missing_old_file');continue
        observed=rt.identity(target,expected_owner=owner,expected_mode=mode)['sha256']
        allowed={entry['after_sha256']} if after else ({entry['before_sha256'],entry['after_sha256']} if mixed else {entry['before_sha256']})
        must(observed in allowed,'assistant_upgrade_foreign_drift')


def rendered_bindings(rt,plan,bundle):
    old=rt.read(guard.STORE/'POLICY.json',plan['operational']['policy']['before_sha256'])
    new=rt.read(bundle/'POLICY.next.json',plan['operational']['policy']['after_sha256'])
    must(old['schema']=='R25_CORE_BUSINESS_POLICY_V2' and new['schema']==old['schema'] and new['upgrade']['capability']=='assistant-v1','assistant_upgrade_policy_transition')
    must(new['upgrade']['baseline_release']==plan['current_release'] and old['installation']==new['installation'],'assistant_upgrade_identity_preserved')
    must(old['upgrade']['assets']==new['upgrade']['assets'] and old['upgrade']['configuration']['knowledge']==new['upgrade']['configuration']['knowledge'],'assistant_upgrade_knowledge_preserved')
    must(new['installation']['controller_owner']==plan['controller_owner'] and new['installation']['private_owner']==plan['private_owner'],'assistant_upgrade_owner_binding')
    for name in new['runtime_modules']:
        expected=plan['files'][name]['after_sha256'] if name in plan['files'] else old['runtime_modules'][name]
        must(new['runtime_modules'][name]==expected,'assistant_upgrade_runtime_bindings')
    must(new['controllers']['core_release_guard.py']==plan['files']['core_release_guard.py']['after_sha256'] and
         new['controllers']['lifecycle_adapter.py']==plan['operational']['lifecycle']['after_sha256'] and
         new['controllers']['r25-production-java-launch.py']==old['controllers']['r25-production-java-launch.py'],'assistant_upgrade_controller_bindings')
    wrapper=guard.read_file(targets(plan)['critic-wrapper'][0],owner=tuple(plan['controller_owner']),mode=0o700,
                             expected=plan['operational']['critic-wrapper']['before_sha256'])
    after_wrapper=overlay.render(wrapper)
    must(sha(after_wrapper)==plan['operational']['critic-wrapper']['after_sha256'],'assistant_upgrade_wrapper_render')
    lifecycle=guard.read_file(targets(plan)['lifecycle'][0],owner=tuple(plan['controller_owner']),mode=0o700,
                             expected=plan['operational']['lifecycle']['before_sha256'])
    must(lifecycle.count(overlay.BASE_SHA256.encode())==1,'assistant_upgrade_lifecycle_wrapper_anchor')
    after_lifecycle=lifecycle.replace(overlay.BASE_SHA256.encode(),sha(after_wrapper).encode())
    must(sha(after_lifecycle)==plan['operational']['lifecycle']['after_sha256'],'assistant_upgrade_lifecycle_render')
    import ai_release_guard as ai_guard
    old_ai=rt.read(guard.ROOT/'runtime/ai-publications/POLICY.json',plan['operational']['ai-policy']['before_sha256'])
    new_ai=rt.read(bundle/'AI_POLICY.next.json',plan['operational']['ai-policy']['after_sha256'])
    must(old_ai.get('schema')=='R25_AI_SOURCE_POLICY_V1' and old_ai.get('source_paths')==list(ai_guard.SOURCE_PATHS),'assistant_ai_installed_v1_required')
    must(new_ai.get('schema')=='R25_AI_SOURCE_POLICY_V2' and new_ai.get('repository')=='bailangguihun/auralink-ai-service' and new_ai.get('source_paths')==list(ai_guard.ASSISTANT_PATHS),'assistant_ai_successor_inventory')
    must(new_ai.get('legacy_policy_sha256')==plan['operational']['ai-policy']['before_sha256'] and new_ai.get('dependency_sha256')==old_ai.get('dependency_sha256') and new_ai.get('review_evidence_sha256')==plan['review_evidence_sha256'],'assistant_ai_policy_binding')
    owner=new_ai.get('source_owner');must(type(owner)is list and len(owner)==2 and all(type(x)is int and x>=0 for x in owner),'assistant_ai_source_owner')
    for name in ai_guard.SOURCE_PATHS:
        rt.identity(guard.ROOT/'release'/name,expected_owner=tuple(owner),expected_mode=0o600)
    before=guard.read_file(LIVE_FILES['handoff'],owner=tuple(plan['private_owner']),expected=plan['operational']['handoff']['before_sha256'])
    after=replace_env(before,{'R25_CORE_RELEASE_POLICY_SHA256':plan['operational']['policy']['after_sha256'],
        'R25_CORE_RELEASE_GUARD_SHA256':plan['files']['core_release_guard.py']['after_sha256'],
        'R25_LIFECYCLE_ADAPTER_SHA256':plan['operational']['lifecycle']['after_sha256'],
        'R25_R24_CRITIC_ENV_WRAPPER_SHA256':plan['operational']['critic-wrapper']['after_sha256'],
        'R25_AI_RELEASE_GUARD_SHA256':plan['operational']['ai-guard']['after_sha256'],
        'R25_AI_RELEASE_POLICY_SHA256':plan['operational']['ai-policy']['after_sha256']})
    must(sha(after)==plan['operational']['handoff']['after_sha256'],'assistant_upgrade_handoff_render')
    # Execute only review-bound validator bytes from this formal controller
    # bundle; do not import an unverified candidate module or cached .pyc.
    validator_path=bundle/'core_business.py'
    validator_raw=guard.read_file(validator_path,owner=tuple(plan['private_owner']),expected=plan['files']['core_business.py']['after_sha256'])
    validator=guard.source_module(validator_path,'assistant_upgrade_policy_validator',validator_raw)
    validator.validate_policy(new)
    return new


def service_identities(engine):
    result={}
    for name,port in (('java',19080),('guide',19084),('critic',19085)):
        value=engine.active(name,port);must(value is not None,'assistant_upgrade_service_missing')
        result[name]={'pid':value['pid'],'ticks':value['ticks']}
    # Existing c5ea read-only status, never a second Next lifecycle owner.
    return result


def approval(rt,plan,expected):
    path=guard.STORE/'controller-upgrades'/expected
    record=path/'approval.json' if (path/'approval.json').exists() else guard.STORE/'CONTROL_UPGRADE_APPROVAL.json'
    must(rt.read(record,expected)==plan,'assistant_upgrade_private_approval_binding')
    return path


def install(rt,plan,bundle,*,approval_sha256):
    with upgrade_lease(rt):
        folder=approval(rt,plan,approval_sha256);journal_path=folder/'journal.json'
        if journal_path.exists():
            old=rt.read(journal_path)
            if old['phase']=='INSTALLED':verify(rt,plan,bundle,after=True);return 'INSTALLED_VERIFIED_NOOP'
            must(old['phase']=='RESTORED','assistant_upgrade_recovery_required')
        active=guard.STORE/'CONTROL_UPGRADE_ACTIVE.json'
        if active.exists():
            pointer=rt.read(active);previous=pointer.get('approval_sha256')
            must(type(previous)is str and re.fullmatch('[a-f0-9]{64}',previous),'assistant_upgrade_active_pointer')
            prior=rt.read(guard.STORE/'controller-upgrades'/previous/'journal.json')
            must(prior.get('phase')in ('INSTALLED','RESTORED'),'assistant_previous_controller_recovery_required')
        verify(rt,plan,bundle);rendered_bindings(rt,plan,bundle)
        rt.verify_current(rt.current());rt.require_no_active_work()
        engine=rt.engine();engine.frontend('status',rt.fd);before=service_identities(engine)
        rt.storage.mkdir_private(guard.STORE/'controller-upgrades');rt.storage.mkdir_private(folder);rt.storage.mkdir_private(folder/'before')
        if not (folder/'approval.json').exists():
            rt.storage.atomic_copy_file(guard.STORE/'CONTROL_UPGRADE_APPROVAL.json',folder/'approval.json',approval_sha256)
        for name,entry in entries(plan).items():
            if entry['before_sha256']is not None:
                path,owner,mode=targets(plan)[name]
                rt.storage.atomic_copy_file(path,folder/'before'/name,entry['before_sha256'],source_owner=owner,source_mode=mode)
        record={'schema':SCHEMA,'approval_sha256':approval_sha256,'phase':'PREPARED','service_identities':before}
        rt.write(journal_path,record)
        rt.write(guard.STORE/'CONTROL_UPGRADE_ACTIVE.json',{'schema':'R25_CORE_CONTROLLER_UPGRADE_ACTIVE_V1','approval_sha256':approval_sha256})
        engine.watchdog_stop_locked();record['phase']='INSTALL_INTENT';rt.write(journal_path,record)
        try:
            # Policy/handoff last; mixed state cannot launch applications.
            for name,entry in entries(plan).items():
                path,owner,mode=targets(plan)[name]
                rt.storage.atomic_copy_file(source(bundle,name),path,entry['after_sha256'],replace=entry['before_sha256']is not None,
                    expected_existing_sha256=entry['before_sha256'],target_owner=owner,mode=mode,existing_owner=owner,existing_mode=mode)
            verify(rt,plan,bundle,after=True)
            must(service_identities(engine)==before,'assistant_upgrade_unexpected_service_restart')
            engine.frontend('status',rt.fd)
            engine.watchdog_start_locked();must(engine.watchdog_identity(),'assistant_upgrade_watchdog')
            record['phase']='INSTALLED';rt.write(journal_path,record);return 'INSTALLED'
        except BaseException:
            record['phase']='RECOVERY_REQUIRED';rt.write(journal_path,record);raise


def recover(rt,plan,bundle,*,approval_sha256):
    with upgrade_lease(rt):
        folder=approval(rt,plan,approval_sha256);record=rt.read(folder/'journal.json')
        must(record['approval_sha256']==approval_sha256 and record['phase']in PHASES,'assistant_upgrade_recovery_phase')
        if record['phase']=='INSTALLED':verify(rt,plan,bundle,after=True);return 'INSTALLED_NO_RECOVERY'
        verify(rt,plan,bundle,mixed=True)
        # Mixed controllers cannot pass normal engine.load(). Use the exact
        # recorded lifecycle before-image solely for owned stop/recovery.
        path=folder/'before/lifecycle'
        raw=guard.read_file(path,owner=tuple(plan['private_owner']),expected=plan['operational']['lifecycle']['before_sha256'])
        import types
        module=types.ModuleType('assistant_controller_recovery_lifecycle');module.__file__=str(path)
        exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
        os.environ['R25_ROOT']=str(guard.ROOT)
        os.environ['ARTLIVE_R25_HANDOFF_CONFIG']=str(LIVE_FILES['handoff'])
        engine=module.production(rt.fd)
        engine.v=env_values(guard.read_file(folder/'before/handoff',owner=tuple(plan['private_owner']),expected=plan['operational']['handoff']['before_sha256']))
        engine.kind=engine.v.get('R25_LIFECYCLE_RELEASE_KIND')
        engine.watchdog_stop_locked()
        record['phase']='RESTORE_INTENT';rt.write(folder/'journal.json',record)
        for name,entry in entries(plan).items():
            path,owner,mode=targets(plan)[name]
            if not path.exists():continue
            actual=rt.identity(path,expected_owner=owner,expected_mode=mode)['sha256']
            if entry['before_sha256']is None:
                rt.storage.remove_bound_file(path,entry['after_sha256'],expected_owner=owner)
            else:
                rt.storage.atomic_copy_file(folder/'before'/name,path,entry['before_sha256'],replace=True,expected_existing_sha256=actual,
                    target_owner=owner,mode=mode,existing_owner=owner,existing_mode=mode)
        must(service_identities(engine)==record['service_identities'],'assistant_upgrade_service_drift')
        engine=rt.engine();rt.verify_current(rt.current())
        engine.watchdog_start_locked();must(engine.watchdog_identity(),'assistant_upgrade_watchdog')
        record['phase']='RESTORED';rt.write(folder/'journal.json',record);return 'RESTORED'


def main():
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('upgrade','recover'))
    parser.add_argument('--approval-sha256',required=True)
    args=parser.parse_args()
    try:
        guard.digest_value(args.approval_sha256)
        rt=ControlUpgradeRuntime()
        recorded=guard.STORE/'controller-upgrades'/args.approval_sha256/'approval.json'
        approval_file=recorded if args.command=='recover' and recorded.exists() else guard.STORE/'CONTROL_UPGRADE_APPROVAL.json'
        plan=validate(rt.read(approval_file,args.approval_sha256))
        bundle=guard.ROOT/'operations/r25-controller-candidates'/plan['deploy']['commit']
        must(Path(__file__).absolute()==bundle/'upgrade_assistant_controller.py','assistant_upgrade_trusted_bundle_location')
        rt.identity(Path(__file__),expected_sha256=plan['files']['upgrade_assistant_controller.py']['after_sha256'])
        result=(install if args.command=='upgrade' else recover)(rt,plan,bundle,approval_sha256=args.approval_sha256)
        print(json.dumps({'outcome':result,'application_restart':False,'database_writes':False}));return 0
    except Exception as error:
        print(json.dumps({'outcome':'ASSISTANT_CONTROLLER_REFUSED_OR_RECOVERY_REQUIRED','failure_class':type(error).__name__,
            'reason':str(error) if re.fullmatch('[a-z0-9_]+',str(error)) else 'private_diagnostic_required'}),file=sys.stderr);return 65


if __name__=='__main__':raise SystemExit(main())
