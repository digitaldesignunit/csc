"""``POST /datasets/{did}/public`` (decision 8.131 c): every published, not
withdrawn piece of a dataset public or private at once, by ``moderator(D)``;
each change logged like a metadata PATCH; unpublished and withdrawn pieces and
other datasets untouched; no inheritance."""

from __future__ import annotations

import copy

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')
FELD = iid('feld')
DRAFT = 'aaaaaaaa-0000-4000-8000-000000000001'      # never published
GONE = 'aaaaaaaa-0000-4000-8000-000000000002'       # withdrawn
CHILD = 'aaaaaaaa-0000-4000-8000-000000000003'      # a child of the beam


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    identities = db['component_identities']
    beam = identities.find_one({'_id': BEAM})
    draft = copy.deepcopy(beam)
    draft.update({'_id': DRAFT, 'current_snapshot_id': None,
                  'catalog_number': 9001, 'is_public': False})
    gone = copy.deepcopy(beam)
    gone.update({'_id': GONE, 'catalog_number': 9002, 'is_public': False,
                 'withdrawn': {'at': '2026-09-01T00:00:00Z', 'reason': 'x',
                               'by_user_id': 'u-admin'}})
    child = copy.deepcopy(beam)
    child.update({'_id': CHILD, 'catalog_number': 9003, 'is_public': False,
                  'parent_identities': [BEAM]})
    identities.insert_many([draft, gone, child])
    identities.update_many({'dataset': 'dbu_zirkus'},
                           {'$set': {'is_public': False}})
    identities.update_one({'_id': FELD}, {'$set': {'is_public': False}})
    m, _ = member_headers({'dbu_zirkus': ['moderator']})
    c, _ = member_headers({'dbu_zirkus': ['contributor']})
    other, _ = member_headers({'schoenes_neues_feld': ['moderator']})
    return {'api': api, 'db': db, 'm': m, 'c': c, 'other': other,
            'admin': auth_headers('admin')}


def _flag(world, identity_id):
    return world['db']['component_identities'].find_one(
        {'_id': identity_id}).get('is_public')


def _post(world, headers, body, did='dbu_zirkus'):
    return world['api'].post(f'/datasets/{did}/public', json=body,
                             headers=headers)


def _anonymous_ids(world):
    rows = world['api'].get('/identities', params={'expand': 'shallow'}).json()
    return {row['_id'] for row in rows}


def test_a_moderator_makes_the_published_pieces_public_and_the_rest_stays(world):
    w = world
    assert BEAM not in _anonymous_ids(w)
    before = w['db']['change_log'].count_documents({'record_id': BEAM})
    got = _post(w, w['m'], {'is_public': True})
    assert got.status_code == 200, got.text
    result = got.json()
    published = w['db']['component_identities'].count_documents(
        {'dataset': 'dbu_zirkus', 'is_public': True})
    assert result['changed'] == published >= 1
    assert result['dry_run'] is False and result['is_public'] is True
    assert _flag(w, BEAM) is True
    # unpublished and withdrawn pieces and other datasets: untouched; the
    # child is a published piece of the dataset itself, so it is set too
    assert _flag(w, DRAFT) is False and _flag(w, GONE) is False
    assert _flag(w, CHILD) is True
    assert _flag(w, FELD) is False
    # one change log entry per changed piece, like a metadata PATCH
    entries = list(w['db']['change_log'].find({'record_id': BEAM}))
    assert len(entries) == before + 1
    last = max(entries, key=lambda e: e['at'])
    assert last.get('cause') == 'patch' and last.get('by_user_id')
    # anonymous visitors list the piece now
    assert BEAM in _anonymous_ids(w)
    # again: nothing left to change
    assert _post(w, w['m'], {'is_public': True}).json()['changed'] == 0


def test_a_dry_run_counts_and_writes_nothing(world):
    w = world
    count = w['db']['change_log'].count_documents({})
    got = _post(w, w['m'], {'is_public': True, 'dry_run': True})
    assert got.status_code == 200
    assert got.json()['dry_run'] is True and got.json()['changed'] >= 1
    assert _flag(w, BEAM) is False
    assert w['db']['change_log'].count_documents({}) == count
    assert BEAM not in _anonymous_ids(w)


def test_private_again(world):
    w = world
    _post(w, w['m'], {'is_public': True})
    assert BEAM in _anonymous_ids(w)
    got = _post(w, w['m'], {'is_public': False})
    assert got.json()['changed'] >= 1
    assert _flag(w, BEAM) is False and _flag(w, CHILD) is False
    assert BEAM not in _anonymous_ids(w)


