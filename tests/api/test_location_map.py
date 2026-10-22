"""
The points of the location map (decisions 8.170, 8.171): ``GET
/identities/locations`` per layer, with the filters, the visibility and the
near and fit searches of the list, and the count of the pieces left out.
"""

from __future__ import annotations

import pytest

from test_near_search import (
    BERLIN,
    DARMSTADT,
    FRANKFURT,
    PIECES,
    _insert,
    metres,
)


@pytest.fixture
def world(api, db, auth_headers):
    for number, (current, origin, dataset, public, bbx) in PIECES.items():
        _insert(db, number, current, origin, dataset, public, bbx)
    return {'api': api, 'db': db, 'admin': auth_headers('admin'),
            'user': auth_headers('user')}


def _get(world, who='admin', status=200, **params):
    headers = world.get(who) if who else None
    response = world['api'].get('/identities/locations', params=params, headers=headers)
    assert response.status_code == status, response.text
    return response.json()


def _numbers(body):
    return [p['catalog_number'] for p in body['points']]


# PIECES (catalog number: current, origin, dataset, public)
#   1 Darmstadt, origin Berlin    2 Darmstadt            3 Frankfurt, origin (49.9, 8.7)
#   4 Berlin                      5 no current, origin Frankfurt
#   6 Darmstadt, private dataset  7 no point at all      8 Darmstadt


def test_the_current_layer_lists_the_pieces_with_a_current_point_and_counts_the_rest(world):
    body = _get(world)
    assert body['layer'] == 'current'
    assert _numbers(body) == [1, 2, 3, 4, 6, 8]            # by catalog number
    assert (body['total'], body['displayed'], body['left_out']) == (8, 6, 2)
    first = body['points'][0]
    assert (first['lat'], first['lon']) == pytest.approx(DARMSTADT, abs=1e-6)
    assert first['id'] == 'i01' and first['name'] == 'piece 1'
    assert first['dataset'] == 'd' and first['material'] == 'timber'
    assert first['original_function'] == 'IfcBeam'
    assert first['in_place'] is False
    third = body['points'][2]
    assert (third['lat'], third['lon']) == pytest.approx(FRANKFURT, abs=1e-6)


def test_the_origin_layer_lists_the_pieces_with_an_origin_point(world):
    body = _get(world, layer='origin')
    assert body['layer'] == 'origin'
    assert _numbers(body) == [1, 3, 5]
    assert (body['total'], body['displayed'], body['left_out']) == (8, 3, 5)
    by_number = {p['catalog_number']: p for p in body['points']}
    assert (by_number[1]['lat'], by_number[1]['lon']) == pytest.approx(BERLIN, abs=1e-6)
    assert (by_number[3]['lat'], by_number[3]['lon']) == pytest.approx((49.9, 8.7), abs=1e-6)


def test_a_layer_that_does_not_exist_is_refused(world):
    _get(world, status=422, layer='sky')


def test_a_layer_without_a_point_is_empty_and_says_how_many_are_left_out(world):
    world['db']['component_identities'].update_many({}, {'$unset': {'geo_origin': ''}})
    body = _get(world, layer='origin')
    assert body['points'] == [] and body['displayed'] == 0
    assert (body['total'], body['left_out']) == (8, 8)


def test_the_filters_of_the_list_apply_and_the_counts_follow_them(world):
    world['db']['component_identities'].update_one({'_id': 'i03'}, {'$set': {'material': 'steel'}})
    body = _get(world, material='steel')
    assert _numbers(body) == [3] and (body['total'], body['left_out']) == (1, 0)
    body = _get(world, dataset='other')
    assert _numbers(body) == [6]
    body = _get(world, q='piece 8')
    assert _numbers(body) == [8]
    # a piece with no point on the layer is counted as left out under the filter
    body = _get(world, layer='origin', q='piece 2')
    assert body['points'] == [] and (body['total'], body['left_out']) == (1, 1)


def test_a_fit_search_and_a_near_search_combine_with_the_map(world):
    fit = {'fit_mode': 'can_hold', 'fit_size': '1200,600,200'}
    assert _numbers(_get(world, **fit)) == [1, 3, 4, 6, 8]     # 2 and 5 are too small
    near = {'near_lat': DARMSTADT[0], 'near_lon': DARMSTADT[1], 'radius_km': 30}
    body = _get(world, **near)
    assert sorted(_numbers(body)) == [1, 2, 3, 6, 8]
    assert body['total'] == 5
    # near on the current layer, the map showing the origin layer
    body = _get(world, layer='origin', **near)
    assert _numbers(body) == [1, 3]
    assert body['total'] == 5 and body['left_out'] == 3
    assert _get(world, **near, **fit)['total'] == 4


def test_a_private_piece_never_appears_or_counts_for_someone_who_may_not_see_it(world):
    admin = _get(world)
    assert 6 in _numbers(admin) and admin['total'] == 8
    for who in ('user', None):
        body = _get(world, who=who)
        assert _numbers(body) == [1, 2, 3, 4, 8]
        assert (body['total'], body['left_out']) == (7, 2)
        assert 'piece 6' not in str(body) and 'other' not in str(body['points'])
        origin = _get(world, who=who, layer='origin')
        assert _numbers(origin) == [1, 3, 5] and origin['total'] == 7
    # a filter that names the private dataset finds nothing, not a count of one
    body = _get(world, who='user', dataset='other')
    assert body['points'] == [] and body['total'] == 0


def test_the_points_carry_what_the_map_colours_by(world):
    db = world['db']
    db['component_identities'].update_one({'_id': 'i02'}, {'$set': {
        'origin': {'kind': 'deinstallation', 'planned': True}}})
    db['component_snapshots'].update_one({'_id': 's02'}, {'$set': {'shape_class': 'planar'}})
    body = _get(world)
    by_number = {p['catalog_number']: p for p in body['points']}
    assert by_number[2]['in_place'] is True and by_number[2]['shape_class'] == 'planar'
    assert by_number[1]['in_place'] is False and by_number[1]['shape_class'] is None
    # nothing else of the record leaves with a point
    assert set(by_number[1]) == {
        'id', 'catalog_number', 'name', 'lat', 'lon', 'original_function', 'dataset',
        'material', 'shape_class', 'in_place'}


def test_the_row_schema_of_the_map_is_served_for_the_generator(world):
    schema = world['api'].get('/schema/location-map').json()
    assert {'layer', 'total', 'displayed', 'left_out', 'points'} <= set(schema['properties'])


def test_the_distance_to_a_point_is_not_part_of_the_map(world):
    body = _get(world, near_lat=DARMSTADT[0], near_lon=DARMSTADT[1])
    assert all('distance_m' not in p for p in body['points'])
    assert metres(DARMSTADT, DARMSTADT) == 0
