#!/usr/bin/env python3.13
"""
Routes for the `component_snapshots` collection: the lists and one snapshot.

* `GET
    /snapshots/mine`, `/snapshots/pending`
    -> the caller's snapshots, the moderation queue
* `GET
    /snapshots/{snapshot_id}`
    -> fetch one snapshot by id (ADR-014 #3)

The files of a snapshot have their own modules: `snapshot_meshes.py`,
`snapshot_point_clouds.py`, `snapshot_media.py` (photos, preview, capture
fixtures) and `snapshot_proxies.py`.
"""

from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from apps.catalog.people import for_viewer
from apps.catalog.permissions import dataset_roles
from apps.catalog.read_models import (
    ComponentSnapshot,
    MySnapshotItem,
    PendingSnapshotItem,
    snapshot_body,
)
from .auth import get_current_active_user
from .access import load_datasets, viewer_of
from .public_access import (
    ensure_snapshot_read_access,
    viewer_etag,
    viewer_headers,
)
from .catalog_common import (
    internal_error,
    get_identities_col,
    get_snapshots_col,
    not_modified_response,
)
from logging_setup import get_logger
from .snapshot_common import OptionalUser


log = get_logger(__name__)

router = APIRouter()


MINE_STATUSES = ('draft', 'pending', 'rejected', 'published', 'withdrawn')


@router.get(
    '/snapshots',
    summary='The caller\'s own snapshots (mine=1), newest change first',
)
async def list_my_snapshots(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    mine: bool = Query(
        False, description='required: only the caller\'s own are listed'),
    status_: str = Query(
        'draft,pending,rejected', alias='status',
        description='comma-separated: draft, pending, rejected, published, '
                    'withdrawn; "any" for all'),
    limit: int = Query(100, ge=1, le=500),
):
    """
    The versions the caller added (``added_by_user_id``), for "My work"
    (8.118 Q4): drafts, pending and rejected ones by default, each with its
    piece and, when rejected, the reason. Nobody lists another person's
    snapshots here.
    """
    if not mine:
        raise HTTPException(
            status_code=422,
            detail='mine=1 is required: only your own snapshots are listed')
    wanted = ([s.strip() for s in status_.split(',') if s.strip()]
              if status_.strip() != 'any' else list(MINE_STATUSES))
    unknown = [s for s in wanted if s not in MINE_STATUSES]
    if unknown or not wanted:
        raise HTTPException(
            status_code=422,
            detail=f'status: one of {", ".join(MINE_STATUSES)} or any')
    snapshots = await get_snapshots_col(request)
    identities = await get_identities_col(request)
    try:
        docs = await snapshots.find(
            {'added_by_user_id': current_user.id,
             'status': {'$in': wanted}},
            {'_id': 1, 'identity_id': 1, 'version': 1, 'status': 1,
             'name': 1, 'created': 1, 'status_changed_at': 1,
             'supersedes': 1, 'status_history': 1},
        ).sort('status_changed_at', -1).limit(limit).to_list(length=None)
        ids = sorted({d['identity_id'] for d in docs if d.get('identity_id')})
        pieces = {
            i['_id']: i async for i in identities.find(
                {'_id': {'$in': ids}},
                {'_id': 1, 'current_snapshot_id': 1, 'catalog_number': 1,
                 'original_function': 1, 'material': 1, 'dataset': 1})}
    except PyMongoError:
        log.exception('list_my_snapshots')
        raise HTTPException(status_code=500, detail='Internal server error')
    items: List[Dict[str, Any]] = []
    for snap in docs:
        piece = pieces.get(snap.get('identity_id'))
        if piece is None:
            continue
        reason = None
        if snap.get('status') == 'rejected':
            for entry in reversed(snap.get('status_history') or []):
                if entry.get('to') == 'rejected':
                    reason = entry.get('reason')
                    break
        try:
            items.append(MySnapshotItem.model_validate({
                **{k: v for k, v in snap.items() if k != 'status_history'},
                'is_current': snap['_id'] == piece.get('current_snapshot_id'),
                'catalog_number': piece.get('catalog_number'),
                'original_function': piece.get('original_function'),
                'material': piece.get('material'),
                'dataset': piece.get('dataset'),
                'rejection_reason': reason,
            }).model_dump(by_alias=True))
        except Exception as exc:
            raise internal_error(exc, 'snapshot row validation')
    return JSONResponse(status_code=200, content=items)


