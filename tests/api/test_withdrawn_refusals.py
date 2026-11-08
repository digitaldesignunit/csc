"""
A withdrawn element stays out of circulation (decision 8.190, #49): the
backend refuses reserve, re-enter, undo exit, undo deinstall, a new photo on a
withdrawn version or on any version of a withdrawn element, and a new
attachment on a withdrawn record, a correction of a version, and the submit, publish, promote and reinstate of a version, the
reinstate of an evidence record and a withdrawal with a replacement, with a 409 --- for a site admin as well, since it is the state that refuses.
Recall, reject, back to draft and delete stay. Removing a photo or an attachment and
editing a text stay as they are.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import PDF, claim_body, png_bytes
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
V1 = sid('beam', 1)
WITHDRAWN = 'The component is withdrawn.'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, contributor_id = member_headers(
        {'dbu_zirkus': ['contributor']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': contributor, 'cid': contributor_id,
            'm': moderator, 'admin': auth_headers('admin'),
            'user': auth_headers('user')}


def _withdraw(w):
    done = w['api'].post(f'/identities/{BEAM}/withdraw',
                         json={'reason': 'test'}, headers=w['m'])
    assert done.status_code == 200, done.text


def _reinstate(w):
    done = w['api'].post(f'/identities/{BEAM}/reinstate', headers=w['m'])
    assert done.status_code == 200, done.text


def _photo(w, headers, snapshot=V1):
    return w['api'].put(f'/snapshots/{snapshot}/photos/0',
                        files={'photo': ('p.png', png_bytes(), 'image/png')},
                        headers=headers)


def _refused(response):
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == WITHDRAWN


# CIRCULATION -----------------------------------------------------------------
def test_reserve_answers_409_on_a_withdrawn_element(world):
    w, api = world, world['api']
    _withdraw(w)
    for who in ('c', 'm', 'admin'):
        _refused(api.post(f'/identities/{BEAM}/reserve', headers=w[who]))
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM})['reserved'] == ''
    # a caller who cannot read the element learns nothing of its state
    assert api.post(f'/identities/{BEAM}/reserve',
                    headers=w['user']).status_code == 403
    _reinstate(w)
    assert api.post(f'/identities/{BEAM}/reserve',
                    headers=w['c']).status_code == 200


def test_undo_exit_and_re_enter_answer_409_on_a_withdrawn_element(world):
    w, api = world, world['api']
    assert api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'},
        headers=w['m']).status_code == 200
    _withdraw(w)
    again = {'origin': {'kind': 'deinstallation',
                        'at': '2026-10-01T00:00:00Z', 'at_precision': 'day'}}
    for who in ('m', 'admin'):
        _refused(api.delete(f'/identities/{BEAM}/exit', headers=w[who]))
        _refused(api.post(f'/identities/{BEAM}/reenter', json=again,
                          headers=w[who]))
    # the permission comes first: a contributor is refused, not told the state
    assert api.delete(f'/identities/{BEAM}/exit',
                      headers=w['c']).status_code == 403
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM})['exit']['kind'] == 'installed'
    _reinstate(w)
    assert api.post(f'/identities/{BEAM}/reenter', json=again,
                    headers=w['m']).status_code == 200


def test_undo_deinstall_answers_409_on_a_withdrawn_element(world):
    w, api = world, world['api']
    # an in-place element that was deinstalled, then withdrawn
    w['db']['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'origin': {'kind': 'deinstallation', 'planned': True,
                   'at': '2026-01-01T00:00:00Z', 'at_precision': 'day'}}})
    deinstall = {'at': '2026-09-01T00:00:00Z'}
    assert api.post(f'/identities/{BEAM}/deinstall', json=deinstall,
                    headers=w['m']).status_code == 200
    _withdraw(w)
    for who in ('m', 'admin'):
        _refused(api.post(f'/identities/{BEAM}/undo-deinstall',
                          headers=w[who]))
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM})['origin']['planned'] is False
    # the passport does not offer the undo of a withdrawn element
    _reinstate(w)
    passport = api.get(f'/identities/{BEAM}/compose', headers=w['m']).json()
    assert passport['identity']['can_undo_deinstall'] is True
    _withdraw(w)
    passport = api.get(f'/identities/{BEAM}/compose', headers=w['m']).json()
    assert not passport['identity'].get('can_undo_deinstall')


# PHOTOS AND ATTACHMENTS ------------------------------------------------------
def test_a_photo_is_refused_on_any_version_of_a_withdrawn_element(world):
    w = world
    assert _photo(w, w['c']).status_code == 200      # baseline: published
    _withdraw(w)
    for who in ('c', 'm', 'admin'):
        _refused(_photo(w, w[who]))
    # nobody who may not add one learns the state
    assert _photo(w, w['user']).status_code == 403
    # removing stays as it is: a moderator removes
    assert w['api'].delete(f'/snapshots/{V1}/photos/0',
                           headers=w['m']).status_code in (200, 204)
    _reinstate(w)
    assert _photo(w, w['c']).status_code == 200


def test_a_photo_is_refused_on_a_withdrawn_version(world):
    w, api = world, world['api']
    # v0 of the beam is published and no longer current: withdraw it alone
    v0 = sid('beam', 0)
    done = api.post(f'/snapshots/{v0}/withdraw', json={'reason': 'wrong scan'},
                    headers=w['m'])
    assert done.status_code == 200, done.text
    for who in ('c', 'm', 'admin'):
        refused = _photo(w, w[who], snapshot=v0)
        assert refused.status_code == 409, refused.text
        assert refused.json()['detail'] == 'This snapshot is withdrawn.'
    # the other version of the same, not withdrawn element still takes one
    assert _photo(w, w['c']).status_code == 200


def test_an_attachment_is_refused_on_a_withdrawn_record(world):
    w, api = world, world['api']
    created = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                       headers=w['c'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    assert api.post(f'/evidence/{eid}/submit', headers=w['c']).status_code == 200
    assert api.post(f'/evidence/{eid}/publish',
                    headers=w['m']).status_code == 200

    def attach(headers, data=PDF):
        return api.post('/evidence/attachments', data={'record_ids': [eid]},
                        files={'file': ('a.pdf', data, 'application/pdf')},
                        headers=headers)
    assert attach(w['c']).status_code == 201
    assert api.post(f'/evidence/{eid}/withdraw', json={'reason': 'x'},
                    headers=w['m']).status_code == 200
    for who, data in (('c', PDF + b'1'), ('m', PDF + b'2'),
                      ('admin', PDF + b'3')):
        refused = attach(w[who], data)
        assert refused.status_code == 409, (who, refused.text)
        assert 'withdrawn' in refused.json()['detail']
    # removing stays: a moderator takes the file out, with a reason
    removed = api.delete(f'/evidence/{eid}/attachments/0',
                         params={'reason': 'wrong file'}, headers=w['m'])
    assert removed.status_code == 200, removed.text


def test_a_text_edit_of_a_withdrawn_version_stays_allowed(world):
    w, api = world, world['api']
    _withdraw(w)
    edit = api.patch(f'/snapshots/{V1}', json={'name': 'Typo fixed'},
                     headers=w['m'])
    assert edit.status_code == 200, edit.text


def test_an_attachment_is_refused_on_any_record_of_a_withdrawn_element(world):
    w, api = world, world['api']
    published = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                         headers=w['c']).json()['_id']
    assert api.post(f'/evidence/{published}/submit',
                    headers=w['c']).status_code == 200
    assert api.post(f'/evidence/{published}/publish',
                    headers=w['m']).status_code == 200
    draft = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                     headers=w['c']).json()['_id']

    def attach(eid, headers, data):
        return api.post('/evidence/attachments', data={'record_ids': [eid]},
                        files={'file': ('a.pdf', data, 'application/pdf')},
                        headers=headers)
    assert attach(published, w['c'], PDF).status_code == 201
    _withdraw(w)
    for eid in (published, draft):
        for who, data in (('c', PDF + b'1'), ('m', PDF + b'2'),
                          ('admin', PDF + b'3')):
            refused = attach(eid, w[who], data)
            assert refused.status_code == 409, (eid, who, refused.text)
            assert refused.json()['detail'] == WITHDRAWN
    # removing stays as it is
    removed = api.delete(f'/evidence/{published}/attachments/0',
                         params={'reason': 'wrong file'}, headers=w['m'])
    assert removed.status_code == 200, removed.text
    _reinstate(w)
    assert attach(published, w['c'], PDF + b'4').status_code == 201


def _correction_body():
    import trimesh
    mesh = trimesh.creation.box(extents=(310, 200, 150))
    return {'geometry': {'meshes': [{'vertices': mesh.vertices.tolist(),
                                     'faces': mesh.faces.tolist()}],
                         'point_clouds': [], 'proxies': []}}


def test_a_correction_answers_409_on_a_withdrawn_element(world):
    """8.190 amended: a correction would publish a new state of an element out
    of circulation; the check comes before any other 409 on the route."""
    w, api = world, world['api']
    _withdraw(w)
    for who in ('c', 'admin'):     # a correction is a contributor's step
        _refused(api.post(f'/snapshots/{V1}/supersede',
                          json=_correction_body(), headers=w[who]))
    assert w['db']['component_snapshots'].count_documents(
        {'identity_id': BEAM, 'status': {'$in': ['draft', 'pending']}}) == 0
    # reinstate, then the correction works
    _reinstate(w)
    made = api.post(f'/snapshots/{V1}/supersede', json=_correction_body(),
                    headers=w['c'])
    assert made.status_code == 201, made.text


def _draft(w):
    made = w['api'].post(f'/identities/{BEAM}/snapshots',
                         json=_correction_body(), headers=w['c'])
    assert made.status_code == 201, made.text
    return made.json()['_id']


def _step(w, who, path, **kw):
    return w['api'].post(path, headers=w[who], **kw)


def test_submit_answers_409_on_a_withdrawn_element(world):
    """8.190 amended: a version opened before the withdrawal is not submitted
    after it; deleting it stays allowed; reinstate, then it submits."""
    w = world
    sid_ = _draft(w)
    _withdraw(w)
    for who in ('c', 'admin'):
        _refused(_step(w, who, f'/snapshots/{sid_}/submit'))
    assert w['db']['component_snapshots'].find_one(
        {'_id': sid_})['status'] == 'draft'
    # a caller without the right still gets 403, not a word of the state
    assert _step(w, 'user', f'/snapshots/{sid_}/submit').status_code == 403
    _reinstate(w)
    assert _step(w, 'c', f'/snapshots/{sid_}/submit').status_code == 200
    # and delete stays allowed on a withdrawn element
    _withdraw(w)
    recalled = _step(w, 'c', f'/snapshots/{sid_}/recall')
    assert recalled.status_code == 200, recalled.text
    gone = w['api'].delete(f'/snapshots/{sid_}', headers=w['m'])
    assert gone.status_code == 200, gone.text


def test_publish_and_promote_answer_409_on_a_withdrawn_element(world):
    w = world
    sid_ = _draft(w)
    assert _step(w, 'c', f'/snapshots/{sid_}/submit').status_code == 200
    _withdraw(w)
    for who in ('m', 'admin'):
        _refused(_step(w, who, f'/snapshots/{sid_}/publish'))
        _refused(_step(w, who, f'/snapshots/{sid_}/publish',
                       params={'promote': 1}))
        # promote: the check comes before any other 409 on the route
        _refused(_step(w, who, f'/snapshots/{V1}/promote'))
    assert w['db']['component_snapshots'].find_one(
        {'_id': sid_})['status'] == 'pending'
    assert _step(w, 'user', f'/snapshots/{sid_}/publish').status_code == 403
    # the allowed steps stay: recall, submit again is refused, reject, resubmit
    assert _step(w, 'c', f'/snapshots/{sid_}/recall').status_code == 200
    _refused(_step(w, 'c', f'/snapshots/{sid_}/submit'))
    _reinstate(w)
    assert _step(w, 'c', f'/snapshots/{sid_}/submit').status_code == 200
    _withdraw(w)
    rejected = _step(w, 'm', f'/snapshots/{sid_}/reject',
                     json={'reason': 'not now'})
    assert rejected.status_code == 200, rejected.text
    again = _step(w, 'c', f'/snapshots/{sid_}/resubmit')
    assert again.status_code == 200, again.text
    # reinstate, then submit, publish and promote work
    _reinstate(w)
    assert _step(w, 'c', f'/snapshots/{sid_}/submit').status_code == 200
    done = _step(w, 'm', f'/snapshots/{sid_}/publish',
                 params={'promote': 1})
    assert done.status_code == 200, done.text
    assert _step(w, 'm', f'/snapshots/{V1}/promote').status_code == 200


def test_withdrawing_stays_allowed_while_a_version_is_open(world):
    w = world
    sid_ = _draft(w)
    _withdraw(w)           # asserts 200
    assert w['db']['component_snapshots'].find_one(
        {'_id': sid_})['status'] == 'draft'


def test_a_version_is_reinstated_after_the_element_not_before(world):
    """8.190 amended: ``reinstate_snapshot`` answers 409 on a withdrawn
    element, admin included; the element's own reinstate comes first."""
    w, api = world, world['api']
    # every version withdrawn, then the element
    for row in list(w['db']['component_snapshots'].find(
            {'identity_id': BEAM, 'status': 'published'})):
        gone = api.post(f'/snapshots/{row["_id"]}/withdraw',
                        json={'reason': 'x'}, headers=w['m'])
        assert gone.status_code == 200, gone.text
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM}).get('current_snapshot_id') in (None, '')
    _withdraw(w)
    for who in ('m', 'admin'):
        _refused(_step(w, who, f'/snapshots/{V1}/reinstate'))
    assert w['db']['component_snapshots'].find_one(
        {'_id': V1})['status'] == 'withdrawn'
    assert _step(w, 'user', f'/snapshots/{V1}/reinstate').status_code == 403
    # the element comes back without a current version, and a moderator
    # reinstates a version afterwards: it becomes the current one
    _reinstate(w)
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM}).get('current_snapshot_id') in (None, '')
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM}).get('withdrawn') is None
    back = _step(w, 'm', f'/snapshots/{V1}/reinstate')
    assert back.status_code == 200, back.text
    assert w['db']['component_identities'].find_one(
        {'_id': BEAM})['current_snapshot_id'] == V1


