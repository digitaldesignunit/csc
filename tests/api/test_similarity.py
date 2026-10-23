"""
True similarity (decision 8.174): the standardised feature matrix, its cache
and the cron that builds it, and ``GET /identities/{id}/similar`` with the
visibility, the filters before the ranking and the errors in words.
"""

from __future__ import annotations

import asyncio
import uuid

import numpy as np
import pytest

from apps.catalog import similarity as sim
from apps.catalog.geo import point_of

SCALAR_KEYS = ('boxscore', 'spherescore', 'linescore', 'planescore')


def pid(n):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'csc-test/sim/{n}'))


# THE PURE PARTS ----------------------------------------------------------------
def test_standardising_gives_zero_mean_and_unit_deviation_and_leaves_a_flat_column_at_zero():
    data = np.array([[1.0, 5.0, 7.0], [2.0, 5.0, 9.0], [3.0, 5.0, 11.0], [6.0, 5.0, 13.0]])
    z, mean, std = sim.standardise(data)
    assert z.dtype == np.float32
    assert np.allclose(z[:, [0, 2]].mean(axis=0), 0, atol=1e-6)
    assert np.allclose(z[:, [0, 2]].std(axis=0), 1, atol=1e-6)
    # the column without variance: no division by zero, nothing in a distance
    assert np.all(z[:, 1] == 0) and std[1] == 1.0 and mean[1] == 5.0
    assert np.isfinite(z).all()
    # one row: every dimension is flat
    z1, _, std1 = sim.standardise(np.array([[3.0, 4.0]]))
    assert np.all(z1 == 0) and np.all(std1 == 1)
    with pytest.raises(ValueError):
        sim.standardise(np.zeros((0, 3)))
    # a new vector lands in the same space as the matrix rows
    again = sim.standardise_vector(data[2], mean, std)
    assert np.allclose(again, z[2], atol=1e-6)


def test_a_piece_added_after_the_build_is_zero_in_the_flat_columns_too():
    data = np.array([[1.0, 5.0, 7.0], [2.0, 5.0, 9.0], [3.0, 5.0, 11.0], [6.0, 5.0, 13.0]])
    z, mean, std = sim.standardise(data)
    flat = sim.flat_columns(data)
    assert flat.tolist() == [False, True, False]
    # a new piece with another value in the flat column: without the mask that adds 2.0 to its distances
    new = np.array([2.0, 7.0, 9.0])
    assert sim.standardise_vector(new, mean, std)[1] == pytest.approx(2.0)
    masked = sim.standardise_vector(new, mean, std, flat)
    assert masked[1] == 0.0 and np.allclose(masked[[0, 2]], z[1, [0, 2]], atol=1e-6)
    # the mask survives the stored document; a document without it (older build) has none
    matrix = sim.FeatureMatrix('scalars', list('abcd'), z, mean, std, 't', 'b', flat)
    doc = sim.matrix_to_doc(matrix, 't')
    assert doc['flat'] == [1] and sim.matrix_from_doc(doc).flat.tolist() == [False, True, False]
    del doc['flat']
    assert not sim.matrix_from_doc(doc).flat.any()


def _matrix(vectors):
    names = list(vectors)
    z = np.asarray([vectors[n] for n in names], dtype=np.float32)
    return sim.FeatureMatrix('scalars', names, z, np.zeros(z.shape[1]), np.ones(z.shape[1]), 't', 'b')


def test_the_nearest_are_ranked_by_euclidean_distance_without_the_piece_itself():
    matrix = _matrix({'a': [0, 0], 'b': [1, 0], 'c': [-2, 0], 'd': [3, 4], 'e': [10, 0]})
    ranked, considered = sim.nearest(matrix, matrix.vector_of('a'), None, 3, exclude='a')
    assert ranked == [('b', 1.0), ('c', 2.0), ('d', 5.0)] and considered == 4
    # k beyond the rows: every other piece
    assert [i for i, _ in sim.nearest(matrix, matrix.vector_of('a'), None, 99, exclude='a')[0]] == [
        'b', 'c', 'd', 'e']
    # the candidates come first, then the ranking: the k nearest that pass
    ranked, considered = sim.nearest(matrix, matrix.vector_of('a'), ['d', 'e', 'a', 'zzz'], 1, exclude='a')
    assert ranked == [('d', 5.0)] and considered == 2          # 'zzz' has no row, 'a' is the query
    assert sim.nearest(matrix, matrix.vector_of('a'), [], 3, exclude='a') == ([], 0)
    assert sim.nearest(matrix, matrix.vector_of('a'), None, 0)[0] == []
    # a query that is not a row of the matrix
    assert sim.nearest(matrix, np.array([9.0, 0.0]), None, 1)[0] == [('e', 1.0)]


