"""
S10 (decision 8.144): sign-in takes the same work for an unknown identifier;
the verification token is stored as a hash (an old plain token still works
until it expires); the resend route has a typed body, an always-equal answer
and a cap per address; a second registration for the same address meets the
unique index and answers 409; a short JWT secret refuses to start; a token is
looked up by its subject only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import Request
from jose import jwt

from apps.catalog.api import auth as auth_api
from apps.catalog.api.auth import jwt_secret_problem, token_sha256
from services import email_service
from support import DEFAULT_PASSWORD

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'
ANSWER = ('If an unverified account exists with this email, '
          'a verification email has been sent.')


@pytest.fixture
def outbox(monkeypatch):
    box = {'mails': []}

    def send_mails(config, batch):
        batch = list(batch)
        box['mails'].extend(batch)
        return [None] * len(batch)

    monkeypatch.setattr(email_service, 'send_mails', send_mails)
    return box


def _token_of(mail) -> str:
    return mail.text.split('token=')[1].split()[0]


# SIGN-IN TIMING --------------------------------------------------------------
def test_an_unknown_identifier_costs_a_password_check(login, make_user,
                                                      monkeypatch):
    make_user('alice')
    calls = []
    real = auth_api.verify_password

    def counting(plain, hashed):
        calls.append(hashed)
        return real(plain, hashed)

    monkeypatch.setattr(auth_api, 'verify_password', counting)
    assert login('nobody-at-all').status_code == 401
    assert len(calls) == 1                       # bcrypt ran, against a dummy
    assert login('alice').status_code == 200
    assert len(calls) == 2
    assert login('alice', 'wrong password!').status_code == 401
    assert len(calls) == 3


def test_a_disabled_account_and_a_wrong_password_look_the_same(login,
                                                               make_user):
    make_user('gone', disabled=True)
    make_user('alice')
    a = login('gone')
    b = login('alice', 'wrong password!')
    c = login('nobody-at-all')
    assert a.status_code == b.status_code == c.status_code == 401
    assert a.json() == b.json() == c.json()


# VERIFICATION TOKEN ----------------------------------------------------------
def _register(api, name='dora'):
    return api.post('/auth/register', json={
        'username': name, 'full_name': name.title(),
        'email': f'{name}@stud.tu-darmstadt.de', 'password': DEFAULT_PASSWORD})


def test_the_verification_token_is_stored_as_a_hash(api, db, outbox):
    assert _register(api).status_code == 201
    user = db['users'].find_one({'username': 'dora'})
    token = _token_of(outbox['mails'][0])
    assert user['verification_token_sha256'] == token_sha256(token)
    assert not user.get('verification_token')
    assert token not in str(user)                    # the plain token is nowhere
    # the link works once and clears the hash
    done = api.get('/auth/verify-email', params={'token': token})
    assert done.status_code == 200, done.text
    after = db['users'].find_one({'username': 'dora'})
    assert after['email_verified'] is True
    assert 'verification_token_sha256' not in after
    assert api.get('/auth/verify-email',
                   params={'token': token}).status_code == 400


def test_a_plain_token_from_before_the_patch_still_works_until_it_expires(
        api, db):
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    db['users'].insert_many([
        {'_id': 'old-ok', 'username': 'oldok', 'email': 'oldok@x.org',
         'hashed_password': 'x', 'email_verified': False,
         'verification_token': 'plain-token-ok-0123456789abcdef',
         'verification_token_expires': soon},
        {'_id': 'old-late', 'username': 'oldlate', 'email': 'oldlate@x.org',
         'hashed_password': 'x', 'email_verified': False,
         'verification_token': 'plain-token-late-0123456789abcd',
         'verification_token_expires': soon - timedelta(hours=9)},
    ])
    ok = api.get('/auth/verify-email',
                 params={'token': 'plain-token-ok-0123456789abcdef'})
    assert ok.status_code == 200
    late = api.get('/auth/verify-email',
                   params={'token': 'plain-token-late-0123456789abcd'})
    assert late.status_code == 400
    assert db['users'].find_one({'_id': 'old-ok'})['email_verified'] is True


def test_the_hash_has_a_sparse_index(db):
    indexes = db['users'].index_information()
    entry = [v for v in indexes.values()
             if v['key'] == [('verification_token_sha256', 1)]]
    assert entry and entry[0].get('sparse') is True


# RESEND ----------------------------------------------------------------------
def test_resend_has_a_typed_body(api):
    assert api.post('/auth/resend-verification', json={}).status_code == 422
    assert api.post('/auth/resend-verification',
                    json={'email': 'not an address'}).status_code == 422
    assert api.post('/auth/resend-verification',
                    json={'email': ['a@b.org']}).status_code == 422


def test_resend_answers_alike_and_mails_only_an_unverified_account(
        api, db, outbox, make_user):
    make_user('verified')
    make_user('unverified', verified=False)
    make_user('gone', verified=False, disabled=True)
    answers = [api.post('/auth/resend-verification', json={'email': e})
               for e in ('verified@tu-darmstadt.de',
                         'unverified@tu-darmstadt.de',
                         'gone@tu-darmstadt.de', 'nobody@tu-darmstadt.de')]
    assert {a.status_code for a in answers} == {200}
    assert all(a.json() == {'message': ANSWER} for a in answers)
    assert [m.to for m in outbox['mails']] == ['unverified@tu-darmstadt.de']
    user = db['users'].find_one({'username': 'unverified'})
    assert user['verification_token_sha256'] == token_sha256(
        _token_of(outbox['mails'][0]))


def test_resend_is_capped_per_address(api, db, outbox, make_user):
    make_user('unverified', verified=False)
    for _ in range(auth_api.VERIFICATION_MAILS_PER_HOUR + 3):
        response = api.post('/auth/resend-verification',
                            json={'email': 'unverified@tu-darmstadt.de'})
        assert response.status_code == 200
        assert response.json() == {'message': ANSWER}
    assert len(outbox['mails']) == auth_api.VERIFICATION_MAILS_PER_HOUR


def test_resend_sends_in_a_background_task_not_in_the_request(
        api, make_user, monkeypatch):
    make_user('unverified', verified=False)
    seen = []
    monkeypatch.setattr(auth_api, '_send_verification_mail',
                        lambda *args: seen.append(args))
    api.post('/auth/resend-verification',
             json={'email': 'unverified@tu-darmstadt.de'})
    assert len(seen) == 1                    # ran after the answer, once


# REGISTRATION RACE -----------------------------------------------------------
def test_a_duplicate_that_passes_the_check_answers_409(api, app, monkeypatch):
    """Two requests for one address pass the existence check together; the
    unique index refuses the second, which must be a 409 and not a 500."""
    assert _register(api, 'first').status_code == 201
    users = app.mongodb_users

    class Blind:
        """The users collection, except that the existence check finds
        nobody."""
        def __getattr__(self, name):
            return getattr(users, name)

        async def find_one(self, *args, **kwargs):
            return None

    async def blind_users(request: Request):
        return Blind()

    app.dependency_overrides[auth_api.users_coll] = blind_users
    try:
        response = api.post('/auth/register', json={
            'username': 'first', 'full_name': 'Again',
            'email': 'first@stud.tu-darmstadt.de',
            'password': DEFAULT_PASSWORD})
    finally:
        app.dependency_overrides.pop(auth_api.users_coll, None)
    assert response.status_code == 409, response.text


# JWT SECRET AND CLAIMS -------------------------------------------------------
@pytest.mark.parametrize('secret,bad', [
    ('', True), (None, True), ('short', True), ('x' * 31, True),
    ('x' * 32, False), ('\u00e4' * 16, False), ('\u00e4' * 15, True),
])
def test_a_short_jwt_secret_is_a_problem(secret, bad):
    assert (jwt_secret_problem(secret) is not None) is bad


def test_the_backend_refuses_to_start_with_a_short_secret(backend_env):
    env = {**os.environ, **backend_env, 'JWT_SECRET': 'too-short'}
    run = subprocess.run(
        [sys.executable, '-c', 'import main_fastapi'], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120)
    assert run.returncode == 1
    assert 'JWT_SECRET must be at least 32 bytes' in run.stderr
    assert 'too-short' not in run.stderr + run.stdout


def test_a_token_is_looked_up_by_its_subject_only(api, app, make_user):
    user = make_user('alice')
    secret, algorithm = app.state.jwt_secret, app.state.jwt_algorithm
    now = int(datetime.now(timezone.utc).timestamp())
    base = {'iat': now, 'exp': now + 600, 'role': 'user'}
    # the account named by a legacy claim is not found
    for claims in ({'username': 'alice'}, {'email': 'alice@tu-darmstadt.de'}):
        token = jwt.encode({**base, **claims}, secret, algorithm=algorithm)
        response = api.get('/users/me',
                           headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 401, claims
    token = jwt.encode({**base, 'sub': user['id']}, secret,
                       algorithm=algorithm)
    ok = api.get('/users/me', headers={'Authorization': f'Bearer {token}'})
    assert ok.status_code == 200
