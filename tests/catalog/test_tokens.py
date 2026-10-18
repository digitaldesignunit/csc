"""
Access tokens (src/backend/tokens.py; PyJWT replaced python-jose in 0.6.2.0):
HS256 only, `exp` and `sub` required, the claims and the secret of before so
that a token issued before the deploy stays valid, one decode per request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from starlette.requests import Request

import tokens

SECRET = 'a-test-secret-of-at-least-32-bytes'


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def old_encoder_token(claims: dict, secret: str = SECRET) -> str:
    """A token as python-jose made it: compact JSON, header ``{"alg":"HS256",
    "typ":"JWT"}``, HMAC-SHA256 over ``header.payload`` (written out by hand,
    the library is gone)."""
    header = b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'},
                            separators=(',', ':')).encode())
    payload = b64(json.dumps(claims, separators=(',', ':')).encode())
    signing = f'{header}.{payload}'.encode()
    mac = hmac.new(secret.encode(), signing, hashlib.sha256).digest()
    return f'{header}.{payload}.{b64(mac)}'


def claims(**over):
    now = datetime.now(timezone.utc)
    base = {'sub': 'user-1', 'role': 'user', 'iat': int(now.timestamp()),
            'exp': int((now + timedelta(minutes=10)).timestamp())}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def request(secret=SECRET):
    scope = {'type': 'http', 'headers': [], 'method': 'GET', 'path': '/',
             'query_string': b'', 'client': ('198.51.100.5', 1),
             'app': SimpleNamespace(state=SimpleNamespace(jwt_secret=secret))}
    return Request(scope)


# A TOKEN OF BEFORE THE DEPLOY ------------------------------------------------
def test_a_token_made_by_the_old_encoder_decodes_with_the_new_code():
    token = old_encoder_token(claims())
    assert tokens.decode_token(token, SECRET)['sub'] == 'user-1'
    assert tokens.verified_payload(request(), token)['role'] == 'user'


def test_a_token_made_by_the_new_code_has_the_header_of_the_old_one():
    token = tokens.encode_token(SECRET, claims())
    header = json.loads(base64.urlsafe_b64decode(token.split('.')[0] + '=='))
    assert header == {'alg': 'HS256', 'typ': 'JWT'}
    assert tokens.decode_token(token, SECRET)['sub'] == 'user-1'


# WHAT IS REFUSED -------------------------------------------------------------
@pytest.mark.filterwarnings('ignore:The HMAC key')   # the test signs with HS384/HS512 on purpose
def test_only_hs256_is_accepted():
    for algorithm in ('HS384', 'HS512'):
        token = jwt.encode(claims(), SECRET, algorithm=algorithm)
        assert tokens.verified_payload(request(), token) is None, algorithm
    # "alg": "none" with no signature at all
    header = b64(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode())
    body = b64(json.dumps(claims()).encode())
    assert tokens.verified_payload(request(), f'{header}.{body}.') is None


@pytest.mark.parametrize('missing', ['exp', 'sub'])
def test_exp_and_sub_are_required(missing):
    token = old_encoder_token(claims(**{missing: None}))
    assert tokens.verified_payload(request(), token) is None


def test_a_wrong_key_or_an_expired_token_is_refused():
    assert tokens.verified_payload(
        request(), old_encoder_token(claims(), secret='x' * 40)) is None
    past = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
    assert tokens.verified_payload(
        request(), old_encoder_token(claims(exp=past))) is None
    assert tokens.verified_payload(request(), 'not.a.token') is None


# ONE DECODE PER REQUEST ------------------------------------------------------
def test_a_request_is_decoded_once(monkeypatch):
    calls = []
    real = tokens.decode_token
    monkeypatch.setattr(tokens, 'decode_token',
                        lambda token, secret: calls.append(1) or real(token, secret))
    req = request()
    token = tokens.encode_token(SECRET, claims())
    assert tokens.verified_payload(req, token)['sub'] == 'user-1'
    assert tokens.verified_payload(req, token)['sub'] == 'user-1'
    assert len(calls) == 1


def test_a_refused_token_is_not_decoded_again_either(monkeypatch):
    calls = []
    real = tokens.decode_token
    monkeypatch.setattr(tokens, 'decode_token',
                        lambda token, secret: calls.append(1) or real(token, secret))
    req = request()
    assert tokens.verified_payload(req, 'garbage') is None
    assert tokens.verified_payload(req, 'garbage') is None
    assert len(calls) == 1


def test_the_answer_for_one_token_is_not_given_for_another():
    req = request()
    good = tokens.encode_token(SECRET, claims(sub='u1'))
    other = tokens.encode_token(SECRET, claims(sub='u2'))
    assert tokens.verified_payload(req, good)['sub'] == 'u1'
    assert tokens.verified_payload(req, other)['sub'] == 'u2'
    assert tokens.verified_payload(req, 'garbage') is None


def test_the_log_never_holds_the_token(caplog):
    token = old_encoder_token(claims(), secret='x' * 40)
    with caplog.at_level('INFO', logger='csc'):
        assert tokens.verified_payload(request(), token) is None
    assert caplog.records and token not in caplog.text
    assert token.split('.')[1] not in caplog.text
