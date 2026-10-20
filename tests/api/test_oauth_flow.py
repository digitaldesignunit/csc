"""
CSC as an OAuth server for Claude's connectors (decision 8.168): discovery,
registration, authorization with PKCE, the consent of a signed-in account, the
code exchange, refresh with rotation and the end of a connection, the redirect
rules, and who may allow. The MCP endpoint behind the tokens is covered in
test_mcp_endpoint.py.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.catalog import access_tokens as tk
from apps.catalog import oauth_server as oa
from oauth_helpers import (
    CALLBACK,
    RESOURCE,
    authorize,
    bearer,
    code_of,
    connect,
    exchange,
    mcp_post,
    pkce,
    refresh,
    register,
    request_id_of,
    reset_address_counters,
)


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def admin(make_user, login):
    user = make_user('adminuser', role='admin')
    token = login('adminuser').json()['access_token']
    return {**user, 'headers': bearer(token)}


@pytest.fixture
def member(make_user, login):
    user = make_user('memberuser', role='user')
    token = login('memberuser').json()['access_token']
    return {**user, 'headers': bearer(token)}


# THE REDIRECT RULES, WITHOUT A SERVER ---------------------------------------------
@pytest.mark.parametrize('uri', [
    CALLBACK, 'http://localhost/callback', 'http://127.0.0.1/callback',
    'http://localhost:3118/callback', 'http://127.0.0.1:54321/callback'])
def test_these_redirect_uris_may_be_registered(uri):
    assert oa.redirect_allowed(uri)


@pytest.mark.parametrize('uri', [
    'https://claude.ai/api/mcp/auth_callback/', 'https://claude.ai/other',
    'http://claude.ai/api/mcp/auth_callback', 'https://evil.example/cb',
    'https://claude.ai.evil.example/api/mcp/auth_callback',
    'http://localhost/other', 'http://localhost.evil.example/callback',
    'http://localhost:abc/callback', 'http://0.0.0.0/callback',
    'http://[::1]/callback', 'https://localhost/callback',
    'http://user:pw@localhost/callback', 'http://localhost/callback?x=1',
    'http://localhost/callback#frag', 'javascript:alert(1)',
    'custom-app://callback', 'https://claude.ai/api/mcp/auth_callback?x=1'])
def test_no_other_redirect_uri_may_be_registered(uri):
    assert not oa.redirect_allowed(uri)


def test_a_loopback_redirect_matches_on_any_port_and_nothing_else_does():
    registered = ['http://localhost:3118/callback']
    assert oa.redirect_matches('http://localhost:9999/callback', registered)
    assert oa.redirect_matches('http://localhost/callback', registered)
    assert not oa.redirect_matches('http://127.0.0.1:3118/callback', registered)
    assert not oa.redirect_matches('http://localhost:3118/other', registered)
    assert not oa.redirect_matches('https://claude.ai/api/mcp/auth_callback', registered)
    exact = [CALLBACK]
    assert oa.redirect_matches(CALLBACK, exact)
    assert not oa.redirect_matches(CALLBACK + '?x=1', exact)


# DISCOVERY ---------------------------------------------------------------------------
def test_an_unauthenticated_mcp_call_is_401_with_the_resource_metadata(api):
    for response in (api.get('/mcp'), api.post('/mcp', json={})):
        assert response.status_code == 401
        challenge = response.headers['www-authenticate']
        assert challenge.startswith('Bearer ')
        assert 'resource_metadata="http://localhost/.well-known/oauth-protected-resource/mcp"' in challenge


def test_the_protected_resource_names_the_url_exactly_and_one_server(api):
    meta = api.get('/.well-known/oauth-protected-resource/mcp').json()
    assert meta['resource'] == RESOURCE == 'http://localhost/mcp'
    assert len(meta['authorization_servers']) == 1
    assert meta['authorization_servers'][0].rstrip('/') == 'http://localhost'
    assert meta['scopes_supported'] == ['read:catalog']


def test_the_authorization_server_metadata_advertises_what_claude_needs(api):
    meta = api.get('/.well-known/oauth-authorization-server').json()
    assert meta['issuer'].rstrip('/') == 'http://localhost'
    assert meta['authorization_endpoint'] == 'http://localhost/authorize'
    assert meta['token_endpoint'] == 'http://localhost/token'
    assert meta['registration_endpoint'] == 'http://localhost/register'
    assert meta['code_challenge_methods_supported'] == ['S256']
    assert 'none' in meta['token_endpoint_auth_methods_supported']
    assert 'authorization_code' in meta['grant_types_supported']
    assert 'refresh_token' in meta['grant_types_supported']
    assert meta['response_types_supported'] == ['code']
    # no client id metadata documents: Claude falls back to registration
    assert 'client_id_metadata_document_supported' not in meta


def test_the_discovery_routes_need_no_client_header_or_sign_in(api, app):
    app.state.min_client_versions = {'web': (0, 6, 0, 0)}
    try:
        for path in ('/.well-known/oauth-protected-resource/mcp',
                     '/.well-known/oauth-authorization-server'):
            assert api.get(path, headers={'X-CSC-Client': ''}).status_code == 200
        assert register(api).status_code in (201, 400)
        assert api.post('/register', json={'redirect_uris': [CALLBACK]},
                        headers={'X-CSC-Client': ''}).status_code != 426
    finally:
        app.state.min_client_versions = {}


# REGISTRATION ---------------------------------------------------------------------------
def test_a_client_registers_with_claudes_callback_or_a_loopback_one(api):
    for uri in (CALLBACK, 'http://localhost:3118/callback', 'http://127.0.0.1/callback'):
        response = register(api, [uri])
        assert response.status_code == 201, (uri, response.text)
        body = response.json()
        assert body['client_id'] and body['scope'] == 'read:catalog'
        assert body['redirect_uris'] == [uri]


@pytest.mark.parametrize('uris', [['https://evil.example/cb'],
                                  [CALLBACK, 'https://evil.example/cb'],
                                  ['http://localhost/other'], []])
def test_any_other_redirect_uri_is_refused_at_registration(api, uris):
    response = register(api, uris)
    assert response.status_code == 400, response.text
    assert response.json()['error'] in ('invalid_redirect_uri', 'invalid_client_metadata')


def utc_now():
    """Mongo hands datetimes back without a time zone, in UTC."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


