#!/usr/bin/env python3.9
"""
Canonical PCA / OBB orientation for catalog snapshots.

Ports the Grasshopper ``DDU_CSC_CreateComponent`` orientation pipeline so the
same ``compute_obb_3d``, ``compute_obb_2d``, and minimum-bounding-rectangle
logic can run in the backend, maintenance scripts, and (eventually) GH.

Geometry contract (matches legacy ingest):
    * Snapshot geometry is **centered at the world origin** but **not** rotated
      into PCA space.
    * ``pca_frame`` stores the principal axes; ``bbx`` / ``bbx_origin``
      describe the oriented bounding box in PCA space.
    * ``iframe`` remains identity at create time.

3D meshes use **face-area-weighted** sample points (centroid repeats) before
PCA to reduce bias from sparse / irregular vertex distributions. Extrusions
use the 2D minimum-bounding-rectangle path (same as GH), not 3D vertex PCA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import ConvexHull
from sklearn.decomposition import PCA

from apps.descriptors.geometry import create_mesh_from_extrusion

FrameDict = Dict[str, List[float]]
GeometryDict = Dict[str, Any]

# One PCA sample per this many square millimetres of triangle area (3D path).
DEFAULT_REFERENCE_FACE_AREA_MM2 = 100.0


@dataclass(frozen=True)
class OrientationResult:
    """Oriented bounding box metadata for one snapshot geometry block."""

    bbx: Tuple[float, float, float]
    bbx_origin: Tuple[float, float, float]
    pca_frame: FrameDict


def identity_frame() -> FrameDict:
    """World-aligned frame at the origin (legacy ``iframe`` default)."""
    return {
        'o': [0.0, 0.0, 0.0],
        'x': [1.0, 0.0, 0.0],
        'y': [0.0, 1.0, 0.0],
        'z': [0.0, 0.0, 1.0],
    }


def principal_components_to_frame(
    principal_components: np.ndarray,
    origin: Sequence[float] = (0.0, 0.0, 0.0),
) -> FrameDict:
    """
    Build a ``ComponentFrame`` dict from a (3, 3) principal-component matrix.
    """
    return {
        'o': [float(origin[0]), float(origin[1]), float(origin[2])],
        'x': principal_components[0].astype(float).tolist(),
        'y': principal_components[1].astype(float).tolist(),
        'z': principal_components[2].astype(float).tolist(),
    }


def center_points(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Translate *points* so their centroid is at the origin.

    Returns ``(centered_points, translation_vector)`` where
    ``translation_vector`` is ``-centroid`` (same convention as GH create).
    """
    if points.size == 0:
        raise ValueError('Cannot center an empty point cloud')
    centroid = np.mean(points, axis=0)
    translation = -centroid
    return points + translation, translation


def minimum_bounding_rectangle(
    points_2d: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """
    Minimum-area bounding rectangle of 2D points (convex-hull edge sweep).

    Port of ``DDU_CSC_CreateComponent.minimum_bounding_rectangle``.

    Returns:
        Rectangle corners (4, 2) and ``optimal_angle`` (radians).
    """
    if points_2d.shape[0] < 3:
        raise ValueError(
            f'Need at least 3 points for minimum bounding rectangle, '
            f'got {points_2d.shape[0]}'
        )

    hull = ConvexHull(points_2d)
    hull_points = points_2d[hull.vertices]

    min_area = float('inf')
    best_rectangle: Optional[np.ndarray] = None
    best_angle = 0.0

    for i in range(len(hull_points)):
        p1 = hull_points[i]
        p2 = hull_points[(i + 1) % len(hull_points)]
        edge_vec = p2 - p1
        angle = np.arctan2(edge_vec[1], edge_vec[0])
        cos_angle = np.cos(-angle)
        sin_angle = np.sin(-angle)
        rot_matrix = np.array([
            [cos_angle, -sin_angle],
            [sin_angle, cos_angle],
        ])
        rotated_points = np.dot(points_2d, rot_matrix.T)

        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])
        area = (max_x - min_x) * (max_y - min_y)

        if area < min_area:
            min_area = area
            best_angle = angle
            best_rectangle = np.array([
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
            ])
            inv_rot_matrix = np.array([
                [cos_angle, sin_angle],
                [-sin_angle, cos_angle],
            ])
            best_rectangle = np.dot(best_rectangle, inv_rot_matrix.T)

    if best_rectangle is None:
        raise ValueError('Failed to compute minimum bounding rectangle')

    return best_rectangle, best_angle


