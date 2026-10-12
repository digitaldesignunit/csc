"""``GET /identities/{id}/history`` (decision 8.140 g, h): lanes, events,
links, stubs for what the caller may not see, the public tier, the cap of
twelve lanes, grouped or single evidence."""

from __future__ import annotations

import copy
import json

import pytest

from apps.catalog.lanes import first_version, lane_events, link_kind
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog

BEAM = iid('beam')


def uid(n):
    return f'bbbbbbbb-0000-4000-8000-{n:012d}'


ROOT, P1, P2, GP, C1, C2, GC = (uid(n) for n in range(1, 8))


def sn(identity_id, number):
    """A snapshot id, unique per piece and version."""
    return identity_id.replace('bbbbbbbb', f'cccc{number:04d}')


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    other, _ = member_headers({'schoenes_neues_feld': ['contributor']})
    beam = db['component_identities'].find_one({'_id': BEAM})

    def piece(identity_id, number, parents=(), dataset='dbu_zirkus',
              public=False, **extra):
        doc = copy.deepcopy(beam)
        doc.update({'_id': identity_id, 'catalog_number': number,
                    'dataset': dataset, 'is_public': public,
                    'parent_identities': list(parents),
                    'current_snapshot_id': sn(identity_id, 0),
                    'exit': None, 'withdrawn': None, 'past_cycles': [],
                    'origin': {'kind': 'deinstallation',
                               'at': '2020-01-01T00:00:00Z',
                               'at_precision': 'day', 'planned': False},
                    **extra})
        db['component_identities'].insert_one(doc)
        version(identity_id, 0, '2021-01-01T00:00:00Z', name=f'Piece {number}')

    def version(identity_id, number, at, name=None, **extra):
        db['component_snapshots'].insert_one({
            '_id': sn(identity_id, number),
            'identity_id': identity_id, 'version': number,
            'status': 'published', 'effective_from': at,
            'effective_from_precision': 'day', 'name': name,
            'supersedes': None, 'superseded_by': None,
            'added_by_user_id': cid, 'created': at, **extra})

    def record(identity_id, record_id, method, at, status='published'):
        db['component_evidence'].insert_one({
            '_id': record_id, 'identity_id': identity_id, 'method': method,
            'status': status, 'observed_at': at,
            'observed_at_precision': 'exact', 'superseded_by': None,
            'recorded_by_user_id': cid,
            'summary': {'quantity': 'rebound_number'}})

    piece(GP, 10, public=True)
    piece(P1, 11, [GP], public=True)
    piece(P2, 12, dataset='schoenes_neues_feld')            # not visible
    piece(ROOT, 20, [P1, P2], public=True)
    piece(C1, 30, [ROOT])
    piece(C2, 31, [ROOT], public=True)
    piece(GC, 40, [C1])
    return {'api': api, 'db': db, 'c': c, 'cid': cid, 'other': other,
            'admin': auth_headers('admin'), 'piece': piece,
            'version': version, 'record': record}


def history(w, identity_id=ROOT, headers=None, **params):
    return w['api'].get(f'/identities/{identity_id}/history', params=params,
                        headers=headers)


def lane(body, lane_id):
    return next(item for item in body['lanes'] if item['id'] == lane_id)


# VISIBILITY ------------------------------------------------------------------
def test_a_member_sees_the_lanes_and_a_stub_for_what_is_not_theirs(world):
    w = world
    got = history(w, headers=w['c'])
    assert got.status_code == 200, got.text
    body = got.json()
    assert body['root'] == ROOT and body['depth'] == 1 and body['more'] == 0
    ids = [item['id'] for item in body['lanes']]
    assert ids == [P1, P2, ROOT, C1, C2]            # parents above, children below
    assert [item['role'] for item in body['lanes']] == [
        'parent', 'parent', 'piece', 'child', 'child']
    assert [item['level'] for item in body['lanes']] == [-1, -1, 0, 1, 1]
    stub = lane(body, P2)
    assert stub == {'id': P2, 'level': -1, 'role': 'parent', 'visible': False,
                    'label': 'not visible'}          # nothing else leaks
    full = lane(body, ROOT)
    assert full['visible'] and full['catalog_number'] == 20
    assert full['name'] == 'Piece 20' and full['dataset'] == 'dbu_zirkus'
    # an admin sees all
    admin = history(w, headers=w['admin']).json()
    assert lane(admin, P2)['visible'] is True


