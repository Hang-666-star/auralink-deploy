import json
import unittest

from core_acceptance import verify_http
from core_release_guard import Refused


class ReadonlyHttpTest(unittest.TestCase):
    identity = '11111111-1111-4111-8111-111111111111'

    def fixture(self, leak=False, html_error=False, total=9553):
        calls = []
        def get(path, accept='application/json'):
            calls.append((path, accept))
            if path.startswith('/api/v1/assets/'):
                return 404, 'text/html' if html_error else 'application/json', b'{"code":"NOT_FOUND"}'
            if '?' in path:
                body = {'totalElements': total, 'items': [{'paintingId': self.identity}]}
            else:
                if leak:
                    return 200, 'application/json', json.dumps({'paintingId': self.identity, 'sourceSequence': 'private'}).encode()
                return 401, 'application/json', b'{"code":"UNAUTHORIZED","status":401}'
            return 200, 'application/json', json.dumps(body).encode()
        def query(sql):
            self.assertTrue(sql.startswith('BEGIN READ ONLY;'))
            self.assertTrue(sql.endswith('ROLLBACK;'))
            return json.dumps([{'painting_id': self.identity, 'hidden_sequence': True, 'hidden_image': True}])
        return calls, get, query

    def test_real_contract_shapes_and_image_accept_error(self):
        calls, get, query = self.fixture()
        receipt = verify_http(query, get=get)
        self.assertEqual(receipt['gallery_total'], 9553)
        self.assertEqual(receipt['private_projection_live_samples'], 0)
        self.assertEqual(receipt['private_projection_pg_sample_count'], 1)
        self.assertEqual(receipt['authenticated_detail_projection'], 'NOT_EXERCISED_NO_TEST_CREDENTIAL')
        self.assertEqual(receipt['write_requests'], 0)
        self.assertTrue(any(accept.startswith('image/') for _, accept in calls))

    def test_anonymous_detail_exposure_refused(self):
        _, get, query = self.fixture(leak=True)
        with self.assertRaisesRegex(Refused, 'http_json_contract'):
            verify_http(query, get=get)

    def test_error_dispatch_html_refused(self):
        _, get, query = self.fixture(html_error=True)
        with self.assertRaisesRegex(Refused, 'http_json_contract'):
            verify_http(query, get=get)

    def test_gallery_loss_refused(self):
        _, get, query = self.fixture(total=1)
        with self.assertRaisesRegex(Refused, 'gallery_pagination_contract'):
            verify_http(query, get=get, minimum_total=9553)

    def test_unknown_database_sample_is_not_zero(self):
        _, get, _ = self.fixture()
        with self.assertRaises(Refused):
            verify_http(lambda _: 'connection failed', get=get)


if __name__ == '__main__':
    unittest.main()
