#!/usr/bin/env python3.13
"""
One ``ProxySpec`` per primitive (data model spec section 4.3, appendix B):
box, prism, cylinder, hull. Numpy / scipy / trimesh / shapely only.

Local axes of every primitive: origin at its centroid, ``z`` along the
extrusion / axis direction. Placements are independent of the snapshot's
frame (a beam's prism has z along the beam, its frame has x along it).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, List, Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import shapely
import trimesh
from shapely.geometry import MultiPoint, Polygon
from shapely.geometry.polygon import orient

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.proxies.primitives import (
    frame_dict,
    to_local,
    to_stored,
)
from apps.catalog.proxies.registry import (
    FaceUnwrap,
    FitContext,
    Fitted,
    ProxySpec,
)
from apps.catalog.proxies.robust import ransac_circle

CONCAVITY = 0.1                      # shapely concave_hull ratio (outline.py)
SECTION_SLAB = 0.1                   # mid-span slab, fraction of the length
CYLINDER_SLAB = 0.2
CYLINDER_INLIER = 0.9                # ransac inlier ratio that accepts
CYLINDER_TOLERANCE_REL = 0.02        # of the estimated radius
OUTLINE_MAX_VERTICES = 400
SIMPLIFY_START = 0.002               # first simplification tolerance, of the extent
SIMPLIFY_CAP = 0.05                  # no coarser than this of the extent
OUTLINE_INPUT_MAX = 50_000           # points of a planar outline (8.121 c)
HULL_MAP_SIZE = (128, 64)            # (theta, phi) cells of the hull map
_CHUNK = 2000
NORMAL_FLOOR = 0.5                   # best n . face below this: nearest plane
NORMAL_TIE = 0.05                    # faces this close to the best compete
ORIENT_SAMPLE = 4000                 # points that decide the normals' side
CONSISTENT = 0.9                     # share of decisive points that must agree


# FRAMES ----------------------------------------------------------------------
def _axes(frame: Dict[str, list]) -> np.ndarray:
    return np.array([frame['x'], frame['y'], frame['z']], dtype=np.float64)


def _length_placement(ctx: FitContext) -> Dict[str, list]:
    """Placement whose z is the frame's longest axis (x, y: the other two in
    right-handed order); the origin is the frame origin."""
    axes = _axes(ctx.frame)
    k = int(np.argmax(ctx.bbx))
    order = {0: (1, 2, 0), 1: (2, 0, 1), 2: (0, 1, 2)}[k]
    return frame_dict(ctx.frame['o'], axes[list(order)])


def _simplify(polygon: Polygon, extent: float) -> Optional[Polygon]:
    """The polygon with at most ``OUTLINE_MAX_VERTICES`` vertices, or None.

    The tolerance grows by half each step from ``SIMPLIFY_START`` up to
    ``SIMPLIFY_CAP`` of the extent. A topology-preserving simplification can
    stall above the limit at any tolerance (a jagged hull of a smooth piece
    stood at 433 vertices up to a tolerance of 2e5 mm), and a tolerance of
    several percent no longer describes the piece: then there is no outline
    and the caller keeps the box (8.121 d, 8.127)."""
    tolerance = SIMPLIFY_START * extent
    cap = SIMPLIFY_CAP * extent
    while True:
        simple = polygon.simplify(tolerance, preserve_topology=True)
        if not simple.is_valid or simple.is_empty:
            simple = polygon
        if len(simple.exterior.coords) <= OUTLINE_MAX_VERTICES:
            return simple
        if tolerance >= cap:
            return None
        tolerance = min(tolerance * 1.5, cap)


def _thin(xy: np.ndarray, cell: float) -> np.ndarray:
    """One point per grid cell, always: the hull of a few thousand random
    points is as jagged as the points are loose (8.127)."""
    keys = np.floor(xy / max(cell, 1e-9)).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return xy[first]


def _outline(xy: np.ndarray, extent: float) -> Optional[Polygon]:
    """Concave outline of 2D points, simplified, counter-clockwise."""
    xy = _thin(np.unique(np.round(xy, 6), axis=0), extent / 1000.0)
    if len(xy) < 3:
        return None
    hull = shapely.concave_hull(MultiPoint(xy), ratio=CONCAVITY)
    if hull.geom_type == 'MultiPolygon':
        hull = max(hull.geoms, key=lambda g: g.area)
    if hull.geom_type != 'Polygon' or hull.is_empty or hull.area <= 0:
        return None
    simple = _simplify(hull, extent)
    return None if simple is None else orient(simple, sign=1.0)


def _polygon_params(polygon: Polygon, height: float) -> Dict[str, Any]:
    outer = np.asarray(polygon.exterior.coords)[:-1]
    holes = [np.asarray(r.coords)[:-1].tolist() for r in polygon.interiors]
    return {'profile': outer.tolist(), 'holes': holes or None,
            'height': float(height)}


def _prism_fit(ctx: FitContext, placement: Dict[str, list],
               local: np.ndarray, polygon: Optional[Polygon]
               ) -> Optional[Fitted]:
    if polygon is None:
        return None
    z = local[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    height = zmax - zmin
    if height <= 0:
        return None
    centre = np.array(polygon.centroid.coords[0])
    shifted = shapely.affinity.translate(polygon, -centre[0], -centre[1])
    origin = to_stored(np.array([[centre[0], centre[1],
                                  (zmin + zmax) / 2.0]]), placement)[0]
    axes = np.array([placement['x'], placement['y'], placement['z']])
    return Fitted('prism', _polygon_params(shifted, height),
                  frame_dict(origin, axes), 'lsq')


def _section_polygon(ctx: FitContext, placement: Dict[str, list],
                     local: np.ndarray) -> Optional[Polygon]:
    """Mid-span cross-section of a linear piece in the placement's xy."""
    z = local[:, 2]
    mid = float((z.min() + z.max()) / 2.0)
    length = float(z.max() - z.min())
    extent = float(max(local[:, 0].max() - local[:, 0].min(),
                       local[:, 1].max() - local[:, 1].min()))
    mesh = ctx.source.mesh()
    if mesh is not None:
        try:
            normal = np.array(placement['z'])
            origin = to_stored(np.array([[0.0, 0.0, mid]]), placement)[0]
            section = mesh.section(plane_origin=origin, plane_normal=normal)
            if section is not None:
                loops = [to_local(np.asarray(d), placement)[:, :2]
                         for d in section.discrete]
                polygons = [Polygon(loop) for loop in loops if len(loop) >= 4]
                polygons = [p if p.is_valid else p.buffer(0)
                            for p in polygons if p.area > 0]
                polygons.sort(key=lambda p: -p.area)
                if polygons:
                    outer = polygons[0]
                    holes = [p.exterior.coords for p in polygons[1:]
                             if p.within(outer)]
                    simple = _simplify(
                        Polygon(outer.exterior.coords, holes), extent)
                    if simple is not None:
                        return orient(simple, sign=1.0)
        except Exception:                                  # noqa: BLE001
            pass
    dense = to_local(ctx.sample.points, placement)
    for fraction in (SECTION_SLAB, 3 * SECTION_SLAB, 1.0):
        slab = dense[np.abs(dense[:, 2] - mid) <= 0.5 * fraction * length]
        if len(slab) >= 32 or fraction == 1.0:
            return _outline(slab[:, :2], extent)
    return None


