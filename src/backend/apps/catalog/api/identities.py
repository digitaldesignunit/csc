#!/usr/bin/env python3.13
"""
Routes for the v0.5 `component_identities` collection.

Owns the primary read path of the new data model:

* `GET /identities` / `GET /identities/count`
    -> catalog list + count

* `GET /identities/stats`
    -> aggregated stats (identity + current snapshot)

* `GET /identities/map`
    -> 2D descriptor embedding (cached UMAP/PCA; optional live compute)

* `GET /identities/{identity_id}/compose`
    -> passport (identity + snapshots[]): default current, `?snapshots=all`,
    or `?snapshots=<uuid>` (comma-separated for many)
    The `compose` path segment predates the `passport` term and stays for
    compatibility with released Grasshopper userobjects.

* `GET /identities/{identity_id}/snapshots`
    -> summary list of all snapshot versions for one identity

* `GET /identities/{identity_id}/children`
    -> shallow rows for identities that list this identity as a parent

* `GET /identities/{identity_id}/provenance`
    -> identity + snapshot lineage graph (ancestors, descendants, versions)

* `GET /schema/catalog-compose`
    -> JSON Schema for the passport body (frontend codegen)

* `GET /schema/catalog-shared`
    -> JSON Schema for shared catalog value types (frontend codegen)

* `GET /schema/create-identity`
    -> JSON Schema for POST /identities (Grasshopper)

* `GET /schema/create-snapshot`
    -> JSON Schema for POST /identities/{id}/snapshots (Grasshopper)

Single-snapshot reads: `GET /snapshots/{snapshot_id}` in `snapshots.py`.

Write routes:
* `POST create identity`
* `POST new snapshot version`
* `PATCH identity`

PATCH current snapshot here;
snapshot preview/photo file routes in `snapshots.py`.
"""

import asyncio
import hashlib
import json
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

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
from apps.catalog.models import (
    ComponentCount,
    CreateComponentRequest,
    CreateSnapshotRequest,
    User,
)
from apps.catalog.read_models import (
    CatalogRow,
    CatalogSharedTypesEnvelope,
    ComponentPassport,
    PendingSnapshotItem,
    SnapshotSummaryItem,
    catalog_row,
    identity_body,
    passport_body,
)
from apps.catalog.documents import Evidence
from apps.catalog.permissions import dataset_roles
from apps.catalog.api.access import (
    and_match,
    dataset_of,
    deny_read,
    viewer_of,
    visible_identity_ids,
    visible_identity_match,
    visible_snapshot_docs,
)
from apps.catalog.provenance import (
    DEFAULT_PROVENANCE_DEPTH,
    MAX_PROVENANCE_DEPTH,
    build_provenance_graph,
)
from .auth import get_current_active_user, get_optional_current_user
from .public_access import (
    ensure_identity_read_access,
    identity_allows_anonymous_read,
    public_cache_control,
)
from .catalog_common import (
    not_modified_response,
    get_identities_col,
    get_snapshots_col,
    validate_uuid,
)
from .identity_filters import (
    CatalogFilters,
    ExpandMode,
    catalog_filters,
    children_identity_match,
)
from .identity_query import (
    aggregate_identities,
    build_count_pipeline,
    build_identity_stats_pipeline,
    build_list_pipeline,
    count_identities,
    shallow_row_for_identity,
)
from .snapshots import refresh_snapshot_photo_count


router = APIRouter()


@router.get(
    '/schema/catalog-compose',
    summary='JSON Schema for the passport body (GET .../{id}/compose)',
)
async def get_catalog_passport_json_schema():
    """
    Used by the frontend `generate:models` script (see `CatalogModels.ts`).
    """
    schema = ComponentPassport.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/catalog-shared',
    summary='JSON Schema for shared catalog value types (frontend codegen)',
)
async def get_catalog_shared_json_schema():
    """
    Used by the frontend `generate:models` script
    (see `CatalogSharedTypes.ts`).
    """
    schema = CatalogSharedTypesEnvelope.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/catalog-row',
    summary='JSON Schema for a GET /identities row (CatalogRow)',
)
async def get_catalog_row_json_schema():
    """Used by frontend `generate:models` (see `CatalogModels.ts`)."""
    schema = CatalogRow.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/snapshot-summary',
    summary=(
        'JSON Schema for GET /identities/{id}/snapshots '
        'row (SnapshotSummaryItem)'
    ),
)
async def get_snapshot_summary_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = SnapshotSummaryItem.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/pending-snapshot',
    summary='JSON Schema for GET /snapshots/pending row',
)
async def get_pending_snapshot_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = PendingSnapshotItem.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


