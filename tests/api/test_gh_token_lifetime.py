"""
The lifetime of the token a sign-in gets (decision 8.166): the Grasshopper
client (`X-CSC-Client: gh-userobjects/...`) gets CSC_GH_TOKEN_HOURS (default 6),
every other caller, a missing or malformed header included, the standard
JWT_ACCESS_TOKEN_EXPIRE_MINUTES (30).
"""

from __future__ import annotations

import jwt
import pytest

from support import DEFAULT_PASSWORD

GH = 'gh-userobjects/0.6.2.1'


def lifetime(token: str) -> int:
    """Seconds between iat and exp of a token."""
    claims = jwt.decode(token, options={'verify_signature': False})
    return claims['exp'] - claims['iat']


@pytest.fixture
def account(make_user):
    return make_user(username='tokenuser')['username']


def sign_in(client, account, header=None):
    headers = {} if header is None else {'X-CSC-Client': header}
    response = client.post('/auth/token', headers=headers,
                           data={'username': account, 'password': DEFAULT_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()['access_token']


def test_the_default_is_six_hours_from_the_settings(api):
    assert api.app.state.gh_token_minutes == 6 * 60
    assert api.app.state.jwt_access_minutes == 30


def test_a_grasshopper_sign_in_lives_six_hours(api, account):
    assert lifetime(sign_in(api, account, GH)) == 6 * 3600


@pytest.mark.parametrize('header', ['web/0.6.2.1', 'test-suite/0.0.0', 'gh-userobjects-x/1.0.0'])
def test_any_other_client_lives_thirty_minutes(api, account, header):
    assert lifetime(sign_in(api, account, header)) == 30 * 60


def test_no_header_lives_thirty_minutes(api, account):
    # the shared client sends X-CSC-Client by default: take it away for this call
    kept = api.headers.pop('x-csc-client')
    try:
        assert 'x-csc-client' not in api.headers
        assert lifetime(sign_in(api, account)) == 30 * 60
    finally:
        api.headers['X-CSC-Client'] = kept


@pytest.mark.parametrize('header', [
    'gh-userobjects', 'gh-userobjects/', 'gh-userobjects/one', 'GH-USEROBJECTS/0.6.2.1',
    ' ', 'gh-userobjects/0.6.2.1 extra', 'gh-userobjects/0.6.2.1.2.3'])
def test_a_malformed_header_lives_thirty_minutes(api, account, header):
    assert lifetime(sign_in(api, account, header)) == 30 * 60


def test_the_setting_is_respected(api, account):
    # not monkeypatch.setattr: since pytest 9.2 its undo deletes an attribute
    # that is not in the instance __dict__, and State keeps its own
    kept = api.app.state.gh_token_minutes
    api.app.state.gh_token_minutes = 2 * 60
    try:
        assert lifetime(sign_in(api, account, GH)) == 2 * 3600
        assert lifetime(sign_in(api, account, 'web/0.6.2.1')) == 30 * 60
    finally:
        api.app.state.gh_token_minutes = kept


def test_the_long_token_is_a_working_token(api, account):
    token = sign_in(api, account, GH)
    me = api.get('/users/me', headers={'Authorization': f'Bearer {token}',
                                      'X-CSC-Client': GH})
    assert me.status_code == 200 and me.json()['username'] == 'tokenuser'