def close_to(moment, days, minutes=5):
    return abs((moment - utc_now()) - timedelta(days=days)) < timedelta(minutes=minutes)


def ttl_indexes(db):
    return [v for v in db['oauth_clients'].index_information().values()
            if v.get('expireAfterSeconds') is not None]


def test_a_registration_lives_one_day_until_somebody_consents(api, db):
    client_id = register(api).json()['client_id']
    stored = db['oauth_clients'].find_one({'_id': client_id})
    assert stored['info']['client_name'] == 'Claude' and stored['last_used']
    assert stored['consented'] is False and close_to(stored['expires_at'], 1)
    # one TTL index, on expires_at, deletes a document when that date has passed;
    # the index of the earlier build (on last_used) is gone
    ttl = ttl_indexes(db)
    assert len(ttl) == 1 and ttl[0]['key'] == [('expires_at', 1)] and ttl[0]['expireAfterSeconds'] == 0


def test_the_ttl_rule_takes_an_unconsented_client_after_a_day_and_a_consented_one_after_thirty(api, db, admin):
    lonely = register(api).json()['client_id']
    consented = connect(api, admin['headers'])['client_id']
    horizon = utc_now() + timedelta(days=2)
    due = {d['_id'] for d in db['oauth_clients'].find({'expires_at': {'$lt': horizon}})}
    assert lonely in due and consented not in due                      # the rule, not the clock
    assert close_to(db['oauth_clients'].find_one({'_id': consented})['expires_at'], 30)
    assert close_to(db['oauth_clients'].find_one({'_id': lonely})['expires_at'], 1)


def test_the_first_granted_consent_moves_the_client_to_thirty_days_and_a_deny_does_not(api, db, admin):
    allowed, _, rid = start(api)
    denied, _, rid_denied = start(api)
    api.post(f'/oauth/requests/{rid_denied}/decision', json={'allow': False}, headers=admin['headers'])
    assert db['oauth_clients'].find_one({'_id': denied})['consented'] is False
    assert close_to(db['oauth_clients'].find_one({'_id': denied})['expires_at'], 1)
    api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers'])
    stored = db['oauth_clients'].find_one({'_id': allowed})
    assert stored['consented'] is True and close_to(stored['expires_at'], 30)


