#!/usr/bin/env python3.9

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from apps.catalog.models import User
from .catalog_common import get_identities_col, get_snapshots_col


def identity_allows_anonymous_read(identity_doc: Dict[str, Any]) -> bool:
    return identity_doc.get('is_public') is True


async def load_identity_doc(
    request: Request,
    identity_id: str,
    *,
    projection: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    identities = await get_identities_col(request)
    doc = await identities.find_one({'_id': identity_id}, projection)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Identity {identity_id} not found',
        )
    return doc


async def ensure_identity_read_access(
    request: Request,
    identity_id: str,
    current_user: Optional[User],
    *,
    projection: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    identity_doc = await load_identity_doc(
        request,
        identity_id,
        projection=projection,
    )
    if current_user is not None:
        return identity_doc
    if identity_allows_anonymous_read(identity_doc):
        return identity_doc
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Authentication required',
        headers={'WWW-Authenticate': 'Bearer'},
    )


async def ensure_snapshot_read_access(
    request: Request,
    snapshot_id: str,
    current_user: Optional[User],
) -> Dict[str, Any]:
    snapshots = await get_snapshots_col(request)
    snapshot_doc = await snapshots.find_one({'_id': snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Snapshot {snapshot_id} not found',
        )

    identity_id = snapshot_doc.get('identity_id')
    if not identity_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Snapshot {snapshot_id} has no identity_id',
        )

    await ensure_identity_read_access(
        request,
        str(identity_id),
        current_user,
        projection={'_id': 1, 'is_public': 1},
    )

    return snapshot_doc


def public_cache_control() -> str:
    return 'public, max-age=3600'
