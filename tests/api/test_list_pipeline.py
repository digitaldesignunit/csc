"""The identity list does not sort whole joined documents (hotfix 0.6.0.1).

Production (Atlas free tier) caps a blocking sort at 32 MB and ignores
allowDiskUse. ``build_list_pipeline`` without a limit used to sort the
joined documents after the lookup, with the inline meshes of the external
catalogue pieces: ``QueryExceededMemoryLimitNoDiskUseAllowed``. A sort on an
identity field now runs before the join; one on a snapshot field sorts slim
states and joins the whole ones after the sort.
"""

from __future__ import annotations

import pytest
from pymongo.errors import OperationFailure

from apps.catalog.api.identity_query import (
    SORT_SNAPSHOT_FIELDS,
    build_list_pipeline,
)

SNAPSHOTS = 'component_snapshots'


def _pipeline(sortkey='_id', size=0, page=0, snapshot_match=None, **over):
    args = dict(snapshots_collection=SNAPSHOTS, identity_match={},
                snapshot_match=snapshot_match or {}, sortkey=sortkey,
                sort_order=1, page=page, size=size, include_username=False,
                current_user_id=None, reserved_filter=None)
    args.update(over)
    return build_list_pipeline(**args)


def _names(pipeline):
    return [next(iter(stage)) for stage in pipeline]


def test_an_identity_sort_runs_right_after_the_first_match_before_the_join():
    for key in ('_id', 'catalog_number', 'dataset', 'material', 'reserved'):
        pipeline = _pipeline(sortkey=key)
        assert _names(pipeline)[:4] == ['$match', '$sort', '$lookup', '$unwind']
        assert pipeline[1] == {'$sort': {key: 1}}
        assert _names(pipeline).count('$sort') == 1
    # an unknown key falls back to _id: the same early sort
    assert _pipeline(sortkey='nonsense')[1] == {'$sort': {'_id': 1}}
    # skip and limit stay last
    paged = _pipeline(sortkey='_id', page=2, size=10,
                      snapshot_match={'current_snapshot.status': 'published'},
                      include_username=True)
    assert _names(paged)[-2:] == ['$skip', '$limit']
    assert paged[-2] == {'$skip': 10} and paged[-1] == {'$limit': 10}
    assert _names(paged).index('$sort') == 1


def test_a_snapshot_sort_without_a_limit_sorts_slim_states_and_joins_after():
    pipeline = _pipeline(sortkey='name',
                         snapshot_match={'current_snapshot.status': 'published'})
    names = _names(pipeline)
    assert names == ['$match', '$lookup', '$unwind', '$match', '$sort',
                     '$lookup', '$unwind']
    slim, full = pipeline[1]['$lookup'], pipeline[5]['$lookup']
    assert set(slim['pipeline'][0]['$project']) == set(SORT_SNAPSHOT_FIELDS)
    assert 'pipeline' not in full and full['as'] == 'current_snapshot'
    assert pipeline[4] == {'$sort': {'current_snapshot.name': 1}}


def test_a_snapshot_sort_with_a_limit_keeps_the_plain_join():
    for kwargs in (dict(page=1, size=20), dict(page=0, size=20)):
        pipeline = _pipeline(sortkey='name', **kwargs)
        assert _names(pipeline)[:4] == ['$match', '$lookup', '$unwind', '$sort']
        assert 'pipeline' not in pipeline[1]['$lookup']       # top-k sort: small
        assert _names(pipeline).count('$lookup') == 1


def test_the_filters_read_only_slim_snapshot_fields():
    from apps.catalog.api.identity_filters import CatalogFilters
    match = CatalogFilters(status='published', q='beam', shape_class='planar',
                           complexity=2, fragment=True, bbx_min_x=1,
                           bbx_max_z=9).snapshot_match()
    wanted = set()
    stack = [match]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key.startswith('current_snapshot.'):
                    wanted.add(key.split('.')[1])
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    assert wanted <= set(SORT_SNAPSHOT_FIELDS), wanted


# AGAINST A REAL MONGOD -------------------------------------------------------
BLOB = 'x' * 150_000          # an inline mesh, roughly


@pytest.fixture
def small_sort_limit(db):
    admin = db.client.admin
    default = admin.command('getParameter', 1,
                            internalQueryMaxBlockingSortMemoryUsageBytes=1)[
        'internalQueryMaxBlockingSortMemoryUsageBytes']
    admin.command('setParameter', 1,
                  internalQueryMaxBlockingSortMemoryUsageBytes=2_000_000)
    yield
    admin.command('setParameter', 1,
                  internalQueryMaxBlockingSortMemoryUsageBytes=default)


def _world(db, count=40):
    for n in range(count):
        iid, sid = f'i{n:03d}', f's{n:03d}'
        db['component_identities'].insert_one(
            {'_id': iid, 'catalog_number': count - n, 'dataset': 'd',
             'current_snapshot_id': sid, 'exit': None, 'withdrawn': None})
        db[SNAPSHOTS].insert_one(
            {'_id': sid, 'identity_id': iid, 'status': 'published',
             'name': f'piece {(n * 7) % count:03d}', 'bbx': [n, 1, 1],
             'geometry': {'meshes': [{'blob': BLOB}]}})


def _run(db, pipeline):
    return list(db['component_identities'].aggregate(
        pipeline, allowDiskUse=False))


def test_a_listing_without_a_limit_survives_a_small_blocking_sort(
        db, small_sort_limit):
    _world(db)
    old = [{'$match': {}},
           {'$lookup': {'from': SNAPSHOTS, 'localField': 'current_snapshot_id',
                        'foreignField': '_id', 'as': 'current_snapshot'}},
           {'$unwind': '$current_snapshot'}, {'$sort': {'_id': 1}}]
    with pytest.raises(OperationFailure) as error:
        _run(db, old)                              # what production did
    assert 'memory limit' in str(error.value).lower() or error.value.code == 292

    by_id = _run(db, _pipeline(sortkey='_id'))
    assert [d['_id'] for d in by_id] == sorted(d['_id'] for d in by_id)
    assert len(by_id) == 40
    assert by_id[0]['current_snapshot']['geometry']['meshes'][0]['blob'] == BLOB

    by_name = _run(db, _pipeline(sortkey='name'))
    names = [d['current_snapshot']['name'] for d in by_name]
    assert names == sorted(names) and len(names) == 40
    # the whole state is back after the sort: the mesh, and every field
    assert by_name[0]['current_snapshot']['geometry']['meshes'][0]['blob'] == BLOB
    assert by_name[0]['current_snapshot']['identity_id'] == by_name[0]['_id']
    desc = _run(db, _pipeline(sortkey='name', sort_order=-1))
    assert [d['_id'] for d in desc] == [d['_id'] for d in reversed(by_name)]


def test_the_early_sort_gives_the_rows_the_old_order_gave(db):
    _world(db, count=25)
    old = [{'$match': {}},
           {'$lookup': {'from': SNAPSHOTS, 'localField': 'current_snapshot_id',
                        'foreignField': '_id', 'as': 'current_snapshot'}},
           {'$unwind': '$current_snapshot'},
           {'$match': {'current_snapshot.status': 'published'}},
           {'$sort': {'catalog_number': 1}}, {'$skip': 7}, {'$limit': 7}]
    new = _pipeline(sortkey='catalog_number', page=2, size=7,
                    snapshot_match={'current_snapshot.status': 'published'})
    assert [d['_id'] for d in _run(db, new)] == [d['_id'] for d in _run(db, old)]
    assert _run(db, new) == _run(db, old)
