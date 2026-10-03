"""
The 12 findings of the P6 part 1 review, one test each (decision 8.70).

M1 as_of projection, M2 gdpr in the change log, M3 reviewer and
self_attested, L1 text in a converted unit, L2 reinstating a correction,
L3 since / until, L4 attachment indices and the download validator, L5
submit?publish and the order of permission and status, L6 the etag guard of
a status step, L7 the list page, L8 a partial multi-record upload, L9 the
redaction route.
"""

from __future__ import annotations

import os

import pytest

from evidence_samples import (
    LAB,
    PDF,
    claim_body,
    clone,
    core_body,
    rebound_body,
    visual_body,
)
from support import iid, sid
from test_evidence_routes import (  # noqa: F401  (world is a fixture)
    BEAM,
    OBS,
    made,
    published,
    step,
    verify,
    world,
)

ADA = {**LAB, 'name': 'Dr. Ada Example', 'email': 'ada@lab.example',
       'orcid': '0000-0002-1825-0097'}


def attach(w, ids, data=PDF, name='r.pdf', headers=None):
    return w['api'].post(
        '/evidence/attachments', data={'record_ids': list(ids)},
        files={'file': (name, data, 'application/pdf')},
        headers=w['c'] if headers is None else headers)


# M1 ---------------------------------------------------------------------------
def test_m1_as_of_applies_the_viewer_projection(world):
    w = world
    api = w['api']
    pub = published(w, core_body(performed_by=[ADA]))
    api.patch(f'/evidence/{pub["_id"]}', json={'notes': 'later'},
              headers=w['m'])
    future = {'as_of': '2999-01-01T00:00:00Z'}
    for who in ('c', 'r'):
        body = api.get(f'/evidence/{pub["_id"]}', params=future,
                       headers=w[who]).json()
        actor = body['performed_by'][0]
        assert actor['name'] == 'Dr. Ada Example'      # members see names
        assert actor['email'] is None, who             # never the e-mail
    body = api.get(f'/evidence/{pub["_id"]}', params=future,
                   headers=w['m']).json()
    assert body['performed_by'][0]['email'] == 'ada@lab.example'
    # the roll-back restores old values: a removed name does not come back
    # through the projection of a non-member either (a public piece)
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    assert api.get(f'/evidence/{pub["_id"]}', params=future,
                   headers=w['user']).status_code == 403


# M2 ---------------------------------------------------------------------------
def test_m2_gdpr_removal_blanks_the_name_in_the_change_log(world):
    w = world
    api = w['api']
    eid = published(w, claim_body())['_id']
    assert attach(w, [eid], name='Mueller_Befund.pdf',
                  headers=w['m']).status_code == 201
    log = w['db']['change_log']
    assert 'Mueller' in str(list(log.find({'record_id': eid})))
    done = api.delete(f'/evidence/{eid}/attachments/0',
                      params={'reason': 'gdpr'}, headers=w['m'])
    assert done.status_code == 200
    assert 'Mueller' not in str(list(log.find({'record_id': eid})))
    changes = api.get(f'/identities/{BEAM}/changes', headers=w['m'])
    assert changes.status_code == 200 and 'Mueller' not in changes.text
    # any other reason leaves the log alone
    other = published(w, claim_body('density', (1500, 1700), 'kg/m3'))
    attach(w, [other['_id']], name='Lieferschein.pdf', headers=w['m'])
    api.delete(f'/evidence/{other["_id"]}/attachments/0',
               params={'reason': 'wrong report'}, headers=w['m'])
    assert 'Lieferschein' in str(list(log.find({'record_id':
                                                other['_id']})))


# M3 ---------------------------------------------------------------------------
def test_m3_a_reviewer_steps_back_only_to_unverified(world):
    from evidence_samples import person
    w = world
    eid = made(w, core_body(performed_by=[person(w['cid'])]))['_id']
    step(w, eid, 'submit', w['c'])
    assert verify(w, eid, 'reviewed', w['r']).status_code == 200
    assert verify(w, eid, 'self_attested', w['r']).status_code == 403
    assert verify(w, eid, 'self_attested', w['admin']).status_code == 403
    assert w['db']['component_evidence'].find_one({'_id': eid})[
        'verification']['state'] == 'reviewed'
    assert verify(w, eid, 'unverified', w['r']).status_code == 200
    # the recorder still sets his own claim
    assert verify(w, eid, 'self_attested', w['c']).status_code == 200


