"""
Evidence on the real routes (spec section 3.3, 7.2, I5 - I15, I22, I26 -
I28; decisions 8.12, 8.16, 8.18, 8.40 - 8.42; plan P6).

One migrated catalog; the ZirKuS beam (``dbu_zirkus``, members-only) is the
target. Its v1 starts 2026-06-15, so evidence observed in July 2026 resolves
to v1.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import (
    LAB,
    clone,
    claim_body,
    core_body,
    person,
    rebound_body,
    visual_body,
)
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
OBS = '2026-07-01T10:00:00Z'
CORED = '2026-06-20T09:00:00Z'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    c2, c2id = member_headers({'dbu_zirkus': ['contributor']})
    r, rid = member_headers({'dbu_zirkus': ['reviewer']})
    m, mid = member_headers({'dbu_zirkus': ['moderator']})
    o, _ = member_headers({'schoenes_neues_feld': ['moderator']})
    return {'api': api, 'db': db, 'c': c, 'cid': cid, 'c2': c2,
            'c2id': c2id, 'r': r, 'rid': rid, 'm': m, 'mid': mid, 'o': o,
            'admin': auth_headers('admin'), 'user': auth_headers('user')}


def create(w, body, headers=None, identity=BEAM, **params):
    return w['api'].post(f'/identities/{identity}/evidence', json=body,
                         params=params,
                         headers=w['c'] if headers is None else headers)


def made(w, body, **kw):
    response = create(w, body, **kw)
    assert response.status_code == 201, response.text
    return response.json()


def step(w, eid, verb, headers, **body):
    response = w['api'].post(f'/evidence/{eid}/{verb}',
                             json=body or None, headers=headers)
    assert response.status_code == 200, (verb, response.text)
    return response.json()


def published(w, body, **kw):
    record = made(w, body, **kw)
    step(w, record['_id'], 'submit', w['c'])
    return step(w, record['_id'], 'publish', w['m'])


def errors(response):
    return [e['path'] for e in response.json()['detail']['errors']]


def rebound_at(readings=None, observed_at=OBS, **over):
    return rebound_body(observed_at=observed_at, readings=readings, **over)


# CREATE AND VALIDATE ----------------------------------------------------------
def test_create_recomputes_and_refuses_what_disagrees(world):
    w = world
    record = made(w, rebound_at())
    assert record['status'] == 'draft'
    assert record['summary']['value'] == 43 and record['summary'][
        'quantity'] == 'rebound_number'
    assert record['payload']['median'] == 43
    assert record['source_tier'] == 'ndt' and record['verification'][
        'state'] == 'unverified'
    assert record['recorded_by_user_id'] == w['cid']
    assert record['warnings'] == [] and record['context'] is None
    assert record['identity_id'] == BEAM

    # a value the server computes differently is refused, with its path
    wrong = rebound_at()
    wrong['payload']['median'] = 50
    bad = create(w, wrong)
    assert bad.status_code == 422 and errors(bad) == ['payload.median']
    short = create(w, rebound_at(readings=[40] * 8))
    assert short.status_code == 422 and errors(short) == ['payload.readings']
    # unknown fields, unknown method, a derived field from a client
    assert create(w, {**rebound_at(), 'frame': 1}).status_code == 422
    assert create(w, {**rebound_at(), 'method': 'astm_c805'}
                  ).status_code == 422
    assert create(w, {**rebound_at(), 'source_tier': 'destructive'}
                  ).status_code == 422
    assert w['db']['component_evidence'].count_documents(
        {'status': 'draft'}) == 1
    # ?submit=1 creates it pending, history draft --> pending
    pending = made(w, rebound_at(), submit=1)
    assert pending['status'] == 'pending'
    assert [(h['from'], h['to']) for h in pending['status_history']] == [
        ('draft', 'pending')]


def test_who_may_create(world):
    w = world
    assert create(w, rebound_at(), headers={}).status_code == 401
    # roles are a set, not a ladder: a moderator who is no contributor
    # does not record evidence (7.0)
    for who in ('user', 'r', 'o', 'm'):
        assert create(w, rebound_at(), headers=w[who]).status_code == 403, who
    assert create(w, rebound_at(), headers=w['admin']).status_code == 201
    unknown = create(w, rebound_at(),
                     identity='11111111-2222-4333-8444-555555555555')
    assert unknown.status_code == 404


def test_position_snapshot_belongs_to_the_identity_I9(world):
    w = world
    ok = clone(rebound_at(), position={
        'kind': 'point', 'snapshot_id': sid('beam', 1),
        'point': [100, 10, 5]})
    assert create(w, ok).status_code == 201
    other = clone(ok, position={'kind': 'point',
                                'snapshot_id': sid('panel', 0),
                                'point': [1, 2, 3]})
    bad = create(w, other)
    assert bad.status_code == 422 and errors(bad) == [
        'position.snapshot_id']


def test_units_and_claims(world):
    w = world
    record = made(w, claim_body(rng=(18, 28), unit='N/mm2'))
    assert record['summary']['unit'] == 'MPa' and record['summary'][
        'unit_entered'] == 'N/mm2'
    assert record['position'] == {'kind': 'none', 'snapshot_id': None,
                                  'point': None,
                                  'description': 'whole component'}
    exposure = made(w, claim_body('exposure_class', ('XC4', 'XF1'), None))
    assert exposure['summary']['range'] == ['XC4', 'XF1']
    assert create(w, claim_body('exposure_class', ('XC9',), None)
                  ).status_code == 422


def test_methods_quantities_and_schemas(world):
    w = world
    methods = w['api'].get('/evidence/methods').json()
    assert [m['name'] for m in methods][:2] == ['rebound_hammer',
                                                'core_compression']
    rebound = methods[0]
    assert rebound['source_tier'] == 'ndt' and rebound['derived_models'][
        0]['kind'] == 'din_en_13791_a20_na6'
    props = rebound['payload_schema']['properties']
    assert props['median']['server_computed'] is True
    assert 'description' in props['readings']
    quantities = {q['name']: q for q in w['api'].get(
        '/evidence/quantities').json()}
    assert quantities['crack_width']['unit'] == 'mm'
    assert quantities['exposure_class']['values'][0] == 'X0'
    schema = w['api'].get('/schema/evidence').json()
    assert {'EvidenceView', 'PropertiesView'} <= set(schema['$defs'])
    create_schema = w['api'].get('/schema/create-evidence').json()
    assert 'ReboundHammerPayload' in create_schema['$defs']
    assert 'EvidencePayloads' in create_schema['$defs']


# EDITING FROM THE FORM (decision 8.127) ----------------------------------------
def test_the_form_edits_a_draft_and_a_pending_record_with_its_create_body(world):
    """The web form saves an edit with ``PATCH /evidence/{id}`` and the body
    of the create form (without the component and ``self_attested``; empty
    note as null): the record keeps its status and its attachments."""
    w = world
    api = w['api']
    eid = made(w, rebound_at(readings=None, notes='first'))['_id']
    stored = api.get(f'/evidence/{eid}', headers=w['c']).json()
    assert stored['status'] == 'draft'
    edited = rebound_at(readings=None, notes=None)
    edited['payload']['test_area']['label'] = 'A2'
    edited['position'] = {'kind': 'none', 'description': 'south face'}
    response = api.patch(f'/evidence/{eid}', json=edited, headers=w['c'])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'draft' and body['_id'] == eid
    assert body['payload']['test_area']['label'] == 'A2'
    assert body['position']['description'] == 'south face'
    assert body['notes'] is None
    assert body['attachments'] == stored['attachments']
    # self_attested is for a new record: the route refuses it in an edit
    assert api.patch(f'/evidence/{eid}', json={**edited, 'self_attested': True},
                     headers=w['c']).status_code == 422
    # someone else's draft: not for another contributor, but for a moderator
    assert api.patch(f'/evidence/{eid}', json=edited,
                     headers=w['c2']).status_code == 403
    assert api.patch(f'/evidence/{eid}', json=edited,
                     headers=w['m']).status_code == 200
    # pending: the author no longer edits, a moderator does; status stays
    step(w, eid, 'submit', w['c'])
    assert api.patch(f'/evidence/{eid}', json=edited,
                     headers=w['c']).status_code == 403
    again = api.patch(f'/evidence/{eid}', json=edited, headers=w['m'])
    assert again.status_code == 200 and again.json()['status'] == 'pending'


# THE LIFECYCLE ----------------------------------------------------------------
def test_lifecycle_and_permissions_I15(world):
    w = world
    eid = made(w, rebound_at())['_id']
    api = w['api']
    # draft: submit is the author's step
    assert api.post(f'/evidence/{eid}/submit', headers=w['c2']
                    ).status_code == 403
    assert api.post(f'/evidence/{eid}/submit', headers=w['r']
                    ).status_code == 403
    assert step(w, eid, 'submit', w['c'])['status'] == 'pending'
    # pending: only moderator(D) edits (8.18); the author recalls
    assert api.patch(f'/evidence/{eid}', json={'notes': 'x'},
                     headers=w['c']).status_code == 403
    assert api.patch(f'/evidence/{eid}', json={'notes': 'checked'},
                     headers=w['m']).json()['notes'] == 'checked'
    assert step(w, eid, 'recall', w['c'])['status'] == 'draft'
    step(w, eid, 'submit', w['c'])

    def queued(headers):
        return [r['id'] for r in api.get('/evidence/pending',
                                         headers=headers).json()]
    assert queued(w['m']) == [eid] and queued(w['admin']) == [eid]
    assert queued(w['c']) == [] and queued(w['o']) == []
    row = api.get('/evidence/pending', headers=w['m']).json()[0]
    assert row['identity_published'] is True and row['quantity'] == \
        'rebound_number' and row['catalog_number'] == 5

    assert api.post(f'/evidence/{eid}/publish', headers=w['c']
                    ).status_code == 403
    assert api.post(f'/evidence/{eid}/reject', json={}, headers=w['m']
                    ).status_code == 422
    rejected = step(w, eid, 'reject', w['m'], reason='no photo of the area')
    assert rejected['status'] == 'rejected'
    # rejected: nobody edits (8.18); the author resubmits
    assert api.patch(f'/evidence/{eid}', json={'notes': 'y'},
                     headers=w['m']).status_code == 403
    assert api.post(f'/evidence/{eid}/publish', headers=w['m']
                    ).status_code == 409
    assert step(w, eid, 'resubmit', w['c'])['status'] == 'draft'
    step(w, eid, 'submit', w['c'])
    assert step(w, eid, 'publish', w['m'])['status'] == 'published'
    history = [(h['from'], h['to']) for h in api.get(
        f'/evidence/{eid}', headers=w['m']).json()['status_history']]
    assert history == [
        ('draft', 'pending'), ('pending', 'draft'), ('draft', 'pending'),
        ('pending', 'rejected'), ('rejected', 'draft'),
        ('draft', 'pending'), ('pending', 'published')]
    assert w['db']['component_evidence'].find_one({'_id': eid})[
        'status_history'][3]['reason'] == 'no photo of the area'

    # published: frozen, derived, mutable; never deleted; withdraw and back
    frozen = api.patch(f'/evidence/{eid}', json={
        'payload': rebound_at()['payload']}, headers=w['m'])
    assert frozen.status_code == 409 and 'supersede' in str(frozen.json())
    assert api.patch(f'/evidence/{eid}', json={'source_tier': 'visual'},
                     headers=w['m']).status_code == 422
    assert api.patch(f'/evidence/{eid}', json={'notes': 'n'},
                     headers=w['c']).status_code == 403
    assert api.patch(f'/evidence/{eid}', json={
        'notes': 'n', 'position': {'description': 'north face, mid-span'}},
        headers=w['m']).json()['position']['description'] == \
        'north face, mid-span'
    assert api.delete(f'/evidence/{eid}', headers=w['admin']
                      ).status_code == 409
    assert api.post(f'/evidence/{eid}/withdraw', json={'reason': ''},
                    headers=w['m']).status_code == 422
    assert api.post(f'/evidence/{eid}/withdraw', json={'reason': 'x'},
                    headers=w['c']).status_code == 403
    assert step(w, eid, 'withdraw', w['m'], reason='wrong piece')[
        'status'] == 'withdrawn'
    assert step(w, eid, 'reinstate', w['m'])['status'] == 'published'


def test_edit_before_publish_recomputes(world):
    w = world
    eid = made(w, rebound_at())['_id']
    api = w['api']
    new = rebound_at(readings=[50, 51, 52, 50, 49, 51, 50, 52, 50])['payload']
    edited = api.patch(f'/evidence/{eid}', json={'payload': new},
                       headers=w['c'])
    assert edited.status_code == 200, edited.text
    assert edited.json()['summary']['value'] == 50
    assert edited.json()['payload']['median'] == 50
    # a stale server value in the resent payload is refused
    stale = dict(new, median=43)
    bad = api.patch(f'/evidence/{eid}', json={'payload': stale},
                    headers=w['c'])
    assert bad.status_code == 422
    assert api.patch(f'/evidence/{eid}', json={'method': 'core_compression'},
                     headers=w['c']).status_code == 422
    assert api.patch(f'/evidence/{eid}', json={'notes': 'x'},
                     headers=w['c2']).status_code == 403    # not the author
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['summary']['value'] == 50
    log = list(w['db']['change_log'].find({'record_id': eid}))
    assert log and log[0]['record_kind'] == 'evidence'          # I30
    assert {c['path'] for c in log[0]['changes']} >= {'payload', 'summary'}


def test_delete_only_before_publish(world):
    w = world
    api = w['api']
    eid = made(w, rebound_at())['_id']
    assert api.delete(f'/evidence/{eid}', headers=w['r']).status_code == 403
    assert api.delete(f'/evidence/{eid}', headers=w['c2']).status_code == 403
    assert api.delete(f'/evidence/{eid}', headers=w['c']).status_code == 200
    assert api.get(f'/evidence/{eid}', headers=w['m']).status_code == 404
    pid = published(w, rebound_at())['_id']
    assert api.delete(f'/evidence/{pid}', headers=w['m']).status_code == 409


# CORRECTIONS ------------------------------------------------------------------
def test_supersede_one_open_correction_and_the_fold(world):
    w = world
    api = w['api']
    old = published(w, rebound_at())
    fix = rebound_at(readings=[45] * 9)
    # published only; contributor(D); one open correction (I14, 8.16)
    draft = made(w, rebound_at())
    assert api.post(f'/evidence/{draft["_id"]}/supersede', json=fix,
                    headers=w['c']).status_code == 409
    assert api.post(f'/evidence/{old["_id"]}/supersede', json=fix,
                    headers=w['r']).status_code == 403
    wrong_method = api.post(f'/evidence/{old["_id"]}/supersede',
                            json=claim_body(), headers=w['c'])
    assert wrong_method.status_code == 422
    new = api.post(f'/evidence/{old["_id"]}/supersede', json=fix,
                   headers=w['c'])
    assert new.status_code == 201, new.text
    new = new.json()
    assert new['status'] == 'pending' and new['supersedes'] == old['_id']
    second = api.post(f'/evidence/{old["_id"]}/supersede', json=fix,
                      headers=w['c2'])
    assert second.status_code == 409 and new['_id'] in second.text
    # the old record stays in the fold until the correction is published
    props = api.get(f'/identities/{BEAM}/properties', headers=w['m']).json()
    assert props['properties']['rebound_number']['range'] == [43, 43]
    step(w, new['_id'], 'publish', w['m'])
    stored = w['db']['component_evidence'].find_one({'_id': old['_id']})
    assert stored['superseded_by'] == new['_id']
    props = api.get(f'/identities/{BEAM}/properties', headers=w['m']).json()
    assert props['properties']['rebound_number']['range'] == [45, 45]
    assert props['properties']['rebound_number']['evidence_ids'] == [
        new['_id']]
    # default lists drop the corrected record; ?include=superseded keeps it
    ids = [r['_id'] for r in api.get(
        f'/identities/{BEAM}/evidence', headers=w['m']).json()]
    assert old['_id'] not in ids and new['_id'] in ids
    ids = [r['_id'] for r in api.get(
        f'/identities/{BEAM}/evidence', params={'include': 'superseded'},
        headers=w['m']).json()]
    assert old['_id'] in ids
    # a record is superseded at most once; the corrected one is retrievable
    assert api.post(f'/evidence/{old["_id"]}/supersede', json=fix,
                    headers=w['c']).status_code == 409
    assert api.get(f'/evidence/{old["_id"]}', headers=w['m']).json()[
        'superseded_by'] == new['_id']
    log = list(w['db']['change_log'].find({'record_id': old['_id']}))
    assert any(c['path'] == 'superseded_by' for e in log
               for c in e['changes'])                           # I30

    # withdrawing the correction gives the old record its place back
    step(w, new['_id'], 'withdraw', w['m'], reason='wrong again')
    props = api.get(f'/identities/{BEAM}/properties', headers=w['m']).json()
    assert props['properties']['rebound_number']['range'] == [43, 43]
    assert w['db']['component_evidence'].find_one({'_id': old['_id']})[
        'superseded_by'] is None
    step(w, new['_id'], 'reinstate', w['m'])
    assert w['db']['component_evidence'].find_one({'_id': old['_id']})[
        'superseded_by'] == new['_id']


def test_a_rejected_correction_can_be_resubmitted_only_alone(world):
    w = world
    api = w['api']
    old = published(w, rebound_at())
    first = api.post(f'/evidence/{old["_id"]}/supersede',
                     json=rebound_at(readings=[44] * 9),
                     headers=w['c']).json()
    step(w, first['_id'], 'reject', w['m'], reason='no')
    second = api.post(f'/evidence/{old["_id"]}/supersede',
                      json=rebound_at(readings=[46] * 9),
                      headers=w['c']).json()                    # allowed now
    assert api.post(f'/evidence/{first["_id"]}/resubmit',
                    headers=w['c']).status_code == 409          # I14, 8.16
    step(w, second['_id'], 'recall', w['c'])
    assert api.post(f'/evidence/{first["_id"]}/resubmit',
                    headers=w['c']).status_code == 409


# VERIFICATION -----------------------------------------------------------------
def verify(w, eid, state, headers, note=None):
    return w['api'].put(f'/evidence/{eid}/verification',
                        json={'state': state, 'note': note}, headers=headers)


def test_verification_owners_and_four_eyes_8_12(world):
    w = world
    rec = made(w, core_body(performed_by=[person(w['cid'])]))
    eid = rec['_id']
    step(w, eid, 'submit', w['c'])        # a reviewer(D) reads pending (7.0)
    # the recorder, who performed it, toggles self_attested
    assert verify(w, eid, 'self_attested', w['c']).status_code == 200
    got = w['db']['component_evidence'].find_one({'_id': eid})
    assert got['verification']['state'] == 'self_attested'
    assert got['verification']['by']['user_id'] == w['cid']
    assert verify(w, eid, 'unverified', w['c']).status_code == 200
    # nobody else claims it for the recorder; the recorder never reviews
    assert verify(w, eid, 'self_attested', w['c2']).status_code == 403
    assert verify(w, eid, 'reviewed', w['c']).status_code == 403
    assert verify(w, eid, 'reviewed', w['c2']).status_code == 403
    assert verify(w, eid, 'reviewed', {}).status_code == 401
    # the recorder is not among the performers: no self_attested (I27)
    outside = made(w, core_body(performed_by=[LAB]))
    step(w, outside['_id'], 'submit', w['c'])
    assert verify(w, outside['_id'], 'self_attested', w['c']
                  ).status_code == 403
    # a reviewer(D) other than the recorder / performers reviews
    done = verify(w, eid, 'reviewed', w['r'])
    assert done.status_code == 200, done.text
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['verification']['by']['user_id'] == w['rid']
    assert stored['verification']['at']
    # the recorder never overrides a reviewer's state
    assert verify(w, eid, 'unverified', w['c']).status_code == 403
    assert verify(w, eid, 'self_attested', w['c']).status_code == 403
    # the moderator is no reviewer(D) unless admin; a reviewer downgrades
    assert verify(w, eid, 'unverified', w['m']).status_code == 403
    assert verify(w, eid, 'unverified', w['r']).status_code == 200
    # admin passes the role but not the four eyes: they are the recorder's
    # own record only if they performed it; here they may review
    assert verify(w, eid, 'reviewed', w['admin']).status_code == 200
    assert w['db']['component_evidence'].find_one({'_id': eid})[
        'verification']['by']['user_id'] != w['cid']


def test_an_admin_who_recorded_it_cannot_review_it(world, db):
    w = world
    response = w['api'].post(f'/identities/{BEAM}/evidence',
                             json=rebound_at(), headers=w['admin'])
    assert response.status_code == 201
    eid = response.json()['_id']
    assert verify(w, eid, 'reviewed', w['admin']).status_code == 403
    # the same admin reviews a record somebody else recorded
    other = made(w, rebound_at())['_id']
    assert verify(w, other, 'reviewed', w['admin']).status_code == 200


def test_accredited_needs_the_note_and_a_covering_accreditation(world):
    w = world
    eid = made(w, core_body())['_id']
    step(w, eid, 'submit', w['c'])
    no_note = verify(w, eid, 'accredited', w['r'])
    assert no_note.status_code == 422 and 'I27' in no_note.text
    ok = verify(w, eid, 'accredited', w['r'],
                note='D-PL-12345-01-00 scope checked in the DAkkS register')
    assert ok.status_code == 200, ok.text
    # a lab without a covering accreditation (I22)
    lab = clone(LAB)
    lab['accreditation']['scope'] = ['EN 12504-2']
    eid2 = made(w, core_body(performed_by=[lab]))['_id']
    step(w, eid2, 'submit', w['c'])
    bad = verify(w, eid2, 'accredited', w['r'], note='checked')
    assert bad.status_code == 422 and 'I22' in bad.text
    # the scope check follows the observation date
    expired = clone(LAB)
    expired['accreditation']['valid_until'] = '2020-01-01T00:00:00Z'
    eid3 = made(w, core_body(performed_by=[expired]))['_id']
    step(w, eid3, 'submit', w['c'])
    assert verify(w, eid3, 'accredited', w['r'], note='checked'
                  ).status_code == 422


def test_a_result_edit_resets_a_review(world):
    w = world
    eid = made(w, core_body())['_id']
    step(w, eid, 'submit', w['c'])
    assert verify(w, eid, 'reviewed', w['r']).status_code == 200
    step(w, eid, 'recall', w['c'])         # back to a draft the author edits
    # notes are no result field: the review stands
    w['api'].patch(f'/evidence/{eid}', json={'notes': 'x'}, headers=w['c'])
    assert w['db']['component_evidence'].find_one({'_id': eid})[
        'verification']['state'] == 'reviewed'
    changed = core_body()['payload']
    changed['test']['max_load_kn'] = 250.0
    changed['result'] = {}
    edited = w['api'].patch(f'/evidence/{eid}', json={'payload': changed},
                            headers=w['c'])
    assert edited.status_code == 200, edited.text
    got = w['db']['component_evidence'].find_one({'_id': eid})
    assert got['verification'] == {'state': 'unverified', 'by': None,
                                   'at': None, 'note': None}


def test_verification_moves_the_fold(world):
    w = world
    eid = published(w, core_body())['_id']

    def confidence():
        return w['api'].get(f'/identities/{BEAM}/properties',
                            headers=w['m']).json()['properties'][
            'compressive_strength']['confidence']
    assert confidence() == round(0.9 * 0.7, 4)
    assert verify(w, eid, 'reviewed', w['r']).status_code == 200
    assert confidence() == round(0.9 * 1.0, 4)


# I26, I28 ---------------------------------------------------------------------
def test_evidence_of_an_unpublished_identity_cannot_be_published_I26(world):
    w = world
    api = w['api']
    created = api.post('/identities', json={
        'dataset': 'dbu_zirkus', 'original_function': 'IfcBeam',
        'material': 'concrete',
        'snapshot': {'geometry': {'meshes': [{
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}]}}},
        headers=w['c'])
    assert created.status_code == 201, created.text
    new_id = created.json()['identity']['_id']
    eid = made(w, rebound_at(), identity=new_id)['_id']
    step(w, eid, 'submit', w['c'])
    row = api.get('/evidence/pending', headers=w['m']).json()[0]
    assert row['identity_published'] is False and row[
        'pending_snapshot_id'] is None
    refused = api.post(f'/evidence/{eid}/publish', headers=w['m'])
    assert refused.status_code == 409 and 'I26' in refused.text
    # once the v0 is published the evidence can follow
    snap = created.json()['snapshot']['_id']
    api.post(f'/snapshots/{snap}/submit', headers=w['c'])
    api.post(f'/snapshots/{snap}/publish', headers=w['m'])
    assert api.post(f'/evidence/{eid}/publish', headers=w['m']
                    ).status_code == 200


def test_withdrawn_identity_and_terminal_exit_I28(world):
    w = world
    api = w['api']
    # a terminal exit: only observations from before it
    api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'recycled', 'at': '2026-08-01T00:00:00Z'}, headers=w['m'])
    late = create(w, rebound_at(observed_at='2026-09-01T00:00:00Z'))
    assert late.status_code == 409 and 'I28' in late.text
    assert create(w, rebound_at(observed_at='2026-07-15T00:00:00Z')
                  ).status_code == 201
    # a non-terminal exit allows it (the record resolves after_exit)
    api.delete(f'/identities/{BEAM}/exit', headers=w['m'])
    api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'}, headers=w['m'])
    after = create(w, rebound_at(observed_at='2026-09-01T00:00:00Z'))
    assert after.status_code == 201
    got = api.get(f'/evidence/{after.json()["_id"]}',
                  params={'include': 'context'}, headers=w['m']).json()
    assert got['context'] == {'snapshot_id': None,
                              'resolution': 'after_exit'}
    api.delete(f'/identities/{BEAM}/exit', headers=w['m'])
    # a withdrawn identity: 409, naming the canonical piece
    panel = iid('panel')
    withdrawn = api.post(f'/identities/{BEAM}/withdraw', json={
        'reason': 'dup', 'duplicate_of': panel}, headers=w['m'])
    assert withdrawn.status_code == 200, withdrawn.text
    refused = create(w, rebound_at())
    assert refused.status_code == 409
    assert refused.json()['detail']['duplicate_of'] == panel


# BULK -------------------------------------------------------------------------
def bulk(w, records, headers=None, **extra):
    return w['api'].post('/evidence/bulk', json={'records': records,
                                                 **extra},
                         headers=headers or w['c'])


def test_bulk_is_all_or_nothing(world):
    w = world
    items = [{**rebound_at(), 'identity_id': BEAM},
             {**rebound_at(readings=[40, 41, 42, 43, 44, 45, 46, 47, 48]),
              'identity_id': BEAM},
             {**claim_body(), 'identity_id': iid('beam')}]
    ok = bulk(w, items)
    assert ok.status_code == 201, ok.text
    assert len(ok.json()['records']) == 3
    assert {r['status'] for r in ok.json()['records']} == {'draft'}
    before = w['db']['component_evidence'].count_documents({})
    broken = clone(items[1])
    broken['payload']['median'] = 1
    bad = bulk(w, [items[0], broken, items[2]])
    assert bad.status_code == 422
    assert bad.json()['detail']['index'] == 1
    assert w['db']['component_evidence'].count_documents({}) == before
    # contributor(D) of every target: one foreign identity rejects all
    foreign = {**claim_body(), 'identity_id': iid('feld')}
    denied = bulk(w, [items[0], foreign])
    assert denied.status_code == 403
    assert w['db']['component_evidence'].count_documents({}) == before
    submitted = bulk(w, [items[0]], submit=True)
    assert submitted.json()['records'][0]['status'] == 'pending'
    assert bulk(w, [], headers=w['c']).status_code == 422


# PAIRING ----------------------------------------------------------------------
def test_a_core_pairs_with_one_rebound_record_8_42(world):
    w = world
    api = w['api']
    reb = published(w, rebound_at(observed_at='2026-06-19T09:00:00Z'))

    def paired_core(pid, **kw):
        return core_body(paired=pid, cored_at=CORED,
                         tested_at='2026-06-25T09:00:00Z', **kw)
    ok = paired_core(reb['_id'])
    created = create(w, ok)
    assert created.status_code == 201, created.text
    # a second core for the same rebound record
    again = create(w, ok)
    assert again.status_code == 422 and 'one core per rebound' in again.text
    # not a rebound record, not a record at all, another component
    assert create(w, paired_core('11111111-2222-4333-8444-555555555555')
                  ).status_code == 422
    claim = published(w, claim_body())
    assert create(w, paired_core(claim['_id'])).status_code == 422
    # a rebound taken after the coring cannot be its spot
    late = published(w, rebound_at(observed_at='2026-06-25T09:00:00Z'))
    assert create(w, paired_core(late['_id'])).status_code == 422
    # a discarded set cannot be paired
    discarded = made(w, rebound_at(
        readings=[40, 40, 40, 40, 40, 40, 40, 60, 62, 20],
        observed_at='2026-06-19T09:00:00Z'))
    assert discarded['payload']['set_discarded'] is True
    assert create(w, paired_core(discarded['_id'])).status_code == 422
    # the paired rebound record cannot be deleted while a core names it
    draft_pair = made(w, rebound_at(observed_at='2026-06-19T09:00:00Z'))
    core_rec = made(w, paired_core(draft_pair['_id']))
    blocked = api.delete(f'/evidence/{draft_pair["_id"]}', headers=w['c'])
    assert blocked.status_code == 409 and core_rec['_id'] in blocked.text
    # the pairing is checked again on an edit of the core, without itself
    payload = paired_core(draft_pair['_id'])['payload']
    assert api.patch(f'/evidence/{core_rec["_id"]}',
                     json={'payload': payload},
                     headers=w['c']).status_code == 200


# READING, PROJECTION, TOMBSTONES ----------------------------------------------
def test_reads_follow_the_visibility_rule(world):
    w = world
    api = w['api']
    pub = published(w, core_body(performed_by=[
        {**LAB, 'name': 'Dr. Ada Example', 'email': 'ada@lab.example',
         'orcid': '0000-0002-1825-0097'}]))
    draft = made(w, rebound_at())
    eid = pub['_id']
    # members of D see the people; e-mail only admin / moderator(D), never
    # in a list
    one = api.get(f'/evidence/{eid}', headers=w['c']).json()
    assert one['performed_by'][0]['name'] == 'Dr. Ada Example'
    assert one['performed_by'][0]['email'] is None
    assert api.get(f'/evidence/{eid}', headers=w['m']).json()[
        'performed_by'][0]['email'] == 'ada@lab.example'
    listed = api.get(f'/identities/{BEAM}/evidence',
                     params={'method': 'core_compression'},
                     headers=w['m']).json()
    assert [r['performed_by'][0]['email'] for r in listed] == [None]
    # a members-only piece is not readable by outsiders (not a 404, 8.11)
    assert api.get(f'/evidence/{eid}').status_code == 401
    assert api.get(f'/evidence/{eid}', headers=w['user']).status_code == 403
    assert api.get(f'/evidence/{eid}', headers=w['o']).status_code == 403
    # a draft: its author and moderator(D) only
    assert api.get(f'/evidence/{draft["_id"]}', headers=w['c']
                   ).status_code == 200
    assert api.get(f'/evidence/{draft["_id"]}', headers=w['m']
                   ).status_code == 200
    for who in ('c2', 'r', 'o', 'user'):
        assert api.get(f'/evidence/{draft["_id"]}', headers=w[who]
                       ).status_code == 403, who
    assert api.get(f'/evidence/{draft["_id"]}').status_code == 401
    # lists show only what the caller may see
    def ids(who):
        rows = api.get(f'/identities/{BEAM}/evidence',
                       params={'status': 'all'}, headers=w[who]).json()
        return {r['_id'] for r in rows
                if r.get('method') != 'reinforcement_layout'}
    assert ids('m') == {eid, draft['_id']}
    assert ids('c') == {eid, draft['_id']}
    assert ids('r') == {eid}               # a draft is not the reviewer's
    # a pending record is seen by reviewer(D) too (7.0)
    step(w, draft['_id'], 'submit', w['c'])
    assert api.get(f'/evidence/{draft["_id"]}', headers=w['r']
                   ).status_code == 200


def test_public_pieces_show_organizations_only(world):
    w = world
    api = w['api']
    pub = published(w, core_body(performed_by=[
        {**LAB, 'name': 'Dr. Ada Example', 'email': 'ada@lab.example',
         'orcid': '0000-0002-1825-0097'}]))
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    anon = api.get(f'/evidence/{pub["_id"]}')
    assert anon.status_code == 200, anon.text
    actor = anon.json()['performed_by'][0]
    assert actor['organization'] == 'Pruefstelle Muster GmbH'
    # the person is absent, not empty (8.101)
    assert not {'name', 'orcid', 'email', 'role', 'user_id'} & set(actor)
    assert 'recorded_by_username' not in anon.json()
    assert 'recorded_by_user_id' not in anon.json()
    signed = api.get(f'/evidence/{pub["_id"]}', headers=w['user']).json()
    assert signed['performed_by'][0]['name'] == 'Dr. Ada Example'
    assert signed['performed_by'][0]['orcid'] == '0000-0002-1825-0097'
    # anonymous lists get published records only
    draft = made(w, rebound_at())
    listing = api.get(f'/identities/{BEAM}/evidence',
                      params={'status': 'all',
                              'method': 'core_compression'}).json()
    assert [r['_id'] for r in listing] == [pub['_id']]
    assert all(r['status'] == 'published' for r in api.get(
        f'/identities/{BEAM}/evidence', params={'status': 'all'}).json())
    assert api.get(f'/evidence/{draft["_id"]}').status_code == 401


def test_a_withdrawn_record_is_a_tombstone_outside_the_dataset(world):
    w = world
    api = w['api']
    pub = published(w, claim_body())
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    step(w, pub['_id'], 'withdraw', w['m'], reason='a person in the photo')
    inside = api.get(f'/evidence/{pub["_id"]}', headers=w['c']).json()
    assert inside['status'] == 'withdrawn' and inside['summary']
    assert 'person' in str(inside['status_history'])
    outside = api.get(f'/evidence/{pub["_id"]}', headers=w['user'])
    assert outside.status_code == 200
    body = outside.json()
    assert (body['kind'], body['status']) == ('evidence', 'withdrawn')
    assert 'person' not in str(body) and 'summary' not in body
    listing = api.get(f'/identities/{BEAM}/evidence',
                      params={'status': 'withdrawn'},
                      headers=w['user']).json()
    assert listing[0]['kind'] == 'evidence'
    anonymous = api.get(f'/evidence/{pub["_id"]}')
    assert anonymous.status_code == 200 and anonymous.json()['kind'] == \
        'evidence'


def test_etag_and_304_and_as_of(world):
    w = world
    api = w['api']
    pub = published(w, claim_body())
    first = api.get(f'/evidence/{pub["_id"]}', headers=w['c'])
    etag = first.headers['etag']
    again = api.get(f'/evidence/{pub["_id"]}',
                    headers={**w['c'], 'If-None-Match': etag})
    assert again.status_code == 304 and not again.content
    # another viewer tier is another representation
    assert api.get(f'/evidence/{pub["_id"]}',
                   headers={**w['m'], 'If-None-Match': etag}
                   ).status_code == 200
    # as_of: the record before a later change (members only)
    api.patch(f'/evidence/{pub["_id"]}', json={'notes': 'later note'},
              headers=w['m'])
    past = api.get(f'/evidence/{pub["_id"]}',
                   params={'as_of': '2020-01-01T00:00:00Z'}, headers=w['m'])
    assert past.status_code == 404                  # did not exist yet
    now = api.get(f'/evidence/{pub["_id"]}',
                  params={'as_of': '2999-01-01T00:00:00Z'}, headers=w['m'])
    assert now.status_code == 200 and now.json()['notes'] == 'later note'
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    assert api.get(f'/evidence/{pub["_id"]}',
                   params={'as_of': '2999-01-01T00:00:00Z'},
                   headers=w['user']).status_code == 403


def test_cross_catalog_list_and_filters(world):
    w = world
    api = w['api']
    published(w, core_body())
    published(w, rebound_at())
    published(w, claim_body())
    visual = published(w, visual_body())
    rows = api.get('/evidence', headers=w['m']).json()
    assert len(rows) >= 4
    only = api.get('/evidence', params={'method': 'core_compression'},
                   headers=w['m']).json()
    assert [r['method'] for r in only] == ['core_compression']
    by_quantity = api.get('/evidence', params={'quantity':
                                               'compressive_strength_in_situ'},
                          headers=w['m']).json()
    assert [r['method'] for r in by_quantity] == ['core_compression']
    hi = api.get('/evidence', params={'quantity': 'compressive_strength',
                                      'min': 100}, headers=w['m']).json()
    assert hi == []
    lo = api.get('/evidence', params={'quantity': 'compressive_strength',
                                      'min': 30, 'max': 40},
                 headers=w['m']).json()
    assert len(lo) == 1
    assert api.get('/evidence', params={'dataset': 'dbu_zirkus'},
                   headers=w['m']).json()
    assert api.get('/evidence', params={'dataset': 'ddu_aggregations'},
                   headers=w['m']).json() == []
    assert api.get('/evidence', headers=w['user']).json() == []
    page = api.get('/evidence', params={'limit': 1}, headers=w['m']).json()
    assert len(page) == 1
    assert api.get('/evidence', params={'limit': 1, 'skip': 1},
                   headers=w['m']).json()[0]['_id'] != page[0]['_id']
    tier = api.get(f'/identities/{BEAM}/evidence', params={'tier': 'visual'},
                   headers=w['m']).json()
    assert [r['_id'] for r in tier] == [visual['_id']]
    window = api.get(f'/identities/{BEAM}/evidence', params={
        'since': '2026-07-02T00:00:00Z'}, headers=w['m']).json()
    assert window == [] or all(r['observed_at'] >= '2026-07-02' for r in
                               window)
    assert api.get(f'/identities/{BEAM}/evidence', params={
        'since': 'yesterday'}, headers=w['m']).status_code == 422
    assert api.get(f'/identities/{BEAM}/evidence', params={
        'status': 'bogus'}, headers=w['m']).status_code == 422


def test_the_passport_carries_evidence_on_request(world):
    w = world
    api = w['api']
    pub = published(w, core_body(performed_by=[
        {**LAB, 'name': 'Dr. Ada Example', 'email': 'ada@lab.example'}]))
    draft = made(w, rebound_at())
    plain = api.get(f'/identities/{BEAM}/compose', headers=w['m']).json()
    assert 'evidence' not in plain
    assert plain['identity']['properties']['compressive_strength']['n'] == 1
    with_ev = api.get(f'/identities/{BEAM}/compose',
                      params={'include': 'evidence'}, headers=w['m'])
    assert with_ev.status_code == 200
    ids = {e['_id'] for e in with_ev.json()['evidence']}
    assert pub['_id'] in ids and draft['_id'] not in ids   # published only
    core = [e for e in with_ev.json()['evidence']
            if e['_id'] == pub['_id']][0]
    assert core['performed_by'][0]['email'] is None          # a list
    assert core['performed_by'][0]['name'] == 'Dr. Ada Example'
    assert with_ev.headers['etag'] != api.get(
        f'/identities/{BEAM}/compose', headers=w['m']).headers['etag']
    # public: organization only, no drafts
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    anon = api.get(f'/identities/{BEAM}/compose',
                   params={'include': 'evidence'}).json()
    core = [e for e in anon['evidence'] if e['_id'] == pub['_id']][0]
    assert 'name' not in core['performed_by'][0]          # absent (8.101)
    assert core['performed_by'][0]['organization']
    # a change of the evidence changes the representation
    etag = api.get(f'/identities/{BEAM}/compose',
                   params={'include': 'evidence'}, headers=w['m']
                   ).headers['etag']
    api.patch(f'/evidence/{pub["_id"]}', json={'notes': 'n'}, headers=w['m'])
    assert api.get(f'/identities/{BEAM}/compose',
                   params={'include': 'evidence'}, headers=w['m']
                   ).headers['etag'] != etag


def test_a_reviewer_never_sets_the_recorders_claim(world):
    w = world
    eid = made(w, core_body(performed_by=[person(w['cid'])]))['_id']
    step(w, eid, 'submit', w['c'])
    # a reviewer(D) does not attest on the recorder's behalf ...
    assert verify(w, eid, 'self_attested', w['r']).status_code == 403
    assert verify(w, eid, 'self_attested', w['admin']).status_code == 403
    # ... nor steps a review back to it: back only to unverified (8.70 a)
    assert verify(w, eid, 'reviewed', w['r']).status_code == 200
    assert verify(w, eid, 'self_attested', w['r']).status_code == 403
    assert verify(w, eid, 'unverified', w['r']).status_code == 200
