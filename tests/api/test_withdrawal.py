"""
Withdrawal, tombstones, deletion, purge and the identifier resolver on the
real routes (spec section 3.1.4, section 3.1.5, section 7.5, I19;
decisions 6.4, 8.11, 8.17; plan P3).

``cut2`` (dataset ``ddu_aggregations``, visibility ``catalog``) is seen by
every signed-in user, so outsiders get tombstones there.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog, sid

CUT2 = iid('cut2')
DRAFT_PIECE = 'c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f'
DRAFT_SNAP = 'd4e5f6a7-b8c9-4d0e-9f1a-2b3c4d5e6f7a'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    member, member_id = member_headers({'ddu_aggregations': ['contributor']})
    moderator, _ = member_headers({'ddu_aggregations': ['moderator']})
    return {'api': api, 'db': db, 'user': auth_headers('user'),
            'member': member, 'member_id': member_id,
            'moderator': moderator, 'admin': auth_headers('admin')}


def _withdraw(api, identity_id, headers, **body):
    return api.post(f'/identities/{identity_id}/withdraw',
                    json={'reason': 'test', **body}, headers=headers)


def test_withdrawn_identity_full_inside_tombstone_outside(world):
    api, user, member = world['api'], world['user'], world['member']
    assert _withdraw(api, CUT2, member).status_code == 403
    assert api.post(f'/identities/{CUT2}/withdraw', json={'reason': ''},
                    headers=world['moderator']).status_code == 422
    assert _withdraw(api, CUT2, world['moderator'],
                     reason='a person in the photo').status_code == 200

    inside = api.get(f'/identities/{CUT2}/compose', headers=member).json()
    assert inside['identity']['withdrawn']['reason'] == 'a person in the photo'

    for path in (f'/identities/{CUT2}', f'/identities/{CUT2}/compose',
                 f'/identities/{CUT2}/snapshots'):
        outside = api.get(path, headers=user)
        assert outside.status_code == 200, (path, outside.text)
        body = outside.json()
        assert (body['kind'], body['status']) == ('identity', 'withdrawn')
        assert 'reason' not in str(body) and body['withdrawn_at']
    snap = api.get(f'/snapshots/{sid("cut2")}', headers=user).json()
    assert (snap['kind'], snap['version']) == ('snapshot', 0)
    files = api.get(f'/snapshots/{sid("cut2")}/proxies/0/mesh', headers=user)
    assert files.status_code == 403
    assert api.get(f'/snapshots/{sid("cut2")}/proxies/0/mesh',
                   headers=member).status_code == 200

    def listed(headers, **params):
        rows = api.get('/identities', params={'circulation': 'all', **params},
                       headers=headers).json()
        return {r['_id'] for r in rows}
    assert CUT2 not in listed(member)
    assert CUT2 in listed(member, include_withdrawn=True)

    assert api.post(f'/identities/{CUT2}/reinstate',
                    headers=world['moderator']).status_code == 200
    assert 'identity' in api.get(f'/identities/{CUT2}/compose',
                                 headers=user).json()


def test_withdrawn_snapshot_is_a_bare_row_outside(world):
    api, user, db = world['api'], world['user'], world['db']
    response = api.post(f'/snapshots/{sid("cut2")}/withdraw',
                        json={'reason': 'wrong scan'},
                        headers=world['moderator'])
    assert response.status_code == 200, response.text
    assert db['component_identities'].find_one(
        {'_id': CUT2})['current_snapshot_id'] is None      # 8.17
    tomb = api.get(f'/snapshots/{sid("cut2")}', headers=user).json()
    assert tomb['kind'] == 'snapshot' and tomb['withdrawn_at']
    rows = api.get(f'/identities/{CUT2}/snapshots', headers=user).json()
    assert [(r['version'], r['status'], r['name']) for r in rows] == [
        (0, 'withdrawn', None)]
    full = api.get(f'/snapshots/{sid("cut2")}', headers=world['member'])
    assert full.json()['status_history'][-1]['reason'] == 'wrong scan'


def test_duplicates_and_the_resolver(world):
    api, moderator = world['api'], world['moderator']
    cut, panel = iid('cut'), iid('panel')
    world['db']['datasets'].update_one(
        {'_id': 'mineral_composite_panels'},
        {'$push': {'members': world['db']['datasets'].find_one(
            {'_id': 'ddu_aggregations'})['members'][-1]}})

    assert _withdraw(api, CUT2, moderator,
                     duplicate_of=CUT2).status_code == 422
    assert _withdraw(api, CUT2, moderator,
                     duplicate_of=cut).status_code == 200
    moved = api.get(f'/id/{CUT2}', follow_redirects=False)
    assert moved.status_code == 301 and moved.headers['location'] == f'/id/{cut}'
    # cut is named as canonical: withdrawing it needs a successor (I19)
    assert _withdraw(api, cut, moderator).status_code == 409
    assert _withdraw(api, cut, moderator,
                     duplicate_of=panel).json()['followers_repointed'] == 1
    assert world['db']['component_identities'].find_one(
        {'_id': CUT2})['withdrawn']['duplicate_of'] == panel

    beam = iid('beam')
    html = api.get(f'/id/{beam}', headers={'Accept': 'text/html'},
                   follow_redirects=False)
    assert html.status_code == 302
    assert html.headers['location'].endswith(f'/components/{beam}')
    data = api.get(f'/id/{beam}', follow_redirects=False)
    assert data.headers['location'] == f'/identities/{beam}/compose'
    unknown = 'e5f6a7b8-c9d0-4e1f-8a2b-3c4d5e6f7a8b'
    assert api.get(f'/id/{unknown}').status_code == 404


def test_delete_never_published_purge_anything(world):
    api, db = world['api'], world['db']
    db['component_identities'].insert_one({
        **db['component_identities'].find_one({'_id': CUT2}),
        '_id': DRAFT_PIECE, 'catalog_number': 99, 'current_snapshot_id': None,
        'parent_identities': [], 'created_by_user_id': world['member_id']})
    db['component_snapshots'].insert_one({
        **db['component_snapshots'].find_one({'_id': sid('cut2')}),
        '_id': DRAFT_SNAP, 'identity_id': DRAFT_PIECE, 'status': 'draft',
        'added_by_user_id': world['member_id']})
    # unpublished: invisible to the resolver for outsiders (3.1.5)
    assert api.get(f'/id/{DRAFT_PIECE}').status_code == 404
    assert api.delete(f'/identities/{DRAFT_PIECE}',
                      headers=world['user']).status_code == 403
    assert api.delete(f'/identities/{DRAFT_PIECE}',
                      headers=world['member']).status_code == 200
    assert db['component_snapshots'].find_one({'_id': DRAFT_SNAP}) is None
    assert api.delete(f'/identities/{CUT2}',
                      headers=world['moderator']).status_code == 409

    feld = iid('feld')

    def purge(path, headers, **body):
        return api.request('DELETE', path, params={'purge': 1},
                           json=body or None, headers=headers)

    assert purge(f'/identities/{feld}', world['moderator'],
                 confirm_id=feld, reason='x').status_code == 403
    assert purge(f'/identities/{feld}', world['admin'],
                 confirm_id='nope', reason='x').status_code == 422
    done = purge(f'/identities/{feld}', world['admin'], confirm_id=feld,
                 reason='GDPR request')
    assert done.status_code == 200, done.text
    for path in (f'/identities/{feld}', f'/snapshots/{sid("feld")}',
                 f'/id/{feld}'):
        assert api.get(path, headers=world['admin']).status_code == 410, path

    v0 = sid('beam', 0)
    assert purge(f'/snapshots/{v0}', world['admin'], confirm_id=v0,
                 reason='x').status_code == 200
    assert api.get(f'/snapshots/{v0}',
                   headers=world['admin']).status_code == 410
    current = sid('beam', 1)
    assert purge(f'/snapshots/{current}', world['admin'], confirm_id=current,
                 reason='x').status_code == 409