def test_a_member_who_may_not_allow_does_not_consent_the_client(api, db, member):
    client_id, _, rid = start(api)
    api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=member['headers'])
    assert db['oauth_clients'].find_one({'_id': client_id})['consented'] is False


def test_using_an_unconsented_client_does_not_extend_its_day(api, db):
    client_id = register(api).json()['client_id']
    db['oauth_clients'].update_one({'_id': client_id}, {'$set': {'last_used': utc_now() - timedelta(hours=3)}})
    before = db['oauth_clients'].find_one({'_id': client_id})['expires_at']
    _, challenge = pkce()
    assert authorize(api, client_id, challenge).status_code == 302
    after = db['oauth_clients'].find_one({'_id': client_id})
    assert after['expires_at'] == before and after['consented'] is False



def test_a_long_client_name_is_cut(api):
    body = register(api, name='x' * 500).json()
    assert len(body['client_name']) <= oa.CLIENT_NAME_MAX


# AUTHORIZE ---------------------------------------------------------------------------------
def test_authorize_sends_the_browser_to_the_consent_page_with_a_request_id(api, db):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    response = authorize(api, client_id, challenge)
    rid = request_id_of(response)
    assert len(rid) >= 40
    stored = db['oauth_requests'].find_one({})
    assert rid not in repr(stored)                       # only its hash is stored
    assert stored['client_id'] == client_id and stored['bound_user'] is None
    assert stored['redirect_uri'] == CALLBACK and stored['state'] == 'st-1'


def test_pkce_is_required_and_only_s256(api):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    without = authorize(api, client_id, None)
    assert without.status_code in (302, 400)
    assert 'error=invalid_request' in without.headers.get('location', '') or without.status_code == 400
    plain = authorize(api, client_id, challenge, code_challenge_method='plain')
    assert 'error=invalid_request' in plain.headers.get('location', '') or plain.status_code == 400
    assert 'oauth/consent' not in plain.headers.get('location', '')


def test_an_unregistered_redirect_never_receives_the_browser(api):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    for bad in ('https://evil.example/cb', 'http://localhost/callback'):
        response = authorize(api, client_id, challenge, redirect_uri=bad)
        assert response.status_code == 400, response.text
        assert 'location' not in response.headers
        assert response.json()['error'] == 'invalid_request'


def test_an_unknown_client_is_refused_without_a_redirect(api):
    _, challenge = pkce()
    response = authorize(api, 'no-such-client', challenge)
    assert response.status_code == 400 and 'location' not in response.headers


def test_a_loopback_port_is_matched_without_the_port(api):
    client_id = register(api, ['http://localhost:3118/callback']).json()['client_id']
    _, challenge = pkce()
    response = authorize(api, client_id, challenge, redirect_uri='http://localhost:54000/callback')
    assert request_id_of(response)


def test_another_resource_or_scope_is_refused(api):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    other = authorize(api, client_id, challenge, resource='https://elsewhere.example/mcp')
    assert 'error=invalid_request' in other.headers['location']
    assert other.headers['location'].startswith(CALLBACK)
    scope = authorize(api, client_id, challenge, scope='read:catalog write:catalog')
    assert 'error=invalid_scope' in scope.headers['location']


def test_a_wrong_response_type_is_unsupported(api):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    response = authorize(api, client_id, challenge, response_type='token')
    assert 'error=unsupported_response_type' in response.headers.get('location', '') \
        or response.status_code == 400


# THE CONSENT --------------------------------------------------------------------------------
def start(api):
    client_id = register(api).json()['client_id']
    verifier, challenge = pkce()
    return client_id, verifier, request_id_of(authorize(api, client_id, challenge))


def test_the_consent_view_names_the_host_and_the_tool_and_binds_the_request(api, admin, member):
    client_id, _, rid = start(api)
    view = api.get(f'/oauth/requests/{rid}', headers=admin['headers'])
    assert view.status_code == 200 and view.headers['cache-control'] == 'no-store'
    assert view.json() == {
        'redirect_host': 'claude.ai', 'redirect_is_loopback': False,
        'client_name': 'Claude', 'access': 'Read access to the catalog, as you see it',
        'can_allow': True, 'refusal': None}
    assert api.get(f'/oauth/requests/{rid}', headers=admin['headers']).status_code == 200
    # bound to the first account: another one gets the answer of an unknown id
    other = api.get(f'/oauth/requests/{rid}', headers=member['headers'])
    missing = api.get('/oauth/requests/' + 'A' * 43, headers=member['headers'])
    assert other.status_code == missing.status_code == 404 and other.json() == missing.json()
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                    headers=member['headers']).status_code == 404


