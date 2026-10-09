"""
In place, deinstall, batches and draws, documents (data model spec 3.1.6,
4.1, I6, I18, I31, I32; decisions 8.104 -- 8.107, 8.110; plan P9) on the real
routes, over the migrated test catalog.
"""

from __future__ import annotations

import pytest

from apps.catalog.invariants import Corpus, check_all
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import claim_body
from support import iid, seed_05_catalog

BEAM = iid('beam')
P9_INVARIANTS = {'I6', 'I16', 'I17', 'I18', 'I31', 'I32'}
FRAME = {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}
BOX = {'primitive': 'box', 'role': 'primary', 'params': {'size': [2, 1, 1]},
       'placement': FRAME, 'fit': {'method': 'authored'}}
WORKS = {'name': 'Hall 7', 'use': 'warehouse', 'year_built': 1998}


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, contributor_id = member_headers(
        {'dbu_zirkus': ['contributor']})
    moderator, moderator_id = member_headers(
        {'dbu_zirkus': ['moderator', 'contributor']})
    other, other_id = member_headers({'dbu_zirkus': ['contributor']})
    material = db['component_identities'].find_one({'_id': BEAM})['material']
    return {'api': api, 'db': db, 'c': contributor, 'cid': contributor_id,
            'm': moderator, 'mid': moderator_id, 'o': other, 'oid': other_id,
            'admin': auth_headers('admin'), 'material': material}


def _violations(db):
    corpus = Corpus(identities=list(db['component_identities'].find({})),
                    snapshots=list(db['component_snapshots'].find({})),
                    evidence=list(db['component_evidence'].find({})),
                    datasets=list(db['datasets'].find({})),
                    materials=list(db['materials'].find({})),
                    users=list(db['users'].find({})))
    return [v for v in check_all(corpus)
            if v.severity == 'error' and v.invariant in P9_INVARIANTS]


def _identity(db, identity_id):
    return db['component_identities'].find_one({'_id': identity_id})


def _publish(w, created, author=None):
    sid = created['snapshot']['_id']
    submitted = w['api'].post(f'/snapshots/{sid}/submit',
                              headers=author or w['c'])
    assert submitted.status_code == 200, submitted.text
    published = w['api'].post(f'/snapshots/{sid}/publish?promote=1',
                              headers=w['m'])
    assert published.status_code == 200, published.text
    return published.json()


def _new(w, *, planned=True, quantity=1, origin=None, snapshot=None,
         headers=None, **fields):
    """A root piece, in place by default, with an authored box."""
    body = {
        'dataset': 'dbu_zirkus', 'original_function': 'IfcWall',
        'material': w['material'],
        'origin': {'kind': 'deinstallation', 'planned': planned,
                   'construction_work': WORKS, **(origin or {})},
        'snapshot': {'geometry': {'proxies': [BOX]}, 'quantity': quantity,
                     **(snapshot or {})},
        **fields}
    return w['api'].post('/identities', json=body,
                         headers=headers or w['c'])


def _published(w, **kw):
    created = _new(w, **kw)
    assert created.status_code == 201, created.text
    created = created.json()
    _publish(w, created)
    return created['identity']['_id']


def _draw(w, batch_id, quantity=1, headers=None, **snapshot):
    return w['api'].post('/identities', json={
        'dataset': 'dbu_zirkus', 'parent_identities': [batch_id],
        'snapshot': {'quantity': quantity, **snapshot}},
        headers=headers or w['c'])


def _remaining(w, batch_id):
    got = w['api'].get(f'/identities/{batch_id}',
                       params={'expand': 'none'}, headers=w['m'])
    assert got.status_code == 200, got.text
    return got.json().get('remaining')


# IN PLACE (8.104) ------------------------------------------------------------
def test_a_planned_origin_needs_a_deinstallation_or_demolition(world):
    bad = _new(world, origin={'kind': 'offcut', 'construction_work': None})
    assert bad.status_code == 422
    assert 'I31' in bad.text
    assert _new(world, origin={'kind': 'demolition'}).status_code == 201


