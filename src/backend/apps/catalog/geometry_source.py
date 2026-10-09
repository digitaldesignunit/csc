#!/usr/bin/env python3.13
"""
The geometry every derivation reads (data model spec section 4.3).

One loader for all runner stages: the highest-resolution copy of **all**
component geometry of a snapshot, in the snapshot's stored coordinates
(never moved by the frame). ``capture`` markers and fixtures are not
component geometry and are never read here (I23).

Representation priority, as in 0.5: meshes outrank point clouds (two
captures of one physical state), and both outrank authored proxies. Per
mesh, ``detailed.ply`` > ``reduced.ply`` > the inline mesh; per cloud, the
PLY on disk > the inline preview.

The loader also fingerprints its inputs (inline geometry, the PLY files it
used with size and modification time), so a stage knows when its source
changed (decision 8.7).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_mesh_export import load_trimesh_from_ply_file
from apps.catalog.proxies.primitives import proxy_mesh

RESOLUTION_OF_FILE = {'detailed': 'original', 'reduced': 'reduced'}
_RESOLUTION_RANK = {'original': 2, 'reduced': 1, 'preview': 0}
_FILE_ORDER = ('detailed', 'reduced')


class NoGeometry(ValueError):
    """The snapshot has no component geometry to derive from."""


@dataclass
class Source:
    """The component geometry of one snapshot, ready for the stages."""
    kind: str                                   # meshes | point_clouds | authored
    resolution: str                             # original | reduced | preview
    meshes: List[trimesh.Trimesh] = field(default_factory=list)
    clouds: List[np.ndarray] = field(default_factory=list)
    fingerprint: str = ''

    @property
    def fit_kind(self) -> str:
        """``fit.source.kind``; authored geometry is never a fit source."""
        return 'meshes' if self.kind in ('meshes', 'authored') \
            else 'point_clouds'

    def points(self) -> np.ndarray:
        """All component points: mesh vertices or cloud points."""
        parts = [m.vertices for m in self.meshes] + list(self.clouds)
        if not parts:
            raise NoGeometry('no points')
        return np.vstack(parts).astype(np.float64, copy=False)

    def mesh(self) -> Optional[trimesh.Trimesh]:
        """All meshes as one (None for a cloud-only snapshot)."""
        if not self.meshes:
            return None
        if len(self.meshes) == 1:
            return self.meshes[0]
        return trimesh.util.concatenate(self.meshes)


def _inline_mesh(entry: Mapping[str, Any]) -> trimesh.Trimesh:
    vertices = entry.get('vertices') or entry.get('v')
    faces = entry.get('faces') or entry.get('f')
    if not vertices or not faces:
        raise NoGeometry('inline mesh without vertices or faces')
    return trimesh.Trimesh(np.asarray(vertices, dtype=np.float64),
                           np.asarray(faces, dtype=np.int64), process=True)


def _ply_state(path: str, root: str) -> List[Any]:
    stat = os.stat(path)
    return [os.path.relpath(path, root).replace(os.sep, '/'),
            stat.st_size, stat.st_mtime_ns]


def _manifest(snapshot: Mapping[str, Any], index: int) -> Tuple[str, ...]:
    listed = (snapshot.get('mesh_ply_resolutions') or {}).get(str(index))
    if listed is None:
        return _FILE_ORDER
    return tuple(r for r in _FILE_ORDER if r in listed) \
        + tuple(r for r in listed if r not in _FILE_ORDER)


def _mesh_file(snapshot: Mapping[str, Any], index: int,
               meshes_dir: Optional[str]) -> Optional[Tuple[str, str]]:
    """``(path, resolution)`` of the best PLY of mesh ``index`` on disk."""
    if not meshes_dir:
        return None
    sid = str(snapshot.get('_id'))
    for label in _manifest(snapshot, index):
        path = os.path.join(meshes_dir, sid, str(index), f'{label}.ply')
        if os.path.isfile(path):
            return path, RESOLUTION_OF_FILE.get(label, 'reduced')
    return None


def _cloud_file(snapshot: Mapping[str, Any], index: int,
                point_clouds_dir: Optional[str]) -> Optional[str]:
    if not point_clouds_dir:
        return None
    path = os.path.join(point_clouds_dir, str(snapshot.get('_id')),
                        f'{index}.ply')
    return path if os.path.isfile(path) else None


def _load_mesh(snapshot: Mapping[str, Any], index: int, entry: Mapping,
               meshes_dir: Optional[str]) -> Tuple[trimesh.Trimesh, str]:
    found = _mesh_file(snapshot, index, meshes_dir)
    if found:
        try:
            return load_trimesh_from_ply_file(found[0]), found[1]
        except Exception:                                  # noqa: BLE001
            pass
    return _inline_mesh(entry), 'preview'


def _load_cloud(snapshot: Mapping[str, Any], index: int, entry: Mapping,
                point_clouds_dir: Optional[str]
                ) -> Tuple[np.ndarray, str]:
    path = _cloud_file(snapshot, index, point_clouds_dir)
    if path:
        try:
            loaded = trimesh.load(path, process=False)
            points = np.asarray(loaded.vertices, dtype=np.float64)
            if len(points):
                return points, 'original'
        except Exception:                                  # noqa: BLE001
            pass
    points = np.asarray(entry.get('points') or [], dtype=np.float64)
    if not len(points):
        raise NoGeometry('inline point cloud without points')
    return points, 'preview'


def _digest(parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, separators=(',', ':'),
                      default=str)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:24]


def inline_fingerprint(geometry: Mapping[str, Any]) -> str:
    """Digest of the inline geometry a snapshot carries (meshes, clouds,
    authored proxies; fitted proxies are derived and left out)."""
    authored = [{k: p.get(k) for k in ('primitive', 'params', 'placement')}
                for p in geometry.get('proxies') or []
                if (p.get('fit') or {}).get('method') == 'authored']
    return _digest([geometry.get('meshes') or [],
                    geometry.get('point_clouds') or [], authored])


def stored_files(snapshot: Mapping[str, Any],
                 meshes_dir: Optional[str] = None,
                 point_clouds_dir: Optional[str] = None) -> dict:
    """The PLY files ``load_source`` would read: per mesh index the chosen
    file (``detailed`` / ``reduced``), per cloud index whether it is on
    disk. A remote worker fetches exactly these."""
    geometry = snapshot.get('geometry') or {}
    meshes = {}
    for i in range(len(geometry.get('meshes') or [])):
        found = _mesh_file(snapshot, i, meshes_dir)
        if found:
            meshes[str(i)] = os.path.splitext(os.path.basename(found[0]))[0]
    clouds = [i for i in range(len(geometry.get('point_clouds') or []))
              if _cloud_file(snapshot, i, point_clouds_dir)]
    return {'meshes': meshes, 'point_clouds': clouds}


def stored_file_sizes(snapshot: Mapping[str, Any],
                      meshes_dir: Optional[str] = None,
                      point_clouds_dir: Optional[str] = None) -> dict:
    """The PLY files ``load_source`` would read with their sizes: per mesh
    index ``[label, bytes]``, per cloud index ``bytes``. The size says it is
    the same file after a copy; the modification time does not (8.122 f)."""
    geometry = snapshot.get('geometry') or {}
    meshes = {}
    for i in range(len(geometry.get('meshes') or [])):
        found = _mesh_file(snapshot, i, meshes_dir)
        if found:
            label = os.path.splitext(os.path.basename(found[0]))[0]
            meshes[str(i)] = [label, os.path.getsize(found[0])]
    clouds = {}
    for i in range(len(geometry.get('point_clouds') or [])):
        path = _cloud_file(snapshot, i, point_clouds_dir)
        if path:
            clouds[str(i)] = os.path.getsize(path)
    return {'meshes': meshes, 'point_clouds': clouds}


def source_fingerprint(snapshot: Mapping[str, Any],
                       meshes_dir: Optional[str] = None,
                       point_clouds_dir: Optional[str] = None) -> str:
    """Digest of everything ``load_source`` reads: the inline geometry and,
    per mesh / cloud, the PLY file chosen with its size and modification
    time. Stats files, never reads them, so a sweep stays cheap."""
    geometry = snapshot.get('geometry') or {}
    files: List[Any] = []
    for i in range(len(geometry.get('meshes') or [])):
        found = _mesh_file(snapshot, i, meshes_dir)
        if found:
            files.append(_ply_state(found[0], meshes_dir))
    for i in range(len(geometry.get('point_clouds') or [])):
        path = _cloud_file(snapshot, i, point_clouds_dir)
        if path:
            files.append(_ply_state(path, point_clouds_dir))
    return _digest([inline_fingerprint(geometry), files])


def load_source(snapshot: Mapping[str, Any],
                meshes_dir: Optional[str] = None,
                point_clouds_dir: Optional[str] = None) -> Source:
    """Load the component geometry of ``snapshot``; raises NoGeometry."""
    geometry = snapshot.get('geometry') or {}
    fingerprint = source_fingerprint(snapshot, meshes_dir, point_clouds_dir)

    meshes, resolutions = [], []
    for i, entry in enumerate(geometry.get('meshes') or []):
        mesh, resolution = _load_mesh(snapshot, i, entry, meshes_dir)
        meshes.append(mesh)
        resolutions.append(resolution)
    if meshes:
        return Source('meshes', min(resolutions, key=_RESOLUTION_RANK.get),
                      meshes=meshes, fingerprint=fingerprint)

    clouds, resolutions = [], []
    for i, entry in enumerate(geometry.get('point_clouds') or []):
        points, resolution = _load_cloud(snapshot, i, entry,
                                         point_clouds_dir)
        clouds.append(points)
        resolutions.append(resolution)
    if clouds:
        return Source('point_clouds',
                      min(resolutions, key=_RESOLUTION_RANK.get),
                      clouds=clouds, fingerprint=fingerprint)

    authored = [proxy_mesh(p) for p in geometry.get('proxies') or []
                if (p.get('fit') or {}).get('method') == 'authored']
    if authored:
        return Source('authored', 'preview', meshes=authored,
                      fingerprint=fingerprint)
    raise NoGeometry('the snapshot has no mesh, point cloud or authored '
                     'proxy')
