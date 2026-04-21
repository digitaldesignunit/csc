#!/usr/bin/env python3.9
"""
Radial shape signature for planar (sheet / panel) components.

Given the 2D boundary polyline of a planar part, this descriptor:

1. Translates the outline so its centroid lies at the origin.
2. Rotates it into a canonical "rest position" (min-distance-to-bbox-edge
   orientation, ported from the legacy C# RestPosition algorithm).
3. Casts N evenly spaced rays outward from the origin and records, for each
   ray, the distance from the origin to the first boundary intersection
   together with the boundary tangent at that intersection.

The resulting descriptors are known in the shape-analysis literature as the
*centroid distance function* (Zhang & Lu, 2004) and an accompanying
*boundary tangent signature*. They are rotation-canonical (via rest
position), translation-invariant (centered at the centroid), and easy to
compare at a fixed resolution.

The module is intentionally restricted to planar component types because
the signature is only meaningful when a single closed planar polyline
describes the component's outline.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np


# MODULE CONSTANTS ------------------------------------------------------------

APPLICABLE_COMPONENT_TYPES: Tuple[str, ...] = ("sheet", "panel")
"""Component types this descriptor is valid for.

`panel` is included ahead of the locked `sheet -> panel` migration
(see IMPLEMENTATION_PLAN.md, ADR-002) so no change is required at cutover.
"""

SUPPORTED_RESOLUTIONS: Tuple[int, ...] = (16, 32, 64)
"""Canonical ray counts exposed by the module."""

DEFAULT_REST_ANGLES: int = 180
"""Sample count over [0, pi) for rest-position search.

