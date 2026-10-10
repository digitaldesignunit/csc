"""The identity list does not sort or return whole joined documents.

Hotfix 0.6.0.1: production (Atlas free tier) caps a blocking sort at 32 MB and
ignores allowDiskUse; ``build_list_pipeline`` without a limit sorted the
joined documents after the lookup, with the inline meshes of the external
catalogue pieces: ``QueryExceededMemoryLimitNoDiskUseAllowed``. A sort on an
identity field runs before the join.

0.6.1.0 A4 (Atlas traffic): the join is projected to the fields a row, the
filters and the sort read, inside the lookup, so no row carries geometry,
descriptors or proxies; only a passport row (``expand=current_snapshot``)
carries the whole state, joined after ``$skip`` / ``$limit``.
"""

from __future__ import annotations

import bson
import pytest
from pymongo.errors import OperationFailure

from apps.catalog.api.identities import _format_list_rows
from apps.catalog.api.identity_query import (
    MAP_SNAPSHOT_FIELDS,
    ROW_SNAPSHOT_FIELDS,
    SORT_SNAPSHOT_FIELDS,
    build_count_pipeline,
    build_list_pipeline,
)
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import seed_05_catalog

SNAPSHOTS = 'component_snapshots'
FULL_LOOKUP = {'$lookup': {'from': SNAPSHOTS, 'localField': 'current_snapshot_id',
                           'foreignField': '_id', 'as': 'current_snapshot'}}


def _pipeline(sortkey='_id', size=0, page=0, snapshot_match=None, **over):
    args = dict(snapshots_collection=SNAPSHOTS, identity_match={},
                snapshot_match=snapshot_match or {}, sortkey=sortkey,
                sort_order=1, page=page, size=size, include_username=False,
                current_user_id=None, reserved_filter=None)
    args.update(over)
    return build_list_pipeline(**args)


def _names(pipeline):
    return [next(iter(stage)) for stage in pipeline]


def _projected(stage):
    return set(stage['$lookup']['pipeline'][0]['$project'])


# THE ORDER OF THE STAGES -----------------------------------------------------
def test_an_identity_sort_runs_right_after_the_first_match_before_the_join():
    for key in ('_id', 'catalog_number', 'dataset', 'material', 'reserved'):
        pipeline = _pipeline(sortkey=key)
        assert _names(pipeline)[:4] == ['$match', '$sort', '$lookup', '$unwind']
        assert pipeline[1] == {'$sort': {key: 1}}
        assert _names(pipeline).count('$sort') == 1
    # an unknown key falls back to _id: the same early sort
    assert _pipeline(sortkey='nonsense')[1] == {'$sort': {'_id': 1}}
    # skip and limit stay last (a row view)
    paged = _pipeline(sortkey='_id', page=2, size=10,
                      snapshot_match={'current_snapshot.status': 'published'},
                      include_username=True)
    assert _names(paged)[-2:] == ['$skip', '$limit']
    assert paged[-2] == {'$skip': 10} and paged[-1] == {'$limit': 10}
    assert _names(paged).index('$sort') == 1


def test_the_join_is_projected_whatever_the_sort_and_the_limit():
    for kwargs in (dict(), dict(page=1, size=20), dict(page=0, size=20)):
        for key in ('_id', 'name', 'bbx.0'):
            pipeline = _pipeline(sortkey=key, **kwargs)
            lookups = [s for s in pipeline if '$lookup' in s]
            assert len(lookups) == 1
            assert _projected(lookups[0]) == set(ROW_SNAPSHOT_FIELDS)


def test_a_snapshot_sort_sorts_the_slim_join():
    pipeline = _pipeline(sortkey='name',
                         snapshot_match={'current_snapshot.status': 'published'})
    assert _names(pipeline) == ['$match', '$lookup', '$unwind', '$match', '$sort']
    assert pipeline[4] == {'$sort': {'current_snapshot.name': 1}}


def test_a_passport_view_joins_the_whole_state_after_the_page_is_cut():
    paged = _pipeline(sortkey='name', page=2, size=5, snapshot_view='full',
                      snapshot_match={'current_snapshot.status': 'published'})
    assert _names(paged) == ['$match', '$lookup', '$unwind', '$match', '$sort',
                             '$skip', '$limit', '$lookup', '$unwind']
    assert _projected(paged[1]) == set(ROW_SNAPSHOT_FIELDS)
    assert 'pipeline' not in paged[7]['$lookup']             # the whole state
    # no limit: still joined last, after the (slim) sort
    every = _pipeline(sortkey='name', snapshot_view='full')
    assert _names(every) == ['$match', '$lookup', '$unwind', '$sort',
                             '$lookup', '$unwind']
    # an identity sort with a limit: the early sort, the cut, then the join
    early = _pipeline(sortkey='_id', size=3, snapshot_view='full')
    assert _names(early) == ['$match', '$sort', '$lookup', '$unwind', '$limit',
                             '$lookup', '$unwind']