def test_an_anonymous_caller_gets_public_pieces_only_and_no_people(world):
    w = world
    got = history(w)
    assert got.status_code == 200
    body = got.json()
    assert lane(body, ROOT)['visible'] and lane(body, P1)['visible']
    assert lane(body, C2)['visible']
    assert lane(body, C1)['visible'] is False        # not public
    assert lane(body, P2)['visible'] is False
    text = json.dumps(body)
    for key in ('user_id', 'username', 'recorded_by', 'added_by'):
        assert key not in text
    # a piece that is not public: 401 for anonymous, 403 for a stranger
    assert history(w, C1).status_code == 401
    assert history(w, C1, headers=w['other']).status_code == 403
    assert history(w, uid(999), headers=w['c']).status_code == 404
    assert w['api'].get('/identities/not-an-id/history').status_code in (400, 404, 422)


def test_a_draft_record_is_seen_by_its_author_only(world):
    w = world
    w['record'](ROOT, uid(101), 'rebound_hammer', '2026-03-01T10:00:00Z')
    w['record'](ROOT, uid(102), 'rebound_hammer', '2026-03-01T11:00:00Z',
                status='draft')
    own = lane(history(w, headers=w['c']).json(), ROOT)['events']
    group = next(e for e in own if e['kind'] == 'evidence_group')
    assert group['count'] == 2 and group['statuses'] == ['draft', 'published']
    anonymous = lane(history(w).json(), ROOT)['events']
    group = next(e for e in anonymous if e['kind'] == 'evidence_group')
    assert group['count'] == 1 and group['statuses'] == ['published']


# DEPTH, LINKS ----------------------------------------------------------------
def test_depth_two_adds_the_grandparent_and_the_grandchild(world):
    w = world
    one = history(w, headers=w['c'], depth=1).json()
    assert {item['id'] for item in one['lanes']} == {P1, P2, ROOT, C1, C2}
    two = history(w, headers=w['c'], depth=2).json()
    assert {item['id'] for item in two['lanes']} == {GP, P1, P2, ROOT, C1,
                                                     C2, GC}
    assert lane(two, GP)['level'] == -2 and lane(two, GC)['level'] == 2
    assert history(w, headers=w['c'], depth=3).status_code == 422


def test_a_cut_and_an_assembly_are_links_at_the_childs_first_version(world):
    w = world
    body = history(w, headers=w['c'], depth=2).json()
    links = {(link['from'], link['to']): link for link in body['links']}
    # the root has two parents: assembled; its first version starts the link
    assert links[(P1, ROOT)]['kind'] == 'assemble'
    assert links[(P2, ROOT)]['kind'] == 'assemble'
    assert links[(P1, ROOT)]['at'] == '2021-01-01T00:00:00Z'
    assert links[(P1, ROOT)]['version_id'] == sn(ROOT, 0)
    # a piece with one parent was cut
    assert links[(ROOT, C1)]['kind'] == 'cut'
    assert links[(ROOT, C2)]['kind'] == 'cut'
    assert links[(GP, P1)]['kind'] == 'cut'
    assert links[(C1, GC)]['kind'] == 'cut'
    assert len(body['links']) == 6


def test_links_into_a_stub_have_no_version(world):
    w = world
    w['db']['component_identities'].update_one({'_id': P2},
                                               {'$set': {'is_public': False}})
    body = history(w, C2, headers=w['c']).json()      # C2 is cut from ROOT only
    assert {link['kind'] for link in body['links']} == {'cut'}
    anonymous = history(w).json()
    link = next(item for item in anonymous['links'] if item['to'] == C1)
    assert link['kind'] == 'cut' and 'at' not in link      # C1 is a stub


# EVENTS ----------------------------------------------------------------------
def test_evidence_is_grouped_per_day_and_method_or_listed_singly(world):
    w = world
    for n, (method, at) in enumerate([
            ('rebound_hammer', '2026-03-01T08:00:00Z'),
            ('rebound_hammer', '2026-03-01T09:30:00Z'),
            ('rebound_hammer', '2026-03-01T17:00:00Z'),
            ('core_compression', '2026-03-01T10:00:00Z'),
            ('rebound_hammer', '2026-03-02T08:00:00Z')]):
        w['record'](ROOT, uid(200 + n), method, at)
    grouped = lane(history(w, headers=w['c']).json(), ROOT)['events']
    groups = [e for e in grouped if e['kind'] == 'evidence_group']
    assert [(e['day'], e['method'], e['count']) for e in groups] == [
        ('2026-03-01', 'rebound_hammer', 3),
        ('2026-03-01', 'core_compression', 1),
        ('2026-03-02', 'rebound_hammer', 1)]
    assert groups[0]['ids'] == [uid(200), uid(201), uid(202)]
    single = lane(history(w, headers=w['c'], expand='all').json(),
                  ROOT)['events']
    singles = [e for e in single if e['kind'] == 'evidence']
    assert len(singles) == 5 and not any(
        e['kind'] == 'evidence_group' for e in single)
    assert singles[0]['id'] == uid(200) and singles[0]['quantity']
    assert history(w, headers=w['c'], expand='nonsense').status_code == 422


