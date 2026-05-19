#!/usr/bin/env python3.9
"""
Routes for the v0.5 `component_snapshots` collection.

* `GET /snapshots/{snapshot_id}` - fetch one snapshot by id (ADR-014 #3)
* `GET /snapshots/{snapshot_id}/preview` - rendered catalog thumbnail
* `GET /snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}` - PLY file or OBJ (`?format=obj`)
* `GET /snapshots/{snapshot_id}/meshes/{primitive_index}/primitive` - inline mesh (`?format=ply|obj`)
* `GET /snapshots/{snapshot_id}/extrusions/{index}` - inline extrusion mesh (`?format=ply|obj`)
* `GET /snapshots/{snapshot_id}/point_clouds/{index}.ply` - file or inline → PLY
* `GET|PUT|DELETE /snapshots/{snapshot_id}/photos/{index}` - user photos (JPEG)
"""

import hashlib
import io
import os
import stat
from typing import Annotated, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image
from pymongo.errors import PyMongoError

from apps.catalog.models import ComponentSnapshot, User
from utility import ensure_file, read_upload_limited

from apps.catalog.geometry_mesh_export import (
    export_extrusion,
    export_inline_mesh,
    export_inline_point_cloud_ply,
    export_mesh_file,
    get_inline_extrusion_primitive,
    get_inline_mesh_primitive,
    get_inline_point_cloud_primitive,
    mesh_export_extension,
    mesh_export_media_type,
    normalize_mesh_format,
)

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

_ALLOWED_RESOLUTIONS = frozenset({'reduced', 'detailed'})

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


def _mesh_etag(path: str) -> str:
    st = os.stat(path)
    raw = f'{st[stat.ST_MTIME]}-{st[stat.ST_SIZE]}'
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


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


def _http_mesh_format(format: str) -> str:
    try:
        return normalize_mesh_format(format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/primitive',
    summary='Export inline mesh primitive (PLY or OBJ)',
)
async def get_snapshot_mesh_primitive(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    primitive_index: int,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """Build mesh from ``geometry.meshes[primitive_index]``; OBJ is converted on the fly."""
    fmt = _http_mesh_format(format)
    if primitive_index < 0:
        raise HTTPException(
            status_code=400,
            detail='primitive_index must be >= 0',
        )
    doc = await _load_snapshot(request, snapshot_id)
    try:
        mesh = get_inline_mesh_primitive(doc, primitive_index)
        body = export_inline_mesh(mesh, fmt)  # type: ignore[arg-type]
    except IndexError:
        raise HTTPException(status_code=404, detail='Mesh primitive not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] mesh primitive export ({fmt}): {exc}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to export mesh primitive as {fmt.upper()}',
        )

    ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_mesh_{primitive_index}_primitive.{ext}'
    return _mesh_export_attachment_response(body, filename, fmt)


@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}',
    summary='Get mesh file for snapshot primitive (PLY or OBJ)',
)
async def get_snapshot_mesh(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    primitive_index: int,
    resolution: str,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """
    Serve ``meshes/<snapshot_id>/<primitive_index>/{reduced|detailed}.ply``.

    ``?format=obj`` converts the on-disk PLY to OBJ at request time (no duplicate files).

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

    doc = await _load_snapshot(request, snapshot_id)

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
            detail=f'PLY file not found on disk: {path}',
        )

    ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_{primitive_index}_{resolution}.{ext}'

    if fmt == 'ply':
        etag = _mesh_etag(path)
        if_none_match = request.headers.get('if-none-match')
        if if_none_match and if_none_match == etag:
            from fastapi.responses import Response
            return Response(
                status_code=304,
                headers={'ETag': etag},
            )
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
        body = export_mesh_file(path, fmt)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] mesh file OBJ conversion: {exc}')
        raise HTTPException(
            status_code=500,
            detail='Failed to convert mesh file to OBJ',
        )
    return _mesh_export_attachment_response(body, filename, fmt)


@router.get(
    '/snapshots/{snapshot_id}/extrusions/{index}',
    summary='Export inline extrusion primitive (PLY or OBJ mesh)',
)
async def get_snapshot_extrusion(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
    format: str = Query('ply', description='ply (default) or obj'),
):
    """Triangulate ``geometry.extrusions[index]``; OBJ is converted on the fly."""
    fmt = _http_mesh_format(format)
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')
    doc = await _load_snapshot(request, snapshot_id)
    try:
        ext = get_inline_extrusion_primitive(doc, index)
        body = export_extrusion(ext, fmt)  # type: ignore[arg-type]
    except IndexError:
        raise HTTPException(status_code=404, detail='Extrusion primitive not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] extrusion export ({fmt}): {exc}')
        raise HTTPException(
            status_code=500,
            detail=f'Failed to export extrusion as {fmt.upper()}',
        )

    file_ext = mesh_export_extension(fmt)  # type: ignore[arg-type]
    filename = f'{snapshot_id}_extrusion_{index}.{file_ext}'
    return _mesh_export_attachment_response(body, filename, fmt)


@router.get(
    '/snapshots/{snapshot_id}/point_clouds/{index}.ply',
    summary='Get point cloud PLY (file on disk or generated from inline points)',
)
async def get_snapshot_point_cloud_ply(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    snapshot_id: str,
    index: int,
):
    """
    Serve ``point_clouds/<snapshot_id>/<index>.ply`` when present; otherwise
    build PLY from ``geometry.point_clouds[index]`` inline points.
    """
    if index < 0:
        raise HTTPException(status_code=400, detail='index must be >= 0')

    doc = await _load_snapshot(request, snapshot_id)
    path = _point_cloud_path(request, snapshot_id, index)
    filename = f'{snapshot_id}_point_cloud_{index}.ply'

    if os.path.isfile(path):
        return FileResponse(
            path,
            media_type='model/ply',
            filename=filename,
            headers={
                'Cache-Control': 'private, max-age=86400',
                'Content-Disposition': f'attachment; filename="{filename}"',
            },
        )

    try:
        pc = get_inline_point_cloud_primitive(doc, index)
        ply_bytes = export_inline_point_cloud_ply(pc)
    except IndexError:
        raise HTTPException(status_code=404, detail='Point cloud not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] point cloud PLY export: {exc}')
        raise HTTPException(
            status_code=500,
            detail='Failed to export point cloud as PLY',
        )

    return _mesh_export_attachment_response(ply_bytes, filename, 'ply')


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
