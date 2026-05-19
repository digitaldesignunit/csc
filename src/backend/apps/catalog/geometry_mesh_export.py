"""
Export snapshot geometry as PLY or OBJ (on-the-fly conversion; no duplicate files on disk).

Canonical storage remains PLY under ``meshes/`` and inline JSON primitives; OBJ is
generated at download time via trimesh.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Literal, Union

import numpy as np
import trimesh

from apps.descriptors.geometry import create_mesh_from_extrusion

MeshExportFormat = Literal['ply', 'obj']
ALLOWED_MESH_EXPORT_FORMATS = frozenset({'ply', 'obj'})

MeshGeometry = Union[trimesh.Trimesh, trimesh.PointCloud]


def normalize_mesh_format(value: str) -> MeshExportFormat:
    fmt = (value or 'ply').strip().lower()
    if fmt not in ALLOWED_MESH_EXPORT_FORMATS:
        raise ValueError(
            f'format must be one of: {sorted(ALLOWED_MESH_EXPORT_FORMATS)}'
        )
    return fmt  # type: ignore[return-value]


def mesh_export_media_type(fmt: MeshExportFormat) -> str:
    return 'model/ply' if fmt == 'ply' else 'model/obj'


def mesh_export_extension(fmt: MeshExportFormat) -> str:
    return fmt


def trimesh_to_bytes(mesh: MeshGeometry, fmt: MeshExportFormat) -> bytes:
    buf = io.BytesIO()
    mesh.export(buf, file_type=fmt)
    return buf.getvalue()


def load_trimesh_from_ply_file(path: str) -> trimesh.Trimesh:
    """Load a on-disk PLY mesh file for conversion to another format."""
    loaded = trimesh.load(path, force='mesh')
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise ValueError('PLY file contains no mesh geometry')
        return trimesh.util.concatenate(tuple(loaded.geometry.values()))
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError('PLY file did not contain a triangle mesh')
    return loaded


def _mesh_from_inline_primitive(mesh: Dict[str, Any]) -> trimesh.Trimesh:
    vertices = np.asarray(mesh.get('vertices') or [], dtype=np.float64)
    faces_raw = mesh.get('faces') or []
    if vertices.size == 0 or not faces_raw:
        raise ValueError('Mesh primitive has no vertices or faces')

    faces = np.asarray(faces_raw, dtype=np.int64)
    kwargs: Dict[str, Any] = {}
    colors = mesh.get('colors')
    if colors:
        vc = np.asarray(colors, dtype=np.uint8)
        if vc.ndim == 2 and vc.shape[1] >= 3:
            kwargs['vertex_colors'] = vc[:, :3]

    return trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        process=True,
        **kwargs,
    )


def _mesh_from_extrusion(ext: Dict[str, Any]) -> trimesh.Trimesh:
    profile = ext.get('profile') or []
    height = ext.get('height')
    if height is None:
        raise ValueError('Extrusion primitive has no height')
    return create_mesh_from_extrusion(profile, float(height))


def _point_cloud_from_inline(pc: Dict[str, Any]) -> trimesh.PointCloud:
    points = np.asarray(pc.get('points') or [], dtype=np.float64)
    if points.size == 0:
        raise ValueError('Point cloud primitive has no points')
    colors = pc.get('colors')
    if colors:
        vc = np.asarray(colors, dtype=np.uint8)
        if vc.ndim == 2 and vc.shape[1] >= 3:
            return trimesh.PointCloud(vertices=points, colors=vc[:, :3])
    return trimesh.PointCloud(vertices=points)


def export_inline_mesh(
    mesh: Dict[str, Any],
    fmt: MeshExportFormat,
) -> bytes:
    return trimesh_to_bytes(_mesh_from_inline_primitive(mesh), fmt)


def export_extrusion(
    ext: Dict[str, Any],
    fmt: MeshExportFormat,
) -> bytes:
    return trimesh_to_bytes(_mesh_from_extrusion(ext), fmt)


def export_mesh_file(
    ply_path: str,
    fmt: MeshExportFormat,
) -> bytes:
    """Read canonical on-disk PLY and export as PLY (passthrough) or OBJ."""
    mesh = load_trimesh_from_ply_file(ply_path)
    return trimesh_to_bytes(mesh, fmt)


def export_inline_point_cloud_ply(pc: Dict[str, Any]) -> bytes:
    return trimesh_to_bytes(_point_cloud_from_inline(pc), 'ply')


def _geometry_block(doc: Dict[str, Any]) -> Dict[str, Any]:
    geometry = doc.get('geometry') or {}
    if not isinstance(geometry, dict):
        return {}
    return geometry


def get_inline_mesh_primitive(
    doc: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    meshes: List[Dict[str, Any]] = _geometry_block(doc).get('meshes') or []
    if index < 0 or index >= len(meshes):
        raise IndexError(f'mesh primitive index {index} out of range')
    return meshes[index]


def get_inline_extrusion_primitive(
    doc: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    extrusions: List[Dict[str, Any]] = (
        _geometry_block(doc).get('extrusions') or []
    )
    if index < 0 or index >= len(extrusions):
        raise IndexError(f'extrusion primitive index {index} out of range')
    return extrusions[index]


def get_inline_point_cloud_primitive(
    doc: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    point_clouds: List[Dict[str, Any]] = (
        _geometry_block(doc).get('point_clouds') or []
    )
    if index < 0 or index >= len(point_clouds):
        raise IndexError(f'point cloud primitive index {index} out of range')
    return point_clouds[index]
