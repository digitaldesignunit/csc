#!/usr/bin/env python3.13
"""
The change log at the API (data model spec section 3.8, I30; decision
8.36; plan P4).

* ``log_change(...)`` --- every route that changes an identity, snapshot or
  evidence record calls it with the document before and after the write
* ``GET /identities/{id}/changes`` --- members of D and admin: the entries
  of the identity, its snapshots and its evidence, newest first
* ``as_of_body(...)`` --- the record as it was at a date (``?as_of=``)
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.history import as_of, diff
from apps.catalog.models import User
from apps.catalog.permissions import dataset_roles
from .access import dataset_of, ensure_identity_visible, viewer_of
from .auth import get_current_active_user
from .catalog_common import now_iso, validate_uuid

router = APIRouter()


async def log_change(request: Request, kind: str, before: Dict[str, Any],
                     after: Dict[str, Any], *, by_user_id: Optional[str],
                     cause: str, source_record_id: Optional[str] = None,
                     at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Append one entry for a write (I30); a write that changes no logged
    field appends nothing. Returns the entry."""
    changes = diff(kind, before, after)
    if not changes:
        return None
    record_id = after.get('_id') or before.get('_id')
    identity_id = record_id if kind == 'identity' else \
        (after.get('identity_id') or before.get('identity_id'))
    entry = {'_id': str(uuid.uuid4()), 'record_kind': kind,
             'record_id': record_id, 'identity_id': identity_id,
             'at': at or now_iso(), 'by_user_id': by_user_id, 'cause': cause,
             'source_record_id': source_record_id, 'changes': changes}
    await request.app.mongodb_change_log.insert_one(dict(entry))
    return entry


async def entries_for(request: Request, record_id: str) -> List[dict]:
    return await request.app.mongodb_change_log.find(
        {'record_id': record_id}, {'_id': 0}).sort('at', 1).to_list(
        length=None)


def _when(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise HTTPException(status_code=422,
                            detail=f'as_of: not an ISO-8601 date: {value!r}'
                            ) from exc


async def as_of_body(request: Request, kind: str, doc: Dict[str, Any],
                     at: str) -> Dict[str, Any]:
    """The record as it was at ``at`` (404 if it did not exist yet)."""
    when = _when(at)
    created = doc.get('created')
    if created and _when(created) > when:
        raise HTTPException(status_code=404,
                            detail=f'{kind} {doc["_id"]} did not exist at '
                                   f'{at}')
    return as_of(kind, doc, await entries_for(request, doc['_id']), at)


@router.get('/identities/{identity_id}/changes',
            summary='Change log of a component (members of D, admin)')
async def list_changes(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    identity_id: str,
    limit: int = Query(200, ge=1, le=1000),
):
    """Entries of the identity, its snapshots and evidence, newest first.
    Old values may name people, so the log is for members only (8.36)."""
    validate_uuid(identity_id, label='identity id')
    identity = await ensure_identity_visible(request, identity_id,
                                             current_user)
    viewer = viewer_of(current_user)
    dataset = await dataset_of(request, identity.get('dataset'))
    if not dataset_roles(viewer, dataset):
        raise HTTPException(status_code=403,
                            detail='The change log is for members of the '
                                   'dataset.')
    entries = await request.app.mongodb_change_log.find(
        {'identity_id': identity_id}).sort('at', -1).limit(limit).to_list(
        length=None)
    return JSONResponse(status_code=200, content=entries)
