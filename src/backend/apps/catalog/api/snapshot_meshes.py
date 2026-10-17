#!/usr/bin/env python3.13
"""
Mesh files of a snapshot.

* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}`
    -> reduced / original mesh file, stored as `reduced.ply` /
    `detailed.ply` (GET supports `?format=obj`; DELETE clears disk +
    manifest)
* `GET
    /snapshots/{snapshot_id}/meshes/{primitive_index}/preview`
    -> the preview: the inline mesh (`?format=ply|obj`; decision 8.23;
    `/primitive` is an alias until P5)
"""

import asyncio
import os
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

from apps.catalog.models import User
from utility import read_upload_limited
from apps.catalog.geometry_mesh_export import (
    export_inline_mesh,
    export_mesh_file,
    get_inline_mesh_primitive,
    mesh_export_extension,
)
from .auth import get_current_active_user
from limiter import limiter, signed_in_or_ip
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
    MESH_RATE,
    OptionalUser,
    _http_mesh_format,
    _load_snapshot,
    _mesh_etag,
    _mesh_export_attachment_response,
    _write_bytes,
)


log = get_logger(__name__)

router = APIRouter()


OBJ_CONVERSION_MAX_BYTES = 50 * 1024 * 1024


_ALLOWED_RESOLUTIONS = frozenset({'reduced', 'detailed'})


def _mesh_path(
    request: Request,
    snapshot_id: str,
    primitive_index: int,
    resolution: str,
) -> str:
    return os.path.join(
        request.app.snapshot_meshes_dir,
        snapshot_id,
        str(primitive_index),
        f'{resolution}.ply',
    )


@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/preview',
    summary='Export the mesh preview stored in the snapshot (PLY or OBJ)',
)
@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/primitive',
    summary='Alias of .../preview until plan P5 (decision 8.23)',
    deprecated=True,
)
@limiter.limit(MESH_RATE, key_func=signed_in_or_ip)
async def get_snapshot_mesh_preview(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    primitive_index: int,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """
    The preview (decision 8.23): ``geometry.meshes[primitive_index]`` as
    a file; OBJ is converted on the fly.
    """
    fmt = _http_mesh_format(format)
    if primitive_index < 0:
        raise HTTPException(
            status_code=400,
            detail='primitive_index must be >= 0',
        )
    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )
    try:
        mesh = get_inline_mesh_primitive(doc, primitive_index)
        body = await run_in_threadpool(export_inline_mesh, mesh, fmt)  # type: ignore[arg-type]
    except IndexError:
        raise HTTPException(status_code=404, detail='Mesh preview not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception('mesh preview export')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to export mesh preview as {fmt.upper()}',
        )

    ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_mesh_{primitive_index}_preview.{ext}'
    return _mesh_export_attachment_response(body, filename, fmt)


@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}',
    summary='Get mesh file for snapshot primitive (PLY or OBJ)',
)
@limiter.limit(MESH_RATE, key_func=signed_in_or_ip)
async def get_snapshot_mesh(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    primitive_index: int,
    resolution: str,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """
    Serve ``meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply``.

    ``?format=obj`` converts the on-disk PLY to OBJ
    at request time (no duplicate files).

    Returns 404 when the file is not on disk or ``mesh_ply_resolutions``
    does not list the requested resolution for this primitive index.
    """
    fmt = _http_mesh_format(format)
    if primitive_index < 0:
        raise HTTPException(
            status_code=400,
            detail='primitive_index must be >= 0'
        )
    if resolution not in _ALLOWED_RESOLUTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f'resolution must be one of: {sorted(_ALLOWED_RESOLUTIONS)}'
            )
        )

    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )

    resolutions_map: dict = doc.get('mesh_ply_resolutions') or {}
    key = str(primitive_index)
    available = resolutions_map.get(key) or []
    if resolution not in available:
        raise HTTPException(
            status_code=404,
            detail=(
                f'No {resolution} PLY for primitive {primitive_index} '
                f'on snapshot {snapshot_id}'
            ),
        )

    path = _mesh_path(request, snapshot_id, primitive_index, resolution)
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail='PLY file not found on disk',
        )

    ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_{primitive_index}_{resolution}.{ext}'

    if fmt == 'ply':
        etag = _mesh_etag(path)
        if_none_match = request.headers.get('if-none-match')
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

    if os.path.getsize(path) > OBJ_CONVERSION_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail='This mesh is too large to convert to OBJ; '
                   'download the PLY.',
        )
    try:
        body = await run_in_threadpool(
            export_mesh_file, path, fmt)  # type: ignore[arg-type]
    except ValueError:
        # the parser's text can name the file: the log only
        log.exception('mesh file OBJ conversion')
        raise HTTPException(
            status_code=400,
            detail='The mesh file could not be converted to OBJ',
        )
    except Exception:
        log.exception('mesh file OBJ conversion')
        raise HTTPException(
            status_code=500,
            detail='Failed to convert mesh file to OBJ',
        )
    return _mesh_export_attachment_response(body, filename, fmt)


