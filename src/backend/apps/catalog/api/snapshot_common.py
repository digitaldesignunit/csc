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
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response

from apps.catalog.models import User
from apps.catalog.geometry_mesh_export import (
    mesh_export_media_type,
    normalize_mesh_format,
)
from .auth import get_optional_current_user
from .catalog_common import get_snapshots_col, validate_uuid
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
