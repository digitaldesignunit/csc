#!/usr/bin/env python3.9
"""
Component ID Transmission endpoints.

Allows a user to transmit a scanned component ID from the web frontend to
CAD integrations. One pending transmission per user is stored in the
`component_id_transmission` MongoDB collection (document _id = user_id).

Lifecycle:
    - User scans a QR code on the frontend and POSTs the ID here.
    - If the user already has a pending item with a different ID, the request
      is rejected with 409 unless `force_overwrite` is True.
    - Client integration fetches the current pending item via GET.
    - After the component is successfully added to the database, the pending
      item is removed via POST /component_id_transmission/consume (or DELETE).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import datetime, timezone
from typing import Annotated, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.models import User  # NOQA
from .auth import get_current_active_user


# INIT ROUTER -----------------------------------------------------------------
router = APIRouter()


# CONSTANTS -------------------------------------------------------------------
MAX_COMPONENT_ID_LEN = 128


# PAYLOAD MODELS --------------------------------------------------------------
class TransmitPayload(BaseModel):
    component_id: str = Field(
        min_length=1,
        max_length=MAX_COMPONENT_ID_LEN,
        description="The component ID that was scanned from the QR code."
    )
    force_overwrite: bool = Field(
        default=False,
        description=(
            "If True, overwrite an existing pending transmission with a "
            "different component_id."
        )
    )


class ConsumePayload(BaseModel):
    component_id: Optional[str] = Field(
        default=None,
        max_length=MAX_COMPONENT_ID_LEN,
        description=(
            "Optional: if provided, only consume the pending transmission if "
            "it matches this component_id. Prevents accidentally consuming "
            "a newer transmission."
        )
    )


# FASTAPI DEPENDENCIES --------------------------------------------------------
async def get_transmit_col(request: Request):
    return request.app.mongodb_component_id_transmission


async def get_components_col(request: Request):
    return request.app.mongodb_components


# HELPERS ---------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _serialize_item(doc: dict) -> dict:
    """Shape the Mongo document for API responses."""
    if not doc:
        return None
    return {
        'user_id': doc.get('_id'),
        'component_id': doc.get('component_id'),
        'created_at': doc.get('created_at'),
        'updated_at': doc.get('updated_at'),
    }


# ROUTES ----------------------------------------------------------------------

@router.get(
    '/component_id_transmission',
    summary='Get the current pending transmitted component ID for the user'
)
async def get_pending_transmission(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Returns the current pending transmission for the authenticated user.
    If there is none, returns `{ "pending": null }`.
    """
    coll = await get_transmit_col(request)
    try:
        doc = await coll.find_one({'_id': current_user.id})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={'pending': _serialize_item(doc)}
        )
    except PyMongoError as e:
        print(f'[ERROR] get_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.post(
    '/component_id_transmission',
    summary=(
        'Transmit a scanned component ID for the user (one pending per user)'
    )
)
async def transmit_component_id(
    payload: TransmitPayload,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Store a pending component ID transmission for the authenticated user.

    Behavior:
        - No existing pending item -> create and return 200 `status: stored`.
        - Existing pending item with same ID -> return 200
          `status: already_pending` (no-op).
        - Existing pending item with different ID and
          `force_overwrite=False` -> return 409 `status: conflict` with the
          existing item, so the frontend can prompt the user.
        - Existing pending item with different ID and
          `force_overwrite=True` -> overwrite and return 200
          `status: overwritten`.
    """
    component_id = payload.component_id.strip()
    if not component_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='component_id must not be empty'
        )

    coll = await get_transmit_col(request)
    now = _now_iso()

    try:
        components_coll = await get_components_col(request)
        existing_component = await components_coll.find_one(
            {'_id': component_id},
            {'_id': 1}
        )
        if existing_component:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    'status': 'component_id_exists',
                    'message': (
                        'This component ID already exists in the catalog and '
                        'cannot be transmitted as a new ID.'
                    ),
                    'component_id': component_id,
                }
            )

        existing = await coll.find_one({'_id': current_user.id})

        if existing and existing.get('component_id') == component_id:
            # Idempotent: same ID already pending
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    'status': 'already_pending',
                    'item': _serialize_item(existing),
                }
            )

        if existing and not payload.force_overwrite:
            # Different ID and user did not confirm overwrite
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    'status': 'conflict',
                    'message': (
                        'A different component ID is still pending. '
                        'Confirm overwrite to replace it.'
                    ),
                    'existing': _serialize_item(existing),
                    'new_component_id': component_id,
                }
            )

        # Upsert (create or overwrite). A force-overwrite is treated as a
        # fresh transmission, so created_at is reset to `now`.
        new_doc = {
            '_id': current_user.id,
            'component_id': component_id,
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
            }
        )
    except PyMongoError as e:
        print(f'[ERROR] transmit_component_id DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.delete(
    '/component_id_transmission',
    summary='Clear the current pending transmitted component ID'
)
async def clear_pending_transmission(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Removes the user's pending transmission item, if any.
    Idempotent: always returns 200.
    """
    coll = await get_transmit_col(request)
    try:
        result = await coll.delete_one({'_id': current_user.id})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'status': 'cleared',
                'deleted': int(result.deleted_count or 0),
            }
        )
    except PyMongoError as e:
        print(f'[ERROR] clear_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )


@router.post(
    '/component_id_transmission/consume',
    summary=(
        'Consume the current pending transmission '
        '(after component successfully added)'
    )
)
async def consume_pending_transmission(
    payload: ConsumePayload,
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: Request,
):
    """
    Consume the user's pending transmission. Intended to be called from
    client integrations (or from the frontend) only after the component has
    been successfully added to the database.

    If `component_id` is provided in the payload, the item is only removed
    when it matches, which prevents accidentally consuming a newer scan that
    the user performed in the meantime.
    """
    coll = await get_transmit_col(request)
    try:
        query = {'_id': current_user.id}
        if payload.component_id:
            query['component_id'] = payload.component_id.strip()

        result = await coll.delete_one(query)
        consumed = int(result.deleted_count or 0) > 0

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'status': 'consumed' if consumed else 'noop',
                'consumed': consumed,
            }
        )
    except PyMongoError as e:
        print(f'[ERROR] consume_pending_transmission DB error: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal server error'
        )