def _schema_etag(schema: dict) -> str:
    schema_string = json.dumps(schema, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(schema_string.encode('utf-8')).hexdigest()


def _check_schema_conditional_request(request: Request, etag: str) -> bool:
    if_none_match = request.headers.get('if-none-match')
    return bool(if_none_match and if_none_match == etag)


def _list_etag(content: Any) -> str:
    payload = json.dumps(content, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(payload.encode('utf-8')).hexdigest()


@router.get(
    '/schema/create-snapshot',
    summary=(
        'JSON Schema for POST '
        '/identities/{id}/snapshots (CreateSnapshotRequest)'
    ),
)
async def get_create_snapshot_json_schema(request: Request):
    """
    Grasshopper CreateComponentSnapshot and snapshot-evolution flows.
    """
    schema = CreateSnapshotRequest.model_json_schema(by_alias=True)
    etag = _schema_etag(schema)
    if _check_schema_conditional_request(request, etag):
        return not_modified_response(etag)
    return JSONResponse(
        status_code=200,
        content=schema,
        headers={
            'ETag': etag,
            'Cache-Control': 'public, max-age=86400',
        },
    )


@router.get(
    '/schema/create-identity',
    summary='JSON Schema for POST /identities (CreateComponentRequest)',
)
async def get_create_identity_json_schema(request: Request):
    """Grasshopper CreateComponentIdentity and catalog create flows."""
    schema = CreateComponentRequest.model_json_schema(by_alias=True)
    etag = _schema_etag(schema)
    if _check_schema_conditional_request(request, etag):
        return not_modified_response(etag)
    return JSONResponse(
        status_code=200,
        content=schema,
        headers={
            'ETag': etag,
            'Cache-Control': 'public, max-age=86400',
        },
    )


def _compute_passport_etag(
    identity_doc: dict,
    snapshot_docs: List[dict],
) -> str:
    """Composite ETag from identity.lastmodified + sorted snapshot etags."""
    parts = [identity_doc.get('lastmodified', '')]
    for doc in sorted(
        snapshot_docs,
        key=lambda row: str(row.get('_id', '')),
    ):
        parts.append(str(doc.get('etag', '')))
    return hashlib.sha256('::'.join(parts).encode('utf-8')).hexdigest()


def _parse_snapshots_query(
    snapshots: Optional[str],
) -> tuple[str, List[str]]:
    """
    Parse ``snapshots`` query param.

    Returns ``('current'|'all'|'ids', uuid_list)``.
    """
    if not snapshots or not str(snapshots).strip():
        return 'current', []
    token = str(snapshots).strip()
    if token.lower() == 'current':
        return 'current', []
    if token.lower() == 'all':
        return 'all', []
    parsed: List[str] = []
    for part in token.split(','):
        item = part.strip()
        if item:
            parsed.append(item)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail='snapshots must be "current", "all", or one or more UUIDs',
        )
    return 'ids', parsed


async def _resolve_passport_snapshot_docs(
    request: Request,
    *,
    identity_id: str,
    identity_doc: dict,
    snapshots_col,
    mode: str,
    snapshot_ids: List[str],
) -> List[dict]:
    """Load full snapshot documents for a passport response."""
    if mode == 'all':
        try:
            cursor = snapshots_col.find(
                {'identity_id': identity_id},
            ).sort('version', 1)
            docs = await cursor.to_list(length=None)
        except PyMongoError as exc:
            print(f'[ERROR] passport snapshots=all DB: {exc}')
            raise HTTPException(
                status_code=500,
                detail='Internal server error',
            )
        if not docs:
            raise HTTPException(
                status_code=404,
                detail=f'No snapshots found for identity {identity_id}',
            )
    elif mode == 'ids':
        docs = []
        for snapshot_id in snapshot_ids:
            validate_uuid(snapshot_id, label='snapshot id')
            doc = await snapshots_col.find_one({'_id': snapshot_id})
            if doc is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'Snapshot {snapshot_id} not found',
                )
            if doc.get('identity_id') != identity_id:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f'Snapshot {snapshot_id} does not belong to identity '
                        f'{identity_id}'
                    ),
                )
            docs.append(doc)
        docs.sort(
            key=lambda row: (
                row.get('version', 0),
                str(row.get('_id', '')),
            ),
        )
    else:
        current_snapshot_id = identity_doc.get('current_snapshot_id')
        if not current_snapshot_id:
            return []                 # no published snapshot left (8.17)
        doc = await snapshots_col.find_one({'_id': current_snapshot_id})
        if doc is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    f'current_snapshot_id={current_snapshot_id} of identity '
                    f'{identity_id} not found in component_snapshots.'
                ),
            )
        docs = [doc]

    for doc in docs:
        await refresh_snapshot_photo_count(
            request,
            str(doc['_id']),
            doc,
        )
    return docs


