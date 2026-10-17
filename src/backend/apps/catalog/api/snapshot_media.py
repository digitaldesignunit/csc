#!/usr/bin/env python3.13
"""
Photos, the preview image and the capture fixtures of a snapshot.

* `GET
    /snapshots/{snapshot_id}/preview`
    -> rendered catalog thumbnail
* `GET
    /snapshots/{snapshot_id}/photos`
    -> list occupied photo slot indices (no per-slot probing)
* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/photos/{index}`
    -> user photos (JPEG)
"""

import asyncio
import os
from typing import Annotated, List, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from utility import ensure_file, read_upload_limited
from .auth import get_current_active_user
from .access import load_snapshot
from .catalog_common import get_snapshots_col, not_modified_response
from .snapshot_images import (
    PHOTO_EXTENSION,
    PHOTO_MEDIA_TYPE,
    ImageTooLarge,
    UnreadableImage,
    compress_and_save_jpeg,
    open_upload_photo,
    photo_filename,
)
from logging_setup import get_logger
from .snapshot_common import OptionalUser, _mesh_etag


log = get_logger(__name__)

router = APIRouter()


_ALLOWED_PHOTO_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/webp',
})


_LEGACY_PHOTO_EXTENSION = '.webp'


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


def _list_photo_indices(request: Request, snapshot_id: str) -> List[int]:
    directory = _photo_dir(request, snapshot_id)
    if not os.path.isdir(directory):
        return []
    indices: set[int] = set()
    for name in os.listdir(directory):
        stem, ext = os.path.splitext(name)
        if (ext in (PHOTO_EXTENSION, _LEGACY_PHOTO_EXTENSION) and
                stem.isdigit()):
            indices.add(int(stem))
    return sorted(indices)


def _count_photos(request: Request, snapshot_id: str) -> int:
    return len(_list_photo_indices(request, snapshot_id))


async def refresh_snapshot_photo_count(
    request: Request,
    snapshot_id: str,
    snapshot_doc=None,
) -> int:
    """Count photos on disk; update Mongo and optional in-memory doc."""
    count = _count_photos(request, snapshot_id)
    snapshots = await get_snapshots_col(request)
    try:
        await snapshots.update_one(
            {'_id': snapshot_id},
            {'$set': {'photo_count': count}},
        )
    except PyMongoError:
        log.exception('refresh_snapshot_photo_count DB error')
    if snapshot_doc is not None:
        snapshot_doc['photo_count'] = count
    return count


async def _sync_photo_count(request: Request, snapshot_id: str) -> int:
    return await refresh_snapshot_photo_count(request, snapshot_id)


@router.get(
    '/snapshots/{snapshot_id}/capture/fixtures/{index}.ply',
    summary='Capture fixture mesh (e.g. the robot gripper; decision 7.7)',
)
async def get_snapshot_capture_fixture(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    index: int,
):
    """
    Serve ``capture.fixtures[index].file`` (``capture/<snapshot_id>/
    fixtures/<i>.ply`` under ``SNAPSHOT_CAPTURE_DIR``). Fixtures are capture
    context, never the component: no derivation reads them.
    """
    doc = (await load_snapshot(request, current_user, snapshot_id)).record
    fixtures = ((doc.get('capture') or {}).get('fixtures')) or []
    if index < 0 or index >= len(fixtures):
        raise HTTPException(status_code=404, detail='Fixture not found')
    root = getattr(request.app, 'snapshot_capture_dir', None)
    relative = str(fixtures[index].get('file') or '')
    if relative.startswith('capture/'):
        relative = relative[len('capture/'):]
    path = os.path.normpath(os.path.join(root, relative)) if root else ''
    if not root \
            or not path.startswith(os.path.normpath(root) + os.sep) \
            or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='Fixture file not found')
    etag = _mesh_etag(path)
    if request.headers.get('if-none-match') == etag:
        return not_modified_response(etag)
    filename = f'{snapshot_id}_fixture_{index}.ply'
    return FileResponse(
        path,
        media_type='model/ply',
        filename=filename,
        headers={
            'ETag': etag,
            'Cache-Control': 'private, max-age=86400',
        },
    )


@router.get(
    '/snapshots/{snapshot_id}/preview',
    summary='Rendered catalog preview (webp)',
)
async def get_snapshot_preview(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
):
    """Serve snapshot_previews/{snapshot_id}.webp only."""
    await load_snapshot(request, current_user, snapshot_id)
    path = _resolve_preview_path(request, snapshot_id)
    return FileResponse(
        ensure_file(path),
        media_type='image/webp',
        filename=f'{snapshot_id}.webp',
    )


@router.get(
    '/snapshots/{snapshot_id}/photos',
    summary='List occupied photo slot indices for a snapshot',
)
async def list_snapshot_photos(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
):
    """Return sorted slot indices and count from disk (one directory read)."""
    await load_snapshot(request, current_user, snapshot_id)
    indices = _list_photo_indices(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={'indices': indices, 'count': len(indices)},
    )


@router.get(
    '/snapshots/{snapshot_id}/photos/{index}',
    summary='Get user-uploaded photo for snapshot',
)
async def get_snapshot_photo(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    index: int,
):
    await load_snapshot(request, current_user, snapshot_id)
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
    await load_snapshot(
        request, current_user, snapshot_id, 'add_photo', files=True,
        frozen=False)

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

    # decoding and encoding are CPU work: off the event loop, as the evidence
    # path does (S5); sniffed and size-checked before any pixel is decoded (S6)
    try:
        image = await asyncio.to_thread(open_upload_photo, raw)
    except ImageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UnreadableImage:
        raise HTTPException(status_code=400, detail='Invalid image file')
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid image file')

    directory = _photo_dir(request, snapshot_id)
    os.makedirs(directory, exist_ok=True)
    dest = _photo_path(request, snapshot_id, index)
    legacy = _legacy_photo_path(request, snapshot_id, index)

    try:
        size_bytes, width, height = await asyncio.to_thread(
            compress_and_save_jpeg,
            image,
            dest,
            max_bytes=request.app.snapshot_photo_max_output_bytes,
            max_long_edge_px=request.app.snapshot_photo_max_long_edge_px,
        )
    except Exception:
        log.exception('put_snapshot_photo encode')
        raise HTTPException(
            status_code=500,
            detail='Failed to process image',
        )

    if os.path.exists(legacy):
        try:
            os.remove(legacy)
        except OSError:
            log.warning('put_snapshot_photo legacy remove', exc_info=True)

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
    await load_snapshot(
        request, current_user, snapshot_id, 'delete_photo', files=True,
        frozen=False)

    removed = False
    for path in (
        _photo_path(request, snapshot_id, index),
        _legacy_photo_path(request, snapshot_id, index),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
                removed = True
            except OSError:
                log.exception('delete_snapshot_photo')
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