def test_a_loopback_redirect_is_marked_in_the_view(api, admin):
    client_id = register(api, ['http://127.0.0.1:3118/callback']).json()['client_id']
    _, challenge = pkce()
    rid = request_id_of(authorize(api, client_id, challenge, redirect_uri='http://127.0.0.1:3118/callback'))
    view = api.get(f'/oauth/requests/{rid}', headers=admin['headers']).json()
    assert view['redirect_host'] == '127.0.0.1' and view['redirect_is_loopback'] is True


def test_the_consent_needs_a_signed_in_account(api):
    _, _, rid = start(api)
    assert api.get(f'/oauth/requests/{rid}').status_code == 401
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}).status_code == 401


def test_allow_returns_the_callback_with_a_code_and_the_clients_state(api, admin):
    client_id, verifier, rid = start(api)
    decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers'])
    assert decision.status_code == 200 and decision.headers['cache-control'] == 'no-store'
    target = urlsplit(decision.json()['redirect_to'])
    assert f'{target.scheme}://{target.netloc}{target.path}' == CALLBACK
    query = parse_qs(target.query)
    assert query['state'] == ['st-1'] and len(query['code'][0]) >= 40


def test_deny_returns_access_denied_with_the_state_and_no_code(api, admin):
    _, _, rid = start(api)
    decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': False}, headers=admin['headers'])
    query = parse_qs(urlsplit(decision.json()['redirect_to']).query)
    assert query['error'] == ['access_denied'] and query['state'] == ['st-1']
    assert 'code' not in query


def test_a_request_is_answered_once(api, admin):
    _, _, rid = start(api)
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers']).status_code == 200
    again = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers'])
    assert again.status_code == 404 and 'no longer valid' in again.json()['detail']
    assert api.get(f'/oauth/requests/{rid}', headers=admin['headers']).status_code == 404


def test_a_request_ends_after_10_minutes(api, db, admin):
    _, _, rid = start(api)
    from datetime import datetime, timezone
    db['oauth_requests'].update_many({}, {'$set': {'expire_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert api.get(f'/oauth/requests/{rid}', headers=admin['headers']).status_code == 404
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers']).status_code == 404
    ttl = [v for v in db['oauth_requests'].index_information().values() if v.get('expireAfterSeconds') is not None]
    assert ttl and ttl[0]['key'] == [('expire_at', 1)]


def test_a_member_may_not_allow_and_the_request_stays_open_for_deny(api, db, member):
    _, _, rid = start(api)
    view = api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()
    assert view['can_allow'] is False and 'may not connect tools' in view['refusal']
    refused = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=member['headers'])
    assert refused.status_code == 403
    assert db['oauth_codes'].count_documents({}) == 0
    denied = api.post(f'/oauth/requests/{rid}/decision', json={'allow': False}, headers=member['headers'])
    assert denied.status_code == 200 and 'access_denied' in denied.json()['redirect_to']


def test_the_setting_lets_a_member_allow(api, member, env):
    env(CSC_PAT_ROLES='admin,user')
    _, _, rid = start(api)
    assert api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()['can_allow'] is True
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=member['headers']).status_code == 200


def test_nothing_is_remembered_every_connection_asks_again(api, admin):
    first = connect(api, admin['headers'])
    client_id = first['client_id']
    _, challenge = pkce()
    again = authorize(api, client_id, challenge)
    rid = request_id_of(again)                       # asks, does not skip the page
    assert api.get(f'/oauth/requests/{rid}', headers=admin['headers']).status_code == 200


# THE TOKEN ENDPOINT ----------------------------------------------------------------------------
def test_the_code_buys_an_access_and_a_refresh_token(api, db, admin):
    c = connect(api, admin['headers'])
    body = c['body']
    assert body['token_type'] == 'Bearer' and body['expires_in'] == 3600 and body['scope'] == 'read:catalog'
    assert body['access_token'].startswith('csc_oat_') and body['refresh_token'].startswith('csc_ort_')
    row = db['access_tokens'].find_one({'kind': 'oauth'})
    assert row['owner_user_id'] == admin['id'] and row['scopes'] == ['read:catalog']
    assert row['token_sha256'] == tk.token_hash(c['access']) and row['refresh_sha256'] == tk.token_hash(c['refresh'])
    assert c['access'] not in repr(row) and c['refresh'] not in repr(row)
    created = tk.parse_stamp(row['created'])
    assert tk.parse_stamp(row['expires']) - created == timedelta(days=90)
    assert tk.parse_stamp(row['access_expires']) - created == timedelta(hours=1)
    assert tk.parse_stamp(row['refresh_expires']) - created == timedelta(days=30)
    assert row['name'] == 'Claude (claude.ai)' and row['redirect_host'] == 'claude.ai'


def test_the_token_endpoint_takes_form_bodies_and_answers_no_store(api, admin):
    c = connect(api, admin['headers'])
    response = refresh(api, c['client_id'], c['refresh'])
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.request.headers['content-type'].startswith('application/x-www-form-urlencoded')


def test_a_code_works_once_and_a_second_use_ends_the_connection(api, db, admin):
    c = connect(api, admin['headers'])
    again = exchange(api, c['client_id'], c['code'], c['verifier'])
    assert again.status_code == 400 and again.json()['error'] == 'invalid_grant'
    assert db['access_tokens'].find_one({'kind': 'oauth'})['revoked']
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401
    assert refresh(api, c['client_id'], c['refresh']).json()['error'] == 'invalid_grant'


def test_a_wrong_verifier_redirect_client_or_code_is_refused(api, admin):
    client_id, verifier, rid = start(api)
    code = code_of(api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers=admin['headers']).json()['redirect_to'])
    wrong_verifier = exchange(api, client_id, code, pkce()[0])
    assert wrong_verifier.status_code == 400 and wrong_verifier.json()['error'] == 'invalid_grant'
    wrong_redirect = exchange(api, client_id, code, verifier, redirect_uri='https://claude.ai/api/mcp/other')
    assert wrong_redirect.status_code == 400
    other_client = register(api).json()['client_id']
    assert exchange(api, other_client, code, verifier).json()['error'] == 'invalid_grant'
    assert exchange(api, client_id, 'not-a-code', verifier).json()['error'] == 'invalid_grant'
    # none of those used the code
    assert exchange(api, client_id, code, verifier).status_code == 200