@router.get(
    '/snapshots/pending',
    summary='Moderation queue: pending snapshots of the caller\'s datasets',
)
async def list_pending_snapshots(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Snapshots with ``status == pending`` in the datasets the caller
    moderates (admin: all), oldest first --- the order they arrived.
    """
    snapshots = await get_snapshots_col(request)
    identities = await get_identities_col(request)
    viewer = viewer_of(current_user)
    moderated = {d.id for d in (await load_datasets(request)).values()
                 if 'moderator' in dataset_roles(viewer, d)}

    try:
        pending_docs = await snapshots.find(
            {'status': 'pending'},
            {
                '_id': 1,
                'identity_id': 1,
                'version': 1,
                'status': 1,
                'name': 1,
                'created': 1,
                'supersedes': 1,
                'added_by_username': 1,
            },
        ).sort('created', 1).to_list(length=None)
    except PyMongoError:
        log.exception('list_pending_snapshots')
        raise HTTPException(status_code=500, detail='Internal server error')

    items: List[Dict[str, Any]] = []
    for snap in pending_docs:
        identity_id = snap.get('identity_id')
        if not identity_id:
            continue

        identity_doc = await identities.find_one(
            {'_id': identity_id},
            {
                '_id': 1,
                'current_snapshot_id': 1,
                'catalog_number': 1,
                'original_function': 1,
                'material': 1,
                'dataset': 1,
            },
        )
        if identity_doc is None or identity_doc.get('dataset') not in moderated:
            continue

        current_snapshot_id = identity_doc.get('current_snapshot_id')
        live_version: Optional[int] = None
        if current_snapshot_id:
            current_snap = await snapshots.find_one(
                {'_id': current_snapshot_id},
                {'version': 1},
            )
            if current_snap is not None:
                live_version = current_snap.get('version')

        row = {
            **snap,
            'is_current': snap.get('_id') == current_snapshot_id,
            'catalog_number': identity_doc.get('catalog_number'),
            'original_function': identity_doc.get('original_function'),
            'material': identity_doc.get('material'),
            'dataset': identity_doc.get('dataset'),
            'live_version': live_version,
        }
        try:
            items.append(
                PendingSnapshotItem.model_validate(row).model_dump(
                    by_alias=True
                )
            )
        except Exception as exc:
            raise internal_error(exc, 'pending snapshot row validation')

    return JSONResponse(status_code=200, content=items)


@router.get(
    '/snapshots/{snapshot_id}',
    summary='Get snapshot by id',
    response_model=ComponentSnapshot,
    response_model_by_alias=True,
)
async def get_snapshot_by_id(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
):
    """Return a single snapshot document. ETag == stored `etag` field.
    A withdrawn one outside its dataset answers with its tombstone (8.17)."""
    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
        allow_tombstone=True,
    )

    etag = doc.get('etag')
    if not etag:
        raise HTTPException(
            status_code=500,
            detail=f'Snapshot {snapshot_id} has no etag field',
        )
    # the stored etag for a signed-in caller, its own one for an anonymous
    # caller: the bodies differ (8.101), a 304 must not mix them
    etag = viewer_etag(etag, current_user)

    if_none_match = request.headers.get('if-none-match')
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag, **viewer_headers())

    try:
        body = snapshot_body(doc)
    except Exception as exc:
        raise internal_error(exc, 'snapshot validation')

    return JSONResponse(
        status_code=200,
        content=for_viewer(body, current_user),      # no people (8.101)
        headers=viewer_headers(etag=etag),
    )
