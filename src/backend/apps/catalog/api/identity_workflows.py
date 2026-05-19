#!/usr/bin/env python3.9
"""
Identity lifecycle workflows for the v0.5 model (reserve, validate, consume).
"""

import os
import shutil
from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.catalog_meta_vocab import (
    ADDITIONAL_DATASETS,
    ADDITIONAL_MATERIALS,
    merge_additional_with_catalog,
)
from apps.catalog.models import User
from .auth import get_current_active_user, require_admin
from .catalog_common import (
    compute_snapshot_etag,
    get_identities_col,
    get_snapshots_col,
    now_iso,
    validate_uuid,
)
from .identity_filters import (
    ConsumedFilter,
    build_identity_match_stage,
    merge_shallow_catalog_row,
)
from .identity_query import (
    aggregate_identities,
    build_list_pipeline,
    shallow_row_for_identity,
)
router = APIRouter()


async def _load_identity(request: Request, identity_id: str) -> Dict[str, Any]:
    validate_uuid(identity_id, label='identity id')
    identities = await get_identities_col(request)
    doc = await identities.find_one({'_id': identity_id})
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Identity {identity_id} not found',
        )
    return doc


async def _load_current_snapshot(
    request: Request,
    identity_doc: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot_id = identity_doc.get('current_snapshot_id')
    if not snapshot_id:
        raise HTTPException(
            status_code=500,
            detail='Identity has no current_snapshot_id',
        )
    snapshots = await get_snapshots_col(request)
    snap = await snapshots.find_one({'_id': snapshot_id})
    if snap is None:
        raise HTTPException(
            status_code=500,
            detail=f'current_snapshot_id={snapshot_id} not found',
        )
    return snap


async def _resolve_user_id(
    request: Request,
    user_identifier: str,
) -> tuple[str, str]:
    users = request.app.mongodb_users
    user_doc = await users.find_one({
        '$or': [
            {'_id': user_identifier},
            {'username': user_identifier},
        ],
    })
    if user_doc is None:
        raise HTTPException(status_code=404, detail='User not found')
    return user_doc['_id'], user_doc.get('username', 'Unknown')


@router.get(
    '/identities/reserved/{user_identifier}',
    summary='List identities reserved by a user (shallow rows)',
)
async def list_reserved_identities(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_identifier: str,
):
    user_id, username = await _resolve_user_id(request, user_identifier)
    if current_user.id != user_id and current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail='You can only view your own reserved components',
        )

    identity_match = build_identity_match_stage(
        consumed_filter='active',
    )
    identity_match['reserved'] = user_id

    pipeline = build_list_pipeline(
        snapshots_collection=request.app.mongodb_component_snapshots.name,
        identity_match=identity_match,
        snapshot_match={},
        sortkey='_id',
        sort_order=1,
        page=0,
        size=0,
        include_username=True,
        current_user_id=user_id,
        reserved_filter='true',
    )
    try:
        docs = await aggregate_identities(request, pipeline)
    except PyMongoError as exc:
        print(f'[ERROR] list_reserved_identities: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    components = [merge_shallow_catalog_row(doc) for doc in docs]
    return JSONResponse(
        status_code=200,
        content={
            'user_id': user_id,
            'username': username,
            'reserved_count': len(components),
            'components': components,
        },
    )


@router.get(
    '/identities/meta/materials',
    summary=(
        'Materials for dropdowns (catalog distinct + additional suggestions)'
    ),
)
async def list_identity_materials(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    consumed_filter: ConsumedFilter = Query('active'),
):
    match = build_identity_match_stage(consumed_filter=consumed_filter)
    coll = await get_identities_col(request)
    try:
        values = await coll.distinct('material', match)
        content = merge_additional_with_catalog(ADDITIONAL_MATERIALS, values)
        return JSONResponse(status_code=200, content=content)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_materials: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/identities/meta/types',
    summary='Distinct component types on identities',
)
async def list_identity_types(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    consumed_filter: ConsumedFilter = Query('active'),
):
    match = build_identity_match_stage(consumed_filter=consumed_filter)
    coll = await get_identities_col(request)
    try:
        values = await coll.distinct('type', match)
        return JSONResponse(
            status_code=200, content=sorted(v for v in values if v)
        )
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_types: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get(
    '/identities/meta/datasets',
    summary=(
        'Datasets for dropdowns (catalog distinct + additional suggestions)'
    ),
)
async def list_identity_datasets(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    consumed_filter: ConsumedFilter = Query('active'),
):
    match = build_identity_match_stage(consumed_filter=consumed_filter)
    coll = await get_identities_col(request)
    try:
        values = await coll.distinct('dataset', match)
        content = merge_additional_with_catalog(ADDITIONAL_DATASETS, values)
        return JSONResponse(status_code=200, content=content)
    except PyMongoError as exc:
        print(f'[ERROR] list_identity_datasets: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post(
    '/identities/{identity_id}/reserve',
    summary='Reserve identity for the current user',
)
async def reserve_identity(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    identity = await _load_identity(request, identity_id)
    if identity.get('consumed_at'):
        raise HTTPException(
            status_code=409,
            detail='Consumed identity cannot be reserved',
        )

    reserved = identity.get('reserved') or ''
    if reserved:
        if reserved == current_user.id:
            return JSONResponse(
                status_code=200,
                content={
                    'message': 'Component already reserved by you',
                    'identity_id': identity_id,
                    'reserved_by': current_user.id,
                },
            )
        raise HTTPException(
            status_code=409,
            detail='Component is already reserved by another user',
        )

    identities = await get_identities_col(request)
    try:
        result = await identities.update_one(
            {'_id': identity_id},
            {'$set': {'reserved': current_user.id, 'lastmodified': now_iso()}},
        )
    except PyMongoError as exc:
        print(f'[ERROR] reserve_identity: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, detail='Failed to reserve component'
        )

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Component reserved successfully',
            'identity_id': identity_id,
            'reserved_by': current_user.id,
        },
    )


