#!/usr/bin/env python3.13
"""
Stage 5 of the geometry runner: complexity (data model spec section 4.2b,
decision 6.15).

Ordinal 0--3 (0 simple, 1 normal, 2 complex, 3 very complex) from how far
the piece departs from its primary proxy (``p95_mm / e1``, absent for an
authored proxy, which has no residuals) and from the hull concavity
(``boxscore``). A composite piece is at least 2.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, Sequence

COMPLEXITY_VERSION = 2

# Level thresholds, ascending: a value at or above the k-th threshold is at
# least level k + 1. FROZEN 2026-10-02 (decision 8.59): the best of a grid
# search against the 71 authored ``beyond_debris`` ratings of dump 261001
# (``scripts/dev/tune_geometry.py``; 44 / 71 exact, 71 / 71 within one level).
# A change is a COMPLEXITY_VERSION bump.
T_RESIDUAL: Sequence[float] = (0.005, 0.05, 0.12)
T_BOXSCORE: Sequence[float] = (5.0, 15.0, 45.0)


def _level(value: Optional[float], thresholds: Sequence[float]) -> int:
    if value is None:
        return 0
    return sum(value >= t for t in thresholds)


def derive_complexity(residual_ratio: Optional[float],
                      boxscore: Optional[float],
                      shape_class: Optional[str] = None) -> int:
    level = max(_level(residual_ratio, T_RESIDUAL),
                _level(boxscore, T_BOXSCORE))
    if shape_class == 'composite':
        level = max(level, 2)
    return level
