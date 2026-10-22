#!/usr/bin/env python3.13
"""
The catalogue reads: list, count, stats and the 2D component map.

* `GET /identities` / `GET /identities/count`
    -> catalog list + count

* `GET /identities/stats`
    -> aggregated stats (identity + current snapshot)

* `GET /identities/map`
    -> 2D descriptor embedding (cached UMAP/PCA; optional live compute)

* `GET /identities/locations`
    -> the points of the location map (current or origin layer)
"""

import asyncio
import hashlib
import json
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure, PyMongoError

from apps.catalog.component_map import (
    MapBasis,
    MapMethod,
    MapSource,
    annotate_live_payload,
    build_component_map,
    cache_doc_id,
    map_rows_project_stage,
    payload_from_cache_doc,
)
from apps.catalog.models import ComponentCount, User
from apps.catalog.read_models import (
    LocationMap,
    catalog_row,
    identity_body,
    passport_body,
)
from apps.catalog.people import for_viewer
from limiter import local_limiter, signed_in_or_ip
from apps.catalog.api.access import (
    and_match,
    viewer_of,
    visible_identity_ids,
    visible_identity_match,
)
from .auth import get_optional_current_user
from .public_access import viewer_etag, viewer_headers
from .catalog_common import internal_error, not_modified_response
from .identity_filters import (
    CatalogFilters,
    ExpandMode,
    catalog_filters,
    public_filters,
)
from .near_search import LAYER_FIELDS, NearLayer
from .identity_query import (
    aggregate_identities,
    annotate_has_preview,
    build_count_pipeline,
    build_identity_stats_pipeline,
    build_list_pipeline,
    count_identities,
)
from logging_setup import get_logger
from .schema_routes import _check_schema_conditional_request


log = get_logger(__name__)

router = APIRouter()


# a read of the catalogue lists: per user, or per address when anonymous
LIST_RATE = '120/minute'


