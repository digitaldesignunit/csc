#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_identities` collection.

Owns the primary read path of the new data model:

* `GET /identities/{identity_id}/compose` -> identity + current snapshot.

Single-snapshot reads: `GET /snapshots/{snapshot_id}` in `snapshots.py`.

Write routes: PATCH current snapshot here; create / virtual routes in
`snapshots.py` when added.

Legacy `/components/...` routes in `components.py` are untouched and remain
available throughout the M4 cutover.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import (
    ComponentIdentity,
    ComponentSnapshot,
    ComposeIdentityResponse,
    UpdateComponentSnapshotModel,
    User,
)
from .auth import get_current_active_user, require_admin


router = APIRouter()


async def get_identities_col(request: Request):
    return request.app.mongodb_component_identities


async def get_snapshots_col(request: Request):
    return request.app.mongodb_component_snapshots


def _compute_snapshot_etag(snapshot_doc: Dict[str, Any]) -> str:
    """sha256 over canonical snapshot JSON, excluding etag and lastmodified."""
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ('etag', 'lastmodified')
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


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
    geometry-derived fields cannot be changed here (new snapshot version instead).
    Photo files use dedicated routes under `/snapshots/.../photos/...`.
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
        raise HTTPException(status_code=400, detail='No updatable fields provided')

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    update_data['lastmodified'] = now

    merged = {**snapshot_doc, **update_data}
    update_data['etag'] = _compute_snapshot_etag(merged)

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