def test_an_in_place_piece_starts_at_its_survey_date_and_is_listed(world):
    api, db = world['api'], world['db']
    created = _new(world, origin={'at': '2031-05-01T00:00:00Z',
                                  'at_precision': 'month'})
    assert created.status_code == 201, created.text
    created = created.json()
    assert created['identity']['origin']['planned'] is True
    # not the planned date (8.10's default does not hold for in place)
    assert created['snapshot']['effective_from'] != '2031-05-01T00:00:00Z'
    in_place = created['identity']['_id']
    _publish(world, created)
    done = _published(world, planned=False,
                      origin={'at': '2020-01-01T00:00:00Z'})
    # the default read lists both; the sub-values split them

    def ids(circulation):
        rows = api.get('/identities', params={'circulation': circulation},
                       headers=world['m']).json()
        return {r['_id'] for r in rows}
    assert {in_place, done} <= ids('active')
    assert in_place in ids('in_place') and done not in ids('in_place')
    assert done in ids('deinstalled') and in_place not in ids('deinstalled')
    assert in_place not in ids('exited')
    # the timeline marks the planned origin
    events = api.get(f'/identities/{in_place}/timeline',
                     headers=world['m']).json()['events']
    assert [e['planned'] for e in events if e['kind'] == 'origin'] == [True]
    assert _violations(db) == []


def test_deinstall_and_undo(world):
    api, db = world['api'], world['db']
    piece = _published(world)
    reserved = api.post(f'/identities/{piece}/reserve', headers=world['o'])
    assert reserved.status_code == 200, reserved.text
    body = {'at': '2030-09-01T00:00:00Z', 'at_precision': 'day',
            'method': 'unscrewed', 'kind': 'demolition',
            'performed_by': [{'kind': 'organization',
                              'organization': 'Example Reuse Ltd',
                              'role': 'operator'}]}
    assert api.post(f'/identities/{piece}/deinstall', json=body,
                    headers=world['c']).status_code == 403
    done = api.post(f'/identities/{piece}/deinstall', json=body,
                    headers=world['m'])
    assert done.status_code == 200, done.text
    origin = done.json()['origin']
    assert origin['planned'] is False and origin['kind'] == 'demolition'
    assert origin['at'] == body['at'] and origin['method'] == 'unscrewed'
    assert origin['construction_work']['name'] == 'Hall 7'
    assert done.json()['reserved'] == world['oid']          # survives
    assert db['change_log'].find_one({'record_id': piece,
                                      'cause': 'deinstall'})
    again = api.post(f'/identities/{piece}/deinstall', json=body,
                     headers=world['m'])
    assert again.status_code == 409
    # no state or evidence after the act: undo works
    undone = api.post(f'/identities/{piece}/undo-deinstall',
                      headers=world['m'])
    assert undone.status_code == 200, undone.text
    assert undone.json()['origin']['planned'] is True
    assert db['change_log'].find_one({'record_id': piece,
                                      'cause': 'undo_deinstall'})
    # a state after the act: too late
    assert api.post(f'/identities/{piece}/deinstall', json=body,
                    headers=world['m']).status_code == 200
    state = api.post(f'/identities/{piece}/snapshots', json={
        'geometry': {'proxies': [BOX]},
        'effective_from': '2031-01-01T00:00:00Z'}, headers=world['m'])
    assert state.status_code == 201, state.text
    late = api.post(f'/identities/{piece}/undo-deinstall',
                    headers=world['m'])
    assert late.status_code == 409 and 'Too late' in late.json()['detail']
    assert _violations(db) == []


