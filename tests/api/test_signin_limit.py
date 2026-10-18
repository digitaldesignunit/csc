"""
Failed sign-ins per account (decision 8.162): at most 10 in 15 minutes, then
429 with Retry-After; a success is not counted; an identifier no account has
is counted and answered like one that has; the store holds no plain
identifier.
"""

from __future__ import annotations

import pytest

import limiter as lim
import signin_limit
from support import DEFAULT_PASSWORD


@pytest.fixture(autouse=True)
def clean_store():
    lim.store().reset()
    yield
    lim.store().reset()


def fail(login, identifier):
    return login(identifier, 'a-wrong-password')


def test_the_eleventh_failure_is_answered_429(make_user, login):
    make_user('limited')
    for _ in range(signin_limit.MAX_FAILED):
        assert fail(login, 'limited').status_code == 401
    locked = fail(login, 'limited')
    assert locked.status_code == 429, locked.text
    retry = int(locked.headers['Retry-After'])
    assert 1 <= retry <= signin_limit.WINDOW_SECONDS
    assert 'reset the password' in locked.json()['detail']
    # the right password does not get past the lock either: the answer must
    # not say whether a guess was right
    assert login('limited', DEFAULT_PASSWORD).status_code == 429


def test_the_lock_follows_the_identifier_in_any_case(make_user, login):
    make_user('casey')
    for identifier in ('casey', 'CASEY', ' Casey '):
        for _ in range(3):
            assert fail(login, identifier).status_code == 401
    assert fail(login, 'casey').status_code == 401        # the 10th
    assert fail(login, 'CASEY').status_code == 429


def test_the_email_and_the_username_are_two_identifiers(make_user, login):
    user = make_user('pair')
    for _ in range(signin_limit.MAX_FAILED):
        assert fail(login, 'pair').status_code == 401
    assert fail(login, 'pair').status_code == 429
    # a different identifier of the same account has its own count
    assert login(f'{user["username"]}@tu-darmstadt.de').status_code == 200


def test_a_success_is_not_counted_and_does_not_reset(make_user, login):
    make_user('steady')
    for _ in range(25):
        assert login('steady', DEFAULT_PASSWORD).status_code == 200
    for _ in range(signin_limit.MAX_FAILED - 1):
        assert fail(login, 'steady').status_code == 401
    # a success between the failures does not reset them
    assert login('steady', DEFAULT_PASSWORD).status_code == 200
    assert fail(login, 'steady').status_code == 401           # the 10th
    assert fail(login, 'steady').status_code == 429


def test_an_identifier_no_account_has_is_answered_like_one_that_has(make_user, login):
    make_user('known')
    answers = {}
    for identifier in ('known', 'nobody-has-this'):
        codes = [fail(login, identifier).status_code
                 for _ in range(signin_limit.MAX_FAILED + 1)]
        assert codes == [401] * signin_limit.MAX_FAILED + [429], identifier
        locked = fail(login, identifier)
        answers[identifier] = (locked.status_code, locked.json(),
                               locked.headers['Retry-After'])
    # same status, same body; the time left is within a second or two
    known, unknown = answers['known'], answers['nobody-has-this']
    assert known[:2] == unknown[:2]
    assert abs(int(known[2]) - int(unknown[2])) <= 2


def test_other_accounts_are_not_affected(make_user, login):
    make_user('victim')
    make_user('bystander')
    for _ in range(signin_limit.MAX_FAILED):
        fail(login, 'victim')
    assert fail(login, 'victim').status_code == 429
    assert login('bystander', DEFAULT_PASSWORD).status_code == 200


def test_the_store_holds_no_plain_identifier(make_user, login, app):
    make_user('plainsight')
    for _ in range(3):
        fail(login, 'plainsight')
        fail(login, 'plainsight@tu-darmstadt.de')
    store = lim.store()
    keys = [str(key) for key in getattr(store, 'storage', {})]
    assert any(key.startswith('signin-failed:') for key in keys), keys
    assert not [key for key in keys if 'plainsight' in key.lower()], keys
    # the key is a keyed hash: it depends on the secret
    one = signin_limit.counter_key('first-secret-of-at-least-32-bytes!!', 'plainsight')
    two = signin_limit.counter_key('other-secret-of-at-least-32-bytes!!', 'plainsight')
    assert one != two and 'plainsight' not in one


def test_the_per_address_limit_stays(api, make_user, login, monkeypatch):
    make_user('burst')
    monkeypatch.setattr(lim.shared_limiter, 'enabled', True)
    lim.shared_limiter.reset()
    try:
        codes = [login('burst', DEFAULT_PASSWORD).status_code for _ in range(12)]
    finally:
        lim.shared_limiter.enabled = False
        lim.shared_limiter.reset()
    assert codes[:10] == [200] * 10 and set(codes[10:]) == {429}
