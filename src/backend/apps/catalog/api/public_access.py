#!/usr/bin/env python3.13

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from apps.catalog.models import User
from .access import ensure_identity_visible, ensure_snapshot_visible
from .catalog_common import get_identities_col


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
    """The identity, if the caller may see the component (3.6, 3.1.5);
    401 (anonymous) / 403 (signed in) otherwise (8.11)."""
    return await ensure_identity_visible(
        request, identity_id, current_user, projection=projection)


async def ensure_snapshot_read_access(
    request: Request,
    snapshot_id: str,
    current_user: Optional[User],
    *,
    allow_tombstone: bool = False,
) -> Dict[str, Any]:
    """The snapshot, if the caller sees it in full: published ones follow
    the component's visibility, unpublished ones their author and
    moderator(D) (7.0). Files never serve a tombstone."""
    return await ensure_snapshot_visible(
        request, snapshot_id, current_user, allow_tombstone=allow_tombstone)


def public_cache_control() -> str:
    return 'public, max-age=3600'
