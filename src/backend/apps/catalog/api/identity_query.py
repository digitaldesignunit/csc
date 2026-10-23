"""
Aggregation pipelines for listing identities with current snapshot.
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from apps.catalog.read_models import catalog_row

from .dimension_fit import match_sort_field, sorted_sides, volume_stages
from .identity_filters import resolve_sort_field
from .near_search import DISTANCE_FIELD, Near, distance_sort, first_stages


def annotate_has_preview(request: Request, docs: List[Dict[str, Any]]) -> None:
    """Say on each row whether its current state has a rendered preview, so a
    client asks for the image only when there is one (no 404 per row)."""
    preview_dir = request.app.snapshot_preview_dir
    for doc in docs:
        snapshot_id = doc.get('current_snapshot_id')
        doc['has_preview'] = bool(snapshot_id) and os.path.isfile(
            os.path.join(preview_dir, f'{snapshot_id}.webp'))


def _username_enrichment_stages() -> List[Dict[str, Any]]:
    return [
        {
            '$lookup': {
                'from': 'users',
                'localField': 'reserved',
                'foreignField': '_id',
                'as': 'user_info',
            }
        },
        {
            '$addFields': {
                'reserved_by_username': {
                    '$cond': {
                        'if': {'$gt': [{'$size': '$user_info'}, 0]},
                        'then': {'$arrayElemAt': ['$user_info.username', 0]},
                        'else': None,
                    }
                }
            }
        },
        {'$unset': 'user_info'},
    ]


# What the sort and the snapshot filters read of the current snapshot
# (``resolve_sort_field``, ``CatalogFilters.snapshot_match``): all small.
SORT_SNAPSHOT_FIELDS = (
    'status', 'name', 'shape_class', 'complexity', 'fragment', 'bbx',
    'color', 'effective_from', 'created', 'lastmodified',
)
# What a catalog row (``read_models.catalog_row``) reads of it; includes the
# sort and filter fields. No ``descriptors``, no inline ``geometry``, no
# proxies with their deviation data, no capture, no photos' bookkeeping.
ROW_SNAPSHOT_FIELDS = tuple(dict.fromkeys(SORT_SNAPSHOT_FIELDS + (
    'identity_id', 'version', 'effective_from_precision', 'location', 'frame',
    'etag', 'quantity',
)))
# What the component map reads (``component_map.map_rows_project_stage``)
# besides the filters: the descriptors are the map's input.
MAP_SNAPSHOT_FIELDS = tuple(dict.fromkeys(
    SORT_SNAPSHOT_FIELDS + ('descriptors',)))

# The three views of the joined snapshot (decision 8.136, Atlas traffic):
# ``row``  the fields a catalog row reads (Browse, the single row, the
#          children, the reservations); ``map`` the fields of the map;
# ``full`` the whole snapshot, joined after the page is cut (a passport row:
#          ``expand=current_snapshot``, read by Grasshopper).
SNAPSHOT_VIEWS = {'row': ROW_SNAPSHOT_FIELDS, 'map': MAP_SNAPSHOT_FIELDS,
                  'full': ROW_SNAPSHOT_FIELDS}


def _current_snapshot_lookup(snapshots_collection: str, *,
                             fields: Optional[tuple] = None
                             ) -> Dict[str, Any]:
    """The join of the current snapshot, projected to ``fields`` inside the
    lookup (nothing else leaves the database); the whole state without."""
    lookup: Dict[str, Any] = {
        'from': snapshots_collection,
        'localField': 'current_snapshot_id',
        'foreignField': '_id',
        'as': 'current_snapshot',
    }
    if fields is not None:
        lookup['pipeline'] = [{'$project': {name: 1 for name in fields}}]
    return {'$lookup': lookup}


def build_list_pipeline(
    *,
    snapshots_collection: str,
    identity_match: Dict[str, Any],
    snapshot_match: Dict[str, Any],
    sortkey: str,
    sort_order: int,
    page: int,
    size: int,
    include_username: bool,
    current_user_id: Optional[str],
    reserved_filter: Optional[str],
    snapshot_view: str = 'row',
    fit_stages: Optional[List[Dict[str, Any]]] = None,
    fit_mode: Optional[str] = None,
    near: Optional[Near] = None,
) -> List[Dict[str, Any]]:
    """The identities with their current snapshot. ``snapshot_view`` (see
    ``SNAPSHOT_VIEWS``) says how much of the snapshot comes back: the join is
    always projected to the fields the filters, the sort and the row read, so
    the sort never holds an inline mesh (Atlas' free tier caps a blocking sort
    at 32 MB and ignores allowDiskUse) and a row carries no geometry; the
    whole state of a ``full`` view is joined after ``$skip`` / ``$limit``.

    ``fit_stages`` (the dimension search, 8.169) come right after the filters
    of the snapshot and add ``fit`` to the row; the sort key ``match`` sorts
    on it (``fit_mode`` says which value), ``volume`` on the product of the
    sides of ``bbx`` (8.173). Both are computed, so they sort after the join.

    ``near`` (the near search, 8.170) opens the pipeline with ``$geoNear``
    instead of the plain ``$match``, which adds ``distance_m`` to the row; the
    sort key ``distance`` sorts on it, with the catalog number as the tie."""
    sort_prep: List[Dict[str, Any]] = []
    sort_drop: List[str] = []
    if sortkey == 'volume':
        sort_prep, sort_spec, sort_drop = volume_stages(sort_order)
        sort_field = 'volume'
    elif sortkey == 'match':
        sort_field = match_sort_field(fit_mode)
        # ties by id, so a page boundary never repeats or skips a piece
        sort_spec = {sort_field: sort_order, '_id': 1}
    elif sortkey == 'distance':
        sort_field = DISTANCE_FIELD
        sort_spec = distance_sort(sort_order)
    else:
        sort_field = resolve_sort_field(sortkey)
        sort_spec = {sort_field: sort_order}
    sort_stage = {'$sort': sort_spec}
    # a sort on an identity field runs on the small identity documents, right
    # after the first match (an index serves ``_id``); every later stage keeps
    # the order
    identity_sort = not sort_field.startswith(
        ('current_snapshot.', 'fit.', 'volume'))

    pipeline: List[Dict[str, Any]] = first_stages(identity_match, near)
    if identity_sort:
        pipeline.append(sort_stage)
    pipeline.extend([
        _current_snapshot_lookup(snapshots_collection,
                                 fields=SNAPSHOT_VIEWS[snapshot_view]),
        {'$unwind': '$current_snapshot'},
    ])

    if snapshot_match:
        pipeline.append({'$match': snapshot_match})
    if fit_stages:
        pipeline.extend(fit_stages)

    if (
        include_username
        and reserved_filter == 'true'
        and current_user_id
    ):
        pipeline.append({'$match': {'reserved': current_user_id}})

    if include_username:
        pipeline.extend(_username_enrichment_stages())

    if not identity_sort:
        pipeline.extend(sort_prep)
        pipeline.append(sort_stage)
        if sort_drop:
            pipeline.append({'$unset': sort_drop})

    if page > 0 and size > 0:
        pipeline.extend([
            {'$skip': (page - 1) * size},
            {'$limit': size},
        ])
    elif page == 0 and size > 0:
        pipeline.append({'$limit': size})

    if snapshot_view == 'full':
        # only the rows of the page carry the whole state
        pipeline.extend([
            _current_snapshot_lookup(snapshots_collection),
            {'$unwind': '$current_snapshot'},
        ])

    return pipeline


def build_count_pipeline(
    *,
    snapshots_collection: str,
    identity_match: Dict[str, Any],
    snapshot_match: Dict[str, Any],
    reserved_filter: Optional[str],
    current_user_id: Optional[str],
    include_username: bool,
    fit_stages: Optional[List[Dict[str, Any]]] = None,
    near: Optional[Near] = None,
) -> List[Dict[str, Any]]:
    pipeline: List[Dict[str, Any]] = [
        *first_stages(identity_match, near),
        _current_snapshot_lookup(snapshots_collection,
                                 fields=SORT_SNAPSHOT_FIELDS),
        {'$unwind': '$current_snapshot'},
    ]
    if snapshot_match:
        pipeline.append({'$match': snapshot_match})
    if fit_stages:
        pipeline.extend(fit_stages)
    if (
        include_username
        and reserved_filter == 'true'
        and current_user_id
    ):
        pipeline.append({'$match': {'reserved': current_user_id}})
    pipeline.append({'$count': 'count'})
    return pipeline


_BBX_ARRAY = {'$cond': [{'$isArray': '$bbx'}, '$bbx', []]}

_STATS_FACET_TEMPLATE: Dict[str, Any] = {
    'total': [{'$count': 'count'}],
    'byOriginalFunction': [
        {'$group': {'_id': '$original_function', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'byShapeClass': [
        {'$group': {'_id': '$shape_class', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'byMaterial': [
        {'$group': {'_id': '$material', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'byDataset': [
        {'$group': {'_id': '$dataset', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'byComplexity': [
        {'$group': {'_id': '$complexity', 'count': {'$sum': 1}}},
        {'$sort': {'_id': 1}},
    ],
    'byStatus': [
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'byFragment': [
        {'$group': {'_id': '$fragment', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    # where the pieces are: in place, not in place, out of circulation
    'byCirculation': [
        {
            '$group': {
                '_id': {
                    '$cond': [
                        {'$ne': [{'$ifNull': ['$exit', None]}, None]},
                        'exited',
                        {'$cond': [{'$eq': ['$planned', True]},
                                   'in_place', 'deinstalled']},
                    ]
                },
                'count': {'$sum': 1},
            }
        },
        {'$sort': {'count': -1}},
    ],
    # the pieces the current states stand for (a batch counts its quantity)
    'pieces': [
        {'$group': {'_id': None,
                    'count': {'$sum': {'$ifNull': ['$quantity', 1]}}}},
    ],
    'reserved': [
        {
            '$group': {
                '_id': {'$cond': [{'$ne': ['$reserved', '']}, True, False]},
                'count': {'$sum': 1},
            }
        },
        {'$sort': {'count': -1}},
    ],
    'descriptorsKeys': [
        {
            '$project': {
                'pairs': {'$objectToArray': {'$ifNull': ['$descriptors', {}]}}
            }
        },
        {'$unwind': '$pairs'},
        {'$group': {'_id': '$pairs.k', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ],
    'createdMonthly': [
        {
            '$group': {
                '_id': {
                    '$dateToString': {
                        'format': '%Y-%m',
                        'date': {'$toDate': '$created'},
                    }
                },
                'count': {'$sum': 1},
            }
        },
        {'$sort': {'_id': 1}},
    ],
    # the sorted sides (largest, middle, smallest) of the pieces that have a
    # size: how many, and the smallest and largest value of each (8.173)
    'sides': [
        {'$match': {'_sides': {'$type': 'array'}}},
        {'$group': {
            '_id': None,
            'count': {'$sum': 1},
            'largest_min': {'$min': {'$arrayElemAt': ['$_sides', 0]}},
            'largest_max': {'$max': {'$arrayElemAt': ['$_sides', 0]}},
            'middle_min': {'$min': {'$arrayElemAt': ['$_sides', 1]}},
            'middle_max': {'$max': {'$arrayElemAt': ['$_sides', 1]}},
            'smallest_min': {'$min': {'$arrayElemAt': ['$_sides', 2]}},
            'smallest_max': {'$max': {'$arrayElemAt': ['$_sides', 2]}},
        }},
    ],
    # how many have a point on each location layer (8.170), and how many of
    # the counted pieces are not public
    'visibility': [
        {'$group': {
            '_id': None,
            'current': {'$sum': {'$cond': ['$_has_current', 1, 0]}},
            'origin': {'$sum': {'$cond': ['$_has_origin', 1, 0]}},
            'not_public': {'$sum': {'$cond': [
                {'$eq': ['$is_public', True]}, 0, 1]}},
        }},
    ],
    'bbx': [
        {
            '$project': {
                # a bbx that is no array reads as an empty one: $arrayElemAt
                # fails on it, and one bad document must not 500 the stats
                'x': {'$arrayElemAt': [_BBX_ARRAY, 0]},
                'y': {'$arrayElemAt': [_BBX_ARRAY, 1]},
                'z': {'$arrayElemAt': [_BBX_ARRAY, 2]},
            }
        },
        {
            '$bucket': {
                'groupBy': '$x',
                'boundaries': [
                    0, 0.5, 1, 2, 5, 10, 20, 50, 100, 1000,
                ],
                'default': '>=1000',
                'output': {'count': {'$sum': 1}},
            }
        },
    ],
}


def build_identity_stats_pipeline(
    *,
    snapshots_collection: str,
    identity_match: Dict[str, Any],
    snapshot_match: Dict[str, Any],
    limit_dim: int,
    fit_stages: Optional[List[Dict[str, Any]]] = None,
    near: Optional[Near] = None,
) -> List[Dict[str, Any]]:
    """
    Join identities to current snapshots, reshape to flat fields, facet.
    """
    _ = limit_dim  # retained for parity with legacy handler (Top-N applied in Python)
    pipeline: List[Dict[str, Any]] = [
        *first_stages(identity_match, near),
        {
            '$lookup': {
                'from': snapshots_collection,
                'localField': 'current_snapshot_id',
                'foreignField': '_id',
                'as': 'current_snapshot',
            }
        },
        {'$unwind': '$current_snapshot'},
    ]
    if snapshot_match:
        pipeline.append({'$match': snapshot_match})
    if fit_stages:
        pipeline.extend(fit_stages)
    # the three sides of a piece with a size, largest first (else null)
    # (a bbx that is no array reads as an empty one: $arrayElemAt fails on it)
    box = {'$cond': [{'$isArray': '$current_snapshot.bbx'},
                     '$current_snapshot.bbx', []]}
    has_size = {'$and': [
        {'$eq': [{'$size': box}, 3]},
        *({'$isNumber': {'$arrayElemAt': [box, i]}} for i in range(3)),
    ]}
    pipeline.append({'$addFields': {'_stat_sides': {'$cond': [
        has_size, sorted_sides(box), None]}}})
    pipeline.append(
        {
            '$replaceRoot': {
                'newRoot': {
                    '$mergeObjects': [
                        '$current_snapshot',
                        {
                            '_id': '$_id',
                            'is_public': '$is_public',
                            '_sides': '$_stat_sides',
                            '_has_current': {
                                '$eq': [{'$type': '$geo_current'}, 'object']},
                            '_has_origin': {
                                '$eq': [{'$type': '$geo_origin'}, 'object']},
                            'original_function': '$original_function',
                            'material': '$material',
                            'dataset': '$dataset',
                            'reserved': {'$ifNull': ['$reserved', '']},
                            'catalog_number': '$catalog_number',
                            'exit': '$exit',
                            'planned': '$origin.planned',
                        },
                    ]
                }
            }
        },
    )
    pipeline.append({'$facet': dict(_STATS_FACET_TEMPLATE)})
    return pipeline


async def aggregate_identities(
    request: Request,
    pipeline: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    col = request.app.mongodb_component_identities
    cursor = await col.aggregate(pipeline)
    return [doc async for doc in cursor]


async def shallow_row_for_identity(
    request: Request,
    identity_id: str,
) -> dict:
    """One catalog row (``CatalogRow``) for a single identity."""
    pipeline = build_list_pipeline(
        snapshots_collection=request.app.mongodb_component_snapshots.name,
        identity_match={'_id': identity_id},
        snapshot_match={},
        sortkey='_id',
        sort_order=1,
        page=1,
        size=1,
        include_username=True,
        current_user_id=None,
        reserved_filter=None,
    )
    docs = await aggregate_identities(request, pipeline)
    if not docs:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )
    return catalog_row(docs[0])


async def count_identities(
    request: Request,
    pipeline: List[Dict[str, Any]],
) -> int:
    col = request.app.mongodb_component_identities
    cursor = await col.aggregate(pipeline)
    results = [doc async for doc in cursor]
    if not results:
        return 0
    return int(results[0].get('count', 0))
