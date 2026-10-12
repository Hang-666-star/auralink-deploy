"""Real stale-bytecode fixtures for source-bound trusted control loading.

Only synthetic temp modules execute. No legacy controller, production
process, database, provider or credential is invoked by these tests.
"""
import ast
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import control_overlay as overlay
import core_release_guard as guard
import core_runtime as runtime
import core_publish


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(ok, reason):
    if not ok:
        raise RuntimeError(reason)


class TrustedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".trusted-source-fixture-",
                                                    dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.names = []
        self.addCleanup(self.cleanup_modules)

    def cleanup_modules(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def cache_pair(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"VALUE = 1\n")
        observed = path.stat()
        cached = Path(py_compile.compile(str(path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
        approved = b"VALUE = 2\n"
        path.write_bytes(approved)
        os.utime(path, ns=(observed.st_atime_ns, observed.st_mtime_ns))
        self.assertTrue(cached.is_file())
        return approved, cached

    def test_fixture_reproduces_source_sha_matching_but_standard_loader_reads_old_cache(self):
        path = self.root / "standard.py"
        approved, cached = self.cache_pair(path)
        spec = importlib.util.spec_from_file_location("stale_standard_fixture", path)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        self.assertEqual(digest(path.read_bytes()), digest(approved))
        self.assertEqual(module.VALUE, 1)
        self.assertTrue(cached.exists())

    def test_source_module_ignores_real_cache_and_marks_executed_source_hash(self):
        path = self.root / "trusted.py"
        approved, cached = self.cache_pair(path)
        name = "r25_trusted_raw_fixture"
        self.names.append(name)
        module = guard.source_module(path, name, approved)
        self.assertEqual(module.VALUE, 2)
        self.assertEqual(module.__r25_source_sha256__, digest(approved))
        self.assertIs(sys.modules[name], module)
        self.assertEqual(Path(module.__file__), path)
        self.assertTrue(cached.exists(), "The loader must not delete unknown cache evidence")

    def test_source_module_registers_before_dataclass_and_cleans_up_failed_execution(self):
        path = self.root / "record.py"
        name = "r25_trusted_dataclass_fixture"
        self.names.append(name)
        raw = b"from dataclasses import dataclass\n@dataclass\nclass Record:\n    value: int = 2\n"
        module = guard.source_module(path, name, raw)
        self.assertEqual(module.Record().value, 2)
        with self.assertRaises(RuntimeError):
            guard.source_module(path, name, b"raise RuntimeError('synthetic failure')\n")
        self.assertIs(sys.modules[name], module)
        failed = "r25_trusted_new_failed_fixture"
        self.names.append(failed)
        with self.assertRaises(SyntaxError):
            guard.source_module(path, failed, b"this is invalid Python :\n")
        self.assertNotIn(failed, sys.modules)

    def test_runtime_loader_uses_verified_raw_and_explicit_owner_mode_hash(self):
        path = self.root / "runtime_control.py"
        approved, _ = self.cache_pair(path)
        name = "r25_trusted_runtime_fixture"
        self.names.append(name)
        with patch.object(guard, "read_file", return_value=approved) as read:
            module = runtime.load_module(path, name, digest(approved), owner=(1000, 1000), mode=0o700)
        self.assertEqual(module.VALUE, 2)
        self.assertEqual(module.__r25_source_sha256__, digest(approved))
        self.assertEqual(read.call_args.args[0], path)
        self.assertEqual(read.call_args.kwargs["expected"], digest(approved))
        self.assertEqual(read.call_args.kwargs["owner"], (1000, 1000))
        self.assertEqual(read.call_args.kwargs["mode"], 0o700)

    def test_legacy_pg_cache_refused_without_deleting_it(self):
        path = self.root / "postgres_access.py"
        _, cached = self.cache_pair(path)
        with self.assertRaises(guard.Refused):
            guard.reject_legacy_bytecode(path)
        self.assertTrue(cached.exists())
        cached.unlink()  # Only this fixture's own created file.
        path.with_suffix(".pyc").write_bytes(b"fixture legacy bytecode")
        with self.assertRaises(guard.Refused):
            guard.reject_legacy_bytecode(path)
        self.assertTrue(path.with_suffix(".pyc").exists())

    def test_configured_cache_prefix_is_also_refused(self):
        path = self.root / "postgres_access.py"
        path.write_bytes(b"VALUE = 1\n")
        prefix = self.root / "explicit-prefix"
        with patch.object(sys, "pycache_prefix", str(prefix)):
            cached = Path(py_compile.compile(str(path), doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
            with self.assertRaises(guard.Refused):
                guard.reject_legacy_bytecode(path)
        self.assertTrue(cached.exists())

    def overlay_method(self, raw, name):
        node = ast.parse(raw.decode("utf-8")).body[0]
        method = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == name)
        program = ast.Module(body=[method], type_ignores=[])
        namespace = {"Path": Path, "hashlib": hashlib, "importlib": importlib,
                     "sys": sys, "re": __import__("re"), "must": checked,
                     "sha": lambda path: digest(Path(path).read_bytes()),
                     "guard": lambda *args: None}
        exec(compile(ast.fix_missing_locations(program), "<trusted-overlay-method-fixture>", "exec"), namespace)
        return namespace[name]

    def test_core_and_ai_overlay_methods_execute_current_raw_and_reject_stale_cached_module(self):
        methods = ((overlay.CORE_MODULE_METHOD, "core", "core_release_guard_module"),
                   (overlay.AI_MODULE_METHOD, "ai", "ai_release_guard_module"))
        for raw, component, method_name in methods:
            with self.subTest(component=component):
                path = self.root / component / "operations" / (component + "_release_guard.py")
                approved, cached = self.cache_pair(path)
                context = type("Context", (), {})()
                context.root, context.script = path.parent.parent, (1000, 1000)
                prefix = "R25_" + component.upper() + "_RELEASE_GUARD"
                context.v = {prefix: str(path), prefix + "_SHA256": digest(approved)}
                method = self.overlay_method(b"class Controller:\n" + raw, method_name)
                module = method(context)
                self.names.append(module.__name__)
                self.assertEqual(module.VALUE, 2)
                self.assertEqual(module.__r25_source_sha256__, digest(approved))
                self.assertTrue(cached.exists())
                module.__r25_source_sha256__ = "f" * 64
                with self.assertRaises(RuntimeError):
                    method(context)

    def test_launcher_edited_guard_loader_never_reads_real_cache(self):
        path = self.root / "core_release_guard.py"
        approved, cached = self.cache_pair(path)
        original, rendered, _ = next(edit for edit in overlay.LAUNCHER_EDITS
                                    if b"exec_module" in edit[0])
        self.assertIn(b"compile(raw", rendered)
        program = ast.parse("def load():\n" + rendered.decode())
        namespace = {"importlib": importlib, "sys": sys, "helper": path,
                     "expected": digest(approved), "hashlib": hashlib,
                     "fail": lambda reason: (_ for _ in ()).throw(RuntimeError(reason))}
        # The original source preceding this exact replacement creates the spec.
        namespace["specification"] = importlib.util.spec_from_file_location("launcher_trusted_fixture", path)
        self.names.append("launcher_trusted_fixture")
        exec(compile(program, "<trusted-launcher-fixture>", "exec"), namespace)
        # The replacement defines module inside the function; return it for inspection.
        function = program.body[0]
        function.body.append(ast.Return(value=ast.Name(id="module", ctx=ast.Load())))
        exec(compile(ast.fix_missing_locations(program), "<trusted-launcher-fixture>", "exec"), namespace)
        module = namespace["load"]()
        self.assertEqual(module.VALUE, 2)
        self.assertEqual(module.__r25_source_sha256__, digest(approved))
        self.assertTrue(cached.exists())

    def cached_rewrite(self, path, old_raw, new_raw):
        self.assertEqual(len(old_raw), len(new_raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(old_raw)
        original = path.stat()
        cached = Path(py_compile.compile(str(path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
        path.write_bytes(new_raw)
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        return cached

    def test_direct_publisher_cli_refuses_stale_sibling_cache_before_import(self):
        bundle = self.root / "cli-bundle"
        bundle.mkdir()
        script = bundle / "core_publish.py"
        script.write_bytes(Path(core_publish.__file__).read_bytes())
        marker = bundle / "sibling-imported"
        new_raw = ("from pathlib import Path\nVALUE = 2\nPath(" + repr(str(marker)) +
                   ").write_text(str(VALUE))\nraise RuntimeError('sibling must not execute')\n").encode()
        cached = self.cached_rewrite(bundle / "core_release_guard.py",
            new_raw.replace(b"VALUE = 2", b"VALUE = 1"), new_raw)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        result = subprocess.run([sys.executable, "-B", str(script), "status"],
            cwd=bundle, env=environment, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(result.stderr), {"outcome": "REFUSED",
            "reason": "controller_bundle_bytecode_cache"})
        self.assertFalse(marker.exists(), "Refusal must precede source or bytecode imports")
        self.assertTrue(cached.exists(), "Refusal must preserve stale cache evidence")

    def test_server_packaged_verifier_ignores_existing_old_cache(self):
        candidate_path = Path(__file__).with_name("core-release-candidate.py")
        module = guard.source_module(candidate_path, "server_candidate_cache_fixture", candidate_path.read_bytes())
        self.names.append(module.__name__)
        bundle = self.root / "packaged"
        helper = bundle / "verify-r25-artifact.py"
        new_raw = b"VALUE = 2\ndef verify(jar): return VALUE\n"
        cached = self.cached_rewrite(helper, new_raw.replace(b"VALUE = 2", b"VALUE = 1"), new_raw)
        with patch.object(module, "__file__", str(bundle / "core-release-candidate.py")), \
             patch.object(guard, "read_file", side_effect=lambda path, **_: Path(path).read_bytes()):
            verifier = module.packaged_verifier()
        self.names.append(verifier.__name__)
        self.assertEqual(verifier.verify(None), 2)
        self.assertEqual(verifier.__r25_source_sha256__, digest(new_raw))
        self.assertTrue(cached.exists())

    def test_actual_server_stage_uses_new_verified_candidate_code_despite_cache(self):
        from test_core_runtime import FileFixture
        bundle = self.root / "stage-bundle"
        helper = bundle / "core-release-candidate.py"
        jar_raw = b"synthetic staged jar fixture"
        artifact = digest(jar_raw)
        new_raw = ("VALUE = 2\ndef verify(*args):\n    return {'artifact': {'sha256': '" + artifact +
                   "' if VALUE == 2 else '" + "0" * 64 + "', 'bytes': " + str(len(jar_raw)) + "}}\n").encode()
        cached = self.cached_rewrite(helper, new_raw.replace(b"VALUE = 2", b"VALUE = 1"), new_raw)
        incoming, store = self.root / "incoming", self.root / "store"
        commit = "a" * 40
        folder = incoming / (commit + "-12-1")
        folder.mkdir(parents=True)
        (store / "releases").mkdir(parents=True)
        (folder / "auralink-backend-0.0.1-SNAPSHOT.jar").write_bytes(jar_raw)
        (folder / "r25-artifact-verification.json").write_bytes(b"{}")
        (folder / "core-release-candidate.json").write_bytes(b"{}")
        (store / "POLICY.json").write_bytes(b"{}")
        files = FileFixture(self.root)
        rt = SimpleNamespace(storage=files, identity=files.file_identity,
            read=files.read_private_record, lease=lambda: nullcontext(),
            verify_candidate=lambda value: checked(value.artifact_sha256 == artifact, "stage_artifact"),
            require_terminal_component_transactions=lambda: None)
        with patch.object(core_publish, "__file__", str(bundle / "core_publish.py")), \
             patch.object(core_publish, "INCOMING", incoming), patch.object(guard, "STORE", store), \
             patch.object(guard, "read_file", side_effect=lambda path, **_: Path(path).read_bytes()), \
             patch.object(guard, "policy", return_value={"payload_fingerprint": "fixture-payload"}), \
             patch.object(guard, "payload_fingerprint", return_value="fixture-payload"):
            release = core_publish.stage(rt, commit, "12", "1")
        self.names.append("trusted_core_candidate")
        self.assertEqual(release.artifact_sha256, artifact)
        self.assertEqual((store / "releases" / (artifact + "-" + commit) / "backend.jar").read_bytes(), jar_raw)
        self.assertTrue(cached.exists())

    def test_legacy_factory_does_not_create_pg_cache_or_leave_global_flag_changed(self):
        operations = self.root / "operations"
        operations.mkdir()
        pg = operations / "postgres_access.py"
        pg.write_bytes(b"VALUE = 7\n")
        raw = ("import importlib.util\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
               "def production():\n    path=Path(" + repr(str(pg)) + ")\n"
               "    spec=importlib.util.spec_from_file_location('synthetic_legacy_pg_fixture',path)\n"
               "    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
               "    return SimpleNamespace(lock=path, observed=module.VALUE)\n").encode()
        with patch.object(guard, "ROOT", self.root), \
             patch.object(guard.os, "geteuid", return_value=0, create=True), \
             patch.object(guard, "read_file", return_value=raw), \
             patch.object(sys, "dont_write_bytecode", False):
            result = guard.production()
            self.assertEqual(result.legacy.observed, 7)
            self.assertFalse(sys.dont_write_bytecode)
            guard.reject_legacy_bytecode(pg)
        self.names.append("original_r25_huaniao_guard")
        self.assertFalse(Path(importlib.util.cache_from_source(str(pg))).exists())


if __name__ == "__main__":
    unittest.main()

