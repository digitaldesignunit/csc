#!/usr/bin/env python3.13
"""
Stages 1--2 of the geometry runner inside the API (spec section 4.3,
decision 6.14): a piece is usable at once, so the frame and the shape class
are derived synchronously on every source-geometry write to a draft (create,
supersede, PLY write or delete, geometry PATCH), on submit, when a shape
class override is set or cleared (8.55) and when ``original_function``
changes (the column rule of the frame, 8.52). The expensive stages are left
to the cron sweep (``main_geometry.py``), on this server or on a remote
worker (``CSC_GEOMETRY_HEAVY_STAGES``, decision 8.54).

A failure here never fails the write: the stage stamps a short error on the
snapshot (``derivation``) and the sweep reports it.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
from typing import Any, List, Mapping, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import HTTPException, Request

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.api.catalog_common import now_iso
from apps.catalog.etag import compute_snapshot_etag
from apps.catalog.geometry_runner import derive_and_store
from apps.catalog.geometry_stages import (
    HEAVY_STAGES,
    STAGES,
    SYNC_STAGES,
    Env,
    heavy_stages_where,
    short_error,
)


def _env(request: Request) -> Env:
    app = request.app
    return Env(meshes_dir=app.snapshot_meshes_dir,
               point_clouds_dir=app.snapshot_point_clouds_dir,
               preview_dir=app.snapshot_preview_dir,
               log=lambda message: print(f'[GEOMETRY] {message}'))


def fitted_map_files(snapshot: Mapping[str, Any]) -> List[str]:
    """Deviation-map files named by the snapshot's fitted proxies."""
    return [face['file']
            for proxy in (snapshot.get('geometry') or {}).get('proxies') or []
            if (proxy.get('fit') or {}).get('method') != 'authored'
            for face in ((proxy.get('deviation_maps') or {})
                         .get('faces') or {}).values()]


def remove_map_files(proxies_root: Optional[str], names: List[str]) -> None:
    """Delete map files (``proxies/<sid>/...``) below ``proxies_root``."""
    if not proxies_root:
        return
    root = os.path.normpath(proxies_root)
    for name in names:
        path = os.path.normpath(os.path.join(root, *name.split('/')[1:]))
        if path.startswith(root + os.sep):
            try:
                os.remove(path)
            except OSError:
                pass


async def derive_sync(request: Request, snapshot_id: str) -> Optional[dict]:
    """Run the cheap stages that are stale on one snapshot; returns the
    stored document afterwards (None when it no longer exists)."""
    app = request.app
    snapshots = app.mongodb_component_snapshots
    snapshot = await snapshots.find_one({'_id': snapshot_id})
    if snapshot is None:
        return None
    identity = await app.mongodb_component_identities.find_one(
        {'_id': snapshot['identity_id']})
    if identity is None:
        return snapshot
    try:
        await derive_and_store(snapshots, snapshot, identity, _env(request),
                               app.snapshot_proxies_dir, SYNC_STAGES)
    except Exception as exc:                               # noqa: BLE001
        print(f'[ERROR] stages 1-2 of snapshot {snapshot_id}: '
              f'{short_error(exc)}')
    return await snapshots.find_one({'_id': snapshot_id})


async def recompute_all_stages(request: Request, snapshot_id: str
                               ) -> Optional[dict]:
    """A moderator asked for a recompute (decision 8.54). Frame and class are
    recomputed at once. The heavy stages run here when
    ``CSC_GEOMETRY_HEAVY_STAGES`` is ``server`` (the default); when it is
    ``remote`` they are only marked stale (their stamps go), and a worker
    picks them up. A storage failure is a 500 with a short text."""
    app = request.app
    snapshots = app.mongodb_component_snapshots
    snapshot = await snapshots.find_one({'_id': snapshot_id})
    if snapshot is None:
        return None
    identity = await app.mongodb_component_identities.find_one(
        {'_id': snapshot['identity_id']})
    if identity is None:
        return snapshot
    where = heavy_stages_where()
    try:
        outcome = await derive_and_store(
            snapshots, snapshot, identity, _env(request),
            app.snapshot_proxies_dir,
            STAGES if where == 'server' else SYNC_STAGES, force=True)
        if outcome.errors.get('write'):
            raise HTTPException(
                status_code=409,
                detail='The snapshot changed meanwhile; try again.')
        if where == 'remote':
            await _mark_stale(request, snapshot_id)
    except HTTPException:
        raise
    except Exception as exc:                               # noqa: BLE001
        print(f'[ERROR] recompute of snapshot {snapshot_id}: '
              f'{short_error(exc)}')
        raise HTTPException(
            status_code=500,
            detail='The recompute failed; see the server log.') from exc
    return await snapshots.find_one({'_id': snapshot_id})


async def _mark_stale(request: Request, snapshot_id: str) -> None:
    """Drop the stamps of the heavy stages (etag-guarded, like every
    derivation write); the remote worker finds them stale."""
    snapshots = request.app.mongodb_component_snapshots
    snapshot = await snapshots.find_one({'_id': snapshot_id})
    if snapshot is None:
        return
    derivation = {k: v for k, v in (snapshot.get('derivation') or {}).items()
                  if k not in HEAVY_STAGES}
    merged = {**snapshot, 'derivation': derivation}
    result = await snapshots.update_one(
        {'_id': snapshot_id, 'etag': snapshot.get('etag')},
        {'$set': {'derivation': derivation, 'lastmodified': now_iso(),
                  'etag': compute_snapshot_etag(merged)}})
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail='The snapshot changed meanwhile; try again.')


async def derive_sync_identity(request: Request, identity_id: str) -> None:
    """The same for every snapshot of an identity (its function changed)."""
    cursor = request.app.mongodb_component_snapshots.find(
        {'identity_id': identity_id}, {'_id': 1})
    async for row in cursor:
        await derive_sync(request, row['_id'])
