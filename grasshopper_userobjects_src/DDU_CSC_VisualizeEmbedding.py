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
import System.Drawing  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'VisualizeEmbedding'  # NOQA
ghenv.Component.NickName = 'VisualizeEmbedding'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '8 Visualisation'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Visualises a low-dimensional embedding (e.g. from PCA or t-SNE) by '
    'placing the associated input geometry at its embedding coordinate. '
    'Supports 1D, 2D and 3D layouts; when the embedding has more than 3 '
    'dimensions the remaining dimensions (4, 5, 6) are mapped to RGB colour '
    'channels. Each embedding dimension is min-max normalised to '
    '[0, ScaleFactor] per axis so the whole layout fits within the given '
    'extent.'
)

_EPS: float = 1e-12


def _minmax_normalise(values: np.ndarray) -> np.ndarray:
    """Column-wise min-max normalise a (N, D) array to [0, 1].

    Columns whose range is below ``_EPS`` collapse to 0.5 (centre) so the
    layout does not explode along a constant axis.
    """
    V = np.asarray(values, dtype=np.float64)
    if V.ndim != 2:
        raise ValueError(
            f'expected a 2D (N, D) array, got shape {V.shape}'
        )
    v_min = V.min(axis=0)
    v_max = V.max(axis=0)
    v_range = v_max - v_min

    out = np.empty_like(V)
    for d in range(V.shape[1]):
        if v_range[d] < _EPS:
            out[:, d] = 0.5
        else:
            out[:, d] = (V[:, d] - v_min[d]) / v_range[d]
    return out


def _embedding_to_layout(values: np.ndarray, scale: float):
    """
    Map a (N, D) embedding to layout points and optional RGB colours.

    Returns:
        points: (N, 3) float array in world units
        colors: (N, 3) uint8 array in [0, 255] (RGB)
        dims_used_pos: int, how many embedding dims were used for position
        dims_used_col: int, how many embedding dims were used for colour
    """
    normed = _minmax_normalise(values)
    n, d = normed.shape

    points = np.zeros((n, 3), dtype=np.float64)
    dims_used_pos = min(d, 3)
    for ax in range(dims_used_pos):
        points[:, ax] = normed[:, ax] * float(scale)

    colors = np.full((n, 3), 128, dtype=np.int32)
    dims_used_col = max(0, min(d - 3, 3))
    for ch in range(dims_used_col):
        colors[:, ch] = np.clip(
            np.round(normed[:, 3 + ch] * 255.0), 0, 255
        ).astype(np.int32)

    return points, colors, dims_used_pos, dims_used_col


def _geometry_bbox(geometry):
    """
    Return the world-aligned bounding box of a piece of geometry, or
    ``None`` if one cannot be computed.
    """
    if geometry is None:
        return None

    if hasattr(geometry, 'GetBoundingBox'):
        bbox = geometry.GetBoundingBox(True)
        if bbox is not None and bbox.IsValid:
            return bbox

    if isinstance(geometry, Rhino.Geometry.Point3d):
        return Rhino.Geometry.BoundingBox(geometry, geometry)

    return None


def _branch_anchor(geometries) -> Rhino.Geometry.Point3d:
    """
    Return the combined bounding-box centre of all geometries in a branch.

    All valid items in the branch contribute to one union bounding box;
    the centre of that union is used as the shared anchor so every
    geometry in the branch receives the same translation and their
    relative arrangement is preserved.
    """
    union = Rhino.Geometry.BoundingBox.Empty
    any_valid = False
    for geo in geometries:
        bbox = _geometry_bbox(geo)
        if bbox is None:
            continue
        union.Union(bbox)
        any_valid = True

    if not any_valid or not union.IsValid:
        raise ValueError(
            'cannot determine an anchor point: no geometry in branch '
            'has a valid bounding box'
        )
    return union.Center


