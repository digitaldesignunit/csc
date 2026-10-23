"""
Dimension search and the sort keys ``volume`` and ``match`` (decisions 8.169,
8.173): the REST list, count and stats against a real database. The two modes
compare the three sides of the asked box with the sorted sides of the current
``bbx``, so the stored orientation does not matter.
"""

from __future__ import annotations

import pytest

from apps.catalog.api.dimension_fit import (
    FitError,
    parse_size,
    parse_tolerance,
)

PIECES = {
    # catalog number: (bbx, dataset, public)
    1: ([1200, 600, 200], 'd', True),          # exactly the asked size
    2: ([200, 1200, 600], 'd', True),          # the same, turned
    3: ([1320, 660, 220], 'd', True),          # +10 % on every side: the edge
    4: ([1321, 600, 200], 'd', True),          # 0.1 % beyond +10 % on one side
    5: ([200, 200, 1200], 'd', True),          # a standing column (z longest)
    6: (None, 'd', True),                      # geometry not derived
    7: ([2000, 1000, 500], 'other', True),     # big enough to cut from
    8: ([1200, 600, 199.9], 'd', True),        # a hair too thin
    9: ([1200, 600], 'd', True),               # not three sides
}


def _iid(n):
    return f'i{n:02d}'


def _insert(api, db, number, bbx, dataset='d', public=True):
    iid, sid = _iid(number), f's{number:02d}'
    db['component_identities'].insert_one({
        '_id': iid, 'catalog_number': number, 'dataset': dataset,
        'original_function': 'IfcBeam', 'material': 'timber',
        'material_class': '17 02 01', 'is_public': public,
        'current_snapshot_id': sid, 'exit': None, 'withdrawn': None,
        'created': '2026-01-01T00:00:00Z', 'lastmodified': '2026-01-01T00:00:00Z',
        'created_by_user_id': 'u-test'})
    snapshot = {
        '_id': sid, 'identity_id': iid, 'version': 1,
        'status': 'published', 'name': f'piece {number}',
        'created': '2026-01-01T00:00:00Z',
        'lastmodified': '2026-01-01T00:00:00Z',
        'effective_from': f'2026-01-{number:02d}T00:00:00Z'}
    if bbx is not None:
        snapshot['bbx'] = bbx
    db[api.app.mongodb_component_snapshots.name].insert_one(snapshot)


@pytest.fixture
def world(api, db, auth_headers):
    for number, (bbx, dataset, public) in PIECES.items():
        _insert(api, db, number, bbx, dataset, public)
    return {'api': api, 'db': db, 'admin': auth_headers('admin')}


def _list(world, headers=True, **params):
    response = world['api'].get(
        '/identities', params=params,
        headers=world['admin'] if headers else None)
    assert response.status_code == 200, response.text
    return response.json()


def _numbers(rows):
    return [row['catalog_number'] for row in rows]


# THE PARSERS -------------------------------------------------------------------
def test_the_size_is_three_positive_numbers_largest_first():
    assert parse_size('200, 1200,600') == (1200.0, 600.0, 200.0)
    assert parse_size('1.5,1.5,1.5') == (1.5, 1.5, 1.5)
    for bad in ('', '1,2', '1,2,3,4', '1,2,x', '0,1,2', '-1,2,3', '1;2;3',
                '1,2,100001', '1e3,2,3', 'nan,1,2', '1,,2'):
        with pytest.raises(FitError):
            parse_size(bad)


def test_the_tolerance_is_a_percentage_or_millimetres():
    assert parse_tolerance('10%') == ('percent', 10.0)
    assert parse_tolerance(' 2.5 % ') == ('percent', 2.5)
    assert parse_tolerance('50mm') == ('mm', 50.0)
    assert parse_tolerance('0mm') == ('mm', 0.0)
    for bad in ('', '10', '%', '-5%', '101%', 'mm', '5cm', 'ten%', '100001mm'):
        with pytest.raises(FitError):
            parse_tolerance(bad)


