#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'RadialSignature'  # NOQA
ghenv.Component.NickName = 'RadialSignature'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Radial shape signature for planar boundary curves: rotates each curve '
    'into its canonical rest position (min-bbox-edge orientation), casts '
    'N evenly spaced rays from the centroid, and returns the distance to '
    'the first boundary intersection together with the boundary tangent '
    'at that intersection. Mirrors the backend `radial_signature` module.'
)


# -----------------------------------------------------------------------------
# PURE GEOMETRY HELPERS (port of apps/descriptors/radial_signature.py)
# -----------------------------------------------------------------------------
# Kept as module-level functions so they can be unit-tested / reused without
# the Grasshopper component shell, and so they stay numerically identical to
# the backend reference implementation.

_COINCIDENT_EPS: float = 1e-9
_DEFAULT_REST_ANGLES: int = 180


def _as_profile_array(profile) -> np.ndarray:
    """Validate and return an (M, 2) float array of profile points."""
    P = np.asarray(profile, dtype=np.float64)
    if P.ndim != 2 or P.shape[1] != 2:
        raise ValueError(
            f'profile must be a sequence of [x, y] pairs, got shape {P.shape}'
        )
    if len(P) < 3:
        raise ValueError(
            f'profile must have at least 3 points, got {len(P)}'
        )
    # Drop a duplicate closing vertex if present; the polyline is always
    # treated as an implicit closed polygon.
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
        if len(P) < 3:
            raise ValueError(
                'profile collapses to fewer than 3 unique points'
            )
    return P


def _polygon_centroid_2d(profile: np.ndarray) -> np.ndarray:
    """Shoelace area-weighted centroid of a closed 2D polygon."""
    x, y = profile[:, 0], profile[:, 1]
    xn = np.roll(x, -1)
    yn = np.roll(y, -1)
    cross = x * yn - xn * y
    area2 = cross.sum()
    if abs(area2) < _COINCIDENT_EPS:
        return profile.mean(axis=0)
    cx = ((x + xn) * cross).sum() / (3.0 * area2)
    cy = ((y + yn) * cross).sum() / (3.0 * area2)
    return np.array([cx, cy], dtype=np.float64)