def _list_etag(content: Any) -> str:
    payload = json.dumps(content, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(payload.encode('utf-8')).hexdigest()


def _format_list_rows(
    docs: List[Dict[str, Any]],
    expand: ExpandMode,
) -> List[Dict[str, Any]]:
    """Aggregation rows -> CatalogRow (shallow), {identity, snapshots}
    (current_snapshot) or identity documents (none)."""
    rows: List[Dict[str, Any]] = []
    try:
        for doc in docs:
            if expand == 'shallow':
                rows.append(catalog_row(doc))
                continue
            identity_doc = {
                k: v for k, v in doc.items()
                if k not in ('current_snapshot', 'reserved_by_username',
                             'fit', 'distance_m', 'geo_current', 'geo_origin')
            }
            if expand == 'current_snapshot':
                row = passport_body(identity_doc,
                                    [doc.get('current_snapshot') or {}])
            else:
                row = identity_body(identity_doc)
            if 'reserved_by_username' in doc:
                row['reserved_by_username'] = doc['reserved_by_username']
            if doc.get('fit') is not None:
                row['fit'] = doc['fit']
            if doc.get('distance_m') is not None:
                row['distance_m'] = doc['distance_m']
            rows.append(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(exc, 'list row validation')
    return rows


async def _pipelines_args(request: Request, filters: CatalogFilters,
                          user: Optional[User]) -> Dict[str, Any]:
    """The filters plus the visibility rule (3.6) for this caller."""
    return {
        'snapshots_collection': request.app.mongodb_component_snapshots.name,
        'identity_match': and_match(
            filters.identity_match(),
            await visible_identity_match(request, viewer_of(user))),
        'snapshot_match': filters.snapshot_match(),
        'fit_stages': filters.fit_pipeline_stages(),
        'near': filters.near,
    }


async def _visible_map_payload(request: Request, user: Optional[User],
                               payload: Dict[str, Any]) -> Dict[str, Any]:
    """A cached map holds every component; keep the caller's (3.6). The
    ``total`` is computed from the points this caller may see, never the
    cached one: that counts the hidden pieces too, so anyone could derive how
    many there are (8.125 d). An admin sees everything: the cache stands."""
    viewer = viewer_of(user)
    if viewer.is_admin:
        return payload
    ids = [p['id'] for p in payload.get('points') or []]
    keep = await visible_identity_ids(request, viewer, ids)
    points = [p for p in payload.get('points') or [] if p['id'] in keep]
    return {**payload, 'points': points, 'displayed': len(points),
            'total': len(points)}


@router.get(
    '/identities/count',
    summary='Count identities (current snapshot filters)',
    response_model=ComponentCount,
)
@local_limiter.limit(LIST_RATE, key_func=signed_in_or_ip)
async def count_identities_route(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
):
    if current_user is None:
        filters = public_filters(filters)
    try:
        pipeline = build_count_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            reserved_filter=filters.reserved,
            current_user_id=current_user.id if current_user else None,
            include_username=current_user is not None,
        )
        total = await count_identities(request, pipeline)
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('count_identities_route DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    return JSONResponse(
        status_code=200, content={'count': total},
        headers=viewer_headers(anonymous_public=current_user is None))


# what the location map needs of a piece: where it is, and what it colours by
_LOCATION_PROJECT = {
    '$project': {
        '_id': 0,
        'id': '$_id',
        'catalog_number': 1,
        'original_function': 1,
        'dataset': 1,
        'material': 1,
        'in_place': {'$eq': ['$origin.planned', True]},
        'name': '$current_snapshot.name',
        'shape_class': '$current_snapshot.shape_class',
        'lon': {'$arrayElemAt': ['$_point.coordinates', 0]},
        'lat': {'$arrayElemAt': ['$_point.coordinates', 1]},
    }
}


@router.get(
    '/identities/locations',
    summary='The points of the location map (current or origin layer)',
    response_model=LocationMap,
)
@local_limiter.limit(LIST_RATE, key_func=signed_in_or_ip)
async def get_identities_locations(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    layer: NearLayer = Query(
        'current', description='which place of a piece is a point: '
                               'current (the location of the current '
                               'version) or origin (the origin building)'),
):
    """Every piece this caller may see that matches the filters and has a
    point on the layer (decisions 8.170, 8.171), with what the map colours
    and labels it by; the pieces without a point are only counted
    (``left_out``). The filters, the visibility and a near or fit search are
    those of the list. A piece never appears for someone who may not see it,
    and neither does it count."""
    if current_user is None:
        filters = public_filters(filters)
    field = LAYER_FIELDS[layer]
    try:
        args = await _pipelines_args(request, filters, current_user)
        total = await count_identities(request, build_count_pipeline(
            **args, reserved_filter=filters.reserved,
            current_user_id=current_user.id if current_user else None,
            include_username=False))
        with_point = {**args, 'identity_match': and_match(
            args['identity_match'], {field: {'$type': 'object'}})}
        pipeline = build_list_pipeline(
            **with_point, fit_mode=filters.fit_mode, sortkey='catalog_number',
            sort_order=1, page=0, size=0, include_username=False,
            current_user_id=None, reserved_filter=filters.reserved,
            snapshot_view='row')
        pipeline.append({'$addFields': {'_point': f'${field}'}})
        pipeline.append(_LOCATION_PROJECT)
        points = await aggregate_identities(request, pipeline)
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('identities locations DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    content = LocationMap(
        layer=layer, total=total, displayed=len(points),
        left_out=max(0, total - len(points)), points=points,
    ).model_dump(mode='json')
    return JSONResponse(
        status_code=200, content=content,
        headers=viewer_headers(anonymous_public=current_user is None))


@router.get(
    '/identities/map',
    summary=(
        '2D component map from descriptors '
        '(cached UMAP/PCA by default; live compute optional)'
    ),
)
@local_limiter.limit(LIST_RATE, key_func=signed_in_or_ip)
async def get_identities_map(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    basis: MapBasis = Query(
        'radial_signature',
        description=(
            'Feature space: radial_signature (concatenated ray distances), '
            'scalars (box/sphere/line/planescore) or hks (the heat kernel '
            'signature)'
        ),
    ),
    method: MapMethod = Query(
        'umap',
        description='Embedding method: pca (fast) or umap (preferred)',
    ),
    source: MapSource = Query(
        'auto',
        description=(
            'auto/cache=read component_map_cache only (default scope); '
            'live=recompute now'
        ),
    ),
):
    """
    Embed current-snapshot descriptors into 2D for the Component Map page.

    Default catalog scope layouts are precomputed by ``main_component_map.py``
    into ``component_map_cache``. ``source=auto`` / ``cache`` serve those only
    (no surprise live recompute). Pass ``source=live`` to compute on demand.

    Components missing the chosen descriptor basis are omitted from
    ``points``; ``displayed`` / ``total`` report coverage.
    """
    if current_user is None:
        filters = public_filters(filters)
    cache_col = getattr(request.app, 'mongodb_component_map_cache', None)
    if cache_col is None:
        cache_col = request.app.mongodb['component_map_cache']

    if source in ('auto', 'cache') and filters.is_default_scope():
        doc_id = cache_doc_id(basis, method)
        try:
            cached = await cache_col.find_one({'_id': doc_id})
        except PyMongoError:
            log.exception('identities map cache read')
            cached = None
        if cached is not None:
            return JSONResponse(
                status_code=200,
                content=await _visible_map_payload(
                    request, current_user, payload_from_cache_doc(cached)),
                headers=viewer_headers(anonymous_public=current_user is None),
            )
        # Prefer a cached PCA sibling over a slow live embed.
        if method == 'umap':
            try:
                pca_cached = await cache_col.find_one(
                    {'_id': cache_doc_id(basis, 'pca')})
            except PyMongoError:
                pca_cached = None
            if pca_cached is not None:
                payload = await _visible_map_payload(
                    request, current_user, payload_from_cache_doc(pca_cached))
                payload['requested_method'] = method
                return JSONResponse(
                    status_code=200, content=payload,
                    headers=viewer_headers(
                        anonymous_public=current_user is None))

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f'No cached map for {doc_id}. '
                'Run main_component_map.py or use source=live.'
            ),
        )

    if source == 'cache':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                'source=cache only supports the default catalog scope '
                '(published, in circulation, no extra filters)'
            ),
        )

    if source != 'live':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                'Non-default filters require source=live '
                '(or use the default scope with cache)'
            ),
        )

    try:
        pipeline = build_list_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            sortkey='_id',
            sort_order=1,
            page=0,
            size=0,
            include_username=False,
            current_user_id=None,
            reserved_filter=filters.reserved,
            snapshot_view='map',
        )
        pipeline.append(map_rows_project_stage())
        docs = await aggregate_identities(request, pipeline)
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('identities map DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    try:
        payload = await asyncio.to_thread(
            build_component_map,
            docs,
            basis=basis,
            method=method,
        )
    except RuntimeError as exc:
        # the layout needs a package this server may not have; say so, and
        # keep the exception text (it can be anything) in the log
        log.exception('identities map embed unavailable')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='This layout method is not available on this server',
        ) from exc
    except Exception as exc:
        log.exception('identities map embed')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to compute component map embedding',
        ) from exc

    annotated = annotate_live_payload(payload)
    annotated['requested_method'] = method
    return JSONResponse(
        status_code=200, content=annotated,
        headers=viewer_headers(anonymous_public=current_user is None))