def compute_obb_3d(
    points: np.ndarray,
) -> Tuple[List[float], np.ndarray, List[float]]:
    """
    3D OBB via sklearn PCA on a point cloud.

    Port of ``DDU_CSC_CreateComponent.compute_obb_3d``.

    Returns:
        ``dimensions`` (unsorted, PCA axis order),
        ``principal_components`` (3, 3) row vectors,
        ``bbx_origin`` (center of OBB in PCA space).
    """
    if points.shape[0] < 3:
        raise ValueError(
            f'Need at least 3 points for 3D OBB/PCA, got {points.shape[0]}'
        )

    pca = PCA(n_components=3)
    pca.fit(points)
    principal_components = np.array(pca.components_, dtype=np.float64)

    det = np.linalg.det(principal_components)
    if det < 0:
        principal_components[2] = -principal_components[2]

    pca_points = np.dot(points, principal_components.T)
    min_bounds = np.min(pca_points, axis=0)
    max_bounds = np.max(pca_points, axis=0)
    dimensions = max_bounds - min_bounds
    bbx_origin = (min_bounds + max_bounds) / 2.0

    return dimensions.tolist(), principal_components, bbx_origin.tolist()


def compute_obb_2d(
    points: np.ndarray,
    height: float,
) -> Tuple[List[float], np.ndarray, List[float]]:
    """
    Extrusion OBB via 2D minimum bounding rectangle + extrusion height.

    Port of ``DDU_CSC_CreateComponent.compute_obb_2d``.

    Args:
        points: (N, 3) sample points (typically extrusion solid corners).
        height: Extrusion extent along Z (stored as third ``bbx`` dimension).
    """
    if points.shape[0] < 3:
        raise ValueError(
            f'Need at least 3 points for 2D OBB, got {points.shape[0]}'
        )
    if height <= 0:
        raise ValueError(f'Extrusion height must be positive, got {height}')

    points_2d = points[:, :2]
    _, optimal_angle = minimum_bounding_rectangle(points_2d)

    cos_angle = np.cos(-optimal_angle)
    sin_angle = np.sin(-optimal_angle)
    rot_matrix = np.array([
        [cos_angle, -sin_angle],
        [sin_angle, cos_angle],
    ])
    rotated_points = np.dot(points_2d, rot_matrix.T)

    min_x = np.min(rotated_points[:, 0])
    max_x = np.max(rotated_points[:, 0])
    min_y = np.min(rotated_points[:, 1])
    max_y = np.max(rotated_points[:, 1])
    x_dim = max_x - min_x
    y_dim = max_y - min_y

    bbx_center_2d = [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0]
    min_z = np.min(points[:, 2])
    max_z = np.max(points[:, 2])
    z_center = (min_z + max_z) / 2.0
    bbx_origin = [bbx_center_2d[0], bbx_center_2d[1], z_center]

    if x_dim >= y_dim:
        dimensions = [x_dim, y_dim, height]
        principal_components = np.array([
            [cos_angle, -sin_angle, 0.0],
            [sin_angle, cos_angle, 0.0],
            [0.0, 0.0, 1.0],
        ])
    else:
        dimensions = [y_dim, x_dim, height]
        cos_angle_90 = np.cos(-optimal_angle + np.pi / 2)
        sin_angle_90 = np.sin(-optimal_angle + np.pi / 2)
        principal_components = np.array([
            [cos_angle_90, -sin_angle_90, 0.0],
            [sin_angle_90, cos_angle_90, 0.0],
            [0.0, 0.0, 1.0],
        ])

    return dimensions, principal_components, bbx_origin


