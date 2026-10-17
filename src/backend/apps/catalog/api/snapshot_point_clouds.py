#!/usr/bin/env python3.13
"""
Point cloud files of a snapshot.

* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/point_clouds/{index}.ply`
    -> PLY file (GET falls back to inline points when no file on disk)
"""

import asyncio
import hashlib
import os
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from utility import read_upload_limited
from apps.catalog.geometry_mesh_export import (
    export_inline_point_cloud_ply,
    get_inline_point_cloud_primitive,
)
from .auth import get_current_active_user
from .geometry_hooks import derive_sync
from .access import require_snapshot_file_write
from .public_access import ensure_snapshot_read_access
from .catalog_common import (
    compute_snapshot_etag,
    get_snapshots_col,
    not_modified_response,
    now_iso,
)
from logging_setup import get_logger
from .snapshot_common import (
    OptionalUser,
    _load_snapshot,
    _mesh_etag,
    _write_bytes,
)


log = get_logger(__name__)

router = APIRouter()


def _point_cloud_path(
    request: Request,
    snapshot_id: str,
    index: int,
) -> str:
    return os.path.join(
        request.app.snapshot_point_clouds_dir,
        snapshot_id,
        f'{index}.ply',
    )


async def _mark_point_cloud_file(
    request: Request,
    snapshot_id: str,
    index: int,
    present: bool,
) -> list:
    """
    Record that the full cloud of ``geometry.point_clouds[index]`` is (or no
    longer is) stored as a file in ``point_cloud_files``, and refresh the
    snapshot etag. Reads the stored document again (the upload took its time)
    and returns the sorted index list.
    """
    snapshot_doc = await _load_snapshot(request, snapshot_id)
    indices = {int(i) for i in snapshot_doc.get('point_cloud_files') or []}
    if present:
        indices.add(index)
    else:
        indices.discard(index)
    marked = sorted(indices)

    modified = now_iso()
    merged = dict(snapshot_doc)
    merged['point_cloud_files'] = marked
    merged['lastmodified'] = modified
    etag = compute_snapshot_etag(merged)

    snapshots = await get_snapshots_col(request)
    try:
        await snapshots.update_one(
            {'_id': snapshot_id},
            {'$set': {
                'point_cloud_files': marked,
                'lastmodified': modified,
                'etag': etag,
            }},
        )
    except PyMongoError:
        log.exception('_mark_point_cloud_file DB error')
        raise HTTPException(
            status_code=500,
            detail='Failed to update snapshot point cloud manifest',
        )
    return marked


@router.get(
    '/snapshots/{snapshot_id}/point_clouds/{index}.ply',
    summary=(
        'Get point cloud PLY (file on disk or '
        'generated from inline points)'
    )
)
async def get_snapshot_point_cloud_ply(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    index: int,
):
    """
    Serve ``point_clouds/<snapshot_id>/<index>.ply`` when present; otherwise
    build PLY from ``geometry.point_clouds[index]`` inline points.
    """
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')

    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )
    path = _point_cloud_path(request, snapshot_id, index)
    filename = f'{snapshot_id}_point_cloud_{index}.ply'
    if_none_match = request.headers.get('if-none-match')

    if os.path.isfile(path):
        etag = _mesh_etag(path)
        if if_none_match and if_none_match == etag:
            return not_modified_response(etag)
        return FileResponse(
            path,
            media_type='model/ply',
            filename=filename,
            headers={
                'ETag': etag,
                'Cache-Control': 'private, max-age=86400',
                'Content-Disposition': f'attachment; filename="{filename}"',
            },
        )

    try:
        pc = get_inline_point_cloud_primitive(doc, index)
        ply_bytes = await run_in_threadpool(export_inline_point_cloud_ply, pc)
    except IndexError:
        raise HTTPException(status_code=404, detail='Point cloud not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception('point cloud PLY export')
        raise HTTPException(
            status_code=500,
            detail='Failed to export point cloud as PLY',
        )

    etag = doc.get('etag') or hashlib.sha256(ply_bytes).hexdigest()[:32]
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag)
    return Response(
        content=ply_bytes,
        media_type='model/ply',
        headers={
            'ETag': etag,
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'private, max-age=3600',
        },
    )


@router.put(
    '/snapshots/{snapshot_id}/point_clouds/{index}.ply',
    summary='Upload point cloud PLY for snapshot primitive',
)
async def put_snapshot_point_cloud_ply(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
    point_cloud_file: UploadFile = File(
        ...,
        description='Binary PLY point cloud file',
    ),
):
    """
    Store ``point_clouds/<snapshot_id>/<index>.ply``.

    ``index`` must match an entry in ``geometry.point_clouds``.
    """
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')

    filename = (point_cloud_file.filename or '').lower()
    if not filename.endswith('.ply'):
        raise HTTPException(
            status_code=400,
            detail='Point cloud file must be a .ply file',
        )

    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'upload_geometry',
        frozen_when_published=True)
    point_clouds = (doc.get('geometry') or {}).get('point_clouds') or []
    if index >= len(point_clouds):
        raise HTTPException(
            status_code=400,
            detail=(
                f'index {index} out of range; snapshot has '
                f'{len(point_clouds)} point cloud primitive(s)'
            ),
        )

    raw = await read_upload_limited(
        point_cloud_file,
        request.app.geometry_upload_limit_bytes,
    )
    if len(raw) < 3 or raw[:3] != b'ply':
        raise HTTPException(
            status_code=400,
            detail='Invalid PLY file (expected ASCII or binary PLY header)',
        )

    dest_dir = os.path.join(
        request.app.snapshot_point_clouds_dir,
        snapshot_id,
    )
    os.makedirs(dest_dir, exist_ok=True)
    dest = _point_cloud_path(request, snapshot_id, index)

    try:
        await asyncio.to_thread(_write_bytes, dest, raw)
    except OSError:
        log.exception('put_snapshot_point_cloud_ply write')
        raise HTTPException(
            status_code=500,
            detail='Failed to save point cloud file',
        )

    marked = await _mark_point_cloud_file(
        request, snapshot_id, index, True)

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'size_bytes': len(raw),
            'point_cloud_files': marked,
        },
    )


@router.delete(
    '/snapshots/{snapshot_id}/point_clouds/{index}.ply',
    summary='Delete on-disk point cloud PLY for snapshot primitive',
)
async def delete_snapshot_point_cloud_ply(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
):
    """Remove ``point_clouds/<snapshot_id>/<index>.ply`` when present."""
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')

    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'delete_geometry',
        frozen_when_published=True)
    point_clouds = (doc.get('geometry') or {}).get('point_clouds') or []
    if index >= len(point_clouds):
        raise HTTPException(
            status_code=400,
            detail=(
                f'index {index} out of range; snapshot has '
                f'{len(point_clouds)} point cloud primitive(s)'
            ),
        )

    path = _point_cloud_path(request, snapshot_id, index)

    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail='Point cloud file not found'
        )

    try:
        os.remove(path)
    except OSError:
        log.exception('delete_snapshot_point_cloud_ply')
        raise HTTPException(
            status_code=500,
            detail='Failed to delete point cloud file',
        )

    marked = await _mark_point_cloud_file(
        request, snapshot_id, index, False)

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'ok': True,
            'point_cloud_files': marked,
        },
    )
