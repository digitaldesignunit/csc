#!/usr/bin/env python3.13
"""
Stage 3 of the geometry runner: fit the primary proxy (spec section 4.3).

``fit_primary`` walks the fit preference of the shape class (section 6) and
returns the proxy document with its residuals and deviation maps, plus the
map files to store. Pure: no database, no disk.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_source import Source
from apps.catalog.proxies.deviation import (
    build_deviation_maps,
    resolution_for,
)
from apps.catalog.proxies.primitives import to_local
from apps.catalog.proxies.registry import (
    FIT_PREFERENCE,
    PROXIES_VERSION,
    FitContext,
    Fitted,
    ProxySpec,
)
from apps.catalog.proxies.sampling import sample_surface
from apps.catalog.proxies.specs import ALL_PROXY_SPECS

RESIDUAL_SAMPLE_MIN = 50_000
RESIDUAL_SAMPLE_MAX = 300_000
POINTS_PER_CELL = 3                 # of a deviation map, over the sampled area
PRISM_LINEAR_TOLERANCE = 0.05       # p95 of a linear prism, of the middle extent
# p95 of a planar prism, of the thickness (8.121 d). The prisms of the real
# planar pieces of the 261001 dump (scanned rubble, 11 pieces) have a p95 of
# 0.07 to 0.39 of their thickness, the prisms of notched slabs 0.003 to 0.006;
# an outline that is wrong (a plain rectangular wall gave 7.6) is off by more
# than the slab is thick. One thickness separates the two with room on both
# sides: past it the prism no longer says where the piece is.
PRISM_PLANAR_TOLERANCE = 1.0


@dataclass
class Residuals:
    n: int
    rms: float
    p95: float
    maximum: float
    inlier_ratio: float


def residual_sample_size(source: Source, bbx: Tuple[float, float, float]
                         ) -> int:
    """The surface sample sized to the deviation maps (8.119): about
    ``POINTS_PER_CELL`` points per map cell of the sampled surface area (a
    cell is ``resolution_for(max(bbx))`` squared), at least
    ``RESIDUAL_SAMPLE_MIN`` and at most ``RESIDUAL_SAMPLE_MAX``. The area is
    the mesh area; a point cloud has none, so its bounding box stands in."""
    cell = resolution_for(max(bbx)) ** 2
    if source.meshes:
        area = float(sum(m.area for m in source.meshes))
    else:
        a, b, c = (float(v) for v in bbx)
        area = 2.0 * (a * b + b * c + a * c)
    wanted = math.ceil(POINTS_PER_CELL * area / cell)
    return int(min(RESIDUAL_SAMPLE_MAX, max(RESIDUAL_SAMPLE_MIN, wanted)))


def residuals(spec: ProxySpec, fitted: Fitted, points: np.ndarray
              ) -> Tuple[Residuals, np.ndarray, np.ndarray]:
    """Signed residual of each point to the proxy surface; the statistics,
    the local points and the signed distances."""
    local = to_local(points, fitted.placement)
    signed = spec.sdf(fitted.params, local)
    absolute = np.abs(signed)
    stats = Residuals(
        n=len(points), rms=float(np.sqrt(np.mean(absolute ** 2))),
        p95=float(np.percentile(absolute, 95)), maximum=float(absolute.max()),
        inlier_ratio=float((absolute <= spec.inlier_tolerance_mm).mean()))
    return stats, local, signed


def _accept(name: str, shape_class: str, stats: Residuals,
            bbx: Tuple[float, float, float],
            box_stats: Optional[Callable[[], Residuals]] = None) -> bool:
    """Whether a fit is kept or the next one in ``FIT_PREFERENCE`` is tried.
    A linear prism must follow the section; a planar prism (8.121 d) must be
    within ``PRISM_PLANAR_TOLERANCE`` thicknesses (p95) and no worse than the
    frame's box (``box_stats`` gives that box's residuals, computed only
    here). The comparison is the rms, not the p95: a notch or an opening
    covers a few per cent of a wall's surface, below what the p95 sees, so
    the box would tie the prism that describes it."""
    if name == 'prism' and shape_class == 'linear':
        return stats.p95 <= PRISM_LINEAR_TOLERANCE * sorted(bbx)[1]
    if name == 'prism' and shape_class == 'planar':
        if stats.p95 > PRISM_PLANAR_TOLERANCE * min(bbx):
            return False
        return box_stats is None or stats.rms <= box_stats().rms
    return True


def _box_stats(context: FitContext, sample) -> Residuals:
    """The residuals of the frame's box on the same sample (the planar prism
    has to beat them)."""
    spec = ALL_PROXY_SPECS['box']
    fitted = spec.fit(context)
    if fitted is None:
        return Residuals(n=len(sample.points), rms=float('inf'),
                         p95=float('inf'), maximum=float('inf'),
                         inlier_ratio=0.0)
    return residuals(spec, fitted, sample.points)[0]


def fit_primary(source: Source, frame: Dict[str, list],
                bbx: Tuple[float, float, float], shape_class: str,
                snapshot_id: str, index: int, computed_at: str
                ) -> Tuple[Dict[str, Any], Dict[str, bytes]]:
    """The fitted primary proxy document and its deviation-map files."""
    points = source.points()
    sample = sample_surface(source, residual_sample_size(source, bbx))
    context = FitContext(source=source, frame=frame, bbx=bbx,
                         shape_class=shape_class, points=points,
                         sample=sample)
    chosen = None
    for name in FIT_PREFERENCE.get(shape_class, ('box',)):
        spec = ALL_PROXY_SPECS[name]
        fitted = spec.fit(context)
        if fitted is None:
            continue
        stats, local, signed = residuals(spec, fitted, sample.points)
        if _accept(name, shape_class, stats, bbx,
                   lambda: _box_stats(context, sample)):
            chosen = (spec, fitted, stats, local, signed)
            break
    if chosen is None:
        raise ValueError(f'no proxy fits a {shape_class} piece')
    spec, fitted, stats, local, signed = chosen
    rotation = np.array([fitted.placement['x'], fitted.placement['y'],
                         fitted.placement['z']])
    local_normals = sample.normals @ rotation.T
    maps, files = build_deviation_maps(
        spec, fitted.params, local, local_normals, signed,
        resolution_for(max(bbx)), f'proxies/{snapshot_id}/{index}')
    document = {
        'primitive': fitted.primitive,
        'role': 'primary',
        'params': fitted.params,
        'placement': fitted.placement,
        'fit': {
            'method': fitted.method,
            'source': {'kind': source.fit_kind, 'index': 0,
                       'resolution': source.resolution},
            'n_points': int(len(points)),
            'inlier_ratio': (fitted.inlier_ratio
                             if fitted.inlier_ratio is not None
                             else stats.inlier_ratio),
            'rms_mm': stats.rms, 'max_mm': stats.maximum, 'p95_mm': stats.p95,
            'spec_version': PROXIES_VERSION, 'computed_at': computed_at,
        },
        'deviation_maps': maps,
        'regions': [],
    }
    return document, files
