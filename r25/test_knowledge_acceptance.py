"""GET-only Knowledge acceptance with bounded synthetic HTTP responses."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import core_acceptance as acceptance
from core_release_guard import Refused


class KnowledgeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.policy = {'upgrade': {'configuration': {'knowledge': {
            'graph-sha256': '1'*64, 'stats-sha256': '2'*64, 'china-sha256': '3'*64}}}}
        self.stats = {'schemaVersion': 1, 'population': {'key': 'gallery-displayable', 'count': 6},
            'authorNames': {'count': 2, 'eligibleRecords': 3}, 'metrics': {}}
        for name in ('dynasty', 'category', 'geography', 'style', 'imagery', 'sentiment', 'sentimentByDynasty'):
            self.stats['metrics'][name] = {'status': 'available', 'eligibleRecords': 3,
                'missingOrRestrictedRecords': 3, 'unmatchedRecords': 1, 'items': []}
        self.graph = {'schemaVersion': 1, 'source': 'legacy-poetry-snapshot',
            'graphSha256': '1'*64, 'statsSha256': '2'*64, 'nodeCount': 2, 'edgeCount': 1,
            'nodes': [{'id':'one'}, {'id':'two'}], 'links': [{'source':'one','target':'two'}]}
        self.china = {'type': 'FeatureCollection', 'sha256':'3'*64, 'features':[{}]}
        self.detail = {'sourceSequence':None, 'imageStorageName':None, 'annotations':[{'visibility':'public'}]}

    def query(self, sql):
        self.assertEqual(sql, acceptance.PRIVATE_SAMPLE_SQL)
        return json.dumps([{'painting_id':'11111111-1111-4111-8111-111111111111',
                           'hidden_sequence':True,'hidden_image':True}])

    def get(self, path, authenticated=False):
        self.calls.append((path, authenticated))
        status = 200
        if path.startswith('/api/v1/paintings?'):
            result = {'totalElements':6, 'items':[]}
        elif not authenticated:
            status, result = 401, {'code':'UNAUTHORIZED', 'status':401}
        elif path.endswith('/painting-statistics'): result = self.stats
        elif path.endswith('/poetry-graph'): result = self.graph
        elif path.endswith('/china-map'): result = self.china
        else: result = self.detail
        return status, 'application/json', json.dumps(result).encode()

    def verify(self, auth=None):
        return acceptance.verify_knowledge_http(self.query, self.policy, get=self.get,
            get_authenticated=auth or (lambda path: self.get(path, True)))

    def test_get_only_auth_hashes_coverage_and_public_details(self):
        receipt = self.verify()
        self.assertEqual(receipt['gallery_total'], 6)
        self.assertEqual(receipt['node_count'], 2)
        self.assertEqual(receipt['authenticated_projection_samples'], 1)
        self.assertEqual(receipt['write_requests'], 0)
        self.assertEqual(len(self.calls), 9)
        self.assertNotIn('annotations', json.dumps(receipt))

    def test_missing_assets_or_expired_session_never_accept(self):
        for status in (401, 503):
            with self.subTest(status=status), self.assertRaisesRegex(Refused, 'http_json_contract'):
                self.verify(lambda _: (status, 'application/json', b'{}'))

    def test_denominator_coverage_graph_hash_endpoints_and_private_leaks_refuse(self):
        for change in ('count','coverage','hash','edge','private','annotation'):
            with self.subTest(change=change):
                originals = deepcopy((self.stats,self.graph,self.detail))
                if change == 'count': self.stats['population']['count'] = 5
                if change == 'coverage': self.stats['metrics']['category']['eligibleRecords'] = 7
                if change == 'hash': self.graph['graphSha256'] = '4'*64
                if change == 'edge': self.graph['links'][0]['source'] = 'missing'
                if change == 'private': self.detail['imageStorageName'] = '/private/fixture'
                if change == 'annotation': self.detail['annotations'][0]['visibility'] = 'private'
                with self.assertRaises(Refused): self.verify()
                self.stats,self.graph,self.detail = originals

    def test_session_input_cannot_inject_headers_or_be_logged(self):
        for token in (None, '', 'abc\r\nHeader: value', 'short'):
            with self.assertRaisesRegex(Refused, 'session_format'): acceptance.authenticated_request(token)
        token = 'synthetic-session-never-real'
        with patch.object(acceptance, 'request', return_value=(200,'application/json',b'{}')) as get:
            acceptance.authenticated_request(token)(acceptance.KNOWLEDGE_PATHS[0])
        get.assert_called_once_with(acceptance.KNOWLEDGE_PATHS[0], 'application/json', bearer=token)


if __name__ == '__main__': unittest.main()
