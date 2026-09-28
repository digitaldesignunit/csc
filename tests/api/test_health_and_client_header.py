"""App boots against a real mongod; every request's client is logged."""

from support import TEST_CLIENT_HEADER


def _client_log(backend_env):
    with open(backend_env['CLIENT_LOG_PATH'], encoding='utf-8') as handle:
        return handle.read()


def test_health_reaches_the_database(api):
    response = api.get('/health/db')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_requests_are_logged_with_their_client(api, backend_env):
    api.get('/health/db')
    client, version = TEST_CLIENT_HEADER.split('/')
    assert f'client={client} version={version} GET /health/db 200' in (
        _client_log(backend_env))


def test_missing_or_invalid_header_is_logged_never_rejected(api, backend_env):
    # 0.5.1.0 only logs; enforcement arrives with 0.6 (spec section 7.4)
    response = api.get('/health/db', headers={
        'X-CSC-Client': '', 'User-Agent': 'python-requests/2.32'})
    assert response.status_code == 200
    response = api.get('/health/db', headers={'X-CSC-Client': 'garbage'})
    assert response.status_code == 200
    log = _client_log(backend_env)
    assert "client=unknown agent='python-requests/2.32'" in log
    assert "client=invalid raw='garbage'" in log