def test_undo_stops_at_dated_evidence(world):
    api = world['api']
    piece = _published(world)
    assert api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-09-01T00:00:00Z'}, headers=world['m']
    ).status_code == 200
    record = api.post(f'/identities/{piece}/evidence', json=claim_body(
        observed_at='2030-11-01T00:00:00Z'), headers=world['c'])
    assert record.status_code == 201, record.text
    late = api.post(f'/identities/{piece}/undo-deinstall',
                    headers=world['m'])
    assert late.status_code == 409 and 'evidence' in late.json()['detail']


def test_deinstalling_a_parent_reaches_the_children_that_inherit(world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=6)
    follower = _draw(world, batch, 2).json()
    _publish(world, follower)
    own = _draw(world, batch, 2).json()
    _publish(world, own)
    own_id = own['identity']['_id']
    # one piece is deinstalled on its own and keeps that origin
    assert api.post(f'/identities/{own_id}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m']).status_code == 200
    assert 'origin' not in _identity(db, own_id)['inherited_fields']
    done = api.post(f'/identities/{batch}/deinstall', json={
        'at': '2030-09-01T00:00:00Z', 'at_precision': 'day'},
        headers=world['m'])
    assert done.status_code == 200, done.text
    followed = _identity(db, follower['identity']['_id'])['origin']
    assert followed['planned'] is False
    assert followed['at'] == '2030-09-01T00:00:00Z'
    assert _identity(db, own_id)['origin']['at'] == '2030-01-01T00:00:00Z'
    assert db['change_log'].find_one({
        'record_id': follower['identity']['_id'],
        'cause': 'inherited_from_parent'})
    # undo reaches the same children
    assert api.post(f'/identities/{batch}/undo-deinstall',
                    headers=world['m']).status_code == 200
    assert _identity(db, follower['identity']['_id'])['origin'][
        'planned'] is True
    assert _violations(db) == []


def test_exits_from_in_place(world):
    api, db = world['api'], world['db']
    piece = _published(world)
    for kind in ('installed', 'returned'):
        refused = api.post(f'/identities/{piece}/exit', json={
            'kind': kind, 'at': '2026-09-01T00:00:00Z'}, headers=world['m'])
        assert refused.status_code == 409, kind
        assert 'in place' in refused.json()['detail']
    reserved = api.post(f'/identities/{piece}/reserve', headers=world['o'])
    assert reserved.status_code == 200
    lost = api.post(f'/identities/{piece}/exit', json={
        'kind': 'lost', 'at': '2026-09-01T00:00:00Z'}, headers=world['m'])
    assert lost.status_code == 200, lost.text
    assert lost.json()['reserved'] == ''
    assert api.post(f'/identities/{piece}/deinstall', json={
        'at': '2026-09-01T00:00:00Z'}, headers=world['m']
    ).status_code == 409
    recycled = _published(world)
    assert api.post(f'/identities/{recycled}/exit', json={
        'kind': 'recycled', 'at': '2026-09-01T00:00:00Z'},
        headers=world['m']).status_code == 200
    assert _violations(db) == []


# DOCUMENTS, STEEL GRADE, VOCABULARY (8.106, 8.107) ---------------------------
def _document(**document):
    return {'method': 'archival_document',
            'observed_at': '2022-03-01T00:00:00Z',
            'payload': {'document': {'title': 'Profile drawing',
                                     'kind': 'drawing', **document}}}


def test_a_document_has_no_result_and_stays_out_of_the_fold(world):
    api, db = world['api'], world['db']
    before = _identity(db, BEAM).get('properties')
    made = api.post(f'/identities/{BEAM}/evidence', json=_document(
        url='https://example.org/files/profile.pdf',
        retrieved_at='2026-10-05'), headers=world['c'])
    assert made.status_code == 201, made.text
    record = made.json()
    assert record['summary'] is None
    assert record['payload']['document']['url'] == \
        'https://example.org/files/profile.pdf'
    assert record['payload']['document']['retrieved_at'] == '2026-10-05'
    assert _identity(db, BEAM).get('properties') == before
    # a record of another method still needs its result (I6)
    visual = api.post(f'/identities/{BEAM}/evidence', json={
        'method': 'rebound_hammer', 'observed_at': '2022-03-01T00:00:00Z',
        'payload': {}}, headers=world['c'])
    assert visual.status_code == 422
    assert _violations(db) == []


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'ftp://x.org/a',
                                 'https://', '/relative/path',
                                 'https://exa mple.org/a'])