# L1 ---------------------------------------------------------------------------
def test_l1_text_in_a_converted_unit_is_422_not_500(world):
    w = world
    api = w['api']
    bad_value = claim_body('compressive_strength', (18, 28), 'N/mm2')
    bad_value['summary'] = {'quantity': 'compressive_strength',
                            'value': 'high', 'unit': 'kPa',
                            'kind': 'claimed'}
    r = api.post(f'/identities/{BEAM}/evidence', json=bad_value,
                 headers=w['c'])
    assert r.status_code == 422 and 'summary.unit' in str(r.json())
    bad_range = clone(bad_value)
    bad_range['summary'] = {'quantity': 'compressive_strength',
                            'range': ['low', 'high'], 'unit': 'kPa',
                            'kind': 'claimed'}
    assert api.post(f'/identities/{BEAM}/evidence', json=bad_range,
                    headers=w['c']).status_code == 422
    derived = rebound_body(observed_at=OBS)
    derived['derived'] = [{
        'quantity': 'compressive_strength_in_situ', 'value': 'x',
        'unit': 'kPa', 'kind': 'derived',
        'model': {'kind': 'en_13791_correlation', 'reference': 'r'}}]
    r = api.post(f'/identities/{BEAM}/evidence', json=derived,
                 headers=w['c'])
    assert r.status_code == 422 and 'derived.0.unit' in str(r.json())
    uncertain = claim_body('compressive_strength', (18, 28), 'N/mm2')
    uncertain['summary']['uncertainty'] = {'type': 'expanded',
                                           'value': 2, 'k': 2}
    ok = api.post(f'/identities/{BEAM}/evidence', json=uncertain,
                  headers=w['c'])
    assert ok.status_code == 201, ok.text


# L2 ---------------------------------------------------------------------------
def test_l2_a_correction_is_not_reinstated_beside_an_open_newer_one(world):
    w = world
    api = w['api']
    old = published(w, rebound_body(observed_at=OBS))
    first = api.post(f'/evidence/{old["_id"]}/supersede',
                     json=rebound_body(observed_at=OBS,
                                       readings=[44] * 9),
                     headers=w['c']).json()
    step(w, first['_id'], 'publish', w['m'])
    step(w, first['_id'], 'withdraw', w['m'], reason='wrong')
    second = api.post(f'/evidence/{old["_id"]}/supersede',
                      json=rebound_body(observed_at=OBS,
                                        readings=[46] * 9),
                      headers=w['c']).json()                # open
    refused = api.post(f'/evidence/{first["_id"]}/reinstate',
                       headers=w['m'])
    assert refused.status_code == 409 and second['_id'] in refused.text
    # once the newer one is decided the older may come back, or not
    step(w, second['_id'], 'reject', w['m'], reason='no')
    assert api.post(f'/evidence/{first["_id"]}/reinstate',
                    headers=w['m']).status_code == 200


# L3 ---------------------------------------------------------------------------
def test_l3_since_and_until_are_instants_and_a_bare_until_is_a_day(world):
    w = world
    api = w['api']
    rec = published(w, rebound_body(observed_at='2026-07-01T10:00:00Z'))

    def ids(**params):
        return [r['_id'] for r in api.get(
            f'/identities/{BEAM}/evidence',
            params={'method': 'rebound_hammer', **params},
            headers=w['m']).json()]
    # offsets compare as instants, not as strings
    assert ids(since='2026-07-01T11:30:00+02:00') == [rec['_id']]  # 09:30Z
    assert ids(since='2026-07-01T12:30:00+02:00') == []            # 10:30Z
    assert ids(until='2026-07-01T11:30:00+02:00') == []
    assert ids(until='2026-07-01T12:30:00+02:00') == [rec['_id']]
    # a bare until date includes the whole day; a bare since is midnight
    assert ids(until='2026-07-01') == [rec['_id']]
    assert ids(until='2026-06-30') == []
    assert ids(since='2026-07-01') == [rec['_id']]
    assert ids(since='2026-07-02') == []
    assert ids(since='2026-07-01', until='2026-07-01') == [rec['_id']]
    assert api.get(f'/identities/{BEAM}/evidence',
                   params={'until': 'soon'},
                   headers=w['m']).status_code == 422