async def _register_mesh_ply_resolution(
    request: Request,
    snapshot_id: str,
    snapshot_doc: dict,
    primitive_index: int,
    resolution: str,
) -> dict:
    """
    Record one on-disk PLY resolution and refresh snapshot etag.
    """
    key = str(primitive_index)
    resolutions_map = dict(snapshot_doc.get('mesh_ply_resolutions') or {})
    current = list(resolutions_map.get(key) or [])
    if resolution not in current:
        current.append(resolution)
    order = {'reduced': 0, 'detailed': 1}
    current.sort(key=lambda r: order.get(r, 99))
    resolutions_map[key] = current

    modified = now_iso()
    merged = dict(snapshot_doc)
    merged['mesh_ply_resolutions'] = resolutions_map
    merged['lastmodified'] = modified
    etag = compute_snapshot_etag(merged)

    snapshots = await get_snapshots_col(request)
    try:
        await snapshots.update_one(
            {'_id': snapshot_id},
            {'$set': {
                'mesh_ply_resolutions': resolutions_map,
                'lastmodified': modified,
                'etag': etag,
            }},
        )
    except PyMongoError:
        log.exception('_register_mesh_ply_resolution DB error')
        raise HTTPException(
            status_code=500,
            detail='Failed to update snapshot mesh manifest',
        )

    return resolutions_map


async def _unregister_mesh_ply_resolution(
    request: Request,
    snapshot_id: str,
    snapshot_doc: dict,
    primitive_index: int,
    resolution: str,
) -> dict:
    """
    Remove one on-disk PLY resolution from the manifest and refresh etag.
    """
    key = str(primitive_index)
    resolutions_map = dict(snapshot_doc.get('mesh_ply_resolutions') or {})
    current = list(resolutions_map.get(key) or [])
    if resolution in current:
        current = [item for item in current if item != resolution]
    if current:
        resolutions_map[key] = current
    else:
        resolutions_map.pop(key, None)

    modified = now_iso()
    merged = dict(snapshot_doc)
    merged['mesh_ply_resolutions'] = resolutions_map
    merged['lastmodified'] = modified
    etag = compute_snapshot_etag(merged)

    snapshots = await get_snapshots_col(request)
    try:
        await snapshots.update_one(
            {'_id': snapshot_id},
            {'$set': {
                'mesh_ply_resolutions': resolutions_map,
                'lastmodified': modified,
                'etag': etag,
            }},
        )
    except PyMongoError:
        log.exception('_unregister_mesh_ply_resolution DB error')
        raise HTTPException(
            status_code=500,
            detail='Failed to update snapshot mesh manifest',
        )

    return resolutions_map