def test_a_document_link_is_http_or_https(world, url):
    refused = world['api'].post(f'/identities/{BEAM}/evidence',
                                json=_document(url=url), headers=world['c'])
    assert refused.status_code == 422, url


def test_a_layout_cites_a_file_by_url(world):
    api, db = world['api'], world['db']
    snapshot = db['component_snapshots'].find_one({'identity_id': BEAM})
    body = {'method': 'reinforcement_layout',
            'observed_at': '2022-03-01T00:00:00Z',
            'position': {'kind': 'none', 'snapshot_id': snapshot['_id'],
                         'description': 'bar centrelines'},
            'payload': {'basis': 'drawing',
                        'document': {'title': 'Layout',
                                     'url': 'http://example.org/layout.dwg',
                                     'retrieved_at': '2026-10-05'},
                        'bars': [{'spec': 'BSt III', 'diameter_mm': 12,
                                  'points': [[0, 0, 20], [6000, 0, 20]]}]}}
    made = api.post(f'/identities/{BEAM}/evidence', json=body,
                    headers=world['c'])
    assert made.status_code == 201, made.text
    document = made.json()['payload']['document']
    assert document['url'] == 'http://example.org/layout.dwg'
    assert document['retrieved_at'] == '2026-10-05'


def test_steel_grade_and_the_new_functions_come_with_the_vocabulary(world):
    api = world['api']
    vocab = api.get('/vocab').json()
    functions = {e['value'] for e in vocab['original_function']}
    assert {'IfcWindow', 'IfcDoor', 'IfcStair', 'IfcRailing',
            'IfcDuctSegment'} <= functions
    assert {'value': 'IfcStair', 'label': 'composite'} in \
        vocab['shape_class_hint']
    assert {'value': 'IfcDuctSegment', 'label': 'linear'} in \
        vocab['shape_class_hint']
    assert 'steel_grade' in {e['value'] for e in vocab['quantity']}
    claim = api.post(f'/identities/{BEAM}/evidence', json={
        'method': 'archival_document', 'observed_at': '2022-03-01T00:00:00Z',
        'payload': {'document': {'title': 'IFC reuse property set',
                                 'kind': 'other'}},
        'summary': {'quantity': 'steel_grade', 'value': 'S355',
                    'kind': 'claimed'}}, headers=world['c'])
    assert claim.status_code == 201, claim.text
    wrong = api.post(f'/identities/{BEAM}/evidence', json={
        'method': 'archival_document', 'observed_at': '2022-03-01T00:00:00Z',
        'payload': {'document': {'title': 'IFC', 'kind': 'other'}},
        'summary': {'quantity': 'steel_grade', 'value': 'S999',
                    'kind': 'claimed'}}, headers=world['c'])
    assert wrong.status_code == 422


