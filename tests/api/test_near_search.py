"""
Near search and the sort key ``distance`` (decisions 8.170, 8.173): the REST
list, count and stats against a real database with its ``2dsphere`` indexes,
and the stored points ``geo_current`` and ``geo_origin`` on every write path
that moves them, with the script that backfills them.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from apps.catalog.api.near_search import NearError, parse_near
from apps.catalog.geo import point_of, with_geo_origin
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import iid, seed_05_catalog, sid

DARMSTADT = (49.8728, 8.6512)
FRANKFURT = (50.1109, 8.6821)       # about 27 km north of Darmstadt
BERLIN = (52.5200, 13.4050)         # about 445 km
EARTH_RADIUS_M = 6_378_100          # the sphere of $geoNear
BOX = {'primitive': 'box', 'role': 'primary', 'params': {'size': [2, 1, 1]},
       'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]},
       'fit': {'method': 'authored'}}


def metres(a, b):
    """The great-circle distance between two (lat, lon) in metres."""
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


# catalog number: (current, origin, dataset, public, bbx)
PIECES = {
    1: (DARMSTADT, BERLIN, 'd', True, [1200, 600, 200]),
    2: (DARMSTADT, None, 'd', True, [200, 200, 200]),            # ties with 1
    3: (FRANKFURT, (49.9, 8.7), 'd', True, [1200, 600, 200]),
    4: (BERLIN, None, 'd', True, [1200, 600, 200]),
    5: (None, FRANKFURT, 'd', True, [300, 300, 300]),            # no current
    6: (DARMSTADT, None, 'other', False, [1200, 600, 200]),      # private
    7: (None, None, 'd', True, [1200, 600, 200]),                # no point
    8: (DARMSTADT, None, 'd', True, [1250, 600, 200]),           # third at one point
}


def _iid(n):
    return f'i{n:02d}'


def _insert(db, number, current, origin, dataset, public, bbx, material='timber'):
    doc = {
        '_id': _iid(number), 'catalog_number': number, 'dataset': dataset,
        'original_function': 'IfcBeam', 'material': material,
        'material_class': '17 02 01', 'is_public': public,
        'current_snapshot_id': f's{number:02d}', 'exit': None,
        'withdrawn': None, 'created': '2026-01-01T00:00:00Z',
        'lastmodified': '2026-01-01T00:00:00Z', 'created_by_user_id': 'u-test'}
    if origin:
        doc['origin'] = {'kind': 'deinstallation',
                         'place': {'location': {'lat': origin[0], 'lon': origin[1]}}}
        doc['geo_origin'] = point_of({'lat': origin[0], 'lon': origin[1]})
    if current:
        doc['geo_current'] = point_of({'lat': current[0], 'lon': current[1]})
    db['component_identities'].insert_one(doc)
    snapshot = {
        '_id': f's{number:02d}', 'identity_id': _iid(number), 'version': 1,
        'status': 'published', 'name': f'piece {number}', 'bbx': bbx,
        'created': '2026-01-01T00:00:00Z', 'lastmodified': '2026-01-01T00:00:00Z',
        'effective_from': '2026-01-01T00:00:00Z', 'geometry': {'proxies': [BOX]},
        'added_by_user_id': 'u-test'}
    if current:
        snapshot['location'] = {'lat': current[0], 'lon': current[1]}
    db['component_snapshots'].insert_one(snapshot)


@pytest.fixture
def world(api, db, auth_headers):
    for number, (current, origin, dataset, public, bbx) in PIECES.items():
        _insert(db, number, current, origin, dataset, public, bbx)
    return {'api': api, 'db': db, 'admin': auth_headers('admin')}


def _point(place):
    return {'near_lat': place[0], 'near_lon': place[1]}


def _list(world, path='/identities', headers=True, status=200, **params):
    response = world['api'].get(
        path, params=params, headers=world['admin'] if headers is True else headers)
    assert response.status_code == status, response.text
    return response.json()


def _numbers(rows):
    return [row['catalog_number'] for row in rows]


# THE PARSER --------------------------------------------------------------------
def test_a_near_query_needs_a_whole_point_on_the_globe():
    assert parse_near(None, None, None, None) == {}
    assert parse_near(49.9, 8.6, None, None) == {
        'near_lat': 49.9, 'near_lon': 8.6, 'near_layer': 'current', 'radius_km': None}
    assert parse_near(-90, 180, 'origin', 2.5)['near_layer'] == 'origin'
    for args in ((49, None, None, None), (None, 8, None, None), (91, 8, None, None),
                 (-90.1, 8, None, None), (49, 181, None, None), (49, -180.1, None, None),
                 (float('nan'), 8, None, None), (49, float('inf'), None, None),
                 (49, 8, None, 0), (49, 8, None, -3), (49, 8, None, float('nan')),
                 (49, 8, 'sky', None), (None, None, 'origin', None),
                 (None, None, None, 5)):
        with pytest.raises(NearError):
            parse_near(*args)


def test_a_location_off_the_globe_is_no_point():
    assert point_of({'lat': 49.87, 'lon': 8.65}) == {
        'type': 'Point', 'coordinates': [8.65, 49.87]}      # GeoJSON: lon first
    for bad in (None, {}, {'lat': 49.87}, {'lat': None, 'lon': 8}, {'lat': 91, 'lon': 0},
                {'lat': 0, 'lon': 181}, {'lat': float('nan'), 'lon': 0}, {'lat': '49', 'lon': 8},
                {'lat': True, 'lon': 8}, 'x'):
        assert point_of(bad) is None, bad


# NEAR, CURRENT LAYER -----------------------------------------------------------
def test_near_lists_pieces_with_a_point_nearest_first_with_the_distance(world):
    rows = _list(world, **_point(DARMSTADT))
    # three pieces on the point (ties by catalog number), then Frankfurt, then
    # Berlin; 5 and 7 have no current point and drop out
    assert _numbers(rows) == [1, 2, 6, 8, 3, 4]
    assert [row['distance_m'] for row in rows[:4]] == pytest.approx([0] * 4, abs=1)
    for row in rows[4:]:
        place = FRANKFURT if row['catalog_number'] == 3 else BERLIN
        assert row['distance_m'] == pytest.approx(metres(DARMSTADT, place), rel=0.005)
    distances = [row['distance_m'] for row in rows]
    assert distances == sorted(distances)


def test_a_radius_keeps_the_pieces_within_it(world):
    here = _point(DARMSTADT)
    assert _numbers(_list(world, **here, radius_km=1)) == [1, 2, 6, 8]
    assert _numbers(_list(world, **here, radius_km=30)) == [1, 2, 6, 8, 3]
    assert _numbers(_list(world, **here, radius_km=26)) == [1, 2, 6, 8]
    assert _numbers(_list(world, **here, radius_km=500)) == [1, 2, 6, 8, 3, 4]
    assert _numbers(_list(world, **_point((0, 0)), radius_km=100)) == []


def test_the_pieces_at_one_point_keep_their_order_across_pages(world):
    seen = []
    for page in (1, 2, 3):
        seen += _numbers(_list(world, **_point(DARMSTADT), page=page, size=2))
    assert seen == [1, 2, 6, 8, 3, 4]


def test_a_plain_list_has_no_distance(world):
    for row in _list(world):
        assert 'distance_m' not in row


def test_the_distance_is_on_every_shape_of_row(world):
    here = _point(FRANKFURT)
    for expand in ('shallow', 'current_snapshot', 'none'):
        rows = _list(world, **here, expand=expand, radius_km=1)
        assert len(rows) == 1
        row = rows[0]
        assert row['distance_m'] == pytest.approx(0, abs=1)
        # the stored points never leave the server
        text = str(row)
        assert 'geo_current' not in text and 'geo_origin' not in text


# NEAR, ORIGIN LAYER ------------------------------------------------------------
def test_the_origin_layer_measures_the_origin_building(world):
    rows = _list(world, **_point(DARMSTADT), near_layer='origin')
    # 3 has an origin near Darmstadt, 5 sits in Frankfurt, 1 in Berlin; the
    # pieces without an origin point drop out, whatever their current place
    assert _numbers(rows) == [3, 5, 1]
    assert rows[0]['distance_m'] == pytest.approx(metres(DARMSTADT, (49.9, 8.7)), rel=0.005)
    assert rows[1]['distance_m'] == pytest.approx(metres(DARMSTADT, FRANKFURT), rel=0.005)
    assert _numbers(_list(world, **_point(DARMSTADT), near_layer='origin',
                          radius_km=50)) == [3, 5]
    assert _numbers(_list(world, **_point(DARMSTADT), near_layer='current',
                          radius_km=1)) == [1, 2, 6, 8]


# VALIDATION --------------------------------------------------------------------
def test_a_near_search_that_cannot_run_answers_422_in_words(world):
    for params, words in (
            ({'near_lat': 49}, 'both or neither'),
            ({'near_lon': 8}, 'both or neither'),
            ({'near_lat': 91, 'near_lon': 8}, 'latitude'),
            ({'near_lat': 49, 'near_lon': -181}, 'longitude'),
            ({'near_lat': 'nan', 'near_lon': 8}, 'latitude'),
            ({'near_lat': 49, 'near_lon': 8, 'radius_km': 0}, 'above 0'),
            ({'near_lat': 49, 'near_lon': 8, 'radius_km': -2}, 'above 0'),
            ({'near_lat': 49, 'near_lon': 8, 'radius_km': 'inf'}, 'above 0'),
            ({'radius_km': 5}, 'need near_lat'),
            ({'near_layer': 'origin'}, 'need near_lat'),
            ({'sortkey': 'distance'}, 'needs near_lat')):
        for path in ('/identities', '/identities/count', '/identities/stats'):
            if 'sortkey' in params and path != '/identities':
                continue
            body = _list(world, path=path, status=422, **params)
            assert words in str(body['detail']), (params, path, body)
    # a layer that does not exist is refused by the type of the parameter
    assert world['api'].get('/identities', params={
        **_point(DARMSTADT), 'near_layer': 'sky'}, headers=world['admin']).status_code == 422


# SORTING -----------------------------------------------------------------------
def test_distance_is_the_default_sort_and_can_be_turned(world):
    here = _point(DARMSTADT)
    assert _numbers(_list(world, **here, sortkey='distance')) == [1, 2, 6, 8, 3, 4]
    # farthest first; the catalog number still breaks the tie
    assert _numbers(_list(world, **here, sortkey='distance', sortorder='desc')) == [
        4, 3, 1, 2, 6, 8]


def test_any_other_sort_stays_one_choice_away(world):
    here = _point(DARMSTADT)
    assert _numbers(_list(world, **here, sortkey='catalog_number', sortorder='desc')) == [
        8, 6, 4, 3, 2, 1]
    assert _numbers(_list(world, **here, sortkey='volume')) == [2, 1, 3, 4, 6, 8]
    for row in _list(world, **here, sortkey='name'):
        assert 'distance_m' in row


def test_a_dimension_search_filters_and_the_near_search_sorts(world):
    fit = {'fit_mode': 'can_hold', 'fit_size': '1200,600,200'}
    rows = _list(world, **fit, **_point(DARMSTADT))
    # 2 and 5 are too small; the rest are nearest first, each with its match
    assert _numbers(rows) == [1, 6, 8, 3, 4]
    assert all('fit' in row and 'distance_m' in row for row in rows)
    # the match is one choice away, and is the default without the near search
    by_match = _list(world, **fit, **_point(DARMSTADT), sortkey='match')
    assert _numbers(by_match)[:3] == [1, 3, 4]       # exact fits first
    assert _numbers(_list(world, **fit))[:3] == [1, 3, 4]
    assert _numbers(_list(world, **fit, **_point(DARMSTADT), radius_km=30)) == [1, 6, 8, 3]
    assert _list(world, path='/identities/count', **fit, **_point(DARMSTADT),
                 radius_km=30) == {'count': 4}


# VISIBILITY AND THE OTHER READS ------------------------------------------------
def test_a_private_piece_never_appears_for_someone_who_may_not_see_it(world, auth_headers):
    here = _point(DARMSTADT)
    assert 6 in _numbers(_list(world, **here))                     # the admin
    stranger = auth_headers('user')
    assert _numbers(_list(world, headers=stranger, **here)) == [1, 2, 8, 3, 4]
    assert _numbers(_list(world, headers=None, **here)) == [1, 2, 8, 3, 4]
    counted = _list(world, path='/identities/count', headers=stranger, **here, radius_km=1)
    assert counted == {'count': 3}
    assert _list(world, path='/identities/count', **here, radius_km=1) == {'count': 4}
    # and the origin layer the same way
    assert _numbers(_list(world, headers=None, **here, near_layer='origin')) == [3, 5, 1]


def test_count_and_stats_take_the_near_search(world):
    here = _point(DARMSTADT)
    assert _list(world, path='/identities/count', **here) == {'count': 6}
    assert _list(world, path='/identities/count', **here, radius_km=1) == {'count': 4}
    assert _list(world, path='/identities/count', **here, near_layer='origin') == {'count': 3}
    stats = _list(world, path='/identities/stats', **here, radius_km=1)
    assert stats['total'] == 4
    assert _list(world, path='/identities/stats')['total'] == 8


def test_the_other_filters_combine_with_near(world):
    world['db']['component_identities'].update_one({'_id': _iid(3)}, {'$set': {'material': 'steel'}})
    here = _point(DARMSTADT)
    assert _numbers(_list(world, **here, material='steel')) == [3]
    assert _numbers(_list(world, **here, material='steel', radius_km=1)) == []
    assert _numbers(_list(world, **here, q='piece 8')) == [8]
    assert _numbers(_list(world, **here, dataset='other')) == [6]
    assert _numbers(_list(world, **here, bbx_min_x=1250)) == [8]


def test_the_row_schema_names_the_distance(world):
    schema = world['api'].get('/schema/catalog-row').json()
    assert 'distance_m' in schema['properties']


# THE STORED POINTS ON EVERY WRITE PATH -----------------------------------------
@pytest.fixture
def story(api, db, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    moderator, _ = member_headers({'dbu_zirkus': ['moderator', 'contributor']})
    material = db['component_identities'].find_one({'_id': iid('beam')})['material']
    return {'api': api, 'db': db, 'c': contributor, 'm': moderator, 'material': material}


def _create(story, name='located', location=DARMSTADT, origin=FRANKFURT):
    snapshot = {'name': name, 'geometry': {'proxies': [BOX]}}
    if location:
        snapshot['location'] = {'lat': location[0], 'lon': location[1]}
    body = {'dataset': 'dbu_zirkus', 'original_function': 'IfcWall',
            'material': story['material'], 'snapshot': snapshot,
            'origin': {'kind': 'offcut', 'construction_work': None}}
    if origin:
        body['origin']['place'] = {'location': {'lat': origin[0], 'lon': origin[1]}}
    created = story['api'].post('/identities', json=body, headers=story['c'])
    assert created.status_code == 201, created.text
    return created.json()


def _publish(story, snapshot_id):
    assert story['api'].post(f'/snapshots/{snapshot_id}/submit',
                             headers=story['c']).status_code == 200
    published = story['api'].post(f'/snapshots/{snapshot_id}/publish?promote=1',
                                  headers=story['m'])
    assert published.status_code == 200, published.text


def _stored(story, identity_id):
    return story['db']['component_identities'].find_one({'_id': identity_id})


def _lonlat(place):
    return {'type': 'Point', 'coordinates': [place[1], place[0]]}


def test_a_new_piece_has_its_origin_point_and_its_current_point_when_published(story):
    created = _create(story)
    identity_id = created['identity']['_id']
    stored = _stored(story, identity_id)
    assert stored['geo_origin'] == _lonlat(FRANKFURT)
    assert 'geo_current' not in stored            # a draft is nobody's current state
    _publish(story, created['snapshot']['_id'])
    assert _stored(story, identity_id)['geo_current'] == _lonlat(DARMSTADT)
    # the point is not a field of the record: it neither shows nor is logged
    body = story['api'].get(f'/identities/{identity_id}', headers=story['m']).json()
    assert 'geo_current' not in str(body) and 'geo_origin' not in str(body)
    history = story['db']['change_log'].find({'record_id': identity_id})
    assert not any('geo_' in change['path'] for entry in history for change in entry['changes'])


def test_a_piece_without_a_location_has_no_point_not_null_and_not_zero(story):
    created = _create(story, location=None, origin=None)
    identity_id = created['identity']['_id']
    _publish(story, created['snapshot']['_id'])
    stored = _stored(story, identity_id)
    assert 'geo_current' not in stored and 'geo_origin' not in stored


def test_a_location_patched_on_the_current_version_moves_the_point(story):
    created = _create(story)
    identity_id, snapshot_id = created['identity']['_id'], created['snapshot']['_id']
    _publish(story, snapshot_id)
    moved = story['api'].patch(f'/snapshots/{snapshot_id}',
                               json={'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}},
                               headers=story['m'])
    assert moved.status_code == 200, moved.text
    assert _stored(story, identity_id)['geo_current'] == _lonlat(BERLIN)
    cleared = story['api'].patch(f'/snapshots/{snapshot_id}', json={'location': None},
                                 headers=story['m'])
    assert cleared.status_code == 200, cleared.text
    assert 'geo_current' not in _stored(story, identity_id)


def test_a_location_patched_on_a_version_that_is_not_current_leaves_the_point(story):
    created = _create(story)
    identity_id, first = created['identity']['_id'], created['snapshot']['_id']
    _publish(story, first)
    draft = story['api'].post(f'/identities/{identity_id}/snapshots', json={
        'geometry': {'proxies': [BOX]}, 'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}},
        headers=story['c'])
    assert draft.status_code == 201, draft.text
    assert story['api'].patch(f"/snapshots/{draft.json()['_id']}", json={
        'location': {'lat': 1.0, 'lon': 2.0}}, headers=story['c']).status_code == 200
    assert _stored(story, identity_id)['geo_current'] == _lonlat(DARMSTADT)


def test_the_point_follows_the_current_version_when_another_is_published_or_withdrawn(story):
    created = _create(story)
    identity_id, first = created['identity']['_id'], created['snapshot']['_id']
    _publish(story, first)
    api = story['api']
    # a correction of the current version becomes current
    corrected = api.post(f'/snapshots/{first}/supersede', json={
        'geometry': {'proxies': [BOX]}, 'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}},
        headers=story['c'])
    assert corrected.status_code == 201, corrected.text
    second = corrected.json()['_id']
    assert _stored(story, identity_id)['geo_current'] == _lonlat(DARMSTADT)   # still a draft
    _publish(story, second)
    assert _stored(story, identity_id)['geo_current'] == _lonlat(BERLIN)
    # withdrawing it: no live version is left to fall back to
    withdrawn = api.post(f'/snapshots/{second}/withdraw', json={'reason': 'test'},
                         headers=story['m'])
    assert withdrawn.status_code == 200, withdrawn.text
    assert _stored(story, identity_id).get('current_snapshot_id') is None
    assert 'geo_current' not in _stored(story, identity_id)
    # and reinstating brings it back
    assert api.post(f'/snapshots/{second}/reinstate', headers=story['m']).status_code == 200
    assert _stored(story, identity_id)['geo_current'] == _lonlat(BERLIN)


def test_a_promoted_older_version_gives_its_point(story):
    created = _create(story)
    identity_id, first = created['identity']['_id'], created['snapshot']['_id']
    _publish(story, first)
    api = story['api']
    draft = api.post(f'/identities/{identity_id}/snapshots', json={
        'geometry': {'proxies': [BOX]}, 'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}},
        headers=story['c'])
    assert draft.status_code == 201, draft.text
    second = draft.json()['_id']
    assert api.post(f'/snapshots/{second}/submit', headers=story['c']).status_code == 200
    # published without promote: the first version stays current
    assert api.post(f'/snapshots/{second}/publish', headers=story['m']).status_code == 200
    assert _stored(story, identity_id)['geo_current'] == _lonlat(DARMSTADT)
    assert api.post(f'/snapshots/{second}/promote', headers=story['m']).status_code == 200
    assert _stored(story, identity_id)['geo_current'] == _lonlat(BERLIN)


def test_the_origin_point_follows_a_patch_and_survives_the_other_edits(story):
    created = _create(story, origin=None)
    identity_id, snapshot_id = created['identity']['_id'], created['snapshot']['_id']
    _publish(story, snapshot_id)
    api = story['api']
    assert 'geo_origin' not in _stored(story, identity_id)
    origin = {'kind': 'offcut', 'construction_work': None,
              'place': {'name': 'Hall', 'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}}}
    assert api.patch(f'/identities/{identity_id}', json={'origin': origin},
                     headers=story['m']).status_code == 200
    stored = _stored(story, identity_id)
    assert stored['geo_origin'] == _lonlat(BERLIN)
    # an edit of something else keeps both points (the write replaces the record)
    assert api.patch(f'/identities/{identity_id}', json={'trade_name': 'x'},
                     headers=story['m']).status_code == 200
    stored = _stored(story, identity_id)
    assert stored['geo_origin'] == _lonlat(BERLIN)
    assert stored['geo_current'] == _lonlat(DARMSTADT)
    # a new place moves it, clearing the coordinates removes it
    origin['place']['location'] = {'lat': FRANKFURT[0], 'lon': FRANKFURT[1]}
    assert api.patch(f'/identities/{identity_id}', json={'origin': origin},
                     headers=story['m']).status_code == 200
    assert _stored(story, identity_id)['geo_origin'] == _lonlat(FRANKFURT)
    origin['place'] = {'name': 'Hall'}
    assert api.patch(f'/identities/{identity_id}', json={'origin': origin},
                     headers=story['m']).status_code == 200
    stored = _stored(story, identity_id)
    assert 'geo_origin' not in stored and stored['geo_current'] == _lonlat(DARMSTADT)


def test_a_child_that_inherits_the_origin_has_its_point_and_follows_the_parent(story):
    parent = _create(story, name='parent')
    parent_id = parent['identity']['_id']
    _publish(story, parent['snapshot']['_id'])
    cut = story['api'].post('/identities', json={
        'dataset': 'dbu_zirkus', 'parent_identities': [parent_id],
        'snapshot': {'geometry': {'proxies': [BOX]}}}, headers=story['c'])
    assert cut.status_code == 201, cut.text
    child_id = cut.json()['identity']['_id']
    assert _stored(story, child_id)['geo_origin'] == _lonlat(FRANKFURT)
    origin = {'kind': 'offcut', 'construction_work': None,
              'place': {'location': {'lat': BERLIN[0], 'lon': BERLIN[1]}}}
    assert story['api'].patch(f'/identities/{parent_id}', json={'origin': origin},
                              headers=story['m']).status_code == 200
    assert _stored(story, child_id)['geo_origin'] == _lonlat(BERLIN)


def test_the_stored_points_cannot_be_set_through_the_api(story):
    created = _create(story)
    identity_id = created['identity']['_id']
    _publish(story, created['snapshot']['_id'])
    for body in ({'geo_current': _lonlat(BERLIN)}, {'geo_origin': _lonlat(BERLIN)}):
        story['api'].patch(f'/identities/{identity_id}', json=body, headers=story['m'])
        stored = _stored(story, identity_id)
        assert stored['geo_current'] == _lonlat(DARMSTADT)
        assert stored['geo_origin'] == _lonlat(FRANKFURT)


def test_a_new_piece_is_found_by_the_near_search_at_once(story):
    created = _create(story)
    _publish(story, created['snapshot']['_id'])
    found = story['api'].get('/identities', params={
        'near_lat': DARMSTADT[0], 'near_lon': DARMSTADT[1], 'radius_km': 1,
        'status': 'any'}, headers=story['m'])
    assert found.status_code == 200, found.text
    # the migrated catalog has its pieces at 49.87, 8.65 too, but no points yet
    assert [row['_id'] for row in found.json()] == [created['identity']['_id']]


def test_with_geo_origin_carries_the_current_point_over_a_model_dump():
    stored = {'_id': 'a', 'origin': {'place': {'location': {'lat': 1, 'lon': 2}}},
              'geo_current': _lonlat(DARMSTADT), 'geo_origin': _lonlat(BERLIN)}
    rewritten = with_geo_origin({'_id': 'a', 'origin': stored['origin']}, stored)
    assert rewritten['geo_origin'] == {'type': 'Point', 'coordinates': [2.0, 1.0]}
    assert rewritten['geo_current'] == stored['geo_current']
    assert 'geo_origin' not in with_geo_origin({'_id': 'a', 'origin': None}, stored)


# THE BACKFILL ------------------------------------------------------------------
def _backfill_module():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'db_maintenance' / 'backfill_geo_points.py'
    spec = importlib.util.spec_from_file_location('backfill_geo_points', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_backfill_fills_corrects_and_removes_points_and_then_finds_nothing(story, db, tmp_path):
    module = _backfill_module()
    identities = db['component_identities']
    # the migrated catalog: every current version has a location, no point yet
    before = module.scan(db)
    assert before['to_set'] >= 4 and before['to_remove'] == 0
    # origin coordinates on one piece, a wrong point on another, a stale one
    # on a piece whose version has no location
    identities.update_one({'_id': iid('beam')}, {'$set': {
        'origin': {'kind': 'unknown', 'place': {'location': {'lat': 10, 'lon': 20}}}}})
    identities.update_one({'_id': iid('feld')}, {'$set': {'geo_current': _lonlat(BERLIN)}})
    db['component_snapshots'].update_one({'_id': sid('panel')}, {'$unset': {'location': ''}})
    identities.update_one({'_id': iid('panel')}, {'$set': {'geo_current': _lonlat(BERLIN)}})
    # an unusable location is counted, never written
    identities.update_one({'_id': iid('stone')}, {'$set': {
        'origin': {'kind': 'unknown', 'place': {'location': {'lat': 99, 'lon': 0}}}}})
    stamps = {i['_id']: i['lastmodified'] for i in identities.find({})}
    scanned = module.scan(db)
    assert scanned['unusable'] == [(iid('stone'), 'geo_origin')]
    assert scanned['to_remove'] == 1
    module.apply(db, scanned['updates'])
    assert identities.find_one({'_id': iid('beam')})['geo_origin'] == _lonlat((10, 20))
    assert identities.find_one({'_id': iid('beam')})['geo_current'] == _lonlat((49.87, 8.65))
    assert identities.find_one({'_id': iid('feld')})['geo_current'] == _lonlat((49.87, 8.65))
    assert 'geo_current' not in identities.find_one({'_id': iid('panel')})
    assert 'geo_origin' not in identities.find_one({'_id': iid('stone')})
    again = module.scan(db)
    assert again['updates'] == []
    # a point is written without touching the record's time
    assert {i['_id']: i['lastmodified'] for i in identities.find({})} == stamps


def test_a_point_set_between_the_read_and_the_write_of_an_edit_is_not_overwritten(story, monkeypatch):
    """The edit replaces the whole record; a ``geo_current`` that a publish set
    after the edit read it is a conflict (409), not a lost update."""
    from apps.catalog.api import identity_edit
    created = _create(story)
    identity_id = created['identity']['_id']
    _publish(story, created['snapshot']['_id'])
    real = identity_edit.with_geo_origin

    def racing(identity, previous=None):
        # another request moves the current point after this one read the record
        story['db']['component_identities'].update_one(
            {'_id': identity_id}, {'$set': {'geo_current': _lonlat(BERLIN)}})
        return real(identity, previous)

    monkeypatch.setattr(identity_edit, 'with_geo_origin', racing)
    clash = story['api'].patch(f'/identities/{identity_id}', json={'trade_name': 'x'},
                               headers=story['m'])
    assert clash.status_code == 409, clash.text
    stored = _stored(story, identity_id)
    assert stored['geo_current'] == _lonlat(BERLIN)
    assert stored.get('trade_name') is None
    # without the race the same edit goes through and keeps the point
    monkeypatch.setattr(identity_edit, 'with_geo_origin', real)
    assert story['api'].patch(f'/identities/{identity_id}', json={'trade_name': 'x'},
                              headers=story['m']).status_code == 200
    assert _stored(story, identity_id)['geo_current'] == _lonlat(BERLIN)


def test_a_redaction_never_overwrites_a_point_set_meanwhile(story, auth_headers, monkeypatch):
    from apps.catalog.api import actors
    ada = {'kind': 'person', 'name': 'Dr. Ada Example'}
    db = story['db']
    db['component_identities'].update_one({'_id': iid('beam')}, {'$set': {
        'origin': {'kind': 'deinstallation', 'at': '2024-07-24T00:00:00Z',
                   'at_precision': 'day', 'performed_by': [ada]},
        'geo_current': _lonlat(DARMSTADT)}})
    real, raced = actors.blank, []

    def racing(value, body, now):
        if not raced:                   # once: after the first read, before its write
            raced.append(True)
            db['component_identities'].update_one(
                {'_id': iid('beam')}, {'$set': {'geo_current': _lonlat(BERLIN)}})
        return real(value, body, now)

    monkeypatch.setattr(actors, 'blank', racing)
    done = story['api'].post('/actors/redact', json={'name': 'dr. ada example'},
                             headers=auth_headers('admin'))
    assert done.status_code == 200, done.text
    stored = db['component_identities'].find_one({'_id': iid('beam')})
    # the first write found the point changed and missed; the retry read the new one
    assert stored['geo_current'] == _lonlat(BERLIN)
    assert 'Ada' not in str(stored['origin'])


def test_a_dry_run_of_the_backfill_exits_4_while_points_disagree_and_0_when_they_agree(
        story, db, mongod, db_name, monkeypatch):
    module = _backfill_module()
    monkeypatch.setenv('MONGO_URI', f'{mongod.uri}/{db_name}')
    assert module.run(dry_run=True) == 4           # the migrated catalog has no points yet
    assert db['component_identities'].count_documents({'geo_current': {'$exists': True}}) == 0
    assert module.run(dry_run=False) == 0
    assert db['component_identities'].count_documents({'geo_current': {'$exists': True}}) > 0
    assert module.run(dry_run=True) == 0
    db['component_identities'].update_one({'_id': iid('beam')}, {'$set': {'geo_current': _lonlat(BERLIN)}})
    assert module.run(dry_run=True) == 4
    assert module.run(dry_run=False) == 0
    assert module.run(dry_run=True) == 0