def test_an_expired_code_is_refused(api, db, admin):
    client_id, verifier, rid = start(api)
    code = code_of(api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers=admin['headers']).json()['redirect_to'])
    db['oauth_codes'].update_many({}, {'$set': {'expires_at': 1.0}})
    assert exchange(api, client_id, code, verifier).json()['error'] == 'invalid_grant'


def test_a_code_is_good_for_five_minutes(api, db, admin):
    import time
    client_id, verifier, rid = start(api)
    api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers'])
    stored = db['oauth_codes'].find_one({})
    assert 250 < stored['expires_at'] - time.time() <= 300
    assert stored['code_challenge'] and 'code' not in stored


def test_the_owner_losing_the_role_before_the_exchange_stops_the_connection(api, db, admin):
    client_id, verifier, rid = start(api)
    code = code_of(api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers=admin['headers']).json()['redirect_to'])
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'user'}})
    assert exchange(api, client_id, code, verifier).json()['error'] == 'invalid_grant'
    assert db['access_tokens'].count_documents({'kind': 'oauth'}) == 0


# REFRESH AND ROTATION ---------------------------------------------------------------------------
def test_a_refresh_makes_new_tokens_and_the_old_ones_are_dead_at_once(api, db, admin):
    c = connect(api, admin['headers'])
    new = refresh(api, c['client_id'], c['refresh'])
    assert new.status_code == 200, new.text
    body = new.json()
    assert body['access_token'] != c['access'] and body['refresh_token'] != c['refresh']
    assert body['access_token'].startswith('csc_oat_') and body['refresh_token'].startswith('csc_ort_')
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401        # old access
    assert mcp_post(api, body['access_token'], 'tools/list').status_code == 200
    old = refresh(api, c['client_id'], c['refresh'])
    assert old.status_code == 400 and old.json()['error'] == 'invalid_grant'
    assert db['oauth_used_refresh'].count_documents({}) == 1
    assert db['access_tokens'].count_documents({'kind': 'oauth'}) == 1         # one row per connection