# BATCHES AND DRAWS (8.105, 8.110) --------------------------------------------
def test_a_draw_takes_pieces_and_the_batch_runs_out(world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=10)
    assert _remaining(world, batch) == 10

    drawn = _draw(world, batch, 3)
    assert drawn.status_code == 201, drawn.text
    child = drawn.json()
    # the batch's authored proxy and its in-place origin come along
    assert child['snapshot']['geometry']['proxies'][0]['primitive'] == 'box'
    assert child['identity']['origin']['planned'] is True
    assert 'origin' in child['identity']['inherited_fields']
    assert _remaining(world, batch) == 10        # a draft draws nothing yet
    over = _draw(world, batch, 11)
    assert over.status_code == 409 and 'Only 10 of 10' in over.json()['detail']

    _publish(world, child)
    assert _remaining(world, batch) == 7
    assert _identity(db, batch)['exit'] is None
    compose = api.get(f'/identities/{batch}/compose', headers=world['m'])
    assert compose.json()['identity']['remaining'] == 7

    second = _draw(world, batch, 7).json()
    _publish(world, second)
    drawn_out = _identity(db, batch)
    assert _remaining(world, batch) == 0
    assert drawn_out['exit']['kind'] == 'split'
    assert drawn_out['exit']['recorded_by_user_id'] is None
    last = db['component_snapshots'].find_one(
        {'identity_id': second['identity']['_id']})
    assert drawn_out['exit']['at'] == last['effective_from']
    assert _draw(world, batch, 1).status_code == 409
    assert _violations(db) == []

    # withdrawing the last draw brings the pieces back and ends the split
    withdrawn = api.post(f"/identities/{second['identity']['_id']}/withdraw",
                         json={'reason': 'drawn by mistake'},
                         headers=world['m'])
    assert withdrawn.status_code == 200, withdrawn.text
    assert _identity(db, batch)['exit'] is None
    assert _remaining(world, batch) == 7
    assert _violations(db) == []


def test_the_remaining_check_holds_at_publish(world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=10)
    first = _draw(world, batch, 6)
    second = _draw(world, batch, 6)
    assert first.status_code == 201 and second.status_code == 201
    _publish(world, first.json())
    sid = second.json()['snapshot']['_id']
    assert api.post(f'/snapshots/{sid}/submit',
                    headers=world['c']).status_code == 200
    refused = api.post(f'/snapshots/{sid}/publish', headers=world['m'])
    assert refused.status_code == 409, refused.text
    assert db['component_snapshots'].find_one({'_id': sid})['status'] \
        == 'pending'
    assert _remaining(world, batch) == 4
    assert _violations(db) == []


def test_a_draw_changes_the_etag_of_the_batch(world):
    api = world['api']
    batch = _published(world, quantity=4)
    first = api.get(f'/identities/{batch}/compose', headers=world['m'])
    etag = first.headers['etag']
    assert api.get(f'/identities/{batch}/compose', headers={
        **world['m'], 'If-None-Match': etag}).status_code == 304
    _publish(world, _draw(world, batch, 1).json())
    after = api.get(f'/identities/{batch}/compose',
                    headers={**world['m'], 'If-None-Match': etag})
    assert after.status_code == 200
    assert after.json()['identity']['remaining'] == 3


def test_a_reserved_batch_is_drawn_by_its_holder_or_a_moderator(world):
    api = world['api']
    batch = _published(world, quantity=5)
    assert api.post(f'/identities/{batch}/reserve',
                    headers=world['o']).status_code == 200
    refused = _draw(world, batch, 1, headers=world['c'])
    assert refused.status_code == 409
    assert 'reserved' in refused.json()['detail']
    assert _draw(world, batch, 1, headers=world['o']).status_code == 201
    assert _draw(world, batch, 1, headers=world['m']).status_code == 201
    # a draw does not clear the reservation
    _publish(world, _draw(world, batch, 1, headers=world['o']).json(),
             author=world['o'])
    assert api.get(f'/identities/{batch}', params={'expand': 'none'},
                   headers=world['m']).json()['reserved'] == world['oid']


def test_a_merge_never_takes_a_batch(world):
    batch = _published(world, quantity=5)
    other = _published(world, quantity=1)
    merge = world['api'].post('/identities', json={
        'dataset': 'dbu_zirkus', 'parent_identities': [batch, other],
        'original_function': 'IfcWall', 'material': world['material'],
        'snapshot': {'geometry': {'proxies': [BOX]}}}, headers=world['c'])
    assert merge.status_code == 409, merge.text
    assert 'batch' in merge.json()['detail']


