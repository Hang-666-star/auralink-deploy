"""Focused guards; actual PostgreSQL rehearsal is retained outside Git in S4."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import assistant_release as ar
import assistant_runtime_overlay as overlay
import ai_release_candidate as ai
from publisher_transaction import Refused
from r25_storage import R25Storage, StorageRefused
import upgrade_assistant_controller as uc


class AssistantGuards(unittest.TestCase):
    def test_fixed_migrations_reject_rebound_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);entries=[]
            for i,(name,digest) in enumerate(ar.MIGRATION_SHA256.items(),1):
                p=root/name;p.write_text('-- attacker changed source and rebound its own manifest\n')
                entries.append({'version':f'V{i:03}','name':name,'path':str(p),'sha256':ar.sha(p.read_bytes())})
            with self.assertRaisesRegex(Refused,'unreviewed_migration_bytes'):
                ar.migration_inventory(entries)

    def test_unknown_schema_is_not_permitted_range(self):
        self.assertEqual(ar.PREFIX_LENGTHS,(13,15,16))
        self.assertEqual(len(ar.MIGRATION_SHA256),16)
        self.assertEqual(ar.MIGRATION_SHA256['V014__assistant_records.sql'],'7f073ba6c5504e2aeb60b210474c27be81733ff34617ba81b82bfed4eb9b5bcd')
        self.assertEqual(ar.MIGRATION_SHA256['V015__assistant_execution.sql'],'f4f53364d20a6e62c97de9978755944e238dd24600f7da0904b822bea4ba9685')

    def test_private_namespace_permissions_and_foreign_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);os.chmod(root,0o700)
            marker=root/'.assistant-attachments-v1';marker.write_bytes(b'ArtLIVE Assistant private attachments v1\n');marker.chmod(0o600)
            image=root/('a'*8+'-'+'a'*4+'-'+'a'*4+'-'+'a'*4+'-'+'a'*12+'.blob');image.write_bytes(b'private fixture');image.chmod(0o600)
            self.assertEqual(len(ar.file_inventory(root)),2)
            image.chmod(0o644)
            with self.assertRaisesRegex(Refused,'permissions'):ar.file_inventory(root)
            image.chmod(0o600);(root/'catalog.jpg').write_bytes(b'not owned')
            with self.assertRaisesRegex(Refused,'unowned'):ar.file_inventory(root)

    def test_controller_rejects_v1_impersonation(self):
        plan={'schema':uc.SCHEMA,'from_policy_schema':'R25_CORE_EQUIVALENT_PAYLOAD_POLICY_V1','deploy':{},'current_release':{},'next_owner':'c5ea','controller_owner':[os.getuid(),os.getgid()],'private_owner':[os.getuid(),os.getgid()],'files':{},'operational':{},'review_evidence_sha256':'a'*64}
        with self.assertRaisesRegex(Refused,'installed_v2'):uc.validate(plan)

    def test_real_descriptor_removal_preserves_unknown_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);root.chmod(0o700)
            storage=R25Storage([str(root)],owner_uid=os.getuid(),owner_gid=os.getgid())
            p=root/'new.py';p.write_bytes(b'approved');p.chmod(0o600)
            with self.assertRaises(StorageRefused):storage.remove_bound_file(p,'0'*64,expected_owner=(os.getuid(),os.getgid()))
            self.assertEqual(p.read_bytes(),b'approved')
            storage.remove_bound_file(p,ar.sha(b'approved'),expected_owner=(os.getuid(),os.getgid()))
            self.assertFalse(p.exists())

    def test_real_descriptor_empty_directory_refuses_untracked_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);root.chmod(0o700);child=root/'assistant';child.mkdir(mode=0o700)
            storage=R25Storage([str(root)],owner_uid=os.getuid(),owner_gid=os.getgid())
            (child/'foreign').write_bytes(b'keep')
            with self.assertRaises(StorageRefused):storage.remove_empty_directory(child,expected_owner=(os.getuid(),os.getgid()))
            self.assertTrue((child/'foreign').exists())


class SourceInventory(unittest.TestCase):
    def test_both_exact_versions_roundtrip_without_repo_alias(self):
        for schema,paths,repo in ((ai.SCHEMA,ai.SOURCE_PATHS,ai.REPOSITORY),(ai.ASSISTANT_SCHEMA,ai.ASSISTANT_PATHS,ai.CURRENT_REPOSITORY)):
            source={p:b'# synthetic source\n' for p in paths}
            identity=ai.provenance(repo,ai.REF,'a'*40,'42','1',schema)
            manifest,blob=ai.build(source,identity,schema)
            self.assertEqual(len(ai.verify(manifest,blob,'a'*40,'42','1')['files']),len(paths))
            bad=copy.deepcopy(manifest);bad['repository']='foreign/auralink-ai-service'
            with self.assertRaises(ai.InvalidCandidate):ai.verify(bad,blob,'a'*40,'42','1')
        with self.assertRaises(ai.InvalidCandidate):ai.build({p:b'# fixture\n' for p in ai.ASSISTANT_PATHS},ai.provenance(ai.REPOSITORY,ai.REF,'a'*40,'42','1'))

    def test_wrapper_only_forwards_two_refs_preserves_critic(self):
        before=(Path(__file__).parent/'fixtures/r25-private-critic-env-policy-v2.py.snapshot').read_bytes()
        after=overlay.render(before);scope={};exec(compile(after,'synthetic-trusted-wrapper','exec'),scope)
        values={'QWEN_API_KEY':'synthetic-private-key-not-used','QWEN_BASE_URL':'https://example.invalid/compatible-mode/v1','QWEN_MODEL':'reviewed-model'}
        baseline=scope['child_environment'](values,'synthetic-token','configured-provider')
        with_refs=scope['child_environment']({**values,'AURALINK_ASSISTANT_CONFIG_FILE':'/private/assistant.json','AURALINK_ASSISTANT_INTERNAL_TOKEN_FILE':'/private/assistant-token','PORT':'9999'},'synthetic-token','configured-provider')
        self.assertEqual({k:v for k,v in with_refs.items() if not k.startswith('AURALINK_ASSISTANT_')},baseline)
        self.assertEqual(with_refs['AURALINK_ASSISTANT_CONFIG_FILE'],'/private/assistant.json')
        malformed=scope['child_environment']({**values,'AURALINK_ASSISTANT_CONFIG_FILE':'relative/malformed'},'synthetic-token','configured-provider')
        self.assertEqual(malformed,baseline)
        with self.assertRaisesRegex(ValueError,'baseline_hash'):overlay.render(before+b'# drift')

if __name__=='__main__':unittest.main()
