"""
The read-only flag (decision 8.154): while the file exists every write is
refused with 503 before its body is read, the sign-in writes nothing, /version
and /health/db report it, and the jobs that write skip their run. The file is
looked at per request: touch and rm switch it at once.
"""

from __future__ import annotations

import logging
import os

import pytest

import limiter as lim
import read_only
import signin_limit
from support import DEFAULT_PASSWORD

WRITES = ('POST', 'PUT', 'PATCH', 'DELETE')
SAFE = ('GET', 'HEAD', 'OPTIONS')


# THE MIDDLEWARE ----------------------------------------------------------------
@pytest.mark.parametrize('method', WRITES)
def test_every_write_is_refused_while_the_flag_is_set(api, read_only_flag, method):
    read_only_flag.on()
    response = api.request(method, '/identities/x', json={'a': 1})
    assert response.status_code == 503, response.text
    assert response.json() == {'detail': 'read-only: maintenance'}
    assert int(response.headers['Retry-After']) > 0


@pytest.mark.parametrize('path, method', [
    ('/auth/register', 'POST'), ('/snapshots/s1/meshes/0/reduced', 'PUT'),
    ('/evidence/attachments', 'POST'), ('/snapshots/s1/photos/0', 'PUT'),
    ('/geometry/results/s1', 'POST'), ('/auth/password-reset', 'POST'),
    ('/ghinterface/identities', 'POST'),
])
def test_registration_uploads_and_the_gh_writes_are_included(api, read_only_flag, path, method):
    read_only_flag.on()
    assert api.request(method, path, content=b'x').status_code == 503


@pytest.mark.parametrize('method', SAFE)
def test_reads_and_preflights_are_never_refused(api, read_only_flag, method):
    read_only_flag.on()
    response = api.request(method, '/version')
    assert response.status_code != 503, method


def test_the_flag_switches_per_request_without_a_restart(api, read_only_flag):
    assert api.post('/identities/x', json={}).status_code != 503
    read_only_flag.on()
    assert api.post('/identities/x', json={}).status_code == 503
    assert api.post('/identities/x', json={}).status_code == 503
    read_only_flag.off()
    assert api.post('/identities/x', json={}).status_code != 503


def test_the_refusal_comes_before_the_body_is_read(api, read_only_flag, env):
    # a body over the cap would be a 413; the read-only answer wins, so the
    # middleware sits outside the body limit
    env(CSC_JSON_BODY_LIMIT_MB='1')
    read_only_flag.on()
    response = api.post('/identities/x', content=b'x' * (2 * 1024 * 1024),
                        headers={'Content-Type': 'application/json'})
    assert response.status_code == 503


def test_the_refusal_carries_the_cors_headers(api, read_only_flag):
    read_only_flag.on()
    response = api.post('/identities/x', json={}, headers={'Origin': 'http://localhost:3000'})
    assert response.status_code == 503
    assert response.headers.get('access-control-allow-origin') == 'http://localhost:3000'


def test_a_flag_path_that_cannot_exist_counts_as_off(env):
    env(CSC_READ_ONLY_FLAG='/no/such/folder/READ_ONLY')
    assert read_only.is_on() is False


def test_the_default_flag_is_in_the_shared_folder(env):
    from settings import get_settings
    env(CSC_READ_ONLY_FLAG=None)
    assert get_settings().csc_read_only_flag == os.path.expanduser('~/csc/shared/READ_ONLY')


# THE SIGN-IN -------------------------------------------------------------------
@pytest.fixture
def counting(monkeypatch):
    """Every write to the shared counter store, recorded."""
    calls = []
    real = lim.store().incr
    monkeypatch.setattr(lim.store(), 'incr', lambda *a, **k: calls.append(a) or real(*a, **k))
    return calls


def test_sign_in_stays_open_and_writes_nothing_while_the_flag_is_set(
        api, db, make_user, login, read_only_flag, monkeypatch):
    make_user('maint')
    for each in (lim.local_limiter, lim.shared_limiter):
        monkeypatch.setattr(each, 'enabled', True)
        each.reset()
    before = db['users'].find_one({'username': 'maint'})
    read_only_flag.on()
    try:
        assert login('maint', DEFAULT_PASSWORD).status_code == 200
        # the per-address limit of 10/minute still holds (counted in this
        # process's memory, see the MongoDB test below): the 11th is refused ...
        codes = [login('maint', 'wrong-password').status_code for _ in range(12)]
        assert codes[:9] == [401] * 9, codes
        assert set(codes[9:]) == {429}, codes
        # ... by the address limit, not by an account lock (that count is paused)
        assert signin_limit.LOCKED_DETAIL not in login('maint', 'wrong-password').text
    finally:
        for each in (lim.local_limiter, lim.shared_limiter):
            each.enabled = False
            each.reset()
    assert db['users'].find_one({'username': 'maint'}) == before, 'the account was written'


def test_no_account_failure_is_counted_while_the_flag_is_set(
        api, make_user, login, read_only_flag, monkeypatch):
    make_user('paused')
    recorded = []
    monkeypatch.setattr(signin_limit, 'record_failure', lambda key: recorded.append(key))
    read_only_flag.on()
    for _ in range(12):
        assert login('paused', 'wrong-password').status_code == 401   # no limiter enabled here
    assert recorded == []
    read_only_flag.off()
    login('paused', 'wrong-password')
    assert len(recorded) == 1


