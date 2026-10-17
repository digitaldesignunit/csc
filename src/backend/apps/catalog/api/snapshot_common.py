#!/usr/bin/env python3.13
"""
Helpers that the snapshot route modules share: the snapshot loader, the
cleanup of a snapshot's files on disk, the file ETag, the byte writer and the
parts of the mesh downloads that meshes and proxies both use.
"""

import hashlib
import os
import shutil
import stat
from typing import Annotated, Any, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from apps.catalog.geometry_mesh_export import (
    mesh_export_media_type,
    normalize_mesh_format,
)
from .auth import get_optional_current_user
from .catalog_common import (
    compute_snapshot_etag,
    get_snapshots_col,
    now_iso,
)
from logging_setup import get_logger


log = get_logger(__name__)


# Mesh downloads convert on the fly (OBJ) or read the file: CPU and memory
# work any anonymous caller can ask for on a public piece (S5, 8.144). Per
# user for a signed-in caller, per client address otherwise (limiter.py); the
# viewer loads a handful of files per piece, so the limit is generous. The OBJ
# conversion of a PLY above the size cap is refused: the PLY itself is served.
MESH_LIMIT_PER_MINUTE = 120
MESH_RATE = f'{MESH_LIMIT_PER_MINUTE}/minute'


OptionalUser = Annotated[Optional[User], Depends(get_optional_current_user)]


def _delete_snapshot_disk_assets(request: Request, snapshot_id: str) -> None:
    """Best-effort cleanup of on-disk assets for one snapshot."""
    preview_path = os.path.join(
        request.app.snapshot_preview_dir,
        f'{snapshot_id}.webp',
    )
    if os.path.exists(preview_path):
        try:
            os.remove(preview_path)
        except OSError:
            log.warning('delete snapshot preview %s', snapshot_id,
                        exc_info=True)

    for parent in (
        request.app.snapshot_photos_dir,
        request.app.snapshot_meshes_dir,
        request.app.snapshot_point_clouds_dir,
    ):
        target = os.path.join(parent, snapshot_id)
        if os.path.isdir(target):
            try:
                shutil.rmtree(target)
            except OSError:
                log.warning('delete snapshot assets %s', target,
                            exc_info=True)


def _mesh_etag(path: str) -> str:
    st = os.stat(path)
    raw = f'{st[stat.ST_MTIME]}-{st[stat.ST_SIZE]}'
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _mesh_export_attachment_response(
    content: bytes,
    filename: str,
    fmt: str,
) -> Response:
    return Response(
        content=content,
        media_type=mesh_export_media_type(fmt),  # type: ignore[arg-type]
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'private, max-age=3600',
        },
    )


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, 'wb') as handle:
        handle.write(data)


def _http_mesh_format(format: str) -> str:
    try:
        return normalize_mesh_format(format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def mark_file(request: Request, snapshot_id: str, field: str,
                    value: Any, *, present: bool, key: Optional[str] = None,
                    descending: bool = False) -> Any:
    """Record that a file is (or no longer is) stored, in the marker list
    ``field`` (``key``: the list under that key of a map, like
    ``mesh_ply_resolutions.<index>``), and refresh ``lastmodified`` and the
    etag. One atomic update of just that list (``$push`` guarded against a
    duplicate and sorted, or ``$pull``; an emptied key of a map is unset), so
    two uploads at once cannot overwrite each other's marker. Returns the
    marker as stored: the list, or the whole map. A repeated upload of a file
    that is marked already changes nothing: ``lastmodified`` and the etag stay
    as they are (the snapshot etag never covered file bytes; the file routes
    have their own ETag).
    """
    snapshots = await get_snapshots_col(request)
    path = field if key is None else f'{field}.{key}'
    now = now_iso()
    try:
        if present:
            doc = await snapshots.find_one_and_update(
                {'_id': snapshot_id, path: {'$ne': value}},
                {'$push': {path: {'$each': [value],
                                  '$sort': -1 if descending else 1}},
                 '$set': {'lastmodified': now}},
                return_document=ReturnDocument.AFTER)
        else:
            doc = await snapshots.find_one_and_update(
                {'_id': snapshot_id},
                {'$pull': {path: value}, '$set': {'lastmodified': now}},
                return_document=ReturnDocument.AFTER)
        if doc is None:
            # the value is in the list already, or the snapshot is gone
            doc = await snapshots.find_one({'_id': snapshot_id})
            if doc is None:
                raise HTTPException(status_code=404,
                                    detail='Snapshot not found')
            return doc.get(field)
        if not present and key is not None and \
                doc.get(field, {}).get(key) == []:
            await snapshots.update_one({'_id': snapshot_id, path: {'$size': 0}},
                                       {'$unset': {path: ''}})
            doc[field].pop(key, None)
        # the etag follows the content; a write that came in between has
        # its own etag, which covers this marker as well
        await snapshots.update_one(
            {'_id': snapshot_id, 'lastmodified': now},
            {'$set': {'etag': compute_snapshot_etag(doc)}})
    except PyMongoError:
        log.exception('file marker %s of snapshot %s', field, snapshot_id)
        raise HTTPException(
            status_code=500,
            detail='Failed to update the snapshot file manifest')
    return doc.get(field)
