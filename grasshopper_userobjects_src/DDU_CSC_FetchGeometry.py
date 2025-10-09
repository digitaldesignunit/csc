#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import math

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA
import Rhino.Geometry as rg  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchGeometry'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FetchGeometry'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_FetchGeometry(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251009

    Fetches reduced or detailed geometry from the CSC API.
    Input can be:
    - A geometry object with 'csc_component' userstring containing
      component JSON
    - A JSON string directly
    - Just the component _id

    Outputs the fetched geometry (detailed if detailed=True,
    otherwise reduced)
    Falls back to primitive geometry if no additional geometry exists.
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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_SignIn component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def extract_component_data(self, input_data):
        """
        Extract component data from various input types:
        """
        try:
            # Check if it's a geometry object with userstring
            if (hasattr(input_data, 'UserStringCount') and
                    input_data.UserStringCount > 0):
                key = 'csc_component'
                value = input_data.GetUserString(key)
                if value:
                    try:
                        # Parse the JSON string to get the _id
                        comp_data = json.loads(value)
                        return comp_data
                    except json.JSONDecodeError:
                        self._addWarning(
                            'Invalid JSON in csc_component userstring'
                        )
                        pass
            # Check if it's a string that could be JSON
            if isinstance(input_data, str):
                input_str = input_data.strip()
                # Try to parse as JSON
                try:
                    comp_data = json.loads(input_str)
                    return comp_data
                except json.JSONDecodeError:
                    # Not JSON, might be just a string
                    pass
        except Exception as e:
            self._addWarning(f'Error extracting ComponentData: {str(e)}')
        return None

    def extract_component_id(self, comp_data):
        """
        Extract component data from various input types:
        - Geometry object with 'csc_component' userstring
        - JSON string
        - Direct component ID
        """
        try:
            # Check if it's a string that could be JSON
            if isinstance(comp_data, str):
                input_str = comp_data.strip()
                auth_core = self.get_auth_core_from_sticky()
                # Check if it's a valid UUID first
                if auth_core.validate_uuid(input_str):
                    return input_str
            # Parse the JSON string to get the _id
            elif '_id' in comp_data:
                return comp_data['_id']
        except Exception as e:
            self._addWarning(f'Error extracting component ID: {str(e)}')
        return None

    def fetch_geometry_from_api(self, auth_core, component_id, detailed=False):
        """
        Fetch geometry from the API with caching support.
        Returns the geometry data or None if failed.
        """
        try:
            geometry_type = 'detailed' if detailed else 'reduced'

            # Check binary cache first
            if auth_core._cache:
                (cached_meshes,
                 cached_etag,
                 is_from_binary_cache) = auth_core._cache.get_geometry_binary(
                    component_id, geometry_type
                )
                if is_from_binary_cache and cached_meshes:
                    self._addRemark(
                        f'Fetched {geometry_type} geometry for '
                        f'{component_id} (from binary cache)'
                    )
                    return {
                        'type': geometry_type,
                        'data': cached_meshes,
                        'format': 'rhino_meshes'
                    }

            # Use cached geometry request
            response = auth_core.cached_get_geometry(
                component_id, geometry_type
            )

            if response.status_code == 200:
                # Check if this was from cache
                is_from_cache = hasattr(response, '_data')
                cache_status = ' (from cache)' if is_from_cache else ''

                self._addRemark(
                    f'Fetched {geometry_type} geometry for '
                    f'{component_id}{cache_status}'
                )

                return {
                    'type': geometry_type,
                    'data': response.text,
                    'format': 'obj'
                }
            elif response.status_code == 404:
                # Geometry not available, try fallback
                if detailed:
                    # Detailed geometry not available, fall back to reduced
                    self._addRemark(
                        f'Detailed geometry not available for {component_id}, '
                        f'trying reduced...')
                    return self.fetch_geometry_from_api(
                        auth_core,
                        component_id,
                        detailed=False
                    )
                else:
                    # Reduced geometry not available, fall back to primitive
                    self._addRemark(
                        f'Reduced geometry not available '
                        f'for {component_id}, using primitive...'
                    )
                    return None
            else:
                self._addWarning(
                    f'Failed to fetch {geometry_type} '
                    f'geometry: {response.status_code}')
                return None

        except Exception as e:
            self._addError(f'Error fetching geometry from API: {str(e)}')
            return None

    def convert_meshes_to_obj(self, meshes):
        """
        Convert Rhino.Geometry.Mesh objects to OBJ file content.
        This is used for compatibility when returning cached binary data
        as OBJ text.
        """
        try:
            if not meshes:
                return "# No geometry data available"

            obj_lines = []
            vertex_offset = 0

            for mesh_idx, mesh in enumerate(meshes):
                # Add object declaration
                obj_lines.append(f"o object_{mesh_idx}")

                # Add vertices
                for i in range(mesh.Vertices.Count):
                    vertex = mesh.Vertices[i]
                    obj_lines.append(f"v {vertex.X} {vertex.Y} {vertex.Z}")
                # Add vertex colors if available
                if mesh.VertexColors.Count > 0:
                    for i in range(mesh.Vertices.Count):
                        if i < mesh.VertexColors.Count:
                            color = mesh.VertexColors[i]
                            obj_lines.append(
                                f"v {mesh.Vertices[i].X} "
                                f"{mesh.Vertices[i].Y} "
                                f"{mesh.Vertices[i].Z} "
                                f"{color.R} {color.G} {color.B}"
                            )
                        else:
                            vertex = mesh.Vertices[i]
                            obj_lines.append(
                                f"v {vertex.X} {vertex.Y} {vertex.Z}"
                            )
                # Add faces (adjust indices for OBJ format)
                for i in range(mesh.Faces.Count):
                    face = mesh.Faces[i]
                    if face.IsTriangle:
                        obj_lines.append(
                            f"f {face.A + vertex_offset + 1} "
                            f"{face.B + vertex_offset + 1} "
                            f"{face.C + vertex_offset + 1}"
                        )
                    elif face.IsQuad:
                        obj_lines.append(
                            f"f {face.A + vertex_offset + 1} "
                            f"{face.B + vertex_offset + 1} "
                            f"{face.C + vertex_offset + 1} "
                            f"{face.D + vertex_offset + 1}"
                        )
                vertex_offset += mesh.Vertices.Count
            return "\n".join(obj_lines)
        except Exception as e:
            return f"# Error converting meshes to OBJ: {str(e)}"

    def convert_obj_to_meshes(self, obj_content):
        """
        Convert OBJ file content to list of Rhino.Geometry.Mesh objects.
        Optimized version with improved performance for large files.
        Supports multiple objects (o object_0, o object_1, etc.) and
        v X Y Z R G B format with RGB integer colors.
        Returns list of mesh objects or empty list if conversion fails.
        """
        try:
            if not obj_content or not obj_content.strip():
                return []
            # Pre-allocate data structures for better performance
            meshes = []
            global_vertices = []
            global_normals = []
            global_vertex_colors = []

            # Current mesh data
            current_mesh_data = {
                'vertices': [],
                'faces': [],
                'normals': [],
                'vertex_colors': [],
                'name': 'default'
            }

            # Parse lines more efficiently
            lines = obj_content.splitlines()

            # Pre-process lines to avoid repeated string operations
            processed_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if parts:
                        processed_lines.append(parts)

            # Process lines without excessive logging
            for i, parts in enumerate(processed_lines):

                if parts[0] == 'o':  # object declaration
                    # Save previous mesh if it exists
                    if (current_mesh_data['vertices'] and
                            current_mesh_data['faces']):
                        mesh = self._create_mesh_from_data(current_mesh_data)
                        if mesh:
                            meshes.append(mesh)

                    # Start new mesh
                    current_mesh_data = {
                        'vertices': [],
                        'faces': [],
                        'normals': [],
                        'vertex_colors': [],
                        'name': (parts[1] if len(parts) > 1
                                 else f'object_{len(meshes)}')
                    }

                elif parts[0] == 'v':  # vertex
                    if len(parts) >= 4:
                        # Use tuple instead of Point3d for better performance
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        vertex = (x, y, z)
                        global_vertices.append(vertex)
                        current_mesh_data['vertices'].append(vertex)

                        # Check for vertex colors in v X Y Z R G B format
                        if len(parts) >= 7:
                            # Extract RGB integer values
                            r = int(parts[4])
                            g = int(parts[5])
                            b = int(parts[6])
                            color = (r, g, b)
                            global_vertex_colors.append(color)
                            current_mesh_data['vertex_colors'].append(color)
                        else:
                            # No color data, use default white
                            color = (255, 255, 255)
                            global_vertex_colors.append(color)
                            current_mesh_data['vertex_colors'].append(color)

                elif parts[0] == 'vn':  # vertex normal
                    if len(parts) >= 4:
                        nx = float(parts[1])
                        ny = float(parts[2])
                        nz = float(parts[3])
                        normal = (nx, ny, nz)
                        global_normals.append(normal)
                        current_mesh_data['normals'].append(normal)

                elif parts[0] == 'f':  # face
                    if len(parts) >= 4:
                        # Optimized face processing
                        face_vertices = []
                        for i in range(1, len(parts)):
                            # Handle different OBJ face formats
                            # (v, v/vt, v//vn, v/vt/vn)
                            vertex_part = parts[i].split('/')[0]
                            if vertex_part:
                                # OBJ is 1-indexed, convert to 0-indexed
                                vertex_index = int(vertex_part) - 1
                                if 0 <= vertex_index < len(global_vertices):
                                    # Use direct local index calculation
                                    vertices_len = len(
                                        current_mesh_data['vertices']
                                    )
                                    local_index = (
                                        vertex_index -
                                        (len(global_vertices) - vertices_len)
                                    )
                                    if (0 <= local_index < len(
                                            current_mesh_data['vertices'])):
                                        face_vertices.append(local_index)
                        if len(face_vertices) >= 3:
                            current_mesh_data['faces'].append(face_vertices)

            # Handle the last mesh
            if (current_mesh_data['vertices'] and
                    current_mesh_data['faces']):
                mesh = self._create_mesh_from_data(current_mesh_data)
                if mesh:
                    meshes.append(mesh)

            # If no objects were found, treat as single mesh
            # (backward compatibility)
            if not meshes and global_vertices:
                # Collect all faces from the global context
                global_faces = []
                for line in lines:
                    line = line.strip()
                    if (not line or line.startswith('#') or
                            line.startswith('o')):
                        continue
                    parts = line.split()
                    if not parts or parts[0] != 'f':
                        continue
                    if len(parts) >= 4:
                        face_vertices = []
                        for i in range(1, len(parts)):
                            vertex_part = parts[i].split('/')[0]
                            if vertex_part:
                                vertex_index = int(vertex_part) - 1
                                if 0 <= vertex_index < len(global_vertices):
                                    face_vertices.append(vertex_index)
                        if len(face_vertices) >= 3:
                            global_faces.append(face_vertices)

                if global_faces:
                    single_mesh = rg.Mesh()
                    self._finalize_mesh(single_mesh, global_vertices,
                                        global_faces, global_normals,
                                        global_vertex_colors)
                    meshes.append(single_mesh)

            if not meshes:
                return []

            return meshes

        except Exception as e:
            self._addError(f'Error converting OBJ to meshes: {str(e)}')
            return []

    def _finalize_mesh(self, mesh, vertices, faces, normals, vertex_colors):
        """
        Helper method to finalize a mesh with vertices, faces, normals,
        and colors.
        """
        try:
            # Add vertices
            for vertex in vertices:
                mesh.Vertices.Add(vertex)

            # Add faces
            for face in faces:
                if len(face) == 3:
                    mesh.Faces.AddFace(face[0], face[1], face[2])
                elif len(face) == 4:
                    mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
                else:
                    # Triangulate polygon faces
                    for i in range(1, len(face) - 1):
                        mesh.Faces.AddFace(face[0], face[i], face[i + 1])

            # Add normals if available
            if normals and len(normals) == len(vertices):
                mesh.Normals.Clear()
                for normal in normals:
                    mesh.Normals.Add(normal)
                mesh.Normals.ComputeNormals()
            else:
                mesh.Normals.ComputeNormals()

            # Add vertex colors if available
            if vertex_colors and len(vertex_colors) == len(vertices):
                for color in vertex_colors:
                    r, g, b = color
                    mesh.VertexColors.Add(r, g, b)

            # rotate around x-axis to normalize for Rhino
            mesh.Rotate(
                (math.pi / 2),
                rg.Plane.WorldXY.XAxis,
                rg.Point3d(0, 0, 0)
            )
            # Compute mesh properties
            mesh.Compact()

        except Exception as e:
            self._addError(f'Error finalizing mesh: {str(e)}')

    def _create_mesh_from_data(self, mesh_data):
        """
        Optimized method to create a Rhino mesh from pre-processed data.
        Uses bulk operations for better performance.
        """
        try:
            vertices = mesh_data['vertices']
            faces = mesh_data['faces']
            normals = mesh_data['normals']
            vertex_colors = mesh_data['vertex_colors']

            if not vertices or not faces:
                return None

            # Create mesh
            mesh = rg.Mesh()

            # Convert tuples to Point3d objects in bulk
            point3d_vertices = []
            for x, y, z in vertices:
                point3d_vertices.append(rg.Point3d(x, y, z))

            # Add vertices in bulk
            mesh.Vertices.AddVertices(point3d_vertices)

            # Add faces efficiently
            for face in faces:
                if len(face) == 3:
                    mesh.Faces.AddFace(face[0], face[1], face[2])
                elif len(face) == 4:
                    mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
                else:
                    # Triangulate polygon faces
                    for i in range(1, len(face) - 1):
                        mesh.Faces.AddFace(face[0], face[i], face[i + 1])

            # Add normals if available
            if normals and len(normals) == len(vertices):
                mesh.Normals.Clear()
                for nx, ny, nz in normals:
                    mesh.Normals.Add(rg.Vector3d(nx, ny, nz))
                mesh.Normals.ComputeNormals()
            else:
                mesh.Normals.ComputeNormals()

            # Add vertex colors if available
            if vertex_colors and len(vertex_colors) == len(vertices):
                for r, g, b in vertex_colors:
                    mesh.VertexColors.Add(r, g, b)

            # Apply coordinate system transformation
            mesh.Rotate(
                (math.pi / 2),
                rg.Plane.WorldXY.XAxis,
                rg.Point3d(0, 0, 0)
            )

            # Set mesh name
            mesh.UserDictionary.Set('Name', mesh_data['name'])

            # Compute mesh properties
            mesh.Compact()

            return mesh

        except Exception as e:
            self._addError(f'Error creating mesh from data: {str(e)}')
            return None

    def fetch_primitive_geometry(self, auth_core, component_id):
        """
        Fetch the primitive geometry stored in the component JSON.
        Returns the geometry data or None if failed.
        """
        try:
            response = auth_core.authorized_get(
                f'/components/{component_id}/geometry'
            )
            if response.status_code == 200:
                comp_data = response.json()
                if 'geometry' in comp_data:
                    return {
                        'type': 'primitive',
                        'data': comp_data['geometry'],
                        'format': 'json'
                    }
                else:
                    self._addWarning(
                        f'No geometry data found in component {component_id}'
                    )
                    return None
            else:
                self._addWarning(
                    f'Failed to fetch component '
                    f'geometry: {response.status_code}'
                )
                return None

        except Exception as e:
            self._addError(f'Error fetching primitive geometry: {str(e)}')
            return None

    def primitive_mesh(self, mesh_data: dict) -> Rhino.Geometry.Mesh:
        """Create a single mesh from primitive mesh data."""
        # Handle mesh with vertices and faces
        if 'v' in mesh_data and 'f' in mesh_data:
            vertices = mesh_data['v']
            faces = mesh_data['f']
            if not vertices or not faces:
                return None
            mesh = rg.Mesh()
            # Add vertices
            for vertex in vertices:
                if len(vertex) >= 3:
                    x, y, z = (
                        float(vertex[0]),
                        float(vertex[1]),
                        float(vertex[2])
                    )
                    mesh.Vertices.Add(rg.Point3d(x, y, z))
            # Add faces
            for face in faces:
                if len(face) >= 3:
                    if len(face) == 3:
                        mesh.Faces.AddFace(face[0], face[1], face[2])
                    elif len(face) == 4:
                        mesh.Faces.AddFace(face[0], face[1], face[2], face[3])
            # Add colors if available
            if 'c' in mesh_data and len(mesh_data['c']) == len(vertices):
                colors = mesh_data['c']
                for i, color in enumerate(colors):
                    if i < mesh.Vertices.Count and len(color) >= 3:
                        r, g, b = int(color[0]), int(color[1]), int(color[2])
                        mesh.VertexColors.Add(r, g, b)

            mesh.Normals.ComputeNormals()
            mesh.Compact()
            return mesh

    def primitive_meshes(self, meshes_data: list) -> list:
        """Create multiple meshes from primitive meshes data."""
        meshes = []
        for i, mesh_data in enumerate(meshes_data):
            mesh = self.primitive_mesh(mesh_data)
            if mesh is not None:
                meshes.append(mesh)
        return meshes

    def primitive_extrusion(
        self,
        extrusion_data: dict
    ) -> Rhino.Geometry.Extrusion:
        pl = Rhino.Geometry.Polyline()
        pts = [Rhino.Geometry.Point3d(pt[0], pt[1], 0.0)
               for pt in extrusion_data['profile']]
        pl.AddRange(pts)
        cxt = Rhino.Geometry.Extrusion.Create(
            pl.ToPolylineCurve(),
            Rhino.Geometry.Plane.WorldXY,
            extrusion_data['height'],
            True)
        # move extrusion downwards half material
        # thickness to center it at the origin
        cxt.Translate(Rhino.Geometry.Vector3d(
            0, 0, extrusion_data['height'] * -0.5))
        return cxt

    def construct_primitive_geometry(self, geometry_data):
        """
        Construct primitive geometry data.
        Handles different primitive geometry types from component JSON.
        Returns list of geometry objects.
        """
        try:
            if not isinstance(geometry_data, dict):
                self._addWarning('Primitive geometry data is not a dictionary')
                return []

            geometries = []

            # Check for single mesh data (backward compatibility)
            if 'mesh' in geometry_data:
                mesh_data = geometry_data['mesh']
                mesh_geometry = self.primitive_mesh(mesh_data)
                if mesh_geometry is not None:
                    geometries.append(mesh_geometry)

            # Check for multiple meshes data
            elif 'meshes' in geometry_data:
                meshes_data = geometry_data['meshes']
                if isinstance(meshes_data, list):
                    mesh_geometries = self.primitive_meshes(meshes_data)
                    geometries.extend(mesh_geometries)
                else:
                    self._addWarning('Meshes data is not a list')
                    return []

            # Check for extrusion data
            elif 'extrusion' in geometry_data:
                extrusion_data = geometry_data['extrusion']
                extrusion_geometry = self.primitive_extrusion(extrusion_data)
                if extrusion_geometry is not None:
                    geometries.append(extrusion_geometry)

            # Check for other primitive types
            else:
                self._addWarning('Unsupported primitive geometry type')
                return []

            return geometries

        except Exception as e:
            self._addError(f'Error constructing primitive geometry: {str(e)}')
            return []

    def iframe_to_xform(self, iframe) -> Rhino.Geometry.Transform:
        """
        Converts a component iframe to a Rhino 4x4 transformation matrix.
        """
        # Extract origin and vectors
        origin = iframe['o']
        x_vec = iframe['x']
        y_vec = iframe['y']
        z_vec = iframe['z']
        # Create 4x4 transformation matrix
        transform_matrix = [
            [x_vec[0], y_vec[0], z_vec[0], origin[0]],
            [x_vec[1], y_vec[1], z_vec[1], origin[1]],
            [x_vec[2], y_vec[2], z_vec[2], origin[2]],
            [0.0, 0.0, 0.0, 1.0]
        ]
        # Convert to Rhino Transform
        XForm = Rhino.Geometry.Transform.Identity
        XForm.M00 = transform_matrix[0][0]
        XForm.M01 = transform_matrix[0][1]
        XForm.M02 = transform_matrix[0][2]
        XForm.M03 = transform_matrix[0][3]
        XForm.M10 = transform_matrix[1][0]
        XForm.M11 = transform_matrix[1][1]
        XForm.M12 = transform_matrix[1][2]
        XForm.M13 = transform_matrix[1][3]
        XForm.M20 = transform_matrix[2][0]
        XForm.M21 = transform_matrix[2][1]
        XForm.M22 = transform_matrix[2][2]
        XForm.M23 = transform_matrix[2][3]
        return XForm

    def fetch_component_data(self, auth_core, component_id):
        """
        Fetch the full component data from the API.
        Returns the component data or None if failed.
        """
        try:
            response = auth_core.authorized_get(
                f'/components/{component_id}'
            )
            if response.status_code == 200:
                return response.json()
            else:
                self._addWarning(
                    f'Failed to fetch component data: '
                    f'{response.status_code}'
                )
                return None
        except Exception as e:
            self._addError(f'Error fetching component data: {str(e)}')
            return None

    def set_component_data_as_user_string(
            self,
            geometry_object,
            component_data
    ):
        """
        Set the component data as a user string to the geometry object.
        """
        try:
            if hasattr(geometry_object, 'SetUserString'):
                # Convert component data to JSON string
                component_json = json.dumps(component_data)
                geometry_object.SetUserString('csc_component', component_json)
                self._addRemark(
                    'Component data set as user string to geometry'
                )
            else:
                self._addWarning(
                    'Geometry object does not support user strings'
                )
        except Exception as e:
            self._addWarning(f'Failed to set user string: {str(e)}')

    def RunScript(self, Input, Detailed: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Input can be:\n'
            '- A geometry object with \'csc_component\' userstring\n'
            '- A JSON string containing component data\n'
            '- Just the component _id'
        )
        self.InputParams[1].Description = (
            'True for detailed geometry, False for reduced'
        )
        self.OutputParams[0].Description = (
            'Fetched geometry as Rhino.Geometry.GeometryBase objects '
            '(can be multiple meshes)'
        )
        self.OutputParams[1].Description = (
            'Geometry type: detailed, reduced, or primitive'
        )
        self.OutputParams[2].Description = 'Component ID that was processed'

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_SignIn '
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

        # Set up output trees and results tuple
        GeometryData = Grasshopper.DataTree[System.Object]()
        GeometryType = Grasshopper.DataTree[str]()
        ComponentID = Grasshopper.DataTree[str]()
        __Results = (GeometryData, GeometryType, ComponentID)

        try:
            self.Component.Message = 'Processing input...'

            # Extract component ID from input
            # (could be from userstring, JSON, or direct ID)
            component_id = None
            component_data = None
            # First try to extract component data from input
            component_data = self.extract_component_data(Input)
            if component_data:
                component_id = self.extract_component_id(component_data)
            else:
                # If no component data, try to extract just the ID
                component_id = self.extract_component_id(Input)

            if not component_id:
                msg = 'Could not extract component ID from input.'
                self._addError(msg)
                self.Component.Message = msg
                return

            # Validate component ID
            if not auth_core.validate_uuid(component_id):
                msg = f'Component ID <{component_id}> is not a valid UUID!'
                self._addError(msg)
                self.Component.Message = msg
                return

            # Ensure we have full component data (fetch if we only had an ID)
            no_prev_transformation = False
            if not component_data:
                self._addRemark(
                    f'Fetching full component data for {component_id}...')
                no_prev_transformation = True
                component_data = self.fetch_component_data(
                    auth_core,
                    component_id
                )
                if not component_data:
                    msg = f'Failed to fetch component data for {component_id}'
                    self._addError(msg)
                    self.Component.Message = msg
                    return __Results

            self.Component.Message = (
                f'Fetching geometry for component {component_id} '
                f'(with cache)...'
            )

            # Try to fetch geometry from API first
            geometry_data = self.fetch_geometry_from_api(
                auth_core,
                component_id,
                Detailed)

            # If API geometry not available, fall back to primitive
            if not geometry_data:
                self._addRemark(
                    f'Falling back to primitive geometry for {component_id}'
                )
                geometry_data = self.fetch_primitive_geometry(
                    auth_core,
                    component_id
                )

                if not geometry_data:
                    msg = f'No geometry available for component {component_id}'
                    self._addError(msg)
                    self.Component.Message = msg
                    return __Results

            # Create datatree paths
            ghp = Grasshopper.Kernel.Data.GH_Path(0)

            # Process geometry based on format
            geometry_objects = []
            if geometry_data['format'] == 'rhino_meshes':
                # Use cached Rhino meshes directly
                geometry_objects = geometry_data['data']
                if not geometry_objects:
                    self._addError('No cached meshes found')
                    return __Results
            elif geometry_data['format'] == 'obj':
                # Convert OBJ to meshes (can be multiple)
                geometry_objects = self.convert_obj_to_meshes(
                    geometry_data['data']
                )
                if not geometry_objects:
                    self._addError('Failed to convert OBJ to meshes')
                    return __Results
            else:
                # Construct primitive geometry (can be multiple)
                geometry_objects = self.construct_primitive_geometry(
                    geometry_data['data']
                )
                if not geometry_objects:
                    self._addError('Failed to construct primitive geometry')
                    return __Results

            # Apply transformation if iframe data is available
            if (not no_prev_transformation and component_data and
                    'iframe' in component_data):
                xform = self.iframe_to_xform(component_data['iframe'])
                for geometry_object in geometry_objects:
                    geometry_object.Transform(xform)
            else:
                self._addWarning(
                    'No previous transformation applied, '
                    'input was only ComponentID!'
                )

            # Set component data as user string on all geometry objects
            for i, geometry_object in enumerate(geometry_objects):
                self.set_component_data_as_user_string(
                    geometry_object,
                    component_data
                )
                # Add mesh index for all geometry objects (0 for single mesh)
                if hasattr(geometry_object, 'SetUserString'):
                    geometry_object.SetUserString('csc_mesh_index', str(i))

            # Add all geometry objects to outputs
            for geometry_object in geometry_objects:
                GeometryData.Add(geometry_object, ghp)
                GeometryType.Add(geometry_data['type'], ghp)
                ComponentID.Add(component_id, ghp)

            # Update success message
            mesh_count = len(geometry_objects)
            if mesh_count == 1:
                self.Component.Message = (
                    f'Successfully fetched {geometry_data["type"]} '
                    f'geometry for {component_id}'
                )
                self._addRemark(
                    f'Fetched {geometry_data["type"]} geometry '
                    f'for component {component_id}'
                )
            else:
                self.Component.Message = (
                    f'Successfully fetched {geometry_data["type"]} '
                    f'geometry ({mesh_count} meshes) for {component_id}'
                )
                self._addRemark(
                    f'Fetched {geometry_data["type"]} geometry '
                    f'({mesh_count} meshes) for component {component_id}'
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
