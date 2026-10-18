"""
One verified payload per request: the limiter key and the authentication
dependency share it through ``request.state`` (src/backend/tokens.py).
"""

from __future__ import annotations

import pytest

import limiter as lim
import tokens


@pytest.fixture
def decodes(monkeypatch):
    calls = []
    real = tokens.decode_token
    monkeypatch.setattr(tokens, 'decode_token',
                        lambda token, secret: calls.append(1) or real(token, secret))
    return calls


def test_a_limited_and_authenticated_request_is_decoded_once(
        api, auth_headers, decodes, monkeypatch):
    headers = auth_headers('user')
    monkeypatch.setattr(lim.local_limiter, 'enabled', True)    # the key function runs
    lim.local_limiter.reset()
    del decodes[:]
    try:
        response = api.get('/identities/count', headers=headers)
    finally:
        lim.local_limiter.enabled = False
        lim.local_limiter.reset()
    assert response.status_code == 200, response.text
    assert len(decodes) == 1


def test_a_request_with_a_bad_token_is_decoded_once_and_refused(api, decodes):
    del decodes[:]
    response = api.get('/users/me', headers={'Authorization': 'Bearer not.a.token'})
    assert response.status_code == 401
    assert len(decodes) == 1


@pytest.mark.filterwarnings('ignore:The HMAC key')   # the test signs with HS512 on purpose
def test_a_token_of_another_algorithm_or_without_exp_is_refused_by_the_route(api, app):
    import jwt
    import time
    secret = app.state.jwt_secret
    soon = int(time.time()) + 600
    for token in (jwt.encode({'sub': 'x', 'exp': soon}, secret, algorithm='HS512'),
                  jwt.encode({'sub': 'x'}, secret, algorithm='HS256')):
        response = api.get('/users/me', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 401
