#!/usr/bin/env python3.9
"""
Remove on-disk snapshot geometry assets that no longer exist in MongoDB.

Compares top-level ``<snapshot_id>/`` folders under the snapshot mesh and
point-cloud directories against ``component_snapshots._id`` and deletes
orphaned directories.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

import asyncio
import os
import shutil
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
) -> None:
    for snapshot_id in stale_ids:
        dir_path = os.path.join(base_dir, snapshot_id)
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
            ts = logts()
            print(
                f'[GEOMMAINT] {ts} Deleted stale {label} assets for '
                f'{snapshot_id}.'
            )


if __name__ == '__main__':
    meshes_dir = get_snapshot_meshes_directory()
    point_clouds_dir = get_snapshot_point_clouds_directory()
    stale_mesh_ids, stale_point_cloud_ids = asyncio.run(
        initialize_geometry_maintenance()
    )

    if stale_mesh_ids:
        _delete_stale_dirs(meshes_dir, stale_mesh_ids, 'mesh')
    else:
        ts = logts()
        print(f'[GEOMMAINT] {ts} No stale mesh asset directories found.')

    if stale_point_cloud_ids:
        _delete_stale_dirs(
            point_clouds_dir, stale_point_cloud_ids, 'point cloud')
    else:
        ts = logts()
        print(
            f'[GEOMMAINT] {ts} No stale point cloud asset directories found.'
        )
