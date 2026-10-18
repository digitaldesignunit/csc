"""A database that cannot be reached answers 503 with Retry-After, and the
traceback goes to the log (decision 8.157 e; found in T2: a request one
second after the host woke from standby ended as a bare 500)."""

from __future__ import annotations

import logging

import pytest
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import rebound_body
from support import iid, seed_05_catalog

SECRET = 'host-and-account-text-of-the-driver'


class Collection:
    """A users collection whose database is gone."""

    def __init__(self, error):
        self.error = error

    async def find_one(self, *_args, **_kwargs):
        raise self.error


@pytest.fixture
def signed_in(api, auth_headers):
    return auth_headers('user')


@pytest.mark.parametrize('error', [AutoReconnect(SECRET), ServerSelectionTimeoutError(SECRET),
                                   NetworkTimeout(SECRET), ConnectionFailure(SECRET)])
def test_a_lost_database_answers_503_with_retry_after_and_logs_the_traceback(
        api, app, signed_in, error, caplog, monkeypatch):
    monkeypatch.setattr(app, 'mongodb_users', Collection(error))
    with caplog.at_level(logging.ERROR, logger='csc'):
        response = api.get('/users/me', headers=signed_in)
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '5'
    assert response.json() == {'detail': 'The database is not available; try again in a few seconds.'}
    assert SECRET not in response.text                         # the driver's text stays in the log
    records = [r for r in caplog.records if r.name.startswith('csc') and r.levelno == logging.ERROR]
    assert records and records[0].exc_info and records[0].exc_info[0] is type(error)
    assert 'database unavailable' in records[0].getMessage()
    assert SECRET in caplog.text                               # with its traceback


def test_the_log_line_names_the_route_not_the_path(api, app, signed_in, caplog,
                                                   monkeypatch):
    monkeypatch.setattr(app, 'mongodb_users', Collection(AutoReconnect('x')))
    with caplog.at_level(logging.ERROR, logger='csc'):
        api.get('/users/me', headers=signed_in)
    message = [r for r in caplog.records if 'database unavailable' in r.getMessage()][0].getMessage()
    assert message == 'database unavailable: GET /users/me'


def test_another_error_is_still_a_500(api, app, signed_in, monkeypatch):
    monkeypatch.setattr(app, 'mongodb_users', Collection(RuntimeError('bug')))
    monkeypatch.setattr(api._transport, 'raise_server_exceptions', False)
    response = api.get('/users/me', headers=signed_in)
    assert response.status_code == 500 and 'Retry-After' not in response.headers


# THE ROUTES THAT CATCH PyMongoError THEMSELVES (decision 8.157 e) -------------------------
class _Boom:
    """What a driver call returns when the database is gone: awaitable and
    chainable (sort, limit, to_list ...), raising on the await."""

    def __init__(self, error):
        self.error = error

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return lambda *a, **k: self

    def __await__(self):
        async def fail():
            raise self.error
        return fail().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self.error


class Flaky:
    """A collection that works, except for the named methods."""

    def __init__(self, real, error, *methods):
        self._real, self._error, self._methods = real, error, methods

    def __getattr__(self, name):
        if name in self._methods:
            return lambda *a, **k: _Boom(self._error)
        return getattr(self._real, name)


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    return {'api': api, 'db': db, 'admin': auth_headers('admin'), 'c': contributor,
            'anonymous': {}}


def _put_cloud(w):
    points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    draft = w['api'].post(f'/identities/{iid("beam")}/snapshots', headers=w['c'], json={
        'geometry': {'meshes': [], 'point_clouds': [{'points': points}], 'proxies': []}})
    assert draft.status_code == 201, draft.text
    return draft.json()['_id']


# (label, method, path, who, collection attribute, broken methods)
CASES = [
    ('a count (status constant)', 'GET', '/identities/count', 'anonymous',
     'mongodb_component_identities', ('aggregate',)),
    ('a list', 'GET', '/identities', 'anonymous', 'mongodb_component_identities', ('aggregate',)),
    ('the stats', 'GET', '/identities/stats', 'anonymous', 'mongodb_component_identities',
     ('aggregate',)),
    ('the user list (admin)', 'GET', '/users', 'admin', 'mongodb_users', ('find',)),
    ('my snapshots', 'GET', '/snapshots?mine=1', 'c', 'mongodb_component_snapshots', ('find',)),
    ('a reservation (an update)', 'POST', f'/identities/{iid("beam")}/reserve', 'c',
     'mongodb_component_identities', ('update_one',)),
    ('the pending transmission', 'GET', '/component_id_transmission', 'c',
     'mongodb_component_id_transmission', ('find_one',)),
    ('the history', 'GET', f'/identities/{iid("beam")}/history', 'c', 'mongodb_component_evidence',
     ('find',)),
]


@pytest.mark.parametrize('label, method, path, who, attribute, methods', CASES,
                         ids=[c[0] for c in CASES])
def test_a_route_that_catches_database_errors_still_answers_503_on_a_lost_connection(
        world, app, monkeypatch, caplog, label, method, path, who, attribute, methods):
    real = getattr(app, attribute)
    monkeypatch.setattr(app, attribute, Flaky(real, AutoReconnect('gone'), *methods))
    with caplog.at_level(logging.ERROR, logger='csc'):
        response = world['api'].request(method, path, headers=world[who])
    assert response.status_code == 503, (label, response.status_code, response.text[:120])
    assert response.headers['Retry-After'] == '5'


def test_the_file_marker_answers_503_on_a_lost_connection(world, app, monkeypatch):
    snapshot_id = _put_cloud(world)
    monkeypatch.setattr(app, 'mongodb_component_snapshots', Flaky(
        app.mongodb_component_snapshots, AutoReconnect('gone'), 'find_one_and_update'))
    ply = (b'ply'+b'\n'+b'format ascii 1.0'+b'\n'+b'element vertex 1'+b'\n'+b'property float x'+b'\n'
           b'property float y'+b'\n'+b'property float z'+b'\n'+b'end_header'+b'\n'+b'0 0 0'+b'\n')
    response = world['api'].put(f'/snapshots/{snapshot_id}/point_clouds/0.ply', headers=world['c'],
                                files={'point_cloud_file': ('c.ply', ply, 'application/octet-stream')})
    assert response.status_code == 503 and response.headers['Retry-After'] == '5'


@pytest.mark.parametrize('error', [OperationFailure('bad query'), PyMongoError('x')])
def test_other_database_errors_keep_their_answer(world, app, monkeypatch, error):
    monkeypatch.setattr(app, 'mongodb_component_identities', Flaky(
        app.mongodb_component_identities, error, 'aggregate'))
    monkeypatch.setattr(world['api']._transport, 'raise_server_exceptions', False)
    response = world['api'].get('/identities/count')
    assert response.status_code == 500 and 'Retry-After' not in response.headers
