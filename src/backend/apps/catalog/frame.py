#!/usr/bin/env python3.13
"""
Stage 1 of the geometry runner: the frame (data model spec section 4.3,
decisions 7.10, 8.1, 8.7, 8.15, 8.52, 8.53).

The frame is the piece's standard orientation and size, never a
re-orientation: ``frame`` maps the stored coordinates to the canonical ones
and the stored geometry is not touched.

1. Minimum-volume oriented bounding box of all component points
   (``trimesh.bounds.oriented_bounds`` on the convex hull); never vertex PCA.
2. Axes by extent: longest -> x, middle -> y, shortest -> z (lying on its
   largest face). An ``IfcColumn`` whose longest extent is at least twice
   its middle one stands: longest -> z, middle -> x, shortest -> y (8.52;
   the box's own elongation, never the shape class, so no stage waits on
   another).
3. Signs and ties (8.15): among the right-handed frames that follow step 2
   --- extents within ``max(2 % of the larger, 3 mm)`` count as tied and may
   swap --- the one closest to the stored axes wins (largest ``trace(R)``);
   exact ties go by a fixed candidate order.
4. Never upside down (8.53): if a candidate's canonical z lies within 60
   degrees of the stored z (``|z . Z| >= 0.5``), only candidates with
   ``z . Z > 0`` are valid; step 3 chooses among those.

The four hull scores (``boxscore``, ``spherescore``, ``linescore``,
``planescore``) come from the same hull and box (8.7) so stage 2 always has
them.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import itertools
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh
from scipy.spatial import QhullError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.proxies.primitives import frame_dict
from apps.descriptors.boxscore import compute_boxscore_with_metadata
from apps.descriptors.linescore import compute_linescore_with_metadata
from apps.descriptors.planescore import compute_planescore_with_metadata
from apps.descriptors.spherescore import compute_spherescore_with_metadata

FRAME_VERSION = 2

COLUMN_ELONGATION = 2.0
UP_LIMIT = 0.5

TIE_RELATIVE = 0.02
TIE_ABSOLUTE_MM = 3.0

# which obb rank (0 = longest) each of x, y, z takes
_LYING = (0, 1, 2)
_STANDING = (1, 2, 0)
_TRACE_EPS = 1e-9


@dataclass(frozen=True)
class FrameResult:
    """Stage 1 output: the frame, its extents and the hull scores."""
    frame: Dict[str, list]
    bbx: Tuple[float, float, float]
    obb_extents: Tuple[float, float, float]        # sorted, longest first
    scores: Dict[str, float]


def is_standing(original_function: Optional[str],
                extents: Sequence[float]) -> bool:
    """The column rule (8.52): an ``IfcColumn`` stands (z is its length)
    when its longest box extent is at least twice the middle one."""
    e1, e2, _ = sorted((float(e) for e in extents), reverse=True)
    return original_function == 'IfcColumn' and e1 >= COLUMN_ELONGATION * e2


# MINIMUM-VOLUME BOX ----------------------------------------------------------
def _flat_box(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Box of a (near) planar or degenerate point set: PCA axes."""
    centred = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    axes = np.vstack([vt, np.zeros((3 - len(vt), 3))])
    for i in range(len(vt), 3):
        axes[i] = np.cross(axes[(i + 1) % 3], axes[(i + 2) % 3])
    local = (points - points.mean(axis=0)) @ axes.T
    low, high = local.min(axis=0), local.max(axis=0)
    centre = points.mean(axis=0) + ((low + high) / 2.0) @ axes
    return axes, centre, high - low


