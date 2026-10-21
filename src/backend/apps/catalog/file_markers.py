"""
File markers that follow the geometry (0.6.3.1).

A snapshot lists the files it has stored: ``mesh_ply_resolutions`` (per mesh
index, the levels that have a PLY) and ``point_cloud_files`` (the indices of
the clouds that have a PLY). A file belongs to the primitive at its index. A
``PATCH`` that replaces ``geometry`` on a draft can change or remove the
primitive at an index: the file of that index then describes something that is
no longer there, and the marker would point past the new primitives or at the
wrong shape. ``reconcile_markers`` keeps the markers of the primitives that are
still the same and drops the others; ``remove_files`` deletes their files.
"""

import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from logging_setup import get_logger

log = get_logger(__name__)


class Reconciled:
    """The markers after a geometry change and what went."""

    def __init__(self, resolutions: Dict[str, List[str]],
                 cloud_files: List[int],
                 dropped_meshes: List[Tuple[int, str]],
                 dropped_clouds: List[int]):
        self.resolutions = resolutions
        self.cloud_files = cloud_files
        self.dropped_meshes = dropped_meshes
        self.dropped_clouds = dropped_clouds

    @property
    def changed(self) -> bool:
        return bool(self.dropped_meshes or self.dropped_clouds)


def _same(old: List[Any], new: List[Any], index: int) -> bool:
    """The primitive at ``index`` is still there and unchanged."""
    return (0 <= index < len(old) and index < len(new)
            and old[index] == new[index])


def _list(geometry: Optional[dict], key: str) -> List[Any]:
    value = (geometry or {}).get(key)
    return value if isinstance(value, list) else []


def reconcile_markers(old_geometry: Optional[dict],
                      new_geometry: Optional[dict],
                      resolutions: Optional[Dict[str, List[str]]],
                      cloud_files: Optional[List[int]]) -> Reconciled:
    """Keep a marker only where its primitive is unchanged: same index, equal
    content. Everything else (replaced, moved, gone, or already beyond the old
    geometry) is dropped."""
    old_meshes = _list(old_geometry, 'meshes')
    new_meshes = _list(new_geometry, 'meshes')
    old_clouds = _list(old_geometry, 'point_clouds')
    new_clouds = _list(new_geometry, 'point_clouds')
    kept_resolutions: Dict[str, List[str]] = {}
    dropped_meshes: List[Tuple[int, str]] = []
    for key, levels in (resolutions or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            index = -1
        if _same(old_meshes, new_meshes, index):
            kept_resolutions[key] = list(levels)
        else:
            dropped_meshes.extend((index, level) for level in levels)
    kept_clouds = [index for index in (cloud_files or [])
                   if _same(old_clouds, new_clouds, index)]
    dropped_clouds = [index for index in (cloud_files or [])
                      if index not in kept_clouds]
    return Reconciled(kept_resolutions, kept_clouds, dropped_meshes,
                      dropped_clouds)


def remove_files(meshes_dir: str, clouds_dir: str, snapshot_id: str,
                 reconciled: Reconciled) -> int:
    """Delete the files of the dropped markers; a file that is not there is
    fine. A mesh folder left empty goes too. Returns how many files went."""
    removed = 0
    for index, level in reconciled.dropped_meshes:
        path = os.path.join(meshes_dir, snapshot_id, str(index), f'{level}.ply')
        removed += _remove(path)
        folder = os.path.dirname(path)
        try:
            if os.path.isdir(folder) and not os.listdir(folder):
                shutil.rmtree(folder)
        except OSError:
            log.warning('mesh folder not removed', exc_info=True)
    for index in reconciled.dropped_clouds:
        removed += _remove(os.path.join(
            clouds_dir, snapshot_id, f'{index}.ply'))
    return removed


def _remove(path: str) -> int:
    try:
        os.remove(path)
        return 1
    except FileNotFoundError:
        return 0
    except OSError:
        log.warning('stale file not removed', exc_info=True)
        return 0
