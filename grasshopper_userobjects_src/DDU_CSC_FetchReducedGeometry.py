#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA
import Rhino.Geometry as rg  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchReducedGeometry'  # NOQA
ghenv.Component.NickName = 'FetchReducedGeometry'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches the reduced (catalog default) snapshot geometry as binary PLY '
    'from the CSC API, with ETag caching.\n'
    'Input can be:\n'
    '- Geometry carrying the \'csc_component\' compose userstring\n'
    '- A compose JSON string ({identity, snapshots[]})\n'
    '- A raw identity_id (resolves the current snapshot)\n'
    '- A raw snapshot_id\n\n'
    'Falls back to the inline snapshot geometry (primitive meshes) when no '
    'reduced PLY is available. Point clouds have no reduced PLY; the inline '
    'preview (at most 5000 points) is returned instead.'
)


class CSC_FetchReducedGeometry(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260826
    """

    # Resolution preference chain (reduced only; inline fallback otherwise)
    resolution_chain = ['reduced']
    # Point clouds have no reduced PLY; always use the inline preview.
    fetch_point_cloud_ply = False

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Input can be:\n'
            '- Geometry with the \'csc_component\' compose userstring\n'
            '- A compose JSON string ({identity, snapshots[]})\n'
            '- A raw identity_id (resolves current snapshot)\n'
            '- A raw snapshot_id'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Fetched reduced geometry as Rhino meshes and point clouds '
            '(one object per snapshot primitive)'
        )
        self.OutputParams[1+i].Description = (
            'Per-primitive source: reduced (mesh PLY) or primitive '
            '(inline fallback, including point-cloud previews)'
        )
        self.OutputParams[2+i].Description = (
            'Snapshot ID that was processed'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def parse_json_safe(self, value):
        """Parse a JSON string, returning None on failure."""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    def normalize_compose(self, obj):
        """
        Classify a parsed JSON object into canonical compose
        {identity, snapshots[]}, or None.
        """
        if not isinstance(obj, dict):
            return None
        identity = obj.get('identity') or {}
        snaps = obj.get('snapshots') or []
        if snaps and isinstance(snaps[0], dict):
            return {'identity': identity, 'snapshots': snaps}
        snap = obj.get('snapshot')
        if isinstance(snap, dict):
            return {'identity': identity, 'snapshots': [snap]}
        # Bare snapshot document
        if 'geometry' in obj and 'identity_id' in obj:
            return {'identity': {}, 'snapshots': [obj]}
        return None

    def primary_snapshot(self, compose):
        """Return the snapshot row used for geometry fetch."""
        if not isinstance(compose, dict):
            return None
        snaps = compose.get('snapshots') or []
        if snaps and isinstance(snaps[0], dict):
            return snaps[0]
        return None

    def fetch_compose_by_identity(self, auth_core, identity_id):
        """Fetch {identity, snapshots[]} for an identity's current snapshot."""
        try:
            resp = auth_core.cached_get_compose(identity_id)
            if resp.status_code == 200:
                return auth_core.normalize_compose_output(resp.json())
        except Exception as e:
            self._addWarning(f'Identity compose fetch failed: {str(e)}')
        return None

    def fetch_compose_by_snapshot(self, auth_core, snapshot_id):
        """Build minimal compose from a bare snapshot document."""
        try:
            resp = auth_core.authorized_get(f'/snapshots/{snapshot_id}')
            if resp.status_code == 200:
                return {'identity': {}, 'snapshots': [resp.json()]}
        except Exception as e:
            self._addWarning(f'Snapshot fetch failed: {str(e)}')
        return None

    def resolve_compose(self, auth_core, Input):
        """
        Resolve the input into canonical compose {identity, snapshots[]}.
        Returns (compose_or_None, input_is_geometry).
        """
        input_is_geometry = isinstance(Input, rg.GeometryBase)

        # Geometry carrying the compose userstring
        if (hasattr(Input, 'UserStringCount') and
                Input.UserStringCount > 0):
            value = Input.GetUserString('csc_component')
            if value:
                compose = self.normalize_compose(
                    self.parse_json_safe(value))
                if compose:
                    return compose, input_is_geometry

        # String input: compose JSON, identity doc, or raw UUID
        if isinstance(Input, str):
            s = Input.strip()
            obj = self.parse_json_safe(s)
            if obj is not None:
                compose = self.normalize_compose(obj)
                if compose:
                    return compose, input_is_geometry
                # Identity document with a current snapshot pointer
                if (isinstance(obj, dict) and obj.get('_id') and
                        obj.get('current_snapshot_id')):
                    compose = self.fetch_compose_by_identity(
                        auth_core, obj['_id'])
                    if compose:
                        return compose, input_is_geometry
                return None, input_is_geometry
            # Not JSON: treat as a raw UUID (identity first, then snapshot)
            if auth_core.validate_uuid(s):
                compose = self.fetch_compose_by_identity(auth_core, s)
                if compose:
                    return compose, input_is_geometry
                compose = self.fetch_compose_by_snapshot(auth_core, s)
                if compose:
                    return compose, input_is_geometry

        return None, input_is_geometry

    def build_inline_mesh(self, mesh_data, default_color):
        """Build a Rhino mesh from an inline SnapshotMesh (Rhino Z-up)."""
        vertices = mesh_data.get('vertices')
        faces = mesh_data.get('faces')
        if not vertices or not faces:
            return None
        mesh = rg.Mesh()
        for v in vertices:
            mesh.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for f in faces:
            if len(f) == 3:
                mesh.Faces.AddFace(f[0], f[1], f[2])
            elif len(f) == 4:
                mesh.Faces.AddFace(f[0], f[1], f[2], f[3])
        colors = mesh_data.get('colors')
        if colors and len(colors) == len(vertices):
            for c in colors:
                mesh.VertexColors.Add(int(c[0]), int(c[1]), int(c[2]))
        elif default_color:
            try:
                r, g, b = default_color
                for _ in range(len(vertices)):
                    mesh.VertexColors.Add(int(r), int(g), int(b))
            except (ValueError, TypeError):
                pass
        mesh.Normals.ComputeNormals()
        mesh.Compact()
        return mesh

    def iframe_xform(self, snapshot):
        """Build the world->iframe transform from the snapshot iframe."""
        iframe = snapshot.get('iframe')
        if not iframe:
            return None
        try:
            plane = rg.Plane(
                rg.Point3d(*iframe['o']),
                rg.Vector3d(*iframe['x']),
                rg.Vector3d(*iframe['y']),
            )
            return rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plane)
        except (KeyError, TypeError):
            return None

    def fetch_primitive_meshes(self, auth_core, snapshot):
        """
        Fetch one mesh per snapshot mesh primitive, preferring the PLY
        resolution chain and falling back to inline geometry.
        Returns a list of (mesh, source) tuples.
        """
        snapshot_id = snapshot.get('_id')
        geometry = snapshot.get('geometry', {}) or {}
        inline_meshes = geometry.get('meshes', []) or []
        res_map = snapshot.get('mesh_ply_resolutions', {}) or {}
        default_color = snapshot.get('color') or [110, 110, 110]

        results = []
        for i in range(len(inline_meshes)):
            available = res_map.get(str(i), []) or []
            mesh = None
            source = None
            for resolution in self.resolution_chain:
                if resolution in available:
                    m, _etag, _from_cache = (
                        auth_core.cached_get_snapshot_mesh(
                            snapshot_id, i, resolution)
                    )
                    if m is not None:
                        mesh = m
                        source = resolution
                        break
            if mesh is None:
                mesh = self.build_inline_mesh(inline_meshes[i], default_color)
                source = 'primitive'
            if mesh is not None:
                results.append((mesh, source))
        return results

    def build_inline_point_cloud(self, pc_data):
        """Build a Rhino point cloud from one inline SnapshotPointCloud."""
        if not isinstance(pc_data, dict):
            return None
        pts = pc_data.get('points', []) or []
        if not pts:
            return None
        cloud = rg.PointCloud()
        colors = pc_data.get('colors')
        if colors and len(colors) == len(pts):
            for p, c in zip(pts, colors):
                cloud.Add(
                    rg.Point3d(float(p[0]), float(p[1]), float(p[2])),
                    System.Drawing.Color.FromArgb(*[int(v) for v in c]),
                )
        else:
            for p in pts:
                cloud.Add(rg.Point3d(float(p[0]), float(p[1]), float(p[2])))
        return cloud if cloud.Count > 0 else None

    def fetch_primitive_point_clouds(self, auth_core, snapshot):
        """
        Fetch one point cloud per snapshot primitive.

        FetchReduced uses the inline preview only (no reduced PLY exists).
        FetchDetailed prefers the full PLY, then the inline preview.
        Returns a list of (cloud, source) tuples.
        """
        geometry = snapshot.get('geometry', {}) or {}
        inline_pcs = geometry.get('point_clouds', []) or []
        snapshot_id = snapshot.get('_id')
        results = []
        for i in range(len(inline_pcs)):
            cloud = None
            source = None
            if self.fetch_point_cloud_ply and auth_core and snapshot_id:
                try:
                    cloud = auth_core.cached_get_snapshot_point_cloud(
                        snapshot_id, i)
                    if cloud is not None:
                        source = 'detailed'
                except Exception as e:
                    self._addWarning(
                        'Point cloud PLY fetch failed '
                        f'for index {i}: {str(e)}')
            if cloud is None:
                cloud = self.build_inline_point_cloud(inline_pcs[i])
                source = 'primitive'
            if cloud is not None:
                results.append((cloud, source))
        return results

    def collect_fetched_geometry(self, auth_core, snapshot):
        """
        Return meshes then point clouds as
        (geometry, source, kind, index) tuples.
        """
        items = []
        for i, (mesh, source) in enumerate(
                self.fetch_primitive_meshes(auth_core, snapshot)):
            items.append((mesh, source, 'mesh', i))
        for i, (cloud, source) in enumerate(
                self.fetch_primitive_point_clouds(auth_core, snapshot)):
            items.append((cloud, source, 'point_cloud', i))
        return items

    def select_fetched_geometry(self, Input, input_is_geometry, items):
        """
        If the input geometry carries a primitive index, return only that
        primitive of the matching kind.
        """
        if not (input_is_geometry and hasattr(Input, 'GetUserString')):
            return items
        if isinstance(Input, rg.PointCloud):
            raw = Input.GetUserString('csc_point_cloud_index')
            if raw:
                try:
                    idx = int(raw)
                except (TypeError, ValueError):
                    return items
                filtered = [
                    item for item in items
                    if item[2] == 'point_cloud' and item[3] == idx
                ]
                return filtered or items
            return items
        raw = Input.GetUserString('csc_mesh_index')
        if raw:
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                return items
            filtered = [
                item for item in items
                if item[2] == 'mesh' and item[3] == idx
            ]
            return filtered or items
        return items

    def RunScript(self, Input):
        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return

        # Input validation
        if not Input:
            msg = 'Please provide input data.'
            self._addWarning(msg)
            self.Component.Message = msg
            return

        # Set up outputs
        GeometryData = System.Collections.Generic.List[System.Object]()
        GeometrySource = System.Collections.Generic.List[str]()
        SnapshotID = System.Collections.Generic.List[str]()
        __Results = (GeometryData, GeometrySource, SnapshotID)

        try:
            self.Component.Message = 'Processing input...'

            compose, input_is_geometry = self.resolve_compose(
                auth_core, Input)
            snapshot = self.primary_snapshot(compose)
            if not compose or not snapshot:
                msg = 'Could not resolve a snapshot from input.'
                self._addError(msg)
                self.Component.Message = msg
                return __Results
            snapshot_id = snapshot.get('_id')
            if not snapshot_id or not auth_core.validate_uuid(snapshot_id):
                msg = f'Snapshot ID <{snapshot_id}> is not a valid UUID!'
                self._addError(msg)
                self.Component.Message = msg
                return __Results

            self.Component.Message = (
                f'Fetching reduced geometry for snapshot {snapshot_id}...'
            )

            items = self.collect_fetched_geometry(auth_core, snapshot)
            if not items:
                msg = f'No geometry available for snapshot {snapshot_id}'
                self._addError(msg)
                self.Component.Message = msg
                return __Results

            # Apply the iframe transform to position geometry in the document
            xform = self.iframe_xform(snapshot)
            if xform is not None:
                for geom, _source, _kind, _idx in items:
                    geom.Transform(xform)

            compose_json = auth_core.compose_json_string(compose)
            for geom, _source, kind, idx in items:
                if hasattr(geom, 'SetUserString'):
                    geom.SetUserString('csc_component', compose_json)
                    if kind == 'mesh':
                        geom.SetUserString('csc_mesh_index', str(idx))
                    else:
                        geom.SetUserString(
                            'csc_point_cloud_index', str(idx))

            selected = self.select_fetched_geometry(
                Input, input_is_geometry, items)
            for geom, source, _kind, _idx in selected:
                GeometryData.Add(geom)
                GeometrySource.Add(source)

            SnapshotID.Add(snapshot_id)

            mesh_count = sum(
                1 for _g, _s, kind, _i in selected if kind == 'mesh')
            pc_count = sum(
                1 for _g, _s, kind, _i in selected
                if kind == 'point_cloud')
            self.Component.Message = (
                f'Fetched reduced geometry ({mesh_count} mesh(es), '
                f'{pc_count} point cloud(s)) for {snapshot_id}'
            )
            self._addRemark(
                f'Fetched reduced geometry ({mesh_count} mesh(es), '
                f'{pc_count} point cloud(s)) for snapshot {snapshot_id}'
            )

            return __Results

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        return __Results
