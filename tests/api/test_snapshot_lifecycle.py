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


def test_nobody_publishes_directly_a_moderator_submits_then_publishes(story):
    api, db, m = story['api'], story['db'], story['moderator']
    db['datasets'].update_one(
        {'_id': 'dbu_zirkus', 'members.roles': 'moderator'},
        {'$push': {'members.$.roles': 'contributor'}})
    draft = api.post(f'/identities/{BEAM}/snapshots',
                     json={'geometry': story['geometry']}, headers=m)
    assert draft.status_code == 201, draft.text
    sid = draft.json()['_id']
    # an old client's ?publish=1&promote=1 is ignored (8.120)
    done = api.post(f'/snapshots/{sid}/submit',
                    params={'publish': 1, 'promote': 1}, headers=m)
    assert done.status_code == 200 and done.json()['status'] == 'pending'
    assert _current(db) != sid
    # publishing is the separate step, also for the moderator's own record
    done = api.post(f'/snapshots/{sid}/publish', params={'promote': 1},
                    headers=m)
    assert done.json()['status'] == 'published'
    assert _current(db) == sid


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


# THE PROFILE OF A NEW PRISM IS A SIMPLE POLYGON (8.112 review) --------------
def _prism(profile, holes=None):
    return {'primitive': 'prism', 'role': 'primary',
            'params': {'profile': profile, 'holes': holes, 'height': 10},
            'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                          'z': [0, 0, 1]},
            'fit': {'method': 'authored'}}


def test_a_new_prism_must_be_a_simple_polygon(story):
    api = story['api']
    c = story['contributor']
    square = [[0, 0], [20, 0], [20, 20], [0, 20]]

    def draft(proxy):
        geometry = {'meshes': [], 'point_clouds': [], 'proxies': [proxy]}
        return api.post(f'/identities/{BEAM}/snapshots', headers=c,
                        json={'name': 'prism', 'geometry': geometry})

    bowtie = draft(_prism([[0, 0], [20, 20], [20, 0], [0, 20]]))
    assert bowtie.status_code == 422, bowtie.text
    assert 'simple polygon' in bowtie.text and 'proxies[0]' in bowtie.text
    # a hole outside the profile, a profile without area
    assert draft(_prism(square, [[[30, 30], [40, 30], [40, 40]]])
                 ).status_code == 422
    assert draft(_prism([[0, 0], [10, 0], [20, 0]])).status_code == 422
    ok = draft(_prism(square, [[[5, 5], [10, 5], [10, 10], [5, 10]]]))
    assert ok.status_code == 201, ok.text
    # creating a whole component takes the same body
    created = api.post('/identities', headers=c, json={
        'dataset': 'dbu_zirkus', 'original_function': 'IfcBeam',
        'material': 'concrete',
        'snapshot': {'name': 'p', 'geometry': {
            'meshes': [], 'point_clouds': [], 'proxies': [_prism(
                [[0, 0], [20, 20], [20, 0], [0, 20]])]}}})
    assert created.status_code == 422


# OLDER VERSIONS (decision 8.123) -----------------------------------------------
def _violations_i3(db):
    from apps.catalog.invariants import Corpus, check_all
    corpus = Corpus(identities=list(db['component_identities'].find({})),
                    snapshots=list(db['component_snapshots'].find({})),
                    evidence=list(db['component_evidence'].find({})),
                    datasets=list(db['datasets'].find({})),
                    materials=list(db['materials'].find({})),
                    users=list(db['users'].find({})))
    return [v for v in check_all(corpus)
            if v.severity == 'error' and v.invariant in ('I3', 'I3b')]