def minimum_volume_box(points: np.ndarray
                       ) -> Tuple[np.ndarray, np.ndarray, np.ndarray,
                                  Optional[trimesh.Trimesh]]:
    """``(axes rows, centre, extents, hull)`` of the minimum-volume box.

    The hull is None for a flat or degenerate point set (the box then comes
    from its principal axes).
    """
    if len(points) < 4:
        raise ValueError(f'need at least 4 points, got {len(points)}')
    try:
        hull = trimesh.convex.convex_hull(points)
        to_origin, extents = trimesh.bounds.oriented_bounds(hull)
    except (QhullError, ValueError, RuntimeError, TypeError):
        axes, centre, extents = _flat_box(points)
        return axes, centre, extents, None
    axes = to_origin[:3, :3]
    centre = np.linalg.inv(to_origin)[:3, 3]
    extents = np.asarray(extents, dtype=np.float64)
    if not np.isfinite(hull.volume) or hull.volume <= 1e-9 * max(
            float(extents.max()), 1e-12) ** 3:
        hull = None                    # flat: a box, but no hull scores
    return axes, centre, extents, hull


# AXIS ASSIGNMENT -------------------------------------------------------------
def _tied(a: float, b: float) -> bool:
    return abs(a - b) <= max(TIE_RELATIVE * max(a, b), TIE_ABSOLUTE_MM)


def candidate_frames(axes: np.ndarray, extents: np.ndarray,
                     standing: bool):
    """Every right-handed frame that follows the extent rule, in a fixed
    order: ``(x, y, z, extents_xyz)``."""
    ranks = _STANDING if standing else _LYING
    for perm in itertools.permutations(range(3)):      # axis taken by x, y, z
        ok = True
        for s, t in itertools.combinations(range(3), 2):
            # the slot of lower rank is meant to take the longer axis
            first, second = (s, t) if ranks[s] < ranks[t] else (t, s)
            a, b = perm[first], perm[second]
            if extents[a] < extents[b] and not _tied(extents[a], extents[b]):
                ok = False
                break
        if not ok:
            continue
        for signs in itertools.product((1.0, -1.0), repeat=3):
            x, y, z = (signs[i] * axes[perm[i]] for i in range(3))
            if np.dot(np.cross(x, y), z) <= 0:
                continue
            yield x, y, z, np.array([extents[perm[i]] for i in range(3)])


def choose_frame(axes: np.ndarray, centre: np.ndarray, extents: np.ndarray,
                 standing: bool) -> Tuple[Dict[str, list],
                                          Tuple[float, float, float]]:
    """Decision 8.15: the valid frame closest to the stored axes."""
    best, best_trace = None, -np.inf
    for x, y, z, ext in candidate_frames(axes, extents, standing):
        if abs(z[2]) >= UP_LIMIT and z[2] <= 0:
            continue                       # upside down against the input
        trace = x[0] + y[1] + z[2]
        if trace > best_trace + _TRACE_EPS:
            best, best_trace = (x, y, z, ext), trace
    if best is None:
        raise ValueError('no valid frame')
    x, y, z, ext = best
    return (frame_dict(centre, np.vstack([x, y, z])),
            (float(ext[0]), float(ext[1]), float(ext[2])))


# HULL SCORES -----------------------------------------------------------------
def hull_scores(hull: trimesh.Trimesh) -> Dict[str, float]:
    """The four shape-abstraction scores from the convex hull (8.7)."""
    return {
        'boxscore': compute_boxscore_with_metadata(hull)['score'],
        'spherescore': compute_spherescore_with_metadata(hull)['score'],
        'linescore': compute_linescore_with_metadata(hull)['score'],
        'planescore': compute_planescore_with_metadata(hull)['score'],
    }


def compute_frame(points: np.ndarray, *,
                  original_function: Optional[str] = None) -> FrameResult:
    """Stage 1 on component points in stored coordinates."""
    axes, centre, extents, hull = minimum_volume_box(points)
    frame, bbx = choose_frame(axes, centre, extents,
                              is_standing(original_function, extents))
    scores: Dict[str, float] = {}
    if hull is not None:
        try:
            scores = {k: float(v) for k, v in hull_scores(hull).items()}
        except (ValueError, ZeroDivisionError, FloatingPointError):
            scores = {}                # a hull too thin to score
    ordered = tuple(float(v) for v in sorted(extents, reverse=True))
    return FrameResult(frame=frame, bbx=bbx, obb_extents=ordered,
                       scores=scores)
