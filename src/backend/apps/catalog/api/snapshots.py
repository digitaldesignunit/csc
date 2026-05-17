#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_snapshots` collection.

* `GET /snapshots/{snapshot_id}` — fetch one snapshot by id (ADR-014 #3).

Further M4 routes (create v0, virtual, PATCH current) go here later.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.catalog.models import ComponentSnapshot, User
from .auth import get_current_active_user

router = APIRouter()


async def get_snapshots_col(request: Request):
    return request.app.mongodb_component_snapshots


@router.get(
    '/snapshots/{snapshot_id}',
    summary='Get snapshot by id',
    response_model=ComponentSnapshot,
    response_model_by_alias=True,
)
async def get_snapshot_by_id(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    """Return a single snapshot document. ETag == stored `etag` field."""
    snapshots = await get_snapshots_col(request)

    doc = await snapshots.find_one({'_id': snapshot_id})
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Snapshot {snapshot_id} not found',
        )

    etag = doc.get('etag')
    if not etag:
        raise HTTPException(
            status_code=500,
            detail=f'Snapshot {snapshot_id} has no etag field',
        )

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return JSONResponse(
            status_code=304,
            content=None,
            headers={'ETag': etag},
        )

    try:
        model = ComponentSnapshot.model_validate(doc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Stored snapshot failed Pydantic validation: {exc}',
        )

    body = model.model_dump(by_alias=True)

    return JSONResponse(
        status_code=200,
        content=body,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=3600',
        },
    )
