#!/usr/bin/env python3.9
"""
Planar outline extraction for the radial signature.

`apps.descriptors.radial_signature` consumes a single closed 2D boundary.
This module reduces a component's geometry to one, by cutting the
PCA-aligned geometry with a Z-normal plane through its centre and keeping
the outer loop of the cut.

`apply_pca_frame_transform` maps the principal axes onto world XYZ, longest
to X and shortest to Z, so the cut plane is always Z-normal here and it
always spans the component's two dominant directions. Dropping the Z
coordinate then yields the 2D outline directly, with no further projection
step that could mirror or rotate it relative to the extrusion profiles the
signature was originally built on.

Meshes are cut exactly: `trimesh.Trimesh.section` returns the true
cross-section, concavities and all. Only the PCA centre plane is used; a
different height would be a different section. A watertight cut yields a
simple closed loop, which is kept. An open scan yields open polylines;
those intersection points are wrapped in a convex hull so the boundary is
simple and the centroid lies inside (a gappy polyline closed by a chord
can miss rays). If the plane misses entirely - typical of an open surface
whose faces lie in the cut plane - the outline falls back to the concave
hull of the vertices in XY.
Extrusions are turned into meshes and cut the same way, because an
extrusion's own profile lies in its extrusion frame, which is only the PCA
plane when the extrusion axis happens to be the shortest one. Point clouds
have no faces to cut, so the points within a slab around the cut height are
flattened and wrapped in a concave hull.

Panels are the exception, described by `PANEL_POLICY` below: they are thin
and prismatic, so their meaningful outline is the silhouette rather than a
band through the middle, and an authored extrusion profile may be used
directly when no mesh or point cloud is available.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh
from shapely import MultiPoint, Polygon, concave_hull

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.descriptors import radial_signature as rs
from apps.descriptors.geometry import (
    apply_pca_frame_to_points,
    first_extrusion,
    load_extrusion_mesh_for_descriptor,
    load_snapshot_point_cloud_points,
    load_snapshot_surface_mesh,
)

# MODULE CONSTANTS ------------------------------------------------------------

LoggerFn = Callable[[str], None]

DEFAULT_CONCAVITY: float = 0.1
"""Shapely `concave_hull` ratio used to wrap a projected point slab.

0 follows the samples as tightly as the Delaunay triangulation allows, 1 is
the convex hull. The ratio is scale-invariant, so it needs no unit-dependent
tuning, but it does trade sharpness against robustness.

Measured on clouds sampled from an L-shaped panel (true area 6400, sharp
concave corner at a known point), the tightest ratio that still survives a
sparse cloud is 0.1:

    ratio   corner error    area @6k    area @400 points
    0.05        2.9           6404      2817  (hull collapses)
    0.10        5.9           6417      6074
    0.20       11.7           6470      6381

Area accuracy is flat from 0.05 upward, so the ratio is really chosen on
concave-corner fidelity, where lower is better - but below 0.1 the hull
fragments on sparse clouds and loses more than half the area. On a plain
rectangle 0.1 recovers 3953 of 4000, so it does not invent concavities.
"""

PANEL_SLAB_FRACTION: float = 1.0
"""Fraction of the depth kept when slicing a panel point cloud.

1.0 means every point is flattened, i.e. the cut spans the full depth.
Panels get the whole thing because a narrow band is actively wrong for
them: a surface scan puts points on the two faces and the rim, so a
mid-depth band of 10-50% selects *zero* points on a two-sided cloud.
Because panels are prismatic, the full silhouette and a true mid-depth
slab describe the same outline anyway, and using every point makes the
concave hull markedly more accurate.
"""

SOLID_SLAB_FRACTION: float = 0.1
"""Fraction of the depth kept when slicing any other point cloud.

Non-planar components are cut for real rather than flattened, so the slab
has to be thin enough to be a section but thick enough to hold points. A
surface scan has no points in the interior, so a slab through the centre
picks up the rim at that depth - which is exactly the section outline.
"""

MIN_SLAB_POINTS: int = 32
"""Fewest points a slab may hold before it is considered too sparse.