def _triangle_area(v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> float:
    return float(0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0)))


def sample_points_area_weighted(
    vertices: np.ndarray,
    faces: Sequence[Sequence[int]],
    *,
    reference_face_area: float = DEFAULT_REFERENCE_FACE_AREA_MM2,
    min_samples_per_face: int = 1,
) -> np.ndarray:
    """Build a PCA point cloud by repeating face centroids weighted by area."""
    if vertices.size == 0:
        raise ValueError('Cannot sample from empty vertices')
    if not faces:
        return np.asarray(vertices, dtype=np.float64)

    samples: List[np.ndarray] = []
    ref_area = max(reference_face_area, 1e-6)

    for face in faces:
        idx = [int(i) for i in face]
        if len(idx) == 3:
            triangles = [idx]
        elif len(idx) == 4:
            triangles = [[idx[0], idx[1], idx[2]], [idx[0], idx[2], idx[3]]]
        else:
            raise ValueError(
                f'Faces must be triangles or quads, got {len(idx)} indices'
            )

        for tri in triangles:
            v0, v1, v2 = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
            area = _triangle_area(v0, v1, v2)
            count = max(
                min_samples_per_face,
                int(round(area / ref_area)),
            )
            centroid = (v0 + v1 + v2) / 3.0
            samples.extend([centroid] * count)

    if not samples:
        return np.asarray(vertices, dtype=np.float64)

    return np.vstack(samples)


def _mesh_primitive_vertices_faces(
    mesh: Dict[str, Any],
) -> Tuple[np.ndarray, List[List[int]]]:
    vertices_raw = mesh.get('vertices') or mesh.get('v')
    faces_raw = mesh.get('faces') or mesh.get('f')
    if not vertices_raw or not faces_raw:
        raise ValueError('Mesh primitive requires vertices and faces')
    return (
        np.asarray(vertices_raw, dtype=np.float64),
        [[int(i) for i in face] for face in faces_raw],
    )


def _collect_mesh_sample_points(
    meshes: Sequence[Dict[str, Any]],
    *,
    use_area_weighted_sampling: bool,
    reference_face_area: float,
) -> np.ndarray:
    chunks: List[np.ndarray] = []
    for mesh in meshes:
        vertices, faces = _mesh_primitive_vertices_faces(mesh)
        if use_area_weighted_sampling:
            chunks.append(
                sample_points_area_weighted(
                    vertices,
                    faces,
                    reference_face_area=reference_face_area,
                )
            )
        else:
            chunks.append(vertices)
    return np.vstack(chunks)


def extrusion_corner_points_3d(
    profile: Sequence[Sequence[float]],
    height: float,
) -> np.ndarray:
    """
    Sample points at bottom/top of an extrusion profile
    (GH brep-vertex analogue).

    Uses the same Z convention as ``create_mesh_from_extrusion``:
    bottom at ``-height/2``, top at ``+height/2``.
    """
    profile_array = np.asarray(profile, dtype=np.float64)
    if profile_array.ndim != 2 or profile_array.shape[1] != 2:
        raise ValueError('Extrusion profile must be [x, y] pairs')
    if len(profile_array) < 3:
        raise ValueError(
            ('Extrusion profile must have at least '
             f'3 points, got {len(profile_array)}')
        )
    if height <= 0:
        raise ValueError(f'Extrusion height must be positive, got {height}')

    if np.allclose(profile_array[0], profile_array[-1]):
        profile_array = profile_array[:-1]

    z_bottom = -height / 2.0
    z_top = height / 2.0
    bottom = np.hstack([
        profile_array,
        np.full((len(profile_array), 1), z_bottom),
    ])
    top = np.hstack([
        profile_array,
        np.full((len(profile_array), 1), z_top),
    ])
    return np.vstack([bottom, top])


