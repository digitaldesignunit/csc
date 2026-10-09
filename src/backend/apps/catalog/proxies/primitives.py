#!/usr/bin/env python3.13
"""
Proxy primitives as meshes (data model spec Appendix B).

A proxy stores ``params`` in its own local axes (origin at the primitive
centroid, ``z`` along the extrusion / axis direction) and a ``placement``
that maps those axes into the snapshot's stored coordinates. This module
turns ``(primitive, params, placement)`` into a triangle mesh, in local or
in stored coordinates, and converts points between the two.

Pure numpy / trimesh / shapely; no new dependency (decision 6.11).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, List, Mapping, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

CYLINDER_SEGMENTS = 96
"""Segments of a cylinder mesh (surface sampling and previews only)."""


# PLACEMENT -------------------------------------------------------------------
def placement_matrix(placement: Mapping[str, Sequence[float]]) -> np.ndarray:
    """4x4 matrix that maps local primitive coordinates to stored ones."""
    matrix = np.eye(4)
    matrix[:3, 0] = np.asarray(placement['x'], dtype=np.float64)
    matrix[:3, 1] = np.asarray(placement['y'], dtype=np.float64)
    matrix[:3, 2] = np.asarray(placement['z'], dtype=np.float64)
    matrix[:3, 3] = np.asarray(placement['o'], dtype=np.float64)
    return matrix


def to_local(points: np.ndarray,
             placement: Mapping[str, Sequence[float]]) -> np.ndarray:
    """Stored coordinates -> the primitive's local axes."""
    matrix = placement_matrix(placement)
    rotation = matrix[:3, :3]
    return (np.asarray(points, dtype=np.float64) - matrix[:3, 3]) @ rotation


def to_stored(points: np.ndarray,
              placement: Mapping[str, Sequence[float]]) -> np.ndarray:
    """The primitive's local axes -> stored coordinates."""
    matrix = placement_matrix(placement)
    return np.asarray(points, dtype=np.float64) @ matrix[:3, :3].T \
        + matrix[:3, 3]


def frame_dict(origin: Sequence[float], axes: np.ndarray) -> Dict[str, List]:
    """A ``Frame`` / placement dict from an origin and rows ``x, y, z``."""
    return {'o': [float(v) for v in origin],
            'x': [float(v) for v in axes[0]],
            'y': [float(v) for v in axes[1]],
            'z': [float(v) for v in axes[2]]}


# LOCAL MESHES ----------------------------------------------------------------
def _ring_array(ring: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(ring, dtype=np.float64)
    if len(array) > 1 and np.allclose(array[0], array[-1]):
        array = array[:-1]
    return array


def _cap_triangles(polygon: Polygon) -> List[np.ndarray]:
    """Triangles (3, 2) of a polygon with holes; constrained Delaunay when
    shapely has it (2.1+), else a fan over the outline (convex only)."""
    triangulate = getattr(shapely, 'constrained_delaunay_triangles', None)
    if triangulate is not None and polygon.is_valid:
        try:
            return [np.asarray(tri.exterior.coords)[:3]
                    for tri in triangulate(polygon).geoms]
        except Exception:                                  # noqa: BLE001
            pass
    outline = np.asarray(polygon.exterior.coords)[:-1]
    return [np.array([outline[0], outline[i], outline[i + 1]])
            for i in range(1, len(outline) - 1)]


def prism_mesh(profile: Sequence[Sequence[float]],
               holes: Sequence[Sequence[Sequence[float]]] | None,
               height: float) -> trimesh.Trimesh:
    """Profile (x, y) swept from z = -h/2 to +h/2; holes cut through."""
    outer = _ring_array(profile)
    rings = [_ring_array(h) for h in (holes or [])]
    polygon = orient(Polygon(outer, rings), sign=1.0)
    exterior = np.asarray(polygon.exterior.coords)[:-1]
    interiors = [np.asarray(r.coords)[:-1] for r in polygon.interiors]
    half = height / 2.0

    vertices: List[Tuple[float, float, float]] = []
    index: Dict[Tuple[float, float, int], int] = {}

    def vertex(x: float, y: float, top: int) -> int:
        key = (float(x), float(y), top)
        if key not in index:
            index[key] = len(vertices)
            vertices.append((float(x), float(y), half if top else -half))
        return index[key]

    faces: List[Tuple[int, int, int]] = []
    for ring in [exterior, *interiors]:
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            b0, b1 = vertex(*a, 0), vertex(*b, 0)
            t0, t1 = vertex(*a, 1), vertex(*b, 1)
            faces.append((b0, b1, t1))
            faces.append((b0, t1, t0))
    for tri in _cap_triangles(polygon):
        (ax, ay), (bx, by), (cx, cy) = tri
        # tri is counter-clockwise: top keeps it, bottom reverses it
        faces.append((vertex(ax, ay, 1), vertex(bx, by, 1),
                      vertex(cx, cy, 1)))
        faces.append((vertex(ax, ay, 0), vertex(cx, cy, 0),
                      vertex(bx, by, 0)))
    return trimesh.Trimesh(np.asarray(vertices), np.asarray(faces),
                           process=False)


def cylinder_mesh(radius: float, height: float,
                  segments: int = CYLINDER_SEGMENTS) -> trimesh.Trimesh:
    theta = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    ring = np.column_stack([radius * np.cos(theta), radius * np.sin(theta)])
    half = height / 2.0
    bottom = np.column_stack([ring, np.full(segments, -half)])
    top = np.column_stack([ring, np.full(segments, half)])
    vertices = np.vstack([bottom, top, [[0, 0, -half]], [[0, 0, half]]])
    bc, tc = 2 * segments, 2 * segments + 1
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j))
        faces.append((i, segments + j, segments + i))
        faces.append((bc, j, i))
        faces.append((tc, segments + i, segments + j))
    return trimesh.Trimesh(vertices, np.asarray(faces), process=False)


def local_mesh(primitive: str, params: Mapping[str, Any]) -> trimesh.Trimesh:
    """The primitive in its own local axes."""
    if primitive == 'box':
        return trimesh.creation.box(extents=np.asarray(params['size'],
                                                       dtype=np.float64))
    if primitive == 'prism':
        return prism_mesh(params['profile'], params.get('holes'),
                          float(params['height']))
    if primitive == 'cylinder':
        return cylinder_mesh(float(params['radius']), float(params['height']))
    if primitive == 'hull':
        return trimesh.Trimesh(np.asarray(params['vertices'], dtype=float),
                               np.asarray(params['faces'], dtype=np.int64),
                               process=False)
    raise ValueError(f'unknown primitive {primitive!r}')


def proxy_mesh(proxy: Mapping[str, Any]) -> trimesh.Trimesh:
    """A stored proxy document as a mesh in stored coordinates."""
    mesh = local_mesh(proxy['primitive'], proxy['params'])
    mesh.apply_transform(placement_matrix(proxy['placement']))
    return mesh