@router.put(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}',
    summary='Upload or replace mesh PLY for snapshot primitive',
)
async def put_snapshot_mesh_ply(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    primitive_index: int,
    resolution: str,
    mesh_file: UploadFile = File(..., description='Binary PLY mesh file'),
):
    """
    Store ``meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply``
    and register the resolution on ``mesh_ply_resolutions``.
    """
    if primitive_index < 0:
        raise HTTPException(
            status_code=400,
            detail='primitive_index must be >= 0',
        )
    if resolution not in _ALLOWED_RESOLUTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f'resolution must be one of: {sorted(_ALLOWED_RESOLUTIONS)}'
            ),
        )

    filename = (mesh_file.filename or '').lower()
    if not filename.endswith('.ply'):
        raise HTTPException(
            status_code=400,
            detail='Mesh file must be a .ply file',
        )

    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'upload_geometry',
        frozen_when_published=True)
    meshes = (doc.get('geometry') or {}).get('meshes') or []
    if primitive_index >= len(meshes):
        raise HTTPException(
            status_code=400,
            detail=(
                f'primitive_index {primitive_index} out of range; '
                f'snapshot has {len(meshes)} mesh primitive(s)'
            ),
        )

    raw = await read_upload_limited(
        mesh_file,
        request.app.geometry_upload_limit_bytes,
    )
    if len(raw) < 3 or raw[:3] != b'ply':
        raise HTTPException(
            status_code=400,
            detail='Invalid PLY file (expected ASCII or binary PLY header)',
        )

    dest_dir = os.path.join(
        request.app.snapshot_meshes_dir,
        snapshot_id,
        str(primitive_index),
    )
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f'{resolution}.ply')

    try:
        await asyncio.to_thread(_write_bytes, dest, raw)
    except OSError:
        log.exception('put_snapshot_mesh_ply write')
        raise HTTPException(
            status_code=500,
            detail='Failed to save mesh file',
        )

    resolutions_map = await _register_mesh_ply_resolution(
        request,
        snapshot_id,
        doc,
        primitive_index,
        resolution,
    )

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'primitive_index': primitive_index,
            'resolution': resolution,
            'size_bytes': len(raw),
            'mesh_ply_resolutions': resolutions_map,
        },
    )


@router.delete(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}',
    summary='Delete mesh PLY for snapshot primitive',
)
async def delete_snapshot_mesh_ply(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    primitive_index: int,
    resolution: str,
):
    """
    Remove ``meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply``
    and drop the resolution from ``mesh_ply_resolutions`` when listed.
    """
    if primitive_index < 0:
        raise HTTPException(
            status_code=400,
            detail='primitive_index must be >= 0',
        )
    if resolution not in _ALLOWED_RESOLUTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f'resolution must be one of: {sorted(_ALLOWED_RESOLUTIONS)}'
            ),
        )

    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'delete_geometry',
        frozen_when_published=True)
    meshes = (doc.get('geometry') or {}).get('meshes') or []
    if primitive_index >= len(meshes):
        raise HTTPException(
            status_code=400,
            detail=(
                f'primitive_index {primitive_index} out of range; '
                f'snapshot has {len(meshes)} mesh primitive(s)'
            ),
        )

    path = _mesh_path(request, snapshot_id, primitive_index, resolution)
    resolutions_map: dict = doc.get('mesh_ply_resolutions') or {}
    key = str(primitive_index)
    in_manifest = resolution in (resolutions_map.get(key) or [])
    on_disk = os.path.isfile(path)

    if not in_manifest and not on_disk:
        raise HTTPException(status_code=404, detail='Mesh PLY not found')

    if on_disk:
        try:
            os.remove(path)
        except OSError:
            log.exception('delete_snapshot_mesh_ply')
            raise HTTPException(
                status_code=500,
                detail='Failed to delete mesh file',
            )

    if in_manifest:
        resolutions_map = await _unregister_mesh_ply_resolution(
            request,
            snapshot_id,
            doc,
            primitive_index,
            resolution,
        )

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'primitive_index': primitive_index,
            'resolution': resolution,
            'mesh_ply_resolutions': resolutions_map,
            'ok': True,
        },
    )