def test_a_correction_of_v0_publishes_while_v1_stays_current(story):
    api, db = story['api'], story['db']
    c, m = story['contributor'], story['moderator']
    v0, v1 = sid('beam', 0), sid('beam', 1)
    assert _current(db) == v1
    correction = api.post(f'/snapshots/{v0}/supersede',
                          json={'geometry': story['geometry'],
                                'name': 'v0 corrected'}, headers=c)
    assert correction.status_code == 201, correction.text
    fixed = correction.json()['_id']
    assert correction.json()['version'] == 2        # the next number
    assert api.post(f'/snapshots/{fixed}/submit', headers=c).status_code == 200
    # both publish buttons send promote=1: the server ignores it here
    published = api.post(f'/snapshots/{fixed}/publish', params={'promote': 1},
                         headers=m)
    assert published.status_code == 200, published.text
    assert _snap(db, v0)['superseded_by'] == fixed
    assert _current(db) == v1                       # v1 was current, stays
    assert _violations_i3(db) == []
    # the timeline shows it as v0, which it corrects
    events = api.get(f'/identities/{BEAM}/timeline', headers=m).json()['events']
    shown = {e['record_id']: e for e in events if e['kind'] == 'snapshot'}
    assert shown[fixed]['version'] == 0 and shown[fixed]['corrects'] == v0
    assert shown[v0]['corrected'] is True and shown[v1]['version'] == 1


def test_a_correction_of_the_current_version_still_replaces_it(story):
    api, db = story['api'], story['db']
    c, m = story['contributor'], story['moderator']
    v1 = sid('beam', 1)
    fixed = api.post(f'/snapshots/{v1}/supersede',
                     json={'geometry': story['geometry']},
                     headers=c).json()['_id']
    api.post(f'/snapshots/{fixed}/submit', headers=c)
    api.post(f'/snapshots/{fixed}/publish', headers=m)       # no promote at all
    assert _current(db) == fixed
    assert _violations_i3(db) == []


def test_the_order_check_still_refuses_a_date_that_breaks_it(story):
    api, db = story['api'], story['db']
    m = story['moderator']
    v0, v1 = sid('beam', 0), sid('beam', 1)
    later = _snap(db, v1)['effective_from']
    broken = api.patch(f'/snapshots/{v0}', json={'effective_from': '2999-01-01T00:00:00Z'},
                       headers=m)
    assert broken.status_code == 409 and 'I3' in broken.text
    assert _snap(db, v1)['effective_from'] == later


def test_an_empty_capture_field_is_filled_once_by_a_moderator(story):
    api, db = story['api'], story['db']
    c, m = story['contributor'], story['moderator']
    v1 = sid('beam', 1)
    assert not (_snap(db, v1).get('capture') or {}).get('device')
    # a contributor may not; a moderator may, once
    assert api.patch(f'/snapshots/{v1}', json={'capture': {'device': 'Rig A'}},
                     headers=c).status_code == 403
    filled = api.patch(f'/snapshots/{v1}', json={'capture': {'device': 'Rig A'}},
                       headers=m)
    assert filled.status_code == 200, filled.text
    assert _snap(db, v1)['capture']['device'] == 'Rig A'
    # the change history records it
    log = list(db['change_log'].find({'record_id': v1}))
    assert any(ch['path'] == 'capture' and ch['new']['device'] == 'Rig A'
               for entry in log for ch in entry['changes'])
    # a set value is a correction, as before
    again = api.patch(f'/snapshots/{v1}', json={'capture': {'device': 'Rig B'}},
                      headers=m)
    assert again.status_code == 409 and 'supersede' in again.text
    assert _snap(db, v1)['capture']['device'] == 'Rig A'
    # notes stay editable; fragment and quantity stay frozen
    assert api.patch(f'/snapshots/{v1}', json={'capture': {'notes': 'n'}},
                     headers=m).status_code == 200
    assert api.patch(f'/snapshots/{v1}', json={'quantity': 2},
                     headers=m).status_code == 409
    assert api.patch(f'/snapshots/{v1}', json={'fragment': True},
                     headers=m).status_code == 409
    # another field, empty, can still be filled once
    assert api.patch(f'/snapshots/{v1}', json={'capture': {'software': 'Tool 1'}},
                     headers=m).status_code == 200