def test_the_reuse_of_a_rotated_refresh_token_ends_the_whole_connection(api, db, admin):
    c = connect(api, admin['headers'])
    new = refresh(api, c['client_id'], c['refresh']).json()
    reuse = refresh(api, c['client_id'], c['refresh'])
    assert reuse.json()['error'] == 'invalid_grant'
    assert db['access_tokens'].find_one({'kind': 'oauth'})['revoked']
    assert mcp_post(api, new['access_token'], 'tools/list').status_code == 401
    assert refresh(api, c['client_id'], new['refresh_token']).json()['error'] == 'invalid_grant'


def test_a_refresh_chain_keeps_working_when_each_token_is_used_once(api, admin):
    c = connect(api, admin['headers'])
    token = c['refresh']
    for _ in range(4):
        body = refresh(api, c['client_id'], token).json()
        assert body['access_token'].startswith('csc_oat_')
        token = body['refresh_token']
    assert mcp_post(api, body['access_token'], 'tools/list').status_code == 200


def test_a_refresh_token_never_passes_the_access_check(api, admin):
    c = connect(api, admin['headers'])
    assert mcp_post(api, c['refresh'], 'tools/list').status_code == 401
    assert api.get('/auth/token-check', headers=bearer(c['refresh'])).status_code == 401
    assert api.get('/users/me', headers=bearer(c['refresh'])).status_code == 401
    assert api.get('/users/me', headers=bearer(c['access'])).status_code == 401      # not a JWT either
    # and an access token is no refresh token
    assert refresh(api, c['client_id'], c['access']).json()['error'] == 'invalid_grant'


def test_a_refresh_by_another_client_is_refused(api, admin):
    c = connect(api, admin['headers'])
    other = register(api).json()['client_id']
    assert refresh(api, other, c['refresh']).json()['error'] == 'invalid_grant'
    assert refresh(api, c['client_id'], c['refresh']).status_code == 200      # the right one still works


def test_a_refresh_token_is_good_30_days_after_its_last_use(api, db, admin):
    c = connect(api, admin['headers'])
    db['access_tokens'].update_one({'kind': 'oauth'}, {'$set': {'refresh_expires': tk.stamp(tk.now() - timedelta(seconds=1))}})
    assert refresh(api, c['client_id'], c['refresh']).json()['error'] == 'invalid_grant'
    c2 = connect(api, admin['headers'])
    # a use moves the date forward by 30 days from that use
    new = refresh(api, c2['client_id'], c2['refresh'])
    assert new.status_code == 200
    row = db['access_tokens'].find_one({'refresh_sha256': tk.token_hash(new.json()['refresh_token'])})
    assert tk.parse_stamp(row['refresh_expires']) - tk.now() > timedelta(days=29, hours=23)


def test_the_hard_limit_is_90_days_from_the_consent(api, db, admin):
    c = connect(api, admin['headers'])
    row = db['access_tokens'].find_one({'kind': 'oauth'})
    soon = tk.stamp(tk.now() + timedelta(days=2))
    db['access_tokens'].update_one({'_id': row['_id']}, {'$set': {'expires': soon}})
    body = refresh(api, c['client_id'], c['refresh'])
    assert body.status_code == 200
    now = db['access_tokens'].find_one({'_id': row['_id']})
    assert now['refresh_expires'] <= soon and now['access_expires'] <= soon      # never past the limit
    assert tk.parse_stamp(now['refresh_expires']) - tk.now() < timedelta(days=2, minutes=1)
    # past the limit nothing works: the access token, the refresh token
    db['access_tokens'].update_one({'_id': row['_id']}, {'$set': {'expires': tk.stamp(tk.now() - timedelta(seconds=1))}})
    assert mcp_post(api, body.json()['access_token'], 'tools/list').status_code == 401
    assert refresh(api, c['client_id'], body.json()['refresh_token']).json()['error'] == 'invalid_grant'


def test_an_access_token_lasts_an_hour(api, db, admin):
    c = connect(api, admin['headers'])
    assert mcp_post(api, c['access'], 'tools/list').status_code == 200
    db['access_tokens'].update_one({'kind': 'oauth'}, {'$set': {'access_expires': tk.stamp(tk.now() - timedelta(seconds=1))}})
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401
    # the refresh token still gets a new one
    assert refresh(api, c['client_id'], c['refresh']).status_code == 200