# ABOUT THIS SIZE ---------------------------------------------------------------
def test_about_ignores_the_orientation_and_the_default_tolerance_is_10_percent(world):
    rows = _list(world, fit_mode='about', fit_size='600,200,1200')
    # 1 and 2 are the asked box (turned), 3 sits exactly on the edge; 4 is a
    # hair outside, 5 and 7 are other boxes, 6 and 9 have no size, 8 is within
    # 10 % too (0.05 % thin)
    assert _numbers(rows) == [1, 2, 8, 3]
    assert [row['fit']['mode'] for row in rows] == ['about'] * 4
    deviations = [row['fit']['deviation'] for row in rows]
    assert deviations[:2] == [0, 0]
    assert deviations == sorted(deviations)
    assert deviations[3] == pytest.approx(0.1)


def test_a_standing_column_matches_by_its_sorted_sides(world):
    rows = _list(world, fit_mode='about', fit_size='200,1200,200')
    assert _numbers(rows) == [5]
    assert rows[0]['bbx'] == [200, 200, 1200]


def test_the_edge_of_the_tolerance_counts_in_percent_and_in_millimetres(world):
    base = {'fit_mode': 'about', 'fit_size': '1200,600,200'}
    assert 3 in _numbers(_list(world, **base, fit_tol='10%'))
    assert 3 not in _numbers(_list(world, **base, fit_tol='9.9%'))
    assert 4 not in _numbers(_list(world, **base, fit_tol='10%'))
    assert 4 in _numbers(_list(world, **base, fit_tol='10.1%'))
    # millimetres: the largest side of piece 3 is 120 mm off
    assert 3 in _numbers(_list(world, **base, fit_tol='120mm'))
    assert 3 not in _numbers(_list(world, **base, fit_tol='119mm'))
    # a tolerance of nothing is an exact match
    assert _numbers(_list(world, **base, fit_tol='0mm')) == [1, 2]


def test_the_tolerance_is_a_share_of_each_asked_side(world):
    # 5 % of 200 is 10 mm: piece 3 is 20 mm off on that side
    rows = _list(world, fit_mode='about', fit_size='1200,600,200',
                 fit_tol='5%')
    assert 3 not in _numbers(rows)
    # in millimetres one value serves every side
    rows = _list(world, fit_mode='about', fit_size='1200,600,200',
                 fit_tol='25mm')
    assert _numbers(rows) == [1, 2, 8]


# CAN HOLD ----------------------------------------------------------------------
def test_can_hold_means_every_sorted_side_is_at_least_the_asked_side(world):
    rows = _list(world, fit_mode='can_hold', fit_size='200,1200,600')
    # 1, 2 equal sides (nothing to waste), 4, 3, 7 are bigger (least waste
    # first); 5 is too narrow, 8 a hair too thin, 6 and 9 have no size
    assert _numbers(rows) == [1, 2, 4, 3, 7]
    wastes = [row['fit']['waste_mm3'] for row in rows]
    assert wastes == sorted(wastes)
    assert wastes[:2] == [0, 0]
    assert wastes[2] == pytest.approx(1321 * 600 * 200 - 1200 * 600 * 200)
    assert wastes[3] == pytest.approx(1320 * 660 * 220 - 1200 * 600 * 200)
    assert wastes[4] == pytest.approx(2000 * 1000 * 500 - 1200 * 600 * 200)
    # the share of the piece's own box volume, in per cent
    shares = [row['fit']['waste_percent'] for row in rows]
    assert shares[:2] == [0, 0]
    assert shares[3] == pytest.approx(100 * (1 - 1200 * 600 * 200 / (1320 * 660 * 220)))
    assert shares[4] == pytest.approx(100 * (1 - 1200 * 600 * 200 / (2000 * 1000 * 500)))
    assert all(row['fit']['mode'] == 'can_hold' for row in rows)


def test_can_hold_takes_no_tolerance(world):
    response = world['api'].get('/identities', params={
        'fit_mode': 'can_hold', 'fit_size': '1,1,1', 'fit_tol': '10%'})
    assert response.status_code == 422
    assert 'no fit_tol' in response.json()['detail']


# THE REST OF THE QUERY ---------------------------------------------------------
def test_another_filter_combines_with_the_fit(world):
    rows = _list(world, fit_mode='can_hold', fit_size='1200,600,200',
                 dataset='other')
    assert _numbers(rows) == [7]
    rows = _list(world, fit_mode='can_hold', fit_size='1200,600,200', q='piece 3')
    assert _numbers(rows) == [3]
    rows = _list(world, fit_mode='about', fit_size='1200,600,200',
                 bbx_min_x=1300)          # the per-axis boxes still work
    assert _numbers(rows) == [3]


