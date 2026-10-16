#!/usr/bin/env python3.13
"""
Remove on-disk snapshot geometry assets that no longer exist in MongoDB.

Compares top-level ``<snapshot_id>/`` folders under the snapshot mesh and
point-cloud directories against ``component_snapshots._id`` and deletes
orphaned directories.

Usage:
    python geometrymaintenance.py           # live delete
    python geometrymaintenance.py --dry-run # report only, no deletes
    python geometrymaintenance.py -d        # same as --dry-run
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
import shutil
import sys
from typing import List, Set, Tuple


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from pymongo import AsyncMongoClient


# LOCAL MODULE IMPORTS --------------------------------------------------------

from logging_setup import configure as configure_logging, get_logger
from settings import get_settings
from utility import (
    get_db_connectionstring,
    get_snapshot_meshes_directory,
    get_snapshot_point_clouds_directory,
)

log = get_logger(__name__)


def _snapshot_subdirs(base_dir: str) -> Set[str]:
    """Return top-level subdirectory names under a snapshot asset root."""
    if not os.path.isdir(base_dir):
        return set()
    return {
        name
        for name in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, name))
    }


async def initialize_geometry_maintenance() -> Tuple[List[str], List[str]]:
    """
    Compare snapshot ids in ``component_snapshots`` with on-disk asset folders.

    Returns:
        (stale_mesh_snapshot_ids, stale_point_cloud_snapshot_ids)
    """
    meshes_dir = get_snapshot_meshes_directory()
    point_clouds_dir = get_snapshot_point_clouds_directory()
    os.makedirs(meshes_dir, exist_ok=True)
    os.makedirs(point_clouds_dir, exist_ok=True)

    mesh_subdirs = _snapshot_subdirs(meshes_dir)
    point_cloud_subdirs = _snapshot_subdirs(point_clouds_dir)

    mongodb_client = AsyncMongoClient(
        get_db_connectionstring(),
        serverSelectionTimeoutMS=5000,
    )
    try:
        await mongodb_client.aconnect()
        mongodb_snapshots = mongodb_client['csc']['component_snapshots']
        snapshot_ids = {
            str(snapshot['_id']) async for snapshot in mongodb_snapshots.find(
                {}, {'_id': 1}
            )
        }
    finally:
        await mongodb_client.close()

    stale_mesh_ids = sorted(mesh_subdirs - snapshot_ids)
    stale_point_cloud_ids = sorted(point_cloud_subdirs - snapshot_ids)
    return stale_mesh_ids, stale_point_cloud_ids


def _delete_stale_dirs(
    base_dir: str,
    stale_ids: List[str],
    label: str,
    dry_run: bool = False,
) -> int:
    """Delete (or report) stale snapshot asset directories. Returns count."""
    deleted = 0
    for snapshot_id in stale_ids:
        dir_path = os.path.join(base_dir, snapshot_id)
        if os.path.isdir(dir_path):
            if dry_run:
                log.info('DRY RUN: would delete stale %s assets for %s',
                         label, snapshot_id)
            else:
                shutil.rmtree(dir_path)
                log.info('Deleted stale %s assets for %s', label, snapshot_id)
            deleted += 1
    return deleted


if __name__ == '__main__':
    configure_logging(get_settings())
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    log.info('Starting geometry maintenance (%s)',
             'DRY RUN' if dry_run else 'LIVE')

    meshes_dir = get_snapshot_meshes_directory()
    point_clouds_dir = get_snapshot_point_clouds_directory()
    stale_mesh_ids, stale_point_cloud_ids = asyncio.run(
        initialize_geometry_maintenance()
    )

    log.info('Found %d stale mesh director%s', len(stale_mesh_ids),
             'y' if len(stale_mesh_ids) == 1 else 'ies')
    if stale_mesh_ids:
        mesh_deleted = _delete_stale_dirs(
            meshes_dir, stale_mesh_ids, 'mesh', dry_run=dry_run)
    else:
        log.info('No stale mesh asset directories found')
        mesh_deleted = 0

    log.info('Found %d stale point cloud director%s',
             len(stale_point_cloud_ids),
             'y' if len(stale_point_cloud_ids) == 1 else 'ies')
    if stale_point_cloud_ids:
        point_cloud_deleted = _delete_stale_dirs(
            point_clouds_dir,
            stale_point_cloud_ids,
            'point cloud',
            dry_run=dry_run,
        )
    else:
        log.info('No stale point cloud asset directories found')
        point_cloud_deleted = 0

    if dry_run and (mesh_deleted or point_cloud_deleted):
        log.info('DRY RUN: no directories were actually deleted')

    action = 'would delete' if dry_run else 'deleted'
    log.info('Summary: mesh directories processed %d (%s), point cloud '
             'directories processed %d (%s), mode %s', mesh_deleted, action,
             point_cloud_deleted, action, 'DRY RUN' if dry_run else 'LIVE')
