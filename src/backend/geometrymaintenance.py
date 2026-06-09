#!/usr/bin/env python3.9
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

from utility import (
    get_db_connectionstring,
    get_snapshot_meshes_directory,
    get_snapshot_point_clouds_directory,
    create_logging_timestamp as logts,
)


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
            ts = logts()
            if dry_run:
                print(
                    f'[GEOMMAINT] {ts} DRY RUN: Would delete stale {label} '
                    f'assets for {snapshot_id}.'
                )
            else:
                shutil.rmtree(dir_path)
                print(
                    f'[GEOMMAINT] {ts} Deleted stale {label} assets for '
                    f'{snapshot_id}.'
                )
            deleted += 1
    return deleted


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    ts = logts()
    print(f'[GEOMMAINT] {ts} Starting geometry maintenance...')
    print(f'[GEOMMAINT] Mode: {"DRY RUN" if dry_run else "LIVE"}')
    print('-' * 80)

    meshes_dir = get_snapshot_meshes_directory()
    point_clouds_dir = get_snapshot_point_clouds_directory()
    stale_mesh_ids, stale_point_cloud_ids = asyncio.run(
        initialize_geometry_maintenance()
    )

    ts = logts()
    print(
        f'[GEOMMAINT] {ts} Found {len(stale_mesh_ids)} stale mesh '
        f'director{"y" if len(stale_mesh_ids) == 1 else "ies"}.'
    )
    if stale_mesh_ids:
        mesh_deleted = _delete_stale_dirs(
            meshes_dir, stale_mesh_ids, 'mesh', dry_run=dry_run)
    else:
        ts = logts()
        print(f'[GEOMMAINT] {ts} No stale mesh asset directories found.')
        mesh_deleted = 0

    ts = logts()
    print(
        f'[GEOMMAINT] {ts} Found {len(stale_point_cloud_ids)} stale point '
        f'cloud director{"y" if len(stale_point_cloud_ids) == 1 else "ies"}.'
    )
    if stale_point_cloud_ids:
        point_cloud_deleted = _delete_stale_dirs(
            point_clouds_dir,
            stale_point_cloud_ids,
            'point cloud',
            dry_run=dry_run,
        )
    else:
        ts = logts()
        print(
            f'[GEOMMAINT] {ts} No stale point cloud asset directories found.'
        )
        point_cloud_deleted = 0

    if dry_run and (mesh_deleted or point_cloud_deleted):
        ts = logts()
        print(
            f'[GEOMMAINT] {ts} DRY RUN - No directories were actually '
            f'deleted.'
        )

    print('-' * 80)
    ts = logts()
    print(f'[GEOMMAINT] {ts} Summary:')
    print(
        f'  Mesh directories processed: {mesh_deleted} '
        f'({"would delete" if dry_run else "deleted"})'
    )
    print(
        f'  Point cloud directories processed: {point_cloud_deleted} '
        f'({"would delete" if dry_run else "deleted"})'
    )
    print(f'  Mode: {"DRY RUN" if dry_run else "LIVE"}')
