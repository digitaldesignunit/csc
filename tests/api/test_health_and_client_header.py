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
    # without CSC_MIN_CLIENT_VERSIONS the header is only logged (8.11)
    response = api.get('/health/db', headers={
        'X-CSC-Client': '', 'User-Agent': 'python-requests/2.32'})
    assert response.status_code == 200
    response = api.get('/health/db', headers={'X-CSC-Client': 'garbage'})
    assert response.status_code == 200
    log = _client_log(backend_env)
    assert "client=unknown agent='python-requests/2.32'" in log
    assert "client=invalid raw='garbage'" in log


def test_enforcement_refuses_outdated_clients_with_426(api, app, backend_env):
    """With a minimum-version table (8.11): 426 for an outdated client,
    anonymous reads without a header still pass, the updater stays open."""
    app.state.min_client_versions = {'gh-userobjects': (0, 6, 0, 0),
                                     'test-suite': (0, 0, 0, 0)}
    try:
        old = {'X-CSC-Client': 'gh-userobjects/0.5.1.0'}
        response = api.get('/materials', headers=old)
        assert response.status_code == 426
        assert 'CSC_Update' in response.json()['detail']
        assert api.get('/ghinterface/version', headers=old).status_code != 426
        anonymous = api.get('/version', headers={'X-CSC-Client': ''})
        assert anonymous.status_code == 200
        write = api.post('/identities', json={}, headers={'X-CSC-Client': ''})
        assert write.status_code == 426
        assert ('client=gh-userobjects version=0.5.1.0 GET /materials 426'
                in _client_log(backend_env))
    finally:
        app.state.min_client_versions = {}


def test_an_outdated_client_can_log_in_but_not_work(api, app):
    """8.95 11: /auth/token answers an old client (so it can run CSC_Update),
    a data route still answers 426."""
    app.state.min_client_versions = {'gh-userobjects': (0, 6, 0, 0)}
    try:
        old = {'X-CSC-Client': 'gh-userobjects/0.5.1.0'}
        login = api.post('/auth/token', headers=old,
                         data={'username': 'nobody', 'password': 'x'})
        assert login.status_code == 401        # reached the route
        assert api.get('/materials', headers=old).status_code == 426
    finally:
        app.state.min_client_versions = {}
