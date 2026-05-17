#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_identities` collection.

Owns the primary read path of the new data model:

* `GET /identities` / `GET /identities/count` — catalog list + count
* `GET /identities/{identity_id}/compose` — identity + current snapshot

Single-snapshot reads: `GET /snapshots/{snapshot_id}` in `snapshots.py`.

Write routes: POST create, PATCH identity, PATCH current snapshot here;
snapshot preview/photo file routes in `snapshots.py`.

Legacy `/components/...` routes in `components.py` are untouched and remain
available throughout the M4 cutover.
"""

import hashlib
import uuid
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status
)
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import (
    ComponentCount,
    ComponentIdentity,
    ComponentSnapshot,
    ComposeIdentityResponse,
    CreateComponentRequest,
    UpdateComponentIdentityModel,
    UpdateComponentSnapshotModel,
    User,
)
from .auth import get_current_active_user, require_admin
from .catalog_common import (
    allocate_catalog_number,
    compute_snapshot_etag,
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
    build_list_pipeline,
    count_identities,
    shallow_row_for_identity,
)


router = APIRouter()


def _compute_compose_etag(identity_doc: dict, snapshot_doc: dict) -> str:
    """Composite ETag from identity.lastmodified + snapshot.etag.

    Identity-side metadata edits bump `identity.lastmodified`; snapshot
    rewrites bump `snapshot.etag` (and snapshot id). Hashing the pair gives
    correct invalidation for both axes without re-serialising the response.
    """
    payload = (
        f"{identity_doc.get('lastmodified', '')}::"
        f"{snapshot_doc.get('etag', '')}"
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


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
    return JSONResponse(status_code=200, content=content)


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

    now = now_iso()
    snapshot_id = str(uuid.uuid4())
    snapshot_doc: Dict[str, Any] = {
        '_id': snapshot_id,
        'identity_id': identity_id,
        'version': 0,
        'virtual': False,
        'name': payload.name or 'Unnamed Component',
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

    catalog_number = await allocate_catalog_number(request)
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

    response_body = {
        'identity': identity_insert,
        'snapshot': snapshot_insert,
    }
    etag = _compute_compose_etag(identity_insert, snapshot_insert)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_body,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600',
        },
    )


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
    try:
        identity_model = ComponentIdentity.model_validate(identity_doc)
        snapshot_model = ComponentSnapshot.model_validate(snapshot_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Compose row failed Pydantic validation: {exc}',
        )
    return JSONResponse(
        status_code=200,
        content={
            'identity': identity_model.model_dump(by_alias=True),
            'snapshot': snapshot_model.model_dump(by_alias=True),
        },
    )


@router.get(
    '/identities/{identity_id}/compose',
    summary='Compose identity + current snapshot',
    response_model=ComposeIdentityResponse,
    response_model_by_alias=True,
)
async def compose_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    """Return the identity document plus its current snapshot.

    This is the canonical read path for the new data model. The response
    shape is `{ "identity": ComponentIdentity, "snapshot": ComponentSnapshot }`
    with both objects serialised by alias (`_id` instead of `id`).

    Returns 404 if the identity is unknown. A 500 is raised if the identity
    references a `current_snapshot_id` that cannot be resolved (data
    integrity bug; `m3_verify` should catch this).
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

    etag = _compute_compose_etag(identity_doc, snapshot_doc)

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return JSONResponse(
            status_code=304,
            content=None,
            headers={'ETag': etag},
        )

    try:
        identity_model = ComponentIdentity.model_validate(identity_doc)
        snapshot_model = ComponentSnapshot.model_validate(snapshot_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Stored document failed Pydantic validation: {exc}',
        )

    response_body = {
        'identity': identity_model.model_dump(by_alias=True),
        'snapshot': snapshot_model.model_dump(by_alias=True),
    }

    return JSONResponse(
        status_code=200,
        content=response_body,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600',
        },
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
