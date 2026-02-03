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
    'Parses component data (JSON) and outputs individual fields as '
    'Grasshopper-native types. Reconstructs geometry, bounding boxes, '
    'PCA frames, and metadata from component JSON.'
)


class CSC_DisassembleComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260203
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
            'The ComponentData that was fetched from the server as JSON.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Component ID (GUID)'
        )
        self.OutputParams[1+i].Description = (
            'Component name (e.g. My Component 01)'
        )
        self.OutputParams[2+i].Description = (
            'Component type (sheet, beam, slab, etc.)'
        )
        self.OutputParams[3+i].Description = (
            'Component material'
        )
        self.OutputParams[4+i].Description = (
            'Component color as System.Drawing.Color'
        )
        self.OutputParams[5+i].Description = (
            'Component location as Point3d (X=latitude, Y=longitude, Z=0)'
        )
        self.OutputParams[6+i].Description = (
            'Component bounding box as Rhino.Geometry.BoundingBox'
        )
        self.OutputParams[7+i].Description = (
            'PCA frame at world origin as Rhino.Geometry.Plane'
        )
        self.OutputParams[8+i].Description = (
            'Component descriptors/metadata as JSON string'
        )
        self.OutputParams[9+i].Description = (
            'Rhino geometry objects (extrusion, mesh, multiple meshes, '
            'polyline)'
        )
        self.OutputParams[10+i].Description = (
            'Marker points as list of Point3d objects'
        )
        self.OutputParams[11+i].Description = (
            'Component attributes as JSON string'
        )

    def ComponentExtrusionProfile(
            self,
            json_comp: dict) -> Rhino.Geometry.Polyline:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in json_comp['geometry']['extrusion']['profile']]
        pl.AddRange(pts)
        return pl

    def ComponentExtrusion(
            self,
            json_comp: dict) -> Rhino.Geometry.Extrusion:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in json_comp['geometry']['extrusion']['profile']]
        pl.AddRange(pts)
        cxt = Rhino.Geometry.Extrusion.Create(
            pl.ToPolylineCurve(),
            Rhino.Geometry.Plane.WorldXY,
            json_comp['geometry']['extrusion']['height'],
            True)
        # move extrusion downwards half material
        # thickness to center it at the origin
        cxt.Translate(Rhino.Geometry.Vector3d(
            0, 0, json_comp['geometry']['extrusion']['height'] * -0.5))
        return cxt

    def ComponentMeshes(self, json_comp: dict) -> list[Rhino.Geometry.Mesh]:
        """Create multiple meshes from geometry.meshes field."""
        meshes = []
        for i, mesh_data in enumerate(json_comp['geometry']['meshes']):
            mesh = Rhino.Geometry.Mesh()
            vl = mesh_data['v']
            fl = mesh_data['f']
            [mesh.Vertices.Add(*v) for v in vl]
            [mesh.Faces.AddFace(*f) for f in fl]
            # Try to get mesh-specific colors first
            try:
                cl = mesh_data['c']
                [mesh.VertexColors.Add(
                    System.Drawing.Color.FromArgb(*c)) for c in cl]
            except KeyError:
                # Fallback: use component color for all vertices
                try:
                    component_color = System.Drawing.Color.FromArgb(
                        255, *json_comp['color'])
                    for _ in range(len(vl)):
                        mesh.VertexColors.Add(component_color)
                except (KeyError, TypeError):
                    # If even component color fails, use a default gray
                    default_color = System.Drawing.Color.Gray
                    for _ in range(len(vl)):
                        mesh.VertexColors.Add(default_color)
                    self._addWarning(
                        f'Mesh {i} in component {json_comp["_id"]} '
                        f'using default gray color')
            mesh.RebuildNormals()
            mesh.UnifyNormals()
            mesh.Compact()
            meshes.append(mesh)
        return meshes

    def ComponentColor(self, json_comp: dict) -> System.Drawing.Color:
        return System.Drawing.Color.FromArgb(255, *json_comp['color'])

    def ComponentBoundingBox(
            self,
            json_comp: dict) -> Rhino.Geometry.BoundingBox:
        xtx = json_comp['bbx'][0]
        xty = json_comp['bbx'][1]
        xtz = json_comp['bbx'][2]

        # Get bbx_origin (center of bounding box in PCA space)
        bbx_origin = json_comp.get('bbx_origin', [0.0, 0.0, 0.0])

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
            pca_frame = json_comp.get('pca_frame', {})
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

    def ComponentPCAPlane(self, json_comp: dict) -> Rhino.Geometry.Plane:
        """Get PCA plane at world origin from component data."""
        try:
            pca_frame = json_comp.get('pca_frame', {})
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
            Attributes)
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
                for j, comp in enumerate(ComponentData.Branches[i]):
                    try:
                        json_comp = json.loads(comp)
                        # create datatree path
                        ghp = ComponentData.Paths[i]
                        # add directly available metadata to the
                        # respective datatrees
                        ID.Add(json_comp['_id'], ghp)
                        Name.Add(json_comp['name'], ghp)
                        Type.Add(json_comp['type'], ghp)
                        Material.Add(json_comp['material'], ghp)

                        # create system color from rgb values
                        color = self.ComponentColor(json_comp)
                        Color.Add(color, ghp)

                        # process location data
                        try:
                            location_data = json_comp.get('location', {})
                            if (location_data and 'lat' in location_data and
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
                            iframe = json_comp['iframe']
                            iplane = Rhino.Geometry.Plane(
                                Rhino.Geometry.Point3d(*iframe['o']),
                                Rhino.Geometry.Vector3d(*iframe['x']),
                                Rhino.Geometry.Vector3d(*iframe['y']),
                            )
                        except KeyError:
                            iplane = Rhino.Geometry.Plane.WorldXY

                        xform = Rhino.Geometry.Transform.PlaneToPlane(
                            Rhino.Geometry.Plane.WorldXY,
                            iplane)

                        # treat geometry key in a special way because
                        # it may hold multiple geometry types
                        for key in sorted(json_comp['geometry'].keys()):
                            if key == 'extrusion':
                                xtr = self.ComponentExtrusion(json_comp)
                                # transform to iframe
                                xtr.Transform(xform)
                                # set user string
                                xtr.SetUserString('csc_component', comp)
                                # add to datatree
                                PrimitiveGeometry.Add(xtr, ghp)
                            elif key == 'meshes':
                                # Handle multiple meshes
                                meshes = self.ComponentMeshes(json_comp)
                                for i, mesh in enumerate(meshes):
                                    # transform to iframe
                                    mesh.Transform(xform)
                                    # set user string with mesh index
                                    mesh.SetUserString('csc_component', comp)
                                    mesh.SetUserString('csc_mesh_index',
                                                       str(i))
                                    # add to datatree
                                    PrimitiveGeometry.Add(mesh, ghp)
                            else:
                                msg = (f'Missing implementation for geometry '
                                       f'of type \'{key}\'!')
                                self._addWarning(msg)

                        # construct boundingbox
                        bbx = self.ComponentBoundingBox(json_comp)

                        # apply iframe transform
                        bbx.Transform(xform)
                        BoundingBox.Add(bbx, ghp)

                        # get PCA plane at world origin
                        pca_plane = self.ComponentPCAPlane(json_comp)
                        # apply iframe transform to PCA plane
                        pca_plane.Transform(xform)
                        PCAFrame.Add(pca_plane, ghp)

                        # add descriptors
                        try:
                            descriptors = json_comp.get('descriptors', {})
                            Descriptors.Add(json.dumps(descriptors), ghp)
                        except KeyError:
                            # If no descriptors, add empty dict as JSON string
                            Descriptors.Add(json.dumps({}), ghp)

                        # process marker points
                        try:
                            marker_points_data = json_comp.get(
                                'marker_points', [])
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

                        # process attributes
                        try:
                            attributes = json_comp.get('attributes', {})
                            Attributes.Add(json.dumps(attributes), ghp)
                        except KeyError:
                            # If no attributes, add empty dict as JSON string
                            Attributes.Add(json.dumps({}), ghp)

                    except json.JSONDecodeError as e:
                        msg = f'Failed to parse component data: {str(e)}'
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