Panels widen to the full silhouette at that point, since failing to produce
any outline is worse than producing the full-depth one. Other components
fail instead: widening their slab would silently swap the section they
asked for with a silhouette, which is a different descriptor.
"""

_CLOSED_EPS: float = 1e-9

_MIN_AREA_RATIO: float = 1e-6
"""Smallest area, relative to the squared bounding-box diagonal, we accept.

Near-collinear input does not always fail loudly: shapely happily returns a
sliver polygon that runs out along the line and back. Such an outline has
its centroid on its own boundary, so the ray casting downstream would miss
and fail with a far less obvious message. A real panel outline scores 0.2
or more on this ratio, so the threshold rejects only true degeneracy.
"""


def _noop_logger(_message: str) -> None:
    return None


# POLICY ----------------------------------------------------------------------


@dataclass(frozen=True)
class OutlinePolicy:
    """How one class of component is reduced to a closed 2D boundary.

    Attributes:
        rest_align: whether the signature rotates the outline into its
            canonical rest position afterwards. Carried here so the single
            planar-versus-solid decision lives in one place, even though
            the rotation itself happens in `radial_signature`.
        use_extrusion_profile: whether an authored extrusion profile may be
            used as the outline directly. Only sound when the extrusion
            axis is also the shortest axis, so that the profile plane and
            the PCA plane coincide.
        slab_fraction: fraction of the depth kept when cutting a cloud.
        widen_sparse_slab: whether a slab holding fewer than
            `MIN_SLAB_POINTS` may grow to the full depth instead of failing.
    """
    rest_align: bool
    use_extrusion_profile: bool
    slab_fraction: float
    widen_sparse_slab: bool


PANEL_POLICY = OutlinePolicy(
    rest_align=True,
    use_extrusion_profile=True,
    slab_fraction=PANEL_SLAB_FRACTION,
    widen_sparse_slab=True,
)
"""Thin planar components: silhouette, canonically rotated.

A panel is a profile swept a short distance, so its extrusion axis is its
shortest axis and the authored profile already lies in the PCA plane.
"""

SOLID_POLICY = OutlinePolicy(
    rest_align=False,
    use_extrusion_profile=False,
    slab_fraction=SOLID_SLAB_FRACTION,
    widen_sparse_slab=False,
)
"""Everything else: a real section through the PCA plane, not rotated.

