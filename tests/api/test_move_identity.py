"""
Moving an element to another dataset (decision 8.191, #50):
``POST /identities/{id}/move``, rule ``move_identity`` --- a moderator of the
source and of the destination dataset. It changes the field ``dataset`` on
the identity and writes a change-log entry; a withdrawn element moves; a
version or record that is draft or pending stops it; a public element does not
move into an unreviewed dataset unless an admin moves it; a dataset emptied
this way can be deleted.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import claim_body
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')              # dbu_zirkus
FELD = iid('feld')              # schoenes_neues_feld, its only element
SOURCE = 'dbu_zirkus'
TARGET = 'ddu_aggregations'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    both, both_id = member_headers({SOURCE: ['moderator'],
                                    TARGET: ['moderator']})
    source_only, _ = member_headers({SOURCE: ['moderator']})
    target_only, _ = member_headers({TARGET: ['moderator']})
    contributor, contributor_id = member_headers({SOURCE: ['contributor']})
    return {'api': api, 'db': db, 'both': both, 'both_id': both_id,
            'src': source_only, 'dst': target_only, 'c': contributor,
            'cid': contributor_id, 'admin': auth_headers('admin'),
            'user': auth_headers('user')}


def _move(w, headers, identity=BEAM, dataset=TARGET):
    return w['api'].post(f'/identities/{identity}/move',
                         json={'dataset': dataset}, headers=headers)


def _stored(w, identity=BEAM):
    return w['db']['component_identities'].find_one({'_id': identity})


# WHO ---------------------------------------------------------------------------
def test_a_moderator_of_both_datasets_moves_the_element(world):
    w, api = world, world['api']
    # a members-only destination: only its own members read what is in it
    w['db']['datasets'].update_one({'_id': TARGET},
                                   {'$set': {'visibility': 'members'}})
    before = _stored(w)
    done = _move(w, w['both'])
    assert done.status_code == 200, done.text
    assert done.json()['dataset'] == TARGET
    after = _stored(w)
    assert after['dataset'] == TARGET
    # the move changes that field and nothing else: the catalog number is
    # global and the versions stay where they are
    assert after['catalog_number'] == before['catalog_number']
    assert after['current_snapshot_id'] == before['current_snapshot_id']
    assert api.get(f'/identities/{BEAM}/compose',
                   headers=w['both']).status_code == 200
    # a change-log entry names the move
    entry = w['db']['change_log'].find_one({'record_id': BEAM,
                                            'cause': 'patch'})
    assert entry['by_user_id'] == w['both_id']
    assert entry['at'] == after['lastmodified']
    assert entry['changes'] == [{'path': 'dataset', 'old': SOURCE,
                                 'new': TARGET}]
    # the rights follow the dataset: a contributor of the old one lost sight
    # of the element that is not public
    assert api.get(f'/identities/{BEAM}/compose',
                   headers=w['c']).status_code == 403


def test_an_admin_moves_the_element(world):
    done = _move(world, world['admin'])
    assert done.status_code == 200, done.text
    assert _stored(world)['dataset'] == TARGET


def test_nobody_else_moves_it(world):
    w = world
    for who in ('src', 'dst', 'c', 'user'):
        refused = _move(w, w[who])
        assert refused.status_code == 403, (who, refused.text)
    assert w['api'].post(f'/identities/{BEAM}/move',
                         json={'dataset': TARGET}).status_code == 401
    assert _stored(w)['dataset'] == SOURCE
    assert w['db']['change_log'].find_one({'record_id': BEAM}) is None
    # a caller who may not move from the source hears no word of the target
    for who in ('dst', 'c', 'user'):
        assert _move(w, w[who], dataset='nowhere').status_code == 403


# WHAT THE DESTINATION IS -------------------------------------------------------
def test_an_unknown_destination_and_the_same_dataset_are_refused(world):
    w = world
    unknown = _move(w, w['both'], dataset='nowhere')
    assert unknown.status_code == 422 and 'unknown dataset' in unknown.text
    same = _move(w, w['both'], dataset=SOURCE)
    assert same.status_code == 409 and 'already' in same.json()['detail']
    # a moderator of the source and an admin hear the same of an unknown one
    for who in ('src', 'admin'):
        assert _move(w, w[who], dataset='nowhere').status_code == 422
    assert _move(w, w['admin'], dataset=SOURCE).status_code == 409
    assert _move(w, w['both'], identity=iid('nobody')).status_code == 404
    assert _stored(w)['dataset'] == SOURCE


def test_the_body_names_the_dataset_only(world):
    api, w = world['api'], world
    assert api.post(f'/identities/{BEAM}/move', json={},
                    headers=w['both']).status_code == 422
    assert api.post(f'/identities/{BEAM}/move',
                    json={'dataset': TARGET, 'all': True},
                    headers=w['both']).status_code == 422


# DRAFT AND PENDING -------------------------------------------------------------
def _add_version(w, status):
    snapshot = w['db']['component_snapshots'].find_one({'_id': sid('beam', 1)})
    snapshot.update({'_id': sid('beam', 2), 'version': 2, 'status': status,
                     'superseded_by': None, 'supersedes': None})
    w['db']['component_snapshots'].insert_one(snapshot)
    return snapshot['_id']


@pytest.mark.parametrize('status', ['draft', 'pending'])
def test_a_draft_or_pending_version_stops_the_move(world, status):
    w = world
    open_id = _add_version(w, status)
    for who in ('both', 'admin'):
        refused = _move(w, w[who])
        assert refused.status_code == 409, (who, refused.text)
        assert 'draft or pending' in refused.json()['detail']
    assert _stored(w)['dataset'] == SOURCE
    # the version leaves: the move goes through
    w['db']['component_snapshots'].update_one(
        {'_id': open_id}, {'$set': {'status': 'rejected'}})
    assert _move(w, w['both']).status_code == 200


@pytest.mark.parametrize('submit', [False, True])
def test_a_draft_or_pending_evidence_record_stops_the_move(world, submit):
    w, api = world, world['api']
    created = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                       headers=w['c'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    if submit:
        assert api.post(f'/evidence/{eid}/submit',
                        headers=w['c']).status_code == 200
    for who in ('both', 'admin'):
        refused = _move(w, w[who])
        assert refused.status_code == 409, (who, refused.text)
        assert 'draft or pending' in refused.json()['detail']
    assert api.delete(f'/evidence/{eid}', headers=w['c']).status_code in (
        200, 204)
    assert _move(w, w['both']).status_code == 200


# WITHDRAWN ---------------------------------------------------------------------
def test_a_withdrawn_element_moves(world):
    w, api = world, world['api']
    assert api.post(f'/identities/{BEAM}/withdraw', json={'reason': 'x'},
                    headers=w['both']).status_code == 200
    done = _move(w, w['both'])
    assert done.status_code == 200, done.text
    assert _stored(w)['dataset'] == TARGET and _stored(w)['withdrawn']


# UNREVIEWED --------------------------------------------------------------------
def _unreview(w):
    w['db']['datasets'].update_one({'_id': TARGET}, {'$set': {
        'reviewed': False}})


def test_a_public_element_does_not_move_into_an_unreviewed_dataset(world):
    w = world
    _unreview(w)
    w['db']['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'is_public': True}})
    refused = _move(w, w['both'])
    assert refused.status_code == 409, refused.text
    assert 'not been reviewed' in refused.json()['detail']
    assert _stored(w)['dataset'] == SOURCE
    # an admin may (8.139 c)
    assert _move(w, w['admin']).status_code == 200
    assert _stored(w)['dataset'] == TARGET


def test_a_non_public_element_moves_into_an_unreviewed_dataset(world):
    w = world
    _unreview(w)
    assert _stored(w)['is_public'] is False
    assert _move(w, w['both']).status_code == 200


# THE EMPTIED DATASET -----------------------------------------------------------
def test_a_dataset_emptied_by_the_move_can_be_deleted(world, member_headers):
    w, api = world, world['api']
    owner, _ = member_headers({'schoenes_neues_feld': ['moderator'],
                               SOURCE: ['moderator']})
    held = api.delete('/datasets/schoenes_neues_feld', headers=owner)
    assert held.status_code == 409
    assert 'move them' in held.json()['detail']
    assert _move(w, owner, identity=FELD, dataset=SOURCE).status_code == 200
    done = api.delete('/datasets/schoenes_neues_feld', headers=owner)
    assert done.status_code == 200, done.text
    assert done.json()['deleted'] == 'schoenes_neues_feld'
    assert w['db']['datasets'].find_one(
        {'_id': 'schoenes_neues_feld'}) is None
    assert _stored(w, FELD)['dataset'] == SOURCE


def test_a_dataset_emptied_by_the_move_can_be_deleted_by_an_admin(world):
    w, api = world, world['api']
    assert api.delete('/datasets/schoenes_neues_feld',
                      headers=w['admin']).status_code == 409
    assert _move(w, w['admin'], identity=FELD, dataset=SOURCE
                 ).status_code == 200
    assert api.delete('/datasets/schoenes_neues_feld',
                      headers=w['admin']).status_code == 200


def test_a_public_element_moves_into_a_reviewed_dataset(world):
    w = world
    w['db']['datasets'].update_one({'_id': TARGET}, {'$set': {
        'reviewed': True}})
    w['db']['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'is_public': True}})
    assert _move(w, w['both']).status_code == 200
    assert _stored(w)['dataset'] == TARGET


def test_a_withdrawn_element_with_open_records_moves_once_they_are_gone(world):
    w, api = world, world['api']
    created = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                       headers=w['c'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    open_id = _add_version(w, 'draft')
    assert api.post(f'/identities/{BEAM}/withdraw', json={'reason': 'x'},
                    headers=w['both']).status_code == 200
    assert _move(w, w['both']).status_code == 409
    # a moderator deletes both, then the move goes through
    assert api.delete(f'/snapshots/{open_id}',
                      headers=w['both']).status_code in (200, 204)
    assert api.delete(f'/evidence/{eid}',
                      headers=w['both']).status_code in (200, 204)
    assert _move(w, w['both']).status_code == 200
    assert _stored(w)['dataset'] == TARGET and _stored(w)['withdrawn']