def test_the_owner_losing_the_role_or_the_account_stops_both_tokens(api, db, admin):
    c = connect(api, admin['headers'])
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'user'}})
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401
    assert refresh(api, c['client_id'], c['refresh']).json()['error'] == 'invalid_grant'
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'admin'}})
    assert mcp_post(api, c['access'], 'tools/list').status_code == 200        # the role is checked on every request
    db['users'].delete_one({'_id': admin['id']})
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401


# REVOKE ---------------------------------------------------------------------------------------------
def test_a_connection_is_in_the_list_and_revoking_it_ends_access_and_refresh(api, admin):
    c = connect(api, admin['headers'])
    rows = api.get('/auth/access-tokens', headers=admin['headers']).json()
    assert [r['kind'] for r in rows] == ['oauth']
    row = rows[0]
    assert row['name'] == 'Claude (claude.ai)' and row['renew_due'] is False and row['status'] == 'active'
    assert 'token' not in row and c['access'] not in str(rows)
    done = api.delete(f'/auth/access-tokens/{row["id"]}', headers=admin['headers'])
    assert done.status_code == 200 and done.json()['status'] == 'revoked'
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401
    assert refresh(api, c['client_id'], c['refresh']).json()['error'] == 'invalid_grant'
    assert api.post(f'/auth/access-tokens/{row["id"]}/renew', headers=admin['headers']).status_code in (404, 409)


def test_an_admin_sees_and_revokes_any_connection(api, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    c = connect(api, member['headers'], name='Claude Code')
    listed = api.get('/admin/access-tokens', headers=admin['headers']).json()
    row = next(r for r in listed if r['kind'] == 'oauth')
    assert row['owner_username'] == 'memberuser' and 'email' not in row
    assert api.delete(f'/admin/access-tokens/{row["id"]}', headers=admin['headers']).status_code == 200
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401


def test_the_client_can_revoke_either_token_and_both_end(api, admin):
    c = connect(api, admin['headers'])
    done = api.post('/revoke', data={'token': c['refresh'], 'client_id': c['client_id'], 'client_secret': ''})
    assert done.status_code == 200
    assert mcp_post(api, c['access'], 'tools/list').status_code == 401
    d = connect(api, admin['headers'])
    assert api.post('/revoke', data={'token': d['access'], 'client_id': d['client_id'], 'client_secret': ''}).status_code == 200
    assert refresh(api, d['client_id'], d['refresh']).json()['error'] == 'invalid_grant'


def test_connections_do_not_count_against_the_limit_of_ten_tokens(api, admin):
    for index in range(3):
        connect(api, admin['headers'])
    for index in range(10):
        made = api.post('/auth/access-tokens', json={'name': f'p{index}'}, headers=admin['headers'])
        assert made.status_code == 201, (index, made.text)
    assert api.post('/auth/access-tokens', json={'name': 'one more'}, headers=admin['headers']).status_code == 409


def test_a_consented_client_gets_thirty_days_from_each_use_written_at_most_hourly(api, db, admin):
    c = connect(api, admin['headers'])
    clients = db['oauth_clients']
    first = clients.find_one({'_id': c['client_id']})
    refresh(api, c['client_id'], c['refresh'])                     # within the hour: not written
    again = clients.find_one({'_id': c['client_id']})
    assert (again['last_used'], again['expires_at']) == (first['last_used'], first['expires_at'])
    # an hour and more later a use pushes the date out again
    clients.update_one({'_id': c['client_id']}, {'$set': {
        'last_used': utc_now() - timedelta(hours=2), 'expires_at': utc_now() + timedelta(days=3)}})
    _, challenge = pkce()
    authorize(api, c['client_id'], challenge)                      # get_client runs
    assert close_to(clients.find_one({'_id': c['client_id']})['expires_at'], 30)



# LIMITS PER ADDRESS ------------------------------------------------------------------------------------
def test_register_authorize_and_token_are_limited_per_address(api):
    for _ in range(30):
        assert register(api).status_code == 201
    limited = register(api)
    assert limited.status_code == 429 and limited.headers['retry-after'] == '60'
    assert limited.json()['error'] == 'rate_limited'
    reset_address_counters()
    client_id = register(api).json()['client_id']
    for _ in range(120):
        assert api.post('/token', data={'grant_type': 'authorization_code', 'code': 'x', 'client_id': client_id,
                                        'code_verifier': 'v' * 43}).status_code == 400
    assert api.post('/token', data={'grant_type': 'authorization_code', 'code': 'x', 'client_id': client_id,
                                    'code_verifier': 'v' * 43}).status_code == 429
    reset_address_counters()
    _, challenge = pkce()
    for _ in range(30):
        assert authorize(api, client_id, challenge).status_code == 302
    assert authorize(api, client_id, challenge).status_code == 429


# THE MAINTENANCE FLAG -------------------------------------------------------------------------------------
def test_under_the_flag_the_connection_works_and_rotates_but_a_new_one_is_refused(api, db, admin, read_only_flag):
    c = connect(api, admin['headers'])
    read_only_flag.on()
    assert mcp_post(api, c['access'], 'tools/list').status_code == 200
    assert db['access_tokens'].find_one({'kind': 'oauth'})['last_used'] is None      # not written under the flag
    rotated = refresh(api, c['client_id'], c['refresh'])
    assert rotated.status_code == 200, rotated.text                                # a token write, allowed
    assert mcp_post(api, rotated.json()['access_token'], 'tools/list').status_code == 200
    # a new registration, a new consent, a revoke
    assert register(api).status_code == 503
    _, challenge = pkce()
    refused = authorize(api, c['client_id'], challenge)
    assert refused.status_code == 302 and 'error=temporarily_unavailable' in refused.headers['location']
    assert api.post('/revoke', data={'token': c['refresh'], 'client_id': c['client_id'], 'client_secret': ''}).status_code == 503
    row = db['access_tokens'].find_one({'kind': 'oauth'})
    assert api.delete(f'/auth/access-tokens/{row["_id"]}', headers=admin['headers']).status_code == 503
    read_only_flag.off()
    assert db['access_tokens'].find_one({'kind': 'oauth'})['revoked'] is None


def test_a_consent_decision_under_the_flag_is_the_503(api, admin, read_only_flag):
    _, _, rid = start(api)
    read_only_flag.on()
    for allow in (True, False):
        refused = api.post(f'/oauth/requests/{rid}/decision', json={'allow': allow}, headers=admin['headers'])
        assert refused.status_code == 503 and refused.json() == {'detail': 'read-only: maintenance'}
    read_only_flag.off()
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=admin['headers']).status_code == 200


