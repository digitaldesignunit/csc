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
    ServerSelectionTimeoutError,
)

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
