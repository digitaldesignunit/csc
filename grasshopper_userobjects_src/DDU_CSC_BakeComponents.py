#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import rhinoscriptsyntax as rs  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'BakeComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'BakeComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_BakeComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250828
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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

    def ComponentMesh(self, json_comp: dict) -> Rhino.Geometry.Mesh:
        mesh = Rhino.Geometry.Mesh()
        vl = json_comp['geometry']['mesh']['v']
        fl = json_comp['geometry']['mesh']['f']
        [mesh.Vertices.Add(*v) for v in vl]
        [mesh.Faces.AddFace(*f) for f in fl]

        # Try to get mesh-specific colors first
        try:
            cl = json_comp['geometry']['mesh']['c']
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
                    f'Mesh {json_comp["_id"]} using default gray color')

        mesh.RebuildNormals()
        mesh.UnifyNormals()
        mesh.Compact()
        return mesh

    def ComponentColor(self, json_comp: dict) -> System.Drawing.Color:
        return System.Drawing.Color.FromArgb(255, *json_comp['color'])

    def RunScript(self,
            Bake: bool,
            ComponentData: System.Collections.Generic.List[str]):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Toggle to bake components to Rhino'
        self.InputParams[1].Description = 'Component data from FetchComponents'

        # Initialize output param descriptions
        if hasattr(self, 'OutputParams') and len(self.OutputParams) > 0:
            self.OutputParams[0].Description = 'Baking status message'

        # set document
        sc.doc = Rhino.RhinoDoc.ActiveDoc

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

            for i, cd in enumerate(ComponentData):
                try:
                    # create path (not used in baking but kept for consistency)
                    _ = Grasshopper.Kernel.Data.GH_Path(i)
                    # load json component
                    json_comp = json.loads(cd)
                    # extract ID
                    comp_id = json_comp['_id']

                    # get insertion plane
                    try:
                        # try to extract insertion frame
                        iframe = json_comp['iframe']
                        iplane = Rhino.Geometry.Plane(
                            Rhino.Geometry.Point3d(*iframe['o']),
                            Rhino.Geometry.Vector3d(*iframe['x']),
                            Rhino.Geometry.Vector3d(*iframe['y']),
                        )
                    except KeyError:
                        # if there is no respective key, create world xy plane
                        iplane = Rhino.Geometry.Plane.WorldXY

                    xform = Rhino.Geometry.Transform.PlaneToPlane(
                        Rhino.Geometry.Plane.WorldXY,
                        iplane)

                    # create component geometry
                    geo_ids = []
                    for key in sorted(json_comp['geometry'].keys()):
                        if key == 'extrusion':
                            xtr = self.ComponentExtrusion(json_comp)
                            xtr.Transform(xform)
                            geo_ids.append(sc.doc.Objects.Add(xtr))
                        elif key == 'mesh':
                            mesh = self.ComponentMesh(json_comp)
                            # transform to iframe
                            mesh.Transform(xform)
                            geo_ids.append(sc.doc.Objects.Add(mesh))
                        else:
                            msg = (f'Missing implementation for geometry '
                                   f'of type \'{key}\'!')
                            self._addWarning(msg)
                            self.Component.Message = msg
                            continue

                    # add objects to document
                    # create layers if they are not present
                    lay_parent = 'CSC_COMPONENTS'
                    lay_name = comp_id
                    layer = '::'.join([lay_parent, lay_name])
                    if not rs.IsLayer(lay_parent):
                        rs.AddLayer(lay_parent)
                    if not rs.IsLayer(layer):
                        rs.AddLayer(layer, self.ComponentColor(json_comp))

                    # set layer and add component data as user strings
                    for gid in geo_ids:
                        rs.ObjectLayer(gid, layer)
                        # set component data as user string
                        rs.SetUserText(
                            gid,
                            'csc_component',
                            ComponentData[i])

                    # create group
                    if len(geo_ids) > 1:
                        _ = sc.doc.Groups.Add(
                            comp_id,
                            geo_ids)

                    baked_count += 1
                    self._addRemark(
                        f'Successfully baked component {comp_id}')

                except json.JSONDecodeError as e:
                    msg = f'Failed to parse component data: {str(e)}'
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
        else:
            self.Component.Message = 'Bake toggle is off'
            self._addRemark('Bake toggle is off - no components baked')

        # Restore original document context if needed
        # Note: ghdoc was undefined in original code
