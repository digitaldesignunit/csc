"""
Request bodies are capped before a route reads them (decision 8.163): per
route group from the settings, 413 on a `Content-Length` over the cap without
reading, and on a chunked body as soon as the cap is passed.
"""

from __future__ import annotations

import pytest

from apps.catalog import body_limit
from apps.catalog.body_limit import MB, MULTIPART_OVERHEAD_BYTES

MESH = '/snapshots/s1/meshes/0/reduced'
CLOUD = '/snapshots/s1/point_clouds/0.ply'
PHOTO = '/snapshots/s1/photos/0'
ATTACHMENT = '/evidence/attachments'
RESULT = '/geometry/results/s1'
JSON_ROUTE = '/auth/register'


@pytest.fixture(autouse=True)
def small_limits(env):
    env(CSC_JSON_BODY_LIMIT_MB='1', GEOMETRY_UPLOAD_LIMIT_MB='2',
        EVIDENCE_UPLOAD_LIMIT_MB='3', SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB='4')


def chunks(total, size=64 * 1024):
    def generate():
        left = total
        while left > 0:
            part = min(size, left)
            left -= part
            yield b'x' * part
    return generate()


# THE CAPS ----------------------------------------------------------------------
def test_each_group_has_its_cap_from_the_settings():
    assert body_limit.body_cap('PUT', MESH) == 2 * MB + MULTIPART_OVERHEAD_BYTES
    assert body_limit.body_cap('PUT', CLOUD) == 2 * MB + MULTIPART_OVERHEAD_BYTES
    assert body_limit.body_cap('POST', ATTACHMENT) == 3 * MB + MULTIPART_OVERHEAD_BYTES
    assert body_limit.body_cap('PUT', PHOTO) == 4 * MB + MULTIPART_OVERHEAD_BYTES
    assert body_limit.body_cap('POST', JSON_ROUTE) == 1 * MB
    assert body_limit.body_cap('PATCH', '/identities/x') == 1 * MB
    assert body_limit.body_cap('POST', RESULT) is None        # its own limits


def test_the_defaults(env):
    env(CSC_JSON_BODY_LIMIT_MB=None, GEOMETRY_UPLOAD_LIMIT_MB=None,
        EVIDENCE_UPLOAD_LIMIT_MB=None, SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB=None)
    assert body_limit.body_cap('POST', JSON_ROUTE) == 16 * MB
    assert body_limit.body_cap('PUT', MESH) == 251 * MB
    assert body_limit.body_cap('POST', ATTACHMENT) == 26 * MB
    assert body_limit.body_cap('PUT', PHOTO) == 11 * MB


def test_what_the_runner_and_the_gh_component_send_fits_the_json_cap():
    """The result route of the remote runner is exempt. The inline geometry of
    a snapshot is at most 1000 faces and points (8.148): well under 16 MB."""
    faces = 1000
    vertices = [[123456.789012, -98765.432101, 0.123456789012]] * (3 * faces)
    import json
    size = len(json.dumps({'meshes': [{'vertices': vertices,
                                       'faces': [[0, 1, 2]] * faces}]}))
    assert size < 16 * MB / 20


# JSON ROUTES -------------------------------------------------------------------
def test_a_content_length_over_the_cap_is_413_before_the_route_runs(api, db):
    body = b'{"username":"' + b'a' * (1 * MB) + b'"}'
    response = api.post(JSON_ROUTE, content=body,
                        headers={'Content-Type': 'application/json'})
    assert response.status_code == 413, response.text[:200]
    assert '1 MB' in response.json()['detail']


def test_a_body_just_under_the_cap_reaches_the_route(api):
    pad = 'a' * (1 * MB - 4096)
    body = ('{"username":"' + pad + '"}').encode()
    response = api.post(JSON_ROUTE, content=body,
                        headers={'Content-Type': 'application/json'})
    assert response.status_code == 422, response.text[:200]    # the route ran


def test_a_chunked_body_over_the_cap_is_413(api):
    response = api.post(JSON_ROUTE, content=chunks(1 * MB + 1),
                        headers={'Content-Type': 'application/json'})
    assert response.status_code == 413, response.text[:200]


def test_a_chunked_body_just_under_the_cap_reaches_the_route(api):
    response = api.post(JSON_ROUTE, content=chunks(1 * MB - 1),
                        headers={'Content-Type': 'application/json'})
    assert response.status_code == 422, response.text[:200]    # not JSON: the route ran


def test_a_get_is_never_capped(api):
    assert api.get('/health').status_code in (200, 404)


# FILE ROUTES -------------------------------------------------------------------
@pytest.mark.parametrize('method, path, cap_mb', [
    ('PUT', MESH, 2), ('PUT', CLOUD, 2), ('POST', ATTACHMENT, 3), ('PUT', PHOTO, 4),
])
def test_an_upload_over_its_cap_is_413_and_one_under_is_not(api, method, path, cap_mb):
    cap = cap_mb * MB + MULTIPART_OVERHEAD_BYTES
    boundary = '----cscboundary'
    headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}

    def multipart(size):
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="f"; '
                f'filename="f.bin"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        tail = f'\r\n--{boundary}--\r\n'.encode()
        return head + b'x' * (size - len(head) - len(tail)) + tail

    over = api.request(method, path, content=multipart(cap + 1), headers=headers)
    assert over.status_code == 413, (path, over.status_code, over.text[:200])
    chunked = api.request(method, path, content=chunks(cap + 1), headers=headers)
    assert chunked.status_code == 413, (path, chunked.status_code)
    under = api.request(method, path, content=multipart(cap - 1024), headers=headers)
    assert under.status_code != 413, (path, under.text[:200])      # the route (or auth) answered


def test_the_result_route_of_the_remote_runner_keeps_its_own_limits(api):
    big = b'x' * (5 * MB)             # over the 1 MB JSON cap
    response = api.post(RESULT, content=big,
                        headers={'Content-Type': 'application/octet-stream'})
    assert response.status_code != 413, response.text[:200]


def test_the_413_carries_the_cors_headers(api):
    response = api.post(JSON_ROUTE, content=b'x' * (1 * MB + 1),
                        headers={'Content-Type': 'application/json',
                                 'Origin': 'http://localhost:3000'})
    assert response.status_code == 413
    assert response.headers.get('access-control-allow-origin') == 'http://localhost:3000'