1 degree steps. This is intentionally ~5x finer than the finest ray
spacing (5.625 degrees at N=64) so rest-position quantization does not
dominate the descriptor noise floor. The legacy C# implementation used
40 samples (4.5 degrees) which is too coarse for N=64.
"""

# Points closer than this are treated as coincident; matches the default
# Rhino model absolute tolerance used in the original Grasshopper script.
_COINCIDENT_EPS: float = 1e-9


# APPLICABILITY --------------------------------------------------------------


def get_profile_from_component(
    component: Dict,
) -> Tuple[Optional[List[List[float]]], Optional[str]]:
    """Return the extrusion profile of a component, or an error reason.

    On success returns ``(profile, None)``; on failure ``(None, reason)``
    with a short human-readable explanation suitable for logging.
    """
    geometry = component.get("geometry") or {}
    extrusion = geometry.get("extrusion") or {}
    profile = extrusion.get("profile")
    if not profile:
        return None, "no extrusion profile"
    if len(profile) < 3:
        return None, (
            f"extrusion profile has only {len(profile)} points, need >= 3"
        )
    return profile, None


def is_applicable(component: Dict) -> bool:
    """Return True if the radial signature can be computed for `component`.

    The component must be of an applicable planar type and carry an
    extrusion profile (the canonical boundary polyline for sheets/panels).
    """
    ctype = component.get("type") or component.get("componenttype")
    if ctype not in APPLICABLE_COMPONENT_TYPES:
        return False
    profile, _ = get_profile_from_component(component)
    return profile is not None


# GEOMETRY PRIMITIVES --------------------------------------------------------


def _as_profile_array(profile: Sequence[Sequence[float]]) -> np.ndarray:
    """Validate and return an (M, 2) float array of profile points."""
    P = np.asarray(profile, dtype=np.float64)
    if P.ndim != 2 or P.shape[1] != 2:
        raise ValueError(
            f"profile must be a sequence of [x, y] pairs, got shape {P.shape}"
        )
    if len(P) < 3:
        raise ValueError(
            f"profile must have at least 3 points, got {len(P)}"
        )
    # Drop a duplicate closing vertex if present; we always treat the
    # polyline as an implicit closed polygon.
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
        if len(P) < 3:
            raise ValueError(
                "profile collapses to fewer than 3 unique points"
            )
    return P


def polygon_centroid_2d(profile: Sequence[Sequence[float]]) -> np.ndarray:
    """Return the area-weighted centroid of a closed 2D polygon (shoelace).

    Matches Rhino's AreaMassProperties.Compute(crv).Centroid for a closed
    planar curve. Falls back to the vertex mean for degenerate (zero-area)
    polygons.
    """
    P = _as_profile_array(profile)
    x, y = P[:, 0], P[:, 1]
    xn = np.roll(x, -1)
    yn = np.roll(y, -1)
    cross = x * yn - xn * y
    area2 = cross.sum()
    if abs(area2) < _COINCIDENT_EPS:
        return P.mean(axis=0)
    cx = ((x + xn) * cross).sum() / (3.0 * area2)
    cy = ((y + yn) * cross).sum() / (3.0 * area2)
    return np.array([cx, cy], dtype=np.float64)


def _rotation_matrix(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


# REST POSITION --------------------------------------------------------------


def rest_position(
    profile: Sequence[Sequence[float]],
    num_angles: int = DEFAULT_REST_ANGLES,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Rotate a planar outline into its canonical rest position.

    Faithful port of the legacy C# `RestPosition` routine. For each of
    `num_angles` sample angles in [0, pi), the profile (already centered at
    its centroid) is rotated and the absolute distance from the origin to
    each of the four axis-aligned bounding-box edges is measured. The
    sample that produces the smallest such distance, combined with a
    90 degree correction indexed by which edge was closest, defines the
    canonical rotation.

    Args:
        profile: Sequence of [x, y] vertices describing the closed boundary.
        num_angles: Number of rotation samples over [0, pi). Defaults to
            `DEFAULT_REST_ANGLES` (180, i.e. 1 degree steps). Must be >= 1.

    Returns:
        Tuple of:
            - rotated_profile: (M, 2) array, centered and rotated into rest.
            - centroid: (2,) array, the centroid subtracted from the input.
            - angle_deg: rotation applied to the centered profile, in degrees.

    Raises:
        ValueError: if the profile is invalid or `num_angles < 1`.
    """
    if num_angles < 1:
        raise ValueError(f"num_angles must be >= 1, got {num_angles}")

    P = _as_profile_array(profile)
    centroid = polygon_centroid_2d(P)
    P_centered = P - centroid

    step_deg = 180.0 / num_angles
    # Vectorise the sweep: (num_angles, M, 2) rotated copies would blow up
    # memory on very dense profiles; iterate but keep the inner bbox work
    # vectorised per angle.
    min_edge_distances = np.empty(num_angles, dtype=np.float64)
    min_edge_corners = np.empty(num_angles, dtype=np.int64)
    for i in range(num_angles):
        ang_rad = np.deg2rad(i * step_deg)
        R = _rotation_matrix(ang_rad)
        Q = P_centered @ R.T
        xmin, ymin = Q.min(axis=0)
        xmax, ymax = Q.max(axis=0)
        # Replicates the original ordering of the four candidate edges:
        # |ymin|, |xmax|, |ymax|, |xmin|. Index of the min is the
        # 90 degree correction bucket used below.
        edges = np.array([abs(ymin), abs(xmax), abs(ymax), abs(xmin)])
        j = int(np.argmin(edges))
        min_edge_distances[i] = edges[j]
        min_edge_corners[i] = j

    best_sample = int(np.argmin(min_edge_distances))
    corner = int(min_edge_corners[best_sample])
    angle_deg = -(corner * 90.0) + best_sample * step_deg
    angle_rad = np.deg2rad(angle_deg)
    R_final = _rotation_matrix(angle_rad)
    P_rotated = P_centered @ R_final.T
    return P_rotated, centroid, float(angle_deg)


# RAY - POLYLINE INTERSECTION -----------------------------------------------


