"""
Token clean-up (0.6.3.1): the access tokens and OAuth rows of a deleted account
go with it (the one deletion path, the unverified-account cleanup); a revoked
row, or one expired past its refresh limit, gets a ``purge_at`` date 90 days
after it died and a TTL index deletes it, with no job; rows of an earlier build
get the date once at start.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import usermaintenance
from apps.catalog import access_tokens as tk
from apps.catalog.token_cleanup import backfill_purge_dates, remove_tokens_of
from oauth_helpers import bearer, connect, gh_sign_in, refresh, reset_address_counters
from support import DEFAULT_PASSWORD

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=9)


@pytest.fixture(autouse=True)
def fresh_counters():
    reset_address_counters()
    yield
    reset_address_counters()


@pytest.fixture
def owner(make_user, login):
    user = make_user('cleanowner', role='admin')
    return {**user, 'headers': bearer(login('cleanowner').json()['access_token'])}


def aware(value):
    """A date read back from Mongo is naive UTC."""
    return value.replace(tzinfo=timezone.utc)


def same(a, b):
    """Mongo keeps milliseconds."""
    return abs((a - b).total_seconds()) < 1


# THE DATE A ROW MAY GO ---------------------------------------------------------
def stamp_days(days):
    return tk.stamp(NOW + timedelta(days=days))


def test_a_row_may_go_90_days_after_it_expires():
    row = {'expires': stamp_days(30)}
    assert tk.purge_at(row) == tk.parse_stamp(row['expires']) + timedelta(days=90)


def test_a_connection_dies_with_its_refresh_limit_when_that_comes_first():
    row = {'expires': stamp_days(90), 'refresh_expires': stamp_days(30)}
    assert tk.purge_at(row) == tk.parse_stamp(row['refresh_expires']) + timedelta(days=90)


def test_a_revoked_row_goes_90_days_after_the_revoke_if_that_is_earlier():
    row = {'expires': stamp_days(300), 'revoked': stamp_days(-1)}
    assert tk.purge_at(row) == tk.parse_stamp(row['revoked']) + timedelta(days=90)


def test_the_purge_date_is_never_before_the_row_died():
    row = {'expires': stamp_days(-100), 'refresh_expires': stamp_days(-120)}
    assert tk.purge_at(row) == tk.parse_stamp(row['refresh_expires']) + timedelta(days=90)


# WRITTEN WHERE A ROW IS MADE AND REVOKED ---------------------------------------
def test_a_personal_token_gets_its_purge_date_when_made(api, db, owner):
    row = api.post('/auth/access-tokens', json={'name': 'a', 'days': 30},
                   headers=owner['headers']).json()
    stored = db['access_tokens'].find_one({'_id': row['id']})
    assert same(aware(stored['purge_at']), tk.parse_stamp(row['expires']) + timedelta(days=90))


def test_revoking_a_personal_token_pulls_the_purge_date_in(api, db, owner):
    row = api.post('/auth/access-tokens', json={'name': 'a', 'days': 365},
                   headers=owner['headers']).json()
    before = aware(db['access_tokens'].find_one({'_id': row['id']})['purge_at'])
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=owner['headers'])
    after = aware(db['access_tokens'].find_one({'_id': row['id']})['purge_at'])
    assert after < before
    assert abs((after - (datetime.now(timezone.utc) + timedelta(days=90))).total_seconds()) < 120


def test_a_token_revoked_late_keeps_its_earlier_date(api, db, owner):
    """$min: a token that dies in 30 days is revoked in 29: still 120 days."""
    row = api.post('/auth/access-tokens', json={'name': 'a', 'days': 30},
                   headers=owner['headers']).json()
    api.delete(f'/auth/access-tokens/{row["id"]}', headers=owner['headers'])
    stored = db['access_tokens'].find_one({'_id': row['id']})
    # revoked now: now + 90 days is later than expires + 90 - 30 days
    assert aware(stored['purge_at']) <= tk.parse_stamp(row['expires']) + timedelta(days=90)


def test_a_connection_has_its_date_and_a_refresh_moves_it(api, db, owner):
    claude = connect(api, owner['headers'])
    row = db['access_tokens'].find_one({'kind': 'oauth'})
    assert same(aware(row['purge_at']), tk.parse_stamp(row['refresh_expires']) + timedelta(days=90))
    db['access_tokens'].update_one({'_id': row['_id']}, {'$set': {
        'refresh_expires': stamp_days(2)}})
    assert refresh(api, claude['client_id'], claude['refresh']).status_code == 200
    after = db['access_tokens'].find_one({'_id': row['_id']})
    assert same(aware(after['purge_at']), tk.parse_stamp(after['refresh_expires']) + timedelta(days=90))
    assert aware(after['purge_at']) > aware(row['purge_at']) - timedelta(days=30)


def test_a_grasshopper_sign_in_has_its_date_too(api, db, owner):
    gh_sign_in(api, owner['headers'])
    row = db['access_tokens'].find_one({'kind': 'device'})
    assert row['purge_at'] is not None


def test_ending_a_connection_and_a_password_change_set_the_date(api, db, owner):
    connect(api, owner['headers'])
    gh_sign_in(api, owner['headers'])
    before = {r['_id']: aware(r['purge_at']) for r in db['access_tokens'].find({})}
    done = api.post('/auth/change-password', json={
        'current_password': DEFAULT_PASSWORD, 'new_password': 'another long password'},
        headers=owner['headers'])
    assert done.status_code == 200
    for row in db['access_tokens'].find({}):
        assert row['revoked']
        assert aware(row['purge_at']) < before[row['_id']]


def test_an_admin_revoke_of_a_connection_sets_the_date(api, db, owner):
    connect(api, owner['headers'])
    row = db['access_tokens'].find_one({'kind': 'oauth'})
    before = aware(row['purge_at'])
    done = api.delete(f'/admin/access-tokens/{row["_id"]}', headers=owner['headers'])
    assert done.status_code == 200
    assert aware(db['access_tokens'].find_one({'_id': row['_id']})['purge_at']) < before


# THE TTL INDEX -----------------------------------------------------------------
def test_a_ttl_index_on_purge_at_deletes_at_the_date(db):
    found = [spec for spec in db['access_tokens'].index_information().values()
             if spec['key'] == [('purge_at', 1)]]
    assert len(found) == 1 and found[0]['expireAfterSeconds'] == 0


# ROWS OF AN EARLIER BUILD -------------------------------------------------------
def old_row(row_id, **extra):
    return {'_id': row_id, 'kind': 'pat', 'owner_user_id': 'u', 'scopes': [tk.SCOPE_CATALOG],
            'name': 'old', 'token_sha256': row_id, 'short_id': row_id[:8],
            'created': tk.stamp(NOW - timedelta(days=200)), 'expires': stamp_days(-100),
            'last_used': None, 'revoked': None, **extra}


def test_rows_without_a_date_get_one_at_start_and_a_second_run_changes_nothing(db):
    db['access_tokens'].insert_many([
        old_row('expired-row'),
        old_row('revoked-row', expires=stamp_days(200), revoked=stamp_days(-10)),
        old_row('has-date', purge_at=NOW + timedelta(days=5)),
    ])
    done = asyncio.run(_backfill(db))
    assert done == 2
    expired = db['access_tokens'].find_one({'_id': 'expired-row'})
    assert same(aware(expired['purge_at']), tk.parse_stamp(expired['expires']) + timedelta(days=90))
    revoked = db['access_tokens'].find_one({'_id': 'revoked-row'})
    assert same(aware(revoked['purge_at']), tk.parse_stamp(revoked['revoked']) + timedelta(days=90))
    untouched = db['access_tokens'].find_one({'_id': 'has-date'})
    assert abs((aware(untouched['purge_at']) - (NOW + timedelta(days=5))).total_seconds()) < 1
    assert asyncio.run(_backfill(db)) == 0


def test_nothing_is_written_at_start_while_the_read_only_flag_is_set(db, read_only_flag):
    db['access_tokens'].insert_one(old_row('expired-row'))
    read_only_flag.on()
    assert asyncio.run(_backfill(db)) == 0
    read_only_flag.off()
    assert 'purge_at' not in db['access_tokens'].find_one({'_id': 'expired-row'})


async def _backfill(db):
    from pymongo import AsyncMongoClient
    client = AsyncMongoClient(db.client.address[0] + ':' + str(db.client.address[1]))
    try:
        return await backfill_purge_dates(client[db.name]['access_tokens'])
    finally:
        await client.close()


# A DELETED ACCOUNT --------------------------------------------------------------
def _unverified(uid):
    return {'_id': uid, 'username': f'name-{uid}', 'email': f'{uid}@mail.example.org',
            'full_name': uid, 'hashed_password': 'x', 'role': 'user', 'disabled': False,
            'email_verified': False, 'verification_token_expires': OLD}


def _rows_for(db, uid, tag):
    db['access_tokens'].insert_many([
        old_row(f'{tag}-pat', owner_user_id=uid),
        old_row(f'{tag}-oauth', kind='oauth', owner_user_id=uid, expires=stamp_days(50)),
        old_row(f'{tag}-device', kind='device', owner_user_id=uid, expires=stamp_days(50)),
    ])
    db['oauth_codes'].insert_one({'_id': f'{tag}-code', 'user_id': uid})
    db['oauth_requests'].insert_one({'_id': f'{tag}-request', 'bound_user': uid})
    db['oauth_used_refresh'].insert_many([
        {'_id': f'{tag}-used-1', 'grant_id': f'{tag}-oauth', 'at': NOW},
        {'_id': f'{tag}-used-2', 'grant_id': f'{tag}-device', 'at': NOW}])


def names(db, collection):
    return sorted(doc['_id'] for doc in db[collection].find({}))


@pytest.fixture
def maintenance(mongod, db, db_name, monkeypatch):
    monkeypatch.setattr(usermaintenance, 'get_db_connectionstring',
                        lambda: f'{mongod.uri}/{db_name}')
    monkeypatch.setattr(usermaintenance, 'get_database_name', lambda: db_name)
    return lambda dry_run=False: asyncio.run(
        usermaintenance.cleanup_unverified_users(dry_run=dry_run))


def test_deleting_an_unverified_account_removes_its_tokens_and_oauth_rows(db, maintenance):
    db['users'].insert_one(_unverified('gone'))
    db['users'].insert_one({**_unverified('stays'), 'email_verified': True})
    _rows_for(db, 'gone', 'gone')
    _rows_for(db, 'stays', 'stays')
    assert maintenance() == 1
    assert names(db, 'users') == ['stays']
    assert names(db, 'access_tokens') == ['stays-device', 'stays-oauth', 'stays-pat']
    assert names(db, 'oauth_codes') == ['stays-code']
    assert names(db, 'oauth_requests') == ['stays-request']
    assert names(db, 'oauth_used_refresh') == ['stays-used-1', 'stays-used-2']


def test_a_dry_run_removes_nothing(db, maintenance):
    db['users'].insert_one(_unverified('gone'))
    _rows_for(db, 'gone', 'gone')
    assert maintenance(dry_run=True) == 1
    assert len(names(db, 'access_tokens')) == 3 and len(names(db, 'oauth_codes')) == 1


def test_a_run_with_no_account_to_delete_touches_no_token(db, maintenance):
    db['users'].insert_one({**_unverified('stays'), 'email_verified': True})
    _rows_for(db, 'stays', 'stays')
    assert maintenance() == 0
    assert len(names(db, 'access_tokens')) == 3


def test_remove_tokens_of_reports_what_it_removed_and_ignores_no_ids(db):
    _rows_for(db, 'gone', 'gone')

    async def run(ids):
        from pymongo import AsyncMongoClient
        client = AsyncMongoClient(db.client.address[0] + ':' + str(db.client.address[1]))
        try:
            return await remove_tokens_of(client[db.name], ids)
        finally:
            await client.close()

    assert asyncio.run(run([])) == {}
    assert asyncio.run(run(['gone'])) == {
        'oauth_used_refresh': 2, 'oauth_codes': 1, 'oauth_requests': 1, 'access_tokens': 3}
    assert asyncio.run(run(['gone'])) == {
        'oauth_used_refresh': 0, 'oauth_codes': 0, 'oauth_requests': 0, 'access_tokens': 0}


def test_the_account_deletion_in_the_dev_server_script_is_not_a_path_of_the_app():
    """The only code of the app that deletes accounts is usermaintenance."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / 'src' / 'backend'
    hits = []
    for path in root.rglob('*.py'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        if ("mongodb_users.delete" in text or "['users'].delete" in text
                or "users.delete_many" in text or "users.delete_one" in text):
            hits.append(path.name)
    assert hits == ['usermaintenance.py']


# THE BACKFILL FROM THE DAILY MAINTENANCE RUN (0.6.3.1) ----------------------------
def test_the_maintenance_run_gives_old_rows_their_purge_date(db, maintenance):
    db['access_tokens'].insert_many([
        old_row('expired-row'),
        old_row('revoked-row', expires=stamp_days(200), revoked=stamp_days(-10)),
        old_row('has-date', purge_at=NOW + timedelta(days=5)),
    ])
    # no account to delete: the backfill still runs
    assert maintenance() == 0
    expired = db['access_tokens'].find_one({'_id': 'expired-row'})
    assert same(aware(expired['purge_at']), tk.parse_stamp(expired['expires']) + timedelta(days=90))
    revoked = db['access_tokens'].find_one({'_id': 'revoked-row'})
    assert same(aware(revoked['purge_at']), tk.parse_stamp(revoked['revoked']) + timedelta(days=90))
    assert same(aware(db['access_tokens'].find_one({'_id': 'has-date'})['purge_at']),
                NOW + timedelta(days=5))


def test_a_dry_run_writes_no_purge_date(db, maintenance):
    db['access_tokens'].insert_one(old_row('expired-row'))
    maintenance(dry_run=True)
    assert 'purge_at' not in db['access_tokens'].find_one({'_id': 'expired-row'})


def test_under_the_read_only_flag_the_job_waits_and_the_next_run_finishes_it(
        db, maintenance, read_only_flag, mongod, db_name, monkeypatch):
    db['access_tokens'].insert_one(old_row('expired-row'))
    # the cleanup itself: the backfill alone does nothing under the flag
    read_only_flag.on()
    assert asyncio.run(usermaintenance.main()) == 0                 # the job is skipped
    assert 'purge_at' not in db['access_tokens'].find_one({'_id': 'expired-row'})
    assert maintenance() == 0                                        # called directly: the backfill skips
    assert 'purge_at' not in db['access_tokens'].find_one({'_id': 'expired-row'})
    # the flag ends: the next run does it
    read_only_flag.off()
    assert asyncio.run(usermaintenance.main()) == 0
    assert db['access_tokens'].find_one({'_id': 'expired-row'})['purge_at'] is not None


def test_deleting_accounts_and_the_backfill_work_in_one_run(db, maintenance):
    db['users'].insert_one(_unverified('gone'))
    _rows_for(db, 'gone', 'gone')
    db['access_tokens'].insert_one(old_row('left-over', owner_user_id='someone-else'))
    assert maintenance() == 1
    assert names(db, 'access_tokens') == ['left-over']
    assert db['access_tokens'].find_one({'_id': 'left-over'})['purge_at'] is not None