def test_events_come_in_time_order_with_the_undated_first(world):
    w = world
    db = w['db']
    db['component_identities'].update_one({'_id': ROOT}, {'$set': {
        'origin': {'kind': 'deinstallation', 'at': None, 'planned': False},
        'exit': {'kind': 'recycled', 'at': '2030-06-01T00:00:00Z',
                 'at_precision': 'day'},
        'withdrawn': {'at': '2031-01-01T00:00:00Z'},
        'past_cycles': [{'origin': {'kind': 'unknown', 'at': '2010-01-01T00:00:00Z'},
                         'exit': {'kind': 'returned', 'at': '2015-01-01T00:00:00Z'}}]}})
    w['version'](ROOT, 1, None, name='Undated version')
    w['record'](ROOT, uid(300), 'rebound_hammer', '2025-05-05T05:00:00Z')
    events = lane(history(w, headers=w['c']).json(), ROOT)['events']
    kinds = [(e['kind'], e.get('at')) for e in events]
    assert kinds == [
        ('origin', None), ('version', None),                    # undated first
        ('origin', '2010-01-01T00:00:00Z'),                      # a past cycle
        ('exit', '2015-01-01T00:00:00Z'),
        ('version', '2021-01-01T00:00:00Z'),
        ('evidence_group', '2025-05-05T05:00:00Z'),
        ('exit', '2030-06-01T00:00:00Z'),
        ('withdrawal', '2031-01-01T00:00:00Z')]
    assert events[2]['cycle'] == 0 and events[3]['cycle'] == 0


def test_a_correction_shows_as_the_version_it_corrects(world):
    w = world
    w['db']['component_snapshots'].update_one(
        {'_id': sn(ROOT, 0)}, {'$set': {'superseded_by': sn(ROOT, 1)}})
    w['version'](ROOT, 1, '2021-01-01T00:00:00Z', name='Corrected',
                 supersedes=sn(ROOT, 0))
    w['version'](ROOT, 2, '2024-01-01T00:00:00Z', name='Later')
    events = [e for e in lane(history(w, headers=w['c']).json(), ROOT)['events']
              if e['kind'] == 'version']
    assert [(e['version'], e.get('corrected'), e.get('corrects')) for e in events] \
        == [(0, True, None), (0, None, sn(ROOT, 0)), (2, None, None)]
    # the link starts at the first version, the corrected one
    link = next(item for item in history(w, headers=w['c']).json()['links']
                if item['to'] == ROOT)
    assert link['version_id'] in (sn(ROOT, 0), sn(ROOT, 1))


# THE CAP ---------------------------------------------------------------------
def test_more_than_twelve_lanes_are_a_count(world):
    w = world
    for n in range(14):
        w['piece'](uid(500 + n), 100 + n, [ROOT])
    body = history(w, headers=w['c']).json()
    assert len(body['lanes']) == 12
    # root, parents (two), then children by number; the rest is counted
    assert body['more'] == (2 + 1 + 2 + 14) - 12
    assert lane(body, ROOT)['visible']
    assert {item['id'] for item in body['lanes']} >= {P1, P2, ROOT, C1, C2}
    assert all(link['from'] in {i['id'] for i in body['lanes']}
               and link['to'] in {i['id'] for i in body['lanes']}
               for link in body['links'])


# THE PURE PARTS --------------------------------------------------------------
def test_the_first_version_and_the_kind_of_a_link():
    snaps = [{'_id': 'b', 'version': 1, 'supersedes': 'a', 'created': '2'},
             {'_id': 'a', 'version': 0, 'supersedes': None, 'created': '1',
              'superseded_by': 'b'},
             {'_id': 'c', 'version': 2, 'supersedes': None, 'created': '3'}]
    assert first_version(snaps)['_id'] == 'a'
    assert first_version([]) is None
    assert link_kind({'parent_identities': ['x']}) == 'cut'
    assert link_kind({'parent_identities': ['x', 'y']}) == 'assemble'
    assert lane_events({'_id': 'i'}, [], []) == []
