"""
S9 (decision 8.144): an answer never carries a file path, a stored document or
a driver message. A 500 has one constant text and the cause goes to the log;
``/health/db`` answers ``{'ok': false}`` with 503. The 422 answers that carry
validation messages meant for the client stay.
"""

from __future__ import annotations

import pytest
from pymongo.errors import PyMongoError

from apps.catalog.api import snapshots as snapshots_api
from apps.catalog.api.catalog_common import INTERNAL_ERROR_TEXT, internal_error
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import seed_05_catalog, sid

SECRET = 'driver says: mongodb://user:pw@host/db at /srv/csc/meshes/x.ply'


def test_internal_error_has_one_constant_text_and_logs_the_cause(capsys):
    exc = internal_error(ValueError(SECRET), 'a thing')
    assert exc.status_code == 500
    assert exc.detail == INTERNAL_ERROR_TEXT == 'Internal server error'
    out = capsys.readouterr().out
    assert 'a thing' in out and 'ValueError' in out and SECRET in out


class _BrokenDatabase:
    async def command(self, *_args, **_kwargs):
        raise PyMongoError(SECRET)


def test_health_db_answers_503_without_the_driver_text(api, app, monkeypatch,
                                                      capsys):
    monkeypatch.setattr(app, 'mongodb', _BrokenDatabase())
    response = api.get('/health/db')
    assert response.status_code == 503
    assert response.json() == {'ok': False}
    assert SECRET not in response.text
    assert SECRET in capsys.readouterr().out                 # logged


@pytest.fixture
def world(api, db, auth_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    return {'api': api, 'admin': auth_headers('admin'), 'db': db}


def test_a_stored_document_that_fails_validation_is_not_echoed(
        world, monkeypatch):
    def broken(_doc):
        raise ValueError(f'1 validation error for X: input {SECRET}')
    monkeypatch.setattr(snapshots_api, 'snapshot_body', broken)
    response = world['api'].get(f'/snapshots/{sid("beam", 1)}',
                                headers=world['admin'])
    assert response.status_code == 500
    assert response.json() == {'detail': 'Internal server error'}
    assert 'validation error' not in response.text


def test_a_missing_mesh_file_does_not_name_its_path(world):
    snapshot = sid('beam', 1)
    world['db']['component_snapshots'].update_one(
        {'_id': snapshot}, {'$set': {'mesh_ply_resolutions': {'0': ['reduced']}}})
    response = world['api'].get(f'/snapshots/{snapshot}/meshes/0/reduced',
                                headers=world['admin'])
    assert response.status_code == 404
    detail = response.json()['detail']
    assert detail == 'PLY file not found on disk'
    assert '/' not in detail and '\\' not in detail


def test_validation_messages_meant_for_the_client_stay(world):
    # a profile edit with a bad ORCID: the 422 says what is wrong
    response = world['api'].patch('/users/me', headers=world['admin'],
                                  json={'orcid': 'not-an-orcid'})
    assert response.status_code == 422
    assert response.json()['detail']
