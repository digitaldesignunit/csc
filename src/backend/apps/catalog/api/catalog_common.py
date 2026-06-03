"""Shared helpers for identity/snapshot catalog routes."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from pymongo import ReturnDocument


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def compute_snapshot_etag(snapshot_doc: Dict[str, Any]) -> str:
    """sha256 over canonical snapshot JSON, excluding etag and lastmodified."""
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ('etag', 'lastmodified')
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def resolve_new_component_name(
    name: Optional[str],
    catalog_number: int,
) -> str:
    """
    Use catalog number when the client leaves name empty (add-component flow).
    """
    raw = (name or '').strip()
    if not raw or raw.lower() == 'unnamed component':
        return f'Component #{catalog_number}'
    return raw


async def allocate_catalog_number(request: Request) -> int:
    """Return the next catalog_number and advance the counter atomically."""
    counters = request.app.mongodb_counters
    doc = await counters.find_one_and_update(
        {'_id': 'catalog_number'},
        {'$inc': {'next_value': 1}},
        return_document=ReturnDocument.BEFORE,
    )
    if doc is None or doc.get('next_value') is None:
        raise HTTPException(
            status_code=500,
            detail='catalog_number counter is not initialised',
        )
    return int(doc['next_value'])


async def validate_parent_identities(
    request: Request,
    parent_ids: Optional[List[str]],
    *,
    self_id: Optional[str] = None,
) -> None:
    if not parent_ids:
        return
    col = request.app.mongodb_component_identities
    for pid in parent_ids:
        if self_id and pid == self_id:
            raise HTTPException(
                status_code=400,
                detail='identity cannot list itself in parent_identities',
            )
        found = await col.find_one({'_id': pid}, {'_id': 1})
        if found is None:
            raise HTTPException(
                status_code=404,
                detail=f'Parent identity {pid} not found',
            )


async def get_identities_col(request: Request):
    return request.app.mongodb_component_identities


async def get_snapshots_col(request: Request):
    return request.app.mongodb_component_snapshots


def validate_uuid(value: str, *, label: str = 'id') -> str:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f'Invalid {label}',
        )
    return str(value)


async def validate_snapshot_and_promote(
    request: Request,
    snapshot_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Mark a snapshot validated and set it as the identity's live snapshot.

    Idempotent when the snapshot is already validated and current.
    """
    from pymongo.errors import PyMongoError

    validate_uuid(snapshot_id, label='snapshot id')
    snapshots = await get_snapshots_col(request)
    identities = await get_identities_col(request)

    snapshot_doc = await snapshots.find_one({'_id': snapshot_id})
    if snapshot_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Snapshot {snapshot_id} not found',
        )

    identity_id = snapshot_doc.get('identity_id')
    if not identity_id:
        raise HTTPException(
            status_code=500,
            detail=f'Snapshot {snapshot_id} has no identity_id',
        )

    identity_doc = await identities.find_one({'_id': identity_id})
    if identity_doc is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f'Identity {identity_id} not found for snapshot {snapshot_id}'
            ),
        )

    now = now_iso()

    if not snapshot_doc.get('validated', False):
        snap_update: Dict[str, Any] = {
            'validated': True,
            'lastmodified': now,
        }
        merged = {**snapshot_doc, **snap_update}
        snap_update['etag'] = compute_snapshot_etag(merged)
        try:
            await snapshots.update_one(
                {'_id': snapshot_id},
                {'$set': snap_update},
            )
        except PyMongoError as exc:
            print(f'[ERROR] validate_snapshot_and_promote snapshot: {exc}')
            raise HTTPException(
                status_code=500,
                detail='Internal server error',
            )
        snapshot_doc = {**snapshot_doc, **snap_update}

    current_snapshot_id = identity_doc.get('current_snapshot_id')
    if current_snapshot_id != snapshot_id:
        identity_update = {
            'current_snapshot_id': snapshot_id,
            'lastmodified': now,
        }
        try:
            await identities.update_one(
                {'_id': identity_id},
                {'$set': identity_update},
            )
        except PyMongoError as exc:
            print(f'[ERROR] validate_snapshot_and_promote identity: {exc}')
            raise HTTPException(
                status_code=500,
                detail='Internal server error',
            )
        identity_doc = {**identity_doc, **identity_update}

    return identity_doc, snapshot_doc
