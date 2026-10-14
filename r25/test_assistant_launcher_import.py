"""Real fresh launcher-style imports; no production paths or application calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = r'''
import hashlib, importlib.util, json, pathlib, sys, types
root = pathlib.Path(sys.argv[1])
scenario = sys.argv[2]
# Model the real launcher's verified guard load. The private publisher folder
# is deliberately absent from sys.path, regardless of cwd/PYTHONPATH.
assert str(root / 'publisher') not in sys.path
assert 'publisher_transaction' not in sys.modules
poison = None
if scenario == 'poisoned':
    poison = types.ModuleType('publisher_transaction')
    def forbidden(name):
        raise RuntimeError('ambient publisher module consulted: ' + name)
    poison.__getattr__ = forbidden
    sys.modules['publisher_transaction'] = poison
spec = importlib.util.spec_from_file_location('core_release_guard', root / 'guard.py')
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
exec(compile((root / 'guard.py').read_bytes(), str(root / 'guard.py'), 'exec'), guard.__dict__)
source = root / 'publisher/core_business.py'
business = guard.source_module(source, 'bound_business', source.read_bytes())
policy = json.loads((root / 'policy.json').read_text())
if scenario in ('bad-hash', 'bad-mode'):
    try:
        business.assistant_module(policy)
    except business.Refused as error:
        assert str(error) == ('business_file_digest' if scenario == 'bad-hash' else 'business_file_mode'), str(error)
    else:
        raise AssertionError('unsafe source accepted')
else:
    assistant = business.assistant_module(policy)
    assert assistant.SCHEMA == 'R25_ASSISTANT_RELEASE_V1'
    assert assistant.__r25_source_sha256__ == policy['runtime_modules']['assistant_release.py']
    assert len(assistant.MIGRATION_SHA256) == 16
    assert assistant.PREFIX_LENGTHS == (13, 15, 16)
    assert issubclass(assistant.Refused, RuntimeError)
    try:
        assistant.must(False, 'synthetic_closed_check')
    except assistant.Refused as error:
        assert str(error) == 'synthetic_closed_check'
    else:
        raise AssertionError('refusal disabled')
assert ('publisher_transaction' not in sys.modules if poison is None
        else sys.modules['publisher_transaction'] is poison)
assert not (root / 'untrusted-import-ran').exists()
print(json.dumps({'scenario': scenario, 'bound_import': 'PASS'}))
'''


class AssistantLauncherImportTests(unittest.TestCase):
    def exercise(self, scenario):
        with tempfile.TemporaryDirectory(prefix='assistant-launcher-import-') as tmp:
            root = Path(tmp)
            folder = root/'publisher'
            folder.mkdir()
            source = Path(__file__).parent
            for name in ('assistant_release.py', 'core_business.py'):
                (folder/name).write_bytes((source/name).read_bytes())
                (folder/name).chmod(0o600)
            (root/'guard.py').write_bytes((source/'core_release_guard.py').read_bytes())
            # Neither an ambient cache nor a shadow sibling may supply this
            # dependency to a source/hash-bound validation module.
            poison = "from pathlib import Path\nPath("+repr(str(root/'untrusted-import-ran'))+").touch()\nraise RuntimeError('untrusted import')\n"
            (folder/'publisher_transaction.py').write_text(poison)
            target = folder/'assistant_release.py'
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            policy = {'runtime_modules': {'assistant_release.py': digest},
                      'installation': {'private_owner': [os.getuid(), os.getgid()]}}
            (root/'policy.json').write_text(json.dumps(policy))
            if scenario == 'bad-hash':
                target.write_bytes(target.read_bytes()+b'\n# unexpected change\n')
            elif scenario == 'bad-mode':
                target.chmod(0o644)
            result = subprocess.run([sys.executable, '-I', '-B', '-c', SCRIPT, str(root), scenario],
                                    cwd=folder, env={**os.environ, 'PYTHONPATH': str(folder)},
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['bound_import'], 'PASS')

    def test_fresh_launcher_without_publisher_search_path(self):
        self.exercise('absent')

    def test_poisoned_ambient_module_is_not_consulted(self):
        self.exercise('poisoned')

    def test_changed_helper_hash_is_rejected_before_execution(self):
        self.exercise('bad-hash')

    def test_open_helper_permissions_are_rejected_before_execution(self):
        self.exercise('bad-mode')


if __name__ == '__main__':
    unittest.main()
