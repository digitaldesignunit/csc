#!/usr/bin/env python3.13
"""
Routes for the v0.5 `component_snapshots` collection.

* `GET
    /snapshots/pending-validation`
    -> admin queue of unvalidated snapshots
* `POST
    /snapshots/{snapshot_id}/validate`
    -> admin validate + promote to live
* `DELETE
    /snapshots/{snapshot_id}`
    -> admin reject / discard a pending (unvalidated) snapshot
* `GET
    /snapshots/{snapshot_id}`
    -> fetch one snapshot by id (ADR-014 #3)
* `GET
    /snapshots/{snapshot_id}/preview`
    -> rendered catalog thumbnail
* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/meshes/{primitive_index}/{resolution}`
    -> reduced / original mesh file, stored as `reduced.ply` /
    `detailed.ply` (GET supports `?format=obj`; DELETE clears disk +
    manifest)
* `GET
    /snapshots/{snapshot_id}/meshes/{primitive_index}/preview`
    -> the preview: the inline mesh (`?format=ply|obj`; decision 8.23;
    `/primitive` is an alias until P5)
* `GET
    /snapshots/{snapshot_id}/proxies/{index}/mesh`
    -> prism proxy as a mesh (`?format=ply|obj`)
* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/point_clouds/{index}.ply`
    -> PLY file (GET falls back to inline points when no file on disk)
* `GET
    /snapshots/{snapshot_id}/photos`
    -> list occupied photo slot indices (no per-slot probing)
* `GET|PUT|DELETE
    /snapshots/{snapshot_id}/photos/{index}`
    -> user photos (JPEG)
"""

import hashlib
import os
import shutil
import stat
from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, Response
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
from utility import ensure_file, read_upload_limited

from apps.catalog.geometry_mesh_export import (
    export_inline_mesh,
    export_inline_point_cloud_ply,
    export_mesh_file,
    get_inline_mesh_primitive,
    get_inline_point_cloud_primitive,
    mesh_export_extension,
    mesh_export_media_type,
    normalize_mesh_format,
    trimesh_to_bytes,
)
from apps.catalog.proxies.primitives import proxy_mesh

from .auth import get_current_active_user, get_optional_current_user
from .geometry_hooks import derive_sync
from .access import load_datasets, require_snapshot_file_write, viewer_of
from .public_access import (
    ensure_snapshot_read_access,
    viewer_etag,
    viewer_headers,
)
from .catalog_common import (
    compute_snapshot_etag,
    get_identities_col,
    get_snapshots_col,
    not_modified_response,
    now_iso,
    validate_uuid,
)
from .snapshot_images import (
    PHOTO_EXTENSION,
    PHOTO_MEDIA_TYPE,
    compress_and_save_jpeg,
    open_upload_photo,
    photo_filename,
)

router = APIRouter()

OptionalUser = Annotated[Optional[User], Depends(get_optional_current_user)]

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


def _delete_snapshot_disk_assets(request: Request, snapshot_id: str) -> None:
    """Best-effort cleanup of on-disk assets for one snapshot."""
    preview_path = os.path.join(
        request.app.snapshot_preview_dir,
        f'{snapshot_id}.webp',
    )
    if os.path.exists(preview_path):
        try:
            os.remove(preview_path)
        except OSError as exc:
            print(f'[WARN] delete snapshot preview {snapshot_id}: {exc}')

    for parent in (
        request.app.snapshot_photos_dir,
        request.app.snapshot_meshes_dir,
        request.app.snapshot_point_clouds_dir,
    ):
        target = os.path.join(parent, snapshot_id)
        if os.path.isdir(target):
            try:
                shutil.rmtree(target)
            except OSError as exc:
                print(f'[WARN] delete snapshot assets {target}: {exc}')


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
    except PyMongoError as exc:
        print(f'[ERROR] refresh_snapshot_photo_count DB error: {exc}')
    if snapshot_doc is not None:
        snapshot_doc['photo_count'] = count
    return count


async def _sync_photo_count(request: Request, snapshot_id: str) -> int:
    return await refresh_snapshot_photo_count(request, snapshot_id)


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
    except PyMongoError as exc:
        print(f'[ERROR] list_my_snapshots: {exc}')
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
            raise HTTPException(
                status_code=500,
                detail=f'Snapshot row failed validation: {exc}')
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
    except PyMongoError as exc:
        print(f'[ERROR] list_pending_snapshots: {exc}')
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
            raise HTTPException(
                status_code=500,
                detail=f'Pending snapshot row failed validation: {exc}',
            )

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
        raise HTTPException(
            status_code=500,
            detail=f'Stored snapshot failed Pydantic validation: {exc}',
        )

    return JSONResponse(
        status_code=200,
        content=for_viewer(body, current_user),      # no people (8.101)
        headers=viewer_headers(etag=etag),
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
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/preview',
    summary='Export the mesh preview stored in the snapshot (PLY or OBJ)',
)
@router.get(
    '/snapshots/{snapshot_id}/meshes/{primitive_index}/primitive',
    summary='Alias of .../preview until plan P5 (decision 8.23)',
    deprecated=True,
)
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
        body = export_inline_mesh(mesh, fmt)  # type: ignore[arg-type]
    except IndexError:
        raise HTTPException(status_code=404, detail='Mesh preview not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] mesh preview export ({fmt}): {exc}')
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
            detail=f'PLY file not found on disk: {path}',
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
    except PyMongoError as exc:
        print(f'[ERROR] _register_mesh_ply_resolution DB error: {exc}')
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
    except PyMongoError as exc:
        print(f'[ERROR] _unregister_mesh_ply_resolution DB error: {exc}')
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
        with open(dest, 'wb') as handle:
            handle.write(raw)
    except OSError as exc:
        print(f'[ERROR] put_snapshot_mesh_ply write: {exc}')
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
        except OSError as exc:
            print(f'[ERROR] delete_snapshot_mesh_ply: {exc}')
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
    doc = await ensure_snapshot_read_access(
        request,
        snapshot_id,
        current_user,
    )
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
    '/snapshots/{snapshot_id}/proxies/{index}/mesh',
    summary='Export a proxy as a mesh (PLY or OBJ), in stored coordinates',
)
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
        body = trimesh_to_bytes(proxy_mesh(proxies[index]), fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f'[ERROR] proxy export ({fmt}): {exc}')
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
        with open(dest, 'wb') as handle:
            handle.write(raw)
    except OSError as exc:
        print(f'[ERROR] put_snapshot_point_cloud_ply write: {exc}')
        raise HTTPException(
            status_code=500,
            detail='Failed to save point cloud file',
        )

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'size_bytes': len(raw),
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
    except OSError as exc:
        print(f'[ERROR] delete_snapshot_point_cloud_ply: {exc}')
        raise HTTPException(
            status_code=500,
            detail='Failed to delete point cloud file',
        )

    await derive_sync(request, snapshot_id)
    return JSONResponse(
        status_code=200,
        content={
            'snapshot_id': snapshot_id,
            'index': index,
            'ok': True,
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
    await ensure_snapshot_read_access(request, snapshot_id, current_user)
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
    await ensure_snapshot_read_access(request, snapshot_id, current_user)
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
    await ensure_snapshot_read_access(request, snapshot_id, current_user)
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
    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'add_photo',
        frozen_when_published=False)

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
        image = open_upload_photo(raw)
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
    doc = await _load_snapshot(request, snapshot_id)
    await require_snapshot_file_write(
        request, current_user, doc, 'delete_photo',
        frozen_when_published=False)

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
