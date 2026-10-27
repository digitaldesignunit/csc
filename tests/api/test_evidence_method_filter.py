"""
Search by evidence method (decision 8.177): ``evidence_method`` on the catalog
list, count, stats, location and map routes against a real database. Only
pieces with at least one published evidence record of that method are listed;
the filter combines with every other filter and keeps the access rules.
``/identities/{id}/similar`` is tested in ``test_similarity.py``.
"""

from __future__ import annotations

import uuid

import pytest

from apps.catalog.geo import point_of
from apps.catalog.vocab import EVIDENCE_METHODS

PIECES = {
    # catalog number: (bbx, dataset, public, point)
    1: ([1200, 600, 200], 'd', True, (49.8728, 8.6512)),     # published layout
    2: ([1200, 600, 200], 'd', True, (52.52, 13.405)),       # published layout, far away
    3: ([1200, 600, 200], 'd', True, (49.8728, 8.6512)),     # only a pending layout
    4: ([300, 300, 300], 'd', True, (49.8728, 8.6512)),      # published layout, too small
    5: ([1200, 600, 200], 'other', False, None),             # private, published layout
    6: ([1200, 600, 200], 'd', True, None),                  # only a withdrawn layout
    7: ([1200, 600, 200], 'd', True, None),                  # a rebound hammer only
    8: ([1200, 600, 200], 'd', True, None),                  # no evidence
}
# (catalog number, method, status)
EVIDENCE = [
    (1, 'reinforcement_layout', 'published'),
    (1, 'reinforcement_layout', 'published'),                # two records: still one piece
    (1, 'rebound_hammer', 'published'),
    (2, 'reinforcement_layout', 'published'),
    (3, 'reinforcement_layout', 'pending'),
    (4, 'reinforcement_layout', 'published'),
    (5, 'reinforcement_layout', 'published'),
    (6, 'reinforcement_layout', 'withdrawn'),
    (7, 'rebound_hammer', 'published'),
]


def _id(n):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'csc-test/evmethod/{n}'))


@pytest.fixture
def world(api, db, auth_headers):
    for number, (bbx, dataset, public, point) in PIECES.items():
        identity_id, snapshot_id = _id(number), _id(f's{number}')
        identity = {
            '_id': identity_id, 'catalog_number': number, 'dataset': dataset,
            'original_function': 'IfcBeam', 'material': 'concrete',
            'material_class': '17 01 01', 'is_public': public,
            'current_snapshot_id': snapshot_id, 'exit': None,
            'withdrawn': None, 'created': '2026-01-01T00:00:00Z',
            'lastmodified': '2026-01-01T00:00:00Z',
            'created_by_user_id': 'u-test'}
        snapshot = {
            '_id': snapshot_id, 'identity_id': identity_id, 'version': 1,
            'status': 'published', 'name': f'piece {number}', 'bbx': bbx,
            'created': '2026-01-01T00:00:00Z',
            'lastmodified': '2026-01-01T00:00:00Z',
            'effective_from': '2026-01-01T00:00:00Z', 'geometry': {},
            'added_by_user_id': 'u-test'}
        if point:
            identity['geo_current'] = point_of({'lat': point[0], 'lon': point[1]})
            snapshot['location'] = {'lat': point[0], 'lon': point[1]}
        db['component_identities'].insert_one(identity)
        db['component_snapshots'].insert_one(snapshot)
    for number, method, status in EVIDENCE:
        # the filter reads the identity, the method and the status only
        db['component_evidence'].insert_one({
            '_id': str(uuid.uuid4()), 'identity_id': _id(number),
            'method': method, 'status': status})
    return {'api': api, 'db': db, 'admin': auth_headers('admin'),
            'user': auth_headers('user')}


def _get(world, path, who='admin', expect=200, **params):
    response = world['api'].get(path, params=params,
                                headers=world.get(who) if who else None)
    assert response.status_code == expect, response.text
    return response.json()


def _numbers(rows):
    return sorted(row['catalog_number'] for row in rows)


def _list(world, **params):
    return _numbers(_get(world, '/identities', size=50, **params))


LAYOUT = 'reinforcement_layout'


def test_the_list_has_the_pieces_with_a_published_record_of_the_method(world):
    # a pending (3) or withdrawn (6) record does not count; two records (1) are one piece
    assert _list(world, evidence_method=LAYOUT) == [1, 2, 4, 5]
    assert _list(world, evidence_method='rebound_hammer') == [1, 7]
    assert _list(world, evidence_method='core_compression') == []
    assert _list(world) == [1, 2, 3, 4, 5, 6, 7, 8]            # no filter: as before


def test_every_method_of_the_vocabulary_is_accepted_and_an_unknown_one_is_a_422(world):
    for method in EVIDENCE_METHODS:
        _get(world, '/identities', evidence_method=method)
    for bad in ('x_ray', 'Reinforcement_Layout', 'reinforcement'):
        for path in ('/identities', '/identities/count', '/identities/stats',
                     '/identities/locations'):
            _get(world, path, expect=422, evidence_method=bad)


