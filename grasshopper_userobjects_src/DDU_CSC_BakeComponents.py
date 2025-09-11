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
    Version: 250911
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
        """Create a single mesh from geometry.mesh field (backward compat)."""
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

    def ComponentMeshes(self, json_comp: dict) -> list:
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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            self._addWarning(
                'No authentication found. Using primitive geometry only.'
            )
            return None
        return auth_core

    def fetch_cached_geometry(self, auth_core, component_id, detailed=True):
        """Fetch cached geometry from binary cache."""
        try:
            if not auth_core or not auth_core._cache:
                return None

            geometry_type = 'detailed' if detailed else 'reduced'
            (cached_meshes,
             cached_etag,
             is_from_cache) = auth_core._cache.get_geometry_binary(
                component_id, geometry_type
            )

            # Check if we got valid meshes from cache
            if is_from_cache and cached_meshes and len(cached_meshes) > 0:
                self._addRemark(
                    f'Using cached {geometry_type} geometry '
                    f'for {component_id}'
                )
                return cached_meshes
            return None
        except Exception as e:
            self._addWarning(f'Error fetching cached geometry: {str(e)}')
            return None

    def RunScript(self,
            Bake: bool,
            ComponentData: System.Collections.Generic.List[str]):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Toggle to bake components to Rhino'
        self.InputParams[1].Description = (
            'Component data from FetchComponents'
        )
        # Initialize output param descriptions
        if hasattr(self, 'OutputParams') and len(self.OutputParams) > 0:
            self.OutputParams[0].Description = 'Baking status message'

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

                    # Try to get cached geometry first
                    cached_meshes = self.fetch_cached_geometry(
                        auth_core,
                        comp_id,
                        detailed=True
                    )
                    if not cached_meshes:
                        # Fall back to reduced geometry
                        cached_meshes = self.fetch_cached_geometry(
                            auth_core,
                            comp_id,
                            detailed=False
                        )

                    # create component geometry
                    geo_ids = []
                    if cached_meshes:
                        # Use cached geometry
                        for j, mesh in enumerate(cached_meshes):
                            try:
                                # Create a copy to avoid modifying
                                # the cached mesh
                                mesh_copy = mesh.Duplicate()
                                if mesh_copy and mesh_copy.IsValid:
                                    mesh_copy.Transform(xform)
                                    geo_id = sc.doc.Objects.Add(mesh_copy)
                                    if geo_id != System.Guid.Empty:
                                        geo_ids.append(geo_id)
                                        # Add mesh index as user text
                                        rs.SetUserText(
                                            geo_id,
                                            'csc_mesh_index',
                                            str(j))
                                    else:
                                        self._addWarning(
                                            f'Failed to add mesh '
                                            f'{j} to document'
                                        )
                                else:
                                    self._addWarning(
                                        f'Invalid mesh {j} in cached geometry'
                                    )
                            except Exception as e:
                                self._addWarning(
                                    'Error processing cached '
                                    f'mesh {j}: {str(e)}'
                                )
                                continue
                    else:
                        # Fall back to primitive geometry
                        for key in sorted(json_comp['geometry'].keys()):
                            if key == 'extrusion':
                                xtr = self.ComponentExtrusion(json_comp)
                                xtr.Transform(xform)
                                geo_ids.append(sc.doc.Objects.Add(xtr))
                            elif key == 'mesh':
                                # Handle single mesh (backward compatibility)
                                mesh = self.ComponentMesh(json_comp)
                                mesh.Transform(xform)
                                geo_ids.append(sc.doc.Objects.Add(mesh))
                            elif key == 'meshes':
                                # Handle multiple meshes
                                meshes = self.ComponentMeshes(json_comp)
                                for j, mesh in enumerate(meshes):
                                    mesh.Transform(xform)
                                    geo_id = sc.doc.Objects.Add(mesh)
                                    geo_ids.append(geo_id)
                                    # Add mesh index as user text
                                    rs.SetUserText(geo_id, 'csc_mesh_index',
                                                   str(j))
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
                    mesh_count = len(geo_ids)
                    if mesh_count == 1:
                        self._addRemark(
                            f'Successfully baked component {comp_id}')
                    else:
                        self._addRemark(
                            f'Successfully baked component {comp_id} '
                            f'({mesh_count} meshes)')

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
            # restore document context
            sc.doc = ghdoc  # type: ignore[reportUnedfinedVariable] # NOQA
        else:
            self.Component.Message = 'Bake toggle is off'
            self._addRemark('Bake toggle is off - no components baked')
