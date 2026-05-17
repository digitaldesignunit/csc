#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_identities` collection.

Owns the primary read path of the new data model:

* `GET /identities/{identity_id}/compose` -> identity + current snapshot.

Single-snapshot reads: `GET /snapshots/{snapshot_id}` in `snapshots.py`.

Write routes (component creation, virtual snapshot proposals, PATCH current
snapshot) live alongside snapshot reads in `snapshots.py`.

Legacy `/components/...` routes in `components.py` are untouched and remain
available throughout the M4 cutover.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.catalog.models import (
    ComponentIdentity,
    ComponentSnapshot,
    ComposeIdentityResponse,
    User,
)
from .auth import get_current_active_user


router = APIRouter()


async def get_identities_col(request: Request):
    return request.app.mongodb_component_identities


async def get_snapshots_col(request: Request):
    return request.app.mongodb_component_snapshots


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
