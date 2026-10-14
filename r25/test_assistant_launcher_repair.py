"""Strict three-file repair: real temp files, flock, atomic copies and CAS.

OS service identities, c5ea status and AIRuntime source/recovery validation are
explicit injected boundaries. No production path/network/DB/process mutation.
Synthetic private plans are not project approvals or formal release evidence.
"""
from dataclasses import asdict
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, PropertyMock
import zipfile

import ai_runtime
import core_runtime
import upgrade_core_controller as original
import upgrade_assistant_controller as repair
from publisher_transaction import Release
from r25_storage import R25Storage


class Runtime(original.ControlUpgradeRuntime):
    def __init__(self,root,store):
        self.storage=R25Storage([str(root)],os.getuid(),os.getgid());self.fd=None;self.store=store
    def current(self):return Release(**self.read(self.store/'CURRENT.json')['release'])


class Repair(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=self.root/'runtime/core-publications'
        self.bundle=self.root/'operations/r25-controller-candidates'/('d'*40)
        self.rt=Runtime(self.root,self.store);self.owner=[os.getuid(),os.getgid()]
        for directory in ('runtime','runtime/core-publications','runtime/ai-publications','runtime/ai-publications/transactions',
                'runtime/ai-publications/transactions/'+repair.REPAIR_TX,'operations','operations/r25-publisher',
                'operations/r25-controller-candidates','operations/r25-controller-candidates/'+('d'*40),'release'):
            self.rt.storage.mkdir_private(self.root/directory)
        self.put(self.root/'lock',b'fixture lock')
        self.handoff=self.root/'runtime/handoff-control.env'
        self.live={'handoff':self.handoff,'release-jar':self.root/'release/backend.jar','preview-jar':self.root/'runtime/preview.jar',
            'manifest':self.root/'release/MANIFEST.json','application':self.root/'runtime/application.yml'}
        for module,name,value in ((repair.guard,'ROOT',self.root),(repair.guard,'STORE',self.store),
                (original,'LOCK',self.root/'lock'),(repair,'LIVE_FILES',self.live)):
            patched=patch.object(module,name,value);patched.start();self.addCleanup(patched.stop)
        jar=b'exact compatible existing jar';self.release=Release('a'*40,repair.sha(jar),'c'*64)
        self.put(self.live['release-jar'],jar);self.put(self.live['preview-jar'],jar)
        app=self.put(self.live['application'],b'unchanged application settings\n')
        live_manifest=self.write(self.live['manifest'],{'entries':[{'path':'artifacts/backend.jar','sha256':self.release.artifact_sha256}]})
        self.write(self.store/'CURRENT.json',{'schema':'R25_CORE_CURRENT_V1','release':asdict(self.release)})
        fixed=(Path(__file__).parent/'assistant_release.py').read_bytes()
        self.assertEqual(fixed.count(repair.REPAIR_NEW),1)
        oldcode=fixed.replace(repair.REPAIR_NEW,repair.REPAIR_OLD)
        self.code=self.root/'operations/r25-publisher/assistant_release.py';self.put(self.code,oldcode)
        self.review=self.write(self.store/'LAUNCHER_IMPORT_REPAIR_REVIEW.json',{'purpose':'synthetic isolated fixture, not real approval'})
        old={'schema':'R25_CORE_BUSINESS_POLICY_V2','installation':{'private_owner':self.owner,'controller_owner':self.owner},
             'controllers':{},'runtime_modules':{'assistant_release.py':repair.sha(oldcode)},
             'upgrade':{'capability':'assistant-v1','baseline_release':asdict(self.release),
                 'assets':{'retained':'unchanged'},'configuration':{'knowledge':{'map-enabled':False},'before_sha256':app},
                 'assistant':{'artifacts':{'deploy':{'repository':'bailangguihun/auralink-deploy','commit':'e'*40,'sha256':'e'*64}},
                     'review_evidence_sha256':'e'*64,'compatible_recovery_jar_sha256':self.release.artifact_sha256}}}
        old_policy=self.write(self.store/'POLICY.json',old)
        before_handoff=('R25_CORE_RELEASE_POLICY_SHA256='+old_policy+'\nR25_BACKEND_SHA256='+self.release.artifact_sha256+'\nOTHER=retained\n').encode();self.put(self.handoff,before_handoff)
        original_plan={'schema':repair.SCHEMA,'current_release':asdict(self.release),'operational':{'policy':{'after_sha256':old_policy},'handoff':{'after_sha256':repair.sha(before_handoff)}},
            'files':{'assistant_release.py':{'after_sha256':repair.sha(oldcode)}}}
        raw=json.dumps(original_plan).encode();control_sha=repair.sha(raw)
        control=self.store/'controller-upgrades'/control_sha
        self.rt.storage.mkdir_private(control.parent);self.rt.storage.mkdir_private(control)
        self.put(control/'approval.json',raw)
        control_journal=self.write(control/'journal.json',{'schema':repair.SCHEMA,'approval_sha256':control_sha,'phase':'INSTALLED'})
        self.write(self.store/'CONTROL_UPGRADE_ACTIVE.json',{'schema':'R25_CORE_CONTROLLER_UPGRADE_ACTIVE_V1','approval_sha256':control_sha})
        self.original_control_bytes=(control/'journal.json').read_bytes()
        self.control_folder=control
        self.ai_store=self.root/'runtime/ai-publications';self.ai_folder=self.ai_store/'transactions'/repair.REPAIR_TX
        self.source=self.root/'release/source.py';self.put(self.source,b'original old source\n')
        self.old_ai={'commit_sha':'f'*40,'source_tree_sha256':'f'*64,'record_sha256':'f'*64}
        snapshot={'core':asdict(self.release),'current':self.old_ai,'changed_roles':['critic'],
            'before_health':{'guide_pid':123,'guide_start_ticks':'456'}}
        snap_sha=self.write(self.ai_folder/'snapshot.json',snapshot)
        self.journal={'schema':'R25_AI_TRANSACTION_V1','transaction_id':repair.REPAIR_TX,'phase':'RECOVERY_REQUIRED',
            'snapshot_sha256':snap_sha,'history':[{'phase':'START_INTENT'},{'phase':'RESTORE_START_INTENT'},{'phase':'RECOVERY_REQUIRED'}]}
        ai_journal=self.write(self.ai_folder/'journal.json',self.journal)
        ai_active=self.write(self.ai_store/'ACTIVE.json',{'schema':'R25_AI_ACTIVE_V1','transaction_id':repair.REPAIR_TX})
        ai_current=self.write(self.ai_store/'CURRENT.json',{'schema':'R25_AI_CURRENT_V1','release':self.old_ai})
        self.services={'guide':{'pid':123,'ticks':'456'},'critic':{'pid':789,'ticks':'1011'}}
        self.java=False;self.watchdog=False;self.frontend_reads=0
        self.engine=SimpleNamespace(active=self.active,watchdog_identity=lambda:({'pid':8,'ticks':'8'} if self.watchdog else None),frontend=self.frontend)
        here=Path(__file__).parent;payload={name:(here/name).read_bytes() for name in sorted(repair.REPAIR_BUNDLE_FILES)}
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as zipped:
            for name,content in payload.items():
                entry=zipfile.ZipInfo(name);entry.external_attr=(0o100600<<16);zipped.writestr(entry,content)
                self.put(self.bundle/name,content)
        archive_raw=archive.getvalue();archive_sha=repair.sha(archive_raw);self.put(self.bundle/'r25-controller.zip',archive_raw)
        manifest={'schema':1,'repository':'bailangguihun/auralink-deploy','ref':'refs/heads/release','commit':'d'*40,'run_id':'42','run_attempt':'1',
            'status':'NOT_DEPLOYED','installation_performed':False,
            'archive':{'name':'r25-controller.zip','bytes':len(archive_raw),'sha256':archive_sha},
            'files':[{'path':name,'bytes':len(value),'sha256':repair.sha(value)} for name,value in payload.items()]}
        manifest_sha=self.write(self.bundle/'r25-controller-manifest.json',manifest)
        new=copy.deepcopy(old);new['runtime_modules']['assistant_release.py']=repair.sha(fixed)
        new['upgrade']['assistant']['artifacts']['deploy']={'repository':'bailangguihun/auralink-deploy','commit':'d'*40,'sha256':archive_sha}
        new['upgrade']['assistant']['review_evidence_sha256']=self.review
        new_policy=self.write(self.bundle/'POLICY.next.json',new)
        after_handoff=core_runtime.replace_env(before_handoff,{'R25_CORE_RELEASE_POLICY_SHA256':new_policy});self.put(self.bundle/'HANDOFF.next.env',after_handoff)
        self.plan={'schema':repair.REPAIR_SCHEMA,'next_owner':'c5ea','private_owner':self.owner,'controller_owner':self.owner,
            'deploy':{k:manifest[k] for k in ('repository','ref','commit','run_id','run_attempt')},
            'installed_control':{'approval_sha256':control_sha,'journal_sha256':control_journal},'current_release':asdict(self.release),
            'preserved':{'release-jar':self.release.artifact_sha256,'preview-jar':self.release.artifact_sha256,'application':app,'manifest':live_manifest},
            'ai':{'transaction_id':repair.REPAIR_TX,'active_sha256':ai_active,'journal_sha256':ai_journal,'snapshot_sha256':snap_sha,'current_sha256':ai_current,'source_tree_sha256':'f'*64},
            'services':copy.deepcopy(self.services),'review_evidence_sha256':self.review,
            'files':{'assistant_release.py':{'before_sha256':repair.sha(oldcode),'after_sha256':repair.sha(fixed)},
                     'policy':{'before_sha256':old_policy,'after_sha256':new_policy},
                     'handoff':{'before_sha256':repair.sha(before_handoff),'after_sha256':repair.sha(after_handoff)}}}
        self.plan['deploy'].update(archive_sha256=archive_sha,manifest_sha256=manifest_sha,tool_sha256=repair.sha(payload['upgrade_assistant_controller.py']))
        self.rebind()
        outer=self
        class FakeAIRuntime:
            def validate_recovery(self,tx):
                self.core.require_lease();outer.assertEqual(tx,repair.REPAIR_TX)
                return outer.rt.read(outer.ai_folder/'journal.json'),outer.rt.read(outer.ai_folder/'snapshot.json')
            def current(self):return outer.rt.read(outer.ai_store/'CURRENT.json')['release']
        for patched in (patch.object(ai_runtime,'AIRuntime',FakeAIRuntime),
                        patch.object(ai_runtime.guard,'verify_live',side_effect=self.verify_old),
                        patch.object(repair,'launcher_repair_engine',return_value=self.engine)):
            patched.start();self.addCleanup(patched.stop)
    def put(self,path,value):return self.rt.storage.atomic_write_bytes(path,value)['sha256']
    def write(self,path,value):return self.rt.storage.atomic_write_json(path,value)['sha256']
    def rebind(self):
        path=self.store/'LAUNCHER_IMPORT_REPAIR_APPROVAL.json'
        if path.exists():path.unlink()
        self.approval=self.write(path,self.plan)
    def active(self,role,port):
        expected={'java':19080,'guide':19084,'critic':19085};self.assertEqual(port,expected[role])
        return ({'pid':33,'ticks':'3'} if self.java else None) if role=='java' else self.services.get(role)
    def frontend(self,mode,fd):self.rt.require_lease();self.assertEqual(mode,'status');self.frontend_reads+=1
    def verify_old(self,ref):
        self.assertEqual(ref,self.old_ai);repair.must(self.source.read_bytes()==b'original old source\n','fixture_old_source_drift')
    def run_repair(self,recovery=False):return repair.repair_launcher_import(self.rt,self.plan,self.bundle,approval_sha256=self.approval,recovery=recovery)
    def hashes(self):return {name:repair.sha(path.read_bytes()) for name,(path,*_) in repair.launcher_repair_targets(self.plan).items()}
    def assert_before(self):self.assertEqual(self.hashes(),{n:v['before_sha256'] for n,v in self.plan['files'].items()})
    def test_exact_repair_repeat_three_files_no_original_journal_mutation(self):
        self.assertEqual(self.run_repair(),'LAUNCHER_IMPORT_REPAIR_INSTALLED')
        self.assertEqual(self.run_repair(),'LAUNCHER_IMPORT_REPAIR_INSTALLED_NOOP')
        self.assertEqual(self.hashes(),{n:v['after_sha256'] for n,v in self.plan['files'].items()})
        self.assertEqual((self.control_folder/'journal.json').read_bytes(),self.original_control_bytes)
        self.assertEqual(self.rt.read(self.ai_folder/'journal.json'),self.journal)
        self.assertGreater(self.frontend_reads,0)
    def test_partial_copy_refuses_replay_and_explicit_recovery_restores_only_three(self):
        original_copy=self.rt.storage.atomic_copy_file;failed=False
        def copy(src,dst,*args,**kwargs):
            nonlocal failed
            if Path(dst)==self.store/'POLICY.json' and not failed:failed=True;raise OSError('injected')
            return original_copy(src,dst,*args,**kwargs)
        with patch.object(self.rt.storage,'atomic_copy_file',side_effect=copy),self.assertRaises(OSError):self.run_repair()
        with self.assertRaisesRegex(Exception,'explicit_recovery'):self.run_repair()
        self.assertEqual(self.run_repair(recovery=True),'LAUNCHER_IMPORT_REPAIR_RESTORED');self.assert_before()
        self.assertEqual(self.run_repair(recovery=True),'LAUNCHER_IMPORT_REPAIR_RESTORED_NOOP')
        self.assertEqual(self.run_repair(),'LAUNCHER_IMPORT_REPAIR_INSTALLED')
    def test_recovery_not_started_refused(self):
        with self.assertRaisesRegex(Exception,'not_started'):self.run_repair(True)
        self.assert_before()
    def test_lock_conflict_precedes_mutation(self):
        import fcntl
        with open(self.root/'lock','rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(Exception,'shared_publication_busy'):self.run_repair()
        self.assert_before()
    def test_foreign_target_drift_refused(self):
        self.code.write_bytes(b'foreign')
        with self.assertRaises(Exception):self.run_repair()
        self.assertEqual(self.code.read_bytes(),b'foreign')
    def test_any_java_or_watchdog_prevents_writes(self):
        for attr in ('java','watchdog'):
            setattr(self,attr,True)
            with self.assertRaisesRegex(Exception,'quiescence'):self.run_repair()
            self.assert_before();setattr(self,attr,False)
    def test_service_identity_drift_refused(self):
        self.services['critic']['ticks']='999'
        with self.assertRaisesRegex(Exception,'service_drift'):self.run_repair()
        self.assert_before()
    def test_ai_wrong_transaction_or_phase_refused(self):
        self.plan['ai']['transaction_id']='0'*32;self.rebind()
        with self.assertRaisesRegex(Exception,'exact_ai_transaction'):self.run_repair()
        self.assert_before()
    def test_even_rebound_ai_phase_must_be_exact_failed_restore(self):
        value=copy.deepcopy(self.journal);value['phase']='INSTALLED'
        path=self.ai_folder/'journal.json';path.write_text(json.dumps(value))
        self.plan['ai']['journal_sha256']=repair.sha(path.read_bytes());self.rebind()
        with self.assertRaisesRegex(Exception,'exact_failed_restore'):self.run_repair()
        self.assert_before()
    def test_changed_ai_journal_is_not_adopted(self):
        value=copy.deepcopy(self.journal);value['phase']='START_INTENT';(self.ai_folder/'journal.json').write_text(json.dumps(value))
        with self.assertRaises(Exception):self.run_repair()
        self.assert_before()
    def test_old_live_source_required(self):
        self.source.write_bytes(b'candidate or foreign source')
        with self.assertRaisesRegex(Exception,'old_source_drift'):self.run_repair()
        self.assert_before()
    def test_nonterminal_other_core_transaction_refused(self):
        tx='1'*32;folder=self.store/'transactions'/tx
        self.rt.storage.mkdir_private(folder.parent);self.rt.storage.mkdir_private(folder)
        self.write(self.store/'ACTIVE.json',{'transaction_id':tx})
        self.write(folder/'journal.json',{'schema':'R25_CORE_TRANSACTION_V1','transaction_id':tx,'phase':'INSTALL_INTENT'})
        with self.assertRaisesRegex(Exception,'other_core_transaction'):self.run_repair()
        self.assert_before()
    def test_policy_weakening_even_if_hash_reapproved_is_rejected(self):
        path=self.bundle/'POLICY.next.json';value=self.rt.read(path);value['upgrade']['configuration']['knowledge']['map-enabled']=True
        path.write_text(json.dumps(value));self.plan['files']['policy']['after_sha256']=repair.sha(path.read_bytes());self.rebind()
        with self.assertRaisesRegex(Exception,'policy_other_changes'):self.run_repair()
        self.assert_before()
    def test_handoff_unrelated_change_rejected(self):
        path=self.bundle/'HANDOFF.next.env';path.write_bytes(path.read_bytes().replace(b'OTHER=retained',b'OTHER=changed'))
        self.plan['files']['handoff']['after_sha256']=repair.sha(path.read_bytes());self.rebind()
        with self.assertRaisesRegex(Exception,'handoff_other_changes'):self.run_repair()
        self.assert_before()
    def test_missing_formal_archive_or_tool_drift_refused(self):
        (self.bundle/'upgrade_assistant_controller.py').write_bytes(b'not approved tool')
        with self.assertRaises(Exception):self.run_repair()
        self.assert_before()
    def test_mid_copy_external_drift_not_overwritten_during_recovery(self):
        original_copy=self.rt.storage.atomic_copy_file;failed=False
        def copy(src,dst,*args,**kwargs):
            nonlocal failed
            if Path(dst)==self.store/'POLICY.json' and not failed:
                failed=True;self.handoff.write_bytes(b'foreign external write\n');raise OSError('injected')
            return original_copy(src,dst,*args,**kwargs)
        with patch.object(self.rt.storage,'atomic_copy_file',side_effect=copy),self.assertRaises(OSError):self.run_repair()
        with self.assertRaisesRegex(Exception,'foreign_target_drift'):self.run_repair(True)
        self.assertEqual(self.handoff.read_bytes(),b'foreign external write\n')
    def test_interrupted_preparation_reuses_exact_immutable_preimages(self):
        original_copy=self.rt.storage.atomic_copy_file;failed=False
        def copy(src,dst,*args,**kwargs):
            nonlocal failed
            if str(dst).endswith('/before/policy') and not failed:failed=True;raise OSError('preparation interrupted')
            return original_copy(src,dst,*args,**kwargs)
        with patch.object(self.rt.storage,'atomic_copy_file',side_effect=copy),self.assertRaises(OSError):self.run_repair()
        self.assert_before()
        with self.assertRaisesRegex(Exception,'not_started'):self.run_repair(True)
        self.assertEqual(self.run_repair(),'LAUNCHER_IMPORT_REPAIR_INSTALLED')
    def test_preserved_jar_and_application_drift_refused(self):
        for name in ('release-jar','preview-jar','application','manifest'):
            path=self.live[name];before=path.read_bytes();path.write_bytes(b'foreign')
            with self.assertRaises(Exception):self.run_repair()
            self.assert_before();path.write_bytes(before)
    def test_noncanonical_archive_rejected_even_if_plan_hash_updated(self):
        path=self.bundle/'r25-controller.zip';raw=path.read_bytes()+b'trailing';path.write_bytes(raw)
        self.plan['deploy']['archive_sha256']=repair.sha(raw)
        manifest_path=self.bundle/'r25-controller-manifest.json';manifest=self.rt.read(manifest_path)
        manifest['archive'].update(sha256=repair.sha(raw),bytes=len(raw));manifest_path.write_text(json.dumps(manifest))
        self.plan['deploy']['manifest_sha256']=repair.sha(manifest_path.read_bytes());self.rebind()
        with self.assertRaisesRegex(Exception,'archive_not_canonical'):self.run_repair()
        self.assert_before()

class FrontendBindings(unittest.TestCase):
    """Real retained lifecycle Engine; selector process observation is a fixture.

    Unlike the transaction fixtures above, this executes Engine.frontend() with
    its normally uninitialized attributes. No Engine.load(), backend-policy
    load, service start or production path is used.
    """
    def setUp(self):
        import contextlib
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.deploy=self.root/'web';self.lock=self.deploy/'runtime/frontend-deployment.lock'
        self.rt=Runtime(self.root,self.root/'runtime/core-publications');self.owner=[os.getuid(),os.getgid()]
        for folder in ('operations','runtime','runtime/config','web','web/runtime'):
            self.rt.storage.mkdir_private(self.root/folder)
        self.rt.storage.atomic_write_bytes(self.lock,b'lock')
        for module,key,value in ((repair.guard,'ROOT',self.root),(repair.guard,'LOCK',self.lock),(original,'LOCK',self.lock)):
            p=patch.object(module,key,value);p.start();self.addCleanup(p.stop)
        source=Path(__file__).parent/'fixtures/lifecycle_adapter.py.snapshot'
        bound=self.root/'operations/lifecycle_adapter.py';self.rt.storage.atomic_write_bytes(bound,source.read_bytes())
        self.lifecycle=repair.guard.source_module(bound,'fixture_retained_lifecycle_frontend',source.read_bytes())
        self.engine=self.lifecycle.Engine(self.root,self.root/'preview',script_owner=tuple(self.owner),private_owner=tuple(self.owner),deployment_root=self.deploy)
        self.assertIsNone(self.engine.selector_module)
        self.assertFalse(hasattr(self.engine,'selection_sha'));self.assertFalse(hasattr(self.engine,'lock'))
        self.selector=self.root/'operations/frontend_lifecycle_selector.py'
        selector_source=b'''import os\nclass Refused(RuntimeError): pass\nclass Engine:\n    def __init__(self, config, sha, deployment_root, *, lease_fd, diagnostics, diagnostics_module):\n        assert config.exists() and len(sha)==64 and deployment_root.exists()\n        assert os.fstat(lease_fd).st_ino==(deployment_root/'runtime/frontend-deployment.lock').stat().st_ino\n    def run(self, mode):\n        assert mode=='status'\n        return 'FIXTURE_OWNED_FRONTEND_STATUS'\n'''
        self.rt.storage.atomic_write_bytes(self.selector,selector_source);self.selector.chmod(0o700)
        self.lifecycle.SELECTOR=repair.sha(selector_source)  # Explicit selector fixture source identity.
        self.selection=self.root/'runtime/config/frontend-selection.json'
        self.selection_sha=self.rt.storage.atomic_write_json(self.selection,{'deployment_root':str(self.deploy),'shared_lock':str(self.lock)})['sha256']
        self.reference=self.root/'runtime/config/frontend-selection.reference'
        self.rt.storage.atomic_write_bytes(self.reference,('schema=ARTLIVE_FRONTEND_SELECTION_REFERENCE_V1\nselection_sha256='+self.selection_sha+'\n').encode())
        self.engine.v={'R25_FRONTEND_SELECTOR':str(self.selector),'R25_FRONTEND_SELECTOR_SHA256':self.lifecycle.SELECTOR,
            'R25_FRONTEND_SELECTION':str(self.selection),'R25_FRONTEND_SELECTION_REFERENCE':str(self.reference)}
        recorder=SimpleNamespace(step=lambda *a,**kw:contextlib.nullcontext())
        diagnostic=SimpleNamespace(lock_proof=lambda path,fd:{'fixture':True})
        for name,value in (('diagnostics',recorder),('diagnostic_module',diagnostic)):
            p=patch.object(self.lifecycle.Engine,name,new_callable=PropertyMock,return_value=value);p.start();self.addCleanup(p.stop)
        self.plan={'controller_owner':self.owner,'private_owner':self.owner}
    def initialize(self):repair.launcher_repair_frontend_bindings(self.rt,self.plan,self.engine,self.lifecycle)
    def test_actual_unloaded_engine_initializes_and_executes_existing_frontend_status(self):
        with original.upgrade_lease(self.rt):
            with self.assertRaises(AttributeError):self.engine.frontend('status',self.rt.fd)
            with patch.object(self.lifecycle.Engine,'load',side_effect=AssertionError('backend load forbidden')):
                self.initialize()
                self.assertEqual(self.engine.frontend('status',self.rt.fd),'FIXTURE_OWNED_FRONTEND_STATUS')
            self.assertEqual(self.engine.selection_sha,self.selection_sha);self.assertEqual(self.engine.lock,self.lock)
    def test_selection_source_reference_and_lock_drift_rejected(self):
        scenarios=((self.selector,b'foreign'),(self.reference,b'schema=wrong\n'),
            (self.selection,json.dumps({'deployment_root':str(self.deploy),'shared_lock':'/foreign'}).encode()))
        with original.upgrade_lease(self.rt):
            for path,bad in scenarios:
                with self.subTest(path=path.name):
                    before=path.read_bytes();path.write_bytes(bad)
                    with self.assertRaises(Exception):self.initialize()
                    path.write_bytes(before)
            self.engine.v['R25_FRONTEND_SELECTOR']='/foreign/selector.py'
            with self.assertRaisesRegex(Exception,'frontend_fixed_bindings'):self.initialize()


if __name__=='__main__':unittest.main()
