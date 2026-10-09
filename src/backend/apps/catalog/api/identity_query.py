"""
Aggregation pipelines for listing identities with current snapshot.
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from apps.catalog.read_models import catalog_row

from .identity_filters import resolve_sort_field


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
) -> List[Dict[str, Any]]:
    pipeline: List[Dict[str, Any]] = [
        {'$match': identity_match},
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

    if (
        include_username
        and reserved_filter == 'true'
        and current_user_id
    ):
        pipeline.append({'$match': {'reserved': current_user_id}})

    if include_username:
        pipeline.extend(_username_enrichment_stages())

    sort_field = resolve_sort_field(sortkey)
    pipeline.append({'$sort': {sort_field: sort_order}})

    if page > 0 and size > 0:
        pipeline.extend([
            {'$skip': (page - 1) * size},
            {'$limit': size},
        ])
    elif page == 0 and size > 0:
        pipeline.append({'$limit': size})

    return pipeline


def build_count_pipeline(
    *,
    snapshots_collection: str,
    identity_match: Dict[str, Any],
    snapshot_match: Dict[str, Any],
    reserved_filter: Optional[str],
    current_user_id: Optional[str],
    include_username: bool,
) -> List[Dict[str, Any]]:
    pipeline: List[Dict[str, Any]] = [
        {'$match': identity_match},
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
    if (
        include_username
        and reserved_filter == 'true'
        and current_user_id
    ):
        pipeline.append({'$match': {'reserved': current_user_id}})
    pipeline.append({'$count': 'count'})
    return pipeline


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
    'bbx': [
        {
            '$project': {
                'x': {'$arrayElemAt': ['$bbx', 0]},
                'y': {'$arrayElemAt': ['$bbx', 1]},
                'z': {'$arrayElemAt': ['$bbx', 2]},
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
) -> List[Dict[str, Any]]:
    """
    Join identities to current snapshots, reshape to flat fields, facet.
    """
    _ = limit_dim  # retained for parity with legacy handler (Top-N applied in Python)
    pipeline: List[Dict[str, Any]] = [
        {'$match': identity_match},
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
    pipeline.append(
        {
            '$replaceRoot': {
                'newRoot': {
                    '$mergeObjects': [
                        '$current_snapshot',
                        {
                            '_id': '$_id',
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
