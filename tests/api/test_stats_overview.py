"""
The overview part of ``GET /identities/stats`` (decision 8.173): the range of
each sorted side, the pieces with a point on each location layer and the
counted pieces that are not public, next to the counts the web already reads.
"""

from __future__ import annotations

import pytest

from test_near_search import PIECES, _insert

OLD_KEYS = {
    'total', 'byOriginalFunction', 'byShapeClass', 'byMaterial', 'byDataset', 'byComplexity', 'byStatus',
    'byFragment', 'reserved', 'byCirculation', 'pieces', 'descriptorsKeys', 'createdMonthly', 'bbxX',
}


@pytest.fixture
def world(api, db, auth_headers):
    for number, (current, origin, dataset, public, bbx) in PIECES.items():
        _insert(db, number, current, origin, dataset, public, bbx)
    return {'api': api, 'db': db, 'admin': auth_headers('admin'), 'user': auth_headers('user')}


def _stats(world, who='admin', **params):
    response = world['api'].get('/identities/stats', params=params, headers=world.get(who) if who else None)
    assert response.status_code == 200, response.text
    return response.json()


# PIECES (current, origin, dataset, public, bbx)
#   1 DA, origin Berlin, 1200x600x200   2 DA, 200^3            3 FRA, origin (49.9, 8.7), 1200x600x200
#   4 BER, 1200x600x200                 5 no current, origin FRA, 300^3
#   6 DA, private, 1200x600x200         7 nothing, 1200x600x200   8 DA, 1250x600x200


def test_the_web_keys_are_unchanged_and_the_overview_is_added(world):
    stats = _stats(world)
    assert OLD_KEYS <= set(stats)
    assert {'sideRanges', 'withLocation', 'notPublic'} <= set(stats)
    assert stats['total'] == 8


def test_the_range_of_each_sorted_side(world):
    sides = _stats(world)['sideRanges']
    assert sides['count'] == 8
    assert sides['largest'] == {'min': 200, 'max': 1250}       # piece 2 is 200^3, piece 8 has 1250
    assert sides['middle'] == {'min': 200, 'max': 600}
    assert sides['smallest'] == {'min': 200, 'max': 300}
    # a filter narrows it
    only = _stats(world, dataset='other')['sideRanges']
    assert only['count'] == 1 and only['largest'] == {'min': 1200, 'max': 1200}


def test_the_bbx_facet_buckets_in_millimetres(world):
    # the label of a bucket is its lower edge, in mm: 200 and 300 are small pieces, not "0 to 1 m"
    rows = _stats(world)['bbxX']
    assert {r['label']: r['count'] for r in rows} == {'100': 1, '250': 1, '1000': 6}
    db = world['db']
    db['component_snapshots'].update_one({'_id': 's08'}, {'$set': {'bbx': [12000, 600, 200]}})
    db['component_snapshots'].update_one({'_id': 's07'}, {'$set': {'bbx': [60, 40, 30]}})
    labels = {r['label']: r['count'] for r in _stats(world)['bbxX']}
    assert labels == {'0': 1, '100': 1, '250': 1, '1000': 4, '>=10000': 1}
    assert sum(labels.values()) == 8


def test_the_bbx_facet_buckets_the_largest_side_whatever_the_stored_order(world):
    db = world['db']
    # 600 x 200 x 1200 is a piece of 1200: bucket "1000", not "500" (the first stored side)
    for number, bbx in ((1, [600, 200, 1200]), (2, [200, 1200, 600]), (3, [1200, 600, 200])):
        db['component_snapshots'].update_one({'_id': f's{number:02d}'}, {'$set': {'bbx': bbx}})
    labels = {r['label']: r['count'] for r in _stats(world, dataset='d', q='piece 1')['bbxX']}
    assert labels == {'1000': 1}
    mixed = {r['label']: r['count'] for r in _stats(world)['bbxX']}
    assert mixed == {'250': 1, '1000': 7}                          # piece 5 is 300^3, the rest 1200 and more


