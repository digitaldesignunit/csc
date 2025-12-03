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
import rhinoscriptsyntax as rs  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'BakeComponents'  # NOQA
ghenv.Component.NickName = 'BakeComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Bakes fetched components into the Rhino document as actual geometry. '
    'Creates layers, groups, and attaches component data as user text. '
    'Prioritizes cached geometry over primitive representations.'
)


class CSC_BakeComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251203
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
            'Component data from FetchComponents'
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

                    # determine unique group name (groups must be unique)
                    # use suffix indexing: <uuid>_1, <uuid>_2, ...
                    base_group_name = comp_id
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

                    # create tag
                    tag = Rhino.Geometry.TextEntity()
                    tag.Text = comp_id
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
                    mesh_count = len(geo_ids)
                    if mesh_count == 1:
                        self._addRemark(
                            f'Successfully baked component {comp_id}')
                    else:
                        self._addRemark(
                            f'Successfully baked component {comp_id} '
                            f'({mesh_count} meshes)')

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
