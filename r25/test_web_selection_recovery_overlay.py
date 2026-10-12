"""CI: real disposable files, synthetic owner/c5ea callback; no lifecycle action.

The unchanged generic Commit source is a reviewed nonsecret fixture. Actual root
ownership + installed selector/supervisor execution is separate isolated evidence.
"""
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import patch

import web_selection_recovery_overlay as overlay

BASE = (Path(__file__).parent/'fixtures/web_selection_commit_baseline.py').read_bytes()
# Minimal syntactically valid serializer preserving the exact guarded edit anchor.
SERIALIZER = b"def allowed(value):\n    require(value.get('state') in {'COMMITTED'},'prior_transition_unfinished')\n"
ENTRY = b'#!/bin/bash\n# hash-bound serializer\ntest "$digest" = ' + overlay.BASE_SERIALIZER_SHA.encode() + b'\n'


def rendered():
    serializer_sha = overlay.digest(SERIALIZER)
    entry = ENTRY.replace(overlay.BASE_SERIALIZER_SHA.encode(), serializer_sha.encode())
    with patch.multiple(overlay, BASE_SERIALIZER_SHA=serializer_sha, BASE_ENTRY_SHA=overlay.digest(entry)):
        return overlay.render(BASE, SERIALIZER, entry)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = types.ModuleType('isolated_commit')
        exec(compile(rendered().helper, '<reviewed-helper-overlay>', 'exec'), self.module.__dict__)
        # CI user ownership is synthetic; preserve actual symlink/mode/hash checks.
        def guard(path, digest=None, kind='file'):
            self.module.must(all(not p.is_symlink() for p in [path, *path.parents]), 'symlink_path')
            observed = path.lstat()
            desired = stat.S_ISDIR if kind == 'dir' else stat.S_ISREG
            self.module.must(desired(observed.st_mode) and (observed.st_uid, observed.st_gid, observed.st_mode & 0o777) ==
                             (os.geteuid(), os.getegid(), 0o700 if kind == 'dir' else 0o600), 'private_identity')
            if digest:self.module.must(self.module.sha(path) == digest, 'saved_pair_hash')
        self.module.guard = guard
        self.selection = self.root/'selection'; self.reference = self.root/'reference'
        self.selection.write_bytes(json.dumps({'commit_sha':'a'*40,'build_id':'old'}).encode()); self.selection.chmod(0o600)
        self.reference.write_bytes(self.module.reference(self.selection.read_bytes()));self.reference.chmod(0o600)
        self.stage = self.root/'transition'
        self.tx = self.module.Commit(self.selection,self.reference,self.stage);self.tx.capture()
        self.before = self.selection.read_bytes(),self.reference.read_bytes()
        self.calls = []

    def owned(self, path, digest):
        self.assertEqual(path, self.stage/'old.selection')
        self.assertEqual(digest, overlay.digest(self.before[0]));self.calls.append((path,digest))

    def test_actual_baseline_fixture_hash_and_unpatched_failure(self):
        self.assertEqual(overlay.digest(BASE), overlay.BASE_HELPER_SHA)
        old = types.ModuleType('unpatched');exec(compile(BASE,'<baseline>','exec'),old.__dict__)
        old.guard=self.module.guard
        self.tx.record('DEPLOY_INTENT')
        with self.assertRaisesRegex(KeyError, 'new_selection_sha'):
            old.Commit(self.selection,self.reference,self.stage).finish(self.owned)
        self.assertFalse(self.calls)

    def test_early_states_require_owned_old_runtime_and_preserve_pair(self):
        for state in ('BASELINE_CAPTURED','DEPLOY_INTENT','DEPLOY_FAILED_OR_UNCERTAIN','BASELINE_RETAINED'):
            with self.subTest(state=state):
                self.tx.record(state);self.tx.finish(self.owned)
                self.assertEqual(json.loads(self.tx.journal.read_text())['state'],'BASELINE_RETAINED')
                self.assertEqual((self.selection.read_bytes(),self.reference.read_bytes()),self.before)
        self.assertEqual(len(self.calls),4)

    def test_failed_owner_check_leaves_unfinished_journal(self):
        self.tx.record('DEPLOY_FAILED_OR_UNCERTAIN')
        def failed(*_):raise RuntimeError('owned_supervisor_status_69')
        with self.assertRaisesRegex(RuntimeError,'owned_supervisor_status_69'):self.tx.finish(failed)
        self.assertEqual(json.loads(self.tx.journal.read_text())['state'],'DEPLOY_FAILED_OR_UNCERTAIN')
        self.assertEqual((self.selection.read_bytes(),self.reference.read_bytes()),self.before)

    def test_changed_live_pair_refuses_without_owner_call(self):
        self.tx.record('DEPLOY_INTENT');self.selection.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'saved_pair_hash'):self.tx.finish(self.owned)
        self.assertFalse(self.calls)
        self.assertEqual(self.selection.read_bytes(),b'changed')

    def test_unbound_new_file_or_atomic_temp_refuses(self):
        self.tx.record('DEPLOY_INTENT')
        for name in ('new.selection','new.reference','state.json.selection-ready'):
            with self.subTest(name=name):
                p=self.stage/name;p.write_bytes(b'unbound')
                with self.assertRaisesRegex(RuntimeError,'baseline_stage_contents'):self.tx.finish(self.owned)
                p.unlink()
        self.assertFalse(self.calls)

    def test_invalid_old_hash_or_journal_binding_refuses(self):
        for extra in ({'old_selection_sha':''},{'old_selection_sha':'g'*64},{'stage':'/another-stage'}):
            with self.subTest(extra=extra):
                self.tx.record('DEPLOY_INTENT',extra)
                with self.assertRaises(RuntimeError):self.tx.finish(self.owned)
                self.tx.record('DEPLOY_INTENT',{'old_selection_sha':overlay.digest(self.before[0])})
        self.assertFalse(self.calls)

    def test_saved_pair_tampering_and_permissions_refuse(self):
        self.tx.record('DEPLOY_INTENT');saved=self.stage/'old.selection'
        saved.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,'private_identity'):self.tx.finish(self.owned)
        saved.chmod(0o600);saved.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'saved_pair_hash'):self.tx.finish(self.owned)
        self.assertFalse(self.calls)

    def test_repeated_retention_rechecks_runtime_without_journal_write(self):
        self.tx.record('DEPLOY_INTENT');self.tx.finish(self.owned)
        before=self.tx.journal.read_bytes();stamp=self.tx.journal.stat().st_mtime_ns
        self.tx.finish(self.owned)
        self.assertEqual((self.tx.journal.read_bytes(),self.tx.journal.stat().st_mtime_ns),(before,stamp))
        self.assertEqual(len(self.calls),2)

    def test_existing_prepared_commit_still_validates_new_runtime(self):
        new=json.dumps({'commit_sha':'b'*40,'build_id':'new'}).encode();self.tx.bind_new(new)
        calls=[];self.tx.finish(lambda path,digest:calls.append((path,digest)))
        self.assertEqual(calls,[(self.stage/'new.selection',overlay.digest(new))])
        self.assertEqual(self.selection.read_bytes(),new)
        self.assertEqual(json.loads(self.tx.journal.read_text())['state'],'COMMITTED')

    def test_unknown_state_refuses_explicitly(self):
        self.tx.record('UNRECOGNIZED')
        with self.assertRaisesRegex(RuntimeError,'commit_state'):self.tx.finish(self.owned)


class RenderTests(unittest.TestCase):
    def test_unknown_baseline_is_refused(self):
        for values in ((BASE,SERIALIZER,ENTRY),(b'',b'',b''),(bytearray(BASE),b'',b'')):
            with self.assertRaisesRegex(overlay.Refused,'unreviewed_input_bytes'):overlay.render(*values)

    def test_exact_edits_preserve_all_other_bytes(self):
        result=rendered()
        self.assertEqual(result.helper.replace(overlay.NEW_FINISH,overlay.OLD_FINISH),BASE)
        self.assertEqual(result.serializer.replace(overlay.NEW_TERMINAL,overlay.OLD_TERMINAL),SERIALIZER)
        self.assertIn(overlay.digest(result.serializer).encode(),result.entry)
        self.assertEqual(overlay.manifest(result)['required_handoff_rebinding']['after'],overlay.digest(result.helper))

    def test_ambiguous_edit_is_refused(self):
        for value in (b'',b'xx'):
            with self.assertRaisesRegex(overlay.Refused,'exact_edit_required'):overlay.replace_once(value,b'x',b'y')


if __name__=='__main__':unittest.main()