# L4 ---------------------------------------------------------------------------
def test_l4_an_attachment_index_is_never_reused_and_downloads_validate(world):
    w = world
    api = w['api']
    draft = made(w, claim_body())['_id']
    attach(w, [draft])
    attach(w, [draft], data=PDF + b'1')
    assert api.delete(f'/evidence/{draft}/attachments/1',
                      headers=w['c']).status_code == 200
    third = attach(w, [draft], data=PDF + b'2').json()
    assert third['attached'][0]['index'] == 2              # not 1 again
    stored = w['db']['component_evidence'].find_one({'_id': draft})
    assert [a['index'] for a in stored['attachments']] == [0, 1, 2]
    assert stored['attachments'][1]['removed']['reason'] == \
        'removed before publish'
    assert api.get(f'/evidence/{draft}/attachments/1',
                   headers=w['c']).status_code == 410
    # the download carries a validator: the bytes under an index never
    # change, a removal shows on the next request
    first = api.get(f'/evidence/{draft}/attachments/0', headers=w['c'])
    etag = first.headers['etag']
    assert first.headers['cache-control'] == 'private, no-cache'
    again = api.get(f'/evidence/{draft}/attachments/0',
                    headers={**w['c'], 'If-None-Match': etag})
    assert again.status_code == 304 and not again.content
    api.delete(f'/evidence/{draft}/attachments/0', headers=w['c'])
    assert api.get(f'/evidence/{draft}/attachments/0',
                   headers={**w['c'], 'If-None-Match': etag}
                   ).status_code == 410
    # still 401 / 403 before the validator is looked at
    assert api.get(f'/evidence/{draft}/attachments/2',
                   headers={'If-None-Match': etag}).status_code == 401


# L5 ---------------------------------------------------------------------------
def test_l5a_submit_and_publish_checks_the_component_first(world,
                                                           member_headers):
    w = world
    api = w['api']
    both, _ = member_headers({'dbu_zirkus': ['contributor', 'moderator']})
    made_ = api.post('/identities', json={
        'dataset': 'dbu_zirkus', 'original_function': 'IfcBeam',
        'material': 'concrete',
        'snapshot': {'geometry': {'meshes': [{
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}]}}},
        headers=both)
    new_id = made_.json()['identity']['_id']
    eid = api.post(f'/identities/{new_id}/evidence', json=rebound_body(
        observed_at=OBS), headers=both).json()['_id']
    refused = api.post(f'/evidence/{eid}/submit', params={'publish': 1},
                       headers=both)
    assert refused.status_code == 409 and 'I26' in refused.text
    assert w['db']['component_evidence'].find_one({'_id': eid})[
        'status'] == 'draft'                        # nothing half done
    assert api.post(f'/evidence/{eid}/submit',
                    headers=both).status_code == 200
    # a published component: submit + publish in one call works
    ok = api.post(f'/identities/{BEAM}/evidence', json=rebound_body(
        observed_at=OBS), headers=both).json()['_id']
    done = api.post(f'/evidence/{ok}/submit', params={'publish': 1},
                    headers=both)
    assert done.status_code == 200 and done.json()['status'] == 'published'


def test_l5b_permission_comes_before_the_status_check(world):
    w = world
    api = w['api']
    pub = published(w, rebound_body(observed_at=OBS))['_id']
    pend = made(w, rebound_body(observed_at=OBS), submit=1)['_id']
    # the same wrong-status request: 403 for a caller who may not act, 409
    # only for one who may --- a status never leaks to the unauthorised
    for verb in ('publish', 'reject', 'recall', 'submit', 'resubmit'):
        for who, want in (('r', 403), ('c2', 403), ('user', 403)):
            r = api.post(f'/evidence/{pub}/{verb}', json={'reason': 'x'},
                         headers=w[who])
            assert r.status_code == want, (verb, who, r.status_code)
    assert api.post(f'/evidence/{pub}/publish', headers=w['m']
                    ).status_code == 409
    assert api.post(f'/evidence/{pend}/withdraw', json={'reason': 'x'},
                    headers=w['c']).status_code == 403
    assert api.post(f'/evidence/{pend}/withdraw', json={'reason': 'x'},
                    headers=w['m']).status_code == 409
    assert api.post(f'/evidence/{pub}/reinstate', headers=w['c']
                    ).status_code == 403
    assert api.post(f'/evidence/{pub}/submit').status_code == 401
    # delete: the status of a record the caller cannot read stays hidden
    assert api.delete(f'/evidence/{pub}', headers=w['user']
                      ).status_code == 403
    assert api.delete(f'/evidence/{pub}', headers=w['admin']
                      ).status_code == 409


