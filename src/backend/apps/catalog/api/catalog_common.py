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
