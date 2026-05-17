"""
Aggregation pipelines for listing identities with current snapshot.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from .identity_filters import merge_shallow_catalog_row, resolve_sort_field


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
    """One legacy-style shallow catalog row for a single identity."""
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
    return merge_shallow_catalog_row(docs[0])


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
