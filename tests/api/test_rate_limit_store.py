"""
The rate limit counters live in MongoDB (decision 8.152): one collection with
a TTL index, shared by the workers, chosen by CSC_RATE_LIMIT_STORAGE, failing
open when the database does not answer.
"""

from __future__ import annotations

import logging
import time

import pytest
from limits.storage import MemoryStorage

import limiter as lim
import rate_store
from support import DEFAULT_PASSWORD


@pytest.fixture
def store(mongod, db_name):
    """A store on the throwaway database, in its own collection state."""
    mongo = rate_store.GuardedMongoStorage(f'{mongod.uri}/{db_name}', db_name)
    mongo.reset()
    yield mongo
    mongo.reset()
    mongo.storage.close()


# THE STORE -------------------------------------------------------------------
def test_counters_add_up_and_expire(store):
    assert store.incr('k', 60) == 1
    assert store.incr('k', 60) == 2
    assert store.get('k') == 2
    assert store.incr('other', 60) == 1
    assert store.get_expiry('k') > time.time()
    assert store.incr('short', 1) == 1
    time.sleep(1.3)
    assert store.get('short') == 0
    assert store.incr('short', 1) == 1                 # a new window


def test_two_workers_count_the_same_requests(mongod, db_name, store):
    other = rate_store.GuardedMongoStorage(f'{mongod.uri}/{db_name}', db_name)
    try:
        assert store.incr('shared', 60) == 1
        assert other.incr('shared', 60) == 2
        assert store.get('shared') == 2
    finally:
        other.storage.close()


def test_one_collection_with_a_ttl_index(store, mongod, db_name):
    store.incr('k', 60)
    database = store.storage[db_name]
    assert rate_store.COLLECTION in database.list_collection_names()
    assert 'windows' not in database.list_collection_names()
    index = database[rate_store.COLLECTION].index_information()['expireAt_1']
    assert index['expireAfterSeconds'] == 0
    assert 'expireAt' in database[rate_store.COLLECTION].find_one({'_id': 'k'})


def test_the_client_has_a_small_pool(store):
    store.incr('k', 60)
    assert store.storage.options.pool_options.max_pool_size == 20


def test_a_key_can_be_cleared_and_the_store_reset(store):
    store.incr('a', 60)
    store.incr('b', 60)
    store.clear('a')
    assert store.get('a') == 0 and store.get('b') == 1
    store.reset()
    assert store.get('b') == 0


# FAIL OPEN -------------------------------------------------------------------
def test_an_unreachable_store_lets_the_request_pass_with_one_log_line(caplog):
    dead = rate_store.GuardedMongoStorage(
        'mongodb://user:secret-pass@127.0.0.1:1/csc', 'csc')
    with caplog.at_level(logging.INFO, logger='csc'):
        started = time.monotonic()
        counts = [dead.incr('k', 60) for _ in range(5)]
        dead.get('k')
        dead.get_expiry('k')
        elapsed = time.monotonic() - started
    assert counts == [0] * 5                       # hit() sees 0 <= limit: passes
    lines = [r for r in caplog.records if 'rate limit store unreachable' in r.getMessage()]
    assert len(lines) == 1
    assert 'secret-pass' not in caplog.text and '127.0.0.1' not in caplog.text
    # asked once, then left alone for the cooldown: not one wait per request
    assert elapsed < 5


def test_a_limiter_over_a_dead_store_passes_every_request():
    from limits import parse
    from limits.strategies import FixedWindowRateLimiter
    dead = rate_store.GuardedMongoStorage('mongodb://127.0.0.1:1/csc', 'csc')
    strategy = FixedWindowRateLimiter(dead)
    item = parse('1/minute')
    assert all(strategy.hit(item, 'someone') for _ in range(5))


def test_the_store_comes_back_after_the_cooldown(mongod, db_name, monkeypatch):
    mongo = rate_store.GuardedMongoStorage(f'{mongod.uri}/{db_name}', db_name)
    try:
        mongo.reset()
        mongo._down_until = time.monotonic() + 3600       # marked down
        assert mongo.incr('k', 60) == 0
        mongo._down_until = 0.0                            # the cooldown is over
        assert mongo.incr('k', 60) == 1
    finally:
        mongo.reset()
        mongo.storage.close()


# THE CHOICE ------------------------------------------------------------------
def test_unset_the_counters_go_to_the_database_of_the_api(env, backend_env):
    env(CSC_RATE_LIMIT_STORAGE=None)
    previous = lim.shared_limiter._storage, lim.shared_limiter._limiter
    try:
        chosen = lim.use_store()
        assert isinstance(chosen, rate_store.GuardedMongoStorage)
        assert lim.store() is chosen and lim.shared_limiter._limiter.storage is chosen
    finally:
        lim.shared_limiter._storage, lim.shared_limiter._limiter = previous


def test_memory_keeps_them_in_the_process(env):
    env(CSC_RATE_LIMIT_STORAGE='memory://')
    previous = lim.shared_limiter._storage, lim.shared_limiter._limiter
    try:
        assert isinstance(lim.use_store(), MemoryStorage)
    finally:
        lim.shared_limiter._storage, lim.shared_limiter._limiter = previous


def test_a_bad_value_stops_the_start_with_the_name(env):
    from settings import SettingsError, get_settings
    env(CSC_RATE_LIMIT_STORAGE='redis://somewhere')
    with pytest.raises(SettingsError, match='CSC_RATE_LIMIT_STORAGE'):
        get_settings()


# A LIMITED ROUTE COUNTS IN THE STORE -------------------------------------------
def test_a_limited_route_counts_in_the_shared_store(api, make_user, login, monkeypatch):
    make_user('counted')
    monkeypatch.setattr(lim.shared_limiter, 'enabled', True)
    lim.shared_limiter.reset()
    try:
        for _ in range(3):
            assert login('counted', DEFAULT_PASSWORD).status_code == 200
        keys = [str(key) for key in getattr(lim.store(), 'storage', {})]
    finally:
        lim.shared_limiter.enabled = False
        lim.shared_limiter.reset()
    assert any('/auth/token' in key or 'login_for_access_token' in key for key in keys), keys


def test_a_limited_route_counts_in_mongodb_when_no_store_is_named(
        api, db, env, make_user, login, monkeypatch):
    make_user('inmongo')
    env(CSC_RATE_LIMIT_STORAGE=None)
    previous = lim.shared_limiter._storage, lim.shared_limiter._limiter
    monkeypatch.setattr(lim.shared_limiter, 'enabled', True)
    try:
        chosen = lim.use_store()
        chosen.reset()
        for _ in range(3):
            assert login('inmongo', DEFAULT_PASSWORD).status_code == 200
        counted = list(db[rate_store.COLLECTION].find())
    finally:
        lim.shared_limiter._storage, lim.shared_limiter._limiter = previous
        lim.shared_limiter.enabled = False
        chosen.reset()
        chosen.storage.close()
    assert counted and all('expireAt' in doc for doc in counted)
    assert max(doc['count'] for doc in counted) == 3
    assert not [doc for doc in counted if 'inmongo' in str(doc['_id'])]   # no identifier