def test_ties_are_broken_by_id_so_the_answer_is_stable():
    vectors = {f'p{n:02d}': [1.0, 0.0] for n in range(30)}
    vectors['q'] = [0.0, 0.0]
    matrix = _matrix(vectors)
    ranked, _ = sim.nearest(matrix, matrix.vector_of('q'), None, 5, exclude='q')
    assert [i for i, _ in ranked] == ['p00', 'p01', 'p02', 'p03', 'p04']
    # the same on the partial-sort path (many candidates, few asked)
    many = _matrix({**{f'p{n:03d}': [1.0, 0.0] for n in range(200)}, 'q': [0.0, 0.0]})
    ranked, _ = sim.nearest(many, many.vector_of('q'), None, 3, exclude='q')
    assert [i for i, _ in ranked] == ['p000', 'p001', 'p002']


def test_the_matrix_document_round_trips_as_float32_with_its_ids():
    matrix = _matrix({'a': [0.5, -1.25, 3.0], 'b': [2.0, 0.0, -0.75]})
    doc = sim.matrix_to_doc(matrix, '2026-10-22T00:00:00Z')
    assert doc['_id'] == 'knn:scalars' and doc['n'] == 2 and doc['dim'] == 3
    assert len(bytes(doc['matrix'])) == 2 * 3 * 4              # float32
    back = sim.matrix_from_doc(doc)
    assert back.ids == ['a', 'b'] and back.basis == 'scalars' and back.build_id == 'b'
    assert np.array_equal(back.z, matrix.z) and back.index == {'a': 0, 'b': 1}


def test_a_matrix_is_built_from_the_pieces_that_have_the_descriptor():
    rows = [
        {'_id': 'a', 'descriptors': dict(zip(SCALAR_KEYS, (0.1, 0.2, 0.3, 0.4)))},
        {'_id': 'b', 'descriptors': dict(zip(SCALAR_KEYS, (0.3, 0.2, 0.9, 0.4)))},
        {'_id': 'c', 'descriptors': {}},                                    # nothing derived yet
        {'_id': 'd', 'descriptors': {'boxscore': 0.1}},                     # incomplete
        {'_id': 'e'},
        {'_id': 'f', 'descriptors': dict(zip(SCALAR_KEYS, (0.5, 0.2, 0.1, 0.4)))},
    ]
    matrix = sim.build_feature_matrix(rows, 'scalars', 't')
    assert matrix.ids == ['a', 'b', 'f'] and matrix.dim == 4
    # the two flat columns carry no weight
    assert np.all(matrix.z[:, 1] == 0) and np.all(matrix.z[:, 3] == 0)
    assert matrix.flat.tolist() == [False, True, False, True]
    assert sim.build_feature_matrix(rows, 'hks') is None
    assert sim.build_feature_matrix([], 'scalars') is None


# THE CATALOG ---------------------------------------------------------------------
# number: scalars, dataset, public, circulation, bbx, current point
PIECES = {
    1: ((0.0, 0.0, 0.0, 0.0), 'dset', True, 'in', [1200, 600, 200], (49.8728, 8.6512)),
    2: ((1.0, 0.0, 0.0, 0.0), 'dset', True, 'in', [1200, 600, 200], (49.8728, 8.6512)),
    3: ((0.0, 2.0, 0.0, 0.0), 'dset', True, 'in', [300, 300, 300], (52.52, 13.405)),
    4: ((0.0, 0.0, 3.0, 4.0), 'dset', True, 'in', [1200, 600, 200], (50.1109, 8.6821)),
    5: ((9.0, 9.0, 9.0, 9.0), 'dset', True, 'in', [1200, 600, 200], None),
    6: ((0.5, 0.0, 0.0, 0.0), 'other', False, 'in', [1200, 600, 200], (49.8728, 8.6512)),   # private
    7: (None, 'dset', True, 'in', [1200, 600, 200], None),                                     # no descriptor
    8: ((0.2, 0.0, 0.0, 0.0), 'dset', True, 'out', [1200, 600, 200], (49.8728, 8.6512)),       # exited
    9: ((0.1, 0.0, 0.0, 0.0), 'dset', True, 'in', [1200, 600, 200], (49.8728, 8.6512)),         # withdrawn
}