def test_it_combines_with_the_other_filters(world):
    assert _list(world, evidence_method=LAYOUT, dataset='other') == [5]
    assert _list(world, evidence_method=LAYOUT, dataset='d') == [1, 2, 4]
    assert _list(world, evidence_method=LAYOUT, q='piece 2') == [2]
    assert _list(world, evidence_method=LAYOUT, q='piece 3') == []
    # a dimension search: the small piece (4) cannot hold the box, the piece without layout is out
    held = _get(world, '/identities', size=50, evidence_method=LAYOUT, fit_mode='can_hold', fit_size='1200,600,200')
    assert _numbers(held) == [1, 2, 5] and all(r['fit']['mode'] == 'can_hold' for r in held)
    # a near search: within 30 km of Darmstadt, with the distance
    near = _get(world, '/identities', size=50, evidence_method=LAYOUT, near_lat=49.8728, near_lon=8.6512,
                radius_km=30)
    assert _numbers(near) == [1, 4] and all('distance_m' in r for r in near)
    both = _get(world, '/identities', size=50, evidence_method=LAYOUT, near_lat=49.8728, near_lon=8.6512,
                radius_km=30, fit_mode='can_hold', fit_size='1200,600,200')
    assert _numbers(both) == [1]


def test_the_access_rules_stay_as_they_are(world):
    # the private piece (5) is the administrator's, not the other account's
    assert _list(world, evidence_method=LAYOUT, status='published') == [1, 2, 4, 5]
    response = world['api'].get('/identities', params={'evidence_method': LAYOUT, 'size': 50})
    assert response.status_code == 200
    assert _numbers(response.json()) == [1, 2, 4]
    anonymous = world['api'].get('/identities/count', params={'evidence_method': LAYOUT}).json()
    assert anonymous['count'] == 3


def test_count_and_stats_agree_with_the_list(world):
    for params in ({'evidence_method': LAYOUT}, {'evidence_method': 'rebound_hammer'},
                   {'evidence_method': LAYOUT, 'dataset': 'd'},
                   {'evidence_method': 'core_compression'}):
        rows = _get(world, '/identities', size=50, **params)
        assert _get(world, '/identities/count', **params)['count'] == len(rows), params
        assert _get(world, '/identities/stats', **params)['total'] == len(rows), params
    stats = _get(world, '/identities/stats', evidence_method=LAYOUT)
    assert stats['total'] == 4
    assert {row['label']: row['count'] for row in stats['byDataset']} == {'d': 3, 'other': 1}


def test_the_location_route_follows_the_filter(world):
    located = _get(world, '/identities/locations', evidence_method=LAYOUT)
    ids = {p['id'] for p in located['points']}
    assert ids == {_id(1), _id(2), _id(4)}                      # 5 and the rest have no point or no layout


def test_a_piece_gains_the_match_when_its_pending_record_is_published(world):
    assert 3 not in _list(world, evidence_method=LAYOUT)
    world['db']['component_evidence'].update_many(
        {'identity_id': _id(3)}, {'$set': {'status': 'published'}})
    assert 3 in _list(world, evidence_method=LAYOUT)


def test_a_superseded_record_does_not_count_only_a_current_one_does(world):
    evidence = world['db']['component_evidence']
    # piece 4: its only layout is superseded by a later record (which is not
    # of the method, as after a correction to another method) -> not listed
    evidence.update_many({'identity_id': _id(4)}, {'$set': {'superseded_by': str(uuid.uuid4())}})
    assert _list(world, evidence_method=LAYOUT) == [1, 2, 5]
    # piece 1 has two layouts: one superseded, one current -> still listed
    first = evidence.find_one({'identity_id': _id(1), 'method': LAYOUT})
    evidence.update_one({'_id': first['_id']}, {'$set': {'superseded_by': str(uuid.uuid4())}})
    assert _list(world, evidence_method=LAYOUT) == [1, 2, 5]
    # both superseded -> piece 1 drops out; its rebound hammer is untouched
    evidence.update_many({'identity_id': _id(1), 'method': LAYOUT}, {'$set': {'superseded_by': str(uuid.uuid4())}})
    assert _list(world, evidence_method=LAYOUT) == [2, 5]
    assert _list(world, evidence_method='rebound_hammer') == [1, 7]
    # count and stats follow the same rule
    assert _get(world, '/identities/count', evidence_method=LAYOUT)['count'] == 2
    assert _get(world, '/identities/stats', evidence_method=LAYOUT)['total'] == 2
    # an explicit null counts as current, like a missing field (the fixture)
    evidence.update_many({'identity_id': _id(1), 'method': LAYOUT}, {'$set': {'superseded_by': None}})
    assert _list(world, evidence_method=LAYOUT) == [1, 2, 5]
