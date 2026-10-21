"""A password change and a password reset end every access token of the account,
all kinds (decisions 8.124, 8.168 f): personal access tokens, Claude connections
and Grasshopper sign-ins, each with its refresh token. Afterwards a new token or
a new consent is needed."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from apps.catalog import access_tokens as tk
from apps.catalog.api.auth import token_sha256
from oauth_helpers import (
    GH_CLIENT,
    bearer,
    connect,
    gh_sign_in,
    mcp_post,
    refresh,
    reset_address_counters,
)
from support import DEFAULT_PASSWORD

NEW_PASSWORD = 'a brand new password'


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def owner(make_user, login):
    user = make_user('ownerone', role='admin')
    return {**user, 'headers': bearer(login('ownerone').json()['access_token'])}


@pytest.fixture
def three(api, owner):
    """One token of each kind for the owner."""
    pat = api.post('/auth/access-tokens', json={'name': 'script'}, headers=owner['headers']).json()['token']
    claude = connect(api, owner['headers'])
    gh = gh_sign_in(api, owner['headers'])
    return {'pat': pat, 'claude': claude, 'gh': gh}


def change(api, owner, current=DEFAULT_PASSWORD, new=NEW_PASSWORD):
    return api.post('/auth/change-password', json={'current_password': current, 'new_password': new},
                    headers=owner['headers'])


def reset(api, db, owner, new=NEW_PASSWORD):
    db['users'].update_one({'_id': owner['id']}, {'$set': {
        'password_reset_sha256': token_sha256('RESET-TOKEN-OF-ONE-0001'),
        'password_reset_expires': datetime.now(timezone.utc) + timedelta(hours=1)}})
    return api.post('/auth/password-reset/confirm', json={'token': 'RESET-TOKEN-OF-ONE-0001', 'new_password': new})


def all_work(api, three):
    assert api.get('/auth/token-check', headers=bearer(three['pat'])).status_code == 200
    assert mcp_post(api, three['claude']['access'], 'tools/list').status_code == 200
    assert api.get('/users/me', headers=bearer(three['gh']['access'])).status_code == 200


def all_dead(api, three):
    assert api.get('/auth/token-check', headers=bearer(three['pat'])).status_code == 401
    assert mcp_post(api, three['claude']['access'], 'tools/list').status_code == 401
    claude = refresh(api, three['claude']['client_id'], three['claude']['refresh'])
    assert claude.status_code == 400 and claude.json()['error'] == 'invalid_grant'
    gh = refresh(api, GH_CLIENT, three['gh']['refresh'])
    assert gh.status_code == 400 and gh.json()['error'] == 'invalid_grant'


@pytest.mark.parametrize('route', ['change', 'reset'])
def test_a_password_change_or_reset_ends_every_token_of_every_kind(api, db, owner, three, route):
    all_work(api, three)
    done = change(api, owner) if route == 'change' else reset(api, db, owner)
    assert done.status_code == 200, done.text
    all_dead(api, three)
    rows = list(db['access_tokens'].find({'owner_user_id': owner['id']}))
    assert sorted(r['kind'] for r in rows) == ['device', 'oauth', 'pat']
    assert all(r['revoked'] for r in rows)


@pytest.mark.parametrize('route', ['change', 'reset'])
def test_the_lists_show_them_revoked_and_new_tokens_work_afterwards(api, db, owner, three, login, route):
    done = change(api, owner) if route == 'change' else reset(api, db, owner)
    assert done.status_code == 200
    headers = bearer(login('ownerone', NEW_PASSWORD).json()['access_token'])
    assert api.get('/auth/access-tokens', headers=headers).json() == []          # revoked ones are not listed
    listed = api.get('/admin/access-tokens', headers=headers).json()
    assert sorted((r['kind'], r['status']) for r in listed) == [
        ('device', 'revoked'), ('oauth', 'revoked'), ('pat', 'revoked')]
    # the account starts again: a new token, a new consent, a new sign-in
    fresh = api.post('/auth/access-tokens', json={'name': 'again'}, headers=headers).json()['token']
    assert api.get('/auth/token-check', headers=bearer(fresh)).status_code == 200
    assert mcp_post(api, connect(api, headers)['access'], 'tools/list').status_code == 200
    assert api.get('/users/me', headers=bearer(gh_sign_in(api, headers)['access'])).status_code == 200


def test_the_old_jwt_of_the_grasshopper_sign_in_is_out_too(api, owner, three):
    """The JWT issued before the change is refused (8.124 a), and the refresh
    token can no longer make a newer one. (A JWT of the same second as the
    change is still good, by design: so wait that second out.)"""
    time.sleep(1.2)
    assert change(api, owner).status_code == 200
    assert api.get('/users/me', headers=bearer(three['gh']['access'])).status_code == 401
    assert refresh(api, GH_CLIENT, three['gh']['refresh']).json()['error'] == 'invalid_grant'


def test_only_the_account_that_changed_its_password_loses_its_tokens(api, db, owner, three, make_user, login):
    other = make_user('ownertwo', role='admin')
    other_headers = bearer(login('ownertwo').json()['access_token'])
    theirs = api.post('/auth/access-tokens', json={'name': 'theirs'}, headers=other_headers).json()['token']
    their_claude = connect(api, other_headers)
    assert change(api, owner).status_code == 200
    assert api.get('/auth/token-check', headers=bearer(theirs)).status_code == 200
    assert mcp_post(api, their_claude['access'], 'tools/list').status_code == 200
    assert db['access_tokens'].count_documents({'owner_user_id': other['id'], 'revoked': None}) == 2


def test_a_token_that_was_revoked_before_keeps_its_own_time(api, db, owner, three):
    row = db['access_tokens'].find_one({'kind': 'pat', 'owner_user_id': owner['id']})
    earlier = tk.stamp(tk.now() - timedelta(days=1))
    db['access_tokens'].update_one({'_id': row['_id']}, {'$set': {'revoked': earlier}})
    assert change(api, owner).status_code == 200
    assert db['access_tokens'].find_one({'_id': row['_id']})['revoked'] == earlier
    assert all(r['revoked'] for r in db['access_tokens'].find({'owner_user_id': owner['id']}))


def test_a_refused_change_or_reset_leaves_the_tokens_alone(api, db, owner, three):
    assert change(api, owner, current='not the password').status_code == 400
    assert change(api, owner, new=DEFAULT_PASSWORD).status_code == 400            # the same password
    bad = api.post('/auth/password-reset/confirm', json={'token': 'wrong-token-of-none-0001', 'new_password': NEW_PASSWORD})
    assert bad.status_code == 400
    all_work(api, three)
    assert db['access_tokens'].count_documents({'owner_user_id': owner['id'], 'revoked': None}) == 3


def test_a_change_under_the_maintenance_flag_changes_nothing(api, owner, three, read_only_flag):
    read_only_flag.on()
    assert change(api, owner).status_code == 503
    read_only_flag.off()
    all_work(api, three)
