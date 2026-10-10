"""Read-only PostgreSQL/HTTP checks for the fixed local R25 Core endpoint.

No login, task creation, provider invocation or database mutation occurs. The
caller supplies its hash-bound readonly psql adapter and holds the shared lease.
Live checks complement, and do not replace, the executable equivalence gate.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from core_release_guard import Refused, must

IDLE_SQL = """BEGIN READ ONLY; SET LOCAL statement_timeout='8000ms';
SELECT (SELECT count(*) FROM creations WHERE status IN ('QUEUED','RUNNING'))
+(SELECT count(*) FROM catalog_painting_critic_tasks WHERE status IN ('QUEUED','RUNNING'))
+(SELECT count(*) FROM catalog_painting_guide_generation_attempts
 WHERE status IN ('DISPATCHING','POST_RESPONSE_UNCERTAIN')); ROLLBACK;"""

PRIVATE_SAMPLE_SQL = """BEGIN READ ONLY; SET LOCAL statement_timeout='8000ms';
SELECT coalesce(jsonb_agg(item),'[]'::jsonb)::text FROM (
 SELECT sr.painting_id::text AS painting_id,
 bool_or(fd.field_key='source.original_sequence' AND fd.visibility<>'public') AS hidden_sequence,
 bool_or(fd.field_key IN ('source.relative_image','source.original_image_reference') AND fd.visibility<>'public') AS hidden_image
 FROM catalog_source_records sr
 JOIN catalog_batch_current_revisions cr ON cr.batch_id=sr.batch_id AND cr.revision=sr.revision
 JOIN catalog_paintings p ON p.public_id=sr.painting_id
  AND p.current_batch_id=sr.batch_id AND p.current_revision=sr.revision
 JOIN catalog_annotation_field_definitions fd ON fd.batch_id=sr.batch_id
  AND fd.revision=sr.revision AND fd.annotation_file_id=sr.annotation_file_id
 WHERE fd.field_key IN ('source.original_sequence','source.relative_image','source.original_image_reference')
 GROUP BY sr.painting_id
 HAVING bool_or(fd.visibility<>'public')
 ORDER BY sr.painting_id LIMIT 3
) item; ROLLBACK;"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refused('http_redirect_refused')


def request(path, accept='application/json'):
    must(type(path) is str and path.startswith('/api/v1/') and
         not any(x in path for x in ('://', '\\', '\r', '\n', '#')), 'fixed_http_path')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request('http://127.0.0.1:19080' + path,
                                 headers={'Accept': accept}, method='GET')
    try:
        response = opener.open(req, timeout=8)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError) as error:
        raise Refused('local_http_unavailable') from error
    with response:
        body = response.read(2 * 1024 * 1024 + 1)
        must(len(body) <= 2 * 1024 * 1024, 'http_response_limit')
        return response.status, response.headers.get_content_type(), body


def json_response(path, expected_status=200, get=request):
    status, content_type, raw = get(path)
    must(status == expected_status and content_type == 'application/json', 'http_json_contract')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise Refused('http_json_parse') from error
    must(type(value) is dict, 'http_json_object')
    return value


def verify_http(query, *, minimum_total=1, get=request):
    gallery = json_response('/api/v1/paintings?page=0&size=1', get=get)
    items = gallery.get('items')
    total = gallery.get('totalElements')
    must(type(total) is int and total >= minimum_total and isinstance(items, list) and
         len(items) == 1 and isinstance(items[0], dict), 'gallery_pagination_contract')
    painting = items[0].get('paintingId')
    must(type(painting) is str and re.fullmatch('[0-9a-fA-F-]{36}', painting), 'gallery_painting_identity')
    # SecurityConfig explicitly protects detail/guide/critic. A successful
    # anonymous detail response is a regression, not a readiness success.
    detail = json_response('/api/v1/paintings/' + painting, 401, get=get)
    must(detail.get('code') == 'UNAUTHORIZED' and detail.get('status') == 401,
         'detail_authentication_contract')
    unknown = '00000000-0000-4000-8000-000000000000'
    missing_detail = json_response('/api/v1/paintings/' + unknown, 401, get=get)
    must(missing_detail.get('code') == 'UNAUTHORIZED' and missing_detail.get('status') == 401,
         'unknown_detail_authentication_contract')
    # The Accept image path must still return JSON for business errors.
    def image_get(path):
        return get(path, 'image/*,application/octet-stream')
    json_response('/api/v1/assets/' + unknown + '/content', 404, get=image_get)
    try:
        samples = json.loads(query(PRIVATE_SAMPLE_SQL))
    except (ValueError, UnicodeError) as error:
        raise Refused('private_projection_sample_unknown') from error
    must(type(samples) is list and len(samples) <= 3, 'private_projection_sample_shape')
    for item in samples:
        must(type(item) is dict and set(item) == {'painting_id', 'hidden_sequence', 'hidden_image'},
             'private_projection_sample_shape')
        identity = item['painting_id']
        must(type(identity) is str and re.fullmatch('[0-9a-f-]{36}', identity), 'private_projection_identity')
        must(type(item['hidden_sequence']) is bool and type(item['hidden_image']) is bool,
             'private_projection_flags')
        sample = json_response('/api/v1/paintings/' + identity, 401, get=get)
        must(sample.get('code') == 'UNAUTHORIZED' and sample.get('status') == 401,
             'private_detail_authentication_contract')
    return {'schema': 'R25_CORE_READONLY_HTTP_ACCEPTANCE_V1', 'gallery_total': total,
            'anonymous_gallery': True, 'detail_requires_authentication': True,
            'public_asset_json_error': True,
            'private_projection_pg_sample_count': len(samples),
            'authenticated_detail_projection': 'NOT_EXERCISED_NO_TEST_CREDENTIAL',
            'private_projection_live_samples': 0,
            'write_requests': 0, 'provider_requests': 0}
