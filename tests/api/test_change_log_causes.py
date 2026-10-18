"""The change log writes one entry per write, with the cause of the action
and the time of the record (decision 8.159); a status step of a snapshot is
a ``status_history`` entry and no change-log entry (8.30); a log entry that
cannot be written does not fail the request."""

from __future__ import annotations

import logging

import pytest
from pymongo.errors import AutoReconnect

from evidence_samples import PDF, claim_body, rebound_body
from support import sid
from test_evidence_routes import (  # noqa: F401  (world is a fixture)
    BEAM,
    OBS,
    published,
    step,
    world,
)

CAUSES = ('patch', 'inherited_from_parent', 'material_merge', 'exit', 'reenter', 'withdraw',
          'reinstate', 'migration', 'derived_exit', 'deinstall', 'undo_deinstall', 'verify',
          'publish', 'attach', 'redact')


def entries(w, record_id):
    return list(w['db']['change_log'].find({'record_id': record_id}).sort('at', 1))


def one_new(w, record_id, before, cause, record_kind, collection):
    """Exactly one entry came with the write, with the cause and the record's time."""
    now = entries(w, record_id)
    assert len(now) == before + 1, [e['cause'] for e in now]
    entry = now[-1]
    assert entry['cause'] == cause and entry['record_kind'] == record_kind
    assert entry['at'] == w['db'][collection].find_one({'_id': record_id})['lastmodified']
    return entry


def test_the_causes_are_a_fixed_list():
    from apps.catalog.vocab import CHANGE_CAUSE_LABELS, CHANGE_CAUSES
    assert tuple(CHANGE_CAUSES) == CAUSES
    assert set(CHANGE_CAUSE_LABELS) == set(CAUSES)


def test_a_cause_outside_the_list_is_refused(world):
    from apps.catalog.documents import ChangeLogEntry
    from pydantic import ValidationError
    base = {'_id': 'x', 'record_kind': 'identity', 'record_id': 'y', 'identity_id': 'y',
            'at': '2026-01-01T00:00:00Z', 'changes': [{'path': 'a', 'old': 1, 'new': 2}]}
    assert ChangeLogEntry.model_validate({**base, 'cause': 'verify'})
    with pytest.raises(ValidationError):
        ChangeLogEntry.model_validate({**base, 'cause': 'because'})


# IDENTITY --------------------------------------------------------------------
def test_identity_writes_name_their_action(world):
    w, api = world, world['api']
    admin = w['admin']
    before = len(entries(w, BEAM))
    assert api.patch(f'/identities/{BEAM}', json={'trade_name': 'Alpha'},
                     headers=w['m']).status_code == 200
    one_new(w, BEAM, before, 'patch', 'identity', 'component_identities')
    before = len(entries(w, BEAM))
    assert api.post(f'/identities/{BEAM}/exit', json={
        'kind': 'installed', 'at': '2026-08-01T00:00:00Z'}, headers=admin).status_code == 200
    one_new(w, BEAM, before, 'exit', 'identity', 'component_identities')
    before = len(entries(w, BEAM))
    assert api.post(f'/identities/{BEAM}/reenter', json={'origin': {
        'kind': 'deinstallation', 'at': '2026-10-01T00:00:00Z', 'at_precision': 'day'}},
        headers=admin).status_code == 200
    one_new(w, BEAM, before, 'reenter', 'identity', 'component_identities')
    before = len(entries(w, BEAM))
    assert api.post(f'/identities/{BEAM}/withdraw', json={'reason': 'x'},
                    headers=w['m']).status_code == 200
    one_new(w, BEAM, before, 'withdraw', 'identity', 'component_identities')
    before = len(entries(w, BEAM))
    assert api.post(f'/identities/{BEAM}/reinstate', headers=w['m']).status_code == 200
    one_new(w, BEAM, before, 'reinstate', 'identity', 'component_identities')


# SNAPSHOT --------------------------------------------------------------------
def test_a_snapshot_patch_is_logged_and_a_status_step_is_not(world):
    w, api = world, world['api']
    v1 = sid('beam', 1)
    before = len(entries(w, v1))
    assert api.patch(f'/snapshots/{v1}', json={'name': 'Renamed'},
                     headers=w['m']).status_code == 200
    one_new(w, v1, before, 'patch', 'snapshot', 'component_snapshots')
    # a status step: one status_history entry, no change-log entry
    import trimesh
    box = trimesh.creation.box(extents=(300, 200, 150))
    geometry = {'meshes': [{'vertices': box.vertices.tolist(), 'faces': box.faces.tolist()}],
                'point_clouds': [], 'proxies': []}
    draft = api.post(f'/identities/{BEAM}/snapshots', json={'geometry': geometry},
                     headers=w['c'])
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()['_id']
    history = len(w['db']['component_snapshots'].find_one({'_id': draft_id})['status_history'])
    logged = w['db']['change_log'].count_documents({'record_id': draft_id})
    assert api.post(f'/snapshots/{draft_id}/submit', headers=w['c']).status_code == 200
    stored = w['db']['component_snapshots'].find_one({'_id': draft_id})
    assert len(stored['status_history']) == history + 1 and stored['status'] == 'pending'
    assert w['db']['change_log'].count_documents({'record_id': draft_id}) == logged