def test_a_batch_keeps_its_quantity_and_a_correction_stays_above_the_draws(
        world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=10)
    _publish(world, _draw(world, batch, 4).json())
    geometry = {'proxies': [BOX]}
    state = api.post(f'/identities/{batch}/snapshots', json={
        'geometry': geometry, 'quantity': 5}, headers=world['m'])
    assert state.status_code == 422 and 'I32' in state.json()['detail']
    state = api.post(f'/identities/{batch}/snapshots', json={
        'geometry': geometry}, headers=world['m'])
    assert state.status_code == 201, state.text
    assert state.json()['quantity'] == 10         # kept, not reset to 1
    sid = state.json()['_id']
    assert api.post(f'/snapshots/{sid}/submit',
                    headers=world['m']).status_code == 200
    assert api.post(f'/snapshots/{sid}/publish',
                    headers=world['m']).status_code == 200

    v0 = db['component_snapshots'].find_one({'identity_id': batch,
                                             'version': 0})
    below = api.post(f'/snapshots/{v0["_id"]}/supersede', json={
        'geometry': geometry, 'quantity': 3}, headers=world['m'])
    assert below.status_code == 409 and 'I32' in below.json()['detail']
    # a correction that omits the quantity keeps it
    same = api.post(f'/snapshots/{v0["_id"]}/supersede', json={
        'geometry': geometry}, headers=world['m'])
    assert same.status_code == 201 and same.json()['quantity'] == 10
    # another state would disagree with a new quantity
    assert api.post(f"/snapshots/{same.json()['_id']}/submit",
                    headers=world['m']).status_code == 200
    assert _violations(db) == []


def test_a_batch_corrected_down_to_what_was_drawn_is_drawn_out(world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=10)
    _publish(world, _draw(world, batch, 4).json())
    v0 = db['component_snapshots'].find_one({'identity_id': batch,
                                             'version': 0})
    ok = api.post(f'/snapshots/{v0["_id"]}/supersede', json={
        'geometry': {'proxies': [BOX]}, 'quantity': 4}, headers=world['m'])
    assert ok.status_code == 201, ok.text
    sid = ok.json()['_id']
    assert api.post(f'/snapshots/{sid}/submit',
                    headers=world['m']).status_code == 200
    assert api.post(f'/snapshots/{sid}/publish',
                    headers=world['m']).status_code == 200
    assert _remaining(world, batch) == 0
    assert _identity(db, batch)['exit']['kind'] == 'split'
    assert _violations(db) == []


def test_a_draw_copies_nothing_but_the_proxy_unless_it_brings_geometry(world):
    batch = _published(world, quantity=3)
    mine = {'proxies': [{**BOX, 'params': {'size': [1, 1, 1]}}]}
    drawn = _draw(world, batch, 1, geometry=mine)
    assert drawn.status_code == 201, drawn.text
    assert drawn.json()['snapshot']['geometry']['proxies'][0]['params'][
        'size'] == [1, 1, 1]
    # no evidence is copied: the child starts clean
    child = drawn.json()['identity']['_id']
    assert world['db']['component_evidence'].count_documents(
        {'identity_id': child}) == 0


