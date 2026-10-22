#!/usr/bin/env python3.13
"""
The JSON Schema routes that the code generators read.

* `GET /schema/catalog-compose`
    -> JSON Schema for the passport body (frontend codegen)

* `GET /schema/catalog-shared`
    -> JSON Schema for shared catalog value types (frontend codegen)

* `GET /schema/create-identity`
    -> JSON Schema for POST /identities (Grasshopper)

* `GET /schema/create-snapshot`
    -> JSON Schema for POST /identities/{id}/snapshots (Grasshopper)

* the row, summary and queue schemas of the catalog, snapshot lists and
  queues (`/schema/catalog-row`, `/schema/snapshot-summary`,
  `/schema/pending-snapshot`, `/schema/my-snapshot`)
"""

import hashlib
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from apps.catalog.read_models import (
    CatalogRow,
    LocationMap,
    SimilarPieces,
    CatalogSharedTypesEnvelope,
    ComponentPassport,
    MySnapshotItem,
    PendingSnapshotItem,
    SnapshotSummaryItem,
)
from .catalog_common import not_modified_response


router = APIRouter()


@router.get(
    '/schema/catalog-compose',
    summary='JSON Schema for the passport body (GET .../{id}/compose)',
)
async def get_catalog_passport_json_schema():
    """
    Used by the frontend `generate:models` script (see `CatalogModels.ts`).
    """
    schema = ComponentPassport.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/catalog-shared',
    summary='JSON Schema for shared catalog value types (frontend codegen)',
)
async def get_catalog_shared_json_schema():
    """
    Used by the frontend `generate:models` script
    (see `CatalogSharedTypes.ts`).
    """
    schema = CatalogSharedTypesEnvelope.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/catalog-row',
    summary='JSON Schema for a GET /identities row (CatalogRow)',
)
async def get_catalog_row_json_schema():
    """Used by frontend `generate:models` (see `CatalogModels.ts`)."""
    schema = CatalogRow.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/location-map',
    summary='JSON Schema for GET /identities/locations (LocationMap)',
)
async def get_location_map_json_schema():
    """Used by frontend `generate:models` (see `CatalogModels.ts`)."""
    schema = LocationMap.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/similar-pieces',
    summary='JSON Schema for GET /identities/{id}/similar (SimilarPieces)',
)
async def get_similar_pieces_json_schema():
    """Used by frontend `generate:models` (see `CatalogModels.ts`)."""
    schema = SimilarPieces.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/snapshot-summary',
    summary=(
        'JSON Schema for GET /identities/{id}/snapshots '
        'row (SnapshotSummaryItem)'
    ),
)
async def get_snapshot_summary_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = SnapshotSummaryItem.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/pending-snapshot',
    summary='JSON Schema for GET /snapshots/pending row',
)
async def get_pending_snapshot_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = PendingSnapshotItem.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


@router.get(
    '/schema/my-snapshot',
    summary='JSON Schema for GET /snapshots?mine=1 row',
)
async def get_my_snapshot_json_schema():
    """Used by frontend `generate:models` (see `SnapshotModels.ts`)."""
    schema = MySnapshotItem.model_json_schema(by_alias=True)
    return JSONResponse(status_code=200, content=schema)


def _schema_etag(schema: dict) -> str:
    schema_string = json.dumps(schema, sort_keys=True, separators=(',', ':'))
    return hashlib.md5(schema_string.encode('utf-8')).hexdigest()


def _check_schema_conditional_request(request: Request, etag: str) -> bool:
    if_none_match = request.headers.get('if-none-match')
    return bool(if_none_match and if_none_match == etag)


def _create_schema_response(request: Request, schema: dict):
    etag = _schema_etag(schema)
    if _check_schema_conditional_request(request, etag):
        return not_modified_response(etag)
    return JSONResponse(
        status_code=200,
        content=schema,
        headers={
            'ETag': etag,
            'Cache-Control': 'public, max-age=86400',
        },
    )


@router.get(
    '/schema/create-snapshot',
    summary=(
        'JSON Schema for POST /identities/{id}/snapshots and '
        '/snapshots/{id}/supersede (SnapshotDraftBody)'
    ),
)
async def get_create_snapshot_json_schema(request: Request):
    """
    The 0.6 body of a new state or a correction, as the Grasshopper
    bridge and other clients send it. Derived fields are not part of it.
    """
    from .snapshot_lifecycle import SnapshotDraftBody
    return _create_schema_response(
        request, SnapshotDraftBody.model_json_schema(by_alias=True))


@router.get(
    '/schema/create-identity',
    summary='JSON Schema for POST /identities (IdentityCreateBody)',
)
async def get_create_identity_json_schema(request: Request):
    """
    The 0.6 body of a new component with its v0 draft. ``snapshot`` is a
    ``SnapshotDraftBody``: the schema refers to it instead of an open
    object, so a client validates the whole body.
    """
    from .identity_edit import IdentityCreateBody
    from .snapshot_lifecycle import SnapshotDraftBody
    schema = IdentityCreateBody.model_json_schema(by_alias=True)
    snapshot = SnapshotDraftBody.model_json_schema(by_alias=True)
    defs = schema.setdefault('$defs', {})
    for name, definition in (snapshot.pop('$defs', None) or {}).items():
        defs.setdefault(name, definition)
    defs['SnapshotDraftBody'] = snapshot
    description = schema['properties']['snapshot'].get('description')
    schema['properties']['snapshot'] = {
        '$ref': '#/$defs/SnapshotDraftBody',
        **({'description': description} if description else {}),
    }
    return _create_schema_response(request, schema)