@router.delete(
    '/identities/{identity_id}/reserve',
    summary='Release reservation on an identity',
)
async def release_identity_reservation(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
):
    identity = await _load_identity(request, identity_id)
    reserved = identity.get('reserved') or ''
    if not reserved:
        return JSONResponse(
            status_code=200,
            content={
                'message': 'Component is not reserved',
                'identity_id': identity_id,
            },
        )

    if current_user.id != reserved and current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail='You can only release your own reservations',
        )

    identities = await get_identities_col(request)
    try:
        result = await identities.update_one(
            {'_id': identity_id},
            {'$set': {'reserved': '', 'lastmodified': now_iso()}},
        )
    except PyMongoError as exc:
        print(f'[ERROR] release_identity_reservation: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, detail='Failed to release component'
        )

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Component released successfully',
            'identity_id': identity_id,
        },
    )


@router.get(
    '/identities/{identity_id}/validate',
    summary='Validate current snapshot (admin only)',
)
async def validate_identity_snapshot(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
):
    identity = await _load_identity(request, identity_id)
    snapshot = await _load_current_snapshot(request, identity)
    snapshots = await get_snapshots_col(request)

    if not snapshot.get('validated', False):
        now = now_iso()
        update: Dict[str, Any] = {
            'validated': True,
            'lastmodified': now,
        }
        merged = {**snapshot, **update}
        update['etag'] = compute_snapshot_etag(merged)
        try:
            await snapshots.update_one(
                {'_id': snapshot['_id']},
                {'$set': update},
            )
        except PyMongoError as exc:
            print(f'[ERROR] validate_identity_snapshot: {exc}')
            raise HTTPException(
                status_code=500, detail='Internal server error'
            )

    row = await shallow_row_for_identity(request, identity_id)
    return JSONResponse(status_code=200, content=row)


