"""Synthetic GET contracts plus actual loopback HTTP; no application/provider writes."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from assistant_acceptance import PATHS, verify_assistant_http
from core_acceptance import request
from core_release_guard import Refused


def fixture(mode='enabled'):
    configured = {'enabled': mode != 'disabled', 'history-only': mode == 'history-only',
                  'execution.enabled': mode == 'enabled',
                  'execution.expected-config-sha256': 'a' * 64,
                  'storage.quota-bytes': 2048, 'storage.draft-lifetime': 'PT1H',
                  'storage.cleanup-enabled': False}
    policy = {'upgrade': {'capability': 'assistant-v1', 'assistant': {'mode': mode},
                          'configuration': {'assistant': configured}}}
    storage = {'policyStatus': 'VALID', 'historyOnly': mode == 'history-only',
               'uploadsAvailable': mode == 'enabled', 'quotaBytes': 2048,
               'readyBytes': 200, 'reservedBytes': 50, 'logicalBytes': 250,
               'cleanupReservedBytes': 100, 'chargedBytes': 350,
               'retainedFileBytes': 330, 'pendingCleanupBytes': 90,
               'availableBytes': 1698, 'draftLifetimeSeconds': 3600, 'cleanupEnabled': False}
    models = {'contractVersion': 1, 'configSha256': 'a' * 64, 'models': [
        {'id': 'synthetic-text', 'configured': True, 'enabled': True,
         'evidence': 'MOCK_ONLY', 'capabilities': {'images': False, 'streaming': True, 'imageMimeTypes': []}},
        {'id': 'synthetic-image', 'configured': True, 'enabled': True,
         'evidence': 'MOCK_ONLY', 'capabilities': {'images': True, 'streaming': True,
                                              'imageMimeTypes': ['image/jpeg', 'image/png']}}]}
    status = {'enabled': mode != 'disabled', 'executionAvailable': mode == 'enabled',
              'stage': 'execution' if mode == 'enabled' else 'foundation',
              'automaticSummaryAvailable': False}
    unavailable = (503, {'status': 503, 'code': 'ASSISTANT_DISABLED'})
    replies = {PATHS[0]: (200, status), PATHS[1]: (200, storage), PATHS[2]: (200, models),
               PATHS[3]: (200, {'items': [], 'hasMore': False, 'nextCursor': None})}
    if mode == 'disabled':
        replies[PATHS[1]] = replies[PATHS[3]] = unavailable
    if mode != 'enabled':
        replies[PATHS[2]] = (503, {'status': 503, 'code': 'ASSISTANT_EXECUTION_DISABLED'})
    return policy, replies


class AssistantAcceptanceTests(unittest.TestCase):
    def adapters(self, replies):
        calls = []

        def anonymous(path, accept='application/json'):
            calls.append(('anonymous', path))
            self.assertIn(path, PATHS)
            return 401, 'application/json', b'{"status":401,"code":"UNAUTHORIZED"}'

        def authenticated(path, accept='application/json'):
            calls.append(('authenticated', path))
            status, body = replies[path]
            return status, 'application/json', json.dumps(body).encode()

        return anonymous, authenticated, calls

    def verify(self, policy, replies):
        anon, auth, calls = self.adapters(replies)
        receipt = verify_assistant_http(policy, get=anon, get_authenticated=auth)
        self.assertEqual(8, len(calls))
        self.assertEqual(4, sum(kind == 'authenticated' for kind, _ in calls))
        self.assertEqual(0, receipt['write_requests'])
        self.assertEqual(0, receipt['provider_requests'])
        self.assertNotIn('items', json.dumps(receipt))
        return receipt

    def test_each_explicit_mode_is_observed_without_submission(self):
        for mode in ('disabled', 'history-only', 'enabled'):
            with self.subTest(mode=mode):
                receipt = self.verify(*fixture(mode))
                self.assertEqual(mode != 'disabled', receipt['history_read_available'])
                self.assertEqual(2 if mode == 'enabled' else 0, receipt['registry_model_count'])
                self.assertEqual('NOT_TESTED_CONFIGURED_REGISTRY_ONLY', receipt['provider_capabilities'])

    def test_full_quota_keeps_read_acceptance_available(self):
        policy, replies = fixture()
        storage = replies[PATHS[1]][1]
        storage.update(readyBytes=2048, reservedBytes=0, logicalBytes=2048,
                       cleanupReservedBytes=0, chargedBytes=2048, availableBytes=0, uploadsAvailable=False)
        self.assertTrue(self.verify(policy, replies)['history_read_available'])

    def test_runtime_mode_and_misconfigured_assistant_are_rejected(self):
        for mode in ('disabled', 'history-only', 'enabled'):
            policy, replies = fixture(mode)
            replies[PATHS[0]][1]['executionAvailable'] = mode != 'enabled'
            with self.subTest(mode=mode), self.assertRaisesRegex(Refused, 'runtime_mode'):
                self.verify(policy, replies)
        policy, replies = fixture()
        replies[PATHS[2]] = (503, {'status': 503, 'code': 'ASSISTANT_EXECUTION_MISCONFIGURED'})
        with self.assertRaisesRegex(Refused, 'http_json_contract'):
            self.verify(policy, replies)

    def test_storage_binding_and_accounting_fail_closed(self):
        for key, bad in [('policyStatus', 'MISSING'), ('historyOnly', True), ('quotaBytes', 999),
                         ('draftLifetimeSeconds', 24), ('cleanupEnabled', True), ('readyBytes', -1),
                         ('chargedBytes', 250), ('availableBytes', 2048), ('uploadsAvailable', False),
                         ('pendingCleanupBytes', 331), ('logicalBytes', True)]:
            policy, replies = fixture()
            replies[PATHS[1]][1][key] = bad
            with self.subTest(key=key), self.assertRaises(Refused):
                self.verify(policy, replies)

    def test_registry_binding_identity_and_declared_capabilities(self):
        cases = [('configSha256', 'b' * 64), ('contractVersion', True), ('models', [])]
        for key, bad in cases:
            policy, replies = fixture()
            replies[PATHS[2]][1][key] = bad
            with self.subTest(key=key), self.assertRaises(Refused):
                self.verify(policy, replies)

    def test_artwork_only_profile_binds_disabled_registry_without_network_probe(self):
        policy, replies = fixture()
        policy['upgrade']['assistant']['retrieval_profile'] = 'artwork-only-v1'
        replies[PATHS[2]][1]['retrieval'] = {'state': 'NOT_CONFIGURED'}
        receipt = self.verify(policy, replies)
        self.assertTrue(receipt['ragflow_registry_disabled'])
        self.assertEqual('artwork-only-v1', receipt['retrieval_profile'])
        for invalid in (None, {}, {'state': 'AVAILABLE'}, {'state': 'DISABLED'},
                        {'state': 'NOT_CONFIGURED', 'baseUrl': 'https://unapproved.invalid'}):
            replies[PATHS[2]][1]['retrieval'] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(Refused, 'ragflow_must_be_disabled'):
                self.verify(policy, replies)

    def test_unknown_retrieval_profile_rejected_in_all_modes(self):
        for mode in ('disabled', 'history-only', 'enabled'):
            policy, replies = fixture(mode)
            policy['upgrade']['assistant']['retrieval_profile'] = 'allow-anything'
            with self.subTest(mode=mode), self.assertRaisesRegex(Refused, 'retrieval_profile'):
                self.verify(policy, replies)

    def test_registry_model_safety_is_preserved(self):
        for mutation in ('duplicate', 'unsupported-images', 'none-configured'):
            policy, replies = fixture()
            models = replies[PATHS[2]][1]['models']
            if mutation == 'duplicate':
                models[1]['id'] = models[0]['id']
            elif mutation == 'unsupported-images':
                models[1]['capabilities']['imageMimeTypes'].append('image/webp')
            else:
                for model in models:
                    model['configured'] = False
            with self.subTest(mutation=mutation), self.assertRaises(Refused):
                self.verify(policy, replies)

    def test_anonymous_exposure_and_invalid_history_page_are_rejected(self):
        policy, replies = fixture()
        _, auth, _ = self.adapters(replies)
        with self.assertRaisesRegex(Refused, 'http_json_contract'):
            verify_assistant_http(policy, get=auth, get_authenticated=auth)
        for page in ({'items': [], 'hasMore': True, 'nextCursor': None},
                     {'items': [{}, {}], 'hasMore': False, 'nextCursor': None}):
            replies[PATHS[3]] = (200, page)
            with self.assertRaisesRegex(Refused, 'history_page'):
                self.verify(policy, replies)

    def test_duration_binding_accepts_same_exact_seconds(self):
        for lifetime in ('PT3600S', 'PT60M', 'PT1H', 'P0DT1H', 'PT3600.0S'):
            policy, replies = fixture()
            policy['upgrade']['configuration']['assistant']['storage.draft-lifetime'] = lifetime
            self.verify(policy, replies)
        for lifetime in ('PT0S', 'P', 'PT0.1S', 3600):
            policy, replies = fixture()
            policy['upgrade']['configuration']['assistant']['storage.draft-lifetime'] = lifetime
            with self.assertRaises(Refused):
                self.verify(policy, replies)

    def test_real_loopback_http_keeps_private_bearer_off_receipt_and_issues_only_get(self):
        policy, replies = fixture()
        calls = []
        synthetic_token = 'isolated-synthetic-token-123456'

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                authed = self.headers.get('Authorization') == 'Bearer ' + synthetic_token
                calls.append((self.command, self.path, authed))
                status, body = replies[self.path] if authed else (401, {'status': 401, 'code': 'UNAUTHORIZED'})
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            result = verify_assistant_http(policy,
                get=lambda path: request(path, port=port),
                get_authenticated=lambda path: request(path, port=port, bearer=synthetic_token))
            self.assertEqual(8, len(calls))
            self.assertTrue(all(method == 'GET' and path in PATHS for method, path, _ in calls))
            self.assertEqual(4, sum(auth for _, _, auth in calls))
            self.assertNotIn(synthetic_token, json.dumps(result))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
