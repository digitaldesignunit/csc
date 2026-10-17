#!/usr/bin/env python3.13
"""
Proxies of a snapshot as meshes, and their deviation maps.

* `GET
    /snapshots/{snapshot_id}/proxies/{index}/mesh`
    -> prism proxy as a mesh (`?format=ply|obj`)
"""

import os
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from apps.catalog.geometry_mesh_export import (
    mesh_export_extension,
    trimesh_to_bytes,
)
from apps.catalog.proxies.primitives import proxy_mesh
from limiter import limiter, signed_in_or_ip
from .public_access import ensure_snapshot_read_access
from .catalog_common import not_modified_response
from logging_setup import get_logger
from .snapshot_common import (
    MESH_RATE,
    OptionalUser,
    _http_mesh_format,
    _mesh_export_attachment_response,
)


log = get_logger(__name__)

router = APIRouter()


def _proxy_mesh_bytes(proxy: dict, fmt: str) -> bytes:
    return trimesh_to_bytes(proxy_mesh(proxy), fmt)  # type: ignore[arg-type]


@router.get(
    '/snapshots/{snapshot_id}/proxies/{index}/mesh',
    summary='Export a proxy as a mesh (PLY or OBJ), in stored coordinates',
)
@limiter.limit(MESH_RATE, key_func=signed_in_or_ip)
async def get_snapshot_proxy_mesh(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    index: int,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """
    Triangulate ``geometry.proxies[index]`` (box, prism, cylinder or hull;
    Appendix B) and place it with its ``placement``, so the mesh lies in the
    snapshot's stored coordinates like the source geometry. OBJ is converted
    on the fly.
    """
    fmt = _http_mesh_format(format)
    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )
    proxies = (doc.get('geometry') or {}).get('proxies') or []
    if index < 0 or index >= len(proxies):
        raise HTTPException(status_code=404, detail='Proxy not found')
    try:
        body = await run_in_threadpool(_proxy_mesh_bytes, proxies[index], fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception('proxy export')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to export proxy as {fmt.upper()}',
        )

    file_ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_proxy_{index}.{file_ext}'
    return _mesh_export_attachment_response(body, filename, fmt)


@router.get(
    '/snapshots/{snapshot_id}/proxies/{index}/faces/{face}',
    summary='Deviation map of one proxy face (16-bit RGB PNG)',
)
async def get_snapshot_deviation_map(
    request: Request,
    current_user: OptionalUser,
    snapshot_id: str,
    index: int,
    face: str,
    if_none_match: Annotated[Optional[str], Header()] = None,
):
    """
    Channels (spec appendix B): R = distance (``value * scale_mm +
    offset_mm`` from ``deviation_maps.faces[face].distance``), G = normal
    deviation (hundredths of a degree), B = occupancy. The face must be
    listed in the proxy's ``deviation_maps``; nothing else is served.
    """
    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )
    proxies = (doc.get('geometry') or {}).get('proxies') or []
    faces = ((proxies[index].get('deviation_maps') or {}).get('faces')
             if 0 <= index < len(proxies) else None) or {}
    if face not in faces:
        raise HTTPException(status_code=404, detail='Deviation map not found')
    root = getattr(request.app, 'snapshot_proxies_dir', None)
    relative = faces[face]['file']
    if relative != f'proxies/{snapshot_id}/{index}/{face}.png':
        raise HTTPException(status_code=404, detail='Deviation map not found')
    path = os.path.normpath(os.path.join(root or '', *relative.split('/')[1:]))
    if not root \
            or not path.startswith(os.path.normpath(root) + os.sep) \
            or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='Deviation map not found')
    etag = f'"{doc.get("etag")}-{index}-{face}"'
    if if_none_match and if_none_match == etag:
        return not_modified_response(etag)
    return FileResponse(
        path, media_type='image/png',
        headers={'ETag': etag, 'Cache-Control': 'private, max-age=86400'})