def _insert(db, number, vector, dataset, public, circulation, bbx, point, withdrawn=False):
    identity_id, snapshot_id = pid(number), str(uuid.uuid5(uuid.NAMESPACE_URL, f'csc-test/sim/s{number}'))
    doc = {
        '_id': identity_id, 'catalog_number': number, 'dataset': dataset,
        'original_function': 'IfcBeam', 'material': 'timber', 'material_class': '17 02 01',
        'is_public': public, 'current_snapshot_id': snapshot_id,
        'exit': None if circulation == 'in' else {'kind': 'recycled', 'at': '2026-01-02T00:00:00Z',
                                                  'recorded_by_user_id': 'u-test'},
        'withdrawn': {'at': '2026-01-02T00:00:00Z', 'by_user_id': 'u-test', 'reason': 'x',
                      'duplicate_of': None} if withdrawn else None,
        'created': '2026-01-01T00:00:00Z', 'lastmodified': '2026-01-01T00:00:00Z',
        'created_by_user_id': 'u-test'}
    snapshot = {
        '_id': snapshot_id, 'identity_id': identity_id, 'version': 1, 'status': 'published',
        'name': f'piece {number}', 'bbx': bbx, 'created': '2026-01-01T00:00:00Z',
        'lastmodified': '2026-01-01T00:00:00Z', 'effective_from': '2026-01-01T00:00:00Z',
        'geometry': {}, 'added_by_user_id': 'u-test',
        'descriptors': dict(zip(SCALAR_KEYS, vector)) if vector else {}}
    if point:
        doc['geo_current'] = point_of({'lat': point[0], 'lon': point[1]})
        snapshot['location'] = {'lat': point[0], 'lon': point[1]}
    db['component_identities'].insert_one(doc)
    db['component_snapshots'].insert_one(snapshot)


def _build(db, mongod, db_name, **kw):
    """Run the cron's matrix step against the test database."""
    from pymongo import AsyncMongoClient
    import main_component_map as cron

    async def run():
        client = AsyncMongoClient(mongod.uri)
        try:
            database = client[db_name]
            return await cron.compute_and_store_knn(
                identities_col=database['component_identities'],
                snapshots_collection='component_snapshots',
                cache_col=database['component_map_cache'],
                bases=kw.pop('bases', ('scalars',)), dry_run=kw.pop('dry_run', False))
        finally:
            await client.close()

    return asyncio.run(run())


@pytest.fixture
def world(api, db, mongod, db_name, auth_headers):
    for number, (vector, dataset, public, circulation, bbx, point) in PIECES.items():
        _insert(db, number, vector, dataset, public, circulation, bbx, point, withdrawn=number == 9)
    return {'api': api, 'db': db, 'mongod': mongod, 'db_name': db_name,
            'admin': auth_headers('admin'), 'user': auth_headers('user')}


def _built(world, **kw):
    return _build(world['db'], world['mongod'], world['db_name'], **kw)


def _similar(world, piece, who='admin', expect=200, **params):
    response = world['api'].get(f'/identities/{pid(piece)}/similar', params={'basis': 'scalars', **params},
                                headers=world.get(who) if who else None)
    assert response.status_code == expect, response.text
    return response.json()


def _numbers(body):
    return [r['piece']['catalog_number'] for r in body['results']]


# THE CRON --------------------------------------------------------------------
def test_the_two_one_sided_flags_exclude_each_other():
    import main_component_map as cron
    assert cron._parse_args(['--knn-only']).knn_only and cron._parse_args(['--no-knn']).no_knn
    with pytest.raises(SystemExit):
        cron._parse_args(['--knn-only', '--no-knn'])


def test_the_cron_builds_one_matrix_per_basis_of_every_piece_with_the_descriptor(world):
    assert _built(world) == 1                          # only scalars exist in this catalog
    doc = world['db']['component_map_cache'].find_one({'_id': 'knn:scalars'})
    # every piece with the descriptor, whoever may see it later: private, exited, withdrawn
    assert doc['n'] == 8 and doc['dim'] == 4 and set(doc['ids']) == {pid(n) for n in PIECES if n != 7}
    assert len(bytes(doc['matrix'])) == 8 * 4 * 4
    assert world['db']['component_map_cache'].find_one({'_id': 'knn:radial_signature'}) is None
    first = doc['build_id']
    assert _built(world) == 1                          # a run replaces it, with a new version
    assert world['db']['component_map_cache'].find_one({'_id': 'knn:scalars'})['build_id'] != first
    world['db']['component_map_cache'].delete_many({})
    assert _built(world, dry_run=True) == 1            # a dry run writes nothing
    assert world['db']['component_map_cache'].count_documents({}) == 0


