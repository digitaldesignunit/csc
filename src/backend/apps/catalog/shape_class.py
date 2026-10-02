#!/usr/bin/env python3.13
"""
Stage 2 of the geometry runner: shape class (data model spec section 4.2).

Inputs are the frame's box extents sorted longest first (so the class does
not depend on the frame's axis order) and the hull scores of stage 1.
Elongation is tested before the hull score (decision 8.56): a clearly
elongated or flat piece is linear or planar even when its hull is uneven;
only the remaining compact pieces can be irregular. A piece that passes both
elongation tests takes the class of its stronger elongation (decision 8.58).
``composite`` is never derived.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, Sequence

SHAPE_CLASS_VERSION = 3

# FROZEN 2026-10-02 on dump 261001 (decision 8.59), tuned with
# ``scripts/dev/tune_geometry.py``. A change is a SHAPE_CLASS_VERSION bump.
T_LINEAR = 3.0
T_PLANAR = 3.0
T_IRREGULAR = 25.0


def derive_shape_class(extents: Sequence[float],
                       boxscore: Optional[float]) -> str:
    """``linear`` / ``planar`` / ``irregular`` / ``block`` from the box
    extents and the boxscore (hull volume against box volume, percent)."""
    e1, e2, e3 = sorted((float(e) for e in extents), reverse=True)
    if e1 <= 0:
        raise ValueError('the box has no extent')
    linear = e2 <= 0 or e1 / e2 >= T_LINEAR
    planar = e3 <= 0 or (e2 > 0 and e2 / e3 >= T_PLANAR)
    if linear and planar:
        # the stronger elongation decides; a strip is planar, a batten linear
        if e2 <= 0:
            return 'linear'
        stronger_linear = e3 > 0 and e1 / e2 >= e2 / e3
        return 'linear' if stronger_linear else 'planar'
    if linear:
        return 'linear'
    if planar:
        return 'planar'
    if boxscore is not None and boxscore > T_IRREGULAR:
        return 'irregular'
    return 'block'
