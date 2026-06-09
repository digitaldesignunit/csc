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

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'DisassembleComponent'  # NOQA
ghenv.Component.NickName = 'DisassembleComponent'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Parses compose JSON ({identity, snapshot}) and outputs individual '
    'fields as Grasshopper-native types. Reconstructs geometry, bounding '
    'boxes, PCA frames, and metadata from the identity/snapshot pair.'
)


class CSC_DisassembleComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260609
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
            'Compose JSON ({identity, snapshot}) fetched from the server.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Identity ID (GUID)'
        )
        self.OutputParams[1+i].Description = (
            'Snapshot name (e.g. My Component 01)'
        )
        self.OutputParams[2+i].Description = (
            'Component type (panel, beam, slab, etc.)'
        )
        self.OutputParams[3+i].Description = (
            'Component material'
        )
        self.OutputParams[4+i].Description = (
            'Snapshot color as System.Drawing.Color'
        )
        self.OutputParams[5+i].Description = (
            'Snapshot location as Point3d (X=latitude, Y=longitude, Z=0)'
        )
        self.OutputParams[6+i].Description = (
            'Snapshot bounding box as Rhino.Geometry.BoundingBox'
        )
        self.OutputParams[7+i].Description = (
            'Snapshot PCA frame at world origin as Rhino.Geometry.Plane'
        )
        self.OutputParams[8+i].Description = (
            'Snapshot descriptors/metadata as JSON string'
        )
        self.OutputParams[9+i].Description = (
            'Rhino geometry objects (extrusions, meshes, point clouds)'
        )
        self.OutputParams[10+i].Description = (
            'Marker points as list of Point3d objects'
        )
        self.OutputParams[11+i].Description = (
            'Identity attributes as JSON string'
        )
        self.OutputParams[12+i].Description = (
            'Snapshot condition grade (0=destroyed/retired, 1=poor, '
            '2=average, 3=good)'
        )
        self.OutputParams[13+i].Description = (
            'Component manufacturing date as ISO-8601 UTC timestamp'
        )
        self.OutputParams[14+i].Description = (
            'Precision qualifier for ManufacturedAt (exact, month, year, '
            'unknown)'
        )
        self.OutputParams[15+i].Description = (
            'Component salvage source (e.g. building name, site)'
        )
        self.OutputParams[16+i].Description = (
            'Component salvage date as ISO-8601 UTC timestamp'
        )
        self.OutputParams[17+i].Description = (
            'Parent identity IDs (GUIDs) this identity was derived from'
        )

    def ComponentExtrusions(
            self,
            geometry: dict) -> list[Rhino.Geometry.Extrusion]:
        """Create extrusions from geometry.extrusions list."""
        extrusions = []
        for extr in geometry.get('extrusions', []) or []:
            pl = Rhino.Geometry.Polyline()
            pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
                   for pt in extr['profile']]
            pl.AddRange(pts)
            height = extr['height']
            cxt = Rhino.Geometry.Extrusion.Create(
                pl.ToPolylineCurve(),
                Rhino.Geometry.Plane.WorldXY,
                height,
                True)
            # move extrusion downwards half material
            # thickness to center it at the origin
            cxt.Translate(Rhino.Geometry.Vector3d(0, 0, height * -0.5))
            extrusions.append(cxt)
        return extrusions

    def ComponentMeshes(
            self,
            geometry: dict,
            snapshot_color,
            identity_id: str) -> list[Rhino.Geometry.Mesh]:
        """Create multiple meshes from geometry.meshes field."""
        meshes = []
        for idx, mesh_data in enumerate(geometry.get('meshes', []) or []):
            mesh = Rhino.Geometry.Mesh()
            vl = mesh_data['vertices']
            fl = mesh_data['faces']
            [mesh.Vertices.Add(*v) for v in vl]
            [mesh.Faces.AddFace(*f) for f in fl]
            # Try to get mesh-specific colors first
            cl = mesh_data.get('colors')
            if cl:
                [mesh.VertexColors.Add(
                    System.Drawing.Color.FromArgb(*c)) for c in cl]
            else:
                # Fallback: use snapshot color for all vertices
                try:
                    component_color = System.Drawing.Color.FromArgb(
                        255, *snapshot_color)
                    for _ in range(len(vl)):
                        mesh.VertexColors.Add(component_color)
                except (KeyError, TypeError):
                    # If even snapshot color fails, use a default gray
                    default_color = System.Drawing.Color.Gray
                    for _ in range(len(vl)):
                        mesh.VertexColors.Add(default_color)
                    self._addWarning(
                        f'Mesh {idx} in identity {identity_id} '
                        f'using default gray color')
            mesh.RebuildNormals()
            mesh.UnifyNormals()
            mesh.Compact()
            meshes.append(mesh)
        return meshes

    def ComponentPointClouds(
            self,
            geometry: dict) -> list[Rhino.Geometry.PointCloud]:
        """Create point clouds from geometry.point_clouds field."""
        clouds = []
        for pc_data in geometry.get('point_clouds', []) or []:
            cloud = Rhino.Geometry.PointCloud()
            pts = pc_data.get('points', [])
            cl = pc_data.get('colors')
            if cl and len(cl) == len(pts):
                for p, c in zip(pts, cl):
                    cloud.Add(
                        Rhino.Geometry.Point3d(p[0], p[1], p[2]),
                        System.Drawing.Color.FromArgb(*c))
            else:
                for p in pts:
                    cloud.Add(Rhino.Geometry.Point3d(p[0], p[1], p[2]))
            clouds.append(cloud)
        return clouds

    def ComponentColor(self, snapshot: dict) -> System.Drawing.Color:
        color = snapshot.get('color') or [110, 110, 110]
        return System.Drawing.Color.FromArgb(255, *color)

    def ComponentBoundingBox(
            self,
            snapshot: dict) -> Rhino.Geometry.BoundingBox:
        xtx = snapshot['bbx'][0]
        xty = snapshot['bbx'][1]
        xtz = snapshot['bbx'][2]

        # Get bbx_origin (center of bounding box in PCA space)
        bbx_origin = snapshot.get('bbx_origin', [0.0, 0.0, 0.0])

        # Create bounding box at bbx_origin in PCA space
        bbx = Rhino.Geometry.BoundingBox(
            bbx_origin[0] - xtx * 0.5,
            bbx_origin[1] - xty * 0.5,
            bbx_origin[2] - xtz * 0.5,
            bbx_origin[0] + xtx * 0.5,
            bbx_origin[1] + xty * 0.5,
            bbx_origin[2] + xtz * 0.5
        )

        # Convert bounding box to Box for transformation
        bbx = Rhino.Geometry.Box(bbx)

        # Transform from PCA space back to original component space
        try:
            pca_frame = snapshot.get('pca_frame', {})
            if pca_frame:
                # Create PCA frame plane at world origin
                pca_origin = Rhino.Geometry.Point3d(
                    *pca_frame.get('o', [0, 0, 0]))
                pca_x = Rhino.Geometry.Vector3d(
                    *pca_frame.get('x', [1, 0, 0]))
                pca_y = Rhino.Geometry.Vector3d(
                    *pca_frame.get('y', [0, 1, 0]))

                pca_plane = Rhino.Geometry.Plane(pca_origin, pca_x, pca_y)

                # Create forward transform (from PCA space to original space)
                pca_transform = (
                    Rhino.Geometry.Transform.PlaneToPlane(
                        Rhino.Geometry.Plane.WorldXY, pca_plane))

                bbx.Transform(pca_transform)

        except (KeyError, TypeError, ValueError) as e:
            # If PCA frame is missing or invalid, use bounding box as-is
            self._addWarning(f'Could not apply PCA frame transform: {str(e)}')

        return bbx

    def ComponentPCAPlane(self, snapshot: dict) -> Rhino.Geometry.Plane:
        """Get PCA plane at world origin from snapshot data."""
        try:
            pca_frame = snapshot.get('pca_frame', {})
            if pca_frame:
                pca_x = Rhino.Geometry.Vector3d(
                    *pca_frame.get('x', [1, 0, 0]))
                pca_y = Rhino.Geometry.Vector3d(
                    *pca_frame.get('y', [0, 1, 0]))
                return Rhino.Geometry.Plane(
                    Rhino.Geometry.Point3d.Origin, pca_x, pca_y)
            else:
                return Rhino.Geometry.Plane.WorldXY
        except (KeyError, TypeError, ValueError):
            return Rhino.Geometry.Plane.WorldXY

    def RunScript(self, ComponentData: Grasshopper.DataTree[str]):
        # set up output trees and results tuple
        ID = Grasshopper.DataTree[System.Object]()
        Name = Grasshopper.DataTree[System.Object]()
        Type = Grasshopper.DataTree[System.Object]()
        Material = Grasshopper.DataTree[System.Object]()
        Color = Grasshopper.DataTree[System.Object]()
        Location = Grasshopper.DataTree[System.Object]()
        BoundingBox = Grasshopper.DataTree[System.Object]()
        PCAFrame = Grasshopper.DataTree[System.Object]()
        Descriptors = Grasshopper.DataTree[System.Object]()
        PrimitiveGeometry = Grasshopper.DataTree[System.Object]()
        MarkerPoints = Grasshopper.DataTree[System.Object]()
        Attributes = Grasshopper.DataTree[System.Object]()
        Condition = Grasshopper.DataTree[System.Object]()
        ManufacturedAt = Grasshopper.DataTree[System.Object]()
        ManufacturedPrecision = Grasshopper.DataTree[System.Object]()
        SalvageSource = Grasshopper.DataTree[System.Object]()
        SalvagedAt = Grasshopper.DataTree[System.Object]()
        ParentComponent = Grasshopper.DataTree[System.Object]()
        __Results = (
            ID,
            Name,
            Type,
            Material,
            Color,
            Location,
            BoundingBox,
            PCAFrame,
            Descriptors,
            PrimitiveGeometry,
            MarkerPoints,
            Attributes,
            Condition,
            ManufacturedAt,
            ManufacturedPrecision,
            SalvageSource,
            SalvagedAt,
            ParentComponent)
        try:
            # Validate input
            if not ComponentData or ComponentData.DataCount == 0:
                msg = ('Input ComponentData failed to collect Data')
                self._addWarning(msg)
                self.Component.Message = msg
                return __Results

            self.Component.Message = 'Disassembling components...'

            # loop over all branches
            for i in range(ComponentData.BranchCount):
                ghp = ComponentData.Paths[i]
                for j, comp in enumerate(ComponentData.Branches[i]):
                    try:
                        compose = json.loads(comp)
                        identity = compose.get('identity') or {}
                        snapshot = compose.get('snapshot') or {}
                        if not identity or not snapshot:
                            self._addWarning(
                                'Compose JSON missing identity/snapshot, '
                                'skipping entry')
                            continue

                        identity_id = identity.get('_id')

                        # add directly available metadata to the
                        # respective datatrees
                        ID.Add(identity_id, ghp)
                        Name.Add(snapshot.get('name'), ghp)
                        Type.Add(identity.get('type'), ghp)
                        Material.Add(identity.get('material'), ghp)

                        # create system color from snapshot rgb values
                        color = self.ComponentColor(snapshot)
                        Color.Add(color, ghp)

                        # process location data
                        try:
                            location_data = snapshot.get('location', {}) or {}
                            if ('lat' in location_data and
                                    'lon' in location_data):
                                location_point = Rhino.Geometry.Point3d(
                                    location_data['lat'],
                                    location_data['lon'],
                                    0.0
                                )
                            else:
                                location_point = Rhino.Geometry.Point3d(
                                    0.0, 0.0, 0.0)
                        except (KeyError, TypeError):
                            location_point = Rhino.Geometry.Point3d(
                                0.0, 0.0, 0.0)
                        Location.Add(location_point, ghp)

                        # process insertion frame
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

                        # treat geometry block in a special way because
                        # it may hold multiple representations
                        geometry = snapshot.get('geometry', {}) or {}
                        for key in sorted(geometry.keys()):
                            if key == 'extrusions':
                                for xtr in self.ComponentExtrusions(geometry):
                                    # transform to iframe
                                    xtr.Transform(xform)
                                    # set user string
                                    xtr.SetUserString('csc_component', comp)
                                    # add to datatree
                                    PrimitiveGeometry.Add(xtr, ghp)
                            elif key == 'meshes':
                                # Handle multiple meshes
                                meshes = self.ComponentMeshes(
                                    geometry,
                                    snapshot.get('color'),
                                    identity_id)
                                for mesh_idx, mesh in enumerate(meshes):
                                    # transform to iframe
                                    mesh.Transform(xform)
                                    # set user string with mesh index
                                    mesh.SetUserString('csc_component', comp)
                                    mesh.SetUserString('csc_mesh_index',
                                                       str(mesh_idx))
                                    # add to datatree
                                    PrimitiveGeometry.Add(mesh, ghp)
                            elif key == 'point_clouds':
                                clouds = self.ComponentPointClouds(geometry)
                                for cloud in clouds:
                                    # transform to iframe
                                    cloud.Transform(xform)
                                    # set user string
                                    cloud.SetUserString('csc_component', comp)
                                    # add to datatree
                                    PrimitiveGeometry.Add(cloud, ghp)
                            elif key == 'marker_points':
                                # handled separately below
                                continue
                            else:
                                msg = (f'Missing implementation for geometry '
                                       f'of type \'{key}\'!')
                                self._addWarning(msg)

                        # construct boundingbox
                        bbx = self.ComponentBoundingBox(snapshot)

                        # apply iframe transform
                        bbx.Transform(xform)
                        BoundingBox.Add(bbx, ghp)

                        # get PCA plane at world origin
                        pca_plane = self.ComponentPCAPlane(snapshot)
                        # apply iframe transform to PCA plane
                        pca_plane.Transform(xform)
                        PCAFrame.Add(pca_plane, ghp)

                        # add descriptors
                        descriptors = snapshot.get('descriptors', {}) or {}
                        Descriptors.Add(json.dumps(descriptors), ghp)

                        # process marker points (now nested under geometry)
                        try:
                            marker_points_data = geometry.get(
                                'marker_points', []) or []
                            marker_points_list = []
                            for point_data in marker_points_data:
                                if (isinstance(point_data, list) and
                                        len(point_data) >= 3):
                                    marker_point = Rhino.Geometry.Point3d(
                                        point_data[0],
                                        point_data[1],
                                        point_data[2]
                                    )
                                    # apply iframe transform to marker point
                                    marker_point.Transform(xform)
                                    marker_points_list.append(marker_point)
                        except (KeyError, TypeError, IndexError):
                            # If no marker points or invalid format, add empty
                            # list
                            marker_points_list = []
                        if marker_points_list:
                            MarkerPoints.AddRange(marker_points_list, ghp)

                        # process attributes (identity-level)
                        attributes = identity.get('attributes', {}) or {}
                        Attributes.Add(json.dumps(attributes), ghp)

                        # snapshot-level state
                        if snapshot.get('condition') is not None:
                            Condition.Add(snapshot['condition'], ghp)

                        # identity-level provenance
                        if identity.get('manufactured_at') is not None:
                            ManufacturedAt.Add(
                                identity['manufactured_at'], ghp)
                        if identity.get('manufactured_precision') is not None:
                            ManufacturedPrecision.Add(
                                identity['manufactured_precision'], ghp)
                        if identity.get('salvage_source') is not None:
                            SalvageSource.Add(identity['salvage_source'], ghp)
                        if identity.get('salvaged_at') is not None:
                            SalvagedAt.Add(identity['salvaged_at'], ghp)
                        parent_identities = identity.get('parent_identities')
                        if parent_identities:
                            ParentComponent.AddRange(parent_identities, ghp)

                    except json.JSONDecodeError as e:
                        msg = f'Failed to parse compose data: {str(e)}'
                        self._addError(msg)
                    except Exception as e:
                        msg = f'Error processing component: {str(e)}'
                        self._addError(msg)

            # Update success message
            total_components = sum(
                len(branch) for branch in ComponentData.Branches
            )
            self.Component.Message = (
                f'Disassembled {total_components} component(s)'
            )
            self._addRemark(
                f'Successfully disassembled {total_components} components'
            )

            # return output trees
            return __Results

        except Exception as e:
            msg = f'Unexpected error during disassembly: {str(e)}'
            self._addError(msg)
            return __Results
