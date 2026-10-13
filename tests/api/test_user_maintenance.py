"""
S8 (decision 8.144 h): the unverified-account cleanup finds the accounts whose
verification expiry is stored as a date or as an ISO text, uses the configured
database name, and logs counts and ids --- no user name, no e-mail address.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import usermaintenance

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=9)
RECENT = NOW - timedelta(days=2)


def _user(uid, *, verified=False, expires=None, name=None):
    return {
        '_id': uid, 'username': name or f'name-{uid}',
        'email': f'{name or uid}@mail-{uid}.example.org',
        'full_name': f'Full {uid}', 'hashed_password': 'x', 'role': 'user',
        'disabled': False, 'email_verified': verified,
        'verification_token_expires': expires,
    }


@pytest.fixture
def maintenance(mongod, db, db_name, monkeypatch):
    monkeypatch.setattr(usermaintenance, 'get_db_connectionstring',
                        lambda: f'{mongod.uri}/{db_name}')
    monkeypatch.setattr(usermaintenance, 'get_database_name', lambda: db_name)
    return lambda dry_run=False: asyncio.run(
        usermaintenance.cleanup_unverified_users(dry_run=dry_run))


def test_old_unverified_accounts_go_whatever_the_type_of_their_expiry(
        db, maintenance):
    db['users'].insert_many([
        _user('a-date', expires=OLD),
        _user('b-text-z', expires=OLD.strftime('%Y-%m-%dT%H:%M:%SZ')),
        _user('c-text-offset', expires=OLD.isoformat()),
        _user('d-recent-date', expires=RECENT),
        _user('e-recent-text', expires=RECENT.isoformat()),
        _user('f-verified-old', verified=True, expires=OLD),
        _user('g-no-expiry', expires=None),
    ])
    assert maintenance(dry_run=True) == 3
    assert db['users'].count_documents({}) == 7        # a dry run deletes none
    assert maintenance() == 3
    left = sorted(u['_id'] for u in db['users'].find({}))
    assert left == ['d-recent-date', 'e-recent-text', 'f-verified-old',
                    'g-no-expiry']


def test_the_log_holds_no_user_name_and_no_address(db, maintenance, capsys):
    db['users'].insert_many([
        _user('old-1', expires=OLD, name='secret-person-one'),
        _user('old-2', expires=OLD.isoformat(), name='secret-person-two'),
    ])
    maintenance()
    out = capsys.readouterr().out
    assert 'old-1' in out and 'old-2' in out           # ids are logged
    assert 'Deleted 2 user(s)' in out
    for private in ('secret-person', '@mail-', 'Full old', 'example.org'):
        assert private not in out, private


def test_a_failure_logs_the_kind_of_error_and_not_its_text(
        monkeypatch, capsys):
    monkeypatch.setattr(usermaintenance, 'get_db_connectionstring',
                        lambda: 'mongodb://user:password-text@127.0.0.1:1/x')
    with pytest.raises(Exception):
        asyncio.run(usermaintenance.cleanup_unverified_users(dry_run=True))
    out = capsys.readouterr().out
    assert 'Error during cleanup:' in out
    assert 'password-text' not in out and '127.0.0.1' not in out


def test_the_configured_database_is_used(mongod, db, monkeypatch):
    """Not a hard-coded ``csc``: a server whose database has another name."""
    from pymongo import MongoClient
    other = 'csc_maintenance_other'
    monkeypatch.setattr(usermaintenance, 'get_db_connectionstring',
                        lambda: f'{mongod.uri}/{other}')
    monkeypatch.setattr(usermaintenance, 'get_database_name', lambda: other)
    client = MongoClient(mongod.uri)
    try:
        client[other]['users'].insert_one(_user('x-old', expires=OLD))
        assert asyncio.run(usermaintenance.cleanup_unverified_users()) == 1
        assert client[other]['users'].count_documents({}) == 0
    finally:
        client.drop_database(other)
        client.close()
