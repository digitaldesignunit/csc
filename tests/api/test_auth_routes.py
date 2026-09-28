"""Login, registration and password change against a real database."""

from support import DEFAULT_PASSWORD


def test_login_by_username_or_email(make_user, login):
    make_user('alice')
    assert login('alice').status_code == 200
    assert login('alice@tu-darmstadt.de').status_code == 200


def test_login_rejects_wrong_password_unverified_and_disabled(make_user, login):
    make_user('alice')
    make_user('bob', verified=False)
    make_user('carol', disabled=True)
    assert login('alice', 'wrong password!').status_code == 401
    assert login('bob').status_code == 403
    assert login('carol').status_code == 401


def test_registration_creates_an_unverified_account(api, db):
    response = api.post('/auth/register', json={
        'username': 'dora', 'full_name': 'Dora',
        'email': 'dora@stud.tu-darmstadt.de', 'password': DEFAULT_PASSWORD,
    })
    assert response.status_code in (200, 201), response.text
    user = db['users'].find_one({'username': 'dora'})
    assert user is not None and user['email_verified'] is False
    assert user['hashed_password'].startswith('$2b$')


def test_registration_rejects_foreign_domains_and_long_passwords(api):
    foreign = api.post('/auth/register', json={
        'username': 'eve', 'full_name': 'Eve',
        'email': 'eve@example.org', 'password': DEFAULT_PASSWORD,
    })
    assert foreign.status_code in (400, 422)
    too_long = api.post('/auth/register', json={
        'username': 'eve', 'full_name': 'Eve',
        'email': 'eve@tu-darmstadt.de', 'password': '\u00e4' * 40,  # a-umlaut: 80 bytes
    })
    assert too_long.status_code == 422


def test_change_password(api, make_user, login):
    make_user('alice')
    token = login('alice').json()['access_token']
    response = api.post(
        '/auth/change-password',
        headers={'Authorization': f'Bearer {token}'},
        json={'current_password': DEFAULT_PASSWORD,
              'new_password': 'a brand new passphrase'},
    )
    assert response.status_code == 200, response.text
    assert login('alice').status_code == 401
    assert login('alice', 'a brand new passphrase').status_code == 200
