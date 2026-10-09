#!/usr/bin/env python3.13
"""
Heat kernel signature of a component (stage 4, decision 8.6).

HKS is computed on ``HKS_POINTS`` points spread evenly over the component's
surface with ``robust_laplacian.point_cloud_laplacian``, never on the mesh
topology and never on the convex hull:

1. Sample: meshes and authored primitives area-uniformly, point clouds
   thinned to the same size; fixed seed; all component geometry, never
   ``capture`` markers or fixtures (I23).
2. ``HKS_EIGS`` non-zero eigenpairs of ``L phi = lambda M phi``; the time
   grid is **fixed in area-normalised units** (one grid for the catalogue,
   not per shape), so values compare across pieces. The grid was derived
   once on dump 260916 by ``scripts/dev/derive_hks_grid.py`` and is frozen.
3. Per-point HKS, mass-weighted mean + variance pooling, L2-normalised
   (``hks_features.py``).

Intrinsic, so it needs no frame. A shape that cannot be sampled or
decomposed raises; the runner records the error.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import List, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_source import Source
from apps.catalog.proxies.sampling import SAMPLE_SEED, thinned_points
from apps.descriptors.hks_features import (
    build_laplacian_from_points,
    hks_from_eigendecomp,
    lap_eigendecomp,
    pool_hks,
)

HKS_VERSION = 1

HKS_POINTS = 3000
HKS_EIGS = 64
HKS_NEIGHBOURS = 30
HKS_TIMES = 16

# Frozen time grid in area-normalised units: logspace(HKS_T_MIN, HKS_T_MAX,
# HKS_TIMES). Derived on dump 260916 (see the module docstring).
# 238 mesh folders of 260916, geometric mean of each shape's own bounds
# (per-shape t_min 4.2e-3 .. 6.4e-3, t_max 0.17 .. 4.0).
HKS_T_MIN = 5.187876e-03
HKS_T_MAX = 3.454702e-01


def hks_time_grid() -> np.ndarray:
    return np.logspace(np.log10(HKS_T_MIN), np.log10(HKS_T_MAX), HKS_TIMES)


def spectrum(source: Source) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(eigenvalues, eigenvectors, mass diagonal)`` of the sampled shape."""
    points = thinned_points(source, HKS_POINTS, SAMPLE_SEED)
    if len(points) < HKS_NEIGHBOURS:
        raise ValueError(f'only {len(points)} surface points; HKS needs '
                         f'at least {HKS_NEIGHBOURS}')
    laplacian, mass = build_laplacian_from_points(
        points, n_neighbors=HKS_NEIGHBOURS)
    start = np.random.default_rng(SAMPLE_SEED).standard_normal(len(points))
    evals, evecs = lap_eigendecomp(laplacian, mass, n_eigs=HKS_EIGS,
                                   v0=start)
    return evals, evecs, np.asarray(mass.diagonal()).ravel()


def compute_hks(source: Source) -> List[float]:
    """The pooled, L2-normalised HKS descriptor: ``2 * HKS_TIMES`` floats
    (mass-weighted mean then variance per time)."""
    evals, evecs, mass = spectrum(source)
    per_point = hks_from_eigendecomp(evals, evecs, hks_time_grid(), mass)
    return [float(v) for v in pool_hks(per_point, mass)]