def test_the_stored_matrix_is_standardised_over_the_catalog(world):
    _built(world)
    doc = world['db']['component_map_cache'].find_one({'_id': 'knn:scalars'})
    matrix = sim.matrix_from_doc(doc)
    raw = np.array([PIECES[int(i)][0] for i in [next(n for n in PIECES if pid(n) == x) for x in matrix.ids]])
    assert np.allclose(matrix.z.mean(axis=0), 0, atol=1e-5)
    assert np.allclose(matrix.z.std(axis=0), 1, atol=1e-5)
    assert np.allclose(matrix.mean, raw.mean(axis=0)) and np.allclose(matrix.std, raw.std(axis=0))


# THE ROUTE ---------------------------------------------------------------------
def test_the_nearest_pieces_are_ranked_in_the_standardised_space_without_the_piece_itself(world):
    _built(world)
    body = _similar(world, 1, circulation='all', status='any', include_withdrawn='true', count=50)
    # independent of the code under test: z-scores by hand over the 8 pieces that have the descriptor
    have = [n for n in PIECES if PIECES[n][0]]
    raw = np.array([PIECES[n][0] for n in have], dtype=float)
    std = raw.std(axis=0)
    z = (raw - raw.mean(axis=0)) / np.where(std > 1e-12, std, 1)
    expected = sorted(((float(np.linalg.norm(z[have.index(n)] - z[have.index(1)])), n)
                       for n in have if n != 1))
    assert [(round(r['distance'], 4), r['piece']['catalog_number']) for r in body['results']] == [
        (round(d, 4), n) for d, n in expected]
    assert 1 not in _numbers(body)
    assert body['basis'] == 'scalars' and body['query_id'] == pid(1) and body['computed_at']
    assert body['considered'] == len(expected)
    # distances are non-negative numbers in ascending order
    distances = [r['distance'] for r in body['results']]
    assert distances == sorted(distances) and all(d > 0 for d in distances)


def test_the_count_limits_the_answer_and_a_row_has_what_a_card_needs(world):
    _built(world)
    body = _similar(world, 1, count=2)
    assert len(body['results']) == 2
    row = body['results'][0]['piece']
    assert {'_id', 'catalog_number', 'name', 'current_snapshot_id', 'has_preview', 'dataset', 'bbx'} <= set(row)
    assert row['name'] == f'piece {row["catalog_number"]}'
    assert 'fit' not in row and 'distance_m' not in row
    assert world['api'].get(f'/identities/{pid(1)}/similar', params={'basis': 'scalars', 'count': 51},
                            headers=world['admin']).status_code == 422
    assert world['api'].get(f'/identities/{pid(1)}/similar', params={'basis': 'scalars', 'count': 0},
                            headers=world['admin']).status_code == 422


def test_the_filters_apply_before_the_ranking(world):
    _built(world)
    # the default scope: in circulation, published, not withdrawn: 6 (private, admin sees it), 8 (exited)
    # and 9 (withdrawn) are not in it, 7 has no descriptor
    assert sorted(_numbers(_similar(world, 1, count=50))) == [2, 3, 4, 5, 6]
    # a dimension search first: only 2 and 4 (and 1 itself) can hold 1200 x 600 x 200 ... 3 and 6/5? 5 and 6 can too
    held = _similar(world, 1, count=50, fit_mode='can_hold', fit_size='1200,600,200')
    assert sorted(_numbers(held)) == [2, 4, 5, 6]
    assert all(r['piece']['fit']['mode'] == 'can_hold' for r in held['results'])
    # only the 2 nearest of those that pass, not the 2 nearest of everyone
    near_two = _similar(world, 1, count=2, fit_mode='can_hold', fit_size='1200,600,200')
    assert _numbers(near_two) == [6, 2] and near_two['considered'] == 4
    # a near search: within 30 km of Darmstadt; the rows carry their distance
    around = _similar(world, 1, count=50, near_lat=49.8728, near_lon=8.6512, radius_km=30)
    assert sorted(_numbers(around)) == [2, 4, 6] and all('distance_m' in r['piece'] for r in around['results'])
    both = _similar(world, 1, count=50, near_lat=49.8728, near_lon=8.6512, radius_km=30,
                    fit_mode='can_hold', fit_size='1200,600,200')
    assert sorted(_numbers(both)) == [2, 4, 6]
    # the other filters of the list: dataset, a name, circulation
    assert _numbers(_similar(world, 1, dataset='other')) == [6]
    assert _numbers(_similar(world, 1, q='piece 4')) == [4]
    assert sorted(_numbers(_similar(world, 1, count=50, circulation='all'))) == [2, 3, 4, 5, 6, 8]
    assert sorted(_numbers(_similar(world, 1, count=50, circulation='exited'))) == [8]
    assert _numbers(_similar(world, 1, count=50, material='nothing')) == []