def _rotation_matrix_2d(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def _rest_position(profile: np.ndarray,
                   num_angles: int = _DEFAULT_REST_ANGLES):
    """Rotate a planar polygon into its canonical rest orientation.

    Faithful port of the legacy C# `RestPosition` routine: for each of
    ``num_angles`` sample angles in [0, pi), rotate the centered profile and
    measure the absolute distance from the origin to each of the four
    axis-aligned bbox edges (|ymin|, |xmax|, |ymax|, |xmin|). The sample
    that produces the smallest such distance, combined with a 90 degree
    correction indexed by which edge was closest, defines the canonical
    rotation.

    Returns:
        rotated: (M, 2) rotated & centered profile
        centroid: (2,) centroid that was subtracted from the input
        angle_deg: rotation applied to the centered profile, degrees
    """
    if num_angles < 1:
        raise ValueError(f'num_angles must be >= 1, got {num_angles}')

    centroid = _polygon_centroid_2d(profile)
    centered = profile - centroid

    step_deg = 180.0 / num_angles
    min_edge_distances = np.empty(num_angles, dtype=np.float64)
    min_edge_corners = np.empty(num_angles, dtype=np.int64)
    for i in range(num_angles):
        ang_rad = np.deg2rad(i * step_deg)
        R = _rotation_matrix_2d(ang_rad)
        Q = centered @ R.T
        xmin, ymin = Q.min(axis=0)
        xmax, ymax = Q.max(axis=0)
        edges = np.array([abs(ymin), abs(xmax), abs(ymax), abs(xmin)])
        j = int(np.argmin(edges))
        min_edge_distances[i] = edges[j]
        min_edge_corners[i] = j

    best_sample = int(np.argmin(min_edge_distances))
    corner = int(min_edge_corners[best_sample])
    angle_deg = -(corner * 90.0) + best_sample * step_deg
    angle_rad = np.deg2rad(angle_deg)
    R_final = _rotation_matrix_2d(angle_rad)
    rotated = centered @ R_final.T
    return rotated, centroid, float(angle_deg)


def _ray_polyline_distances_and_tangents(profile: np.ndarray,
                                         directions: np.ndarray):
    """For each ray, return (distance, unit tangent) of the first boundary hit.

    Rays originate at (0, 0). Segments are the closed polygon edges
    p_i -> p_(i+1 mod M). Returns NaN where no forward hit exists.
    """
    A = profile                       # (M, 2) segment starts
    B = np.roll(profile, -1, axis=0)  # (M, 2) segment ends
    D = B - A                         # (M, 2) segment vectors

    seg_len = np.linalg.norm(D, axis=1)
    valid_seg = seg_len > _COINCIDENT_EPS
    T = np.full_like(D, np.nan)
    T[valid_seg] = D[valid_seg] / seg_len[valid_seg, None]

    R = directions  # (N, 2)
    # denom[n, m] = R[n] x D[m]
    denom = R[:, 0:1] * D[None, :, 1] - R[:, 1:2] * D[None, :, 0]
    A_cross_D = A[:, 0] * D[:, 1] - A[:, 1] * D[:, 0]
    A_cross_R = (A[None, :, 0] * R[:, 1:2]
                 - A[None, :, 1] * R[:, 0:1])

    safe = (np.abs(denom) > _COINCIDENT_EPS) & valid_seg[None, :]
    denom_safe = np.where(safe, denom, 1.0)

    t = A_cross_D[None, :] / denom_safe
    s = A_cross_R / denom_safe

    hit = (
        safe
        & (t >= 0.0)
        & (s >= -_COINCIDENT_EPS)
        & (s <= 1.0 + _COINCIDENT_EPS)
    )

    t_masked = np.where(hit, t, np.inf)
    best_seg = np.argmin(t_masked, axis=1)
    best_t = t_masked[np.arange(len(R)), best_seg]

    miss = ~np.isfinite(best_t)
    distances = np.where(miss, np.nan, best_t)
    tangents = T[best_seg]
    tangents[miss] = np.nan
    return distances, tangents


def _compute_radial_signature(profile, num_rays: int,
                              rest_align: bool = True,
                              num_rest_angles: int = _DEFAULT_REST_ANGLES):
    """Compute distances & tangents for one polygon profile.

    Returns:
        distances: (N,) ndarray
        tangents: (N, 2) ndarray
        centroid: (2,) ndarray (the one that was subtracted)
        angle_deg: float rotation applied to reach rest (0.0 if not aligned)
    """
    if num_rays < 3:
        raise ValueError(f'num_rays must be >= 3, got {num_rays}')

    P = _as_profile_array(profile)
    if rest_align:
        P_rest, centroid, angle_deg = _rest_position(
            P, num_angles=num_rest_angles)
    else:
        centroid = _polygon_centroid_2d(P)
        P_rest = P - centroid
        angle_deg = 0.0

    angles = np.arange(num_rays) * (2.0 * np.pi / num_rays)
    directions = np.column_stack([np.cos(angles), np.sin(angles)])
    distances, tangents = _ray_polyline_distances_and_tangents(
        P_rest, directions)
    return distances, tangents, centroid, angle_deg


class CSC_RadialSignature(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260423
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Describe inputs & outputs."""
        self.InputParams[0].Description = (
            'Closed planar boundary curve(s) to describe. Polylines are '
            'used verbatim; other curves are approximated to polylines '
            'using the document tolerance.'
        )
        self.InputParams[1].Description = (
            'Number of rays cast from the centroid. Default 64. '
            'Must be >= 3.'
        )
        self.InputParams[2].Description = (
            'If True (default), rotate each profile into its canonical '
            'rest position (minimum bbox edge distance) before ray '
            'casting. If False, use the curve as-is (still centered).'
        )
        self.InputParams[3].Description = (
            'Number of rotation samples used for rest-position search '
            'over [0, pi). Default 180 (1 degree steps). Must be >= 1.'
        )
        # Output descriptions -- skip the hidden "out" param if present.
        i = 1 if self.OutputParams[0].Name == 'out' else 0
        self.OutputParams[0 + i].Description = (
            'Tree of distances from the centroid to the first boundary '
            'intersection for each ray. One branch per input curve.'
        )
        self.OutputParams[1 + i].Description = (
            'Tree of unit tangent vectors of the boundary at each ray '
            'hit, expressed in world coordinates on the curve plane.'
        )
        self.OutputParams[2 + i].Description = (
            'Tree of intersection points in world coordinates, one '
            'branch per input curve. Useful for visualising the signature.'
        )
        self.OutputParams[3 + i].Description = (
            'Tree of rays (as Lines) in world coordinates, one branch '
            'per input curve. Useful for visualisation.'
        )
        self.OutputParams[4 + i].Description = (
            'Input curves transformed into their rest position: centroid '
            'at world origin, canonical rest axes aligned with World XY. '
            'This is exactly the geometry the signature is computed on.'
        )
        self.OutputParams[5 + i].Description = (
            'List of rest-position planes, one per input curve. Origin '
            'is the centroid on the input curve plane; X/Y are aligned '
            'with the canonical orientation used by the signature.'
        )
        self.OutputParams[6 + i].Description = (
            'List of rotation angles (degrees) applied to reach rest '
            'position, one per input curve.'
        )
        self.OutputParams[7 + i].Description = (
            'Transform mapping world coordinates into the rest frame '
            '(origin at centroid; World XY only if RestPositionAlign is '
            'True). Apply to any other geometry to see it in the same '
            'frame as the rest curve.'
        )

    def _curve_to_polyline_and_plane(self, curve):
        """Return (polyline_points_3d, curve_plane) or (None, None).

        Falls back to ``Plane.WorldXY`` for non-planar or degenerate curves
        and adds a warning.
        """
        if curve is None:
            return None, None

        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        if tol is None or tol <= 0.0:
            tol = 1e-3

        # Fetch an actual Polyline -- exact for polylines / polygons, an
        # approximation otherwise (angle-based to preserve curvature).
        ok, pl = curve.TryGetPolyline()
        if not ok or pl is None or pl.Count < 3:
            pc = curve.ToPolyline(
                0,           # mainSegmentCount (0 = auto)
                0,           # subSegmentCount
                0.1,         # maxAngleRadians (~5.7 deg chord deviation)
                0.0,         # maxChordLengthRatio
                0.0,         # maxAspectRatio
                tol,         # tolerance
                0.0,         # minEdgeLength
                0.0,         # maxEdgeLength
                True,        # keepStartPoint
            )
            if pc is None:
                return None, None
            pl = pc.ToPolyline()
            if pl is None or pl.Count < 3:
                return None, None

        ok_plane, plane = curve.TryGetPlane(tol)
        if not ok_plane:
            self._addWarning(
                'Curve is not planar within tolerance; falling back to '
                'World XY. Consider supplying a planar curve.'
            )
            plane = Rhino.Geometry.Plane.WorldXY

        return pl, plane

    def _project_polyline_to_plane(self, polyline, plane):
        """Project polyline vertices to the curve's plane. Returns (M, 2)."""
        xform = Rhino.Geometry.Transform.PlaneToPlane(
            plane, Rhino.Geometry.Plane.WorldXY)
        pts_2d = []
        for p in polyline:
            q = Rhino.Geometry.Point3d(p)
            q.Transform(xform)
            pts_2d.append([q.X, q.Y])
        return np.asarray(pts_2d, dtype=np.float64)

    def _rest_frame_in_world(self, plane, centroid_xy, rest_angle_deg):
        """Build a Rhino.Geometry.Plane placed at the rest-position origin.

        The plane's origin is the 3D centroid; its X/Y axes correspond to
        the rest-aligned 2D frame rotated back into world coordinates.
        """
        # Rest frame in curve-plane coordinates: origin is the centroid,
        # axes are rotated by ``rest_angle_deg`` around +Z relative to the
        # curve plane. Since a point ``q`` in the original 2D frame maps
        # to ``R * (q - c)`` in the rest frame, the inverse mapping back
        # to the curve plane is a rotation by ``-rest_angle_deg``.
        theta = np.deg2rad(-rest_angle_deg)
        c, s = float(np.cos(theta)), float(np.sin(theta))
        x_axis_xy = np.array([c, s, 0.0])
        y_axis_xy = np.array([-s, c, 0.0])

        origin_xy = Rhino.Geometry.Point3d(
            float(centroid_xy[0]), float(centroid_xy[1]), 0.0)
        xform = Rhino.Geometry.Transform.PlaneToPlane(
            Rhino.Geometry.Plane.WorldXY, plane)
        origin_3d = Rhino.Geometry.Point3d(origin_xy)
        origin_3d.Transform(xform)

        x_vec_3d = Rhino.Geometry.Vector3d(*x_axis_xy)
        y_vec_3d = Rhino.Geometry.Vector3d(*y_axis_xy)
        x_vec_3d.Transform(xform)
        y_vec_3d.Transform(xform)

        return Rhino.Geometry.Plane(origin_3d, x_vec_3d, y_vec_3d)

    def _xy_point_to_world(self, xform_to_plane, x, y):
        """Map a point in the curve-plane XY frame to world coordinates."""
        p = Rhino.Geometry.Point3d(float(x), float(y), 0.0)
        p.Transform(xform_to_plane)
        return p

    def _xy_vector_to_world(self, xform_to_plane, vx, vy):
        """Map a vector in the curve-plane XY frame to world coordinates."""
        v = Rhino.Geometry.Vector3d(float(vx), float(vy), 0.0)
        v.Transform(xform_to_plane)
        return v

    def RunScript(self,
            Curves: System.Collections.Generic.List[object],
            Resolution: int,
            RestPositionAlign: bool,
            NumAngles: int):
        # Keep list-access behavior by default. If the current input list
        # (which may represent one incoming branch) has multiple curves,
        # switch to explicit tree output keyed by run count + item index.
        multi_input = bool(Curves) and len(Curves) > 1
        if multi_input:
            Distances = Grasshopper.DataTree[System.Object]()
            Tangents = Grasshopper.DataTree[System.Object]()
            IntersectionPoints = Grasshopper.DataTree[System.Object]()
            Rays = Grasshopper.DataTree[System.Object]()
            RestPositionCurve = Grasshopper.DataTree[System.Object]()
            RestPositionFrame = Grasshopper.DataTree[System.Object]()
            RestPositionAngle = Grasshopper.DataTree[System.Object]()
            RestPositionTransform = Grasshopper.DataTree[System.Object]()
        else:
            Distances = []
            Tangents = []
            IntersectionPoints = []
            Rays = []
            RestPositionCurve = []
            RestPositionFrame = []
            RestPositionAngle = []
            RestPositionTransform = []
        __Results = (
            Distances, Tangents, IntersectionPoints, Rays,
            RestPositionCurve, RestPositionFrame,
            RestPositionAngle, RestPositionTransform,
        )

        # Defaults
        if Resolution is None:
            Resolution = 64
        if RestPositionAlign is None:
            RestPositionAlign = True
        if NumAngles is None:
            NumAngles = _DEFAULT_REST_ANGLES

        # Input validation
        if not Curves:
            msg = 'No curves provided'
            self._addWarning(msg)
            self.Component.Message = msg
            return __Results

        try:
            Resolution = int(Resolution)
        except (TypeError, ValueError):
            self._addError(
                f'Resolution must be an integer, got {Resolution!r}')
            return __Results
        if Resolution < 3:
            self._addError(f'Resolution must be >= 3, got {Resolution}')
            return __Results

        try:
            NumAngles = int(NumAngles)
        except (TypeError, ValueError):
            self._addError(
                f'NumAngles must be an integer, got '
                f'{NumAngles!r}')
            return __Results
        if NumAngles < 1:
            self._addError(
                f'NumAngles must be >= 1, got '
                f'{NumAngles}')
            return __Results

        self.Component.Message = f'N={Resolution}'

        successes = 0
        rc = self.Component.RunCount - 1
        for branch_idx, curve in enumerate(Curves):
            path = Grasshopper.Kernel.Data.GH_Path(rc, branch_idx)

            polyline, plane = self._curve_to_polyline_and_plane(curve)
            if polyline is None or plane is None:
                self._addWarning(
                    f'Curve #{branch_idx}: could not build polyline; skipped')
                continue

            try:
                profile_xy = self._project_polyline_to_plane(polyline, plane)
                distances, tangents, centroid_xy, angle_deg = (
                    _compute_radial_signature(
                        profile_xy,
                        num_rays=Resolution,
                        rest_align=bool(RestPositionAlign),
                        num_rest_angles=NumAngles,
                    )
                )
            except ValueError as exc:
                self._addWarning(
                    f'Curve #{branch_idx}: {exc}; skipped')
                continue

            if np.any(np.isnan(distances)):
                missed = int(np.isnan(distances).sum())
                self._addWarning(
                    f'Curve #{branch_idx}: {missed}/{Resolution} rays did '
                    f'not hit the boundary (centroid outside profile or '
                    f'non-simple polygon); skipped'
                )
                continue

            # Map results back to world coordinates.
            # In the rest frame: hit point = t * (cos a, sin a);
            # tangent = (tx, ty). The rest frame itself lives on the
            # curve plane at ``centroid_xy``, rotated by rest_angle_deg.
            # Build a combined transform 2D(rest) -> 2D(curve) -> world.
            rest_frame_curve = Rhino.Geometry.Plane(
                Rhino.Geometry.Point3d(
                    float(centroid_xy[0]), float(centroid_xy[1]), 0.0),
                Rhino.Geometry.Vector3d.XAxis,
                Rhino.Geometry.Vector3d.YAxis,
            )
            # Rotate the rest plane's X/Y by -rest_angle_deg so that a
            # point expressed in the rest frame maps back to the same
            # location in the curve-plane XY frame.
            theta = np.deg2rad(-angle_deg)
            c, s = float(np.cos(theta)), float(np.sin(theta))
            rest_x = Rhino.Geometry.Vector3d(c, s, 0.0)
            rest_y = Rhino.Geometry.Vector3d(-s, c, 0.0)
            rest_frame_curve = Rhino.Geometry.Plane(
                rest_frame_curve.Origin, rest_x, rest_y)

            xform_curve_to_world = Rhino.Geometry.Transform.PlaneToPlane(
                Rhino.Geometry.Plane.WorldXY, plane)

            # Combined mapper: 2D rest frame -> 3D world.
            def to_world_point(xr, yr):
                # Into curve XY frame first...
                px = rest_frame_curve.Origin.X + c * xr - s * yr
                py = rest_frame_curve.Origin.Y + s * xr + c * yr
                # ...then lift to world via the curve plane.
                p = Rhino.Geometry.Point3d(float(px), float(py), 0.0)
                p.Transform(xform_curve_to_world)
                return p

            def to_world_vector(vxr, vyr):
                vx = c * vxr - s * vyr
                vy = s * vxr + c * vyr
                v = Rhino.Geometry.Vector3d(float(vx), float(vy), 0.0)
                v.Transform(xform_curve_to_world)
                return v

            # Rays in the rest frame: origin (0, 0), direction (cos, sin).
            ray_angles = np.arange(Resolution) * (2.0 * np.pi / Resolution)
            ray_dirs = np.column_stack(
                [np.cos(ray_angles), np.sin(ray_angles)])

            world_origin = to_world_point(0.0, 0.0)

            distance_values = []
            tangent_values = []
            hit_points = []
            ray_lines = []
            for k in range(Resolution):
                t = float(distances[k])
                dx, dy = float(ray_dirs[k, 0]), float(ray_dirs[k, 1])
                hit_world = to_world_point(t * dx, t * dy)
                tx, ty = float(tangents[k, 0]), float(tangents[k, 1])
                tan_world = to_world_vector(tx, ty)

                distance_values.append(t)
                tangent_values.append(tan_world)
                hit_points.append(hit_world)
                ray_lines.append(
                    Rhino.Geometry.Line(world_origin, hit_world))

            if multi_input:
                Distances.AddRange(distance_values, path)
                Tangents.AddRange(tangent_values, path)
                IntersectionPoints.AddRange(hit_points, path)
                Rays.AddRange(ray_lines, path)
            else:
                Distances.extend(distance_values)
                Tangents.extend(tangent_values)
                IntersectionPoints.extend(hit_points)
                Rays.extend(ray_lines)

            # Rest-position frame expressed in world coordinates: origin
            # at the 3D centroid on the curve plane, X/Y axes aligned with
            # the canonical orientation picked by the rest-position search.
            rest_frame_world = self._rest_frame_in_world(
                plane, centroid_xy, angle_deg)

            # World -> rest-frame transform. Applying this to the input
            # curve moves it so its centroid sits at the world origin and
            # its rest-aligned axes coincide with the World XY axes -- i.e.
            # exactly what the signature "sees" internally.
            if RestPositionAlign:
                # Full rest-position transform: center + canonical orientation
                # into World XY.
                xform_world_to_rest = Rhino.Geometry.Transform.PlaneToPlane(
                    rest_frame_world, Rhino.Geometry.Plane.WorldXY)
            else:
                # No rest-position rotation: keep the curve orientation as-is
                # in world coordinates and only center it at the origin.
                xform_world_to_rest = Rhino.Geometry.Transform.Translation(
                    Rhino.Geometry.Vector3d(
                        -rest_frame_world.Origin.X,
                        -rest_frame_world.Origin.Y,
                        -rest_frame_world.Origin.Z,
                    )
                )
            rest_curve = curve.DuplicateCurve()
            rest_curve.Transform(xform_world_to_rest)

            if multi_input:
                RestPositionCurve.Add(rest_curve, path)
                RestPositionFrame.Add(rest_frame_world, path)
                RestPositionAngle.Add(float(angle_deg), path)
                RestPositionTransform.Add(xform_world_to_rest, path)
            else:
                RestPositionCurve.append(rest_curve)
                RestPositionFrame.append(rest_frame_world)
                RestPositionAngle.append(float(angle_deg))
                RestPositionTransform.append(xform_world_to_rest)

            successes += 1

        if successes == 0:
            self._addWarning('No curves produced a valid signature')
            self.Component.Message = 'no output'
        else:
            self.Component.Message = (
                f'N = {Resolution}')
            self._addRemark(
                f'Computed radial signature for {successes} curve(s) '
                f'at resolution N={Resolution}'
            )

        return __Results