def test_an_existing_account_lock_still_holds_under_the_flag(
        api, make_user, login, read_only_flag):
    make_user('locked')
    lim.store().reset()
    for _ in range(signin_limit.MAX_FAILED):
        assert login('locked', 'wrong-password').status_code == 401
    assert login('locked', 'wrong-password').status_code == 429
    read_only_flag.on()
    assert login('locked', DEFAULT_PASSWORD).status_code == 429
    lim.store().reset()


def test_the_address_limit_writes_to_mongodb_only_without_the_flag(
        api, db, env, make_user, login, read_only_flag, monkeypatch):
    import rate_store
    make_user('mongo')
    env(CSC_RATE_LIMIT_STORAGE=None)                  # the shared limiter counts in MongoDB
    previous = lim.shared_limiter._storage, lim.shared_limiter._limiter
    for each in (lim.local_limiter, lim.shared_limiter):
        monkeypatch.setattr(each, 'enabled', True)
    chosen = lim.use_store()
    chosen.reset()
    lim.local_limiter.reset()
    try:
        read_only_flag.on()
        for _ in range(3):
            assert login('mongo', DEFAULT_PASSWORD).status_code == 200
        assert db[rate_store.COLLECTION].count_documents({}) == 0, 'written under the flag'
        read_only_flag.off()
        for _ in range(3):
            assert login('mongo', DEFAULT_PASSWORD).status_code == 200
        counted = list(db[rate_store.COLLECTION].find())
        assert counted and max(doc['count'] for doc in counted) == 3
    finally:
        lim.shared_limiter._storage, lim.shared_limiter._limiter = previous
        for each in (lim.local_limiter, lim.shared_limiter):
            each.enabled = False
            each.reset()
        chosen.reset()
        chosen.storage.close()


def test_sign_in_counts_again_when_the_flag_is_gone(
        api, make_user, login, read_only_flag, counting):
    make_user('back')
    read_only_flag.on()
    login('back', 'wrong-password')
    assert counting == []
    read_only_flag.off()
    login('back', 'wrong-password')
    assert counting, 'a failed sign-in is counted without the flag'


# /version AND /health/db -------------------------------------------------------
def test_version_and_health_report_the_flag(api, read_only_flag):
    assert api.get('/version').json()['read_only'] is False
    assert api.get('/health/db').json() == {'ok': True, 'read_only': False}
    read_only_flag.on()
    assert api.get('/version').json()['read_only'] is True
    assert api.get('/health/db').json() == {'ok': True, 'read_only': True}
    read_only_flag.off()
    assert api.get('/version').json()['read_only'] is False


# THE JOBS ----------------------------------------------------------------------
def test_a_job_skips_with_one_log_line_while_the_flag_is_set(read_only_flag):
    lines = []
    assert read_only.skip_job(lines.append, 'a job') is False and lines == []
    read_only_flag.on()
    assert read_only.skip_job(lines.append, 'a job') is True
    assert len(lines) == 1 and 'a job' in lines[0] and 'read-only' in lines[0]
    # a dry run writes nothing: it goes on
    assert read_only.skip_job(lines.append, 'a job', dry_run=True) is False
    assert len(lines) == 1


def test_the_geometry_runner_skips_its_run(read_only_flag, monkeypatch, caplog):
    import argparse
    import main_geometry
    ran = []
    monkeypatch.setattr(main_geometry, 'run', lambda args: ran.append('local'))
    monkeypatch.setattr(main_geometry, 'run_remote_mode', lambda args: ran.append('remote') or 0)
    monkeypatch.setattr(main_geometry, 'configure_logging', lambda settings: None)
    for remote in (None, 'http://localhost:1'):
        args = argparse.Namespace(dry_run=False, remote=remote)
        read_only_flag.on()
        with caplog.at_level(logging.INFO):
            assert main_geometry.main(args) == 0
        assert ran == []
        skipped = [r for r in caplog.records if 'skipped' in r.getMessage() and 'read-only' in r.getMessage()]
        assert skipped, remote
        caplog.clear()
    read_only_flag.off()
    assert main_geometry.main(argparse.Namespace(dry_run=False, remote='http://localhost:1')) == 0
    assert ran == ['remote']


def test_the_component_map_job_skips_its_run(read_only_flag, monkeypatch, caplog):
    import main_component_map
    ran = []
    monkeypatch.setattr(main_component_map, 'run', lambda **kw: None)
    monkeypatch.setattr(main_component_map.asyncio, 'run', lambda coro: ran.append('ran'))
    monkeypatch.setattr(main_component_map, 'configure_logging', lambda settings: None)
    read_only_flag.on()
    with caplog.at_level(logging.INFO):
        assert main_component_map.main([]) == 0
    assert ran == []
    assert [r for r in caplog.records if 'skipped' in r.getMessage()]
    read_only_flag.off()
    assert main_component_map.main([]) == 0
    assert ran == ['ran']


def test_the_user_clean_up_job_skips_its_run(read_only_flag, monkeypatch, caplog):
    import asyncio
    import usermaintenance
    ran = []

    async def fake_cleanup(dry_run=False):
        ran.append(dry_run)
        return 0

    monkeypatch.setattr(usermaintenance, 'cleanup_unverified_users', fake_cleanup)
    monkeypatch.setattr(usermaintenance, 'configure_logging', lambda settings: None)
    monkeypatch.setattr('sys.argv', ['usermaintenance.py'])
    read_only_flag.on()
    with caplog.at_level(logging.INFO):
        assert asyncio.run(usermaintenance.main()) == 0
    assert ran == []
    read_only_flag.off()
    assert asyncio.run(usermaintenance.main()) == 0
    assert ran == [False]