@router.post(
    '/identities/{identity_id}/consume',
    summary='Mark identity as consumed (admin only)',
)
async def consume_identity(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
):
    """
    Set ``consumed_at`` (replaces legacy archive move).
    Geometry is unchanged.
    """
    identity = await _load_identity(request, identity_id)
    if identity.get('consumed_at'):
        raise HTTPException(
            status_code=409,
            detail='Identity is already consumed',
        )

    identities = await get_identities_col(request)
    now = now_iso()
    try:
        await identities.update_one(
            {'_id': identity_id},
            {
                '$set': {
                    'consumed_at': now,
                    'reserved': '',
                    'lastmodified': now,
                },
            },
        )
    except PyMongoError as exc:
        print(f'[ERROR] consume_identity: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Identity marked as consumed',
            'identity_id': identity_id,
            'consumed_at': now,
        },
    )


@router.post(
    '/identities/{identity_id}/restore',
    summary=(
        'Clear consumed_at and return identity to active catalog (admin only)'
    ),
)
async def restore_identity(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
):
    identity = await _load_identity(request, identity_id)
    if not identity.get('consumed_at'):
        raise HTTPException(
            status_code=409,
            detail='Identity is not consumed',
        )

    identities = await get_identities_col(request)
    now = now_iso()
    try:
        await identities.update_one(
            {'_id': identity_id},
            {'$set': {'consumed_at': None, 'lastmodified': now}},
        )
    except PyMongoError as exc:
        print(f'[ERROR] restore_identity: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    return JSONResponse(
        status_code=200,
        content={
            'message': 'Identity restored to active catalog',
            'identity_id': identity_id,
        },
    )


@router.delete(
    '/identities/{identity_id}',
    summary='Delete identity, snapshots, and on-disk assets (admin only)',
)
async def delete_identity(
    request: Request,
    admin_user: Annotated[User, Depends(require_admin)],
    identity_id: str,
):
    """Remove identity + all snapshots. Best-effort file cleanup."""
    identity = await _load_identity(request, identity_id)
    snapshots = await get_snapshots_col(request)
    identities = await get_identities_col(request)

    snapshot_ids: List[str] = []
    async for snap in snapshots.find(
        {'identity_id': identity_id},
        {'_id': 1},
    ):
        snapshot_ids.append(snap['_id'])

    current_id = identity.get('current_snapshot_id')
    if current_id and current_id not in snapshot_ids:
        snapshot_ids.append(current_id)

    for snapshot_id in snapshot_ids:
        preview_path = os.path.join(
            request.app.snapshot_preview_dir,
            f'{snapshot_id}.webp',
        )
        if os.path.exists(preview_path):
            try:
                os.remove(preview_path)
            except OSError as exc:
                print(f'[WARN] delete_identity preview: {exc}')

        photos_dir = os.path.join(
            request.app.snapshot_photos_dir,
            snapshot_id,
        )
        if os.path.isdir(photos_dir):
            try:
                shutil.rmtree(photos_dir)
            except OSError as exc:
                print(f'[WARN] delete_identity photos: {exc}')

    legacy_preview = os.path.join(
        request.app.component_preview_dir,
        f'{identity_id}.webp',
    )
    if os.path.exists(legacy_preview):
        try:
            os.remove(legacy_preview)
        except OSError as exc:
            print(f'[WARN] delete_identity legacy preview: {exc}')

    geometry_dir = os.path.join(
        request.app.component_geometry_dir,
        identity_id,
    )
    if os.path.isdir(geometry_dir):
        try:
            shutil.rmtree(geometry_dir)
        except OSError as exc:
            print(f'[WARN] delete_identity geometry: {exc}')

    try:
        await snapshots.delete_many({'identity_id': identity_id})
        result = await identities.delete_one({'_id': identity_id})
    except PyMongoError as exc:
        print(f'[ERROR] delete_identity DB: {exc}')
        raise HTTPException(status_code=500, detail='Internal server error')

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Identity not found')

    return JSONResponse(
        status_code=200,
        content={'ok': True, 'identity_id': identity_id},
    )
