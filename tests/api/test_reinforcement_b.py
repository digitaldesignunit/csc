"""Reinforcement layouts, backend (decision 8.142 and RL10): the attachments a
correction carries, the document filled once, the position kind script, the
accuracy note an anonymous caller does not get."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import PDF, layout_body
from support import iid, seed_05_catalog, sid

BEAM = iid('beam')
V1 = sid('beam', 1)


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    c2, _ = member_headers({'dbu_zirkus': ['contributor']})
    m, _ = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': c, 'c2': c2, 'm': m,
            'admin': auth_headers('admin'),
            'root': os.environ['EVIDENCE_ATTACHMENTS_DIR']}


def drawing(**document):
    body = layout_body(V1)
    body['payload'] = {
        'basis': 'drawing',
        'document': {'title': 'Bewehrungsplan', **document},
        'bars': body['payload']['bars']}
    return body


def make(w, body, publish=False):
    created = w['api'].post(f'/identities/{BEAM}/evidence', json=body,
                            headers=w['c'])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    if publish:
        w['api'].post(f'/evidence/{eid}/submit', headers=w['c'])
        assert w['api'].post(f'/evidence/{eid}/publish', headers=w['m']
                             ).status_code == 200
    return eid


def attach(w, ids, data=PDF, name='plan.pdf', headers=None):
    return w['api'].post('/evidence/attachments',
                         data={'record_ids': list(ids)},
                         files={'file': (name, data, 'application/pdf')},
                         headers=headers or w['c'])


def stored(w, eid):
    return w['db']['component_evidence'].find_one({'_id': eid})


# RL4 -------------------------------------------------------------------------
def test_a_correction_carries_the_attachments_of_what_it_corrects(world):
    w = world
    old = make(w, drawing(), publish=True)
    assert attach(w, [old], headers=w['m']).status_code == 201
    other = attach(w, [old], data=PDF + b'\n% second', name='detail.pdf',
                   headers=w['m'])
    assert other.status_code == 201, other.text
    # a removed attachment (tombstone) is not carried
    assert w['api'].delete(f'/evidence/{old}/attachments/1',
                           params={'reason': 'wrong file'},
                           headers=w['m']).status_code == 200
    response = w['api'].post(f'/evidence/{old}/supersede', json=drawing(),
                             headers=w['c'])
    assert response.status_code == 201, response.text
    new = response.json()['_id']
    carried = stored(w, new)['attachments']
    assert [(a['index'], a['name']) for a in carried] == [(0, 'plan.pdf')]
    assert carried[0]['sha256'] == stored(w, old)['attachments'][0]['sha256']
    assert carried[0]['removed'] is None
    first = os.path.join(w['root'], old, '0.pdf')
    second = os.path.join(w['root'], new, '0.pdf')
    assert os.path.exists(second)
    assert os.path.samefile(first, second)                # a hard link
    # the original keeps all its entries and files
    assert len(stored(w, old)['attachments']) == 2
    # the author of the pending correction adds a new file and removes the
    # carried one; the original's file stays
    added = attach(w, [new], data=PDF + b'\n% new', name='new.pdf')
    assert added.status_code == 201, added.text
    assert w['api'].delete(f'/evidence/{new}/attachments/0',
                           headers=w['c']).status_code == 200
    entries = stored(w, new)['attachments']
    assert [(a['index'], a['name'], bool(a['removed'])) for a in entries] == [
        (0, 'plan.pdf', True), (1, 'new.pdf', False)]
    assert not os.path.exists(second) and os.path.exists(first)
    # another contributor may not touch the correction's files
    assert attach(w, [new], data=PDF + b'\n% x', name='x.pdf',
                  headers=w['c2']).status_code == 403
    assert w['api'].delete(f'/evidence/{new}/attachments/1',
                           headers=w['c2']).status_code == 403


def test_a_correction_without_attachments_stays_without(world):
    w = world
    old = make(w, drawing(), publish=True)
    new = w['api'].post(f'/evidence/{old}/supersede', json=drawing(),
                        headers=w['c']).json()['_id']
    assert stored(w, new)['attachments'] == []


# RL5 -------------------------------------------------------------------------
def test_a_moderator_fills_the_empty_document_fields_once(world):
    w = world
    eid = make(w, drawing(), publish=True)                 # only a title
    api = w['api']
    fill = {'payload': {'document': {'reference': 'Plan 12', 'date': '1968-03',
                                     'url': 'https://archive.example.org/12',
                                     'retrieved_at': '2026-10-05'}}}
    assert api.patch(f'/evidence/{eid}', json=fill,
                     headers=w['c']).status_code == 403    # not the author
    got = api.patch(f'/evidence/{eid}', json=fill, headers=w['m'])
    assert got.status_code == 200, got.text
    document = got.json()['payload']['document']
    assert document == {'title': 'Bewehrungsplan', 'reference': 'Plan 12',
                        'date': '1968-03',
                        'url': 'https://archive.example.org/12',
                        'retrieved_at': '2026-10-05'}
    assert got.json()['status'] == 'published'
    # change-logged
    entries = list(w['db']['change_log'].find({'record_id': eid}))
    assert any(c['path'] == 'payload' for e in entries for c in e['changes'])
    # a set value changes only through a correction
    again = api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'reference': 'Plan 13'}}}, headers=w['m'])
    assert again.status_code == 409 and 'supersede' in str(again.json())
    # the title is set, and the rest of the payload stays frozen
    assert api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'title': 'Other'}}}, headers=w['m']).status_code == 409
    assert api.patch(f'/evidence/{eid}', json={'payload': {
        'basis': 'scan'}}, headers=w['m']).status_code == 409
    assert api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'color': 'x'}}}, headers=w['m']).status_code == 422


def test_a_layout_without_a_document_gets_one_with_a_title(world):
    w = world
    eid = make(w, layout_body(V1), publish=True)           # a scan, no document
    api = w['api']
    no_title = api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'reference': 'R'}}}, headers=w['m'])
    assert no_title.status_code == 422
    ok = api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'title': 'Drawing found later', 'url': 'javascript:alert(1)'}}},
        headers=w['m'])
    assert ok.status_code == 422                           # only http(s)
    good = api.patch(f'/evidence/{eid}', json={'payload': {'document': {
        'title': 'Drawing found later'}}}, headers=w['m'])
    assert good.status_code == 200, good.text
    assert good.json()['payload']['document'] == {'title': 'Drawing found later'}


def test_only_a_published_layout_is_filled_this_way(world):
    w = world
    draft = make(w, drawing())
    # a draft is edited the ordinary way
    got = w['api'].patch(f'/evidence/{draft}', json={'payload': drawing(
        reference='R')['payload']}, headers=w['c'])
    assert got.status_code == 200, got.text


# RL7 -------------------------------------------------------------------------
def _script():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'db_maintenance' \
        / 'layout_position_none.py'
    spec = importlib.util.spec_from_file_location('layout_position_none', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_converts_region_layouts_and_nothing_else(world):
    w = world
    a = make(w, layout_body(V1, position={'kind': 'region',
                                           'snapshot_id': V1,
                                           'description': 'north face'}))
    b = make(w, layout_body(V1))                           # already none
    module = _script()
    dry = module.convert(w['db'])
    assert dry == {'found': 1, 'changed': 0, 'ids': [a]}
    assert stored(w, a)['position']['kind'] == 'region'    # nothing written
    done = module.convert(w['db'], apply=True, now='2026-10-10T12:00:00Z')
    assert done == {'found': 1, 'changed': 1, 'ids': [a]}
    position = stored(w, a)['position']
    assert position['kind'] == 'none' and position['snapshot_id'] == V1
    assert position['description'] == 'north face'
    assert stored(w, b)['position']['kind'] == 'none'
    entry = w['db']['change_log'].find_one({'record_id': a,
                                            'cause': 'migration'})
    assert entry and any(c['path'] == 'position' for c in entry['changes'])
    # idempotent
    assert module.convert(w['db'], apply=True) == {
        'found': 0, 'changed': 0, 'ids': []}


# RL10 ------------------------------------------------------------------------
def test_an_anonymous_caller_does_not_get_the_accuracy_note(world):
    w = world
    body = layout_body(V1)
    body['payload']['accuracy_note'] = 'size and cover +-20 %, neither known'
    eid = make(w, body, publish=True)
    w['db']['component_identities'].update_one({'_id': BEAM},
                                               {'$set': {'is_public': True}})
    api = w['api']
    signed_in = api.get(f'/evidence/{eid}', headers=w['c']).json()
    assert signed_in['payload']['accuracy_note'].startswith('size and cover')
    for path, params in ((f'/evidence/{eid}', {}),
                         (f'/identities/{BEAM}/evidence', {}),
                         (f'/identities/{BEAM}/compose',
                          {'include': 'evidence'}),
                         (f'/identities/{BEAM}/compose',
                          {'include': 'evidence', 'format': 'jsonld'})):
        got = api.get(path, params=params)
        assert got.status_code == 200, (path, got.text)
        assert 'accuracy_note' not in got.text, path
        assert 'neither known' not in got.text, path
        signed = api.get(path, params=params, headers=w['c'])
        assert 'neither known' in signed.text, path
    pdf = api.get(f'/identities/{BEAM}/export/pdf')
    assert pdf.status_code == 200
