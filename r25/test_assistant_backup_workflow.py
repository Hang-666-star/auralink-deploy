"""Workflow shell executes with a local SSH recorder, never a real connection."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class BackupWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (Path(__file__).parents[1]/'.github/workflows/assistant-backup.yml').read_text()
        cls.condition = re.search(r'^    if: (.+)$', cls.text, re.M).group(1)
        cls.script = '\n'.join(line[10:] for line in cls.text.split('        run: |\n', 1)[1].splitlines())+'\n'

    def test_default_off_main_only_timer_does_not_follow_feature_push(self):
        # Exact GitHub expression contract, not a mock claim about remote execution.
        self.assertEqual(self.condition, "github.ref == 'refs/heads/main' && vars.R25_ASSISTANT_BACKUP_ENABLED == 'true'")
        cases = [('refs/heads/main', '', False), ('refs/heads/main', 'false', False),
                 ('refs/heads/feat/assistant-release-integration', 'true', False), ('refs/heads/main', 'true', True)]
        for ref, flag, expected in cases:
            self.assertEqual(ref == 'refs/heads/main' and flag == 'true', expected)
        self.assertNotIn('\n  push:', self.text)
        self.assertNotIn('\n  pull_request:', self.text)
        self.assertIn("cron: '15 19 * * *'", self.text)
        self.assertIn('cancel-in-progress: false', self.text)

    def execute(self, supplied=True, host='example.invalid'):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recorder = root/'ssh'
            recorder.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$RECORD/argv"\ncat > "$RECORD/stdin"\n')
            recorder.chmod(0o700)
            env = {'PATH': str(root)+':/usr/bin:/bin', 'HOME': str(root), 'RECORD': str(root),
                   'SERVER_HOST': host, 'SERVER_PORT': '49628', 'SERVER_SSH_KEY': 'synthetic-not-a-real-key' if supplied else '',
                   'SERVER_KNOWN_HOSTS': 'synthetic-host-key' if supplied else '', 'CONTROLLER_SHA256': 'a'*64}
            result = subprocess.run(['bash'], input=self.script, text=True, env=env, capture_output=True, timeout=10)
            return result.returncode, (root/'argv').read_text() if (root/'argv').exists() else None, (root/'stdin').read_text() if (root/'stdin').exists() else None

    def test_missing_private_refs_or_malformed_target_never_connect(self):
        for kw in ({'supplied': False}, {'host': 'example.invalid; echo unsafe'}):
            code, args, script = self.execute(**kw)
            self.assertNotEqual(code, 0)
            self.assertIsNone(args)
            self.assertIsNone(script)

    def test_actual_shell_only_calls_hash_bound_existing_backup_cli(self):
        code, args, script = self.execute()
        self.assertEqual(code, 0)
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('BatchMode=yes', args)
        self.assertIn('root@example.invalid', args)
        self.assertIn('test "$(sha256sum "$publisher"', script)
        commands = [line.strip() for line in script.splitlines() if line.strip().startswith('"$python"')]
        self.assertEqual(commands, ['"$python" -B "$publisher" assistant-backup-run',
                                    '"$python" -B "$publisher" assistant-backup-retention --apply'])
        self.assertNotIn(' publish ', script)
        self.assertNotIn('workflow', script)
        self.assertNotIn('api_key', script.lower())


if __name__ == '__main__': unittest.main()
