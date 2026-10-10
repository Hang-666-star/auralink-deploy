from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from core_release_guard import payload_fingerprint, Refused


class PayloadEquivalenceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def jar(self, name, *, year=2020, class_body=b'class-v1', library=b'library-v1',
            extra=None, start='com.auralink.Application', build='17', duplicate=False):
        path = self.root / name
        entries = {'META-INF/MANIFEST.MF': ('Manifest-Version: 1.0\nMain-Class: org.example.Loader\n'
                    'Start-Class: ' + start + '\nBuild-Jdk-Spec: ' + build + '\n').encode(),
                   'BOOT-INF/classes/application-catalog-postgres-production.yml': b'profile-v1',
                   'BOOT-INF/classes/com/auralink/Application.class': class_body,
                   'BOOT-INF/lib/dependency.jar': library}
        if extra:
            entries.update(extra)
        with zipfile.ZipFile(path, 'w') as archive:
            for key, data in entries.items():
                info = zipfile.ZipInfo(key, (year, 1, 1, 0, 0, 0))
                archive.writestr(info, data)
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr('BOOT-INF/classes/com/auralink/Application.class', b'duplicate')
        return path

    def test_only_container_timestamp_and_build_labels_may_differ(self):
        first = self.jar('first.jar')
        second = self.jar('second.jar', year=2026, build='17.0.15')
        self.assertNotEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(payload_fingerprint(first), payload_fingerprint(second))

    def test_class_dependency_launcher_and_extra_entries_change_capability(self):
        baseline = payload_fingerprint(self.jar('base.jar'))
        for i, kwargs in enumerate(({'class_body': b'weakened'}, {'library': b'other'},
                                    {'start': 'com.attacker.Entry'},
                                    {'extra': {'BOOT-INF/classes/unexpected.properties': b'injected'}})):
            self.assertNotEqual(baseline, payload_fingerprint(self.jar(str(i) + '.jar', **kwargs)))

    def test_duplicate_and_path_traversal_fail_closed(self):
        for name, kwargs in (('duplicate.jar', {'duplicate': True}),
                             ('path.jar', {'extra': {'../escaped.class': b'bad'}})):
            with self.assertRaises(Refused):
                payload_fingerprint(self.jar(name, **kwargs))


if __name__ == '__main__':
    unittest.main()