def test_the_map_view_joins_the_descriptors_and_the_count_the_filter_fields():
    pipeline = _pipeline(snapshot_view='map')
    assert _projected(pipeline[2]) == set(MAP_SNAPSHOT_FIELDS)
    assert 'descriptors' in MAP_SNAPSHOT_FIELDS
    assert 'descriptors' not in ROW_SNAPSHOT_FIELDS
    count = build_count_pipeline(
        snapshots_collection=SNAPSHOTS, identity_match={}, snapshot_match={},
        reserved_filter=None, current_user_id=None, include_username=False)
    assert _projected(count[1]) == set(SORT_SNAPSHOT_FIELDS)
    assert count[-1] == {'$count': 'count'}


def test_the_filters_read_only_projected_snapshot_fields():
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
    assert set(SORT_SNAPSHOT_FIELDS) <= set(ROW_SNAPSHOT_FIELDS)


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
             'descriptors': {'radial': [0.5] * 500},
             'geometry': {'meshes': [{'blob': BLOB}]}})


def _run(db, pipeline):
    return list(db['component_identities'].aggregate(
        pipeline, allowDiskUse=False))


def _old(sort, extra=()):
    """What production ran before 0.6.0.1: the whole join, then the sort."""
    return [{'$match': {}}, FULL_LOOKUP, {'$unwind': '$current_snapshot'},
            {'$sort': sort}, *extra]


def test_a_listing_without_a_limit_survives_a_small_blocking_sort(
        db, small_sort_limit):
    _world(db)
    with pytest.raises(OperationFailure) as error:
        _run(db, _old({'_id': 1}))                  # what production did
    assert 'memory limit' in str(error.value).lower() or error.value.code == 292

    by_id = _run(db, _pipeline(sortkey='_id'))
    assert [d['_id'] for d in by_id] == sorted(d['_id'] for d in by_id)
    assert len(by_id) == 40

    by_name = _run(db, _pipeline(sortkey='name'))
    names = [d['current_snapshot']['name'] for d in by_name]
    assert names == sorted(names) and len(names) == 40
    desc = _run(db, _pipeline(sortkey='name', sort_order=-1))
    assert [d['_id'] for d in desc] == [d['_id'] for d in reversed(by_name)]

    # a passport row has the whole state, mesh and descriptors included
    full = _run(db, _pipeline(sortkey='name', snapshot_view='full'))
    assert [d['_id'] for d in full] == [d['_id'] for d in by_name]
    state = full[0]['current_snapshot']
    assert state['geometry']['meshes'][0]['blob'] == BLOB
    assert len(state['descriptors']['radial']) == 500
    assert state['identity_id'] == full[0]['_id']


def test_a_row_carries_no_geometry_and_far_fewer_bytes(db):
    _world(db, count=20)
    row = _run(db, _pipeline())
    full = _run(db, _pipeline(snapshot_view='full'))
    mapped = _run(db, _pipeline(snapshot_view='map'))
    assert 'geometry' not in row[0]['current_snapshot']
    assert 'descriptors' not in row[0]['current_snapshot']
    assert 'descriptors' in mapped[0]['current_snapshot']
    assert 'geometry' not in mapped[0]['current_snapshot']
    size = lambda docs: sum(len(bson.encode(d)) for d in docs)   # noqa: E731
    assert size(row) * 100 < size(full)              # kilobytes against megabytes
    assert size(mapped) < size(full) / 5


def test_the_early_sort_gives_the_rows_the_old_order_gave(db):
    _world(db, count=25)
    skip_limit = [{'$skip': 7}, {'$limit': 7}]
    old = _old({'catalog_number': 1}, skip_limit)
    old.insert(4, {'$match': {'current_snapshot.status': 'published'}})
    new = _pipeline(sortkey='catalog_number', page=2, size=7,
                    snapshot_match={'current_snapshot.status': 'published'},
                    snapshot_view='full')
    assert [d['_id'] for d in _run(db, new)] == [d['_id'] for d in _run(db, old)]
    assert _run(db, new) == _run(db, old)             # the whole documents


# A ROW FROM THE PROJECTED JOIN IS THE ROW FROM THE FULL DOCUMENT -------------
@pytest.fixture
def catalog(db, api):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    return db


@pytest.mark.parametrize('expand, view', [
    ('shallow', 'row'), ('none', 'row'), ('current_snapshot', 'full')])
@pytest.mark.parametrize('sortkey', ['_id', 'name', 'catalog_number'])
def test_rows_from_the_projected_join_equal_rows_from_the_full_document(
        catalog, expand, view, sortkey):
    key = {'_id': '_id', 'name': 'current_snapshot.name',
           'catalog_number': 'catalog_number'}[sortkey]
    old = _run(catalog, _old({key: 1}))
    new = _run(catalog, _pipeline(sortkey=sortkey, snapshot_view=view))
    assert len(old) >= 5 and [d['_id'] for d in new] == [d['_id'] for d in old]
    assert _format_list_rows(new, expand) == _format_list_rows(old, expand)
    # the same with a page cut after the sort
    page_old = _run(catalog, _old({key: 1}, [{'$skip': 3}, {'$limit': 3}]))
    page_new = _run(catalog, _pipeline(sortkey=sortkey, page=2, size=3,
                                       snapshot_view=view))
    assert [d['_id'] for d in page_new] == [d['_id'] for d in page_old]
    assert len(page_new) == 3 or len(old) < 6
    assert _format_list_rows(page_new, expand) ==         _format_list_rows(page_old, expand)