def test_count_and_stats_agree_with_the_list(world):
    api = world['api']
    for params in (
            {'fit_mode': 'about', 'fit_size': '1200,600,200'},
            {'fit_mode': 'about', 'fit_size': '1200,600,200',
             'fit_tol': '50mm'},
            {'fit_mode': 'can_hold', 'fit_size': '1200,600,200'},
            {'fit_mode': 'can_hold', 'fit_size': '1200,600,200',
             'dataset': 'other'},
            {'fit_mode': 'can_hold', 'fit_size': '9000,9000,9000'}):
        rows = _list(world, **params)
        count = api.get('/identities/count', params=params,
                        headers=world['admin'])
        stats = api.get('/identities/stats', params=params,
                        headers=world['admin'])
        assert count.json() == {'count': len(rows)}, params
        assert stats.json()['total'] == len(rows), params
    # and without a fit every piece counts again
    assert api.get('/identities/count', headers=world['admin']
                   ).json()['count'] == len(PIECES)


def test_a_row_without_a_search_carries_no_fit(world):
    rows = _list(world)
    assert len(rows) == len(PIECES)
    assert all('fit' not in row for row in rows)


def test_an_identity_row_carries_the_match_too(world):
    rows = _list(world, expand='none', fit_mode='about',
                 fit_size='1200,600,200', fit_tol='0mm')
    assert [row['fit'] for row in rows] == [{'mode': 'about', 'deviation': 0}] * 2


def test_a_passport_row_carries_the_match_too(api, db, auth_headers):
    from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
    from support import seed_05_catalog
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    sized = db['component_snapshots'].find_one({'bbx.2': {'$gt': 0}})
    assert sized, 'the seed has a piece with a size'
    rows = api.get('/identities', params={
        'fit_mode': 'about', 'fit_size': ','.join(str(v) for v in sized['bbx']),
        'fit_tol': '0mm', 'expand': 'current_snapshot', 'status': 'any',
        'circulation': 'all'}, headers=auth_headers('admin'))
    assert rows.status_code == 200, rows.text
    assert rows.json() and all(
        row['fit'] == {'mode': 'about', 'deviation': 0} for row in rows.json())


# SORTING -----------------------------------------------------------------------
def test_a_search_sorts_by_match_unless_another_sort_is_asked(world):
    params = {'fit_mode': 'can_hold', 'fit_size': '1200,600,200'}
    assert _numbers(_list(world, **params)) == [1, 2, 4, 3, 7]
    assert _numbers(_list(world, sortkey='match', **params)) == [1, 2, 4, 3, 7]
    assert _numbers(_list(world, sortkey='match', sortorder='desc',
                          **params)) == [7, 3, 4, 1, 2]
    assert _numbers(_list(world, sortkey='catalog_number', sortorder='desc',
                          **params)) == [7, 4, 3, 2, 1]


def test_volume_sorts_both_ways_and_a_piece_without_a_size_goes_last(world):
    asc = _numbers(_list(world, sortkey='volume'))
    desc = _numbers(_list(world, sortkey='volume', sortorder='desc'))
    assert set(asc[-2:]) == {6, 9} and set(desc[-2:]) == {6, 9}
    sized_asc, sized_desc = asc[:-2], desc[:-2]
    volumes = {n: PIECES[n][0][0] * PIECES[n][0][1] * PIECES[n][0][2]
               for n in PIECES if n not in (6, 9)}
    assert [volumes[n] for n in sized_asc] == sorted(volumes.values())
    assert [volumes[n] for n in sized_desc] == sorted(volumes.values(),
                                                      reverse=True)
    # a page of the sort holds the same rows as the whole
    page = _numbers(_list(world, sortkey='volume', page=2, size=3))
    assert page == asc[3:6]


def test_volume_sorts_inside_a_fit(world):
    rows = _list(world, fit_mode='can_hold', fit_size='200,600,1200',
                 sortkey='volume', sortorder='desc')
    assert _numbers(rows) == [7, 3, 4, 1, 2]