def _passport_response(
    identity_doc: dict,
    snapshot_docs: List[dict],
    *,
    etag: Optional[str] = None,
    status_code: int = status.HTTP_200_OK,
    anonymous_public: bool = False,
) -> JSONResponse:
    try:
        response_body = passport_body(identity_doc, snapshot_docs)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Stored document failed Pydantic validation: {exc}',
        )
    resolved_etag = etag or _compute_passport_etag(
        identity_doc,
        snapshot_docs,
    )
    return JSONResponse(
        status_code=status_code,
        content=response_body,
        headers={
            'ETag': resolved_etag,
            'Cache-Control': (
                public_cache_control()
                if anonymous_public
                else 'private, max-age=3600'
            ),
        },
    )


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
                if k not in ('current_snapshot', 'reserved_by_username')
            }
            if expand == 'current_snapshot':
                row = passport_body(identity_doc,
                                    [doc.get('current_snapshot') or {}])
            else:
                row = identity_body(identity_doc)
            if 'reserved_by_username' in doc:
                row['reserved_by_username'] = doc['reserved_by_username']
            rows.append(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'List row failed Pydantic validation: {exc}',
        )
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
    }


async def _visible_map_payload(request: Request, user: Optional[User],
                               payload: Dict[str, Any]) -> Dict[str, Any]:
    """A cached map holds every component; keep the caller's (3.6)."""
    viewer = viewer_of(user)
    if viewer.is_admin:
        return payload
    ids = [p['id'] for p in payload.get('points') or []]
    keep = await visible_identity_ids(request, viewer, ids)
    if len(keep) == len(ids):
        return payload
    points = [p for p in payload['points'] if p['id'] in keep]
    return {**payload, 'points': points, 'displayed': len(points),
            'total': len(points)}