A beam extruded along its longest axis is the motivating case. Its profile
is the 100 x 200 cross-section while its PCA plane holds the 2000 x 200
lengthwise cut, so the authored profile is the wrong plane entirely and the
geometry has to be cut instead.
"""


def policy_for(component: Dict) -> OutlinePolicy:
    """Return the outline policy governing `component`."""
    return (
        PANEL_POLICY if rs.is_rest_aligned(component) else SOLID_POLICY
    )


# LOOP SELECTION --------------------------------------------------------------


def _polygon_area(xy: np.ndarray) -> float:
    """Absolute shoelace area of a polygon given as an (M, 2) array."""
    x, y = xy[:, 0], xy[:, 1]
    cross = np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))
    return 0.5 * abs(float(cross))


def _is_closed_loop(loop: np.ndarray) -> bool:
    return bool(np.allclose(loop[0], loop[-1], atol=_CLOSED_EPS))


def _loop_is_simple_polygon(loop: np.ndarray) -> bool:
    """True when `loop` is a simple, valid polygon the centroid can sit in."""
    try:
        poly = Polygon(loop)
    except Exception:
        return False
    return (
        poly.geom_type == 'Polygon'
        and (not poly.is_empty)
        and poly.is_valid
        and poly.is_simple
    )


def _radial_rays_all_hit(outline: List[List[float]]) -> bool:
    """True when every radial-signature ray hits `outline`.

    A simple closed section can still fail the descriptor: a C-shape puts
    its centroid in the opening, and a nearly-closed scan loop can leave a
    crack that one of 32 rays slips through. Convex hull of the same points
    is star-convex from its centroid, so those cases fall back to that.
    """
    try:
        rs.compute_radial_signatures(outline, rest_align=False)
    except Exception:
        return False
    return True


def _convex_outline_from_xy(xy: np.ndarray) -> List[List[float]]:
    """Closed convex hull of 2D section (or silhouette) points."""
    pts = np.asarray(xy, dtype=np.float64)
    pts = pts[np.isfinite(pts).all(axis=1)]
    pts = np.unique(np.round(pts, 9), axis=0)
    if len(pts) < 3:
        raise ValueError(
            f'Section collapses to {len(pts)} distinct points, '
            f'too few for an outline'
        )
    hull = MultiPoint(pts).convex_hull
    if hull.geom_type != 'Polygon' or hull.is_empty:
        raise ValueError(
            f'Convex hull of the section degenerated to {hull.geom_type}'
        )
    loop = np.asarray(hull.exterior.coords, dtype=np.float64)
    return _finalize_outline(loop)


def _largest_loop(loops: Sequence[np.ndarray]) -> Optional[np.ndarray]:
    """Pick the outer boundary from a set of candidate 2D loops.

    A cut through a component with holes yields one loop per boundary; the
    outer one always encloses the largest area. Closed loops are preferred
    over open ones, which a non-watertight scan mesh can produce.
    """
    usable = [np.asarray(lp, dtype=np.float64) for lp in loops]
    usable = [lp for lp in usable if lp.ndim == 2 and len(lp) >= 3]
    if not usable:
        return None
    closed = [lp for lp in usable if _is_closed_loop(lp)]
    candidates = closed or usable
    return max(candidates, key=_polygon_area)


def _finalize_outline(loop: np.ndarray) -> List[List[float]]:
    """Reject a degenerate loop, else return it as [[x, y], ...]."""
    extent = loop.max(axis=0) - loop.min(axis=0)
    diagonal_sq = float(extent[0] ** 2 + extent[1] ** 2)
    area = _polygon_area(loop)
    if diagonal_sq <= 0.0 or area <= _MIN_AREA_RATIO * diagonal_sq:
        raise ValueError(
            f'Outline encloses no meaningful area (area {area:.6g} over a '
            f'{extent[0]:.6g} x {extent[1]:.6g} extent); the geometry is '
            f'collinear or coincident in the section plane'
        )
    return [[float(p[0]), float(p[1])] for p in loop]


def _centre_plane_height(mesh: trimesh.Trimesh) -> float:
    """Z of the PCA centre plane.

    Origin when the mesh straddles z=0 (the usual PCA-aligned case), else
    the middle of the Z bounds for geometry stored without a frame. No
    other height is used: an offset cut is a different section, so outlines
    would not be comparable across identically oriented components.
    """
    z_min = float(mesh.bounds[0][2])
    z_max = float(mesh.bounds[1][2])
    return 0.0 if z_min < 0.0 < z_max else 0.5 * (z_min + z_max)


def _loops_from_section(section: object) -> List[np.ndarray]:
    """2D loops from a trimesh Path3D section, XY of each discrete entity."""
    discrete = getattr(section, 'discrete', None)
    if not discrete:
        return []
    loops = []
    for path in discrete:
        arr = np.asarray(path, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] < 2 or len(arr) < 3:
            continue
        loops.append(arr[:, :2])
    return loops


def _section_xy_points(section: object) -> np.ndarray:
    """Every unique intersection vertex of a Path3D section, as XY.

    Open scan meshes typically section into two-point line fragments, which
    `_loops_from_section` ignores. The vertices of those fragments are still
    the true mid-plane outline; a convex hull of them is a closed boundary.
    """
    vertices = getattr(section, 'vertices', None)
    if vertices is not None:
        arr = np.asarray(vertices, dtype=np.float64)
        if arr.ndim == 2 and arr.shape[1] >= 2 and len(arr) >= 3:
            return arr[:, :2]
    loops = _loops_from_section(section)
    if not loops:
        return np.empty((0, 2), dtype=np.float64)
    return np.vstack(loops)


def _outline_from_mesh_vertices(
    mesh: trimesh.Trimesh,
    concavity: float,
    logger: LoggerFn,
) -> List[List[float]]:
    """Silhouette of a mesh the centre plane could not slice.

    Used for open scanned surfaces whose faces are nearly parallel to the
    PCA XY plane: a Z-normal section is coplanar with the triangles and
    trimesh returns no line intersections. The XY of the vertices is then
    the same outline a mid-plane cut would have produced on a solid.
    """
    points = np.asarray(mesh.vertices, dtype=np.float64)
    logger(
        'centre plane did not intersect the mesh; using the vertex '
        f'silhouette ({len(points)} vertices, z-extent '
        f'{float(mesh.extents[2]):.6g})'
    )
    return section_outline_from_points(
        points,
        slab_fraction=1.0,
        concavity=concavity,
        widen_sparse_slab=False,
        logger=logger,
    )


# MESH SECTIONING -------------------------------------------------------------


def section_outline_from_mesh(
    mesh: trimesh.Trimesh,
    logger: LoggerFn = _noop_logger,
    concavity: float = DEFAULT_CONCAVITY,
) -> List[List[float]]:
    """
    Cut a PCA-aligned mesh through its centre and return the outer loop.

    Args:
        mesh: PCA-aligned mesh, i.e. shortest principal axis on world Z.
        logger: optional progress logger.
        concavity: hull ratio used only if the centre plane misses, i.e. on
            open scanned surfaces that lie in the section plane. Open
            polylines from a successful cut are wrapped in a convex hull
            instead; this argument does not apply to that path.

    Returns:
        List of [x, y] vertices describing the closed outer boundary.

    Raises:
        ValueError: if no usable outline can be produced.
    """
    z_min = float(mesh.bounds[0][2])
    z_max = float(mesh.bounds[1][2])
    depth = z_max - z_min
    if not np.isfinite(depth) or depth < 0.0:
        raise ValueError(
            f'Mesh has no extent along the section axis (depth {depth}); '
            f'it cannot be cut'
        )

    height = _centre_plane_height(mesh)
    last_empty_reason = 'no intersection'
    try:
        section = mesh.section(
            plane_origin=[0.0, 0.0, height],
            plane_normal=[0.0, 0.0, 1.0],
        )
    except Exception as exc:
        logger(f'section at z={height:.6g} failed: {exc}')
        section = None
        last_empty_reason = str(exc)
    if section is not None:
        loops = _loops_from_section(section)
        closed = [
            lp for lp in loops
            if _is_closed_loop(lp) and _loop_is_simple_polygon(lp)
        ]
        hull_reason: Optional[str] = None
        if closed:
            try:
                outline = _finalize_outline(max(closed, key=_polygon_area))
            except ValueError as exc:
                last_empty_reason = str(exc)
            else:
                if _radial_rays_all_hit(outline):
                    return outline
                hull_reason = (
                    'closed section is not star-convex from its centroid'
                )
        points = _section_xy_points(section)
        if len(points) >= 3:
            logger(
                f'{hull_reason or "open section"}; using convex hull of '
                f'{len(points)} intersection points'
            )
            try:
                return _convex_outline_from_xy(points)
            except ValueError as exc:
                last_empty_reason = str(exc)
        else:
            last_empty_reason = 'intersection produced no usable loop'

    try:
        return _outline_from_mesh_vertices(mesh, concavity, logger)
    except Exception as exc:
        raise ValueError(
            f'Mesh produced no usable cross-section at the centre plane '
            f'({last_empty_reason}); vertex silhouette also failed: {exc}'
        ) from exc


# POINT CLOUD SECTIONING ------------------------------------------------------


def section_outline_from_points(
    points: Union[List[List[float]], np.ndarray],
    slab_fraction: float = SOLID_SLAB_FRACTION,
    concavity: float = DEFAULT_CONCAVITY,
    min_slab_points: int = MIN_SLAB_POINTS,
    widen_sparse_slab: bool = False,
    logger: LoggerFn = _noop_logger,
) -> List[List[float]]:
    """
    Cut a PCA-aligned point cloud through its centre and hull the result.

    Args:
        points: PCA-aligned [x, y, z] triplets, shortest axis on world Z.
        slab_fraction: fraction of the depth to keep, centred on the centre
            plane. 1.0 flattens every point. See `SOLID_SLAB_FRACTION` and
            `PANEL_SLAB_FRACTION`.
        concavity: shapely `concave_hull` ratio. See `DEFAULT_CONCAVITY`.
        min_slab_points: fewest points a slab may hold before it counts as
            too sparse.
        widen_sparse_slab: if True, a too-sparse slab grows to the full
            depth rather than failing.
        logger: optional progress logger.

    Returns:
        List of [x, y] vertices describing the closed outer boundary.

    Raises:
        ValueError: if the points are malformed, the slab is too sparse to
            hull and may not widen, or the result is degenerate.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(
            f'Points must be a sequence of [x, y, z] triplets, '
            f'got shape {pts.shape}'
        )
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 3:
        raise ValueError(
            f'Outline needs at least 3 finite points, got {len(pts)}'
        )

    if slab_fraction < 1.0:
        if slab_fraction <= 0.0:
            raise ValueError(
                f'slab_fraction must be > 0, got {slab_fraction}'
            )
        z = pts[:, 2]
        z_min, z_max = float(z.min()), float(z.max())
        # As in `section_outline_from_mesh`, the PCA frame centres the cloud
        # on the origin; unframed geometry falls back to the bounds middle.
        centre = 0.0 if z_min < 0.0 < z_max else 0.5 * (z_min + z_max)
        half_band = 0.5 * slab_fraction * (z_max - z_min)
        slab = pts[np.abs(z - centre) <= half_band]
        if len(slab) >= min_slab_points:
            pts = slab
        elif widen_sparse_slab:
            logger(
                f'slab at {slab_fraction:.0%} of depth holds only '
                f'{len(slab)} points, flattening the full depth instead'
            )
        else:
            raise ValueError(
                f'Slab at {slab_fraction:.0%} of depth holds only '
                f'{len(slab)} points, fewer than the {min_slab_points} '
                f'needed for a section outline'
            )

    xy = np.unique(np.round(pts[:, :2], 9), axis=0)
    if len(xy) < 3:
        raise ValueError(
            f'Projected cloud collapses to {len(xy)} distinct points, '
            f'too few for an outline'
        )

    hull = concave_hull(MultiPoint(xy), ratio=concavity)
    if hull.geom_type == 'MultiPolygon':
        hull = max(hull.geoms, key=lambda g: g.area)
    if hull.geom_type != 'Polygon' or hull.is_empty:
        raise ValueError(
            f'Concave hull of the projected cloud degenerated to '
            f'{hull.geom_type}; the points are collinear or coincident'
        )

    loop = np.asarray(hull.exterior.coords, dtype=np.float64)
    if len(loop) < 4:
        raise ValueError(
            'Concave hull of the projected cloud has fewer than 3 vertices'
        )
    return _finalize_outline(loop)


