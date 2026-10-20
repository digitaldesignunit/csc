"""
Access tokens (decision 8.167): the form and the hash, create / list / revoke /
renew, the limit of 10, who may hold one (CSC_PAT_ROLES), the check that
serves the MCP layer (valid, revoked, expired, wrong scope, a lost role, an
unverified or deleted owner, JWTs and csc_ tokens kept apart), last used at
most once a minute, the read-only flag, 120 requests a minute per token, and
the admin list.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import timedelta

import pytest

from apps.catalog import access_tokens as tk

LONG_AGO = '2000-01-01T00:00:00.000000Z'


# THE FORM ----------------------------------------------------------------------
def test_a_token_is_the_prefix_and_32_random_bytes_in_base64url():
    token = tk.new_token('pat')
    assert token.startswith('csc_pat_')
    body = token[len('csc_pat_'):]
    assert len(body) == 43 and re.fullmatch(r'[A-Za-z0-9_-]{43}', body)
    assert len(base64.urlsafe_b64decode(body + '=')) == 32
    assert tk.new_token('device').startswith('csc_dev_')
    assert len({tk.new_token('pat') for _ in range(200)}) == 200


def test_only_the_sha256_is_kept_and_the_short_id_is_8_characters():
    token = tk.new_token('pat')
    assert tk.token_hash(token) == hashlib.sha256(token.encode()).hexdigest()
    assert tk.short_id_of(token) == token[8:16] and len(tk.short_id_of(token)) == 8
    device = tk.new_token('device')
    assert tk.short_id_of(device) == device[8:16]
    assert tk.prefix_of('eyJhbGciOi') is None


def test_the_timestamps_have_one_width_so_that_strings_compare_as_times():
    from datetime import datetime, timezone
    whole = tk.stamp(datetime(2026, 1, 1, tzinfo=timezone.utc))
    part = tk.stamp(datetime(2026, 1, 1, 0, 0, 0, 5, tzinfo=timezone.utc))
    assert len(whole) == len(part) and whole < part


# HELPERS -----------------------------------------------------------------------
@pytest.fixture
def admin(make_user, login):
    user = make_user('adminuser', role='admin')
    token = login('adminuser').json()['access_token']
    return {**user, 'headers': {'Authorization': f'Bearer {token}'}}


@pytest.fixture
def member(make_user, login):
    user = make_user('memberuser', role='user')
    token = login('memberuser').json()['access_token']
    return {**user, 'headers': {'Authorization': f'Bearer {token}'}}


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def create(api, who, name='mcp', **payload):
    return api.post('/auth/access-tokens', json={'name': name, **payload},
                    headers=who['headers'])


def made(api, who, name='mcp', **payload):
    response = create(api, who, name, **payload)
    assert response.status_code == 201, response.text
    return response.json()


def check(api, token):
    return api.get('/auth/token-check', headers=bearer(token))


# CREATE ------------------------------------------------------------------------
def test_create_returns_the_plain_token_once_and_stores_only_its_hash(api, db, admin):
    row = made(api, admin, 'cursor')
    token = row['token']
    assert token.startswith('csc_pat_') and row['short_id'] == token[8:16]
    assert row['name'] == 'cursor' and row['scopes'] == ['read:catalog']
    assert row['kind'] == 'pat' and row['status'] == 'active'
    stored = db['access_tokens'].find_one({'_id': row['id']})
    assert stored['token_sha256'] == tk.token_hash(token)
    assert token not in repr(stored)
    assert stored['owner_user_id'] == admin['id'] and stored['revoked'] is None
    assert stored['last_used'] is None
    listed = api.get('/auth/access-tokens', headers=admin['headers']).json()
    assert [r['id'] for r in listed] == [row['id']]
    assert 'token' not in listed[0] and token not in repr(listed)
    assert 'token_sha256' not in listed[0]


def test_the_lifetime_is_30_90_or_365_days_and_90_by_default(api, admin):
    for days, payload in ((90, {}), (30, {'days': 30}), (90, {'days': 90}), (365, {'days': 365})):
        row = made(api, admin, f'd{days}', **payload)
        span = tk.parse_stamp(row['expires']) - tk.parse_stamp(row['created'])
        assert span == timedelta(days=days)
        assert tk.lifetime_days({'created': row['created'], 'expires': row['expires']}) == days
    # 4 created so far: the limit is 10
    for days in (0, 1, 31, 366, -5):
        assert create(api, admin, days=days).status_code == 422


@pytest.mark.parametrize('name', ['', '   ', 'x' * 81])
def test_a_name_is_required_and_short(api, admin, name):
    assert create(api, admin, name).status_code in (400, 422)


def test_creating_needs_a_signed_in_account(api):
    assert api.post('/auth/access-tokens', json={'name': 'x'}).status_code == 401


# THE LIMIT OF 10 -----------------------------------------------------------------
def test_at_most_ten_active_tokens_per_user(api, db, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    rows = [made(api, admin, f't{i}') for i in range(10)]
    eleventh = create(api, admin, 'eleventh')
    assert eleventh.status_code == 409
    assert 'revoke one first' in eleventh.json()['detail']
    assert db['access_tokens'].count_documents({'owner_user_id': admin['id']}) == 10
    assert create(api, member, 'other-user').status_code == 201      # per user
    # a revoked token frees a place, an expired one does too
    assert api.delete(f'/auth/access-tokens/{rows[0]["id"]}', headers=admin['headers']).status_code == 200
    db['access_tokens'].update_one({'_id': rows[1]['id']}, {'$set': {'expires': LONG_AGO}})
    assert create(api, admin, 'again').status_code == 201
    assert create(api, admin, 'and again').status_code == 201
    assert create(api, admin, 'no more').status_code == 409


# WHO MAY HOLD ONE ------------------------------------------------------------------
def test_by_default_only_an_admin_may_create_a_personal_access_token(api, admin, member):
    assert create(api, admin).status_code == 201
    refused = create(api, member)
    assert refused.status_code == 403 and 'not available for your role' in refused.json()['detail']


def test_the_setting_opens_it_to_members_or_closes_it_to_admins(api, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    assert create(api, member).status_code == 201
    assert create(api, admin).status_code == 201
    env(CSC_PAT_ROLES='user')
    assert create(api, admin).status_code == 403
    assert create(api, member).status_code == 201


def test_a_member_keeps_seeing_and_revoking_the_tokens_they_have(api, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    row = made(api, member, 'mine')
    env(CSC_PAT_ROLES='admin')                     # the role is closed again
    listed = api.get('/auth/access-tokens', headers=member['headers']).json()
    assert [r['id'] for r in listed] == [row['id']]
    assert api.delete(f'/auth/access-tokens/{row["id"]}', headers=member['headers']).status_code == 200


# LIST AND REVOKE ---------------------------------------------------------------------
def test_everyone_sees_only_their_own_tokens(api, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    mine = made(api, admin, 'a')
    theirs = made(api, member, 'b')
    assert [r['id'] for r in api.get('/auth/access-tokens', headers=admin['headers']).json()] == [mine['id']]
    assert [r['id'] for r in api.get('/auth/access-tokens', headers=member['headers']).json()] == [theirs['id']]
    # nobody revokes or renews another's token, and the answer is the same as for a missing one
    other = api.delete(f'/auth/access-tokens/{theirs["id"]}', headers=admin['headers'])
    missing = api.delete('/auth/access-tokens/nothing', headers=admin['headers'])
    assert other.status_code == missing.status_code == 404 and other.json() == missing.json()
    assert api.post(f'/auth/access-tokens/{theirs["id"]}/renew', headers=admin['headers']).status_code == 404
    assert check(api, theirs['token']).status_code == 200


def test_revoke_stops_the_token_at_once_and_hides_it_from_the_list(api, db, admin):
    row = made(api, admin)
    assert check(api, row['token']).status_code == 200
    revoked = api.delete(f'/auth/access-tokens/{row["id"]}', headers=admin['headers'])
    assert revoked.status_code == 200 and revoked.json()['status'] == 'revoked'
    assert check(api, row['token']).status_code == 401
    assert api.get('/auth/access-tokens', headers=admin['headers']).json() == []
    assert db['access_tokens'].find_one({'_id': row['id']})['revoked']       # kept for the admin list
    assert api.delete(f'/auth/access-tokens/{row["id"]}', headers=admin['headers']).status_code == 200


def test_the_list_marks_what_is_due_for_renewal(api, db, admin):
    made(api, admin, 'fresh')
    near = made(api, admin, 'near')
    old = made(api, admin, 'old')
    db['access_tokens'].update_one({'_id': near['id']}, {'$set': {
        'expires': tk.stamp(tk.now() + timedelta(days=13))}})
    db['access_tokens'].update_one({'_id': old['id']}, {'$set': {'expires': LONG_AGO}})
    rows = {r['name']: r for r in api.get('/auth/access-tokens', headers=admin['headers']).json()}
    assert (rows['fresh']['status'], rows['fresh']['renew_due']) == ('active', False)
    assert (rows['near']['status'], rows['near']['renew_due']) == ('active', True)
    assert (rows['old']['status'], rows['old']['renew_due']) == ('expired', False)


# RENEW -----------------------------------------------------------------------------------
def test_renew_makes_a_new_token_with_the_same_name_and_revokes_the_old(api, db, admin):
    old = made(api, admin, 'cursor', days=365)
    new = api.post(f'/auth/access-tokens/{old["id"]}/renew', headers=admin['headers'])
    assert new.status_code == 201, new.text
    new = new.json()
    assert new['token'] != old['token'] and new['id'] != old['id']
    assert (new['name'], new['scopes'], new['kind']) == ('cursor', old['scopes'], 'pat')
    assert tk.parse_stamp(new['expires']) - tk.parse_stamp(new['created']) == \
        tk.parse_stamp(old['expires']) - tk.parse_stamp(old['created'])
    assert check(api, old['token']).status_code == 401
    assert check(api, new['token']).status_code == 200
    assert api.post(f'/auth/access-tokens/{old["id"]}/renew', headers=admin['headers']).status_code == 409
    renewed = api.post(f'/auth/access-tokens/{new["id"]}/renew', json={'days': 30}, headers=admin['headers']).json()
    assert tk.parse_stamp(renewed['expires']) - tk.parse_stamp(renewed['created']) == timedelta(days=30)


def test_renew_works_at_ten_tokens_and_for_an_expired_one(api, db, admin):
    rows = [made(api, admin, f't{i}') for i in range(10)]
    db['access_tokens'].update_one({'_id': rows[0]['id']}, {'$set': {'expires': LONG_AGO}})
    assert api.post(f'/auth/access-tokens/{rows[0]["id"]}/renew', headers=admin['headers']).status_code == 201
    assert api.post(f'/auth/access-tokens/{rows[1]["id"]}/renew', headers=admin['headers']).status_code == 201
    listed = api.get('/auth/access-tokens', headers=admin['headers']).json()
    assert len([r for r in listed if r['status'] == 'active']) == 10


def test_renew_needs_the_role_still(api, admin, env):
    row = made(api, admin)
    env(CSC_PAT_ROLES='user')
    assert api.post(f'/auth/access-tokens/{row["id"]}/renew', headers=admin['headers']).status_code == 403


# THE CHECK (what the MCP layer builds on) ------------------------------------------------------
def test_a_valid_token_answers_owner_scope_and_expiry(api, admin):
    row = made(api, admin)
    answer = check(api, row['token'])
    assert answer.status_code == 200, answer.text
    assert answer.json() == {'owner': 'adminuser', 'scope': 'read:catalog', 'expires': row['expires']}


def test_every_failure_is_the_same_401(api, db, admin, member, make_user):
    row = made(api, admin)
    token = row['token']
    answers = []

    def refused(headers):
        r = api.get('/auth/token-check', headers=headers)
        assert r.status_code == 401, r.text
        answers.append((r.json(), r.headers.get('www-authenticate')))

    refused({})                                                       # no header
    refused({'Authorization': 'Basic abc'})
    refused(bearer('csc_pat_' + 'A' * 43))                            # unknown
    refused(bearer('not-a-token'))
    jwt = admin['headers']['Authorization'].split(' ', 1)[1]
    refused(bearer(jwt))                                              # a JWT
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {'scopes': ['gh:client']}})
    refused(bearer(token))                                            # wrong scope
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {'scopes': ['read:catalog']}})
    assert check(api, token).status_code == 200
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {'expires': LONG_AGO}})
    refused(bearer(token))                                            # expired
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {'expires': tk.expires_at(30)}})
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'user'}})
    refused(bearer(token))                                            # owner demoted
    db['users'].update_one({'_id': admin['id']}, {'$set': {'role': 'admin'}})
    assert check(api, token).status_code == 200
    db['users'].update_one({'_id': admin['id']}, {'$set': {'email_verified': False}})
    refused(bearer(token))                                            # owner unverified
    db['users'].update_one({'_id': admin['id']}, {'$set': {'email_verified': True, 'disabled': True}})
    refused(bearer(token))                                            # owner disabled
    db['users'].update_one({'_id': admin['id']}, {'$set': {'disabled': False}})
    assert check(api, token).status_code == 200
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=admin['headers'])
    refused(bearer(token))                                            # revoked
    db['users'].delete_one({'_id': admin['id']})
    other = made_direct(db, admin['id'])
    refused(bearer(other))                                            # owner deleted
    assert all(a == answers[0] for a in answers), answers


def made_direct(db, owner_id, kind='pat', scopes=('read:catalog',)):
    """A token inserted straight into the database."""
    token = tk.new_token(kind)
    db['access_tokens'].insert_one({
        '_id': 'direct' + tk.short_id_of(token), 'kind': kind, 'owner_user_id': owner_id,
        'scopes': list(scopes), 'name': 'direct', 'token_sha256': tk.token_hash(token),
        'short_id': tk.short_id_of(token), 'created': tk.stamp(tk.now()),
        'expires': tk.expires_at(30), 'last_used': None, 'revoked': None})
    return token


def test_a_demoted_owner_stops_the_token_at_once_and_a_restored_role_starts_it(api, db, admin, env):
    row = made(api, admin)
    env(CSC_PAT_ROLES='user')                        # the admin role leaves the setting
    assert check(api, row['token']).status_code == 401
    env(CSC_PAT_ROLES='admin,user')
    assert check(api, row['token']).status_code == 200


def test_a_device_token_does_not_pass_the_catalog_scope(api, db, admin):
    device = made_direct(db, admin['id'], 'device', ('gh:client',))
    assert check(api, device).status_code == 401
    mismatched = made_direct(db, admin['id'], 'pat', ('gh:client',))
    assert check(api, mismatched).status_code == 401


def test_the_jwt_dependency_refuses_csc_tokens_and_the_token_check_refuses_jwts(api, admin):
    row = made(api, admin)
    assert api.get('/users/me', headers=bearer(row['token'])).status_code == 401
    assert api.get('/users/me', headers=admin['headers']).status_code == 200
    assert api.get('/auth/token-check', headers=admin['headers']).status_code == 401
    # a token in the place of a JWT is the anonymous caller to every other route
    anonymous = api.get('/identities').status_code
    assert api.get('/identities', headers=bearer(row['token'])).status_code == anonymous


def test_the_token_is_not_taken_from_a_query_or_a_cookie(api, admin):
    row = made(api, admin)
    assert api.get('/auth/token-check', params={'token': row['token']}).status_code == 401
    assert api.get('/auth/token-check', params={'access_token': row['token']}).status_code == 401


# LAST USED -------------------------------------------------------------------------------------------
def test_last_used_is_written_at_most_once_a_minute(api, db, admin):
    row = made(api, admin)
    stored = lambda: db['access_tokens'].find_one({'_id': row['id']})['last_used']
    assert stored() is None
    check(api, row['token'])
    first = stored()
    assert first and first.endswith('Z')
    check(api, row['token'])
    check(api, row['token'])
    assert stored() == first                                           # not written again within the minute
    db['access_tokens'].update_one({'_id': row['id']}, {'$set': {
        'last_used': tk.stamp(tk.now() - timedelta(seconds=61))}})
    check(api, row['token'])
    assert stored() > first and stored() >= tk.stamp(tk.now() - timedelta(seconds=5))


def test_last_used_is_not_written_while_the_read_only_flag_is_set(api, db, admin, read_only_flag):
    row = made(api, admin)
    read_only_flag.on()
    assert check(api, row['token']).status_code == 200                 # reads keep working
    assert db['access_tokens'].find_one({'_id': row['id']})['last_used'] is None
    read_only_flag.off()
    check(api, row['token'])
    assert db['access_tokens'].find_one({'_id': row['id']})['last_used']


def test_create_revoke_and_renew_are_refused_while_the_flag_is_set(api, db, admin, read_only_flag):
    row = made(api, admin)
    read_only_flag.on()
    for response in (
        create(api, admin, 'x'),
        api.delete(f'/auth/access-tokens/{row["id"]}', headers=admin['headers']),
        api.post(f'/auth/access-tokens/{row["id"]}/renew', headers=admin['headers']),
        api.delete(f'/admin/access-tokens/{row["id"]}', headers=admin['headers']),
    ):
        assert response.status_code == 503 and response.json() == {'detail': 'read-only: maintenance'}
    assert api.get('/auth/access-tokens', headers=admin['headers']).status_code == 200
    assert db['access_tokens'].count_documents({}) == 1
    assert db['access_tokens'].find_one({'_id': row['id']})['revoked'] is None


# RATE LIMIT ----------------------------------------------------------------------------------------------
def test_the_limit_is_120_a_minute_per_token(api, admin, monkeypatch):
    assert tk.REQUESTS_PER_MINUTE == 120
    monkeypatch.setattr(tk, 'REQUESTS_PER_MINUTE', 5)
    one, two = made(api, admin, 'one'), made(api, admin, 'two')
    assert [check(api, one['token']).status_code for _ in range(5)] == [200] * 5
    limited = check(api, one['token'])
    assert limited.status_code == 429 and int(limited.headers['Retry-After']) >= 1
    assert check(api, two['token']).status_code == 200                 # counted per token
    assert api.get('/users/me', headers=admin['headers']).status_code == 200


def test_a_refused_token_is_not_counted(api, admin, monkeypatch):
    monkeypatch.setattr(tk, 'REQUESTS_PER_MINUTE', 2)
    row = made(api, admin)
    for _ in range(5):
        assert check(api, 'csc_pat_' + 'B' * 43).status_code == 401
    assert check(api, row['token']).status_code == 200


# THE CLIENT HEADER (8.167 h) ----------------------------------------------------------------------------------------------
def test_with_the_production_table_a_token_check_needs_no_client_header(api, admin, app):
    row = made(api, admin)
    app.state.min_client_versions = {'web': (0, 6, 0, 0), 'gh-userobjects': (0, 6, 0, 0)}
    try:
        no_header = {'X-CSC-Client': ''}
        assert check_with(api, row['token'], no_header).status_code == 200
        assert check_with(api, row['token'], {'X-CSC-Client': 'garbage'}).status_code == 200
        # a JWT route still needs a known client
        refused = api.get('/users/me', headers={**admin['headers'], **no_header})
        assert refused.status_code == 426
        assert api.get('/users/me', headers={**admin['headers'], 'X-CSC-Client': 'web/0.6.2.1'}).status_code == 200
        # the exemption does not make a bad token good
        assert check_with(api, 'csc_pat_' + 'C' * 43, no_header).status_code == 401
    finally:
        app.state.min_client_versions = {}


def check_with(api, token, headers):
    return api.get('/auth/token-check', headers={**bearer(token), **headers})


# THE LOG ---------------------------------------------------------------------------------------------------
def test_one_line_per_use_with_the_short_id_and_no_personal_data(api, admin, caplog):
    row = made(api, admin)
    with caplog.at_level(logging.INFO):
        check(api, row['token'])
    used = [r.getMessage() for r in caplog.records if 'access token used' in r.getMessage()]
    assert used == [f'access token used: {row["short_id"]} /auth/token-check']
    text = caplog.text
    assert row['token'] not in text and 'adminuser' not in text and 'tu-darmstadt.de' not in text


# THE ADMIN LIST -----------------------------------------------------------------------------------------------
def test_an_admin_sees_every_token_with_the_owner_name_and_no_secret(api, db, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    a = made(api, admin, 'a-token')
    b = made(api, member, 'b-token')
    api.delete(f'/auth/access-tokens/{b["id"]}', headers=member['headers'])
    listed = api.get('/admin/access-tokens', headers=admin['headers'])
    assert listed.status_code == 200, listed.text
    rows = {r['id']: r for r in listed.json()}
    assert set(rows) == {a['id'], b['id']}
    assert rows[a['id']]['owner_username'] == 'adminuser' and rows[b['id']]['owner_username'] == 'memberuser'
    assert rows[b['id']]['status'] == 'revoked'
    text = listed.text
    for secret in (a['token'], b['token'], tk.token_hash(a['token']), 'token_sha256', '@tu-darmstadt.de'):
        assert secret not in text, secret
    assert 'email' not in rows[a['id']]


def test_only_an_admin_uses_the_admin_routes(api, admin, member):
    row = made(api, admin)
    assert api.get('/admin/access-tokens', headers=member['headers']).status_code == 403
    assert api.get('/admin/access-tokens').status_code == 401
    assert api.delete(f'/admin/access-tokens/{row["id"]}', headers=member['headers']).status_code == 403


def test_an_admin_revokes_any_token(api, db, admin, member, env):
    env(CSC_PAT_ROLES='admin,user')
    row = made(api, member, 'theirs')
    assert check(api, row['token']).status_code == 200
    done = api.delete(f'/admin/access-tokens/{row["id"]}', headers=admin['headers'])
    assert done.status_code == 200 and done.json()['status'] == 'revoked'
    assert check(api, row['token']).status_code == 401
    assert api.delete('/admin/access-tokens/nothing', headers=admin['headers']).status_code == 404
    assert api.get('/auth/access-tokens', headers=member['headers']).json() == []


# SETTINGS ----------------------------------------------------------------------------------------------------------
def test_the_setting_is_a_list_of_known_roles(env):
    from settings import SettingsError, get_settings
    env(CSC_PAT_ROLES=None)
    assert get_settings().pat_roles == ('admin',)
    env(CSC_PAT_ROLES=' Admin , user ')
    assert get_settings().pat_roles == ('admin', 'user')
    for bad in ('root', 'admin,reviewer', ','):
        env(CSC_PAT_ROLES=bad)
        with pytest.raises(SettingsError, match='CSC_PAT_ROLES'):
            get_settings()
    env(CSC_PAT_ROLES=None)


# WHAT THE SETTINGS PAGE ASKS -------------------------------------------------------------------------------------------
def test_the_options_tell_the_page_whether_to_draw_the_create_form(api, admin, member, env):
    options = api.get('/auth/access-tokens/options', headers=admin['headers']).json()
    assert options == {'can_create': True, 'lifetimes': [30, 90, 365], 'default_days': 90, 'max_active': 10}
    assert api.get('/auth/access-tokens/options', headers=member['headers']).json()['can_create'] is False
    env(CSC_PAT_ROLES='admin,user')
    assert api.get('/auth/access-tokens/options', headers=member['headers']).json()['can_create'] is True
    assert api.get('/auth/access-tokens/options').status_code == 401


def test_the_answers_that_carry_a_token_are_not_cached(api, admin):
    created = create(api, admin)
    assert created.headers['cache-control'] == 'no-store'
    renewed = api.post(f'/auth/access-tokens/{created.json()["id"]}/renew', headers=admin['headers'])
    assert renewed.headers['cache-control'] == 'no-store'
