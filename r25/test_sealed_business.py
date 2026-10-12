"""Sealed transport policy/asset/process dispatch; not an OS enforcement proof."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import core_business as business
from test_core_business import fixture_policy, encoded


class SealedBusinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sealed-business-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = fixture_policy(self.root, 'poetry-only', 'sealed-memfd-capdrop')

    def material(self):
        root = self.root / 'snapshot'; root.mkdir();self.addCleanup(lambda: root.chmod(0o700))
        entries = []
        for filename,key in business.required_assets('poetry-only').items():
            raw = encoded({'synthetic': filename})
            (root/filename).write_bytes(raw);(root/filename).chmod(0o440)
            self.policy['upgrade']['configuration']['knowledge'][key] = business.sha(raw)
            entries.append({'filename':filename,'sha256':business.sha(raw),'bytes':len(raw)})
        raw = encoded({'schemaVersion':2,'releaseProfile':'poetry-only','artifacts':entries})
        (self.root/'assets.json').write_bytes(raw);(self.root/'assets.json').chmod(0o600)
        self.policy['upgrade']['assets']['manifest_sha256'] = business.sha(raw)
        # Only effective traversal identity is simulated in unprivileged CI;
        # actual root capdrop + metadata enforcement is exercised separately.
        service = {**self.policy['installation']['service'], 'uid':os.getuid(), 'gid':os.getgid(), 'groups':[os.getgid()]}
        root.chmod(0o550)
        return root, patch.object(business, '_service', return_value=service)

    def test_exact_transport_profile_and_nonroot_inode_owner_are_bound(self):
        business.validate_policy(self.policy)
        for mutate in (
            lambda p:p['upgrade']['configuration']['knowledge'].pop('snapshot-transport'),
            lambda p:p['upgrade']['configuration']['knowledge'].update({'snapshot-transport':'filesystem'}),
            lambda p:p['upgrade'].update(release_profile='map-enabled'),
            lambda p:p['upgrade']['assets'].pop('sealed_owner'),
            lambda p:p['upgrade']['assets']['sealed_owner'].update(uid=0),
            lambda p:p['upgrade']['assets']['sealed_owner'].update(gid=99999),
            lambda p:p['installation']['service'].update(isolation='readonly-filesystem-capdrop'),
        ):
            changed = deepcopy(self.policy);mutate(changed)
            with self.assertRaises(business.Refused):business.validate_policy(changed)
        changed=deepcopy(self.policy); changed['upgrade']['assets']['sealed_owner']['uid']+=1
        with self.assertRaisesRegex(business.Refused,'sealed_owner_drift'):business.sealed_owner(changed)

    def test_bound_config_adds_only_transport_and_rollback_remains_original(self):
        before=b'auralink:\n  critic:\n    policy: configured-provider\n'
        after=business.render_configuration(before,self.policy)
        self.assertTrue(after.startswith(before))
        self.assertIn(b'auralink.knowledge.snapshot-transport: "sealed-memfd-v1"\n',after)
        self.assertEqual(after.count(b'auralink.knowledge.'),5)
        baseline=self.policy['upgrade']['baseline_release']
        self.assertEqual(business.config_for_release(self.policy,baseline),business.sha(before))

    def test_two_sources_are_verified_but_never_claimed_readonly_filesystem(self):
        _, identity=self.material()
        with identity, patch.object(business,'sandbox_module') as sandbox:
            receipt=business.verify_assets(self.policy)
        sandbox.assert_not_called()
        self.assertEqual(receipt['files'],2)
        self.assertFalse(receipt['durable_source_readonly'])
        self.assertIsNone(receipt['filesystem'])
        self.assertTrue(receipt['candidate_sealed_descriptors_required'])

    def test_missing_changed_extra_and_symlinked_sources_refuse(self):
        root,identity=self.material();path=root/'poetry-graph.json';original=path.read_bytes()
        def edit(action):
            root.chmod(0o700)
            action()
            root.chmod(0o550)
        def replace(raw):
            path.chmod(0o640);path.write_bytes(raw);path.chmod(0o440)
        with identity:
            path.chmod(0o640)
            with self.assertRaises(business.Refused):business.verify_assets(self.policy)
            replace(original+b'changed')
            with self.assertRaisesRegex(business.Refused,'file_digest'):business.verify_assets(self.policy)
            replace(original);edit(path.unlink)
            with self.assertRaisesRegex(business.Refused,'root_identity'):business.verify_assets(self.policy)
            edit(lambda:path.write_bytes(original));path.chmod(0o440)
            edit(lambda:(root/'china.json').write_text('{}'))
            with self.assertRaisesRegex(business.Refused,'root_identity'):business.verify_assets(self.policy)
            edit((root/'china.json').unlink)
            other=self.root/'other.json';other.write_bytes(original);other.chmod(0o440)
            edit(path.unlink);edit(lambda:path.symlink_to(other))
            with self.assertRaises((business.Refused,OSError)):business.verify_assets(self.policy)

    def test_launcher_uses_exact_once_verified_bytes_no_disk_fallback(self):
        _,identity=self.material()
        sandbox=SimpleNamespace(prepare_sealed=lambda *a,**k:None)
        with identity,patch.object(business.os,'geteuid',return_value=os.getuid()),patch.object(business.os,'getegid',return_value=os.getgid()),patch.object(business,'sandbox_module',return_value=sandbox),patch.object(sandbox,'prepare_sealed') as launch:
            business.prepare_asset_sandbox(self.policy)
            raw=launch.call_args.args[0]
            self.assertEqual(set(raw),{'poetry-graph.json','poetry-stats.json'})
            for spec in raw.values():self.assertEqual(business.sha(spec['raw']),spec['sha256'])
            self.assertEqual(launch.call_args.kwargs,business.sealed_owner(self.policy))
            launch.side_effect=RuntimeError('synthetic_seals_refused')
            with self.assertRaisesRegex(RuntimeError,'seals_refused'):business.prepare_asset_sandbox(self.policy)

    def test_runtime_inspects_actual_sealed_descriptors_not_source_receipt(self):
        self.material()
        pid=self.root/'9876';pid.mkdir();(pid/'stat').write_text('9876 (java) S '+'0 '*18+'456 0\n')
        status='Uid: 0 0 0 0\nGid: 0 0 0 0\nGroups: 0\nCapEff: 0000000000000000\n'
        (pid/'status').write_text(status);(pid/'environ').write_bytes(b'PATH=/usr/bin:/bin\0')
        cfg=str(self.root/'application.yml');(pid/'cmdline').write_bytes(('java\0--spring.config.additional-location=file:'+cfg+'\0').encode())
        helper=SimpleNamespace(verify_sealed=lambda *a,**k:{'immutable_bytes':True})
        with patch.object(business,'_service',return_value=self.policy['installation']['service']),patch.object(business,'sandbox_module',return_value=helper),patch.object(helper,'verify_sealed',wraps=helper.verify_sealed) as verify:
            business.verify_process(self.policy,9876,456,cfg,proc_root=self.root)
            self.assertEqual(verify.call_args.args,(9876,business.asset_specs(self.policy)))
            verify.side_effect=RuntimeError('synthetic_descriptor_unsealed')
            with self.assertRaisesRegex(RuntimeError,'unsealed'):business.verify_process(self.policy,9876,456,cfg,proc_root=self.root)
            # Existing compatible baseline rollback does not need sealed objects.
            business.verify_process(self.policy,9876,456,cfg,proc_root=self.root,require_isolated=False)

if __name__=='__main__':unittest.main()