# REVIEW FIXES (8.115) --------------------------------------------------------
TETRA = {'vertices': [[0, 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100]],
         'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}


def test_undo_takes_back_the_act_only(world):
    api, db = world['api'], world['db']
    # a deinstalled piece without a date: set the date first
    undated = _published(world, planned=False)
    refused = api.post(f'/identities/{undated}/undo-deinstall',
                       headers=world['m'])
    assert refused.status_code == 409 and 'date' in refused.json()['detail']
    # a deinstalled origin that was never the act (set at create, or by PATCH)
    hand_set = _published(world, planned=False,
                          origin={'at': '2030-01-01T00:00:00Z'})
    refused = api.post(f'/identities/{hand_set}/undo-deinstall',
                       headers=world['m'])
    assert refused.status_code == 409 and 'act' in refused.json()['detail']
    api.patch(f'/identities/{hand_set}', json={'origin': {
        'kind': 'deinstallation', 'planned': False,
        'at': '2030-02-01T00:00:00Z', 'at_precision': 'day'}},
        headers=world['m'])
    assert api.post(f'/identities/{hand_set}/undo-deinstall',
                    headers=world['m']).status_code == 409
    # the act, then another origin change: no longer the latest
    piece = _published(world)
    assert api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m']).status_code == 200
    api.patch(f'/identities/{piece}', json={'origin': {
        'kind': 'deinstallation', 'planned': False, 'at': '2030-01-02T00:00:00Z',
        'at_precision': 'day'}}, headers=world['m'])
    assert api.post(f'/identities/{piece}/undo-deinstall',
                    headers=world['m']).status_code == 409
    # the normal case: the act, then its undo
    fresh = _published(world)
    assert api.post(f'/identities/{fresh}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m']).status_code == 200
    assert api.post(f'/identities/{fresh}/undo-deinstall',
                    headers=world['m']).status_code == 200
    assert _identity(db, fresh)['origin']['planned'] is True


def test_the_timeline_shows_the_act_and_loses_it_with_the_undo(world):
    api = world['api']
    piece = _published(world)

    def kinds():
        events = api.get(f'/identities/{piece}/timeline',
                         headers=world['m']).json()['events']
        return [(e['kind'], e.get('at')) for e in events
                if e['kind'] == 'deinstalled']

    assert kinds() == []
    api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-03-01T00:00:00Z'}, headers=world['m'])
    assert kinds() == [('deinstalled', '2030-03-01T00:00:00Z')]
    api.post(f'/identities/{piece}/undo-deinstall', headers=world['m'])
    assert kinds() == []


def test_a_draw_with_a_bad_quantity_or_nothing_to_copy_is_422(world):
    batch = _published(world, quantity=5)
    for bad in (2.5, 'x', 0, None):
        refused = _draw(world, batch, bad)
        assert refused.status_code == 422, (bad, refused.text)
    # a batch of meshes only has no authored proxy to copy
    meshed = _published(world, quantity=4, snapshot={
        'geometry': {'meshes': [TETRA]}})
    refused = _draw(world, meshed, 1)
    assert refused.status_code == 422
    assert 'no authored proxy' in refused.text
    given = _draw(world, meshed, 1, geometry={'proxies': [BOX]})
    assert given.status_code == 201, given.text


def test_every_identity_keeps_its_quantity_in_later_states(world):
    api, db = world['api'], world['db']
    batch = _published(world, quantity=10)
    drawn = _draw(world, batch, 1).json()
    _publish(world, drawn)
    child = drawn['identity']['_id']
    refused = api.post(f'/identities/{child}/snapshots', json={
        'geometry': {'proxies': [BOX]}, 'quantity': 5}, headers=world['m'])
    assert refused.status_code == 422 and 'I32' in refused.json()['detail']
    kept = api.post(f'/identities/{child}/snapshots', json={
        'geometry': {'proxies': [BOX]}}, headers=world['m'])
    assert kept.status_code == 201 and kept.json()['quantity'] == 1
    # a correction may change it only while it is the sole live state
    v0 = db['component_snapshots'].find_one({'identity_id': child,
                                             'version': 0})
    assert api.post(f"/snapshots/{kept.json()['_id']}/submit",
                    headers=world['m']).status_code == 200
    assert api.post(f"/snapshots/{kept.json()['_id']}/publish",
                    headers=world['m']).status_code == 200
    again = api.post(f'/snapshots/{v0["_id"]}/supersede', json={
        'geometry': {'proxies': [BOX]}, 'quantity': 2}, headers=world['m'])
    assert again.status_code == 409
    assert _violations(db) == []


