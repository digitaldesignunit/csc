"""
The snapshot lifecycle on the real routes (spec section 3.2.2, section 7.1,
I3, I3b, I15, I21; decisions 8.18, 8.30; plan P3).

One story on the ZirKuS beam (dataset ``dbu_zirkus``): a contributor
records a new state, submits, recalls, gets rejected, resubmits, is
published; the state is corrected, the correction withdrawn and
reinstated; a later draft is deleted.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')


@pytest.fixture
def story(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, contributor_id = member_headers(
        {'dbu_zirkus': ['contributor']})
    reviewer, _ = member_headers({'dbu_zirkus': ['reviewer']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator']})
    other, _ = member_headers({'schoenes_neues_feld': ['moderator']})
    v1 = db['component_snapshots'].find_one({'_id': sid('beam', 1)})
    geometry = {'meshes': v1['geometry']['meshes'], 'point_clouds': [],
                'proxies': []}
    return {'api': api, 'db': db, 'contributor': contributor,
            'contributor_id': contributor_id, 'reviewer': reviewer,
            'moderator': moderator, 'other': other,
            'admin': auth_headers('admin'), 'geometry': geometry}


def _snap(db, snapshot_id):
    return db['component_snapshots'].find_one({'_id': snapshot_id})


def _current(db):
    return db['component_identities'].find_one({'_id': BEAM})[
        'current_snapshot_id']


def test_a_new_state_from_draft_to_published(story):
    api, db = story['api'], story['db']
    c, m = story['contributor'], story['moderator']

    created = api.post(f'/identities/{BEAM}/snapshots',
                       json={'name': 'Beam after cleaning',
                             'geometry': story['geometry']}, headers=c)
    assert created.status_code == 201, created.text
    draft = created.json()
    sid2 = draft['_id']
    assert (draft['version'], draft['status']) == (2, 'draft')
    assert draft['added_by_user_id'] == story['contributor_id']

    # I3b: one in flight; derived / unknown fields are refused
    again = api.post(f'/identities/{BEAM}/snapshots',
                     json={'geometry': story['geometry']}, headers=c)
    assert again.status_code == 409
    sneaky = api.post(f'/identities/{BEAM}/snapshots',
                      json={'geometry': story['geometry'], 'frame': None},
                      headers=c)
    assert sneaky.status_code == 422
    assert api.post(f'/identities/{BEAM}/snapshots',
                    json={'geometry': story['geometry']},
                    headers=story['reviewer']).status_code == 403

    # the author submits; while pending only moderator(D) edits (8.18)
    assert api.post(f'/snapshots/{sid2}/submit',
                    headers=story['reviewer']).status_code == 403
    assert api.post(f'/snapshots/{sid2}/submit', headers=c).json()[
        'status'] == 'pending'
    assert api.patch(f'/snapshots/{sid2}', json={'name': 'x'},
                     headers=c).status_code == 403
    assert api.patch(f'/snapshots/{sid2}', json={'name': 'Cleaned beam'},
                     headers=m).json()['name'] == 'Cleaned beam'

    # the queue: moderators of D (and admin) only
    def queued(headers):
        return [r['_id'] for r in api.get('/snapshots/pending',
                                          headers=headers).json()]
    assert queued(m) == [sid2] and queued(story['admin']) == [sid2]
    assert queued(story['other']) == [] and queued(c) == []

    # recall, resubmit, reject with a reason, resubmit (8.18, I15)
    assert api.post(f'/snapshots/{sid2}/recall', headers=c).json()[
        'status'] == 'draft'
    api.post(f'/snapshots/{sid2}/submit', headers=c)
    assert api.post(f'/snapshots/{sid2}/reject', json={},
                    headers=m).status_code == 422
    rejected = api.post(f'/snapshots/{sid2}/reject',
                        json={'reason': 'photos missing'}, headers=m).json()
    assert rejected['status'] == 'rejected'
    assert api.patch(f'/snapshots/{sid2}', json={'name': 'y'},
                     headers=m).status_code == 403    # rejected: nobody
    assert api.post(f'/snapshots/{sid2}/publish',
                    headers=m).status_code == 409    # not pending
    api.post(f'/snapshots/{sid2}/resubmit', headers=c)
    api.post(f'/snapshots/{sid2}/submit', headers=c)
    published = api.post(f'/snapshots/{sid2}/publish',
                         params={'promote': 1}, headers=m)
    assert published.status_code == 200, published.text
    assert _current(db) == sid2

    history = _snap(db, sid2)['status_history']                 # 8.30
    assert [(h['from'], h['to']) for h in history] == [
        ('draft', 'pending'), ('pending', 'draft'), ('draft', 'pending'),
        ('pending', 'rejected'), ('rejected', 'draft'),
        ('draft', 'pending'), ('pending', 'published')]
    assert history[3]['reason'] == 'photos missing'

    # published: frozen geometry, derived fields, valid time in order
    frozen = api.patch(f'/snapshots/{sid2}',
                       json={'geometry': story['geometry']}, headers=m)
    assert frozen.status_code == 409
    assert api.patch(f'/snapshots/{sid2}', json={'bbx': [1, 2, 3]},
                     headers=m).status_code == 422
    assert api.patch(f'/snapshots/{sid2}', json={'notes': 'n'},
                     headers=c).status_code == 403
    assert api.patch(f'/snapshots/{sid2}', json={'notes': 'n'},
                     headers=m).status_code == 200
    early = api.patch(f'/snapshots/{sid2}',
                      json={'effective_from': '2000-01-01T00:00:00Z'},
                      headers=m)
    assert early.status_code == 409 and 'I3' in early.text
    assert api.delete(f'/snapshots/{sid2}',
                      headers=story['admin']).status_code == 409


def test_correct_withdraw_reinstate_delete(story):
    api, db = story['api'], story['db']
    c, m = story['contributor'], story['moderator']
    v1 = sid('beam', 1)
    assert _current(db) == v1

    correction = api.post(f'/snapshots/{v1}/supersede',
                          json={'geometry': story['geometry']}, headers=c)
    assert correction.status_code == 201, correction.text
    sid3 = correction.json()['_id']
    assert correction.json()['supersedes'] == v1
    assert correction.json()['effective_from'] == _snap(db, v1)[
        'effective_from']
    # submitted by its author, published by moderator(D)
    api.post(f'/snapshots/{sid3}/submit', headers=c)
    assert api.post(f'/snapshots/{sid3}/publish',
                    headers=m).status_code == 200
    assert _snap(db, v1)['superseded_by'] == sid3
    assert _current(db) == sid3                    # replaced the current
    assert api.post(f'/snapshots/{v1}/supersede',
                    json={'geometry': story['geometry']},
                    headers=c).status_code == 409   # superseded once (I21)
    assert api.post(f'/snapshots/{v1}/promote',
                    headers=m).status_code == 409   # no longer live

    # withdraw the current one: falls back to the latest live (8.17)
    assert api.post(f'/snapshots/{sid3}/withdraw', json={'reason': ''},
                    headers=m).status_code == 422
    withdrawn = api.post(f'/snapshots/{sid3}/withdraw',
                         json={'reason': 'wrong scan'}, headers=m)
    assert withdrawn.json()['status'] == 'withdrawn'
    assert _current(db) == sid('beam', 0)
    assert api.post(f'/snapshots/{sid3}/reinstate',
                    headers=c).status_code == 403
    assert api.post(f'/snapshots/{sid3}/reinstate',
                    headers=m).json()['status'] == 'published'
    assert api.post(f'/snapshots/{sid3}/promote',
                    headers=m).status_code == 200
    assert _current(db) == sid3

    # a later draft: its author deletes it, files and all
    draft = api.post(f'/identities/{BEAM}/snapshots',
                     json={'geometry': story['geometry']}, headers=c).json()
    assert api.delete(f'/snapshots/{draft["_id"]}',
                      headers=story['reviewer']).status_code == 403
    assert api.delete(f'/snapshots/{draft["_id"]}',
                      headers=c).status_code == 200
    assert _snap(db, draft['_id']) is None


def test_moderator_submits_and_publishes_at_once(story):
    api, db, m = story['api'], story['db'], story['moderator']
    db['datasets'].update_one(
        {'_id': 'dbu_zirkus', 'members.roles': 'moderator'},
        {'$push': {'members.$.roles': 'contributor'}})
    draft = api.post(f'/identities/{BEAM}/snapshots',
                     json={'geometry': story['geometry']}, headers=m)
    assert draft.status_code == 201, draft.text
    done = api.post(f'/snapshots/{draft.json()["_id"]}/submit',
                    params={'publish': 1, 'promote': 1}, headers=m)
    assert done.json()['status'] == 'published'
    assert _current(db) == draft.json()['_id']


def test_no_new_state_for_a_piece_out_of_circulation(story):
    api = story['api']
    stone = iid('stone')                           # installed (exited)
    story['db']['datasets'].update_one(
        {'_id': 'ddu_build_with_debris'},
        {'$push': {'members': {'user_id': story['contributor_id'],
                               'roles': ['contributor']}}})
    response = api.post(f'/identities/{stone}/snapshots',
                        json={'geometry': story['geometry']},
                        headers=story['contributor'])
    assert response.status_code == 409 and 're-enters' in response.text