# THE CLIENT HEADER ----------------------------------------------------------------------------------------
def test_the_connector_needs_no_client_header_anywhere_in_its_flow(api, app, admin):
    app.state.min_client_versions = {'web': (0, 6, 0, 0), 'gh-userobjects': (0, 6, 0, 0)}
    try:
        none = {'X-CSC-Client': ''}
        client_id = api.post('/register', json={'client_name': 'C', 'redirect_uris': [CALLBACK],
                                                'token_endpoint_auth_method': 'none'}, headers=none).json()['client_id']
        verifier, challenge = pkce()
        resp = api.get('/authorize', params={'response_type': 'code', 'client_id': client_id, 'redirect_uri': CALLBACK,
                                             'code_challenge': challenge, 'code_challenge_method': 'S256'},
                       headers=none, follow_redirects=False)
        rid = request_id_of(resp)
        # the consent routes belong to the web app, which sends its header
        decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers={**admin['headers'], 'X-CSC-Client': 'web/0.6.2.1'})
        assert decision.status_code == 200, decision.text
        token = api.post('/token', headers=none, data={
            'grant_type': 'authorization_code', 'code': code_of(decision.json()['redirect_to']),
            'redirect_uri': CALLBACK, 'client_id': client_id, 'code_verifier': verifier})
        assert token.status_code == 200, token.text
        assert mcp_post(api, token.json()['access_token'], 'tools/list', headers=none).status_code == 200
        assert api.get('/users/me', headers={**admin['headers'], **none}).status_code == 426
    finally:
        app.state.min_client_versions = {}


# NOT CONFIGURED ----------------------------------------------------------------------------------------------
def test_without_a_public_api_url_nothing_is_installed():
    from fastapi import FastAPI
    from apps.catalog import oauth_wiring

    class Off:
        csc_public_api_url = ''
        frontend_url = 'http://localhost:3000'

    fresh = FastAPI()
    before = len(fresh.router.routes)
    assert oauth_wiring.install(fresh, Off()) is False
    assert len(fresh.router.routes) == before and fresh.state.oauth_provider is None