class CSC_VisualizeEmbedding(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Embedded data as a DataTree where each branch represents one '
            'embedded datapoint and its items are the coordinates in the '
            'embedding space (e.g. output of ComputePCA or ComputeTSNE). '
            'Supports any number of dimensions; dimensions beyond the third '
            'are mapped to RGB colour channels.'
        )
        self.InputParams[1].Description = (
            'Geometry to place in the layout as a DataTree. One branch '
            'represents one datapoint; each branch may contain one or '
            'more geometries that are translated together as a rigid '
            'group (sharing a combined bounding-box anchor). Branch order '
            'must match the branch order of EmbeddedData.'
        )
        self.InputParams[2].Description = (
            'Total extent of the layout in world units. Each embedding '
            'dimension is min-max normalised to [0, ScaleFactor] before '
            'being used as a world-space coordinate. Default: 1000.0.'
        )

        # Output descriptions -- skip the hidden "out" param if present.
        i = 1 if self.OutputParams[0].Name == 'out' else 0
        self.OutputParams[0 + i].Description = (
            'Input geometry translated from its bounding-box centre to the '
            'corresponding embedding point in world coordinates.'
        )
        self.OutputParams[1 + i].Description = (
            'Embedding points in world coordinates, one per datapoint. '
            'For 1D embeddings Y = Z = 0; for 2D embeddings Z = 0.'
        )
        self.OutputParams[2 + i].Description = (
            'Per-datapoint RGB colour derived from embedding dimensions '
            '4, 5 and 6 (if present), each normalised to [0, 255]. Missing '
            'channels default to 128 (mid-grey), so low-dimensional '
            'embeddings still produce a usable colour output.'
        )
        self.OutputParams[3 + i].Description = (
            'The translation transform applied to each input geometry '
            '(useful to transform additional geometry into the same layout).'
        )

    def RunScript(self,
            EmbeddedData: Grasshopper.DataTree[float],
            Geometry: Grasshopper.DataTree[object],
            ScaleFactor: float):

        # init outputs
        LayoutGeometry = Grasshopper.DataTree[System.Object]()
        LayoutPoints = Grasshopper.DataTree[System.Object]()
        Colors = Grasshopper.DataTree[System.Object]()
        XForm = Grasshopper.DataTree[System.Object]()
        __Results = (LayoutGeometry, LayoutPoints, Colors, XForm)

        self.Component.Message = None

        # input validation
        if EmbeddedData is None or EmbeddedData.DataCount == 0:
            msg = 'EmbeddedData failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return __Results

        if Geometry is None or Geometry.DataCount == 0:
            msg = 'Geometry failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return __Results

        if ScaleFactor is None:
            ScaleFactor = 1000.0
        try:
            ScaleFactor = float(ScaleFactor)
        except (TypeError, ValueError):
            self._addError(
                f'ScaleFactor must be a number, got {ScaleFactor!r}')
            return __Results
        if not np.isfinite(ScaleFactor) or ScaleFactor <= 0.0:
            self._addError(
                f'ScaleFactor must be > 0, got {ScaleFactor}')
            return __Results

        # collect embedding values into a dense (N, D) array
        paths = list(EmbeddedData.Paths)
        branches = [list(EmbeddedData.Branch(p)) for p in paths]
        n_points = len(branches)

        if n_points < 2:
            self._addError(
                f'Need at least 2 embedded datapoints to build a layout, '
                f'got {n_points}'
            )
            return __Results

        dims = [len(b) for b in branches]
        n_dims = max(dims) if dims else 0
        if n_dims < 1:
            self._addError('EmbeddedData branches are empty')
            return __Results
        if min(dims) != n_dims:
            self._addWarning(
                f'EmbeddedData branches have non-uniform dimensionality '
                f'(min={min(dims)}, max={n_dims}); missing values will be '
                f'treated as 0.0'
            )

        values = np.zeros((n_points, n_dims), dtype=np.float64)
        for i, b in enumerate(branches):
            for j, v in enumerate(b):
                try:
                    values[i, j] = float(v)
                except (TypeError, ValueError):
                    values[i, j] = 0.0

        # Collect geometry branches; each branch == one datapoint
        geo_paths = list(Geometry.Paths)
        geo_branches = [list(Geometry.Branch(p)) for p in geo_paths]
        n_geo = len(geo_branches)

        if n_geo != n_points:
            self._addWarning(
                f'Geometry branch count ({n_geo}) does not match '
                f'EmbeddedData branch count ({n_points}); the shorter of '
                f'the two will be used.'
            )
        n_use = min(n_points, n_geo)

        # Compute layout
        try:
            points, colors_rgb, dims_pos, dims_col = _embedding_to_layout(
                values, ScaleFactor
            )
        except ValueError as exc:
            self._addError(f'Could not compute layout: {exc}')
            return __Results

        # Emit per-datapoint results
        successes = 0
        rc = self.Component.RunCount - 1
        for i in range(n_use):
            path = Grasshopper.Kernel.Data.GH_Path(rc, i)
            branch = [g for g in geo_branches[i] if g is not None]

            if not branch:
                self._addWarning(
                    f'Datapoint #{i}: geometry branch is empty or all '
                    f'None; skipped')
                continue

            try:
                anchor = _branch_anchor(branch)
            except ValueError as exc:
                self._addWarning(
                    f'Datapoint #{i}: {exc}; skipped')
                continue

            target = Rhino.Geometry.Point3d(
                float(points[i, 0]),
                float(points[i, 1]),
                float(points[i, 2]),
            )
            translation = Rhino.Geometry.Vector3d(
                target.X - anchor.X,
                target.Y - anchor.Y,
                target.Z - anchor.Z,
            )
            xform = Rhino.Geometry.Transform.Translation(translation)

            moved_items = []
            for j, geo in enumerate(branch):
                try:
                    moved = (geo.Duplicate()
                             if hasattr(geo, 'Duplicate') else geo)
                    if hasattr(moved, 'Transform'):
                        moved.Transform(xform)
                    else:
                        self._addWarning(
                            f'Datapoint #{i}, item #{j}: geometry does '
                            f'not support Transform; emitting original '
                            f'geometry unchanged'
                        )
                    moved_items.append(moved)
                except Exception as exc:
                    self._addWarning(
                        f'Datapoint #{i}, item #{j}: transform failed '
                        f'({exc}); skipped')
                    continue

            if not moved_items:
                self._addWarning(
                    f'Datapoint #{i}: no item transformed successfully; '
                    f'skipped')
                continue

            color = System.Drawing.Color.FromArgb(
                255,
                int(colors_rgb[i, 0]),
                int(colors_rgb[i, 1]),
                int(colors_rgb[i, 2]),
            )

            LayoutGeometry.AddRange(moved_items, path)
            LayoutPoints.Add(target, path)
            Colors.Add(color, path)
            XForm.Add(xform, path)
            successes += 1

        if successes == 0:
            self._addWarning('No datapoints produced valid output')
            self.Component.Message = 'no output'
        else:
            parts = ['']
            if dims_pos == 1:
                parts = ['1D layout']
            elif dims_pos == 2:
                parts = ['2D layout']
            elif dims_pos == 3:
                parts = ['3D layout']
            if dims_col > 0:
                parts.append(f'+{dims_col}ch colour')
                self.Component.Message = ' | '.join(parts)
            else:
                self.Component.Message = parts[0]
            self._addRemark(
                f'Placed {successes} geometry object(s) using '
                f'{dims_pos} position dim(s) and {dims_col} colour dim(s) '
                f'out of {n_dims} embedding dim(s).'
            )

        return __Results
