#!/usr/bin/env python3.13
"""
Stage 3 of the geometry runner: fit the primary proxy (spec section 4.3).

``fit_primary`` walks the fit preference of the shape class (section 6) and
returns the proxy document with its residuals and deviation maps, plus the
map files to store. Pure: no database, no disk.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass
from typing import Any, Dict, Tuple

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

RESIDUAL_SAMPLE = 50_000
PRISM_LINEAR_TOLERANCE = 0.05       # p95 of a linear prism, of the middle extent


@dataclass
class Residuals:
    n: int
    rms: float
    p95: float
    maximum: float
    inlier_ratio: float


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
            bbx: Tuple[float, float, float]) -> bool:
    if name == 'prism' and shape_class == 'linear':
        return stats.p95 <= PRISM_LINEAR_TOLERANCE * sorted(bbx)[1]
    return True


def fit_primary(source: Source, frame: Dict[str, list],
                bbx: Tuple[float, float, float], shape_class: str,
                snapshot_id: str, index: int, computed_at: str
                ) -> Tuple[Dict[str, Any], Dict[str, bytes]]:
    """The fitted primary proxy document and its deviation-map files."""
    points = source.points()
    sample = sample_surface(source, RESIDUAL_SAMPLE)
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
        if _accept(name, shape_class, stats, bbx):
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