# EVIDENCE --------------------------------------------------------------------
def test_evidence_writes_name_their_action(world):
    w, api = world, world['api']
    record = published(w, claim_body())
    eid = record['_id']
    before = len(entries(w, eid))
    done = api.put(f'/evidence/{eid}/verification', json={'state': 'reviewed', 'note': 'ok'},
                   headers=w['r'])
    assert done.status_code == 200, done.text
    one_new(w, eid, before, 'verify', 'evidence', 'component_evidence')
    before = len(entries(w, eid))
    assert api.patch(f'/evidence/{eid}', json={'notes': 'later'},
                     headers=w['m']).status_code == 200
    one_new(w, eid, before, 'patch', 'evidence', 'component_evidence')
    before = len(entries(w, eid))
    attached = api.post('/evidence/attachments', data={'record_ids': [eid]},
                        files={'file': ('r.pdf', PDF, 'application/pdf')}, headers=w['m'])
    assert attached.status_code == 201, attached.text
    one_new(w, eid, before, 'attach', 'evidence', 'component_evidence')
    before = len(entries(w, eid))
    assert api.delete(f'/evidence/{eid}/attachments/0', params={'reason': 'wrong file'},
                      headers=w['m']).status_code == 200
    one_new(w, eid, before, 'redact', 'evidence', 'component_evidence')


def test_a_correction_logs_the_predecessor_with_the_action_that_moved_it(world):
    w, api = world, world['api']
    old = published(w, rebound_body(observed_at=OBS))
    old_id = old['_id']
    first = api.post(f'/evidence/{old_id}/supersede',
                     json=rebound_body(observed_at=OBS, readings=[44] * 9),
                     headers=w['c']).json()
    before = len(entries(w, old_id))
    step(w, first['_id'], 'publish', w['m'])
    one_new(w, old_id, before, 'publish', 'evidence', 'component_evidence')
    before = len(entries(w, old_id))
    step(w, first['_id'], 'withdraw', w['m'], reason='wrong')
    one_new(w, old_id, before, 'withdraw', 'evidence', 'component_evidence')
    before = len(entries(w, old_id))
    assert api.post(f'/evidence/{first["_id"]}/reinstate', headers=w['m']).status_code == 200
    one_new(w, old_id, before, 'reinstate', 'evidence', 'component_evidence')


# MATERIALS -------------------------------------------------------------------
def test_a_material_merge_logs_after_the_write_with_the_time_of_the_record(world):
    w, api = world, world['api']
    db = w['db']
    using = [d for d in db['component_identities'].find(
        {'material': 'concrete', 'material_class_source': 'derived'})]
    assert using, 'the seeded catalogue has a concrete piece with a derived class'
    merged = api.post('/materials/concrete/merge', json={'into': 'steel'}, headers=w['admin'])
    assert merged.status_code == 200, merged.text
    for identity in using:
        entry = [e for e in entries(w, identity['_id']) if e['cause'] == 'material_merge']
        assert len(entry) == 1, identity['_id']
        stored = db['component_identities'].find_one({'_id': identity['_id']})
        assert entry[0]['at'] == stored['lastmodified'] and stored['material'] == 'steel'


# A LOG ENTRY THAT CANNOT BE WRITTEN --------------------------------------------
def test_a_failed_log_entry_does_not_fail_the_request(world, app, monkeypatch, caplog):
    class Broken:
        async def insert_one(self, *_args, **_kwargs):
            raise AutoReconnect('the log is gone')

    monkeypatch.setattr(app, 'mongodb_change_log', Broken())
    with caplog.at_level(logging.ERROR, logger='csc'):
        response = world['api'].patch(f'/identities/{BEAM}', json={'trade_name': 'Beta'},
                                      headers=world['m'])
    assert response.status_code == 200, response.text
    assert world['db']['component_identities'].find_one({'_id': BEAM})['trade_name'] == 'Beta'
    lost = [r for r in caplog.records if 'change log entry lost' in r.getMessage()]
    assert lost and f'identity {BEAM}' in lost[0].getMessage() and lost[0].exc_info
