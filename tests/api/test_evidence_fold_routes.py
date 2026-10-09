"""
The property fold on the real routes (spec section 4.1, 4.4, 7.1; decisions
8.10, 8.19; plan P6): publishing evidence moves ``identity.properties`` and
the as-of ``snapshot.properties``; exits, re-entries and snapshot events
move the windows; a child inherits from its parents; the timeline merges it
all.

The beam's v0 starts 2026-06-15 15:23:01, its v1 at 15:27:38.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import (
    clone,
    claim_body,
    core_body,
    rebound_body,
    visual_body,
)
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
PANEL = iid('panel')
CUT = iid('cut')
CUT2 = iid('cut2')
IN_V0 = '2026-06-15T15:25:00Z'
IN_V1 = '2026-07-01T10:00:00Z'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    m, mid = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': c, 'cid': cid, 'm': m,
            'admin': auth_headers('admin'), 'user': auth_headers('user')}


def put(w, body, identity=BEAM, who='admin'):
    """Create, submit and publish; returns the published record."""
    api = w['api']
    created = api.post(f'/identities/{identity}/evidence', json=body,
                       headers=w[who])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    assert api.post(f'/evidence/{eid}/submit', headers=w[who]
                    ).status_code == 200
    done = api.post(f'/evidence/{eid}/publish', headers=w['admin'])
    assert done.status_code == 200, done.text
    return done.json()


def identity_props(w, identity=BEAM, **params):
    response = w['api'].get(f'/identities/{identity}/properties',
                            params=params, headers=w['admin'])
    assert response.status_code == 200, response.text
    return response.json()


def snap_props(w, snapshot_id):
    response = w['api'].get(f'/snapshots/{snapshot_id}/properties',
                            headers=w['admin'])
    assert response.status_code == 200, response.text
    return response.json()['properties']


def stored(w, identity=BEAM):
    return w['db']['component_identities'].find_one({'_id': identity})


# IDENTITY TARGET --------------------------------------------------------------
def test_publishing_folds_and_the_highest_tier_wins(world):
    w = world
    assert list(stored(w)['properties']) == ['rebar_diameter']   # the migrated layout
    claim = put(w, claim_body('compressive_strength', (18, 28)))
    first = stored(w)['properties']['compressive_strength']
    assert first['source'] == 'archival' and first['range'] == [18, 28]
    assert first['n'] == 1 and first['evidence_ids'] == [claim['_id']]
    assert first['confidence'] == round((1 - 0.6) * 0.7, 4)
    core = put(w, core_body(), who='admin')
    props = identity_props(w)
    strength = props['properties']['compressive_strength']
    assert strength['source'] == 'destructive'
    assert strength['range'] == [38.3, 38.3] and strength['unit'] == 'MPa'
    assert strength['evidence_ids'] == [core['_id']]
    assert props['properties']['compressive_strength_in_situ'][
        'range'] == [38.3, 38.3]
    # the archival claim is outranked, not superseded (4.4)
    assert props['outranked_evidence_ids'] == {
        'compressive_strength': [claim['_id']]}
    # the stored block and the view agree
    assert stored(w)['properties']['compressive_strength']['source'] == \
        'destructive'
    # the evidence block carries the same on the passport identity
    passport = w['api'].get(f'/identities/{BEAM}/compose',
                            headers=w['admin']).json()
    assert passport['identity']['properties']['compressive_strength'][
        'evidence_ids'] == [core['_id']]


def test_a_discarded_set_and_an_invalid_core_never_count(world):
    w = world
    put(w, rebound_body(observed_at=IN_V1,
                        readings=[40, 40, 40, 40, 40, 40, 40, 60, 62, 20]))
    assert 'rebound_number' not in stored(w)['properties']
    bar = core_body()
    bar['payload']['specimen']['reinforcement'] = [
        {'orientation': 'longitudinal', 'diameter_mm': 12,
         'position_mm': 30}]
    put(w, bar)
    assert 'compressive_strength' not in stored(w)['properties']
    put(w, rebound_body(observed_at=IN_V1))
    assert stored(w)['properties']['rebound_number']['range'] == [43, 43]


def test_withdraw_reinstate_and_the_as_of_window(world):
    w = world
    api = w['api']
    old = put(w, core_body(tested_at='2026-03-01T00:00:00Z'))
    new_body = core_body(cored_at='2026-05-01T00:00:00Z',
                         tested_at='2026-05-02T00:00:00Z')
    new_body['payload']['test']['max_load_kn'] = 400.0
    new = put(w, new_body)
    both = identity_props(w)['properties']['compressive_strength']
    assert both['n'] == 2 and both['range'][0] == 38.3
    past = identity_props(w, as_of='2026-03-15T00:00:00Z')
    assert past['properties']['compressive_strength']['n'] == 1
    assert past['as_of'] == '2026-03-15T00:00:00Z'
    # computed, not stored
    assert stored(w)['properties']['compressive_strength']['n'] == 2
    assert api.get(f'/identities/{BEAM}/properties',
                   params={'as_of': 'later'},
                   headers=w['admin']).status_code == 422
    api.post(f'/evidence/{new["_id"]}/withdraw', json={'reason': 'x'},
             headers=w['admin'])
    assert stored(w)['properties']['compressive_strength']['evidence_ids'] \
        == [old['_id']]
    api.post(f'/evidence/{old["_id"]}/withdraw', json={'reason': 'x'},
             headers=w['admin'])
    assert 'compressive_strength' not in stored(w)['properties']
    api.post(f'/evidence/{old["_id"]}/reinstate', headers=w['admin'])
    assert stored(w)['properties']['compressive_strength']['n'] == 1


def test_derived_rebound_class_and_the_core_beat_the_estimate(world):
    w = world
    estimate = rebound_body(observed_at=IN_V1)
    estimate['derived'] = [{
        'quantity': 'compressive_strength_in_situ', 'value': 28.0,
        'unit': 'N/mm2', 'kind': 'derived',
        'model': {'kind': 'en_13791_correlation',
                  'reference': 'Site correlation 2026-117'}}]
    put(w, estimate)
    props = stored(w)['properties']
    assert props['compressive_strength_in_situ']['source'] == 'ndt'
    assert props['compressive_strength_in_situ']['range'] == [28.0, 28.0]
    put(w, core_body())
    props = identity_props(w)
    assert props['properties']['compressive_strength_in_situ'][
        'source'] == 'destructive'
    assert len(props['outranked_evidence_ids'][
        'compressive_strength_in_situ']) == 1


# SNAPSHOT TARGET --------------------------------------------------------------
def test_snapshot_properties_follow_the_resolved_context(world):
    w = world
    api = w['api']
    v0, v1 = sid('beam', 0), sid('beam', 1)
    early = put(w, visual_body('spalling', 1, observed_at=IN_V0))
    late = put(w, visual_body('spalling', 3, observed_at=IN_V1))
    crack = put(w, visual_body('crack_width', 0.4, observed_at=IN_V1))
    assert snap_props(w, v0)['spalling']['range'] == [1, 1]
    assert snap_props(w, v1)['spalling']['range'] == [3, 3]
    assert snap_props(w, v1)['crack_width']['unit'] == 'mm'
    assert snap_props(w, v1)['spalling']['evidence_ids'] == [late['_id']]
    # identity-scoped quantities never land on a snapshot
    put(w, claim_body())
    assert 'compressive_strength' not in snap_props(w, v1)
    # the identity block holds no snapshot-scoped quantity either
    assert 'spalling' not in stored(w)['properties']
    listing = api.get(f'/identities/{BEAM}/evidence',
                      params={'include': 'context', 'method':
                              'visual_inspection'},
                      headers=w['admin']).json()
    by_id = {r['_id']: r['context'] for r in listing}
    assert by_id[early['_id']] == {'snapshot_id': v0, 'resolution': 'exact'}
    assert by_id[late['_id']]['snapshot_id'] == v1
    assert by_id[crack['_id']]['snapshot_id'] == v1
    # the snapshot's etag follows its properties (the passport's ETag)
    doc = w['db']['component_snapshots'].find_one({'_id': v1})
    from apps.catalog.etag import compute_snapshot_etag
    assert doc['etag'] == compute_snapshot_etag(doc)
    # moving v1's start before the early record moves the window
    moved = api.patch(f'/snapshots/{v1}', json={
        'effective_from': '2026-06-15T15:24:00Z'}, headers=w['admin'])
    assert moved.status_code == 200, moved.text
    assert snap_props(w, v0) == {}
    assert snap_props(w, v1)['spalling']['range'] == [1, 3]
    assert snap_props(w, v1)['spalling']['n'] == 2


def test_snapshot_events_move_the_fold(world):
    w = world
    api = w['api']
    v0, v1 = sid('beam', 0), sid('beam', 1)
    put(w, visual_body('spalling', 2, observed_at=IN_V1))
    assert snap_props(w, v1)['spalling']['range'] == [2, 2]
    # withdrawing v1: the record now resolves to v0, v1 keeps nothing
    assert api.post(f'/snapshots/{v1}/withdraw', json={'reason': 'x'},
                    headers=w['admin']).status_code == 200
    assert snap_props(w, v1) == {}
    assert snap_props(w, v0)['spalling']['range'] == [2, 2]
    api.post(f'/snapshots/{v1}/reinstate', headers=w['admin'])
    assert snap_props(w, v0) == {}
    assert snap_props(w, v1)['spalling']['range'] == [2, 2]


def test_exit_reenter_and_archived_cycles_8_10_8_19(world):
    w = world
    api = w['api']
    v1 = sid('beam', 1)
    inside = put(w, visual_body('spalling', 1, observed_at=IN_V1))
    assert snap_props(w, v1)['spalling']['range'] == [1, 1]
    # exit: evidence after it feeds no snapshot, but an exit also takes the
    # snapshot windows with it (nothing after the exit date is in v1)
    api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'},
        headers=w['admin'])
    away = put(w, visual_body('spalling', 3, observed_at='2026-09-01T00:00:00Z'))
    props = snap_props(w, v1)
    assert props['spalling']['evidence_ids'] == [inside['_id']]
    contexts = {r['_id']: r['context'] for r in api.get(
        f'/identities/{BEAM}/evidence', params={'include': 'context'},
        headers=w['admin']).json()}
    assert contexts[away['_id']] == {'snapshot_id': None,
                                     'resolution': 'after_exit'}
    # re-entry: the gap between the archived exit and the new origin is
    # still outside circulation (8.19)
    reentered = api.post(f'/identities/{BEAM}/reenter', json={'origin': {
        'kind': 'deinstallation', 'at': '2026-10-01T00:00:00Z',
        'at_precision': 'day'}}, headers=w['admin'])
    assert reentered.status_code == 200, reentered.text
    contexts = {r['_id']: r['context'] for r in api.get(
        f'/identities/{BEAM}/evidence', params={'include': 'context'},
        headers=w['admin']).json()}
    assert contexts[away['_id']]['resolution'] == 'after_exit'
    assert snap_props(w, v1)['spalling']['evidence_ids'] == [inside['_id']]
    # evidence after the re-entry resolves to a snapshot again
    back = put(w, visual_body('spalling', 2, observed_at='2026-11-01T00:00:00Z'))
    assert snap_props(w, v1)['spalling']['n'] == 2
    contexts = {r['_id']: r['context'] for r in api.get(
        f'/identities/{BEAM}/evidence', params={'include': 'context'},
        headers=w['admin']).json()}
    assert contexts[back['_id']]['snapshot_id'] == v1
    # undoing the exit before re-entry would have moved the windows too
    # (here: exit and re-entry are already archived; the identity-scoped
    # fold never depended on them)
    put(w, claim_body())
    assert 'compressive_strength' in stored(w)['properties']


def test_before_first_evidence_is_listed_not_folded_into_a_snapshot(world):
    w = world
    early = put(w, visual_body('condition_grade', 1,
                               observed_at='2020-01-01T00:00:00Z'))
    ctx = w['api'].get(f'/evidence/{early["_id"]}',
                       params={'include': 'context'},
                       headers=w['admin']).json()['context']
    assert ctx == {'snapshot_id': None, 'resolution': 'before_first'}
    assert snap_props(w, sid('beam', 0)) == {}
    assert snap_props(w, sid('beam', 1)) == {}
    events = w['api'].get(f'/identities/{BEAM}/timeline',
                          headers=w['admin']).json()['events']
    mine = [e for e in events if e.get('record_id') == early['_id']][0]
    assert mine['section'] == 'before_cataloguing'
    assert mine['resolution'] == 'before_first'


# INHERITANCE ------------------------------------------------------------------
def test_children_inherit_and_follow_the_parent(world):
    w = world
    # panel -> cut -> cut2 is a three-generation lineage (migrated)
    assert stored(w, CUT)['parent_identities'] == [PANEL]
    claim = put(w, claim_body('compressive_strength', (18, 28)),
                identity=PANEL)
    parent_conf = stored(w, PANEL)['properties']['compressive_strength'][
        'confidence']
    child = stored(w, CUT)['properties']['compressive_strength']
    assert child['source'] == 'inherited' and child['range'] == [18, 28]
    assert child['inherited_from'] == [PANEL] and child['n'] == 0
    assert child['confidence'] == round(parent_conf * 0.8, 4)
    grand = stored(w, CUT2)['properties']['compressive_strength']
    assert grand['inherited_from'] == [CUT]
    assert grand['confidence'] == round(parent_conf * 0.8 * 0.8, 4)
    # a better record on the parent propagates down the chain
    put(w, core_body(), identity=PANEL)
    assert stored(w, CUT)['properties']['compressive_strength'][
        'range'] == [38.3, 38.3]
    assert stored(w, CUT2)['properties']['compressive_strength'][
        'range'] == [38.3, 38.3]
    # the child's own evidence beats what it inherits
    own = put(w, claim_body('compressive_strength', (10, 12)), identity=CUT)
    got = stored(w, CUT)['properties']['compressive_strength']
    assert got['source'] == 'archival' and got['range'] == [10, 12]
    assert got['evidence_ids'] == [own['_id']] and got['inherited_from'] is None
    # ... and the grandchild now inherits the child's, not the panel's
    assert stored(w, CUT2)['properties']['compressive_strength'][
        'range'] == [10, 12]
    # withdrawing the parent's records withdraws what it passed on
    w['api'].post(f'/evidence/{own["_id"]}/withdraw', json={'reason': 'x'},
                  headers=w['admin'])
    assert stored(w, CUT2)['properties']['compressive_strength'][
        'range'] == [38.3, 38.3]
    assert claim['status'] == 'published'


def test_a_merge_takes_the_union_and_the_weakest_confidence(world):
    w = world
    api = w['api']
    put(w, claim_body('compressive_strength', (18, 28)), identity=PANEL)
    put(w, core_body(), identity=CUT)               # destructive, own
    created = api.post('/identities', json={
        'dataset': 'ddu_aggregations',
        'parent_identities': [PANEL, CUT],
        'original_function': 'IfcPlate', 'material': 'mineral_composite',
        'snapshot': {'geometry': {'meshes': [{
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'faces': [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]}]}}},
        headers=w['admin'])
    assert created.status_code == 201, created.text
    merged = created.json()['identity']['properties']['compressive_strength']
    assert merged['source'] == 'inherited'
    assert merged['range'] == [18, 38.3]
    weakest = min(
        stored(w, PANEL)['properties']['compressive_strength'][
            'confidence'],
        stored(w, CUT)['properties']['compressive_strength']['confidence'])
    assert merged['confidence'] == round(weakest * 0.8, 4)
    assert sorted(merged['inherited_from']) == sorted([PANEL, CUT])
    child_id = created.json()['identity']['_id']
    # a change on one parent reaches the merged child
    put(w, core_body(), identity=PANEL)
    again = stored(w, child_id)['properties']['compressive_strength']
    assert again['range'] == [38.3, 38.3]


# TIMELINE ---------------------------------------------------------------------
def test_the_timeline_merges_everything_and_hides_what_it_must(world):
    w = world
    api = w['api']
    early = put(w, visual_body('condition_grade', 2,
                               observed_at='2020-01-01T00:00:00Z'))
    mid = put(w, core_body())
    api.patch(f'/identities/{BEAM}', json={'trade_name': 'Beam B3'},
              headers=w['admin'])
    api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'},
        headers=w['admin'])
    away = put(w, claim_body(observed_at='2026-09-01T00:00:00Z'))
    events = api.get(f'/identities/{BEAM}/timeline',
                     headers=w['m']).json()['events']
    kinds = [e['kind'] for e in events]
    assert kinds.count('snapshot') == 2 and 'exit' in kinds
    assert 'metadata_changed' in kinds
    changed = [e for e in events if e['kind'] == 'metadata_changed'][0]
    assert 'trade_name' in changed['paths']
    sections = {e['record_id']: e['section'] for e in events
                if e['kind'] == 'evidence'}
    assert sections[early['_id']] == 'before_cataloguing'
    assert sections[away['_id']] == 'after_leaving_circulation'
    assert sections[mid['_id']] == 'history'
    ats = [e['at'] for e in events if e['at']]
    assert ats == sorted(ats)
    # outside the dataset only the date of a metadata change shows (8.36)
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    outside = api.get(f'/identities/{BEAM}/timeline',
                      headers=w['user']).json()['events']
    changed = [e for e in outside if e['kind'] == 'metadata_changed'][0]
    assert 'paths' not in changed and changed['at']
    anonymous = api.get(f'/identities/{BEAM}/timeline')
    assert anonymous.status_code == 200
    # a draft is not on anybody's timeline but its author's
    draft = api.post(f'/identities/{BEAM}/evidence', json=clone(
        claim_body(), observed_at='2026-02-01T00:00:00Z'),
        headers=w['c']).json()
    ids = lambda who: {e.get('record_id') for e in api.get(  # noqa: E731
        f'/identities/{BEAM}/timeline', headers=who).json()['events']}
    assert draft['_id'] in ids(w['c']) and draft['_id'] in ids(w['m'])
    assert draft['_id'] not in ids(w['user'])
    # a withdrawn record is a bare row outside the dataset
    api.post(f'/evidence/{mid["_id"]}/withdraw', json={'reason': 'secret'},
             headers=w['admin'])
    outside = api.get(f'/identities/{BEAM}/timeline',
                      headers=w['user']).json()['events']
    row = [e for e in outside if e.get('record_id') == mid['_id']][0]
    assert row['status'] == 'withdrawn' and 'secret' not in str(row)
    assert row['quantity'] is None