# L6 ---------------------------------------------------------------------------
def test_l6_a_status_step_loses_against_a_concurrent_edit(world,
                                                          monkeypatch):
    """The step is guarded by status and etag: a write that lands between
    the read and the replace is a 409, not a silent overwrite."""
    import apps.catalog.api.evidence_lifecycle as lifecycle
    w = world
    eid = made(w, rebound_body(observed_at=OBS))['_id']
    original = lifecycle._change_status

    async def raced(request, user, record, to, **kw):
        # someone edits the notes first (a different etag)
        await request.app.mongodb_component_evidence.update_one(
            {'_id': eid}, {'$set': {'notes': 'edited meanwhile',
                                    'etag': 'changed'}})
        return await original(request, user, record, to, **kw)
    monkeypatch.setattr(lifecycle, '_change_status', raced)
    r = w['api'].post(f'/evidence/{eid}/submit', headers=w['c'])
    assert r.status_code == 409
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['status'] == 'draft' and stored['notes'] == \
        'edited meanwhile'


# L7 ---------------------------------------------------------------------------
def test_l7_the_page_is_cut_in_the_database_and_keeps_its_rules(world):
    w = world
    api = w['api']
    for i in range(5):
        published(w, claim_body(
            'density', (1500 + i, 1700 + i), 'kg/m3',
            observed_at=f'2026-03-0{i + 1}T00:00:00Z'))
    base = {'quantity': 'density'}
    page1 = api.get('/evidence', params={**base, 'limit': 2},
                    headers=w['m']).json()
    page2 = api.get('/evidence', params={**base, 'limit': 2, 'skip': 2},
                    headers=w['m']).json()
    page3 = api.get('/evidence', params={**base, 'limit': 2, 'skip': 4},
                    headers=w['m']).json()
    assert [len(page1), len(page2), len(page3)] == [2, 2, 1]
    seen = [r['_id'] for r in page1 + page2 + page3]
    assert len(set(seen)) == 5
    assert [r['observed_at'] for r in page1 + page2 + page3] == sorted(
        r['observed_at'] for r in page1 + page2 + page3)
    # visibility is part of the query: a signed-in outsider gets nothing,
    # a public piece shows to everyone, a withdrawn one as a tombstone
    assert api.get('/evidence', params=base, headers=w['user']).json() == []
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    assert len(api.get('/evidence', params={**base, 'limit': 50},
                       headers=w['user']).json()) == 5
    step(w, seen[0], 'withdraw', w['m'], reason='x')
    rows = api.get('/evidence', params={**base, 'status': 'withdrawn'},
                   headers=w['user']).json()
    assert [r['kind'] for r in rows] == ['evidence']
    # a withdrawn component: the published records are tombstones outside
    api.post(f'/identities/{BEAM}/withdraw', json={'reason': 'x'},
             headers=w['m'])
    out = api.get('/evidence', params={**base, 'limit': 50},
                  headers=w['user']).json()
    assert out and all(r.get('kind') == 'evidence' for r in out)
    inside = api.get('/evidence', params={**base, 'limit': 50},
                     headers=w['c']).json()
    assert inside and all('summary' in r for r in inside)


# L8 ---------------------------------------------------------------------------
def test_l8_a_partial_upload_says_which_records_hold_the_file(world,
                                                              monkeypatch):
    import apps.catalog.api.evidence_attachments as module
    from fastapi import HTTPException
    w = world
    a, b = made(w, claim_body())['_id'], made(
        w, claim_body('density', (1500, 1700), 'kg/m3'))['_id']
    real = module._add_entry

    async def flaky(request, user, record_id, copy, name):
        if record_id == b:
            raise HTTPException(status_code=409, detail='changed')
        return await real(request, user, record_id, copy, name)
    monkeypatch.setattr(module, '_add_entry', flaky)
    r = attach(w, [a, b])
    assert r.status_code == 409
    detail = r.json()['detail']
    assert [x['record_id'] for x in detail['attached']] == [a]
    assert [x['record_id'] for x in detail['failed']] == [b]
    stored = w['db']['component_evidence']
    assert len(stored.find_one({'_id': a})['attachments']) == 1
    assert stored.find_one({'_id': b})['attachments'] == []
    assert os.path.exists(os.path.join(
        os.environ['EVIDENCE_ATTACHMENTS_DIR'], a, '0.pdf'))