def test_the_bad_cases_are_4xx_with_a_readable_message(world):
    api = world['api']

    def refused(**params):
        response = api.get('/identities', params=params)
        assert response.status_code == 422, (params, response.text)
        assert isinstance(response.json()['detail'], str), params
        return response.json()['detail']

    assert 'needs fit_mode' in refused(sortkey='match')
    assert 'needs fit_size' in refused(fit_mode='about')
    assert 'need fit_mode' in refused(fit_size='1,2,3')
    assert 'need fit_mode' in refused(fit_tol='10%')
    refused(fit_mode='about', fit_size='1,2')
    refused(fit_mode='about', fit_size='1,2,x')
    refused(fit_mode='about', fit_size='0,1,2')
    refused(fit_mode='about', fit_size='1,2,3', fit_tol='abc')
    refused(fit_mode='about', fit_size='1,2,3', fit_tol='101%')
    refused(fit_mode='about', fit_size='1,2,3000000')
    # an unknown mode is the framework's 422 with a list of problems
    assert api.get('/identities', params={
        'fit_mode': 'near', 'fit_size': '1,2,3'}).status_code == 422
    # the count and the stats refuse the same way
    for path in ('/identities/count', '/identities/stats'):
        assert api.get(path, params={'fit_mode': 'about'}).status_code == 422


# VISIBILITY --------------------------------------------------------------------
def test_an_anonymous_caller_sees_only_public_pieces_through_a_fit(world):
    _insert(world['api'], world['db'], 10, [1200, 600, 200], public=False)
    params = {'fit_mode': 'about', 'fit_size': '1200,600,200',
              'fit_tol': '0mm'}
    assert _numbers(_list(world, **params)) == [1, 2, 10]
    anonymous = _list(world, headers=False, **params)
    assert _numbers(anonymous) == [1, 2]
    count = world['api'].get('/identities/count', params=params)
    assert count.json() == {'count': 2}
    stats = world['api'].get('/identities/stats', params=params)
    assert stats.json()['total'] == 2
    # a status filter does not widen an anonymous search
    anonymous = _list(world, headers=False, status='any', **params)
    assert _numbers(anonymous) == [1, 2]


# THE SIDES WITHOUT $sortArray ----------------------------------------------------
def test_every_turning_of_a_piece_gives_the_same_match(world):
    import itertools
    db, api = world['db'], world['api']
    for n, bbx in enumerate(itertools.permutations([300, 700, 450]), start=20):
        _insert(api, db, n, list(bbx))
    rows = _list(world, fit_mode='about', fit_size='450,300,700', fit_tol='0mm')
    assert _numbers(rows) == [20, 21, 22, 23, 24, 25]
    assert all(row['fit']['deviation'] == 0 for row in rows)
    rows = _list(world, fit_mode='can_hold', fit_size='299,449,699', dataset='d',
                 q='piece 2')
    assert _numbers(rows) == [20, 21, 22, 23, 24, 25]


def test_equal_sides_stay_equal(world):
    db, api = world['db'], world['api']
    _insert(api, db, 30, [500, 500, 500])
    _insert(api, db, 31, [500, 500, 300])
    _insert(api, db, 32, [300, 500, 500])
    _insert(api, db, 33, [500, 300, 300])
    # a cube is a cube: only the cube holds a cube
    assert _numbers(_list(world, fit_mode='can_hold', fit_size='500,500,500',
                          q='piece 3')) == [30]
    # two long sides and a short one, whichever way the box lies
    assert _numbers(_list(world, fit_mode='about', fit_size='500,300,500',
                          fit_tol='0mm', q='piece 3')) == [31, 32]
    rows = _list(world, fit_mode='can_hold', fit_size='300,300,500', q='piece 3')
    assert _numbers(rows) == [33, 31, 32, 30]
    assert rows[0]['fit']['waste_mm3'] == 0


def test_the_row_schema_describes_fit(world):
    schema = world['api'].get('/schema/catalog-row').json()
    fit = schema['properties']['fit']
    assert {ref['$ref'] for ref in fit['anyOf'] if '$ref' in ref} == {
        '#/$defs/FitAbout', '#/$defs/FitCanHold'}
    assert 'fit' not in schema.get('required', [])
    assert set(schema['$defs']['FitAbout']['properties']) == {'mode', 'deviation'}
    assert set(schema['$defs']['FitCanHold']['properties']) == {
        'mode', 'waste_mm3', 'waste_percent'}
