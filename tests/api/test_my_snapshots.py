"""
``GET /snapshots?mine=1`` (decision 8.118 Q4): the caller's own versions for
"My work", with the piece they belong to and the reason of a rejection.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')
FRAME = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}
BOX = {'primitive': 'box', 'role': 'primary', 'params': {'size': [2, 1, 1]},
       'placement': FRAME, 'fit': {'method': 'authored'}}


@pytest.fixture
def world(api, db, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, contributor_id = member_headers(
        {'dbu_zirkus': ['contributor']})
    other, other_id = member_headers({'dbu_zirkus': ['contributor']})
    moderator, _ = member_headers(
        {'dbu_zirkus': ['moderator', 'contributor']})
    material = db['component_identities'].find_one({'_id': BEAM})['material']
    return {'api': api, 'db': db, 'c': contributor, 'cid': contributor_id,
            'o': other, 'oid': other_id, 'm': moderator,
            'material': material}


def _piece(w, headers, name):
    created = w['api'].post('/identities', json={
        'dataset': 'dbu_zirkus', 'original_function': 'IfcWall',
        'material': w['material'],
        'origin': {'kind': 'offcut', 'construction_work': None},
        'snapshot': {'name': name, 'geometry': {'proxies': [BOX]}}},
        headers=headers)
    assert created.status_code == 201, created.text
    return created.json()


def _mine(w, headers, **params):
    got = w['api'].get('/snapshots', params={'mine': 1, **params},
                       headers=headers)
    assert got.status_code == 200, got.text
    return got.json()


def test_only_the_callers_own_versions_are_listed(world):
    w = world
    mine = _piece(w, w['c'], 'mine draft')
    pending = _piece(w, w['c'], 'mine pending')
    theirs = _piece(w, w['o'], 'theirs')
    assert w['api'].post(f"/snapshots/{pending['snapshot']['_id']}/submit",
                         headers=w['c']).status_code == 200
    rows = _mine(w, w['c'])
    assert {r['name'] for r in rows} == {'mine draft', 'mine pending'}
    by_name = {r['name']: r for r in rows}
    assert by_name['mine draft']['status'] == 'draft'
    assert by_name['mine pending']['status'] == 'pending'
    assert by_name['mine draft']['identity_id'] == mine['identity']['_id']
    assert by_name['mine draft']['dataset'] == 'dbu_zirkus'
    assert by_name['mine draft']['original_function'] == 'IfcWall'
    assert by_name['mine draft']['is_current'] is False
    assert 'theirs' not in {r['name'] for r in rows}
    assert {r['name'] for r in _mine(w, w['o'])} == {'theirs'}
    # nobody else's, whatever the caller's role
    assert theirs['snapshot']['_id'] not in {r['_id'] for r in
                                              _mine(w, w['m'])}


def test_a_rejected_version_carries_its_reason(world):
    w = world
    piece = _piece(w, w['c'], 'to reject')
    sid = piece['snapshot']['_id']
    assert w['api'].post(f'/snapshots/{sid}/submit',
                         headers=w['c']).status_code == 200
    rejected = w['api'].post(f'/snapshots/{sid}/reject',
                             json={'reason': 'The box is too small.'},
                             headers=w['m'])
    assert rejected.status_code == 200, rejected.text
    row = next(r for r in _mine(w, w['c']) if r['_id'] == sid)
    assert row['status'] == 'rejected'
    assert row['rejection_reason'] == 'The box is too small.'
    only = _mine(w, w['c'], status='rejected')
    assert [r['_id'] for r in only] == [sid]


def test_the_status_filter_and_the_required_flag(world):
    w = world
    _piece(w, w['c'], 'draft one')
    published = _piece(w, w['c'], 'published one')
    sid = published['snapshot']['_id']
    assert w['api'].post(f'/snapshots/{sid}/submit',
                         headers=w['c']).status_code == 200
    assert w['api'].post(f'/snapshots/{sid}/publish?promote=1',
                         headers=w['m']).status_code == 200
    names = lambda **kw: {r['name'] for r in _mine(w, w['c'], **kw)}   # noqa: E731
    assert names() == {'draft one'}                      # unfinished by default
    assert names(status='published') == {'published one'}
    assert names(status='draft,published') == {'draft one', 'published one'}
    assert names(status='any') == {'draft one', 'published one'}
    published_row = next(r for r in _mine(w, w['c'], status='published'))
    assert published_row['is_current'] is True
    assert w['api'].get('/snapshots', headers=w['c']).status_code == 422
    assert w['api'].get('/snapshots', params={'mine': 1, 'status': 'bogus'},
                        headers=w['c']).status_code == 422
    assert w['api'].get('/snapshots', params={'mine': 1}).status_code == 401
