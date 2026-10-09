"""
Fixtures for route tests.

`api` is a TestClient on the real app, `db` a pymongo handle on the same
throwaway database (emptied after every test); both need a local `mongod`, or
CSC_TEST_MONGODB_URI pointing at a disposable server (CI's service container).

Under pytest-xdist every worker is its own process with its own session
fixtures: its own `mongod` on a free port, or --- with CSC_TEST_MONGODB_URI ---
its own database `csc_<worker id>` on the shared server (decision 8.114).
"""

from __future__ import annotations

import os
import uuid

import pytest

from mongod import ThrowawayMongod, find_mongod
from support import DEFAULT_PASSWORD, TEST_CLIENT_HEADER


class _ExternalMongo:
    """A MongoDB someone else runs (CI service container)."""

    def __init__(self, uri):
        self.uri = uri.rstrip('/')


@pytest.fixture(scope='session')
def db_name():
    """The database of this process: ``csc``, or ``csc_<worker>`` under
    xdist (only a shared external server needs the split, but it is harmless
    on a private mongod)."""
    worker = os.getenv('PYTEST_XDIST_WORKER')
    return f'csc_{worker}' if worker else 'csc'


@pytest.fixture(scope='session')
def mongod(db_name):
    external = os.getenv('CSC_TEST_MONGODB_URI')
    if external:  # CI: a mongo service container instead of a local binary
        from pymongo import MongoClient
        with MongoClient(external, serverSelectionTimeoutMS=5000) as client:
            if client[db_name]['component_identities'].estimated_document_count():
                pytest.exit(f'CSC_TEST_MONGODB_URI holds catalog data in '
                            f'{db_name}; route tests empty the database '
                            f'--- use a disposable one')
        yield _ExternalMongo(external)
        return
    binary = find_mongod()
    if binary is None:
        pytest.skip(
            'no mongod binary: install MongoDB Community Server or set '
            'MONGOD_BIN (see README, "Local development and tests")'
        )
    server = ThrowawayMongod(binary).start()
    yield server
    server.stop()


@pytest.fixture(scope='session')
def backend_env(mongod, db_name, tmp_path_factory):
    root = tmp_path_factory.mktemp('backend')
    env = {
        'MONGODB_URI': f'{mongod.uri}/{db_name}',
        'MONGODB_DB': db_name,
        'JWT_SECRET': 'test-only-secret',
        'GITHUB_REPO_URL': 'https://github.com/example/csc',
        'SMTP_HOST': 'localhost',
        'SMTP_USER': 'test',
        'SMTP_PASSWORD': 'test',
        'SMTP_FROM_EMAIL': 'noreply@example.org',
        'SMTP_DEV_MODE': 'true',
        'FRONTEND_URL': 'http://localhost:3000',
        'SNAPSHOT_PREVIEW_DIR': str(root / 'previews'),
        'SNAPSHOT_PHOTOS_DIR': str(root / 'photos'),
        'SNAPSHOT_MESHES_DIR': str(root / 'meshes'),
        'SNAPSHOT_POINT_CLOUDS_DIR': str(root / 'point_clouds'),
        'SNAPSHOT_PROXIES_DIR': str(root / 'proxies'),
        'SNAPSHOT_CAPTURE_DIR': str(root / 'capture'),
        'EVIDENCE_ATTACHMENTS_DIR': str(root / 'evidence'),
        'GH_XML_CACHE_DIR': str(root / 'ghxml'),
        'FASTAPI_CORS_ORIGINS': 'http://localhost:3000',
        'CLIENT_LOG_PATH': str(root / 'logs' / 'client_versions.log'),
    }
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    yield env
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope='session')
def app(backend_env):
    import main_fastapi  # imported late: it validates the env on import
    from limiter import limiter
    limiter.enabled = False  # login tests would hit the 10/minute limit
    return main_fastapi.app


@pytest.fixture(scope='session')
def api(app):
    from fastapi.testclient import TestClient
    with TestClient(app, headers={'X-CSC-Client': TEST_CLIENT_HEADER}) as c:
        yield c


@pytest.fixture
def db(mongod, api, db_name):
    from pymongo import MongoClient
    client = MongoClient(mongod.uri)
    database = client[db_name]
    yield database
    for name in database.list_collection_names():
        database[name].delete_many({})
    # what the app created at startup must exist again for the next test
    database['counters'].insert_one({'_id': 'catalog_number', 'next_value': 1})
    client.close()


@pytest.fixture
def make_user(db):
    """Insert a verified account directly; returns its identifier and id."""
    from apps.catalog.api.auth import get_password_hash

    def _make(username='alice', role='user', verified=True, disabled=False):
        user_id = str(uuid.uuid4())
        db['users'].insert_one({
            '_id': user_id,
            'username': username,
            'email': f'{username}@tu-darmstadt.de',
            'full_name': username.title(),
            'hashed_password': get_password_hash(DEFAULT_PASSWORD),
            'role': role,
            'disabled': disabled,
            'email_verified': verified,
        })
        return {'id': user_id, 'username': username}

    return _make


@pytest.fixture
def login(api):
    def _login(identifier, password=DEFAULT_PASSWORD):
        return api.post(
            '/auth/token',
            data={'username': identifier, 'password': password},
        )
    return _login


@pytest.fixture
def auth_headers(make_user, login):
    """Bearer headers for a fresh account with the given global role."""
    def _headers(role='user', username=None):
        user = make_user(username=username or f'{role}-{uuid.uuid4().hex[:6]}',
                         role=role)
        response = login(user['username'])
        assert response.status_code == 200, response.text
        return {'Authorization': f"Bearer {response.json()['access_token']}"}
    return _headers


@pytest.fixture
def member_headers(db, make_user, login):
    """Bearer headers for a fresh user with dataset roles (section 3.6):
    ``member_headers({'dbu_zirkus': ['moderator']})``; ``'*'`` = every
    dataset in the database. Returns (headers, user id)."""
    def _headers(roles_by_dataset, username=None):
        user = make_user(username=username or f'm-{uuid.uuid4().hex[:6]}')
        if '*' in roles_by_dataset:
            roles = roles_by_dataset['*']
            roles_by_dataset = {d['_id']: roles for d in db['datasets'].find({}, {'_id': 1})}
        for slug, roles in roles_by_dataset.items():
            db['datasets'].update_one({'_id': slug}, {'$push': {'members': {
                'user_id': user['id'], 'roles': list(roles),
                'added_by_user_id': None, 'added_at': None}}})
        response = login(user['username'])
        assert response.status_code == 200, response.text
        return ({'Authorization': f"Bearer {response.json()['access_token']}"},
                user['id'])
    return _headers