def test_a_piece_the_caller_cannot_see_is_not_there_and_is_never_a_neighbour(world):
    _built(world)
    admin = _similar(world, 1, count=50)
    assert 6 in _numbers(admin)                        # the administrator sees the private piece
    for who in ('user', None):
        body = _similar(world, 1, who=who, count=50)
        assert sorted(_numbers(body)) == [2, 3, 4, 5]
        assert 'piece 6' not in str(body) and 'other' not in str(body['results'])
        assert body['considered'] == 4
        # the private piece as the query: the same 404 as for a piece that does not exist
        hidden = world['api'].get(f'/identities/{pid(6)}/similar', params={'basis': 'scalars'},
                                  headers=world.get(who) if who else None)
        assert hidden.status_code == 404, who
        missing = world['api'].get(f'/identities/{pid(99)}/similar', params={'basis': 'scalars'},
                                   headers=world.get(who) if who else None)
        assert missing.status_code == 404 and missing.json()['detail'].startswith('Component')
    # a dataset filter naming it finds nothing for them
    assert _similar(world, 1, who='user', dataset='other')['results'] == []
    # an identity id that is not an id
    assert world['api'].get('/identities/not-an-id/similar', headers=world['admin']).status_code == 404


def test_the_errors_say_what_is_missing(world):
    # no matrix yet: a conflict in words, not a 500
    body = _similar(world, 1, expect=409)
    assert 'not been computed' in body['detail'] and 'scalars' in body['detail']
    _built(world)
    # the default basis is the radial signature and has no matrix in this catalog
    default = world['api'].get(f'/identities/{pid(1)}/similar', headers=world['admin'])
    assert default.status_code == 409 and 'radial_signature' in default.json()['detail']
    # a piece without the descriptor cannot be compared
    none = _similar(world, 7, expect=422)
    assert 'no scalar descriptors descriptor' in none['detail'] or 'descriptor' in none['detail']
    assert world['api'].get(f'/identities/{pid(1)}/similar', params={'basis': 'sky'},
                            headers=world['admin']).status_code == 422
    # bad filters are the list's 422
    assert _similar(world, 1, expect=422, near_lat=49.0)['detail']
    assert _similar(world, 1, expect=422, fit_mode='about')['detail']


def test_a_piece_added_after_the_matrix_was_built_is_compared_by_its_own_descriptor(world):
    _built(world)
    _insert(world['db'], 20, (0.1, 0.0, 0.0, 0.0), 'dset', True, 'in', [1200, 600, 200], None)
    body = _similar(world, 20, count=3)
    # nearest in the built matrix to a piece just beside piece 1
    assert _numbers(body)[0] == 1 and 20 not in _numbers(body)
    # but the new piece is not itself a neighbour until the next build
    assert 20 not in _numbers(_similar(world, 1, count=50))
    _built(world)
    assert 20 in _numbers(_similar(world, 1, count=50))


def test_a_rebuilt_matrix_is_picked_up_without_a_restart(world):
    _built(world)
    before = _numbers(_similar(world, 1, count=50))
    world['db']['component_snapshots'].update_one(
        {'identity_id': pid(5)}, {'$set': {'descriptors': dict(zip(SCALAR_KEYS, (0.05, 0.0, 0.0, 0.0)))}})
    assert _numbers(_similar(world, 1, count=50)) == before          # the old matrix until the cron runs
    _built(world)
    assert _numbers(_similar(world, 1, count=1)) == [5]


def test_the_schema_of_the_answer_is_served_for_the_generator(world):
    schema = world['api'].get('/schema/similar-pieces').json()
    assert {'query_id', 'basis', 'considered', 'results'} <= set(schema['properties'])
    assert 'SimilarPiece' in schema['$defs'] and 'standardised' in schema['$defs']['SimilarPiece']['properties'][
        'distance']['description']
