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
cross-section, concavities and all. Extrusions are turned into meshes and
cut the same way, because an extrusion's own profile lies in its extrusion
frame, which is only the PCA plane when the extrusion axis happens to be
the shortest one. Point clouds have no faces to cut, so the points within a
slab around the cut height are flattened and wrapped in a concave hull.

Panels are the exception, described by `PANEL_POLICY` below: they are thin
and prismatic, so their meaningful outline is the silhouette rather than a
band through the middle, and they can use an authored extrusion profile
directly.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import trimesh
from shapely import MultiPoint, concave_hull

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.descriptors import radial_signature as rs
from apps.descriptors.geometry import (
    apply_pca_frame_to_points,
    first_extrusion,
    load_extrusion_mesh_for_descriptor,
    load_primitive_mesh_for_descriptor,
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

_SECTION_RETRY_FRACTIONS: Tuple[float, ...] = (0.0, 0.02, -0.02, 0.1, -0.1)
"""Cut heights to try, as fractions of depth from the centre plane.

A plane exactly through the centre can land on a coplanar band of faces and
return nothing usable, so we step off it slightly before giving up.
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
    closed = [
        lp for lp in usable
        if np.allclose(lp[0], lp[-1], atol=_CLOSED_EPS)
    ]
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


# MESH SECTIONING -------------------------------------------------------------


def section_outline_from_mesh(
    mesh: trimesh.Trimesh,
    logger: LoggerFn = _noop_logger,
) -> List[List[float]]:
    """
    Cut a PCA-aligned mesh through its centre and return the outer loop.

    Args:
        mesh: PCA-aligned mesh, i.e. shortest principal axis on world Z.
        logger: optional progress logger.

    Returns:
        List of [x, y] vertices describing the closed outer boundary.

    Raises:
        ValueError: if no usable cross-section can be cut.
    """
    z_min = float(mesh.bounds[0][2])
    z_max = float(mesh.bounds[1][2])
    depth = z_max - z_min
    if not np.isfinite(depth) or depth <= 0.0:
        raise ValueError(
            f'Mesh has no extent along the section axis (depth {depth}); '
            f'it cannot be cut'
        )

    # The PCA frame puts the component's centre at the origin, so z = 0 is
    # the centre plane. Geometry stored without a frame can sit anywhere,
    # so fall back to the middle of the bounds rather than cutting thin air.
    centre = 0.0 if z_min < 0.0 < z_max else 0.5 * (z_min + z_max)

    for fraction in _SECTION_RETRY_FRACTIONS:
        height = centre + fraction * depth
        try:
            section = mesh.section(
                plane_origin=[0.0, 0.0, height],
                plane_normal=[0.0, 0.0, 1.0],
            )
        except Exception as exc:
            logger(f'section at z={height:.6g} failed: {exc}')
            continue
        if section is None:
            continue
        loop = _largest_loop([np.asarray(d)[:, :2] for d in section.discrete])
        if loop is None:
            continue
        if fraction != 0.0:
            logger(
                f'section through the centre was empty, cut at '
                f'{fraction:+.0%} of depth instead'
            )
        return _finalize_outline(loop)

    raise ValueError(
        'Mesh produced no usable cross-section at any candidate height'
    )


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


def _build_section_mesh(
    meshes: List[Dict],
    extrusion: Optional[Dict],
    pca_frame: Optional[Dict[str, List[float]]],
) -> trimesh.Trimesh:
    """Build the PCA-aligned mesh to cut from a component's inline geometry.

    Only reached when the runner did not already supply a mesh, in which
    case this rebuilds it from the reduced inline copy. That is enough for
    an outline, which is a low-frequency feature of the geometry.
    """
    if meshes:
        vertices = meshes[0].get('v') or meshes[0].get('vertices')
        faces = meshes[0].get('f') or meshes[0].get('faces')
        if not vertices or not faces:
            raise ValueError('inline mesh has no vertices or faces')
        return load_primitive_mesh_for_descriptor(
            vertices=vertices, faces=faces, pca_frame=pca_frame)
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
    logger: LoggerFn = _noop_logger,
) -> Tuple[Optional[List[List[float]]], Optional[str], Optional[str]]:
    """
    Resolve the best available 2D outline for a component.

    Priority:
        1. ``geometry.extrusions[0].profile`` - panels only, see
           `OutlinePolicy.use_extrusion_profile`
        2. ``geometry.meshes[0]``, else ``geometry.extrusions[0]`` swept
           into a mesh - cut through the centre
        3. ``geometry.point_clouds[0]`` - sliced and concave-hulled

    Meshes outrank clouds for the same reason they do in
    `geometry.load_snapshot_mesh`: when a snapshot carries both, they
    describe one object and the mesh is the higher-fidelity record.

    `mesh` is used only when the component actually carries mesh or
    extrusion geometry. A cloud-only snapshot resolves to its convex hull
    upstream, and hulling away the concavities is exactly what makes a
    radial signature meaningless, so that case re-reads the raw points.

    Args:
        component: snapshot or component document.
        mesh: PCA-aligned mesh the runner already loaded, if any.
        concavity: passed to `section_outline_from_points`.
        policy: how to reduce this component; defaults to `policy_for`.
        logger: optional progress logger.

    Returns:
        Tuple of ``(outline, source, reason)``. On success `reason` is None;
        on failure `outline` and `source` are None and `reason` is a short
        human-readable explanation.
    """
    policy = policy if policy is not None else policy_for(component)
    geometry = component.get('geometry') or {}
    pca_frame = component.get('pca_frame')

    profile, profile_reason = rs.get_profile_from_component(component)
    if policy.use_extrusion_profile and profile is not None:
        return profile, 'geometry.extrusions[0].profile', None

    meshes = geometry.get('meshes') or []
    extrusion = first_extrusion(geometry)
    if meshes or extrusion:
        source = (
            'geometry.meshes[0] (section)' if meshes
            else 'geometry.extrusions[0] (section)'
        )
        try:
            section_mesh = mesh
            if section_mesh is None:
                section_mesh = _build_section_mesh(
                    meshes, extrusion, pca_frame)
            return (
                section_outline_from_mesh(section_mesh, logger=logger),
                source,
                None,
            )
        except Exception as exc:
            return None, None, f'{source}: {exc}'

    point_clouds = geometry.get('point_clouds') or []
    if point_clouds:
        source = 'geometry.point_clouds[0] (section)'
        try:
            points = point_clouds[0].get('points') or []
            if not points:
                return None, None, 'inline point cloud has no points'
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
            return None, None, f'{source}: {exc}'

    return None, None, profile_reason or 'no outline-capable geometry'