# L9 ---------------------------------------------------------------------------
def test_l9_redaction_is_described_guarded_and_counts_alike(world):
    w = world
    api = w['api']
    published(w, core_body(performed_by=[ADA]))
    published(w, core_body(performed_by=[ADA], cored_at=
                           '2026-05-01T00:00:00Z',
                           tested_at='2026-05-02T00:00:00Z'))
    schema = api.get('/openapi.json').json()
    text = str(schema['paths']['/actors/redact']['post'])
    assert 'catalogue-wide' in text
    body = {'name': 'Dr. Ada Example'}
    dry = api.post('/actors/redact', json={**body, 'dry_run': True},
                   headers=w['admin']).json()
    done = api.post('/actors/redact', json=body, headers=w['admin']).json()
    assert dry['actors'] == done['actors'] == 2
    assert dry['evidence'] == done['evidence'] == 2
    # a changed record between the scan and the write is not overwritten:
    # the guarded write retries on the fresh document
    eid = published(w, core_body(performed_by=[ADA], cored_at=
                                 '2026-04-01T00:00:00Z',
                                 tested_at='2026-04-02T00:00:00Z'))['_id']
    api.patch(f'/evidence/{eid}', json={'notes': 'kept'}, headers=w['m'])
    api.post('/actors/redact', json=body, headers=w['admin'])
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['notes'] == 'kept'
    assert stored['performed_by'][0]['name'] is None


# FOLD TRIGGERS (8.70 f) ---------------------------------------------------------
def test_f_exit_undo_reenter_and_origin_change_recompute_both_targets(world):
    w = world
    api = w['api']
    v1 = sid('beam', 1)
    inside = published(w, visual_body('spalling', 1, observed_at=OBS))
    props = lambda: api.get(  # noqa: E731
        f'/snapshots/{v1}/properties', headers=w['m']).json()['properties']
    claim = published(w, claim_body(observed_at='2026-09-01T00:00:00Z'))

    def folded():
        return api.get(f'/identities/{BEAM}/properties',
                       headers=w['m']).json()['properties']
    assert props()['spalling']['evidence_ids'] == [inside['_id']]
    # exit before the evidence: the snapshot loses it, undo brings it back
    assert api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-06-20T00:00:00Z'},
        headers=w['m']).status_code == 200
    assert 'spalling' not in props()
    assert 'compressive_strength' in folded()      # identity scope stays
    assert api.delete(f'/identities/{BEAM}/exit',
                      headers=w['m']).status_code == 200
    assert props()['spalling']['evidence_ids'] == [inside['_id']]
    # exit, re-entry, then an origin change moves the archived gap
    api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'},
        headers=w['m'])
    late = published(w, visual_body('spalling', 3,
                                    observed_at='2026-09-01T00:00:00Z'))
    api.post(f'/identities/{BEAM}/reenter', json={'origin': {
        'kind': 'deinstallation', 'at': '2026-10-01T00:00:00Z',
        'at_precision': 'day'}}, headers=w['m'])
    assert props()['spalling']['evidence_ids'] == [inside['_id']]
    moved = api.patch(f'/identities/{BEAM}', json={'origin': {
        'kind': 'deinstallation', 'at': '2026-08-15T00:00:00Z',
        'at_precision': 'day'}}, headers=w['m'])
    assert moved.status_code == 200, moved.text
    # 2026-09-01 is no longer in the gap: it belongs to v1 again
    assert sorted(props()['spalling']['evidence_ids']) == sorted(
        [inside['_id'], late['_id']])


# 8.70 e: the 403 says which role is missing -------------------------------------
def test_e_a_moderator_without_contributor_is_told_which_role_is_missing(
        world):
    w = world
    r = w['api'].post(f'/identities/{BEAM}/evidence',
                      json=rebound_body(observed_at=OBS), headers=w['m'])
    assert r.status_code == 403
    assert 'contributor' in r.json()['detail']
    assert 'moderator' in r.json()['detail']
    pub = published(w, rebound_body(observed_at=OBS))
    r = w['api'].post(f'/evidence/{pub["_id"]}/supersede',
                      json=rebound_body(observed_at=OBS), headers=w['m'])
    assert r.status_code == 403 and 'contributor' in r.json()['detail']
    bulk = w['api'].post('/evidence/bulk', json={'records': [
        {**rebound_body(observed_at=OBS), 'identity_id': BEAM}]},
        headers=w['m'])
    assert bulk.status_code == 403 and 'contributor' in bulk.json()['detail']
    # outsiders and anonymous keep the plain answers
    assert w['api'].post(f'/identities/{BEAM}/evidence',
                         json=rebound_body(observed_at=OBS),
                         headers=w['user']).status_code == 403
    assert 'contributor' not in w['api'].post(
        f'/identities/{BEAM}/evidence', json=rebound_body(observed_at=OBS),
        headers=w['user']).text
    assert iid('beam') == BEAM
