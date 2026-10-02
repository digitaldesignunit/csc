#!/usr/bin/env python3.13
"""
Deviation maps (data model spec section 4.3 step 4, appendix B).

For each face of a proxy, the sample points assigned to it are projected
orthographically onto the face plane (cylinder lateral: unrolled to
``(theta * r, z)``; hull: one ``(theta, phi)`` map of the concavity depth),
binned on a regular grid at ``resolution_mm``, and aggregated per cell into
three 16-bit channels of one RGB PNG:

    R  distance          mean signed distance to the proxy surface, mm
                         (positive outward); ``value * scale_mm + offset_mm``
    G  normal_deviation  mean angle between the point normal and the face
                         normal, degrees * 100
    B  occupancy         number of points in the cell, saturating

Cell ``(column, row)`` covers ``u in [u0 + column * res, +res)`` and
``v in [v0 + row * res, +res)`` of the face extent ``(u0, u1, v0, v1)``;
an empty cell has occupancy 0 and the other channels 0.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
from typing import Any, Dict, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.proxies.png16 import encode_rgb16
from apps.catalog.proxies.registry import ProxySpec
from apps.catalog.proxies.specs import HULL_MAP_SIZE

CHANNELS = ['distance', 'normal_deviation', 'occupancy']
DEFAULT_SCALE_MM = 0.01
MAX_CELLS = 4096                         # per side of one map
NORMAL_UNIT_DEG = 0.01


def resolution_for(extent_mm: float) -> float:
    """Grid resolution: 5 mm, coarser for pieces above 2 m so no map
    exceeds a few hundred cells per side."""
    return max(5.0, float(extent_mm) / 400.0)


def _grid(extent: Tuple[float, float, float, float], resolution: float,
          angular: bool) -> Tuple[int, int]:
    if angular:
        return HULL_MAP_SIZE
    u0, u1, v0, v1 = extent
    width = max(1, min(MAX_CELLS, math.ceil((u1 - u0) / resolution)))
    height = max(1, min(MAX_CELLS, math.ceil((v1 - v0) / resolution)))
    return width, height


def _face_map(u: np.ndarray, v: np.ndarray, distance: np.ndarray,
              angle: np.ndarray, extent, size: Tuple[int, int]
              ) -> Tuple[np.ndarray, Dict[str, float]]:
    width, height = size
    u0, u1, v0, v1 = extent
    column = np.clip(((u - u0) / max(u1 - u0, 1e-12) * width).astype(int),
                     0, width - 1)
    row = np.clip(((v - v0) / max(v1 - v0, 1e-12) * height).astype(int),
                  0, height - 1)
    flat = row * width + column
    count = np.bincount(flat, minlength=width * height).astype(np.float64)
    safe = np.where(count > 0, count, 1.0)
    mean_distance = np.bincount(flat, weights=distance,
                                minlength=width * height) / safe
    mean_angle = np.bincount(flat, weights=angle,
                             minlength=width * height) / safe
    occupied = count > 0
    low = float(mean_distance[occupied].min()) if occupied.any() else 0.0
    high = float(mean_distance[occupied].max()) if occupied.any() else 0.0
    scale = max(DEFAULT_SCALE_MM, (high - low) / 65000.0)
    offset = low - scale                      # the lowest cell encodes as 1
    encoded = np.zeros((width * height, 3), dtype=np.uint16)
    encoded[occupied, 0] = np.clip(
        np.round((mean_distance[occupied] - offset) / scale), 1, 65535)
    encoded[occupied, 1] = np.clip(
        np.round(mean_angle[occupied] / NORMAL_UNIT_DEG), 0, 65535)
    encoded[:, 2] = np.minimum(count, 65535)
    return (encoded.reshape(height, width, 3),
            {'scale_mm': float(scale), 'offset_mm': float(offset)})


def build_deviation_maps(spec: ProxySpec, params: Dict[str, Any],
                         local_points: np.ndarray,
                         local_normals: np.ndarray, distance: np.ndarray,
                         resolution_mm: float, file_prefix: str
                         ) -> Tuple[Dict[str, Any], Dict[str, bytes]]:
    """``(deviation_maps document, {file: PNG bytes})`` for one proxy.

    ``file_prefix`` is ``proxies/<snapshot_id>/<index>``; every file is
    ``<file_prefix>/<face_id>.png``.
    """
    unwrap = spec.unwrap(params, local_points)
    faces = spec.faces(params)
    if spec.angular_map:
        # hull: the value is the concavity depth, never negative
        distance = np.maximum(-distance, 0.0)
    cosine = np.abs(np.einsum('ij,ij->i', local_normals, unwrap.face_normal))
    angle = np.degrees(np.arccos(np.clip(cosine, 0.0, 1.0)))
    documents: Dict[str, Any] = {}
    files: Dict[str, bytes] = {}
    for index, face in enumerate(faces):
        chosen = unwrap.face == index
        extent = spec.extent(params, face)
        size = _grid(extent, resolution_mm, spec.angular_map)
        image, scale = _face_map(unwrap.u[chosen], unwrap.v[chosen],
                                 distance[chosen], angle[chosen], extent,
                                 size)
        name = f'{file_prefix}/{face}.png'
        files[name] = encode_rgb16(image)
        documents[face] = {'file': name, 'width': size[0], 'height': size[1],
                           'distance': scale}
    return ({'resolution_mm': float(resolution_mm), 'channels': CHANNELS,
             'faces': documents}, files)