def _normalize_stats_facet_lists(items):
    """Map Mongo facet bucket rows to `{label, count}`."""
    out = []
    for it in items or []:
        label = it.get('_id')
        if isinstance(label, bool):
            label = 'true' if label else 'false'
        elif label is None:
            label = 'unknown'
        out.append({'label': str(label), 'count': int(it.get('count', 0))})
    return out


@router.get(
    '/identities/stats',
    summary=(
        'Aggregated catalog statistics '
        '(identities joined to current snapshots)'
    ),
)
@local_limiter.limit(LIST_RATE, key_func=signed_in_or_ip)
async def get_identities_stats(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    limit_dim: int = Query(10, description='Top-N limit for long tail dims'),
):
    """Facet counts over the filtered catalog (identity + current snapshot)."""
    if current_user is None:
        filters = public_filters(filters)
    try:
        pipeline = build_identity_stats_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            limit_dim=limit_dim,
        )
        docs = await aggregate_identities(request, pipeline)
        raw = docs[0] if docs else {}

        total_row = raw.get('total') or [{}]
        total = int(total_row[0].get('count', 0)) if total_row else 0

        def topn(items):
            rows = _normalize_stats_facet_lists(items)
            if limit_dim and len(rows) > limit_dim:
                head = rows[:limit_dim]
                others_count = sum(r['count'] for r in rows[limit_dim:])
                head.append({'label': 'others', 'count': others_count})
                return head
            return rows

        content = {
            'total': total,
            'byOriginalFunction': _normalize_stats_facet_lists(
                raw.get('byOriginalFunction')),
            'byShapeClass': _normalize_stats_facet_lists(
                raw.get('byShapeClass')),
            'byMaterial': topn(raw.get('byMaterial')),
            'byDataset': topn(raw.get('byDataset')),
            'byComplexity': _normalize_stats_facet_lists(
                raw.get('byComplexity')
            ),
            'byStatus': _normalize_stats_facet_lists(raw.get('byStatus')),
            'byFragment': _normalize_stats_facet_lists(raw.get('byFragment')),
            'reserved': _normalize_stats_facet_lists(raw.get('reserved')),
            'byCirculation': _normalize_stats_facet_lists(
                raw.get('byCirculation')),
            'pieces': int(((raw.get('pieces') or [{}])[0]).get('count', 0)),
            'descriptorsKeys': topn(raw.get('descriptorsKeys')),
            'createdMonthly': _normalize_stats_facet_lists(
                raw.get('createdMonthly')
            ),
            'bbxX': _normalize_stats_facet_lists(raw.get('bbx'))
        }
        return JSONResponse(
            status_code=200, content=content,
            headers=viewer_headers(anonymous_public=current_user is None))
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('identities stats aggregation DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    except Exception:
        log.exception('identities stats aggregation')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/identities',
    summary='List identities (join current snapshot)',
)
@local_limiter.limit(LIST_RATE, key_func=signed_in_or_ip)
async def list_identities_route(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: Optional[str] = Query(
        None, description='Sort key; volume = the product of the three bbx '
                          'sides (a piece without bbx last); match = the '
                          'closeness to the dimension search (needs '
                          'fit_mode); distance = the distance to the near '
                          'point (needs near_lat and near_lon). Default: '
                          'distance while a near search is set, else match '
                          'while fit_mode is set, else _id'),
    sortorder: Literal['asc', 'desc'] = Query('asc'),
    expand: ExpandMode = Query(
        'shallow',
        description=(
            'shallow=catalog row; '
            'current_snapshot=nested pair; '
            'none=identity fields only'
        ),
    ),
):
    if current_user is None:
        filters = public_filters(filters)
    if sortkey == 'match' and not filters.fit_mode:
        raise HTTPException(
            status_code=422,
            detail='sortkey match needs fit_mode (about or can_hold)')
    if sortkey == 'distance' and not filters.near:
        raise HTTPException(
            status_code=422,
            detail='sortkey distance needs near_lat and near_lon')
    # a near search sorts by distance, also with a dimension search: that
    # one filters (8.173)
    sortkey = sortkey or ('distance' if filters.near
                          else 'match' if filters.fit_mode else '_id')
    try:
        pipeline = build_list_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            fit_mode=filters.fit_mode,
            sortkey=sortkey,
            sort_order=-1 if sortorder == 'desc' else 1,
            page=page,
            size=size,
            include_username=current_user is not None,
            current_user_id=current_user.id if current_user else None,
            reserved_filter=filters.reserved,
            # a passport row carries the whole state (Grasshopper reads it);
            # a catalog row and an identity row only what they show
            snapshot_view='full' if expand == 'current_snapshot' else 'row',
        )
        docs = await aggregate_identities(request, pipeline)
        if expand == 'shallow':
            annotate_has_preview(request, docs)
    except ConnectionFailure:
        raise            # the 503 handler of main_fastapi.py
    except PyMongoError:
        log.exception('list_identities_route DB error')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    content = for_viewer(_format_list_rows(docs, expand), current_user)
    etag = viewer_etag(_list_etag(content), current_user)
    if _check_schema_conditional_request(request, etag):
        return not_modified_response(etag, Vary='Authorization')
    return JSONResponse(
        status_code=200,
        content=content,
        headers=viewer_headers(anonymous_public=current_user is None,
                               etag=etag),
    )
