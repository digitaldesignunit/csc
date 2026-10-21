"""
Grasshopper signs in without a password (decision 8.168 f): the authorization
code flow with PKCE and a loopback redirect, on the OAuth server of the MCP
layer, for the fixed public client ``csc-grasshopper``. Open to every verified
account (no role), a consent variant for scope gh:client, rows of kind device,
the normal CSC JWT of one hour as the access token, a refresh token that
rotates, and the two scopes kept apart both ways.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest

from apps.catalog import access_tokens as tk
from apps.catalog import oauth_server as oa
from oauth_helpers import (
    CALLBACK,
    bearer,
    code_of,
    exchange,
    mcp_post,
    pkce,
    refresh,
    register,
    request_id_of,
    reset_address_counters,
)

CLIENT = 'csc-grasshopper'
REDIRECT = 'http://127.0.0.1:54321/callback'


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def member(make_user, login):
    user = make_user('memberuser', role='user')
    token = login('memberuser').json()['access_token']
    return {**user, 'headers': bearer(token)}


@pytest.fixture
def admin(make_user, login):
    user = make_user('adminuser', role='admin')
    token = login('adminuser').json()['access_token']
    return {**user, 'headers': bearer(token)}


def authorize_gh(api, challenge, redirect_uri=REDIRECT, computer='WORKSTATION-7', **extra):
    params = {'response_type': 'code', 'client_id': CLIENT, 'redirect_uri': redirect_uri,
              'code_challenge': challenge, 'code_challenge_method': 'S256',
              'state': 'gh-state', 'scope': 'gh:client', 'computer': computer, **extra}
    params = {k: v for k, v in params.items() if v is not None}
    return api.get('/authorize', params=params, follow_redirects=False)


def sign_in(api, user, computer='WORKSTATION-7', redirect_uri=REDIRECT):
    """The whole flow of the client: returns the token answer and more."""
    verifier, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge, redirect_uri, computer))
    decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=user['headers'])
    assert decision.status_code == 200, decision.text
    code = code_of(decision.json()['redirect_to'])
    token = exchange(api, CLIENT, code, verifier, redirect_uri)
    assert token.status_code == 200, token.text
    body = token.json()
    return {'access': body['access_token'], 'refresh': body['refresh_token'], 'body': body,
            'code': code, 'verifier': verifier, 'request_id': rid, 'decision': decision.json()}


def claims(token):
    return jwt.decode(token, options={'verify_signature': False})


# THE FIXED CLIENT ---------------------------------------------------------------------------
def test_the_client_is_fixed_public_and_loopback_only():
    client = oa.GH_CLIENT
    assert client.client_id == CLIENT == oa.GH_CLIENT_ID
    assert client.token_endpoint_auth_method == 'none' and client.client_secret is None
    assert client.scope == 'gh:client' and [str(u) for u in client.redirect_uris] == ['http://127.0.0.1/callback']


def test_it_needs_no_registration_and_leaves_no_client_row(api, db, member):
    sign_in(api, member)
    assert db['oauth_clients'].count_documents({}) == 0


@pytest.mark.parametrize('redirect', ['http://127.0.0.1:1/callback', 'http://127.0.0.1:65535/callback',
                                      'http://127.0.0.1/callback'])
def test_any_port_on_127_0_0_1_is_accepted(api, redirect):
    _, challenge = pkce()
    assert request_id_of(authorize_gh(api, challenge, redirect))


@pytest.mark.parametrize('redirect', ['http://localhost:54321/callback', CALLBACK, 'http://127.0.0.1:54321/other',
                                      'https://127.0.0.1:54321/callback', 'http://127.0.0.2:54321/callback',
                                      'http://192.168.0.5:54321/callback', 'http://evil.example/callback',
                                      'http://127.0.0.1:54321/callback?x=1'])
def test_every_other_redirect_is_refused_and_never_receives_the_browser(api, redirect):
    _, challenge = pkce()
    response = authorize_gh(api, challenge, redirect)
    assert response.status_code == 400, (redirect, response.text)
    assert 'location' not in response.headers and response.json()['error'] == 'invalid_request'


def test_the_client_gets_gh_client_only_and_a_dcr_client_never_gets_it(api):
    _, challenge = pkce()
    wrong = authorize_gh(api, challenge, scope='read:catalog')
    assert 'error=invalid_scope' in wrong.headers['location']
    both = authorize_gh(api, challenge, scope='gh:client read:catalog')
    assert 'error=invalid_scope' in both.headers['location']
    assert request_id_of(authorize_gh(api, challenge, scope=None))             # the default scope is its own
    dcr = register(api).json()['client_id']
    other = api.get('/authorize', params={
        'response_type': 'code', 'client_id': dcr, 'redirect_uri': CALLBACK, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'scope': 'gh:client', 'resource': 'http://localhost/mcp'},
        follow_redirects=False)
    assert 'error=invalid_scope' in other.headers['location']


def test_the_client_sends_no_resource_and_pkce_is_required(api):
    _, challenge = pkce()
    assert 'error=invalid_request' in authorize_gh(api, challenge, resource='http://localhost/mcp').headers['location']
    without = authorize_gh(api, None)
    assert without.status_code in (302, 400) and 'oauth/consent' not in without.headers.get('location', '')
    plain = authorize_gh(api, challenge, code_challenge_method='plain')
    assert 'oauth/consent' not in plain.headers.get('location', '')


# THE CONSENT --------------------------------------------------------------------------------------
def test_the_consent_view_is_the_grasshopper_variant(api, member):
    _, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge, computer='WORKSTATION-7'))
    view = api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()
    assert view == {
        'redirect_host': '127.0.0.1', 'redirect_is_loopback': True, 'client_name': None,
        'scope': 'gh:client', 'computer': 'WORKSTATION-7',
        'access': 'Grasshopper on this computer: act as you in the Grasshopper interface',
        'can_allow': True, 'refusal': None}


def test_a_member_may_allow_without_a_role_while_a_tool_that_reads_the_catalog_still_needs_one(api, member):
    _, _, = pkce()
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    rid = request_id_of(api.get('/authorize', params={
        'response_type': 'code', 'client_id': client_id, 'redirect_uri': CALLBACK, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'scope': 'read:catalog', 'resource': 'http://localhost/mcp'},
        follow_redirects=False))
    view = api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()
    assert view['scope'] == 'read:catalog' and view['can_allow'] is False
    assert sign_in(api, member)['body']['scope'] == 'gh:client'


def test_an_admin_may_allow_it_too_and_the_setting_changes_nothing_here(api, admin, member, env):
    assert sign_in(api, admin)['access']
    env(CSC_PAT_ROLES='admin')
    assert sign_in(api, member)['access']
    env(CSC_PAT_ROLES='user')
    assert sign_in(api, admin)['access']


def test_an_account_with_an_unverified_address_cannot_allow(api, db, member):
    _, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge))
    db['users'].update_one({'_id': member['id']}, {'$set': {'email_verified': False}})
    view = api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()
    assert view['can_allow'] is False and 'not verified' in view['refusal']
    refused = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=member['headers'])
    assert refused.status_code == 403
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': False}, headers=member['headers']).status_code == 200


def test_the_computer_name_is_shown_as_plain_cut_text(api, member):
    cases = [('<script>alert(1)</script> PC & "co"', 'scriptalert(1)/script PC co'),
             ('x' * 200, 'x' * 60), ('  two   spaces  ', 'two spaces'), ('', None),
             ('tab\tand\x00null\x1fcontrol', 'tabandnullcontrol')]
    for sent, shown in cases:
        _, challenge = pkce()
        rid = request_id_of(authorize_gh(api, challenge, computer=sent or None))
        assert api.get(f'/oauth/requests/{rid}', headers=member['headers']).json()['computer'] == shown, sent


def test_the_computer_name_of_any_other_client_is_ignored(api, db):
    client_id = register(api).json()['client_id']
    _, challenge = pkce()
    request_id_of(api.get('/authorize', params={
        'response_type': 'code', 'client_id': client_id, 'redirect_uri': CALLBACK, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'resource': 'http://localhost/mcp', 'computer': 'EVIL'},
        follow_redirects=False))
    assert db['oauth_requests'].find_one({})['computer'] is None


def test_the_answer_goes_to_the_loopback_listener_with_the_state(api, member):
    decision = sign_in(api, member)['decision']['redirect_to']
    target = urlsplit(decision)
    assert f'{target.scheme}://{target.netloc}{target.path}' == REDIRECT
    assert parse_qs(target.query)['state'] == ['gh-state']
    _, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge))
    deny = api.post(f'/oauth/requests/{rid}/decision', json={'allow': False}, headers=member['headers'])
    query = parse_qs(urlsplit(deny.json()['redirect_to']).query)
    assert query['error'] == ['access_denied'] and query['state'] == ['gh-state'] and 'code' not in query


# THE TOKENS ---------------------------------------------------------------------------------------
def test_the_access_token_is_the_normal_jwt_of_one_hour_and_the_refresh_token_is_a_device_token(api, db, member):
    got = sign_in(api, member)
    body = got['body']
    assert body['token_type'] == 'Bearer' and body['expires_in'] == 3600 and body['scope'] == 'gh:client'
    assert got['refresh'].startswith('csc_dev_') and len(got['refresh']) == len('csc_dev_') + 43
    c = claims(got['access'])
    assert c['sub'] == member['id'] and c['role'] == 'user' and c['exp'] - c['iat'] == 3600
    row = db['access_tokens'].find_one({'kind': 'device'})
    assert row['owner_user_id'] == member['id'] and row['scopes'] == ['gh:client']
    assert row['name'] == 'Grasshopper on WORKSTATION-7' and row['redirect_host'] == '127.0.0.1'
    assert row['client_id'] == CLIENT and row['revoked'] is None
    assert row['refresh_sha256'] == tk.token_hash(got['refresh'])
    created = tk.parse_stamp(row['created'])
    assert tk.parse_stamp(row['expires']) - created == timedelta(days=90)
    assert tk.parse_stamp(row['refresh_expires']) - created == timedelta(days=30)
    # no secret in the row, and no hash that matches the access token or the refresh token as an access token
    assert got['refresh'] not in repr(row) and got['access'] not in repr(row)
    assert row['token_sha256'] not in (tk.token_hash(got['refresh']), tk.token_hash(got['access']))


def test_the_jwt_works_on_the_routes_the_grasshopper_components_use(api, member):
    got = sign_in(api, member)
    headers = bearer(got['access'])
    assert api.get('/users/me', headers=headers).json()['username'] == 'memberuser'
    for path in ('/identities', '/identities/count', '/datasets', '/schema/create-identity'):
        assert api.get(path, headers=headers).status_code == 200, path
    assert api.get('/identities', headers=headers).status_code == 200


def test_the_gh_scope_and_the_catalog_scope_stay_apart_both_ways(api, member, admin):
    gh = sign_in(api, member)
    # a Grasshopper token never reaches the MCP layer or the token check
    for token in (gh['access'], gh['refresh']):
        assert mcp_post(api, token, 'tools/list').status_code == 401
        assert api.get('/auth/token-check', headers=bearer(token)).status_code == 401
    assert api.get('/users/me', headers=bearer(gh['refresh'])).status_code == 401           # not a JWT
    # a catalog connection never reaches the routes of Grasshopper
    from oauth_helpers import connect
    claude = connect(api, admin['headers'])
    for token in (claude['access'], claude['refresh']):
        assert api.get('/users/me', headers=bearer(token)).status_code == 401
        assert api.get('/ghinterface/userobject_manifest', headers=bearer(token)).status_code == 401
        assert api.get('/identities', headers=bearer(token)).status_code in (401, 200)
    # and a refresh token of one kind is not accepted as the other
    assert refresh(api, CLIENT, claude['refresh']).json()['error'] == 'invalid_grant'
    assert refresh(api, claude['client_id'], gh['refresh']).json()['error'] == 'invalid_grant'
    # a device row has no access token to find
    assert mcp_post(api, tk.new_token('device'), 'tools/list').status_code == 401


# THE CODE ----------------------------------------------------------------------------------------------
def test_a_code_is_used_once_and_a_second_use_ends_the_sign_in(api, db, member):
    got = sign_in(api, member)
    again = exchange(api, CLIENT, got['code'], got['verifier'], REDIRECT)
    assert again.status_code == 400 and again.json()['error'] == 'invalid_grant'
    assert db['access_tokens'].find_one({'kind': 'device'})['revoked']
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'


def test_the_exchange_needs_the_verifier_the_redirect_and_the_client(api, member):
    verifier, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge))
    code = code_of(api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers=member['headers']).json()['redirect_to'])
    assert exchange(api, CLIENT, code, pkce()[0], REDIRECT).json()['error'] == 'invalid_grant'
    assert exchange(api, CLIENT, code, verifier, 'http://127.0.0.1:1/callback').status_code == 400
    other = register(api).json()['client_id']
    assert exchange(api, other, code, verifier, REDIRECT).json()['error'] == 'invalid_grant'
    assert exchange(api, CLIENT, code, verifier, REDIRECT).status_code == 200


def test_an_account_that_cannot_sign_in_any_more_gets_no_token(api, db, member):
    verifier, challenge = pkce()
    rid = request_id_of(authorize_gh(api, challenge))
    code = code_of(api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                            headers=member['headers']).json()['redirect_to'])
    db['users'].update_one({'_id': member['id']}, {'$set': {'disabled': True}})
    assert exchange(api, CLIENT, code, verifier, REDIRECT).json()['error'] == 'invalid_grant'
    assert db['access_tokens'].count_documents({'kind': 'device'}) == 0


# REFRESH ---------------------------------------------------------------------------------------------------
def test_a_refresh_gives_a_new_jwt_and_a_new_refresh_token_and_the_old_one_is_dead(api, db, member):
    got = sign_in(api, member)
    new = refresh(api, CLIENT, got['refresh'])
    assert new.status_code == 200, new.text
    body = new.json()
    assert body['refresh_token'].startswith('csc_dev_') and body['refresh_token'] != got['refresh']
    c = claims(body['access_token'])
    assert c['sub'] == member['id'] and c['exp'] - c['iat'] == 3600 and body['scope'] == 'gh:client'
    assert api.get('/users/me', headers=bearer(body['access_token'])).status_code == 200
    dead = refresh(api, CLIENT, got['refresh'])
    assert dead.status_code == 400 and dead.json()['error'] == 'invalid_grant'
    assert db['access_tokens'].count_documents({'kind': 'device'}) == 1
    assert db['access_tokens'].find_one({'kind': 'device'})['revoked']             # the reuse ended it
    assert refresh(api, CLIENT, body['refresh_token']).json()['error'] == 'invalid_grant'


def test_a_chain_of_refreshes_keeps_working_when_each_token_is_used_once(api, member):
    token = sign_in(api, member)['refresh']
    for _ in range(4):
        body = refresh(api, CLIENT, token).json()
        assert body['access_token'].count('.') == 2
        token = body['refresh_token']


def test_the_refresh_token_is_good_30_days_after_its_last_use_and_90_days_from_the_consent(api, db, member):
    got = sign_in(api, member)
    row = db['access_tokens'].find_one({'kind': 'device'})
    db['access_tokens'].update_one({'_id': row['_id']}, {'$set': {
        'refresh_expires': tk.stamp(tk.now() - timedelta(seconds=1))}})
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'
    got = sign_in(api, member)
    new = refresh(api, CLIENT, got['refresh'])
    fresh = db['access_tokens'].find_one({'refresh_sha256': tk.token_hash(new.json()['refresh_token'])})
    assert tk.parse_stamp(fresh['refresh_expires']) - tk.now() > timedelta(days=29, hours=23)
    soon = tk.stamp(tk.now() + timedelta(minutes=10))
    db['access_tokens'].update_one({'_id': fresh['_id']}, {'$set': {'expires': soon}})
    last = refresh(api, CLIENT, new.json()['refresh_token'])
    assert last.status_code == 200
    capped = db['access_tokens'].find_one({'_id': fresh['_id']})
    assert capped['refresh_expires'] <= soon                                    # never past the hard limit
    c = claims(last.json()['access_token'])
    assert c['exp'] - c['iat'] <= 600 + 60 and last.json()['expires_in'] <= 660   # the JWT never outlives it by much
    db['access_tokens'].update_one({'_id': fresh['_id']}, {'$set': {'expires': tk.stamp(tk.now() - timedelta(seconds=1))}})
    assert refresh(api, CLIENT, last.json()['refresh_token']).json()['error'] == 'invalid_grant'


def test_a_refresh_stops_when_the_account_is_disabled_unverified_or_deleted_but_not_for_a_lost_role(api, db, admin):
    got = sign_in(api, admin)
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'user'}})        # no role is needed
    got = {'refresh': refresh(api, CLIENT, got['refresh']).json()['refresh_token']}
    for change in ({'disabled': True}, {'email_verified': False}):
        db['users'].update_one({'_id': admin['id']}, {'$set': change})
        assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant', change
        db['users'].update_one({'_id': admin['id']}, {'$set': {'disabled': False, 'email_verified': True}})
        # the failed refresh did not use the token up
        replaced = refresh(api, CLIENT, got['refresh'])
        assert replaced.status_code == 200, replaced.text
        got = {'refresh': replaced.json()['refresh_token']}
    db['users'].delete_one({'_id': admin['id']})
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'


# THE LIST, REVOKE ---------------------------------------------------------------------------------------------
def test_the_sign_in_is_in_the_list_of_its_owner_who_revokes_it(api, db, member):
    got = sign_in(api, member, computer='LAPTOP-2')
    rows = api.get('/auth/access-tokens', headers=member['headers']).json()
    assert [(r['kind'], r['name'], r['scopes']) for r in rows] == [('device', 'Grasshopper on LAPTOP-2', ['gh:client'])]
    assert rows[0]['renew_due'] is False and 'token' not in rows[0]
    assert got['refresh'] not in str(rows)
    done = api.delete(f'/auth/access-tokens/{rows[0]["id"]}', headers=member['headers'])
    assert done.status_code == 200 and done.json()['status'] == 'revoked'
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'
    assert api.post(f'/auth/access-tokens/{rows[0]["id"]}/renew', headers=member['headers']).status_code in (404, 409)


def test_an_admin_sees_and_revokes_any_sign_in_and_the_list_of_ten_ignores_them(api, admin, member):
    got = sign_in(api, member, computer='LAPTOP-3')
    listed = api.get('/admin/access-tokens', headers=admin['headers']).json()
    row = next(r for r in listed if r['kind'] == 'device')
    assert row['owner_username'] == 'memberuser' and 'email' not in row
    assert api.delete(f'/admin/access-tokens/{row["id"]}', headers=admin['headers']).status_code == 200
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'
    for _ in range(3):
        sign_in(api, admin)
    for index in range(10):
        assert api.post('/auth/access-tokens', json={'name': f'p{index}'}, headers=admin['headers']).status_code == 201
    assert api.post('/auth/access-tokens', json={'name': 'one more'}, headers=admin['headers']).status_code == 409


def test_the_client_signs_out_by_revoking_its_refresh_token(api, member):
    got = sign_in(api, member)
    done = api.post('/revoke', data={'token': got['refresh'], 'client_id': CLIENT, 'client_secret': ''})
    assert done.status_code == 200
    assert refresh(api, CLIENT, got['refresh']).json()['error'] == 'invalid_grant'
    again = api.post('/revoke', data={'token': got['refresh'], 'client_id': CLIENT, 'client_secret': ''})
    assert again.status_code == 200                                              # a dead token: nothing to do


def test_the_jwt_is_not_ended_by_a_revoke_until_it_runs_out(api, member):
    """The access token is a stateless JWT (one hour): ending the sign-in stops
    the refresh at once and the JWT at its expiry, like a password sign-in."""
    got = sign_in(api, member)
    row = api.get('/auth/access-tokens', headers=member['headers']).json()[0]
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=member['headers'])
    assert api.get('/users/me', headers=bearer(got['access'])).status_code == 200


# THE MAINTENANCE FLAG AND THE HEADER -----------------------------------------------------------------------------
def test_under_the_flag_the_refresh_works_and_a_new_sign_in_is_refused(api, member, read_only_flag):
    got = sign_in(api, member)
    read_only_flag.on()
    assert refresh(api, CLIENT, got['refresh']).status_code == 200
    _, challenge = pkce()
    refused = authorize_gh(api, challenge)
    assert refused.status_code == 302 and 'error=temporarily_unavailable' in refused.headers['location']
    read_only_flag.off()
    rid = request_id_of(authorize_gh(api, challenge))
    read_only_flag.on()
    assert api.post(f'/oauth/requests/{rid}/decision', json={'allow': True},
                    headers=member['headers']).status_code == 503


def test_the_token_endpoint_needs_no_client_header(api, app, member):
    got = sign_in(api, member)
    app.state.min_client_versions = {'gh-userobjects': (0, 6, 3, 0)}
    try:
        none = {'X-CSC-Client': ''}
        assert api.post('/token', headers=none, data={
            'grant_type': 'refresh_token', 'refresh_token': got['refresh'], 'client_id': CLIENT}).status_code == 200
    finally:
        app.state.min_client_versions = {}
