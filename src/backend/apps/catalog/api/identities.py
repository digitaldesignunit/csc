#!/usr/bin/env python3.9
"""
Routes for the v0.5 `component_identities` collection.

Owns the primary read path of the new data model:

* `GET /identities` / `GET /identities/count`
    -> catalog list + count

* `GET /identities/stats`
    -> aggregated stats (identity + current snapshot)

* `GET /identities/{identity_id}/compose`
    -> identity + snapshots[]: default current, `?snapshots=all`, or
    `?snapshots=<uuid>` (comma-separated for many)

* `GET /identities/{identity_id}/snapshots`
    -> summary list of all snapshot versions for one identity

* `GET /schema/catalog-compose`
    -> JSON Schema for the compose body (frontend codegen)

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

import hashlib
import json
import uuid
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import (
    CatalogSharedTypesEnvelope,
    ComponentCount,
    ComponentIdentity,
    ComponentSnapshot,
    ComposeIdentityResponse,
    CreateComponentRequest,
    CreateSnapshotRequest,
    SnapshotSummaryItem,
    PendingValidationSnapshotItem,
    UpdateComponentIdentityModel,
    UpdateComponentSnapshotModel,
    User,
)
from .auth import get_current_active_user, require_admin
from .catalog_common import (
    allocate_catalog_number,
    compute_snapshot_etag,
    not_modified_response,
    resolve_new_component_name,
    get_identities_col,
    get_snapshots_col,
    now_iso,
    validate_parent_identities,
    validate_uuid,
)
from .identity_filters import (
    ConsumedFilter,
    ExpandMode,
    build_identity_match_stage,
    build_snapshot_match_stage,
    merge_shallow_catalog_row,
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
    summary='JSON Schema for GET /identities/{id}/compose (v0.5 compose body)',
)
async def get_catalog_compose_json_schema():
    """
    Used by the frontend `generate:models` script (see `CatalogModels.ts`).
    """
    schema = ComposeIdentityResponse.model_json_schema(by_alias=True)
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
    '/schema/pending-validation-snapshot',
    summary='JSON Schema for GET /snapshots/pending-validation row',
)
async def get_pending_validation_snapshot_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = PendingValidationSnapshotItem.model_json_schema(by_alias=True)
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


def _compute_compose_etag(
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


async def _resolve_compose_snapshot_docs(
    request: Request,
    *,
    identity_id: str,
    identity_doc: dict,
    snapshots_col,
    mode: str,
    snapshot_ids: List[str],
) -> List[dict]:
    """Load full snapshot documents for compose."""
    if mode == 'all':
        try:
            cursor = snapshots_col.find(
                {'identity_id': identity_id},
            ).sort('version', 1)
            docs = await cursor.to_list(length=None)
        except PyMongoError as exc:
            print(f'[ERROR] compose snapshots=all DB: {exc}')
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
            raise HTTPException(
                status_code=500,
                detail=(
                    f'Identity {identity_id} has no current_snapshot_id; '
                    'data integrity error.'
                ),
            )
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


def _compose_json_response(
    identity_doc: dict,
    snapshot_docs: List[dict],
    *,
    etag: Optional[str] = None,
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    try:
        identity_model = ComponentIdentity.model_validate(identity_doc)
        snapshot_models = [
            ComponentSnapshot.model_validate(doc) for doc in snapshot_docs
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Stored document failed Pydantic validation: {exc}',
        )

    response_body = {
        'identity': identity_model.model_dump(by_alias=True),
        'snapshots': [
            model.model_dump(by_alias=True) for model in snapshot_models
        ],
    }
    resolved_etag = etag or _compute_compose_etag(
        identity_doc,
        snapshot_docs,
    )
    return JSONResponse(
        status_code=status_code,
        content=response_body,
        headers={
            'ETag': resolved_etag,
            'Cache-Control': 'private, max-age=3600',
        },
    )


def _catalog_filter_context(
    request: Request,
    *,
    sortorder: Literal['asc', 'desc'],
    comptype: str,
    material: str,
    dataset: str,
    validated: int,
    complexity: Optional[int],
    fragment: Optional[bool],
    reserved: Optional[str],
    bbx_min_x: Optional[float],
    bbx_min_y: Optional[float],
    bbx_min_z: Optional[float],
    bbx_max_x: Optional[float],
    bbx_max_y: Optional[float],
    bbx_max_z: Optional[float],
    consumed_filter: ConsumedFilter,
) -> Dict[str, Any]:
    return {
        'snapshots_collection': (
            request.app.mongodb_component_snapshots.name
        ),
        'sort_order': -1 if sortorder == 'desc' else 1,
        'identity_match': build_identity_match_stage(
            comptype=comptype,
            material=material,
            dataset=dataset,
            reserved=reserved,
            consumed_filter=consumed_filter,
        ),
        'snapshot_match': build_snapshot_match_stage(
            validated=validated,
            complexity=complexity,
            fragment=fragment,
            bbx_min_x=bbx_min_x,
            bbx_min_y=bbx_min_y,
            bbx_min_z=bbx_min_z,
            bbx_max_x=bbx_max_x,
            bbx_max_y=bbx_max_y,
            bbx_max_z=bbx_max_z,
        ),
    }


def _format_list_rows(
    docs: List[Dict[str, Any]],
    expand: ExpandMode,
) -> List[Dict[str, Any]]:
    if expand == 'shallow':
        return [merge_shallow_catalog_row(doc) for doc in docs]

    rows: List[Dict[str, Any]] = []
    for doc in docs:
        snap = doc.get('current_snapshot') or {}
        if expand == 'current_snapshot':
            identity_doc = {
                k: v for k, v in doc.items()
                if k not in ('current_snapshot', 'reserved_by_username')
            }
            try:
                identity_model = ComponentIdentity.model_validate(identity_doc)
                snapshot_model = ComponentSnapshot.model_validate(snap)
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f'List row failed Pydantic validation: {exc}',
                )
            row = {
                'identity': identity_model.model_dump(by_alias=True),
                'snapshot': snapshot_model.model_dump(by_alias=True),
            }
            if 'reserved_by_username' in doc:
                row['reserved_by_username'] = doc['reserved_by_username']
            rows.append(row)
            continue

        identity_doc = {
            k: v for k, v in doc.items()
            if k not in ('current_snapshot', 'reserved_by_username')
        }
        try:
            identity_model = ComponentIdentity.model_validate(identity_doc)
            row = identity_model.model_dump(by_alias=True)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f'Identity row failed Pydantic validation: {exc}',
            )
        if 'reserved_by_username' in doc:
            row['reserved_by_username'] = doc['reserved_by_username']
        rows.append(row)
    return rows


@router.get(
    '/identities/count',
    summary='Count identities (current snapshot filters)',
    response_model=ComponentCount,
)
async def count_identities_route(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    comptype: str = Query(''),
    material: str = Query(''),
    dataset: str = Query(''),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None),
    fragment: Optional[bool] = Query(None),
    reserved: Optional[str] = Query(None),
    bbx_min_x: Optional[float] = Query(None),
    bbx_min_y: Optional[float] = Query(None),
    bbx_min_z: Optional[float] = Query(None),
    bbx_max_x: Optional[float] = Query(None),
    bbx_max_y: Optional[float] = Query(None),
    bbx_max_z: Optional[float] = Query(None),
    consumed_filter: ConsumedFilter = Query('active'),
    sortorder: Literal['asc', 'desc'] = Query('asc', include_in_schema=False),
):
    ctx = _catalog_filter_context(
        request,
        sortorder=sortorder,
        comptype=comptype,
        material=material,
        dataset=dataset,
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        reserved=reserved,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
        consumed_filter=consumed_filter,
    )
    try:
        pipeline = build_count_pipeline(
            snapshots_collection=ctx['snapshots_collection'],
            identity_match=ctx['identity_match'],
            snapshot_match=ctx['snapshot_match'],
            reserved_filter=reserved,
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


def _normalize_stats_facet_lists(items):
    """
    Map Mongo facet bucket rows to `{label, count}`
    (same as ``/components/stats``).
    """
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
    comptype: Optional[str] = Query(None, description='Component type filter'),
    material: Optional[str] = Query(None, description='Material type filter'),
    dataset: Optional[str] = Query(None, description='Dataset name filter'),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None, description='Complexity (0–3)'),
    fragment: Optional[bool] = Query(None, description='Is fragment'),
    bbx_min_x: Optional[float] = Query(None, description='Min X'),
    bbx_min_y: Optional[float] = Query(None, description='Min Y'),
    bbx_min_z: Optional[float] = Query(None, description='Min Z'),
    bbx_max_x: Optional[float] = Query(None, description='Max X'),
    bbx_max_y: Optional[float] = Query(None, description='Max Y'),
    bbx_max_z: Optional[float] = Query(None, description='Max Z'),
    limit_dim: int = Query(10, description='Top-N limit for long tail dims'),
    consumed_filter: ConsumedFilter = Query('active'),
    sortorder: Literal['asc', 'desc'] = Query('asc', include_in_schema=False),
):
    """
    Same JSON shape as ``GET /components/stats``
    backed by ``component_identities``.
    """
    ctx = _catalog_filter_context(
        request,
        sortorder=sortorder,
        comptype=comptype or '',
        material=material or '',
        dataset=dataset or '',
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        reserved=None,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
        consumed_filter=consumed_filter,
    )
    try:
        pipeline = build_identity_stats_pipeline(
            snapshots_collection=ctx['snapshots_collection'],
            identity_match=ctx['identity_match'],
            snapshot_match=ctx['snapshot_match'],
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
            'byType': _normalize_stats_facet_lists(raw.get('byType')),
            'byMaterial': topn(raw.get('byMaterial')),
            'byDataset': topn(raw.get('byDataset')),
            'byComplexity': _normalize_stats_facet_lists(
                raw.get('byComplexity')
            ),
            'byValidated': _normalize_stats_facet_lists(
                raw.get('byValidated')
            ),
            'byFragment': _normalize_stats_facet_lists(raw.get('byFragment')),
            'byAssembly': _normalize_stats_facet_lists(raw.get('byAssembly')),
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
    page: int = Query(0, description='Page number (0=get all, 1+=paginated)'),
    size: int = Query(0, description='Page size (0=get all)'),
    sortkey: str = Query('_id', description='Sort key'),
    sortorder: Literal['asc', 'desc'] = Query('asc'),
    comptype: str = Query(''),
    material: str = Query(''),
    dataset: str = Query(''),
    validated: int = Query(1, description='1=true, -1=false, 0/other=any'),
    complexity: Optional[int] = Query(None),
    fragment: Optional[bool] = Query(None),
    reserved: Optional[str] = Query(None),
    bbx_min_x: Optional[float] = Query(None),
    bbx_min_y: Optional[float] = Query(None),
    bbx_min_z: Optional[float] = Query(None),
    bbx_max_x: Optional[float] = Query(None),
    bbx_max_y: Optional[float] = Query(None),
    bbx_max_z: Optional[float] = Query(None),
    consumed_filter: ConsumedFilter = Query('active'),
    expand: ExpandMode = Query(
        'shallow',
        description=(
            'shallow=legacy catalog row; '
            'current_snapshot=nested pair; '
            'none=identity fields only'
        ),
    ),
):
    ctx = _catalog_filter_context(
        request,
        sortorder=sortorder,
        comptype=comptype,
        material=material,
        dataset=dataset,
        validated=validated,
        complexity=complexity,
        fragment=fragment,
        reserved=reserved,
        bbx_min_x=bbx_min_x,
        bbx_min_y=bbx_min_y,
        bbx_min_z=bbx_min_z,
        bbx_max_x=bbx_max_x,
        bbx_max_y=bbx_max_y,
        bbx_max_z=bbx_max_z,
        consumed_filter=consumed_filter,
    )
    try:
        pipeline = build_list_pipeline(
            snapshots_collection=ctx['snapshots_collection'],
            identity_match=ctx['identity_match'],
            snapshot_match=ctx['snapshot_match'],
            sortkey=sortkey,
            sort_order=ctx['sort_order'],
            page=page,
            size=size,
            include_username=True,
            current_user_id=current_user.id,
            reserved_filter=reserved,
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


@router.post(
    '/identities',
    summary='Create identity and version-0 snapshot',
    response_model=ComposeIdentityResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    payload: CreateComponentRequest = Body(...),
):
    """Allocate catalog_number, insert identity + v0 snapshot, wire current."""
    identity_id = payload.id or str(uuid.uuid4())
    validate_uuid(identity_id, label='identity id')

    identities = await get_identities_col(request)
    snapshots = await get_snapshots_col(request)

    if await identities.find_one({'_id': identity_id}, {'_id': 1}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Identity {identity_id} already exists',
        )

    await validate_parent_identities(
        request,
        payload.parent_identities,
        self_id=identity_id,
    )

    geometry = payload.geometry.model_dump()
    if payload.marker_points and not geometry.get('marker_points'):
        geometry['marker_points'] = payload.marker_points

    catalog_number = await allocate_catalog_number(request)
    resolved_name = resolve_new_component_name(payload.name, catalog_number)

    now = now_iso()
    snapshot_id = str(uuid.uuid4())
    snapshot_doc: Dict[str, Any] = {
        '_id': snapshot_id,
        'identity_id': identity_id,
        'version': 0,
        'virtual': False,
        'name': resolved_name,
        'geometry': geometry,
        'descriptors': payload.descriptors or {},
        'bbx': list(payload.bbx),
        'bbx_origin': payload.bbx_origin,
        'complexity': payload.complexity,
        'fragment': payload.fragment,
        'assembly': payload.assembly,
        'condition': payload.condition,
        'color': payload.color,
        'location': (
            payload.location.model_dump()
            if payload.location is not None
            else {'lat': 0.0, 'lon': 0.0}
        ),
        'processes': payload.processes or {},
        'iframe': payload.iframe.model_dump(),
        'pca_frame': payload.pca_frame.model_dump(),
        'validated': payload.validated,
        'added_by_user_id': current_user.id,
        'added_by_username': current_user.username,
        'notes': payload.notes,
        'quantity': payload.quantity,
        'created': now,
        'lastmodified': now,
    }
    snapshot_doc['etag'] = compute_snapshot_etag(snapshot_doc)

    try:
        snapshot_model = ComponentSnapshot.model_validate(snapshot_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid snapshot payload: {exc}',
        )

    identity_doc: Dict[str, Any] = {
        '_id': identity_id,
        'catalog_number': catalog_number,
        'type': payload.componenttype,
        'material': payload.material,
        'dataset': payload.dataset,
        'manufactured_at': payload.manufactured_at,
        'manufactured_precision': payload.manufactured_precision,
        'salvage_source': payload.salvage_source,
        'salvaged_at': payload.salvaged_at,
        'reserved': payload.reserved or '',
        'attributes': payload.attributes or {},
        'parent_identities': payload.parent_identities,
        'consumed_at': None,
        'current_snapshot_id': snapshot_id,
        'created': now,
        'lastmodified': now,
    }

    try:
        identity_model = ComponentIdentity.model_validate(identity_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid identity payload: {exc}',
        )

    snapshot_insert = snapshot_model.model_dump(by_alias=True)
    identity_insert = identity_model.model_dump(by_alias=True)

    try:
        await snapshots.insert_one(snapshot_insert)
    except PyMongoError as exc:
        print(f'[ERROR] create_identity snapshot insert: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    try:
        await identities.insert_one(identity_insert)
    except PyMongoError as exc:
        await snapshots.delete_one({'_id': snapshot_id})
        print(f'[ERROR] create_identity identity insert: {exc}')
        if 'duplicate key' in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Identity {identity_id} already exists',
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    return _compose_json_response(
        identity_insert,
        [snapshot_insert],
        status_code=status.HTTP_201_CREATED,
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


@router.post(
    '/identities/{identity_id}/snapshots',
    summary='Create new snapshot version for an existing identity',
    response_model=ComposeIdentityResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    payload: CreateSnapshotRequest = Body(...),
):
    """
    Insert snapshot at version max+1.

    Unvalidated snapshots remain pending and do not advance
    ``current_snapshot_id``. Validated snapshots (``validated=true``)
    are promoted immediately. Rejects when another pending snapshot exists.
    """
    validate_uuid(identity_id, label='identity id')

    identities = await get_identities_col(request)
    snapshots = await get_snapshots_col(request)

    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Identity {identity_id} not found',
        )

    pending = await snapshots.find_one(
        {'identity_id': identity_id, 'validated': False},
        {'_id': 1, 'version': 1},
    )
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                'Identity already has a pending snapshot awaiting validation '
                f'(version {pending.get("version")})'
            ),
        )

    snapshot_id = payload.id or str(uuid.uuid4())
    validate_uuid(snapshot_id, label='snapshot id')

    if await snapshots.find_one({'_id': snapshot_id}, {'_id': 1}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Snapshot {snapshot_id} already exists',
        )

    geometry = payload.geometry.model_dump()
    if payload.marker_points and not geometry.get('marker_points'):
        geometry['marker_points'] = payload.marker_points

    resolved_name = await _resolve_snapshot_name(
        snapshots,
        identity_doc,
        payload.name,
    )
    next_version = await _next_snapshot_version(snapshots, identity_id)
    now = now_iso()

    snapshot_doc: Dict[str, Any] = {
        '_id': snapshot_id,
        'identity_id': identity_id,
        'version': next_version,
        'virtual': payload.virtual,
        'name': resolved_name,
        'geometry': geometry,
        'descriptors': payload.descriptors or {},
        'bbx': list(payload.bbx),
        'bbx_origin': payload.bbx_origin,
        'complexity': payload.complexity,
        'fragment': payload.fragment,
        'assembly': payload.assembly,
        'condition': payload.condition,
        'color': payload.color,
        'location': (
            payload.location.model_dump()
            if payload.location is not None
            else {'lat': 0.0, 'lon': 0.0}
        ),
        'processes': payload.processes or {},
        'iframe': payload.iframe.model_dump(),
        'pca_frame': payload.pca_frame.model_dump(),
        'validated': payload.validated,
        'added_by_user_id': current_user.id,
        'added_by_username': current_user.username,
        'notes': payload.notes,
        'quantity': payload.quantity,
        'created': now,
        'lastmodified': now,
    }
    snapshot_doc['etag'] = compute_snapshot_etag(snapshot_doc)

    try:
        snapshot_model = ComponentSnapshot.model_validate(snapshot_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid snapshot payload: {exc}',
        )

    snapshot_insert = snapshot_model.model_dump(by_alias=True)

    try:
        await snapshots.insert_one(snapshot_insert)
    except PyMongoError as exc:
        print(f'[ERROR] create_snapshot insert: {exc}')
        if 'duplicate key' in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f'Snapshot version conflict for identity {identity_id}'
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    promote = bool(payload.validated)
    if promote:
        identity_update: Dict[str, Any] = {
            'current_snapshot_id': snapshot_id,
            'lastmodified': now,
        }
        try:
            result = await identities.update_one(
                {'_id': identity_id},
                {'$set': identity_update},
            )
        except PyMongoError as exc:
            await snapshots.delete_one({'_id': snapshot_id})
            print(f'[ERROR] create_snapshot identity update: {exc}')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Internal server error',
            )

        if result.matched_count == 0:
            await snapshots.delete_one({'_id': snapshot_id})
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Identity {identity_id} not found',
            )

        identity_doc = {**identity_doc, **identity_update}
    identity_insert = ComponentIdentity.model_validate(
        identity_doc
    ).model_dump(by_alias=True)

    return _compose_json_response(
        identity_insert,
        [snapshot_insert],
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    '/identities/{identity_id}/snapshots',
    summary='List snapshot versions for an identity (summary rows)',
    response_model=List[SnapshotSummaryItem],
    response_model_by_alias=True,
)
async def list_identity_snapshots(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    """Return all snapshots for one identity, ordered by version ascending."""
    validate_uuid(identity_id, label='identity id')

    identities = await get_identities_col(request)
    snapshots = await get_snapshots_col(request)

    identity_doc = await identities.find_one(
        {'_id': identity_id},
        {'_id': 1, 'current_snapshot_id': 1},
    )
    if identity_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Identity {identity_id} not found',
        )

    current_snapshot_id = identity_doc.get('current_snapshot_id')

    try:
        cursor = snapshots.find(
            {'identity_id': identity_id},
            {
                '_id': 1,
                'identity_id': 1,
                'version': 1,
                'validated': 1,
                'virtual': 1,
                'name': 1,
                'created': 1,
                'lastmodified': 1,
            },
        ).sort('version', 1)
        docs = await cursor.to_list(length=None)
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


@router.patch(
    '/identities/{identity_id}',
    summary='PATCH identity metadata (admin only)',
    response_model=ComponentIdentity,
    response_model_by_alias=True,
)
async def patch_identity(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
    payload: UpdateComponentIdentityModel = Body(...),
):
    """Partial update of identity-side fields only."""
    validate_uuid(identity_id, label='identity id')

    identities = await get_identities_col(request)
    existing = await identities.find_one({'_id': identity_id})
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )

    update_data: Dict[str, Any] = payload.model_dump(
        by_alias=True,
        exclude_unset=True,
    )
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail='No updatable fields provided',
        )

    if 'parent_identities' in update_data:
        await validate_parent_identities(
            request,
            update_data.get('parent_identities'),
            self_id=identity_id,
        )

    update_data['lastmodified'] = now_iso()

    try:
        await identities.update_one(
            {'_id': identity_id},
            {'$set': update_data},
        )
    except PyMongoError as exc:
        print(f'[ERROR] patch_identity DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    updated_doc = await identities.find_one({'_id': identity_id})
    if updated_doc is None:
        raise HTTPException(
            status_code=500,
            detail='Identity missing after update',
        )

    try:
        identity_model = ComponentIdentity.model_validate(updated_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Updated identity failed Pydantic validation: {exc}',
        )

    body = identity_model.model_dump(by_alias=True)
    return JSONResponse(status_code=200, content=body)


@router.get(
    '/identities/{identity_id}',
    summary='Get one identity (shallow, compose, or identity-only)',
)
async def get_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    expand: ExpandMode = Query(
        'shallow',
        description=(
            'shallow=legacy catalog row; '
            'current_snapshot={identity,snapshot}; none=identity only'
        ),
    ),
):
    validate_uuid(identity_id, label='identity id')

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

    if expand == 'none':
        try:
            model = ComponentIdentity.model_validate(identity_doc)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f'Identity failed Pydantic validation: {exc}',
            )
        return JSONResponse(
            status_code=200,
            content=model.model_dump(by_alias=True),
        )

    snapshots = await get_snapshots_col(request)
    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if not current_snapshot_id:
        raise HTTPException(
            status_code=500,
            detail=f'Identity {identity_id} has no current_snapshot_id',
        )
    snapshot_doc = await snapshots.find_one({'_id': current_snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=500,
            detail=f'current_snapshot_id={current_snapshot_id} not found',
        )
    await refresh_snapshot_photo_count(
        request, str(snapshot_doc['_id']), snapshot_doc
    )
    return _compose_json_response(identity_doc, [snapshot_doc])


@router.get(
    '/identities/{identity_id}/compose',
    summary='Compose identity + snapshot(s)',
    response_model=ComposeIdentityResponse,
    response_model_by_alias=True,
)
async def compose_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
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

    mode, snapshot_ids = _parse_snapshots_query(snapshots)

    identities = await get_identities_col(request)
    snapshots_col = await get_snapshots_col(request)

    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )

    snapshot_docs = await _resolve_compose_snapshot_docs(
        request,
        identity_id=identity_id,
        identity_doc=identity_doc,
        snapshots_col=snapshots_col,
        mode=mode,
        snapshot_ids=snapshot_ids,
    )
    etag = _compute_compose_etag(identity_doc, snapshot_docs)

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag)

    return _compose_json_response(
        identity_doc,
        snapshot_docs,
        etag=etag,
    )


@router.patch(
    '/identities/{identity_id}/current-snapshot',
    summary='PATCH current snapshot metadata (admin only)',
    response_model=ComponentSnapshot,
    response_model_by_alias=True,
)
async def patch_current_snapshot(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
    payload: UpdateComponentSnapshotModel = Body(...),
):
    """Partial update of metadata on the identity's current snapshot.

    Only fields present in the request body are applied. Geometry and
    geometry-derived fields cannot be changed here
    (new snapshot version instead).
    User photos use `/snapshots/.../photos/...` (JPEG, compressed on upload).
    """
    identities = await get_identities_col(request)
    snapshots = await get_snapshots_col(request)

    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )

    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if not current_snapshot_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f'Identity {identity_id} has no current_snapshot_id; '
                'data integrity error.'
            ),
        )

    snapshot_doc = await snapshots.find_one({'_id': current_snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f'current_snapshot_id={current_snapshot_id} of identity '
                f'{identity_id} not found in component_snapshots.'
            ),
        )

    update_data: Dict[str, Any] = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail='No updatable fields provided'
        )

    update_data['lastmodified'] = now_iso()

    merged = {**snapshot_doc, **update_data}
    update_data['etag'] = compute_snapshot_etag(merged)

    try:
        await snapshots.update_one(
            {'_id': current_snapshot_id},
            {'$set': update_data},
        )
    except PyMongoError as exc:
        print(f'[ERROR] patch_current_snapshot DB error: {exc}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )

    updated_doc = await snapshots.find_one({'_id': current_snapshot_id})
    if updated_doc is None:
        raise HTTPException(
            status_code=500,
            detail='Snapshot missing after update',
        )

    try:
        snapshot_model = ComponentSnapshot.model_validate(updated_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Updated snapshot failed Pydantic validation: {exc}',
        )

    body = snapshot_model.model_dump(by_alias=True)
    etag = updated_doc.get('etag', '')

    return JSONResponse(
        status_code=200,
        content=body,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600',
        },
    )