# BOX -------------------------------------------------------------------------
def _box_fit(ctx: FitContext) -> Optional[Fitted]:
    size = [float(v) for v in ctx.bbx]
    if min(size) <= 0:
        return None
    return Fitted('box', {'size': size}, dict(ctx.frame), 'obb')


def _box_sdf(params: Dict[str, Any], local: np.ndarray) -> np.ndarray:
    q = np.abs(local) - np.asarray(params['size']) / 2.0
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(np.max(q, axis=1), 0.0)
    return outside + inside


_BOX_FACES = ('+x', '-x', '+y', '-y', '+z', '-z')
_BOX_NORMALS = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [0, 0, 1], [0, 0, -1]], dtype=np.float64)


# FACE ASSIGNMENT BY SURFACE NORMAL (decision 8.119) ---------------------------
def _assign_by_normal(cosine: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """Index of the face of each point: the face whose outward normal best
    matches the point's surface normal (``cosine`` is ``n . face``), the
    nearest of the faces within ``NORMAL_TIE`` of the best when several
    parallel ones compete, and the nearest plane (``distance``) alone where
    the best match is below ``NORMAL_FLOOR`` (edges, corners)."""
    nearest = distance.argmin(axis=1)
    best = cosine.max(axis=1)
    competing = np.where(cosine >= (best - NORMAL_TIE)[:, None], distance,
                         np.inf)
    return np.where(best >= NORMAL_FLOOR, competing.argmin(axis=1), nearest)


def _outward(cosine: np.ndarray, distance: np.ndarray) -> float:
    """The side the surface normals are on: +1 when they point outward, -1
    when a mesh's winding makes them point inward (the points are near their
    nearest plane, so their normals against that plane's outward normal say
    it), and 0 when the winding is mixed (no side is trusted: the match is
    then unsigned and parallel opposite faces are told apart by distance)."""
    rows = np.arange(len(cosine))
    agree = cosine[rows, distance.argmin(axis=1)]
    for_it = float((agree > NORMAL_FLOOR).sum())
    against = float((agree < -NORMAL_FLOOR).sum())
    if for_it + against == 0:
        return 0.0
    share = for_it / (for_it + against)
    if share >= CONSISTENT:
        return 1.0
    return -1.0 if share <= 1.0 - CONSISTENT else 0.0


def _on_side(cosine: np.ndarray, side: float) -> np.ndarray:
    """``cosine`` as the assignment reads it for that ``_outward`` side."""
    return np.abs(cosine) if side == 0.0 else cosine * side


def _box_faces(params: Dict[str, Any]) -> List[str]:
    return list(_BOX_FACES)


def _box_extent(params: Dict[str, Any], face: str):
    sx, sy, sz = (v / 2.0 for v in params['size'])
    return {'x': (-sy, sy, -sz, sz), 'y': (-sx, sx, -sz, sz),
            'z': (-sx, sx, -sy, sy)}[face[1]]


def _box_unwrap(params: Dict[str, Any], local: np.ndarray,
                normals: Optional[np.ndarray] = None) -> FaceUnwrap:
    """Each point to the face its normal points out of (8.119); without
    normals, and where no face matches, to the nearest plane."""
    half = np.asarray(params['size']) / 2.0
    distance = np.empty((len(local), 6))
    distance[:, 0::2] = np.abs(local - half)           # the + planes
    distance[:, 1::2] = np.abs(local + half)           # the - planes
    if normals is None:
        face = distance.argmin(axis=1)
    else:
        cosine = normals @ _BOX_NORMALS.T
        face = _assign_by_normal(
            _on_side(cosine, _outward(cosine, distance)), distance)
    axis = face // 2
    u = np.where(axis == 0, local[:, 1], local[:, 0])
    v = np.where(axis == 2, local[:, 1], local[:, 2])
    rows = np.arange(len(local))
    sign = 1.0 - 2.0 * (face % 2)                      # + planes, - planes
    plane = sign * local[rows, axis] - half[axis]      # outward positive
    return FaceUnwrap(face, u, v, _BOX_NORMALS[face], plane)


# PRISM -----------------------------------------------------------------------
def _prism_fit_planar(ctx: FitContext) -> Optional[Fitted]:
    """Frame thickness (z) x concave outline of the projection."""
    placement = dict(ctx.frame)
    local = to_local(ctx.points, placement)
    dense = to_local(ctx.sample.points, placement)    # even on the surface
    # the outline does not need the density of the maps (8.121 c): a strided
    # subset (the sample is in random order) before the thinning
    dense = dense[::max(1, -(-len(dense) // OUTLINE_INPUT_MAX))]
    polygon = _outline(dense[:, :2], float(max(ctx.bbx)))
    return _prism_fit(ctx, placement, local, polygon)


def _prism_fit_linear(ctx: FitContext) -> Optional[Fitted]:
    """Mid-span section x length along the longest axis."""
    placement = _length_placement(ctx)
    local = to_local(ctx.points, placement)
    return _prism_fit(ctx, placement, local,
                      _section_polygon(ctx, placement, local))


def _prism_fit_any(ctx: FitContext) -> Optional[Fitted]:
    if ctx.shape_class == 'planar':
        return _prism_fit_planar(ctx)
    return _prism_fit_linear(ctx)


def _ring(params: Dict[str, Any]) -> np.ndarray:
    ring = np.asarray(params['profile'], dtype=np.float64)
    if len(ring) > 1 and np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    if _signed_area(ring) < 0:
        ring = ring[::-1]
    return ring


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _prism_polygon(params: Dict[str, Any]) -> Polygon:
    holes = [np.asarray(h) for h in params.get('holes') or []]
    return Polygon(_ring(params), holes)


def _prism_sdf(params: Dict[str, Any], local: np.ndarray) -> np.ndarray:
    polygon = _prism_polygon(params)
    points = shapely.points(local[:, :2])
    planar = shapely.distance(polygon.boundary, points)
    planar = np.where(shapely.contains(polygon, points), -planar, planar)
    vertical = np.abs(local[:, 2]) - params['height'] / 2.0
    outside = np.hypot(np.maximum(planar, 0.0), np.maximum(vertical, 0.0))
    return outside + np.minimum(np.maximum(planar, vertical), 0.0)


def _prism_faces(params: Dict[str, Any]) -> List[str]:
    return ['top', 'bottom'] + [f'side_{k}'
                                for k in range(len(_ring(params)))]


def _edge_lengths(ring: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)


def _prism_extent(params: Dict[str, Any], face: str):
    h = params['height'] / 2.0
    if face in ('top', 'bottom'):
        ring = _ring(params)
        return (float(ring[:, 0].min()), float(ring[:, 0].max()),
                float(ring[:, 1].min()), float(ring[:, 1].max()))
    k = int(face.split('_')[1])
    return 0.0, float(_edge_lengths(_ring(params))[k]), -h, h


def _edge_distance(ring: np.ndarray, xy: np.ndarray
                   ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest edge of each point: index, distance, position along it."""
    a = ring
    d = np.roll(ring, -1, axis=0) - ring
    length2 = np.maximum((d * d).sum(axis=1), 1e-18)
    best_k = np.empty(len(xy), dtype=int)
    best_d = np.empty(len(xy))
    best_t = np.empty(len(xy))
    for start in range(0, len(xy), _CHUNK):
        block = xy[start:start + _CHUNK]
        rel = block[:, None, :] - a[None, :, :]
        t = np.clip((rel * d[None]).sum(axis=2) / length2[None], 0.0, 1.0)
        nearest = a[None] + t[..., None] * d[None]
        dist = np.linalg.norm(block[:, None, :] - nearest, axis=2)
        k = dist.argmin(axis=1)
        rows = np.arange(len(block))
        best_k[start:start + len(block)] = k
        best_d[start:start + len(block)] = dist[rows, k]
        best_t[start:start + len(block)] = t[rows, k]
    return best_k, best_d, best_t


def _prism_block(ring: np.ndarray, polygon: Polygon, local: np.ndarray,
                 normals: Optional[np.ndarray], half: float,
                 side_normal: np.ndarray):
    """For a block of points, per face (top, bottom, side_k): the distance to
    it, the cosine of the point normal with its outward normal (None without
    normals), and the position ``t`` along each edge."""
    edge = np.roll(ring, -1, axis=0) - ring
    length2 = np.maximum((edge * edge).sum(axis=1), 1e-18)
    xy, z = local[:, :2], local[:, 2]
    rel = xy[:, None, :] - ring[None, :, :]
    t = np.clip((rel * edge[None]).sum(axis=2) / length2[None], 0.0, 1.0)
    nearest = ring[None] + t[..., None] * edge[None]
    edge_distance = np.linalg.norm(xy[:, None, :] - nearest, axis=2)
    inside = shapely.contains(polygon, shapely.points(xy))
    planar_out = np.where(inside, 0.0, edge_distance.min(axis=1))
    over = np.maximum(np.abs(z) - half, 0.0)
    distance = np.column_stack([
        np.hypot(np.abs(z - half), planar_out),          # top
        np.hypot(np.abs(z + half), planar_out),          # bottom
        np.hypot(edge_distance, over[:, None])])         # side_k
    if normals is None:
        return distance, None, t
    cosine = np.column_stack([normals[:, 2], -normals[:, 2],
                              normals[:, :2] @ side_normal[:, :2].T])
    return distance, cosine, t


def _prism_unwrap(params: Dict[str, Any], local: np.ndarray,
                  normals: Optional[np.ndarray] = None) -> FaceUnwrap:
    """Each point to the cap or side its normal points out of (8.119);
    without normals, and where no face matches, to the nearest one."""
    ring = _ring(params)
    lengths = _edge_lengths(ring)
    half = params['height'] / 2.0
    polygon = Polygon(ring)
    edge = np.roll(ring, -1, axis=0) - ring
    side_normal = np.column_stack([edge[:, 1], -edge[:, 0],
                                   np.zeros(len(ring))])
    side_normal /= np.maximum(np.linalg.norm(side_normal, axis=1,
                                             keepdims=True), 1e-12)
    sign = 1.0
    if normals is not None:
        step = max(1, len(local) // ORIENT_SAMPLE)
        distance, cosine, _ = _prism_block(
            ring, polygon, local[::step], normals[::step], half, side_normal)
        sign = _outward(cosine, distance)
    count = len(local)
    face = np.empty(count, dtype=int)
    t_edge = np.zeros(count)
    for start in range(0, count, _CHUNK):
        block = slice(start, start + _CHUNK)
        distance, cosine, t = _prism_block(
            ring, polygon, local[block],
            None if normals is None else normals[block], half, side_normal)
        chosen = (distance.argmin(axis=1) if cosine is None
                  else _assign_by_normal(_on_side(cosine, sign), distance))
        face[block] = chosen
        t_edge[block] = t[np.arange(len(chosen)), np.maximum(chosen - 2, 0)]
    cap = face < 2
    side = np.maximum(face - 2, 0)
    u = np.where(cap, local[:, 0], t_edge * lengths[side])
    v = np.where(cap, local[:, 1], local[:, 2])
    normal = side_normal[side]
    normal[cap] = np.column_stack([np.zeros(cap.sum()), np.zeros(cap.sum()),
                                   np.where(face[cap] == 0, 1.0, -1.0)])
    # the plane of the assigned cap, or of the line of the assigned side
    plane = np.where(
        cap, np.where(face == 0, local[:, 2] - half, -local[:, 2] - half),
        np.einsum('ij,ij->i', local[:, :2] - ring[side],
                  side_normal[side][:, :2]))
    return FaceUnwrap(face, u, v, normal, plane)


# CYLINDER --------------------------------------------------------------------
def _cylinder_fit(ctx: FitContext) -> Optional[Fitted]:
    placement = _length_placement(ctx)
    local = to_local(ctx.points, placement)
    z = local[:, 2]
    length = float(z.max() - z.min())
    if length <= 0:
        return None
    mid = float((z.max() + z.min()) / 2.0)
    slab = local[np.abs(z - mid) <= 0.5 * CYLINDER_SLAB * length]
    if len(slab) < 32:
        slab = local
    xy = _thin(np.unique(np.round(slab[:, :2], 6), axis=0), length / 1000.0)
    sections = sorted(ctx.bbx)[:2]
    tolerance = max(0.5, CYLINDER_TOLERANCE_REL * sections[1] / 2.0)
    circle = ransac_circle(xy, tolerance)
    if circle is None or circle.inlier_ratio < CYLINDER_INLIER \
            or circle.radius <= 0:
        return None
    origin = to_stored(np.array([[circle.centre[0], circle.centre[1], mid]]),
                       placement)[0]
    axes = np.array([placement['x'], placement['y'], placement['z']])
    return Fitted('cylinder', {'radius': circle.radius, 'height': length},
                  frame_dict(origin, axes), 'ransac',
                  inlier_ratio=circle.inlier_ratio)


def _cylinder_sdf(params: Dict[str, Any], local: np.ndarray) -> np.ndarray:
    radial = np.hypot(local[:, 0], local[:, 1]) - params['radius']
    vertical = np.abs(local[:, 2]) - params['height'] / 2.0
    outside = np.hypot(np.maximum(radial, 0.0), np.maximum(vertical, 0.0))
    return outside + np.minimum(np.maximum(radial, vertical), 0.0)


def _cylinder_faces(params: Dict[str, Any]) -> List[str]:
    return ['top', 'bottom', 'lateral']


def _cylinder_extent(params: Dict[str, Any], face: str):
    circumference = 2.0 * np.pi * params['radius']
    if face == 'lateral':
        h = params['height'] / 2.0
        return 0.0, float(circumference), -h, h
    return 0.0, float(circumference), 0.0, float(params['radius'])


def _cylinder_unwrap(params: Dict[str, Any], local: np.ndarray,
                     normals: Optional[np.ndarray] = None) -> FaceUnwrap:
    radius, half = params['radius'], params['height'] / 2.0
    r = np.hypot(local[:, 0], local[:, 1])
    theta = np.mod(np.arctan2(local[:, 1], local[:, 0]), 2.0 * np.pi)
    vertical = np.abs(local[:, 2]) - half
    cap_distance = np.hypot(np.abs(vertical), np.maximum(r - radius, 0.0))
    lateral_distance = np.hypot(np.abs(r - radius), np.maximum(vertical, 0.0))
    cap = cap_distance < lateral_distance
    top = local[:, 2] >= 0
    face = np.where(cap, np.where(top, 0, 1), 2)
    u = theta * radius
    v = np.where(cap, r, local[:, 2])
    normal = np.column_stack([np.cos(theta), np.sin(theta), np.zeros(len(r))])
    normal[cap] = np.column_stack([np.zeros(cap.sum()), np.zeros(cap.sum()),
                                   np.where(top[cap], 1.0, -1.0)])
    plane = np.where(cap, np.where(top, local[:, 2], -local[:, 2]) - half,
                     r - radius)
    return FaceUnwrap(face, u, v, normal, plane)


# HULL ------------------------------------------------------------------------
def _hull_fit(ctx: FitContext) -> Optional[Fitted]:
    try:
        hull = trimesh.convex.convex_hull(ctx.points)
    except Exception:                                      # noqa: BLE001
        return None
    centroid = np.asarray(hull.centroid, dtype=np.float64)
    placement = frame_dict(centroid, np.eye(3))
    vertices = np.asarray(hull.vertices) - centroid
    return Fitted('hull', {'vertices': vertices.tolist(),
                           'faces': hull.faces.tolist()}, placement, 'hull')


def _hull_planes(params: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.Trimesh(np.asarray(params['vertices'], dtype=float),
                           np.asarray(params['faces'], dtype=np.int64),
                           process=False)
    normals = mesh.face_normals
    offsets = np.einsum('ij,ij->i', normals, mesh.triangles[:, 0])
    return normals, offsets


def _hull_sdf(params: Dict[str, Any], local: np.ndarray) -> np.ndarray:
    """Signed distance to a convex hull: exact inside (nearest face plane);
    outside it is the largest plane distance, a lower bound."""
    normals, offsets = _hull_planes(params)
    out = np.empty(len(local))
    for start in range(0, len(local), _CHUNK):
        block = local[start:start + _CHUNK]
        out[start:start + len(block)] = (block @ normals.T
                                         - offsets[None]).max(axis=1)
    return out


def _hull_faces(params: Dict[str, Any]) -> List[str]:
    return ['sphere']


def _hull_extent(params: Dict[str, Any], face: str):
    return 0.0, 2.0 * np.pi, 0.0, np.pi


def _hull_unwrap(params: Dict[str, Any], local: np.ndarray,
                 normals: Optional[np.ndarray] = None) -> FaceUnwrap:
    r = np.maximum(np.linalg.norm(local, axis=1), 1e-12)
    theta = np.mod(np.arctan2(local[:, 1], local[:, 0]), 2.0 * np.pi)
    phi = np.arccos(np.clip(local[:, 2] / r, -1.0, 1.0))
    return FaceUnwrap(np.zeros(len(local), dtype=int), theta, phi,
                      local / r[:, None])


# REGISTRY --------------------------------------------------------------------
BOX = ProxySpec(
    name='box', fit=_box_fit, sdf=_box_sdf, faces=_box_faces,
    extent=_box_extent, unwrap=_box_unwrap,
    applicable_shape_classes=('linear', 'planar', 'block', 'irregular',
                              'composite'))
PRISM = ProxySpec(
    name='prism', fit=_prism_fit_any, sdf=_prism_sdf, faces=_prism_faces,
    extent=_prism_extent, unwrap=_prism_unwrap,
    applicable_shape_classes=('linear', 'planar'))
CYLINDER = ProxySpec(
    name='cylinder', fit=_cylinder_fit, sdf=_cylinder_sdf,
    faces=_cylinder_faces, extent=_cylinder_extent, unwrap=_cylinder_unwrap,
    applicable_shape_classes=('linear',))
HULL = ProxySpec(
    name='hull', fit=_hull_fit, sdf=_hull_sdf, faces=_hull_faces,
    extent=_hull_extent, unwrap=_hull_unwrap,
    applicable_shape_classes=('irregular',), angular_map=True)

ALL_PROXY_SPECS: Dict[str, ProxySpec] = {
    spec.name: spec for spec in (BOX, PRISM, CYLINDER, HULL)}
