"""Render an exact installed c5ea recovery patch offline; never install or run it.

Only an unchanged captured baseline with an independently verified owned Next
process can close an early publication journal. This is not application rollback.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

BASE_HELPER_SHA = '25fe045b7de4d99bbe6b004c3961e3af1154b0cc765225d1272a6538d9c97cd4'
BASE_SERIALIZER_SHA = '1963c48dc821b5a771e2ce74dfdc1c3c445383da1a4a5b3d507a9caf6614f70b'
BASE_ENTRY_SHA = 'd6e8e522b85106790da3b5537a86330b305feef8caa2a4ced1c22739d79b8cdd'


class Refused(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise Refused('exact_edit_required')
    return source.replace(before, after, 1)


OLD_FINISH = b'''    def finish(self,check_owned_next):
        value=self.verified()
'''
NEW_FINISH = b'''    def retain_verified_baseline(self,check_owned_next):
        guard(self.stage,kind='dir');guard(self.journal)
        value=json.loads(self.journal.read_text())
        must(value.get('selection')==str(self.selection) and value.get('reference')==str(self.ref) and
             value.get('stage')==str(self.stage),'state_identity')
        state=value.get('state')
        if state not in {'BASELINE_CAPTURED','DEPLOY_INTENT','DEPLOY_FAILED_OR_UNCERTAIN','BASELINE_RETAINED'}:
            must(state in {'PREPARED','CONFIG_INSTALLED','COMMITTED'},'commit_state')
            return False
        # An interrupted new-pair binding is not evidence of an unchanged runtime.
        must({p.name for p in self.stage.iterdir()}=={'old.selection','old.reference','state.json'},
             'baseline_stage_contents')
        for name in ('selection','reference'):
            expected=value.get('old_'+name+'_sha')
            must(type(expected)is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),
                 'old_pair_digest')
            guard(self.stage/('old.'+name),expected)
        must((self.stage/'old.reference').read_bytes()==reference((self.stage/'old.selection').read_bytes()),
             'saved_reference_binding')
        # Never repair a changed pair or infer/adopt a running candidate here.
        guard(self.selection,value['old_selection_sha']);guard(self.ref,value['old_reference_sha'])
        check_owned_next(self.stage/'old.selection',value['old_selection_sha'])
        if state!='BASELINE_RETAINED':self.record('BASELINE_RETAINED')
        return True
    def finish(self,check_owned_next):
        if self.retain_verified_baseline(check_owned_next):return
        value=self.verified()
'''
OLD_TERMINAL = b".get('state') in {'COMMITTED'},'prior_transition_unfinished')"
NEW_TERMINAL = b".get('state') in {'COMMITTED','BASELINE_RETAINED'},'prior_transition_unfinished')"


@dataclass(frozen=True)
class Rendered:
    helper: bytes
    serializer: bytes
    entry: bytes

    def files(self):
        return {'selection_commit.py': self.helper,
                'serialized_deploy_web.py': self.serializer, 'deploy-web.sh': self.entry}


def render(helper, serializer, entry):
    for data, expected in ((helper, BASE_HELPER_SHA), (serializer, BASE_SERIALIZER_SHA), (entry, BASE_ENTRY_SHA)):
        if type(data) is not bytes or digest(data) != expected:
            raise Refused('unreviewed_input_bytes')
    patched_helper = replace_once(helper, OLD_FINISH, NEW_FINISH)
    patched_serializer = replace_once(serializer, OLD_TERMINAL, NEW_TERMINAL)
    patched_entry = replace_once(entry, BASE_SERIALIZER_SHA.encode(), digest(patched_serializer).encode())
    ast.parse(patched_helper); ast.parse(patched_serializer)
    return Rendered(patched_helper, patched_serializer, patched_entry)


def manifest(rendered):
    baselines = {'selection_commit.py': BASE_HELPER_SHA,
                 'serialized_deploy_web.py': BASE_SERIALIZER_SHA, 'deploy-web.sh': BASE_ENTRY_SHA}
    return {'schema': 'ARTLIVE_WEB_BASELINE_RECOVERY_CANDIDATE_V1', 'status': 'NOT_INSTALLED',
            'production_approved': False,
            'files': [{'name': name, 'before_sha256': baselines[name], 'after_sha256': digest(data),
                       'bytes': len(data), 'installed_uid': 0, 'installed_gid': 0, 'installed_mode': '0700'}
                      for name, data in rendered.files().items()],
            'required_handoff_rebinding': {'key': 'R25_FRONTEND_COMMIT_HELPER_SHA256',
                                          'before': BASE_HELPER_SHA, 'after': digest(rendered.helper)},
            'unchanged': ['c5ea supervisor', 'shared lock', 'retained inner deployer',
                          'Next process ownership', 'R25 selector', 'database and media'],
            'recovery_scope': 'Only exact saved/live old pair plus successful unchanged selector status; no lifecycle or selection writes',
            'installation': 'Use separately reviewed docs/knowledge/web-recovery-installation.md one-off four-file procedure; renderer never installs'}


def read_input(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise Refused('regular_absolute_input_required')
    data = path.read_bytes()
    if len(data) > 1024 * 1024:
        raise Refused('input_too_large')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    try:
        rendered = render(*(read_input(args.source_directory / name) for name in
                            ('selection_commit.py', 'serialized_deploy_web.py', 'deploy-web.sh')))
        out = args.output_directory
        if not out.is_absolute() or any(p.is_symlink() for p in (out, *out.parents)):
            raise Refused('absolute_no_symlink_output_required')
        out.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name, data in rendered.files().items():
            fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
        with (out / 'web-recovery-candidate.json').open('x') as stream:
            json.dump(manifest(rendered), stream, sort_keys=True, indent=2); stream.write('\n')
        print(json.dumps({'status': 'RENDERED_NOT_INSTALLED', 'files': 3, 'production_approved': False}))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'REFUSED', 'reason': str(error) if isinstance(error, Refused) else type(error).__name__}))
        return 65


if __name__ == '__main__':
    raise SystemExit(main())