def _ray_polyline_distances_and_tangents(
    profile: np.ndarray,
    directions: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """For each ray direction, return (distance, tangent) of the first hit.

    Rays originate at (0, 0) and extend in the given unit direction.
    Segments are the implicit closed polygon edges p_i -> p_(i+1 mod M).

    For each ray-segment pair solves t*R - s*D = A (ray parameter t >= 0,
    segment parameter s in [0, 1]). The smallest valid `t` wins, and the
    tangent at that hit is the unit direction of the hit segment.

    Args:
        profile: (M, 2) array of polygon vertices.
        directions: (N, 2) array of unit ray directions.

    Returns:
        distances: (N,) array of ray->boundary distances. NaN where no hit.
        tangents:  (N, 2) array of boundary tangents (unit). NaN where no hit.
    """
    A = profile                       # (M, 2) segment starts
    B = np.roll(profile, -1, axis=0)  # (M, 2) segment ends
    D = B - A                         # (M, 2) segment direction vectors

    seg_len = np.linalg.norm(D, axis=1)
    # Avoid zero-length segments contaminating the intersection math.
    valid_seg = seg_len > _COINCIDENT_EPS
    # Unit tangents per segment (NaN for degenerate segments).
    T = np.full_like(D, np.nan)
    T[valid_seg] = D[valid_seg] / seg_len[valid_seg, None]

    # 2D cross product helpers: cross(u, v) = u.x*v.y - u.y*v.x
    # Vectorise over (N rays, M segments).
    # Shapes: R (N, 2), D (M, 2), A (M, 2).
    R = directions  # (N, 2)

    # denom[n, m] = R[n] x D[m]
    denom = R[:, 0:1] * D[None, :, 1] - R[:, 1:2] * D[None, :, 0]  # (N, M)
    # t[n, m] = A[m] x D[m] / denom[n, m]  (does not depend on ray for numer)
    A_cross_D = A[:, 0] * D[:, 1] - A[:, 1] * D[:, 0]              # (M,)
    # s[n, m] = A[m] x R[n] / denom[n, m]
    # A_cross_R[n, m] = A[m].x * R[n].y - A[m].y * R[n].x
    A_cross_R = (A[None, :, 0] * R[:, 1:2]
                 - A[None, :, 1] * R[:, 0:1])                      # (N, M)

    # Mask out parallels and degenerate segments.
    safe = (np.abs(denom) > _COINCIDENT_EPS) & valid_seg[None, :]
    denom_safe = np.where(safe, denom, 1.0)

    t = A_cross_D[None, :] / denom_safe                            # (N, M)
    s = A_cross_R / denom_safe                                     # (N, M)

    # Valid intersections: forward along ray, within segment bounds.
    hit = (
        safe
        & (t >= 0.0)
        & (s >= -_COINCIDENT_EPS)
        & (s <= 1.0 + _COINCIDENT_EPS)
    )

    # Pick smallest positive t per ray.
    t_masked = np.where(hit, t, np.inf)
    best_seg = np.argmin(t_masked, axis=1)                         # (N,)
    best_t = t_masked[np.arange(len(R)), best_seg]                 # (N,)

    miss = ~np.isfinite(best_t)
    distances = np.where(miss, np.nan, best_t)
    tangents = T[best_seg]                                          # (N, 2)
    tangents[miss] = np.nan
    return distances, tangents


# HIGH-LEVEL DESCRIPTOR ------------------------------------------------------


def compute_radial_signature(
    profile: Sequence[Sequence[float]],
    num_rays: int,
    rest_align: bool = True,
    num_rest_angles: int = DEFAULT_REST_ANGLES,
) -> Dict[str, object]:
    """Compute the radial signature at a single resolution.

    Args:
        profile: Sequence of [x, y] vertices. Treated as a closed polygon.
        num_rays: Number of rays (e.g. 16, 32, 64). Must be >= 3.
        rest_align: If True (default), apply `rest_position` before ray
            casting. If False, use the profile as-is (still centered at the
            centroid).
        num_rest_angles: Sample count for the rest-position search.

    Returns:
        Dictionary with keys:
            - 'distances':   List[float] of length `num_rays`.
            - 'tangents':    List[[tx, ty]] of length `num_rays`.
            - 'num_rays':    int.
            - 'rest_angle_deg': float rotation applied by rest_position
                               (0.0 if `rest_align` is False).

    Raises:
        ValueError: on invalid input or if a ray fails to hit the boundary
            (should not happen for a simple polygon containing the centroid).
    """
    if num_rays < 3:
        raise ValueError(f"num_rays must be >= 3, got {num_rays}")

    if rest_align:
        P_rest, _centroid, rest_angle_deg = rest_position(
            profile, num_angles=num_rest_angles
        )
    else:
        P = _as_profile_array(profile)
        P_rest = P - polygon_centroid_2d(P)
        rest_angle_deg = 0.0

    angles = np.arange(num_rays) * (2.0 * np.pi / num_rays)
    directions = np.column_stack([np.cos(angles), np.sin(angles)])

    distances, tangents = _ray_polyline_distances_and_tangents(
        P_rest, directions
    )

    if np.any(np.isnan(distances)):
        missed = int(np.isnan(distances).sum())
        raise ValueError(
            f"{missed}/{num_rays} rays did not intersect the boundary; "
            f"centroid may lie outside the profile or the polygon is "
            f"non-simple"
        )

    return {
        "distances": [float(v) for v in distances],
        "tangents": [[float(t[0]), float(t[1])] for t in tangents],
        "num_rays": int(num_rays),
        "rest_angle_deg": float(rest_angle_deg),
    }


def compute_radial_signatures(
    profile: Sequence[Sequence[float]],
    resolutions: Iterable[int] = SUPPORTED_RESOLUTIONS,
    num_rest_angles: int = DEFAULT_REST_ANGLES,
) -> Dict[int, Dict[str, object]]:
    """Compute the radial signature at several resolutions in one pass.

    Rest-position alignment is shared across resolutions (the canonical
    orientation does not depend on ray count), so this is meaningfully
    cheaper than calling `compute_radial_signature` per resolution.

    Args:
        profile: Sequence of [x, y] vertices. Closed polygon.
        resolutions: Iterable of ray counts. Defaults to
            `SUPPORTED_RESOLUTIONS` (16, 32, 64).
        num_rest_angles: Sample count for rest-position search.

    Returns:
        Dict keyed by ray count, each value as in `compute_radial_signature`.
    """
    resolutions = tuple(int(n) for n in resolutions)
    if not resolutions:
        raise ValueError("resolutions must contain at least one ray count")
    for n in resolutions:
        if n < 3:
            raise ValueError(f"ray count must be >= 3, got {n}")

    P_rest, _centroid, rest_angle_deg = rest_position(
        profile, num_angles=num_rest_angles
    )

    results: Dict[int, Dict[str, object]] = {}
    for n in resolutions:
        angles = np.arange(n) * (2.0 * np.pi / n)
        directions = np.column_stack([np.cos(angles), np.sin(angles)])
        distances, tangents = _ray_polyline_distances_and_tangents(
            P_rest, directions
        )
        if np.any(np.isnan(distances)):
            missed = int(np.isnan(distances).sum())
            raise ValueError(
                f"{missed}/{n} rays did not intersect the boundary at "
                f"resolution N={n}"
            )
        results[n] = {
            "distances": [float(v) for v in distances],
            "tangents": [[float(t[0]), float(t[1])] for t in tangents],
            "num_rays": int(n),
            "rest_angle_deg": float(rest_angle_deg),
        }
    return results


# DESCRIPTOR KEY HELPERS -----------------------------------------------------


def radial_distance_key(num_rays: int) -> str:
    """Return the canonical descriptor key for radial distances at N rays."""
    return f"radial_distance_{int(num_rays)}"


def radial_tangent_key(num_rays: int) -> str:
    """Return the canonical descriptor key for radial tangents at N rays."""
    return f"radial_tangent_{int(num_rays)}"


def descriptor_keys_for_resolutions(
    resolutions: Iterable[int] = SUPPORTED_RESOLUTIONS,
) -> List[str]:
    """Return the flat list of descriptor field names for given resolutions.

    Useful for populating `DESCRIPTORS_TO_COMPUTE` in the cron dispatcher.
    """
    keys: List[str] = []
    for n in resolutions:
        keys.append(radial_distance_key(n))
        keys.append(radial_tangent_key(n))
    return keys


def flatten_signatures_to_descriptors(
    signatures: Dict[int, Dict[str, object]],
) -> Dict[str, object]:
    """Convert per-resolution results to flat `descriptors.*` fields.

    Each resolution N contributes two fields:
        radial_distance_N -> List[float]
        radial_tangent_N  -> List[[tx, ty]]
    """
    out: Dict[str, object] = {}
    for n, sig in signatures.items():
        out[radial_distance_key(n)] = sig["distances"]
        out[radial_tangent_key(n)] = sig["tangents"]
    return out