@router.get(
    '/identities/count',
    summary='Count identities (current snapshot filters)',
    response_model=ComponentCount,
)
async def count_identities_route(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
):
    try:
        pipeline = build_count_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            reserved_filter=filters.reserved,
            current_user_id=current_user.id,
            include_username=True,
        )
        total = await count_identities(request, pipeline)
    except PyMongoError as exc:
        print(f'[ERROR] count_identities_route DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    return {'count': total}


@router.get(
    '/identities/map',
    summary=(
        '2D component map from descriptors '
        '(cached UMAP/PCA by default; live compute optional)'
    ),
)
async def get_identities_map(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    basis: MapBasis = Query(
        'radial_signature',
        description=(
            'Feature space: radial_signature (concatenated ray distances) '
            'or scalars (box/sphere/line/planescore)'
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
    cache_col = getattr(request.app, 'mongodb_component_map_cache', None)
    if cache_col is None:
        cache_col = request.app.mongodb['component_map_cache']

    if source in ('auto', 'cache') and filters.is_default_scope():
        doc_id = cache_doc_id(basis, method)
        try:
            cached = await cache_col.find_one({'_id': doc_id})
        except PyMongoError as exc:
            print(f'[ERROR] identities map cache read: {exc}')
            cached = None
        if cached is not None:
            return JSONResponse(
                status_code=200,
                content=await _visible_map_payload(
                    request, current_user, payload_from_cache_doc(cached)),
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
                return JSONResponse(status_code=200, content=payload)

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
        )
        pipeline.append(map_rows_project_stage())
        docs = await aggregate_identities(request, pipeline)
    except PyMongoError as exc:
        print(f'[ERROR] identities map DB error: {exc}')
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        print(f'[ERROR] identities map embed: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to compute component map embedding',
        ) from exc

    annotated = annotate_live_payload(payload)
    annotated['requested_method'] = method
    return JSONResponse(status_code=200, content=annotated)


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
async def get_identities_stats(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    limit_dim: int = Query(10, description='Top-N limit for long tail dims'),
):
    """Facet counts over the filtered catalog (identity + current snapshot)."""
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
            'descriptorsKeys': topn(raw.get('descriptorsKeys')),
            'createdMonthly': _normalize_stats_facet_lists(
                raw.get('createdMonthly')
            ),
            'bbxX': _normalize_stats_facet_lists(raw.get('bbx'))
        }
        return JSONResponse(status_code=200, content=content)
    except PyMongoError as exc:
        print(f'[ERROR] identities stats aggregation DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
    except Exception as exc:
        print(f'[ERROR] identities stats aggregation: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/identities',
    summary='List identities (join current snapshot)',
)
async def list_identities_route(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    filters: Annotated[CatalogFilters, Depends(catalog_filters)],
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: str = Query('_id', description='Sort key'),
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
    try:
        pipeline = build_list_pipeline(
            **(await _pipelines_args(request, filters, current_user)),
            sortkey=sortkey,
            sort_order=-1 if sortorder == 'desc' else 1,
            page=page,
            size=size,
            include_username=True,
            current_user_id=current_user.id,
            reserved_filter=filters.reserved,
        )
        docs = await aggregate_identities(request, pipeline)
    except PyMongoError as exc:
        print(f'[ERROR] list_identities_route DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    content = _format_list_rows(docs, expand)
    etag = _list_etag(content)
    if _check_schema_conditional_request(request, etag):
        return not_modified_response(etag)
    return JSONResponse(
        status_code=200,
        content=content,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600',
        },
    )


async def _next_snapshot_version(
    snapshots,
    identity_id: str,
) -> int:
    """Return max(existing version) + 1 for one identity."""
    doc = await snapshots.find_one(
        {'identity_id': identity_id},
        sort=[('version', -1)],
        projection={'version': 1},
    )
    if doc is None:
        return 0
    return int(doc['version']) + 1


async def _resolve_snapshot_name(
    snapshots,
    identity_doc: dict,
    requested_name: Optional[str],
) -> str:
    trimmed = (requested_name or '').strip()
    if trimmed and trimmed.lower() != 'unnamed component':
        return trimmed

    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if current_snapshot_id:
        current = await snapshots.find_one(
            {'_id': current_snapshot_id},
            {'name': 1},
        )
        if current and current.get('name'):
            return str(current['name'])

    catalog_number = identity_doc.get('catalog_number')
    if catalog_number is not None:
        return f'Component #{catalog_number}'
    return 'Unnamed Component'


@router.get(
    '/identities/{identity_id}/children',
    summary='List identities that list this identity as a parent',
)
async def list_identity_children(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    """
    Reverse lookup of ``parent_identities``.

    Returns catalog rows (same shape as ``GET /identities?expand=shallow``),
    including exited and unpublished children. Anonymous callers who can read a public parent only see
    public children.
    """
    validate_uuid(identity_id, label='identity id')
    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection={'_id': 1, 'is_public': 1},
    )

    identity_match = and_match(
        children_identity_match(identity_id),
        await visible_identity_match(request, viewer_of(current_user)),
    )
    try:
        pipeline = build_list_pipeline(
            snapshots_collection=request.app.mongodb_component_snapshots.name,
            identity_match=identity_match,
            snapshot_match={},
            sortkey='_id',
            sort_order=1,
            page=0,
            size=0,
            include_username=True,
            current_user_id=current_user.id if current_user else None,
            reserved_filter=None,
        )
        docs = await aggregate_identities(request, pipeline)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_children DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    docs.sort(
        key=lambda doc: (
            doc.get('catalog_number') is None,
            doc.get('catalog_number')
            if isinstance(doc.get('catalog_number'), (int, float))
            else 0,
            str(doc.get('_id') or ''),
        )
    )

    try:
        content = [catalog_row(doc) for doc in docs]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Child row failed Pydantic validation: {exc}',
        )
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )
    return JSONResponse(
        status_code=200,
        content=content,
        headers={
            'Cache-Control': (
                public_cache_control()
                if anonymous_public
                else 'private, max-age=3600'
            ),
        },
    )


_IDENTITY_LINEAGE_PROJECTION = {
    '_id': 1,
    'parent_identities': 1,
    'catalog_number': 1,
    'original_function': 1,
    'exit': 1,
    'is_public': 1,
    'current_snapshot_id': 1,
    'dataset': 1,
    'created_by_user_id': 1,
    'withdrawn': 1,
}

_SNAPSHOT_LINEAGE_PROJECTION = {
    '_id': 1,
    'identity_id': 1,
    'version': 1,
    'status': 1,
    'superseded_by': 1,
    'added_by_user_id': 1,
    'name': 1,
}


async def _collect_lineage_identity_docs(
    identities_col,
    *,
    root_doc: Dict[str, Any],
    max_depth: int,
    visibility: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    collected: Dict[str, Dict[str, Any]] = {str(root_doc['_id']): root_doc}

    frontier = {
        str(pid)
        for pid in (root_doc.get('parent_identities') or [])
        if pid and str(pid) not in collected
    }
    for _ in range(max_depth):
        pending = [pid for pid in frontier if pid not in collected]
        if not pending:
            break
        query = and_match({'_id': {'$in': pending}}, visibility)
        docs = await identities_col.find(
            query,
            _IDENTITY_LINEAGE_PROJECTION,
        ).to_list(length=None)
        frontier = set()
        for doc in docs:
            ident_id = str(doc['_id'])
            collected[ident_id] = doc
            for pid in doc.get('parent_identities') or []:
                if pid and str(pid) not in collected:
                    frontier.add(str(pid))

    frontier = {str(root_doc['_id'])}
    for _ in range(max_depth):
        query = and_match({'parent_identities': {'$in': list(frontier)}},
                          visibility)
        docs = await identities_col.find(
            query,
            _IDENTITY_LINEAGE_PROJECTION,
        ).to_list(length=None)
        next_frontier: set = set()
        for doc in docs:
            ident_id = str(doc['_id'])
            if ident_id in collected:
                continue
            collected[ident_id] = doc
            next_frontier.add(ident_id)
        if not next_frontier:
            break
        frontier = next_frontier

    return collected


@router.get(
    '/identities/{identity_id}/provenance',
    summary='Lineage graph of related identities and snapshots',
)
async def get_identity_provenance(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    depth: int = Query(
        DEFAULT_PROVENANCE_DEPTH,
        ge=1,
        le=MAX_PROVENANCE_DEPTH,
        description='Max ancestor/descendant hops',
    ),
):
    """
    Walk ``parent_identities`` up and down from this identity, then attach
    each identity's snapshot versions. Anonymous callers who can read a
    public root only see public relatives.
    """
    validate_uuid(identity_id, label='identity id')
    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection=_IDENTITY_LINEAGE_PROJECTION,
    )
    visibility = await visible_identity_match(request,
                                              viewer_of(current_user))
    identities_col = await get_identities_col(request)
    snapshots_col = await get_snapshots_col(request)

    try:
        lineage = await _collect_lineage_identity_docs(
            identities_col,
            root_doc=identity_doc,
            max_depth=depth,
            visibility=visibility,
        )
        identity_ids = list(lineage.keys())
        snapshot_docs: List[Dict[str, Any]] = []
        if identity_ids:
            cursor = snapshots_col.find(
                {'identity_id': {'$in': identity_ids}},
                _SNAPSHOT_LINEAGE_PROJECTION,
            )
            snapshot_docs = await cursor.to_list(length=None)
    except PyMongoError as exc:
        print(f'[ERROR] get_identity_provenance DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    snapshots_by_identity: Dict[str, List[Dict[str, Any]]] = {}
    for snap in snapshot_docs:
        ident_id = str(snap.get('identity_id') or '')
        if not ident_id:
            continue
        snapshots_by_identity.setdefault(ident_id, []).append(snap)
    # drafts / pending / rejected only for their author and moderator(D)
    for ident_id, snaps in snapshots_by_identity.items():
        snapshots_by_identity[ident_id] = await visible_snapshot_docs(
            request, current_user, lineage[ident_id], snaps, tombstones=True)

    graph = build_provenance_graph(
        root_identity_id=identity_id,
        identities=lineage,
        snapshots_by_identity=snapshots_by_identity,
    )
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )
    return JSONResponse(
        status_code=200,
        content=graph,
        headers={
            'Cache-Control': (
                public_cache_control()
                if anonymous_public
                else 'private, max-age=3600'
            ),
        },
    )


_ACTOR_PRIVATE = ('email',)
_ACTOR_NAMED = ('name', 'orcid')


def _project_actor(actor: Dict[str, Any], anonymous: bool) -> Dict[str, Any]:
    """Spec 3.3.1: anonymous readers see the organization only; e-mail
    addresses are left out of every list response."""
    hidden = _ACTOR_PRIVATE + (_ACTOR_NAMED if anonymous else ())
    return {k: (None if k in hidden else v) for k, v in actor.items()}


@router.get(
    '/identities/{identity_id}/evidence',
    summary='Published evidence of an identity (read-only until plan P6)',
)
async def list_identity_evidence(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    method: Optional[str] = Query(None, description='e.g. reinforcement_layout'),
):
    """
    Published, non-superseded evidence records of one identity (e.g. the
    reinforcement layout the viewer draws). Creation, moderation, the fold
    and attachments arrive with plan P6.
    """
    validate_uuid(identity_id, label='identity id')
    await ensure_identity_read_access(
        request, identity_id, current_user, projection={'_id': 1,
                                                        'is_public': 1})
    query: Dict[str, Any] = {'identity_id': identity_id,
                             'status': 'published', 'superseded_by': None}
    if method:
        query['method'] = method
    try:
        docs = await request.app.mongodb_component_evidence.find(query) \
            .sort('observed_at', 1).to_list(length=None)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_evidence DB error: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')
    anonymous = current_user is None
    items = []
    for doc in docs:
        try:
            body = Evidence.model_validate(doc).model_dump(
                by_alias=True, mode='json')
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f'Evidence failed Pydantic validation: {exc}',
            )
        body['performed_by'] = [_project_actor(a, anonymous)
                                for a in body.get('performed_by') or []]
        items.append(body)
    return JSONResponse(status_code=200, content=items)


@router.get(
    '/identities/{identity_id}/snapshots',
    summary='List snapshot versions for an identity (summary rows)',
    response_model=List[SnapshotSummaryItem],
    response_model_by_alias=True,
)
async def list_identity_snapshots(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
):
    """Return all snapshots for one identity, ordered by version ascending."""
    validate_uuid(identity_id, label='identity id')

    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
        projection={'_id': 1, 'current_snapshot_id': 1, 'is_public': 1},
    )

    snapshots = await get_snapshots_col(request)
    current_snapshot_id = identity_doc.get('current_snapshot_id')
    projection = {
        '_id': 1,
        'identity_id': 1,
        'version': 1,
        'status': 1,
        'name': 1,
        'effective_from': 1,
        'effective_from_precision': 1,
        'supersedes': 1,
        'superseded_by': 1,
        'added_by_user_id': 1,
        'added_by_username': 1,
        'status_changed_at': 1,
        'created': 1,
        'lastmodified': 1,
    }

    try:
        cursor = snapshots.find(
            {'identity_id': identity_id},
            projection,
        ).sort('version', 1)
        docs = await visible_snapshot_docs(
            request, current_user, identity_doc,
            await cursor.to_list(length=None), tombstones=True)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_snapshots DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    items: List[Dict[str, Any]] = []
    for doc in docs:
        row = {
            **doc,
            'is_current': doc.get('_id') == current_snapshot_id,
        }
        try:
            items.append(
                SnapshotSummaryItem.model_validate(row).model_dump(
                    by_alias=True
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f'Snapshot summary failed validation: {exc}',
            )

    return JSONResponse(status_code=200, content=items)


async def _identity_as_of(request: Request, user: Optional[User],
                          identity_id: str, at: str) -> JSONResponse:
    """Old values may name people: members of D and admin only (8.36)."""
    from .change_log import as_of_body
    doc = await (await get_identities_col(request)).find_one(
        {'_id': identity_id})
    viewer = viewer_of(user)
    dataset = await dataset_of(request, doc.get('dataset'))
    if not dataset_roles(viewer, dataset):
        raise HTTPException(status_code=403,
                            detail='Earlier versions are for members of the '
                                   'dataset.')
    return JSONResponse(status_code=200,
                        content=await as_of_body(request, 'identity', doc, at))


@router.get(
    '/identities/{identity_id}',
    summary='Get one identity (shallow, passport, or identity-only)',
)
async def get_identity(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    expand: ExpandMode = Query(
        'shallow',
        description=(
            'shallow=catalog row; '
            'current_snapshot={identity,snapshots[]}; none=identity only'
        ),
    ),
    as_of: Optional[str] = Query(
        None, description='the identity as it was at this ISO date '
                          '(members of D and admin; section 3.8)'),
):
    validate_uuid(identity_id, label='identity id')

    await ensure_identity_read_access(request, identity_id, current_user)
    if as_of is not None:
        return await _identity_as_of(request, current_user, identity_id,
                                     as_of)

    if expand == 'shallow':
        row = await shallow_row_for_identity(request, identity_id)
        return JSONResponse(status_code=200, content=row)

    identities = await get_identities_col(request)
    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )

    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )

    if expand == 'none':
        try:
            body = identity_body(identity_doc)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f'Identity failed Pydantic validation: {exc}',
            )
        return JSONResponse(
            status_code=200,
            content=body,
            headers={
                'Cache-Control': (
                    public_cache_control()
                    if anonymous_public
                    else 'private, max-age=3600'
                ),
            },
        )

    snapshots = await get_snapshots_col(request)
    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if not current_snapshot_id:              # no published snapshot (8.17)
        return _passport_response(identity_doc, [],
                                  anonymous_public=anonymous_public)
    snapshot_doc = await snapshots.find_one({'_id': current_snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=500,
            detail=f'current_snapshot_id={current_snapshot_id} not found',
        )
    await refresh_snapshot_photo_count(
        request, str(snapshot_doc['_id']), snapshot_doc
    )
    return _passport_response(
        identity_doc,
        [snapshot_doc],
        anonymous_public=anonymous_public,
    )


@router.get(
    '/identities/{identity_id}/compose',
    summary='Component passport (identity + snapshot(s))',
    response_model=ComponentPassport,
    response_model_by_alias=True,
)
async def get_identity_passport(
    request: Request,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    identity_id: str,
    snapshots: Optional[str] = Query(
        default=None,
        description=(
            'Which snapshots to include: omitted or "current" = live '
            'current_snapshot_id; "all" = every version; or one or more '
            'snapshot UUIDs (comma-separated).'
        ),
    ),
):
    """
    Return ``{identity, snapshots[]}``.

    - Default / ``?snapshots=current``: live ``current_snapshot_id``.
    - ``?snapshots=all``: every version (ascending by version).
    - ``?snapshots=<uuid>`` or comma-separated UUIDs: specific versions.
    """
    validate_uuid(identity_id, label='identity id')

    identities = await get_identities_col(request)
    snapshots_col = await get_snapshots_col(request)

    identity_doc = await ensure_identity_read_access(
        request,
        identity_id,
        current_user,
    )
    anonymous_public = (
        current_user is None and identity_allows_anonymous_read(identity_doc)
    )

    mode, snapshot_ids = _parse_snapshots_query(snapshots)

    snapshot_docs = await _resolve_passport_snapshot_docs(
        request,
        identity_id=identity_id,
        identity_doc=identity_doc,
        snapshots_col=snapshots_col,
        mode=mode,
        snapshot_ids=snapshot_ids,
    )
    visible = await visible_snapshot_docs(
        request, current_user, identity_doc, snapshot_docs)
    if mode == 'ids' and len(visible) < len(snapshot_docs):
        raise deny_read(viewer_of(current_user))
    snapshot_docs = visible
    etag = _compute_passport_etag(identity_doc, snapshot_docs)

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag)

    return _passport_response(
        identity_doc,
        snapshot_docs,
        etag=etag,
        anonymous_public=anonymous_public,
    )
