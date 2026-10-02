#!/usr/bin/env python3.13
"""
Proxy registry (data model spec section 4.3), mirroring
``descriptors/registry.py``: one ``ProxySpec`` per primitive; the stage
loops over the registry and never names a primitive.

A spec knows how to **fit** the primitive to a snapshot's geometry, how to
measure the **signed distance** of points to it, and how it **unwraps** onto
faces for the deviation maps (appendix B).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.geometry_source import Source
from apps.catalog.proxies.sampling import Sample

PROXIES_VERSION = 1


@dataclass
class FitContext:
    """Everything a fit may read (stage 3 inputs)."""
    source: Source
    frame: Dict[str, list]                   # stage 1, stored coordinates
    bbx: Tuple[float, float, float]          # extents along frame x / y / z
    shape_class: str
    points: np.ndarray                       # all component points
    sample: Sample                           # seeded surface sample


@dataclass
class Fitted:
    """A fitted primitive before residuals and maps."""
    primitive: str
    params: Dict[str, Any]
    placement: Dict[str, list]
    method: str                              # obb | lsq | ransac | hull
    inlier_ratio: Optional[float] = None     # ransac only


@dataclass
class FaceUnwrap:
    """Points mapped onto the faces of a primitive (local coordinates)."""
    face: np.ndarray                         # (n,) index into ``faces``
    u: np.ndarray
    v: np.ndarray
    face_normal: np.ndarray                  # (n, 3) of each point's face


@dataclass(frozen=True)
class ProxySpec:
    """Static declaration of one primitive.

    ``fit`` returns None when the primitive does not describe the geometry;
    ``sdf(params, local_points)`` is signed (positive outside);
    ``faces(params)`` lists the ``face_id`` values; ``extent(params, face)``
    gives the ``(u0, u1, v0, v1)`` of a face's map; ``unwrap`` assigns
    points to faces.
    """
    name: str
    fit: Callable[[FitContext], Optional[Fitted]]
    sdf: Callable[[Dict[str, Any], np.ndarray], np.ndarray]
    faces: Callable[[Dict[str, Any]], List[str]]
    extent: Callable[[Dict[str, Any], str], Tuple[float, float, float, float]]
    unwrap: Callable[[Dict[str, Any], np.ndarray], FaceUnwrap]
    applicable_shape_classes: Sequence[str] = field(default_factory=tuple)
    inlier_tolerance_mm: float = 3.0
    angular_map: bool = False               # (theta, phi) map (hull)


# Fit order per shape class (spec section 6): the first spec whose fit
# accepts the geometry wins; the last entry always fits.
FIT_PREFERENCE: Dict[str, Tuple[str, ...]] = {
    'linear': ('cylinder', 'prism', 'box'),
    'planar': ('prism', 'box'),
    'block': ('box',),
    'irregular': ('hull', 'box'),
    'composite': ('box',),
}
