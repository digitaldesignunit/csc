"""
Failed access-token lookups are limited per client address (0.6.3.1): a token
that is unknown, revoked, expired or of the wrong scope counts for the address
in the shared store, and over the limit the answer is 429 with Retry-After
instead of 401. A valid token never counts and is never refused because of
what else comes from its address; no header at all counts nothing. The same
holds for /mcp.
"""

from __future__ import annotations

import pytest
from limits import parse

from apps.catalog import access_tokens as tk
from apps.catalog import token_check
from oauth_helpers import bearer, connect, mcp_post, reset_address_counters

LONG_AGO = '2000-01-01T00:00:00.000000Z'
UNKNOWN = 'csc_pat_' + 'A' * 43
LIMIT = 4


@pytest.fixture(autouse=True)
def tight_limit(monkeypatch):
    """Four failures a minute, and clean counters before and after."""
    monkeypatch.setattr(token_check, '_FAILED', parse(f'{LIMIT}/minute'))
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def owner(make_user, login):
    user = make_user('tokenowner', role='admin')
    return {**user, 'headers': bearer(login('tokenowner').json()['access_token'])}


def make_pat(api, owner):
    return api.post('/auth/access-tokens', json={'name': 'script'},
                    headers=owner['headers']).json()


def check(api, token, **headers):
    return api.get('/auth/token-check', headers={**bearer(token), **headers})


def fail_until_limited(api, token=UNKNOWN, limit=LIMIT):
    """The failed lookups the limit allows, each a 401."""
    for _ in range(limit):
        assert check(api, token).status_code == 401


def test_over_the_limit_a_failed_lookup_is_a_429_with_retry_after(api):
    fail_until_limited(api)
    answer = check(api, UNKNOWN)
    assert answer.status_code == 429
    assert 1 <= int(answer.headers['Retry-After']) <= 61
    assert 'failed attempts' in answer.json()['detail']
    assert 'WWW-Authenticate' not in answer.headers


def test_a_valid_token_is_not_affected_by_the_failures_of_its_address(api, owner):
    pat = make_pat(api, owner)['token']
    fail_until_limited(api)
    assert check(api, UNKNOWN).status_code == 429
    assert check(api, pat).status_code == 200
    assert check(api, pat).status_code == 200


def test_valid_requests_never_count(api, owner):
    pat = make_pat(api, owner)['token']
    for _ in range(LIMIT * 3):
        assert check(api, pat).status_code == 200
    assert check(api, UNKNOWN).status_code == 401       # the first failure only


def test_a_request_without_a_token_counts_nothing(api):
    for _ in range(LIMIT * 3):
        assert api.get('/auth/token-check').status_code == 401
    assert check(api, UNKNOWN).status_code == 401


def test_a_revoked_token_counts(api, owner):
    row = make_pat(api, owner)
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=owner['headers'])
    fail_until_limited(api, row['token'])
    assert check(api, row['token']).status_code == 429


def test_an_expired_token_counts(api, db, owner):
    row = make_pat(api, owner)
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {'expires': LONG_AGO}})
    fail_until_limited(api, row['token'])
    assert check(api, row['token']).status_code == 429


def test_a_token_of_the_wrong_scope_counts(api, db, owner):
    row = make_pat(api, owner)
    db['access_tokens'].update_one(
        {'_id': row['id']}, {'$set': {'scopes': [tk.SCOPE_GH]}})
    fail_until_limited(api, row['token'])
    assert check(api, row['token']).status_code == 429


def test_a_jwt_sent_as_an_access_token_counts(api, owner):
    jwt = owner['headers']['Authorization'].split(' ', 1)[1]
    fail_until_limited(api, jwt)
    assert check(api, jwt).status_code == 429


def test_the_count_is_per_address(api, monkeypatch):
    from apps.catalog.api import access_tokens as routes
    monkeypatch.setattr(routes, 'client_ip', lambda request: request.headers['x-test-address'])
    for _ in range(LIMIT):
        assert check(api, UNKNOWN, **{'x-test-address': '203.0.113.1'}).status_code == 401
    assert check(api, UNKNOWN, **{'x-test-address': '203.0.113.1'}).status_code == 429
    assert check(api, UNKNOWN, **{'x-test-address': '203.0.113.2'}).status_code == 401


def test_the_count_is_in_the_shared_store_not_in_the_worker(api):
    """Another worker counts in the same store: its hits show here."""
    import limiter as lim
    other_worker = lim.shared_limiter._limiter           # what every worker uses
    item = token_check._FAILED
    for _ in range(LIMIT):
        assert other_worker.hit(item, 'token-failures', 'testclient')
    assert check(api, UNKNOWN).status_code == 429


def test_the_limit_is_not_applied_to_a_wrong_sign_in(api):
    """The sign-in has its own limit; failed tokens do not use it up."""
    fail_until_limited(api)
    assert api.post('/auth/token', data={'username': 'nobody', 'password': 'x'}).status_code == 401


# /mcp ---------------------------------------------------------------------------
def test_mcp_failures_are_limited_and_a_valid_connection_still_works(api, owner):
    good = connect(api, owner['headers'])
    for _ in range(LIMIT):
        assert mcp_post(api, UNKNOWN, 'tools/list').status_code == 401
    limited = mcp_post(api, UNKNOWN, 'tools/list')
    assert limited.status_code == 429
    assert int(limited.headers['Retry-After']) >= 1
    assert 'failed attempts' in limited.json()['error_description']
    assert mcp_post(api, good['access'], 'tools/list').status_code == 200


def test_failures_on_mcp_and_on_the_rest_share_one_count(api):
    for _ in range(LIMIT - 1):
        assert mcp_post(api, UNKNOWN, 'tools/list').status_code == 401
    assert check(api, UNKNOWN).status_code == 401                 # the 4th
    assert check(api, UNKNOWN).status_code == 429
    assert mcp_post(api, UNKNOWN, 'tools/list').status_code == 429


def test_mcp_without_a_token_counts_nothing(api):
    for _ in range(LIMIT * 2):
        assert mcp_post(api, None, 'tools/list').status_code == 401
    assert mcp_post(api, UNKNOWN, 'tools/list').status_code == 401
