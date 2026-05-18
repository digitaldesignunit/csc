#!/usr/bin/env python3.9
"""
Identity ID transmission queue (CAD / Grasshopper handoff).

Stores one pending **identity** UUID per user in ``component_id_transmission``
(document ``_id`` = user_id, field ``identity_id``).

Lifecycle:
    - User scans a QR code and POSTs an identity id to queue for AddComponent.
    - Rejected if the UUID is already ``component_identities._id`` or
      ``component_snapshots._id`` (tags must be unused identity ids).
    - Grasshopper fetches pending via GET; consume after successful create.
"""

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from apps.catalog.models import User  # NOQA
from .auth import get_current_active_user
from .catalog_common import (
    get_identities_col,
    get_snapshots_col,
    validate_uuid,
)

router = APIRouter()

MAX_IDENTITY_ID_LEN = 128

CatalogIdConflict = Literal['identity', 'snapshot']


class TransmitPayload(BaseModel):
    identity_id: str = Field(
        min_length=1,
        max_length=MAX_IDENTITY_ID_LEN,
        description='Identity UUID scanned from the QR code.',
    )
    force_overwrite: bool = Field(
        default=False,
        description=(
            'If True, overwrite an existing pending transmission with a '
            'different identity_id.'
        ),
    )


class ConsumePayload(BaseModel):
    identity_id: Optional[str] = Field(
        default=None,
        max_length=MAX_IDENTITY_ID_LEN,
        description=(
            'Optional: only consume if the pending item matches this id.'
        ),
    )


async def get_transmit_col(request: Request):
    return request.app.mongodb_component_id_transmission


async def _identity_exists(request: Request, identity_id: str) -> bool:
    identities = await get_identities_col(request)
    doc = await identities.find_one({'_id': identity_id}, {'_id': 1})
    return doc is not None


async def _snapshot_exists(request: Request, snapshot_id: str) -> bool:
    snapshots = await get_snapshots_col(request)
    doc = await snapshots.find_one({'_id': snapshot_id}, {'_id': 1})
    return doc is not None


async def _catalog_id_conflict(
    request: Request,
    uuid_value: str,
) -> Optional[CatalogIdConflict]:
    """Return how this UUID is already used in the catalog, if at all."""
    if await _identity_exists(request, uuid_value):
        return 'identity'
    if await _snapshot_exists(request, uuid_value):
        return 'snapshot'
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _pending_identity_id(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    value = doc.get('identity_id')
    return str(value) if value else None


def _serialize_item(doc: dict) -> dict:
    if not doc:
        return None
    return {
        'user_id': doc.get('_id'),
        'identity_id': _pending_identity_id(doc),
        'created_at': doc.get('created_at'),
        'updated_at': doc.get('updated_at'),
    }


def _conflict_response(
    conflict: CatalogIdConflict,
    identity_id: str,
) -> JSONResponse:
    if conflict == 'identity':
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                'status': 'identity_id_exists',
                'message': (
                    'This identity id already exists in the catalog and '
                    'cannot be transmitted as a new id.'
                ),
                'identity_id': identity_id,
            },
        )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            'status': 'snapshot_id_exists',
            'message': (
                'This UUID is already a snapshot id. Transmit the physical '
                'identity id from the tag, not a snapshot id.'
            ),
            'identity_id': identity_id,
        },
    )


@router.get(
    '/component_id_transmission/availability/{identity_id}',
    summary='Check whether a UUID is free to transmit as a new identity id',
)
async def check_identity_availability(
    identity_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    identity_id = validate_uuid(identity_id.strip(), label='identity id')
    conflict = await _catalog_id_conflict(request, identity_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            'identity_id': identity_id,
            'available': conflict is None,
            'conflict': conflict,
        },
    )


@router.get(
    '/component_id_transmission',
    summary='Get the current pending transmitted identity id for the user',
)
async def get_pending_transmission(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    coll = await get_transmit_col(request)
    try:
        doc = await coll.find_one({'_id': current_user.id})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'pending': _serialize_item(doc)},
        )
    except PyMongoError as e:
        print(f'[ERROR] get_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.post(
    '/component_id_transmission',
    summary='Transmit a scanned identity id (one pending per user)',
)
async def transmit_identity_id(
    payload: TransmitPayload,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    identity_id = payload.identity_id.strip()
    if not identity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='identity_id must not be empty',
        )
    validate_uuid(identity_id, label='identity id')

    coll = await get_transmit_col(request)
    now = _now_iso()

    try:
        conflict = await _catalog_id_conflict(request, identity_id)
        if conflict is not None:
            return _conflict_response(conflict, identity_id)

        existing = await coll.find_one({'_id': current_user.id})
        pending_id = _pending_identity_id(existing)

        if pending_id == identity_id:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    'status': 'already_pending',
                    'item': _serialize_item(existing),
                },
            )

        if existing and not payload.force_overwrite:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    'status': 'conflict',
                    'message': (
                        'A different identity id is still pending. '
                        'Confirm overwrite to replace it.'
                    ),
                    'existing': _serialize_item(existing),
                    'new_identity_id': identity_id,
                },
            )

        new_doc = {
            '_id': current_user.id,
            'identity_id': identity_id,
            'created_at': now,
            'updated_at': now,
        }

        await coll.replace_one(
            {'_id': current_user.id},
            new_doc,
            upsert=True,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'status': 'overwritten' if existing else 'stored',
                'item': _serialize_item(new_doc),
            },
        )
    except PyMongoError as e:
        print(f'[ERROR] transmit_identity_id DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.delete(
    '/component_id_transmission',
    summary='Clear the current pending transmitted identity id',
)
async def clear_pending_transmission(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    coll = await get_transmit_col(request)
    try:
        result = await coll.delete_one({'_id': current_user.id})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'status': 'cleared',
                'deleted': int(result.deleted_count or 0),
            },
        )
    except PyMongoError as e:
        print(f'[ERROR] clear_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )


@router.post(
    '/component_id_transmission/consume',
    summary='Consume pending transmission after identity was created',
)
async def consume_pending_transmission(
    payload: ConsumePayload,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    coll = await get_transmit_col(request)
    try:
        query = {'_id': current_user.id}
        if payload.identity_id:
            query['identity_id'] = validate_uuid(
                payload.identity_id.strip(),
                label='identity id',
            )

        result = await coll.delete_one(query)
        consumed = int(result.deleted_count or 0) > 0

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'status': 'consumed' if consumed else 'noop',
                'consumed': consumed,
            },
        )
    except PyMongoError as e:
        print(f'[ERROR] consume_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error',
        )