def test_a_piece_does_not_pass_its_flag_to_its_children(world):
    """6.2: every piece keeps its own flag; making the parent public by the
    ordinary PATCH leaves the child as it is."""
    w = world
    got = w['api'].patch(f'/identities/{BEAM}', json={'is_public': True},
                         headers=w['m'])
    assert got.status_code == 200, got.text
    assert _flag(w, BEAM) is True and _flag(w, CHILD) is False


def test_who_may_and_who_may_not(world):
    w = world
    body = {'is_public': True}
    assert w['api'].post('/datasets/dbu_zirkus/public', json=body
                         ).status_code == 401                 # anonymous
    assert _post(w, w['c'], body).status_code == 403          # contributor
    assert _post(w, w['other'], body).status_code == 403      # other dataset
    assert _post(w, w['m'], body, did='schoenes_neues_feld').status_code == 403
    assert _post(w, w['admin'], body).status_code == 200      # admin shortcut
    assert _post(w, w['m'], {'is_public': True, 'extra': 1}).status_code == 422
    assert _post(w, w['m'], body, did='nope').status_code == 404
    assert _flag(w, FELD) is False


# THE 0.6.0.2 REVIEW NOTES (0.6.1.0 B) -----------------------------------------
def test_one_invalid_piece_stops_the_whole_change_before_anything_is_written(
        world):
    w = world
    w['db']['component_identities'].update_one(
        {'_id': CHILD}, {'$set': {'original_function': 'not a class'}})
    before = w['db']['change_log'].count_documents({})
    got = _post(w, w['m'], {'is_public': True})
    assert got.status_code == 422, got.text
    detail = got.json()['detail']
    assert 'nothing was changed' in detail['message']
    assert list(detail['pieces']) == [CHILD]
    assert _flag(w, BEAM) is False                        # none written
    assert w['db']['change_log'].count_documents({}) == before
    # a dry run only counts
    assert _post(w, w['m'], {'is_public': True, 'dry_run': True}
                 ).status_code == 200


def test_a_piece_that_changed_meanwhile_leaves_no_log_entry(world, monkeypatch):
    """The entry is written after the replace stands (a 409 leaves none)."""
    w = world
    app = w['api'].app
    real = app.mongodb_component_identities

    class Racing:
        def __getattr__(self, name):
            return getattr(real, name)

        async def replace_one(self, *args, **kwargs):
            class Lost:
                matched_count = 0
            return Lost()

    monkeypatch.setattr(app, 'mongodb_component_identities', Racing())
    before = w['db']['change_log'].count_documents({})
    got = w['api'].patch(f'/identities/{BEAM}', json={'is_public': True},
                         headers=w['m'])
    assert got.status_code == 409
    assert w['db']['change_log'].count_documents({}) == before
    skipped = _post(w, w['m'], {'is_public': True})
    assert skipped.status_code == 200
    assert skipped.json()['changed'] == 0 and skipped.json()['skipped'] >= 1
    assert w['db']['change_log'].count_documents({}) == before


# S13 (8.144): the anonymous dataset list follows the pieces it counts ---------
def _anonymous_datasets(world):
    rows = world['api'].get('/datasets').json()
    return {row['_id']: row.get('component_count') for row in rows}


def test_an_anonymous_list_shows_a_dataset_only_for_published_public_pieces(
        world):
    identities = world['db']['component_identities']
    identities.update_many({'dataset': 'dbu_zirkus'},
                           {'$set': {'is_public': False}})
    # nothing public: not listed
    assert 'dbu_zirkus' not in _anonymous_datasets(world)
    # a public piece that is not published (no current snapshot) and a public
    # piece that is withdrawn do not make the dataset visible ...
    identities.update_one({'_id': DRAFT}, {'$set': {'is_public': True,
                                                    'dataset': 'dbu_zirkus'}})
    identities.update_one({'_id': GONE}, {'$set': {'is_public': True,
                                                   'dataset': 'dbu_zirkus'}})
    assert 'dbu_zirkus' not in _anonymous_datasets(world)
    # ... a published, public, not withdrawn piece does, with its count
    identities.update_one({'_id': BEAM}, {'$set': {'is_public': True}})
    shown = _anonymous_datasets(world)
    assert shown.get('dbu_zirkus') == 1
    assert all(count for count in shown.values())      # never a count of zero