def test_a_piece_without_a_size_is_in_no_bbx_bucket(world):
    db = world['db']
    db['component_snapshots'].update_one({'_id': 's01'}, {'$unset': {'bbx': ''}})
    db['component_snapshots'].update_one({'_id': 's02'}, {'$set': {'bbx': [1, 2]}})
    db['component_snapshots'].update_one({'_id': 's03'}, {'$set': {'bbx': [1, 'x', 3]}})
    stats = _stats(world)
    labels = {r['label']: r['count'] for r in stats['bbxX']}
    assert labels == {'250': 1, '1000': 4}                          # 5 (300^3) and 4, 6, 7, 8; not 1, 2, 3
    assert '>=10000' not in labels and stats['total'] == 8


def test_a_piece_without_three_numbers_has_no_size_and_is_not_in_a_range(world):
    db = world['db']
    db['component_snapshots'].update_one({'_id': 's01'}, {'$unset': {'bbx': ''}})
    db['component_snapshots'].update_one({'_id': 's02'}, {'$set': {'bbx': [1, 2]}})
    db['component_snapshots'].update_one({'_id': 's03'}, {'$set': {'bbx': [1, 'x', 3]}})
    sides = _stats(world)['sideRanges']
    assert sides['count'] == 5                                   # 4, 5, 6, 7 and 8
    assert sides['largest'] == {'min': 300, 'max': 1250}
    assert _stats(world, q='piece 1')['sideRanges'] == {'count': 0, 'largest': None, 'middle': None,
                                                         'smallest': None}


def test_equal_sides_and_the_order_in_which_they_are_stored_do_not_matter(world):
    db = world['db']
    for number, bbx in ((1, [200, 1200, 600]), (2, [600, 200, 1200]), (3, [1200, 600, 200])):
        db['component_snapshots'].update_one({'_id': f's{number:02d}'}, {'$set': {'bbx': bbx}})
    sides = _stats(world, dataset='d', q='piece 1')['sideRanges']
    assert sides['largest'] == {'min': 1200, 'max': 1200} and sides['smallest'] == {'min': 200, 'max': 200}
    allthree = _stats(world, q='piece')['sideRanges']
    assert allthree['largest']['max'] == 1250


def test_the_pieces_with_a_point_on_each_layer_are_counted(world):
    assert _stats(world)['withLocation'] == {'current': 6, 'origin': 3}
    assert _stats(world, dataset='other')['withLocation'] == {'current': 1, 'origin': 0}
    assert _stats(world, q='piece 5')['withLocation'] == {'current': 0, 'origin': 1}
    # a point is an object: a piece whose field is null or missing is not counted
    world['db']['component_identities'].update_one({'_id': 'i01'}, {'$set': {'geo_current': None}})
    assert _stats(world)['withLocation']['current'] == 5


def test_the_counted_pieces_that_are_not_public(world):
    assert _stats(world)['notPublic'] == 1                       # the administrator sees piece 6
    assert _stats(world, dataset='other')['notPublic'] == 1
    # someone without a role sees the public pieces only
    for who in ('user', None):
        seen = _stats(world, who=who)
        assert seen['total'] == 7 and seen['notPublic'] == 0
        assert seen['sideRanges']['count'] == 7 and seen['withLocation'] == {'current': 5, 'origin': 3}
    world['db']['component_identities'].update_one({'_id': 'i01'}, {'$set': {'is_public': False}})
    assert _stats(world)['notPublic'] == 2


def test_the_overview_follows_a_fit_and_a_near_search(world):
    held = _stats(world, fit_mode='can_hold', fit_size='1200,600,200')
    assert held['total'] == 6 and held['sideRanges']['smallest'] == {'min': 200, 'max': 200}
    near = _stats(world, near_lat=49.8728, near_lon=8.6512, radius_km=30)
    assert near['total'] == 5 and near['withLocation']['current'] == 5


def test_a_bbx_that_is_no_array_does_not_break_the_stats(world):
    """One bad document must not 500 the stats for everyone: its size counts for
    nothing, in the sides and in the old size buckets (bbxX)."""
    world['db']['component_snapshots'].update_one({'_id': 's04'}, {'$set': {'bbx': 'big'}})
    world['db']['component_snapshots'].update_one({'_id': 's05'}, {'$set': {'bbx': {'x': 1}}})
    stats = _stats(world)
    assert stats['total'] == 8
    assert stats['sideRanges']['count'] == 6                     # 1, 2, 3, 6, 7 and 8; not 4 and 5
    assert 'bbxX' in stats
