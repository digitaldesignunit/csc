#!/usr/bin/env python3.13
"""
In-house RANSAC for a circle in a plane (spec section 4.3, decision 6.11).

Seeded, so a re-run gives the same fit. Three random points define a
candidate circle; the best candidate (most points within ``tolerance``) is
refined by an algebraic (Kasa) least-squares fit on its inliers.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass
from typing import Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np

RANSAC_SEED = 7
RANSAC_ITERATIONS = 300


@dataclass(frozen=True)
class CircleFit:
    centre: Tuple[float, float]
    radius: float
    inlier_ratio: float


def circle_through(a: np.ndarray, b: np.ndarray, c: np.ndarray
                   ) -> Optional[Tuple[np.ndarray, float]]:
    """Circle through three points; None when they are (nearly) collinear."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    centre = np.array([ux, uy])
    return centre, float(np.hypot(ax - ux, ay - uy))


def kasa_fit(points: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Algebraic least-squares circle (Kasa) through ``points`` (n, 2)."""
    if len(points) < 3:
        return None
    mean = points.mean(axis=0)
    x, y = (points - mean).T
    design = np.column_stack([x, y, np.ones(len(x))])
    target = x * x + y * y
    try:
        (a, b, c), *_ = np.linalg.lstsq(design, target, rcond=None)
    except np.linalg.LinAlgError:
        return None
    centre = np.array([a / 2.0, b / 2.0])
    square = c + centre @ centre
    if square <= 0:
        return None
    return centre + mean, float(np.sqrt(square))


def ransac_circle(points: np.ndarray, tolerance: float,
                  iterations: int = RANSAC_ITERATIONS,
                  seed: int = RANSAC_SEED) -> Optional[CircleFit]:
    """Best circle in ``points`` (n, 2); inliers lie within ``tolerance``."""
    n = len(points)
    if n < 3:
        return None
    rng = np.random.default_rng(seed)
    best, best_count = None, -1
    for _ in range(iterations):
        pick = points[rng.choice(n, size=3, replace=False)]
        candidate = circle_through(*pick)
        if candidate is None:
            continue
        centre, radius = candidate
        count = int((np.abs(np.hypot(*(points - centre).T) - radius)
                     <= tolerance).sum())
        if count > best_count:
            best, best_count = candidate, count
    if best is None:
        return None
    centre, radius = best
    inliers = np.abs(np.hypot(*(points - centre).T) - radius) <= tolerance
    refined = kasa_fit(points[inliers])
    if refined is not None:
        centre, radius = refined
        inliers = np.abs(np.hypot(*(points - centre).T) - radius) <= tolerance
    return CircleFit((float(centre[0]), float(centre[1])), float(radius),
                     float(inliers.mean()))