def test_the_lock_table_is_empty_after_a_publish(world):
    from apps.catalog.api import batches
    batch = _published(world, quantity=3)
    _publish(world, _draw(world, batch, 1).json())
    assert batches._LOCKS == {}


def _can_undo(w, identity_id):
    got = w['api'].get(f'/identities/{identity_id}/compose', headers=w['m'])
    assert got.status_code == 200, got.text
    return got.json()['identity']['can_undo_deinstall'], got.headers['etag']


def test_the_passport_says_whether_the_undo_is_open(world):
    api = world['api']
    piece = _published(world)
    assert _can_undo(world, piece)[0] is False            # in place: nothing to undo
    assert api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m']).status_code == 200
    can, etag = _can_undo(world, piece)
    assert can is True                                    # the act, nothing after it
    one = api.get(f'/identities/{piece}', params={'expand': 'none'},
                  headers=world['m'])
    assert one.json()['can_undo_deinstall'] is True
    # a record dated after the deinstallation closes it, and the ETag moves
    made = api.post(f'/identities/{piece}/evidence', json=_document(
        url='https://example.org/later.pdf', retrieved_at='2031-01-02',
    ) | {'observed_at': '2031-01-01T00:00:00Z'}, headers=world['c'])
    assert made.status_code == 201, made.text
    after, etag_after = _can_undo(world, piece)
    assert after is False and etag_after != etag
    # the answer is the route's: the undo is refused too
    assert api.post(f'/identities/{piece}/undo-deinstall',
                    headers=world['m']).status_code == 409


def test_an_origin_that_was_not_the_act_has_no_undo(world):
    api = world['api']
    hand_set = _published(world, planned=False,
                          origin={'at': '2030-01-01T00:00:00Z'})
    assert _can_undo(world, hand_set)[0] is False         # never the act
    undated = _published(world, planned=False)
    assert _can_undo(world, undated)[0] is False          # no date
    piece = _published(world)
    api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m'])
    assert _can_undo(world, piece)[0] is True
    api.patch(f'/identities/{piece}', json={'origin': {
        'kind': 'deinstallation', 'planned': False, 'at': '2030-01-02T00:00:00Z',
        'at_precision': 'day'}}, headers=world['m'])
    assert _can_undo(world, piece)[0] is False            # another origin change since
    # the undo itself puts it back in place: nothing left to undo
    fresh = _published(world)
    api.post(f'/identities/{fresh}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m'])
    assert api.post(f'/identities/{fresh}/undo-deinstall',
                    headers=world['m']).status_code == 200
    assert _can_undo(world, fresh)[0] is False


def test_only_a_moderator_or_an_admin_is_asked_about_the_undo(world, monkeypatch):
    api = world['api']
    piece = _published(world)
    api.post(f'/identities/{piece}/deinstall', json={
        'at': '2030-01-01T00:00:00Z'}, headers=world['m'])
    from apps.catalog.api import identity_edit
    asked = []
    real = identity_edit.undo_deinstall_refusal

    async def spy(request, identity):
        asked.append(identity['_id'])
        return await real(request, identity)
    monkeypatch.setattr(identity_edit, 'undo_deinstall_refusal', spy)

    def flag(headers):
        got = api.get(f'/identities/{piece}/compose', headers=headers)
        assert got.status_code == 200, got.text
        return got.json()['identity']['can_undo_deinstall'], got.headers['etag']

    can_c, etag_c = flag(world['c'])
    assert can_c is False and asked == []                 # a contributor: no lookup
    one = api.get(f'/identities/{piece}', params={'expand': 'none'},
                  headers=world['c'])
    assert one.json()['can_undo_deinstall'] is False and asked == []
    can_m, etag_m = flag(world['m'])
    assert can_m is True and len(asked) == 1              # the moderator: asked, true
    assert flag(world['admin'])[0] is True                # an admin holds every role
    # the flag enters the ETag only when true: the contributor's ETag is
    # what it was without the flag, the moderator's differs
    assert etag_c != etag_m
