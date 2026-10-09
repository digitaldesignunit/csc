#!/usr/bin/env python3.13
"""
Seeded surface samples of the component geometry (spec section 4.3).

Meshes (and authored primitives, which load as meshes) are sampled
area-uniformly; point clouds are thinned to the same size. The seed is
fixed, so a re-run on the same input gives the same sample. Used by the
proxy residuals, the deviation maps and the HKS descriptor.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass
from typing import Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from scipy.spatial import cKDTree

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_source import Source

SAMPLE_SEED = 20261002
NORMAL_NEIGHBOURS = 16


@dataclass
class Sample:
    """Points on the component's surface, with a unit normal per point."""
    points: np.ndarray                  # (n, 3) float64
    normals: np.ndarray                 # (n, 3) float64


def _cloud_normals(points: np.ndarray) -> np.ndarray:
    """Normals of a cloud: smallest principal axis of each neighbourhood,
    oriented away from the cloud's centroid (a closed scan's outside)."""
    k = min(NORMAL_NEIGHBOURS, len(points))
    if k < 3:
        return np.tile([0.0, 0.0, 1.0], (len(points), 1))
    _, neighbours = cKDTree(points).query(points, k=k)
    around = points[neighbours]
    local = around - around.mean(axis=1, keepdims=True)
    covariance = np.einsum('nki,nkj->nij', local, local)
    _, vectors = np.linalg.eigh(covariance)
    normals = vectors[:, :, 0]
    outward = points - points.mean(axis=0)
    flip = np.einsum('ij,ij->i', normals, outward) < 0
    normals[flip] *= -1
    norm = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.where(norm > 0, norm, 1.0)


def sample_surface(source: Source, count: int,
                   seed: int = SAMPLE_SEED) -> Sample:
    """``count`` surface points of the source (fewer if it has fewer)."""
    rng = np.random.default_rng(seed)
    mesh = source.mesh()
    if mesh is not None and len(mesh.faces):
        areas = mesh.area_faces
        total = float(areas.sum())
        if total > 0:
            faces = rng.choice(len(areas), size=count, p=areas / total)
            triangles = mesh.triangles[faces]
            u = rng.random((count, 1))
            v = rng.random((count, 1))
            fold = (u + v) > 1.0
            u[fold], v[fold] = 1.0 - u[fold], 1.0 - v[fold]
            points = (triangles[:, 0]
                      + u * (triangles[:, 1] - triangles[:, 0])
                      + v * (triangles[:, 2] - triangles[:, 0]))
            return Sample(points, np.asarray(mesh.face_normals[faces],
                                             dtype=np.float64))
    points = source.points()
    if len(points) > count:
        points = points[np.sort(rng.choice(len(points), size=count,
                                           replace=False))]
    return Sample(points, _cloud_normals(points))


def thinned_points(source: Source, count: int,
                   seed: int = SAMPLE_SEED) -> np.ndarray:
    """Just the points of ``sample_surface`` (HKS input)."""
    return sample_surface(source, count, seed).points


def vertex_subsample(points: np.ndarray, count: Optional[int],
                     seed: int = SAMPLE_SEED) -> np.ndarray:
    """A seeded subset of ``points`` (all of them when few)."""
    if count is None or len(points) <= count:
        return points
    rng = np.random.default_rng(seed)
    return points[np.sort(rng.choice(len(points), size=count,
                                     replace=False))]