def _extrusion_sample_points_area_weighted(
    profile: Sequence[Sequence[float]],
    height: float,
    *,
    reference_face_area: float,
) -> np.ndarray:
    mesh = create_mesh_from_extrusion(list(profile), float(height))
    return sample_points_area_weighted(
        np.asarray(mesh.vertices, dtype=np.float64),
        mesh.faces.tolist(),
        reference_face_area=reference_face_area,
    )


def _normalize_extrusions(geometry: GeometryDict) -> List[Dict[str, Any]]:
    extrusions = list(geometry.get('extrusions') or [])
    if extrusions:
        return extrusions
    legacy = geometry.get('extrusion')
    if legacy:
        return [legacy]
    return []


def _normalize_meshes(geometry: GeometryDict) -> List[Dict[str, Any]]:
    return list(geometry.get('meshes') or [])


def compute_snapshot_orientation(
    geometry: GeometryDict,
    *,
    assembly: bool = False,
    use_area_weighted_sampling: bool = True,
    reference_face_area: float = DEFAULT_REFERENCE_FACE_AREA_MM2,
) -> OrientationResult:
    """
    Compute ``bbx``, ``bbx_origin``, and ``pca_frame`` for snapshot geometry.

    Routing (matches GH create-component behaviour):
        * **Meshes present** - 3D PCA (area-weighted samples when enabled).
          Multiple meshes: all meshes when ``assembly=True``, else first only.
        * **Extrusions only, single primitive** - 2D MBR / ``compute_obb_2d``.
        * **Extrusions only, multiple** - 3D PCA on combined
          area-weighted samples.

    Raises:
        ValueError: when no supported geometry representation is present.
    """
    meshes = _normalize_meshes(geometry)
    extrusions = _normalize_extrusions(geometry)

    if meshes:
        selected = meshes if assembly else [meshes[0]]
        points = _collect_mesh_sample_points(
            selected,
            use_area_weighted_sampling=use_area_weighted_sampling,
            reference_face_area=reference_face_area,
        )
        centered, _ = center_points(points)
        dimensions, principal_components, bbx_origin = compute_obb_3d(centered)
    elif len(extrusions) == 1:
        ext = extrusions[0]
        profile = ext.get('profile') or []
        height = float(ext.get('height') or 0)
        points = extrusion_corner_points_3d(profile, height)
        centered, _ = center_points(points)
        dimensions, principal_components, bbx_origin = compute_obb_2d(
            centered,
            height,
        )
    elif len(extrusions) > 1:
        chunks = [
            _extrusion_sample_points_area_weighted(
                ext.get('profile') or [],
                float(ext.get('height') or 0),
                reference_face_area=reference_face_area,
            )
            for ext in extrusions
        ]
        points = np.vstack(chunks)
        centered, _ = center_points(points)
        dimensions, principal_components, bbx_origin = compute_obb_3d(centered)
    else:
        keys = list(geometry.keys())
        raise ValueError(
            'geometry must include meshes or extrusions for orientation, '
            f'got keys: {keys}'
        )

    return OrientationResult(
        bbx=(float(dimensions[0]), float(dimensions[1]), float(dimensions[2])),
        bbx_origin=(
            float(bbx_origin[0]),
            float(bbx_origin[1]),
            float(bbx_origin[2]),
        ),
        pca_frame=principal_components_to_frame(principal_components),
    )


def orientation_result_to_dict(result: OrientationResult) -> Dict[str, Any]:
    """Serialize an ``OrientationResult`` for Mongo / API payloads."""
    return {
        'bbx': list(result.bbx),
        'bbx_origin': list(result.bbx_origin),
        'pca_frame': result.pca_frame,
    }
