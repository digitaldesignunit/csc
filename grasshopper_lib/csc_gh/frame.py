# The frame of a piece, offline (decision 8.94 c): data model spec section
# 4.3 steps 1-4, decisions 7.10, 8.15, 8.52, 8.53. Pure: no Rhino import.
#
# A copy of the rules of ``src/backend/apps/catalog/frame.py`` (stage 1 of the
# geometry runner); ``tests/grasshopper/test_frame_parity.py`` keeps the two in
# step on shared fixtures and compares FRAME_VERSION. The hull scores of the
# server (shape class input) are not needed on the client and are left out.
#
# numpy always; trimesh and scipy are imported when a frame is computed (they
# live in the DDU_CSC_MATCH environment, not in the bridge one).
# Python 3.9 compatible; part of the package csc_gh (decision 8.111).

import itertools  # NOQA

import numpy as np  # NOQA

# (written as an annotation: the updater takes the first "version: <number>"
# of a script as its version and an assignment of a number would match)
FRAME_VERSION: int = 2

COLUMN_ELONGATION = 2.0
UP_LIMIT = 0.5

TIE_RELATIVE = 0.02
TIE_ABSOLUTE_MM = 3.0

# which obb rank (0 = longest) each of x, y, z takes
_LYING = (0, 1, 2)
_STANDING = (1, 2, 0)
_TRACE_EPS = 1e-9


def is_standing(original_function, extents):
    """The column rule (8.52): an ``IfcColumn`` stands (z is its length)
    when its longest box extent is at least twice the middle one."""
    e1, e2, _ = sorted((float(e) for e in extents), reverse=True)
    return original_function == 'IfcColumn' and e1 >= COLUMN_ELONGATION * e2


# MINIMUM-VOLUME BOX ----------------------------------------------------------
def _flat_box(points):
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


def minimum_volume_box(points):
    """``(axes rows, centre, extents)`` of the minimum-volume box of the
    points, as ``trimesh.bounds.oriented_bounds`` on their convex hull."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 4:
        raise ValueError('need at least 4 points, got %d' % len(points))
    import trimesh  # NOQA  (DDU_CSC_MATCH)
    from scipy.spatial import QhullError  # NOQA
    try:
        hull = trimesh.convex.convex_hull(points)
        to_origin, extents = trimesh.bounds.oriented_bounds(hull)
    except (QhullError, ValueError, RuntimeError, TypeError):
        return _flat_box(points)
    axes = to_origin[:3, :3]
    centre = np.linalg.inv(to_origin)[:3, 3]
    extents = np.asarray(extents, dtype=np.float64)
    return axes, centre, extents


# AXIS ASSIGNMENT -------------------------------------------------------------
def _tied(a, b):
    return abs(a - b) <= max(TIE_RELATIVE * max(a, b), TIE_ABSOLUTE_MM)


def candidate_frames(axes, extents, standing):
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


def frame_dict(origin, axes):
    """A frame ``{o, x, y, z}`` from an origin and rows ``x, y, z``."""
    return {'o': [float(v) for v in origin],
            'x': [float(v) for v in axes[0]],
            'y': [float(v) for v in axes[1]],
            'z': [float(v) for v in axes[2]]}


def choose_frame(axes, centre, extents, standing):
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


def compute_frame(points, original_function=None):
    """The frame and ``bbx`` of component points in stored coordinates.

    Returns ``{'frame': {o, x, y, z}, 'bbx': (x, y, z),
    'obb_extents': (longest, middle, shortest), 'version': FRAME_VERSION}``.
    """
    axes, centre, extents = minimum_volume_box(points)
    frame, bbx = choose_frame(axes, centre, extents,
                              is_standing(original_function, extents))
    ordered = tuple(float(v) for v in sorted(extents, reverse=True))
    return {'frame': frame, 'bbx': bbx, 'obb_extents': ordered,
            'version': FRAME_VERSION}
