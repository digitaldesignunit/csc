#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import rhinoscriptsyntax as rs  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'BakeComponents'  # NOQA
ghenv.Component.NickName = 'BakeComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Bakes compose entries ({identity, snapshots[]}) into the Rhino document '
    'as actual geometry. Creates layers, groups, and attaches the full '
    'compose JSON as user text. Prioritizes cached PLY meshes and point '
    'clouds over inline snapshot primitives.'
)


class CSC_BakeComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260617
    """

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
            'Toggle to bake components to Rhino'
        )
        self.InputParams[1].Description = (
            'Compose JSON strings ({identity, snapshots[]}) from fetch '
            'components'
        )

    def ComponentExtrusions(
            self,
            geometry: dict) -> list[Rhino.Geometry.Extrusion]:
        """Create capped extrusions from geometry.extrusions list."""
        extrusions = []
        tol = Rhino.RhinoMath.SqrtEpsilon
        for extr in geometry.get('extrusions', []) or []:
            profile = extr.get('profile') or []
            if len(profile) < 3:
                continue

            pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
                   for pt in profile]
            if len(pts) >= 2 and pts[0].DistanceTo(pts[-1]) <= tol:
                pts = pts[:-1]
            if len(pts) < 3:
                continue

            pl = Rhino.Geometry.Polyline()
            pl.AddRange(pts)
            if not pl.IsClosed:
                pl.Add(pl[0])

            height = float(extr.get('height', 0))
            if height <= 0:
                continue

            cxt = Rhino.Geometry.Extrusion.Create(
                pl.ToPolylineCurve(),
                Rhino.Geometry.Plane.WorldXY,
                height,
                True)
            if cxt is None:
                continue

            cxt.Translate(Rhino.Geometry.Vector3d(0, 0, height * -0.5))
            extrusions.append(cxt)
        return extrusions

    def build_inline_mesh(self, mesh_data, default_color):
        """Build a Rhino mesh from an inline SnapshotMesh."""
        vertices = mesh_data.get('vertices')
        faces = mesh_data.get('faces')
        if not vertices or not faces:
            return None
        mesh = Rhino.Geometry.Mesh()
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

    def ComponentMeshes(
            self,
            geometry: dict,
            snapshot_color,
            identity_id: str) -> list[Rhino.Geometry.Mesh]:
        """Create meshes from snapshot.geometry.meshes inline primitives."""
        meshes = []
        for idx, mesh_data in enumerate(geometry.get('meshes', []) or []):
            mesh = self.build_inline_mesh(mesh_data, snapshot_color)
            if mesh is None:
                self._addWarning(
                    f'Inline mesh {idx} in identity {identity_id} is invalid')
                continue
            meshes.append(mesh)
        return meshes

    def ComponentColor(self, snapshot: dict) -> System.Drawing.Color:
        color = snapshot.get('color') or [110, 110, 110]
        return System.Drawing.Color.FromArgb(255, *color)

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            self._addWarning(
                'No authentication found. Using primitive geometry only.'
            )
            return None
        return auth_core

    def fetch_snapshot_meshes(self, auth_core, snapshot):
        """
        Fetch snapshot meshes via the unified PLY cache (detailed, then
        reduced), falling back to inline snapshot.geometry.meshes primitives.
        """
        if not auth_core:
            return None

        snapshot_id = snapshot.get('_id')
        geometry = snapshot.get('geometry', {}) or {}
        inline_meshes = geometry.get('meshes', []) or []
        if not snapshot_id or not inline_meshes:
            return None

        res_map = snapshot.get('mesh_ply_resolutions', {}) or {}
        default_color = snapshot.get('color') or [110, 110, 110]
        meshes = []

        for i in range(len(inline_meshes)):
            mesh = None
            available = res_map.get(str(i), []) or []
            for resolution in ('detailed', 'reduced'):
                if resolution in available:
                    m, _etag, _from_cache = auth_core.cached_get_snapshot_mesh(
                        snapshot_id, i, resolution)
                    if m is not None:
                        mesh = m
                        break
            if mesh is None:
                mesh = self.build_inline_mesh(inline_meshes[i], default_color)
            if mesh is not None:
                meshes.append(mesh)

        return meshes if meshes else None

    def build_inline_point_cloud(self, pc_data):
        """Build a Rhino point cloud from one inline SnapshotPointCloud."""
        if not isinstance(pc_data, dict):
            return None
        cloud = Rhino.Geometry.PointCloud()
        pts = pc_data.get('points', []) or []
        cl = pc_data.get('colors')
        if not pts:
            return None
        if cl and len(cl) == len(pts):
            for p, c in zip(pts, cl):
                cloud.Add(
                    Rhino.Geometry.Point3d(p[0], p[1], p[2]),
                    System.Drawing.Color.FromArgb(*c))
        else:
            for p in pts:
                cloud.Add(Rhino.Geometry.Point3d(p[0], p[1], p[2]))
        return cloud if cloud.Count > 0 else None

    def ComponentPointClouds(
            self,
            geometry: dict) -> list[Rhino.Geometry.PointCloud]:
        """Create point clouds from geometry.point_clouds inline primitives."""
        clouds = []
        for idx, pc_data in enumerate(geometry.get('point_clouds', []) or []):
            cloud = self.build_inline_point_cloud(pc_data)
            if cloud is None:
                self._addWarning(
                    f'Inline point cloud {idx} is invalid or empty')
                continue
            clouds.append(cloud)
        return clouds

    def fetch_snapshot_point_clouds(self, auth_core, snapshot):
        """
        Fetch snapshot point clouds via PLY when available, falling back to
        inline snapshot.geometry.point_clouds primitives.
        """
        geometry = snapshot.get('geometry', {}) or {}
        inline_pcs = geometry.get('point_clouds', []) or []
        if not inline_pcs:
            return None

        snapshot_id = snapshot.get('_id')
        clouds = []

        for i in range(len(inline_pcs)):
            cloud = None
            if auth_core and snapshot_id:
                try:
                    cloud = auth_core.cached_get_snapshot_point_cloud(
                        snapshot_id, i)
                except Exception as e:
                    self._addWarning(
                        'Point cloud PLY fetch failed '
                        f'for index {i}: {str(e)}')
            if cloud is None:
                cloud = self.build_inline_point_cloud(inline_pcs[i])
            if cloud is not None:
                clouds.append(cloud)

        return clouds if clouds else None

    def RunScript(self,
            Bake: bool,
            ComponentData: System.Collections.Generic.List[str]):
        # bake toggle
        if Bake:
            if not ComponentData or len(ComponentData) == 0:
                msg = ('No component data provided. Please connect '
                       'FetchComponent output.')
                self._addWarning(msg)
                self.Component.Message = msg
                return

            self.Component.Message = 'Baking components...'
            baked_count = 0

            # Get AuthCore for cached geometry
            auth_core = self.get_auth_core_from_sticky()

            # set document
            sc.doc = Rhino.RhinoDoc.ActiveDoc

            for i, cd in enumerate(ComponentData):
                comp_id = f'item {i}'
                try:
                    compose = json.loads(cd)
                    identity = compose.get('identity')
                    snapshots = compose.get('snapshots') or []
                    snapshot = snapshots[0] if snapshots else None
                    if (not isinstance(identity, dict) or
                            not isinstance(snapshot, dict)):
                        msg = (
                            f'Invalid compose JSON at index {i}: '
                            'expected {{identity, snapshot}}'
                        )
                        self._addWarning(msg)
                        continue

                    identity_id = identity.get('_id')
                    if not identity_id:
                        self._addWarning(
                            f'Missing identity._id in compose at index {i}')
                        continue
                    comp_id = identity_id

                    # determine unique group name (groups must be unique)
                    # use suffix indexing: <uuid>_1, <uuid>_2, ...
                    base_group_name = identity_id
                    idx = 1
                    existing_names = set()
                    for grp in sc.doc.Groups:
                        try:
                            existing_names.add(grp.Name)
                        except Exception:
                            continue
                    while True:
                        candidate = f'{base_group_name}_{idx}'
                        if candidate not in existing_names:
                            group_name = candidate
                            break
                        idx += 1

                    # get insertion plane from snapshot
                    try:
                        iframe = snapshot['iframe']
                        iplane = Rhino.Geometry.Plane(
                            Rhino.Geometry.Point3d(*iframe['o']),
                            Rhino.Geometry.Vector3d(*iframe['x']),
                            Rhino.Geometry.Vector3d(*iframe['y']),
                        )
                    except (KeyError, TypeError):
                        iplane = Rhino.Geometry.Plane.WorldXY

                    xform = Rhino.Geometry.Transform.PlaneToPlane(
                        Rhino.Geometry.Plane.WorldXY,
                        iplane)

                    cached_meshes = self.fetch_snapshot_meshes(
                        auth_core, snapshot)
                    geometry = snapshot.get('geometry', {}) or {}

                    # create component geometry
                    geo_ids = []

                    for xtr in self.ComponentExtrusions(geometry):
                        try:
                            xtr.Transform(xform)
                            geo_id = sc.doc.Objects.Add(xtr)
                            if geo_id != System.Guid.Empty:
                                geo_ids.append(geo_id)
                        except Exception as e:
                            self._addWarning(
                                f'Error baking extrusion: {str(e)}')

                    meshes = cached_meshes or self.ComponentMeshes(
                        geometry,
                        snapshot.get('color'),
                        identity_id)
                    for j, mesh in enumerate(meshes):
                        try:
                            mesh_copy = mesh.Duplicate() if cached_meshes else mesh  # NOQA
                            if mesh_copy and mesh_copy.IsValid:
                                mesh_copy.Transform(xform)
                                geo_id = sc.doc.Objects.Add(mesh_copy)
                                if geo_id != System.Guid.Empty:
                                    geo_ids.append(geo_id)
                                    rs.SetUserText(
                                        geo_id,
                                        'csc_mesh_index',
                                        str(j))
                                else:
                                    self._addWarning(
                                        f'Failed to add mesh {j} to document')
                            else:
                                self._addWarning(
                                    f'Invalid mesh {j} for '
                                    f'identity {identity_id}')
                        except Exception as e:
                            self._addWarning(
                                f'Error processing mesh {j}: {str(e)}')

                    point_clouds = self.fetch_snapshot_point_clouds(
                        auth_core, snapshot)
                    if point_clouds is None:
                        point_clouds = self.ComponentPointClouds(geometry)
                    for j, cloud in enumerate(point_clouds):
                        try:
                            cloud_copy = cloud.Duplicate()
                            if cloud_copy and cloud_copy.Count > 0:
                                cloud_copy.Transform(xform)
                                geo_id = sc.doc.Objects.Add(cloud_copy)
                                if geo_id != System.Guid.Empty:
                                    geo_ids.append(geo_id)
                                    rs.SetUserText(
                                        geo_id,
                                        'csc_point_cloud_index',
                                        str(j))
                                else:
                                    self._addWarning(
                                        f'Failed to add point cloud '
                                        f'{j} to document')
                            else:
                                self._addWarning(
                                    f'Invalid point cloud {j} for identity '
                                    f'{identity_id}')
                        except Exception as e:
                            self._addWarning(
                                f'Error processing point cloud {j}: {str(e)}')

                    for key in sorted(geometry.keys()):
                        if key in (
                                'meshes', 'extrusions', 'point_clouds',
                                'marker_points', 'reinforcements'):
                            continue
                        msg = (f'Missing implementation for geometry '
                               f'of type \'{key}\'!')
                        self._addWarning(msg)

                    if not geo_ids:
                        self._addWarning(
                            f'No geometry baked for identity {identity_id}')
                        continue

                    # add objects to document
                    # create layers if they are not present
                    lay_parent = 'CSC_COMPONENTS'
                    lay_name = identity_id
                    layer = '::'.join([lay_parent, lay_name])
                    if not rs.IsLayer(lay_parent):
                        rs.AddLayer(lay_parent)
                    if not rs.IsLayer(layer):
                        rs.AddLayer(layer, self.ComponentColor(snapshot))

                    # set layer and add component data as user strings
                    for gid in geo_ids:
                        rs.ObjectLayer(gid, layer)
                        # set component data as user string
                        rs.SetUserText(
                            gid,
                            'csc_component',
                            ComponentData[i])

                    # create tag
                    tag = Rhino.Geometry.TextEntity()
                    tag.Text = identity_id
                    tag.Plane = iplane
                    # specify height in millimeters
                    usf = Rhino.RhinoMath.UnitScale(
                        Rhino.UnitSystem.Millimeters,
                        sc.doc.ModelUnitSystem)
                    tag.TextHeight = 10.0 * usf
                    tag.Justification = (
                        Rhino.Geometry.TextJustification.MiddleCenter
                    )
                    id_tag = sc.doc.Objects.Add(tag)
                    # add tag to geometry IDs for grouping
                    if id_tag != System.Guid.Empty:
                        geo_ids.append(id_tag)

                    # set layer to tag
                    rs.ObjectLayer(id_tag, layer)

                    # create group with unique name
                    if len(geo_ids) > 1:
                        _ = sc.doc.Groups.Add(
                            group_name,
                            geo_ids)

                    baked_count += 1
                    object_count = len(geo_ids)
                    if object_count == 1:
                        self._addRemark(
                            f'Successfully baked component {comp_id}')
                    else:
                        self._addRemark(
                            f'Successfully baked component {comp_id} '
                            f'({object_count} objects)')

                except json.JSONDecodeError as e:
                    msg = (
                        f'Failed to parse component data for {comp_id}: '
                        f'{str(e)}'
                    )
                    self._addError(msg)
                    self.Component.Message = msg
                except Exception as e:
                    msg = f'Error baking component: {str(e)}'
                    self._addError(msg)
                    self.Component.Message = msg

            # Update success message
            if baked_count > 0:
                self.Component.Message = f'Baked {baked_count} component(s)'
                self._addRemark(
                    f'Successfully baked {baked_count} components')
            else:
                self.Component.Message = 'No components were baked'
                self._addWarning('No components were baked')
            # restore document context
            sc.doc = self.Component.OnPingDocument()
        else:
            self.Component.Message = 'Bake toggle is off'
            self._addRemark('Bake toggle is off - no components baked')