# COMPONENT-LEVEL RESOLUTION --------------------------------------------------


def _build_extrusion_mesh(
    extrusion: Dict,
    pca_frame: Optional[Dict[str, List[float]]],
) -> trimesh.Trimesh:
    """Sweep an extrusion into a PCA-aligned mesh to cut."""
    return load_extrusion_mesh_for_descriptor(
        profile=extrusion['profile'],
        height=extrusion['height'],
        pca_frame=pca_frame,
    )


def outline_from_component(
    component: Dict,
    mesh: Optional[trimesh.Trimesh] = None,
    concavity: float = DEFAULT_CONCAVITY,
    policy: Optional[OutlinePolicy] = None,
    meshes_dir: Optional[str] = None,
    point_clouds_dir: Optional[str] = None,
    logger: LoggerFn = _noop_logger,
) -> Tuple[Optional[List[List[float]]], Optional[str], Optional[str]]:
    """
    Resolve the best available 2D outline for a component.

    Priority:
        1. highest-resolution surface mesh
           (``detailed.ply`` > ``reduced.ply`` > inline ``geometry.meshes[0]``)
        2. highest-resolution point cloud
           (``point_clouds/<id>/0.ply`` > inline preview)
        3. ``geometry.extrusions[0]`` - authored profile for panels, or a
           section of the swept mesh for every other type

    A mesh passed in from the runner is ignored. `load_snapshot_mesh`
    hulls cloud-only snapshots, and cutting that hull would erase the
    concavities the signature exists to capture. This function always
    reloads the highest-resolution surface mesh or the raw points.

    Args:
        component: snapshot or component document.
        mesh: unused; kept so the runner can pass `ctx.mesh` without a
            special case. See above.
        concavity: passed to `section_outline_from_points`.
        policy: how to reduce this component; defaults to `policy_for`.
        meshes_dir: on-disk snapshot mesh directory; detailed PLY is
            preferred over the inline mesh when present.
        point_clouds_dir: on-disk snapshot point-cloud directory; the full
            PLY is preferred over the inline preview when present.
        logger: optional progress logger.

    Returns:
        Tuple of ``(outline, source, reason)``. On success `reason` is None;
        on failure `outline` and `source` are None and `reason` is a short
        human-readable explanation.
    """
    policy = policy if policy is not None else policy_for(component)
    geometry = component.get('geometry') or {}
    pca_frame = component.get('pca_frame')
    snapshot_id = str(component.get('_id', '<unknown>'))
    last_reason: Optional[str] = None
    _ = mesh

    surface_mesh, mesh_source = load_snapshot_surface_mesh(
        component, meshes_dir=meshes_dir, logger=logger)
    if surface_mesh is not None:
        source = f'{mesh_source} (section)'
        try:
            return (
                section_outline_from_mesh(
                    surface_mesh, logger=logger, concavity=concavity),
                source,
                None,
            )
        except Exception as exc:
            last_reason = f'{source}: {exc}'
            logger(last_reason)

    if geometry.get('point_clouds'):
        cloud_points, cloud_source = load_snapshot_point_cloud_points(
            geometry, snapshot_id, point_clouds_dir, logger)
        if cloud_points is None:
            last_reason = last_reason or 'inline point cloud has no points'
        else:
            source = f'{cloud_source} (section)'
            try:
                points = cloud_points
                if pca_frame is not None:
                    points = apply_pca_frame_to_points(points, pca_frame)
                return (
                    section_outline_from_points(
                        points,
                        slab_fraction=policy.slab_fraction,
                        concavity=concavity,
                        widen_sparse_slab=policy.widen_sparse_slab,
                        logger=logger,
                    ),
                    source,
                    None,
                )
            except Exception as exc:
                last_reason = f'{source}: {exc}'
                logger(last_reason)

    extrusion = first_extrusion(geometry)
    profile, profile_reason = rs.get_profile_from_component(component)
    if extrusion is not None:
        if policy.use_extrusion_profile and profile is not None:
            return profile, 'geometry.extrusions[0].profile', None
        source = 'geometry.extrusions[0] (section)'
        try:
            return (
                section_outline_from_mesh(
                    _build_extrusion_mesh(extrusion, pca_frame),
                    logger=logger,
                    concavity=concavity,
                ),
                source,
                None,
            )
        except Exception as exc:
            last_reason = f'{source}: {exc}'
            logger(last_reason)

    return None, None, last_reason or profile_reason or (
        'no outline-capable geometry'
    )