def test_the_pure_rules_of_the_fill_and_the_place():
    from apps.catalog.lifecycle import (
        chain_position,
        empty_capture_fields,
        patch_problems,
    )
    assert empty_capture_fields(None) == sorted(
        f'capture.{n}' for n in ('method', 'device', 'software', 'captured_at',
                                 'coordinate_system', 'markers', 'fixtures'))
    assert 'capture.device' not in empty_capture_fields({'device': 'x', 'markers': []})
    assert 'capture.markers' in empty_capture_fields({'device': 'x', 'markers': []})
    problems = patch_problems(
        'snapshot', {'capture': ['device', 'method']}, status='published',
        is_moderator=True, fillable=['capture.device'])
    assert problems == {'frozen': ['capture.method']}
    snaps = {'a': {'_id': 'a', 'version': 0, 'supersedes': None},
             'b': {'_id': 'b', 'version': 1, 'supersedes': None},
             'c': {'_id': 'c', 'version': 2, 'supersedes': 'a'},
             'd': {'_id': 'd', 'version': 3, 'supersedes': 'c'}}
    assert [chain_position(snaps[k], snaps) for k in 'abcd'] == [0, 1, 0, 0]


def test_photo_credit_is_mutable_metadata_never_frozen(story):
    """Decision 8.128 a: ``photo_credit`` is accepted on create and PATCH
    (author / moderator(D) before publish, moderator(D) after), returned on
    reads, and never frozen."""
    api, c, m = story['api'], story['contributor'], story['moderator']
    credit = {'text': 'Photo: (c) Example Catalogue (catalogue.example), retrieved '
                      '2026-10-05; for internal testing only',
              'url': 'https://catalogue.example/items/beam'}
    created = api.post(f'/identities/{BEAM}/snapshots', headers=c, json={
        'geometry': story['geometry'], 'photo_credit': credit})
    assert created.status_code == 201, created.text
    sid2 = created.json()['_id']
    assert created.json()['photo_credit'] == credit
    assert api.get(f'/snapshots/{sid2}', headers=c).json()[
        'photo_credit'] == credit
    # the url is optional; a blank one is none; only web addresses
    assert api.patch(f'/snapshots/{sid2}', headers=c, json={
        'photo_credit': {'text': ' Own photo ', 'url': ' '}}).json()[
        'photo_credit'] == {'text': 'Own photo', 'url': None}
    for bad in ({'text': ''}, {'text': 'x', 'url': 'javascript:alert(1)'},
                {'text': 'x', 'extra': 1}):
        assert api.patch(f'/snapshots/{sid2}', headers=c, json={
            'photo_credit': bad}).status_code == 422
    # another contributor cannot, the reviewer cannot
    assert api.patch(f'/snapshots/{sid2}', headers=story['reviewer'], json={
        'photo_credit': credit}).status_code == 403
    # pending: moderator(D) only (8.18)
    api.post(f'/snapshots/{sid2}/submit', headers=c)
    assert api.patch(f'/snapshots/{sid2}', headers=c, json={
        'photo_credit': credit}).status_code == 403
    assert api.patch(f'/snapshots/{sid2}', headers=m, json={
        'photo_credit': credit}).status_code == 200
    # published: moderator(D) still can (not 409, not frozen), a contributor cannot
    assert api.post(f'/snapshots/{sid2}/publish', headers=m,
                    params={'promote': 1}).status_code == 200
    assert api.patch(f'/snapshots/{sid2}', headers=c, json={
        'photo_credit': None}).status_code == 403
    changed = api.patch(f'/snapshots/{sid2}', headers=m, json={
        'photo_credit': {'text': 'Photo: archive', 'url': None}})
    assert changed.status_code == 200, changed.text
    assert changed.json()['photo_credit'] == {'text': 'Photo: archive',
                                              'url': None}
    cleared = api.patch(f'/snapshots/{sid2}', headers=m,
                        json={'photo_credit': None})
    assert cleared.status_code == 200 and cleared.json()['photo_credit'] is None
    from apps.catalog.lifecycle import patch_problems
    assert patch_problems('snapshot', {'photo_credit': []},
                          status='published', is_moderator=True) == {}
    assert patch_problems('snapshot', {'photo_credit': []},
                          status='published', is_author=True) == {
        'forbidden': ['photo_credit']}
