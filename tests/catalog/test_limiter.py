"""
Who a request counts for (src/backend/limiter.py; plan P10 review, decision
8.117 e): the client address behind a trusted proxy, never the leftmost entry
of a header the caller can write, and the signed-in user for the expensive
reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from jose import jwt
from starlette.requests import Request

import limiter as lim

SECRET = 'a-test-secret'


def request(peer, *forwarded, headers=(), app=None):
    scope_headers = [(b'x-forwarded-for', value.encode())
                     for value in forwarded]
    scope_headers += [(k.encode(), v.encode()) for k, v in headers]
    scope = {'type': 'http', 'headers': scope_headers, 'method': 'GET',
             'path': '/', 'query_string': b'',
             'client': (peer, 4711) if peer else None,
             'app': app or SimpleNamespace(state=SimpleNamespace(
                 jwt_secret=SECRET, jwt_algorithm='HS256'))}
    return Request(scope)


@pytest.fixture(autouse=True)
def default_trust(monkeypatch):
    monkeypatch.delenv(lim.TRUSTED_PROXIES_ENV, raising=False)


# THE CLIENT ADDRESS ----------------------------------------------------------
def test_a_header_from_a_peer_that_is_no_trusted_proxy_is_ignored():
    # anyone can write X-Forwarded-For: the peer is the client
    assert lim.client_ip(request('198.51.100.5', '1.1.1.1')) == '198.51.100.5'
    assert lim.client_ip(request('198.51.100.5', '1.1.1.1, 127.0.0.1')) == \
        '198.51.100.5'


def test_the_client_is_what_a_trusted_proxy_reports():
    assert lim.client_ip(request('127.0.0.1', '203.0.113.9')) == '203.0.113.9'
    assert lim.client_ip(request('::1', '203.0.113.9')) == '203.0.113.9'
    assert lim.client_ip(request('::ffff:127.0.0.1', '203.0.113.9')) == \
        '203.0.113.9'


def test_what_the_caller_wrote_on_the_left_is_never_read():
    # the caller sent 6.6.6.6; the proxy appended the real peer
    assert lim.client_ip(request('127.0.0.1', '6.6.6.6, 203.0.113.9')) == \
        '203.0.113.9'
    assert lim.client_ip(request('127.0.0.1', '6.6.6.6', '203.0.113.9')) == \
        '203.0.113.9'          # two header lines make one chain


def test_the_rightmost_entry_that_is_not_a_trusted_proxy_wins(monkeypatch):
    monkeypatch.setenv(lim.TRUSTED_PROXIES_ENV, '127.0.0.0/8, ::1, 10.0.0.2')
    chain = '6.6.6.6, 203.0.113.9, 10.0.0.2, 127.0.0.1'
    assert lim.client_ip(request('127.0.0.1', chain)) == '203.0.113.9'
    # the web server's own address is no proxy unless it is listed
    monkeypatch.delenv(lim.TRUSTED_PROXIES_ENV)
    assert lim.client_ip(request('127.0.0.1', '203.0.113.9, 10.0.0.2')) == \
        '10.0.0.2'


def test_a_trusted_proxy_that_names_no_client_leaves_the_peer():
    assert lim.client_ip(request('127.0.0.1')) == '127.0.0.1'
    assert lim.client_ip(request('127.0.0.1', '127.0.0.1')) == '127.0.0.1'
    assert lim.client_ip(request('127.0.0.1', '')) == '127.0.0.1'


def test_an_entry_that_is_no_address_stops_the_search():
    assert lim.client_ip(request('127.0.0.1', '203.0.113.9, junk')) == \
        '127.0.0.1'
    assert lim.client_ip(request('127.0.0.1', '<script>')) == '127.0.0.1'


def test_ports_brackets_and_mapped_addresses_are_read():
    assert lim.client_ip(request('127.0.0.1', '203.0.113.9:5555')) == \
        '203.0.113.9'
    assert lim.client_ip(request('127.0.0.1', '[2001:db8::7]:443')) == \
        '2001:db8::7'
    assert lim.client_ip(request('127.0.0.1', '::ffff:203.0.113.9')) == \
        '203.0.113.9'


def test_no_peer_at_all():
    assert lim.client_ip(request(None, '203.0.113.9')) == '0.0.0.0'


def test_a_bad_trusted_proxy_setting_is_refused(monkeypatch):
    monkeypatch.setenv(lim.TRUSTED_PROXIES_ENV, '127.0.0.1, not-a-network')
    with pytest.raises(ValueError, match='CSC_TRUSTED_PROXIES'):
        lim.client_ip(request('127.0.0.1', '203.0.113.9'))


# THE KEY OF A SIGNED-IN CALLER -------------------------------------------------
def token(sub='user-1', secret=SECRET, minutes=10):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': sub, 'iat': int(now.timestamp()),
                       'exp': int((now + timedelta(minutes=minutes))
                                  .timestamp())}, secret, algorithm='HS256')


def bearer(value):
    return (('authorization', f'Bearer {value}'),)


def test_a_valid_token_counts_per_user():
    assert lim.signed_in_or_ip(request(
        '198.51.100.5', headers=bearer(token('u1')))) == 'user:u1'
    assert lim.signed_in_or_ip(request(
        '198.51.100.5', headers=bearer(token('u2')))) == 'user:u2'


@pytest.mark.parametrize('headers', [
    (),
    bearer('not.a.token'),
    bearer(token(secret='another-secret')),     # forged: no bucket of its own
    bearer(token(minutes=-5)),                  # expired
    (('authorization', 'Basic abc'),),
])
def test_anyone_else_counts_per_address(headers):
    assert lim.signed_in_or_ip(request('198.51.100.5',
                                       headers=headers)) == '198.51.100.5'


def test_an_unsigned_token_does_not_pick_a_bucket():
    # a token whose signature does not hold must not name a user's bucket
    forged = jwt.encode({'sub': 'victim'}, 'x' * 32, algorithm='HS256')
    assert lim.signed_in_or_ip(request(
        '198.51.100.5', headers=bearer(forged))) == '198.51.100.5'
