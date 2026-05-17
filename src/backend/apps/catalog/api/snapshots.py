#!/usr/bin/env python3.9
"""Routes for the v0.5 `component_snapshots` collection.

* `GET /snapshots/{snapshot_id}` — fetch one snapshot by id (ADR-014 #3)
* `GET /snapshots/{snapshot_id}/preview` — rendered catalog thumbnail
* `GET|PUT|DELETE /snapshots/{snapshot_id}/photos/{index}` — user photos (JPEG)
"""

import io
import os
from typing import Annotated, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pymongo.errors import PyMongoError

from apps.catalog.models import ComponentSnapshot, User
from utility import ensure_file, read_upload_limited

from .auth import get_current_active_user
from .catalog_common import get_snapshots_col, validate_uuid
from .snapshot_images import (
    PHOTO_EXTENSION,
    PHOTO_MEDIA_TYPE,
    compress_and_save_jpeg,
    photo_filename,
)

router = APIRouter()

_ALLOWED_PHOTO_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/webp',
})

_LEGACY_PHOTO_EXTENSION = '.webp'


async def _load_snapshot(
    request: Request,
    snapshot_id: str,
) -> dict:
    validate_uuid(snapshot_id, label='snapshot id')
    snapshots = await get_snapshots_col(request)
    doc = await snapshots.find_one({'_id': snapshot_id})
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f'Snapshot {snapshot_id} not found',
        )
    return doc


def _resolve_preview_path(request: Request, snapshot_id: str) -> str:
    """Return path to snapshot_previews/{snapshot_id}.webp."""
    return os.path.join(
        request.app.snapshot_preview_dir,
        f'{snapshot_id}.webp',
    )


def _photo_dir(request: Request, snapshot_id: str) -> str:
    return os.path.join(request.app.snapshot_photos_dir, snapshot_id)


def _photo_path(request: Request, snapshot_id: str, index: int) -> str:
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')
    return os.path.join(
        _photo_dir(request, snapshot_id),
        photo_filename(index),
    )


def _legacy_photo_path(request: Request, snapshot_id: str, index: int) -> str:
    return os.path.join(
        _photo_dir(request, snapshot_id),
        f'{index}{_LEGACY_PHOTO_EXTENSION}',
    )


def _resolve_photo_path(
    request: Request,
    snapshot_id: str,
    index: int,
) -> Tuple[str, str]:
    jpg_path = _photo_path(request, snapshot_id, index)
    if os.path.exists(jpg_path):
        return jpg_path, PHOTO_MEDIA_TYPE
    legacy_path = _legacy_photo_path(request, snapshot_id, index)
    if os.path.exists(legacy_path):
        return legacy_path, 'image/webp'
    raise HTTPException(status_code=404, detail='Photo not found')


def _count_photos(request: Request, snapshot_id: str) -> int:
    directory = _photo_dir(request, snapshot_id)
    if not os.path.isdir(directory):
        return 0
    indices = set()
    for name in os.listdir(directory):
        stem, ext = os.path.splitext(name)
        if (ext in (PHOTO_EXTENSION, _LEGACY_PHOTO_EXTENSION) and
                stem.isdigit()):
            indices.add(int(stem))
    return len(indices)


async def _sync_photo_count(request: Request, snapshot_id: str) -> int:
    count = _count_photos(request, snapshot_id)
    snapshots = await get_snapshots_col(request)
    try:
        await snapshots.update_one(
            {'_id': snapshot_id},
            {'$set': {'photo_count': count}},
        )
    except PyMongoError as exc:
        print(f'[ERROR] _sync_photo_count DB error: {exc}')
    return count


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
    doc = await _load_snapshot(request, snapshot_id)

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


@router.get(
    '/snapshots/{snapshot_id}/preview',
    summary='Rendered catalog preview (webp)',
)
async def get_snapshot_preview(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
):
    """Serve snapshot_previews/{snapshot_id}.webp only."""
    await _load_snapshot(request, snapshot_id)
    path = _resolve_preview_path(request, snapshot_id)
    return FileResponse(
        ensure_file(path),
        media_type='image/webp',
        filename=f'{snapshot_id}.webp',
    )


@router.get(
    '/snapshots/{snapshot_id}/photos/{index}',
    summary='Get user-uploaded photo for snapshot',
)
async def get_snapshot_photo(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
):
    await _load_snapshot(request, snapshot_id)
    path, media_type = _resolve_photo_path(request, snapshot_id, index)
    filename = os.path.basename(path)
    return FileResponse(
        ensure_file(path),
        media_type=media_type,
        filename=filename,
    )


@router.put(
    '/snapshots/{snapshot_id}/photos/{index}',
    summary='Upload or replace user photo for snapshot',
)
async def put_snapshot_photo(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
    photo: UploadFile = File(..., description='JPEG, PNG, or WebP image'),
):
    """
    Accept up to upload limit; store JPEG scaled/compressed to max output.
    """
    await _load_snapshot(request, snapshot_id)

    content_type = (photo.content_type or '').split(';', 1)[0].strip().lower()
    if content_type not in _ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                'Unsupported image type; allowed: '
                'image/jpeg, image/png, image/webp'
            ),
        )

    raw = await read_upload_limited(
        photo,
        request.app.snapshot_photo_upload_limit_bytes,
    )

    try:
        image = Image.open(io.BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid image file')

    directory = _photo_dir(request, snapshot_id)
    os.makedirs(directory, exist_ok=True)
    dest = _photo_path(request, snapshot_id, index)
    legacy = _legacy_photo_path(request, snapshot_id, index)

    try:
        size_bytes, width, height = compress_and_save_jpeg(
            image,
            dest,
            max_bytes=request.app.snapshot_photo_max_output_bytes,
            max_long_edge_px=request.app.snapshot_photo_max_long_edge_px,
        )
    except Exception as exc:
        print(f'[ERROR] put_snapshot_photo encode: {exc}')
        raise HTTPException(
            status_code=500,
            detail='Failed to process image',
        )

    if os.path.exists(legacy):
        try:
            os.remove(legacy)
        except OSError as exc:
            print(f'[WARN] put_snapshot_photo legacy remove: {exc}')

    count = await _sync_photo_count(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'photo_count': count,
            'format': 'jpeg',
            'size_bytes': size_bytes,
            'width': width,
            'height': height,
        },
    )


@router.delete(
    '/snapshots/{snapshot_id}/photos/{index}',
    summary='Delete user photo slot for snapshot',
)
async def delete_snapshot_photo(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
):
    await _load_snapshot(request, snapshot_id)

    removed = False
    for path in (
        _photo_path(request, snapshot_id, index),
        _legacy_photo_path(request, snapshot_id, index),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError as exc:
                print(f'[ERROR] delete_snapshot_photo: {exc}')
                raise HTTPException(
                    status_code=500,
                    detail='Failed to delete photo file',
                )

    if not removed:
        raise HTTPException(status_code=404, detail='Photo not found')

    count = await _sync_photo_count(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'photo_count': count,
        },
    )