def test_an_evidence_record_is_reinstated_after_the_element_not_before(world):
    w, api = world, world['api']
    created = api.post(f'/identities/{BEAM}/evidence', json=claim_body(),
                       headers=w['c'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    assert api.post(f'/evidence/{eid}/submit', headers=w['c']).status_code == 200
    assert api.post(f'/evidence/{eid}/publish', headers=w['m']).status_code == 200
    assert api.post(f'/evidence/{eid}/withdraw', json={'reason': 'x'},
                    headers=w['m']).status_code == 200
    _withdraw(w)
    for who in ('m', 'admin'):
        refused = api.post(f'/evidence/{eid}/reinstate', headers=w[who])
        assert refused.status_code == 409, (who, refused.text)
        assert 'withdrawn' in str(refused.json()['detail'])
    assert w['db']['component_evidence'].find_one(
        {'_id': eid})['status'] == 'withdrawn'
    _reinstate(w)
    back = api.post(f'/evidence/{eid}/reinstate', headers=w['m'])
    assert back.status_code == 200, back.text


def test_a_withdrawal_with_a_replacement_is_refused_a_plain_one_is_not(world):
    w, api = world, world['api']
    second = _draft(w)
    assert _step(w, 'c', f'/snapshots/{second}/submit').status_code == 200
    assert _step(w, 'm', f'/snapshots/{second}/publish').status_code == 200
    _withdraw(w)
    for who in ('m', 'admin'):
        _refused(_step(w, who, f'/snapshots/{second}/withdraw', json={
            'reason': 'x', 'replacement_id': V1}))
    assert w['db']['component_snapshots'].find_one(
        {'_id': second})['status'] == 'published'
    plain = _step(w, 'm', f'/snapshots/{second}/withdraw',
                  json={'reason': 'x'})
    assert plain.status_code == 200, plain.text
    # reinstate the element, then the version, and a replacement works again
    _reinstate(w)
    assert _step(w, 'm', f'/snapshots/{second}/reinstate').status_code == 200
    again = _step(w, 'm', f'/snapshots/{second}/withdraw', json={
        'reason': 'y', 'replacement_id': V1})
    assert again.status_code == 200, again.text
