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
import uuid  # NOQA
import os  # NOQA
import platform  # NOQA
from datetime import datetime  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA
from scipy.spatial import ConvexHull  # NOQA
from sklearn.decomposition import PCA  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateComponent'  # NOQA
ghenv.Component.NickName = 'CreateComponent'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Creates a complete component JSON string from input geometry. '
    'Computes PCA orientation, handles mesh reduction, saves geometry '
    'files locally, and builds component data according to the schema.'
)


class CSC_CreateComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260421
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
            'If set to True, clears all stored locally '
            'saved geometry files for component creation '
            '(this does NOT affect the regular cache!)'
        )
        self.InputParams[1].Description = (
            'Component ID (must be a valid UUID)'
        )
        self.InputParams[2].Description = (
            'Component Name (e.g. My Beam 01)'
        )
        self.InputParams[3].Description = (
            'Component type (e.g., "sheet", "rubble")'
        )
        self.InputParams[4].Description = (
            'Material type (e.g., "steel", "concrete", "wood")'
        )
        self.InputParams[5].Description = (
            'Dataset that this component belongs to '
            '(i.e. my_rubble_dataset)'
        )
        self.InputParams[6].Description = (
            'Complexity level '
            '(0=simple, 1=normal, 2=complex, 3=very complex)'
        )
        self.InputParams[7].Description = (
            'Fragment status (True for fragments, False for complete)'
        )
        self.InputParams[8].Description = (
            'Assembly status (True for assemblies, False for individual)'
        )
        self.InputParams[9].Description = (
            'Component color (System.Drawing.Color)'
        )
        self.InputParams[10].Description = (
            'Location as Vector3d (X=latitude, Y=longitude, Z ignored)'
        )
        self.InputParams[11].Description = (
            'Rhino geometry object(s) - single object or list of objects. '
            'For single: Mesh or Extrusion for sheets, Mesh for rubble. '
            'For multiple: all must be Meshes.'
        )
        self.InputParams[12].Description = (
            'Marker points as list of Point3d objects for component '
            'identification and positioning'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Component data as JSON string adhering to ComponentModel '
            'structure. Contains geometry, PCA frame, bounding box, '
            'and metadata.'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            self._addWarning('No authentication found. '
                             'Using hardcoded schema.')
            return None
        return auth_core

    def get_component_schema(self):
        """Get component schema from cache or fallback to hardcoded schema."""
        # Try to get schema from AuthCore cache first
        auth_core = self.get_auth_core_from_sticky()
        if auth_core and hasattr(auth_core, 'get_component_schema'):
            try:
                schema = auth_core.get_component_schema()
                if schema:
                    self._addRemark('Using cached component schema')
                    return schema
                else:
                    self._addWarning('Failed to get cached schema, '
                                     'using hardcoded schema')
            except Exception as e:
                self._addWarning(f'Error fetching cached schema: {str(e)}, '
                                 'using hardcoded schema')

        # Fallback to hardcoded schema
        self._addRemark('Using hardcoded component schema')
        return self.get_hardcoded_schema()

    def get_hardcoded_schema(self):
        """Get hardcoded component schema as fallback."""
        return {
            'type': 'object',
            'properties': {
                '_id': {'type': 'string', 'format': 'uuid'},
                'name': {'type': 'string'},
                'type': {'type': 'string'},
                'material': {'type': 'string'},
                'dataset': {'type': 'string'},
                'created': {'type': 'string', 'format': 'date-time'},
                'lastmodified': {'type': 'string', 'format': 'date-time'},
                'complexity': {'type': 'integer', 'minimum': 0, 'maximum': 3},
                'fragment': {'type': 'boolean'},
                'assembly': {'type': 'boolean'},
                'geometry': {
                    'type': 'object',
                    'properties': {
                        'meshes': {
                            'type': 'array',
                            'description': 'Array of mesh geometries',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'v': {'type': 'array',
                                          'items': {
                                            'type': 'array',
                                            'items': {'type': 'number'}}},
                                    'f': {'type': 'array',
                                          'items': {
                                            'type': 'array',
                                            'items': {'type': 'integer'}}},
                                    'c': {'type': 'array',
                                          'items': {
                                            'type': 'array',
                                            'items': {'type': 'integer'}}}
                                }
                            }
                        },
                        'extrusion': {
                            'type': 'object',
                            'description': 'Extrusion geometry',
                            'properties': {
                                'profile': {'type': 'array',
                                            'items': {
                                                'type': 'array',
                                                'items': {'type': 'number'}}},
                                'height': {'type': 'number'}
                            }
                        }
                    }
                },
                'color': {'type': 'array', 'items': {'type': 'integer'}},
                'bbx': {'type': 'array', 'items': {'type': 'number'}},
                'bbx_origin': {'type': 'array', 'items': {'type': 'number'}},
                'location': {'type': 'object'},
                'descriptors': {'type': 'object'},
                'processes': {'type': 'object'},
                'iframe': {'type': 'object'},
                'pca_frame': {'type': 'object'},
                'reserved': {'type': 'string'},
                'attributes': {'type': 'object'},
                'marker_points': {
                    'type': 'array', 'items': {
                        'type': 'array', 'items': {'type': 'number'}}},
                'validated': {'type': 'boolean'},
                'etag': {'type': 'string'}
            },
            'required': ['type', 'material', 'dataset', 'created',
                         'lastmodified', 'complexity', 'fragment', 'assembly',
                         'geometry', 'bbx', 'bbx_origin', 'iframe',
                         'pca_frame', 'reserved', 'validated']
        }

    def validate_component_data(self, component_data, schema):
        """Validate component data against schema."""
        try:
            # Basic validation - check required fields
            required_fields = schema.get('required', [])
            missing_fields = []

            for field in required_fields:
                if field not in component_data:
                    missing_fields.append(field)

            if missing_fields:
                self._addWarning(f'Missing required fields: '
                                 f'{", ".join(missing_fields)}')
                return False

            # Type validation for key fields
            if not isinstance(component_data.get('complexity'), int):
                self._addWarning('Complexity must be an integer')
                return False

            if not isinstance(component_data.get('fragment'), bool):
                self._addWarning('Fragment must be a boolean')
                return False

            if not isinstance(component_data.get('assembly'), bool):
                self._addWarning('Assembly must be a boolean')
                return False

            # Validate optional color field
            color = component_data.get('color', [])
            if color and (not isinstance(color, list) or len(color) != 3):
                self._addWarning(
                    'Color must be a list of 3 integers [R, G, B]')
                return False

            # Validate required frame fields
            if not isinstance(component_data.get('iframe'), dict):
                self._addWarning('iframe must be a dictionary with frame data')
                return False

            if not isinstance(component_data.get('pca_frame'), dict):
                self._addWarning('pca_frame must be a dictionary with '
                                 'frame data')
                return False

            if not isinstance(component_data.get('reserved'), str):
                self._addWarning('reserved must be a string (UUID or empty)')
                return False

            return True

        except Exception as e:
            self._addWarning(f'Validation error: {str(e)}')
            return False

    def build_component_data_from_schema(
            self,
            schema,
            ComponentID: str,
            Name: str,
            Type: str,
            Material: str,
            Dataset: str,
            Complexity: int,
            Fragment: bool,
            Assembly: bool,
            Color,
            dimensions,
            location_data,
            principal_components):
        """Build component data dictionary using the actual schema."""
        current_time = datetime.utcnow().isoformat() + 'Z'

        # Get all properties from the schema
        properties = schema.get('properties', {})
        component_data = {}

        # Build component data based on schema properties
        for field_name, field_schema in properties.items():
            if field_name == '_id':
                component_data[field_name] = ComponentID
            elif field_name == 'name':
                component_data[field_name] = Name if Name else (
                    f'{str(Type).capitalize()} Component made '
                    f'from {str(Material).capitalize()}'
                )
            elif field_name == 'type':
                component_data[field_name] = Type
            elif field_name == 'material':
                component_data[field_name] = Material
            elif field_name == 'dataset':
                component_data[field_name] = Dataset
            elif field_name == 'created':
                component_data[field_name] = current_time
            elif field_name == 'lastmodified':
                component_data[field_name] = current_time
            elif field_name == 'complexity':
                component_data[field_name] = int(Complexity)
            elif field_name == 'fragment':
                component_data[field_name] = bool(Fragment)
            elif field_name == 'assembly':
                component_data[field_name] = bool(Assembly)
            elif field_name == 'geometry':
                component_data[field_name] = {}  # Will be filled later
            elif field_name == 'color':
                component_data[field_name] = [Color.R, Color.G, Color.B]
            elif field_name == 'bbx':
                component_data[field_name] = dimensions
            elif field_name == 'bbx_origin':
                # This will be set later after PCA computation
                component_data[field_name] = [0.0, 0.0, 0.0]  # Placeholder
            elif field_name == 'location':
                component_data[field_name] = location_data
            elif field_name == 'descriptors':
                component_data[field_name] = {}
            elif field_name == 'processes':
                component_data[field_name] = {}
            elif field_name == 'iframe':
                component_data[field_name] = {
                    'o': [0.0, 0.0, 0.0],
                    'x': [1.0, 0.0, 0.0],
                    'y': [0.0, 1.0, 0.0],
                    'z': [0.0, 0.0, 1.0]
                }
            elif field_name == 'pca_frame':
                component_data[field_name] = {
                    'o': [0.0, 0.0, 0.0],
                    'x': principal_components[0].tolist(),
                    'y': principal_components[1].tolist(),
                    'z': principal_components[2].tolist()
                }
            elif field_name == 'reserved':
                component_data[field_name] = ''
            elif field_name == 'attributes':
                component_data[field_name] = {}
            elif field_name == 'marker_points':
                component_data[field_name] = []
            elif field_name == 'validated':
                component_data[field_name] = False
            elif field_name == 'etag':
                component_data[field_name] = ''
            else:
                # Handle any other fields from the
                # schema with appropriate defaults
                field_type = field_schema.get('type', 'string')
                if field_type == 'string':
                    component_data[field_name] = ''
                elif field_type == 'integer':
                    component_data[field_name] = 0
                elif field_type == 'boolean':
                    component_data[field_name] = False
                elif field_type == 'array':
                    component_data[field_name] = []
                elif field_type == 'object':
                    component_data[field_name] = {}

        return component_data

    def center_geometry_at_origin(self, geometry):
        """
        Center extrusion at its volume centroid.
        Returns centered geometry and translation vector.
        """
        # Get the volume centroid of the geometry
        vmp = Rhino.Geometry.VolumeMassProperties.Compute(geometry)
        volume_centroid = vmp.Centroid
        if volume_centroid is None:
            # Fallback to bounding box centroid if volume centroid fails
            bbox = geometry.GetBoundingBox(True)
            volume_centroid = bbox.Center
        # Create translation vector to center
        translation_vector = -np.array([
            volume_centroid.X, volume_centroid.Y, volume_centroid.Z
        ])
        # Create centered extrusion
        centered_geometry = geometry.Duplicate()
        translation_xform = Rhino.Geometry.Transform.Translation(
            translation_vector[0], translation_vector[1], translation_vector[2]
        )
        centered_geometry.Transform(translation_xform)
        return centered_geometry, translation_vector

    def compute_obb_3d(self, points):
        """
        Compute object oriented bounding box for 3D points using PCA.
        Returns unsorted dimensions and bounding box origin.
        """
        # Apply PCA to find principal axes
        pca = PCA(n_components=3)
        pca.fit(points)

        # Get principal components (eigenvectors)
        principal_components = pca.components_

        # Ensure right-handed coordinate system
        # Check if determinant is positive (right-handed)
        det = np.linalg.det(principal_components)
        if det < 0:
            # Flip the third component to ensure right-handedness
            principal_components[2] = -principal_components[2]

        # Transform points to PCA space using original component order
        pca_points = np.dot(points, principal_components.T)

        # Find bounds in PCA space
        min_bounds = np.min(pca_points, axis=0)
        max_bounds = np.max(pca_points, axis=0)

        # Compute unsorted dimensions (keep original PCA axis order)
        dimensions = max_bounds - min_bounds

        # Find bounding box center in PCA space
        # Since component is centered at origin, bbx_origin is just the
        # bounding box center in PCA space
        bbx_origin = (min_bounds + max_bounds) / 2.0

        return dimensions.tolist(), principal_components, bbx_origin.tolist()

    def minimum_bounding_rectangle(self, points):
        """
        Compute minimum bounding rectangle for 2D points.
        Returns rectangle corners and angle.
        """
        # Compute the convex hull of the points
        hull = ConvexHull(points)
        hull_points = points[hull.vertices]

        # Initialize variables to keep track of the best rectangle
        min_area = float('inf')
        best_rectangle = None
        best_angle = 0

        # Loop through each edge of the convex hull
        for i in range(len(hull_points)):
            # Determine the points forming the current edge
            p1 = hull_points[i]
            p2 = hull_points[(i + 1) % len(hull_points)]

            # Calculate edge vector
            edge_vec = p2 - p1

            # Rotate the points to align this edge with the x-axis
            angle = np.arctan2(edge_vec[1], edge_vec[0])
            cos_angle = np.cos(-angle)
            sin_angle = np.sin(-angle)
            rot_matrix = np.array([[cos_angle, -sin_angle],
                                   [sin_angle, cos_angle]])
            rotated_points = np.dot(points, rot_matrix.T)

            # Compute the min/max x/y in the rotated points
            min_x = np.min(rotated_points[:, 0])
            max_x = np.max(rotated_points[:, 0])
            min_y = np.min(rotated_points[:, 1])
            max_y = np.max(rotated_points[:, 1])

            # Calculate area of the bounding rectangle
            area = (max_x - min_x) * (max_y - min_y)

            if area < min_area:
                min_area = area
                best_angle = angle

                # Create the rectangle in the rotated space and then rotate it
                # back
                best_rectangle = np.array([
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y]
                ])

                inv_rot_matrix = np.array([
                    [cos_angle, sin_angle],
                    [-sin_angle, cos_angle]
                ])
                best_rectangle = np.dot(best_rectangle, inv_rot_matrix.T)

        return best_rectangle, best_angle

    def compute_obb_2d(self, points, height):
        """
        Compute object oriented bounding box for extrusions using the
        minimum bounding rectangle method to find optimal 2D orientation.
        Returns unsorted dimensions and bounding box origin.
        """
        # Extract only X and Y coordinates for 2D analysis
        points_2d = points[:, :2]

        # Use the minimum bounding rectangle method to find optimal orientation
        mbr, optimal_angle = self.minimum_bounding_rectangle(points_2d)

        # The optimal_angle is the angle of the edge vector that gives
        # minimum area. To align this edge with the x-axis, we need to
        # rotate by -optimal_angle. This matches the logic in
        # minimum_bounding_rectangle
        cos_angle = np.cos(-optimal_angle)
        sin_angle = np.sin(-optimal_angle)

        # Rotate points to the optimal orientation
        rot_matrix = np.array([
            [cos_angle, -sin_angle],
            [sin_angle, cos_angle]
        ])
        rotated_points = np.dot(points_2d, rot_matrix.T)

        # Compute dimensions in the rotated coordinate system
        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])

        x_dim = max_x - min_x
        y_dim = max_y - min_y

        # Find bounding box center in rotated 2D space
        bbx_center_2d = [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0]

        # Find Z center (since component is centered, this should be near 0)
        min_z = np.min(points[:, 2])
        max_z = np.max(points[:, 2])
        z_center = (min_z + max_z) / 2.0

        # Since component is centered at origin, bbx_origin is the bounding
        # box center in rotated 2D space + Z center
        bbx_origin_2d = [bbx_center_2d[0], bbx_center_2d[1], z_center]

        # Ensure X is the longest dimension for consistency
        if x_dim >= y_dim:
            dimensions = [x_dim, y_dim, height]
            # PCA frame aligns with the optimal orientation
            principal_components = np.array([
                [cos_angle, -sin_angle, 0],  # X axis = long axis
                [sin_angle, cos_angle, 0],   # Y axis = short axis
                [0, 0, 1]                    # Z axis stays vertical
            ])
        else:
            # Swap dimensions - the longer dimension should be X
            dimensions = [y_dim, x_dim, height]
            # Rotate by 90 degrees to make Y the X axis
            cos_angle_90 = np.cos(-optimal_angle + np.pi / 2)
            sin_angle_90 = np.sin(-optimal_angle + np.pi / 2)
            principal_components = np.array([
                [cos_angle_90, -sin_angle_90, 0],  # X axis = long axis
                [sin_angle_90, cos_angle_90, 0],   # Y axis = short axis
                [0, 0, 1]                          # Z axis stays vertical
            ])

        return dimensions, principal_components, bbx_origin_2d

    def rhino_xform(self, transformation_matrix) -> Rhino.Geometry.Transform:
        """
        Convert numpy transformation matrix to Rhino Transform.
        """
        XForm = Rhino.Geometry.Transform.Identity
        XForm.M00 = transformation_matrix[0][0]
        XForm.M01 = transformation_matrix[0][1]
        XForm.M02 = transformation_matrix[0][2]
        XForm.M03 = transformation_matrix[0][3]
        XForm.M10 = transformation_matrix[1][0]
        XForm.M11 = transformation_matrix[1][1]
        XForm.M12 = transformation_matrix[1][2]
        XForm.M13 = transformation_matrix[1][3]
        XForm.M20 = transformation_matrix[2][0]
        XForm.M21 = transformation_matrix[2][1]
        XForm.M22 = transformation_matrix[2][2]
        XForm.M23 = transformation_matrix[2][3]
        return XForm

    def process_geometry(self, geometry: Rhino.Geometry.GeometryBase):
        """
        Process geometry to extract points and determine if 3D.
        Returns points array and boolean indicating if 3D.
        """
        compute_3d = False
        # HANDLE BREP
        if isinstance(geometry, Rhino.Geometry.Brep):
            points = np.array([[p.Location.X,
                                p.Location.Y,
                                p.Location.Z] for p in geometry.Vertices])
            compute_3d = True
        # HANDLE EXTRUSIONS
        elif isinstance(geometry, Rhino.Geometry.Extrusion):
            brep = geometry.ToBrep()
            points = np.array([[p.Location.X,
                                p.Location.Y,
                                p.Location.Z] for p in brep.Vertices])
            compute_3d = False
        # HANDLE MESH
        elif isinstance(geometry, Rhino.Geometry.Mesh):
            points = np.array([[p.X, p.Y, p.Z] for p in geometry.Vertices])
            compute_3d = True
        # IF NOT ONE OF THESE GEOMETRY TYPES
        else:
            raise RuntimeError('Geometry processing not implemented '
                               f'for geometry of type {type(geometry)}!')
        # return results
        return points, compute_3d

    def validate_uuid(self, uuid_to_test: str, version: int = 4) -> bool:
        """
        Check if uuid_to_test is a valid UUID.
        Returns True if uuid_to_test is a valid UUID, otherwise False.
        """
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test

    def get_geometry_folder_path(self, component_id: str) -> str:
        """
        Get the geometry folder path for a component.
        Returns the appropriate path based on the operating system.
        """
        if platform.system() == 'Windows':
            base_path = os.path.expandvars('%APPDATA%')
            geometry_path = os.path.join(
                base_path, 'DDU_CSC', 'create_component_geometry', component_id
            )
        else:  # macOS and Linux
            base_path = os.path.expanduser('~')
            geometry_path = os.path.join(
                base_path, 'Library', 'Application Support', 'DDU_CSC',
                'create_component_geometry', component_id
            )

        return geometry_path

    def create_geometry_folder(self, component_id: str) -> str:
        """
        Create the geometry folder for a component if it doesn't exist.
        Returns the folder path.
        """
        folder_path = self.get_geometry_folder_path(component_id)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def clear_create_component_geometry_directory(self):
        """
        Clear all files in the create_component_geometry directory.
        This does NOT affect the regular cache directories.
        """
        try:
            if platform.system() == 'Windows':
                base_path = os.path.expandvars('%APPDATA%')
                geometry_dir = os.path.join(
                    base_path, 'DDU_CSC', 'create_component_geometry'
                )
            else:  # macOS and Linux
                base_path = os.path.expanduser('~')
                geometry_dir = os.path.join(
                    base_path, 'Library', 'Application Support', 'DDU_CSC',
                    'create_component_geometry'
                )

            if os.path.exists(geometry_dir):
                # Remove all files and subdirectories
                for root, dirs, files in os.walk(geometry_dir, topdown=False):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            os.remove(file_path)
                        except (OSError, IOError):
                            pass  # Silently continue if file can't be removed
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            os.rmdir(dir_path)
                        except (OSError, IOError):
                            pass  # Silently continue if dir can't be removed

                self._addRemark(
                    'Cleared create_component_geometry '
                    f'directory: {geometry_dir}'
                )
                return True
            else:
                self._addRemark(
                    'create_component_geometry directory does not exist'
                )
                return True

        except Exception as e:
            self._addWarning(
                'Failed to clear create_component_geometry '
                f' directory: {str(e)}'
            )
            return False

    def reduce_mesh(
        self, mesh: Rhino.Geometry.Mesh, target_face_count: int
    ) -> Rhino.Geometry.Mesh:
        """
        Reduce a mesh to a target face count using Rhino's mesh reduction.
        Returns the reduced mesh.
        """
        reduced_mesh = mesh.Duplicate()
        reduced_mesh.Reduce(target_face_count, True, 5, False, True)
        reduced_mesh.Faces.ConvertQuadsToTriangles()
        reduced_mesh.Compact()
        return reduced_mesh

    def process_mesh_geometry(
        self,
        geometry: Rhino.Geometry.Mesh,
        component_id: str,
        mesh_primitive_threshold: int = 8000,
        mesh_reduced_threshold: int = 15000,
        mesh_reduced_target: int = 10000,
        mesh_primitive_target: int = 500
    ) -> tuple:
        """
        Process mesh geometry and create reduced/primitive versions if needed.
        Returns (original_mesh, reduced_mesh, primitive_mesh, files_saved)
        """
        # Get face count
        face_count = geometry.Faces.Count

        # Initialize return values
        reduced_mesh = None
        primitive_mesh = None
        files_saved = False

        # Check if geometry files already exist
        folder_path = self.get_geometry_folder_path(component_id)
        detailed_obj_path = os.path.join(folder_path, 'mesh.obj')
        reduced_obj_path = os.path.join(folder_path, 'mesh_reduced.obj')
        files_exist = (os.path.exists(detailed_obj_path) or
                       os.path.exists(reduced_obj_path))
        if files_exist:
            self._addWarning(
                f'Geometry files already exist for component {component_id}. '
                f'Skipping file saving but computing primitive geometry.'
            )

        # Determine what versions to create based on face count
        if face_count > mesh_reduced_threshold:
            # Create both reduced and primitive versions
            if not files_exist:
                reduced_mesh = self.reduce_mesh(
                    geometry,
                    mesh_reduced_target
                )
            primitive_mesh = self.reduce_mesh(
                geometry,
                mesh_primitive_target
            )
            files_saved = not files_exist  # Only save if files don't exist
        elif face_count > mesh_primitive_threshold:
            # Create only primitive version
            primitive_mesh = self.reduce_mesh(
                geometry,
                mesh_primitive_target
            )
            files_saved = not files_exist  # Only save if files don't exist
        else:
            # Use original as primitive, no files saved
            primitive_mesh = geometry

        # Save files if needed and files don't already exist
        if files_saved:
            try:
                folder_path = self.create_geometry_folder(component_id)

                # Save original/detailed mesh with object declaration
                detailed_obj_path = os.path.join(folder_path, 'mesh.obj')
                self.save_multiple_meshes_as_obj(
                    [geometry], detailed_obj_path
                )

                # Save reduced mesh if created
                if reduced_mesh is not None:
                    reduced_obj_path = os.path.join(
                        folder_path, 'mesh_reduced.obj'
                    )
                    self.save_multiple_meshes_as_obj(
                        [reduced_mesh], reduced_obj_path
                    )

                self._addRemark(f'Saved geometry files to {folder_path}')

            except Exception as e:
                self._addWarning(f'Failed to save geometry files: {str(e)}')
                files_saved = False

        return geometry, reduced_mesh, primitive_mesh, files_saved

    def process_multiple_meshes_geometry(
            self,
            meshes,
            component_id,
            mesh_primitive_threshold: int = 8000,
            mesh_reduced_threshold: int = 15000,
            mesh_reduced_target: int = 10000,
            mesh_primitive_target: int = 500):
        """
        Process multiple meshes for geometry reduction and file saving.
        Returns list of primitive meshes and files_saved status.
        """
        if not meshes or len(meshes) == 0:
            return [], False

        primitive_meshes = []
        reduced_meshes = []
        files_saved = False

        # Check if files already exist
        folder_path = self.create_geometry_folder(component_id)
        detailed_obj_path = os.path.join(folder_path, 'mesh.obj')
        reduced_obj_path = os.path.join(folder_path, 'mesh_reduced.obj')
        files_exist = (os.path.exists(detailed_obj_path) or
                       os.path.exists(reduced_obj_path))

        if files_exist:
            self._addWarning(
                f'Geometry files already exist for component {component_id}. '
                f'Skipping file saving but computing primitive geometry.'
            )

        # Check if any mesh needs file saving
        # Save detailed files if any mesh has > 500 faces
        # Save reduced files if any mesh has > 5000 faces
        needs_detailed_saving = any(mesh is not None and
                                    mesh.Faces.Count > mesh_primitive_target
                                    for mesh in meshes)
        needs_reduced_saving = any(mesh is not None and
                                   mesh.Faces.Count > mesh_reduced_threshold
                                   for mesh in meshes)
        needs_file_saving = needs_detailed_saving or needs_reduced_saving

        # Process each mesh
        for i, mesh in enumerate(meshes):
            if mesh is None:
                primitive_meshes.append(None)
                reduced_meshes.append(None)
                continue

            # Determine face count for this mesh
            face_count = mesh.Faces.Count

            # Create versions based on face count (matching single mesh logic)
            if face_count > mesh_reduced_threshold:
                # Create both reduced and primitive versions
                if not files_exist and needs_file_saving:
                    reduced_mesh = self.reduce_mesh(
                        mesh,
                        mesh_reduced_target
                    )
                else:
                    reduced_mesh = None
                primitive_mesh = self.reduce_mesh(
                    mesh,
                    mesh_primitive_target
                )
            elif face_count > mesh_primitive_threshold:
                # Create only primitive version
                reduced_mesh = None
                primitive_mesh = self.reduce_mesh(
                    mesh,
                    mesh_primitive_target
                )
            else:
                # Use original as primitive, no files saved
                reduced_mesh = None
                primitive_mesh = mesh

            primitive_meshes.append(primitive_mesh)
            reduced_meshes.append(reduced_mesh)

        # Set files_saved flag (only save if files don't exist and needed)
        files_saved = not files_exist and needs_file_saving

        # Save files if needed and files don't already exist
        if files_saved:
            try:
                # Save detailed files if any mesh has > 500 faces
                if needs_detailed_saving:
                    self.save_multiple_meshes_as_obj(
                        meshes, detailed_obj_path
                    )

                # Save reduced files if any mesh has > 5000 faces
                if needs_reduced_saving:
                    # Include ALL meshes but use reduced
                    # versions where available
                    reduced_meshes_for_saving = []
                    for i, mesh in enumerate(meshes):
                        if mesh is not None:
                            if reduced_meshes[i] is not None:
                                # Use reduced version if available
                                reduced_meshes_for_saving.append(
                                    reduced_meshes[i])
                            else:
                                # Use original mesh if no reduced version
                                reduced_meshes_for_saving.append(mesh)

                    if reduced_meshes_for_saving:
                        self.save_multiple_meshes_as_obj(
                            reduced_meshes_for_saving, reduced_obj_path
                        )

                self._addRemark(f'Saved geometry files to {folder_path}')

            except Exception as e:
                self._addWarning(f'Failed to save geometry files: {str(e)}')
                files_saved = False

        return primitive_meshes, files_saved

    def save_multiple_meshes_as_obj(self, meshes, file_path):
        """
        Save meshes as a single OBJ file with object declarations.
        Each mesh becomes a separate object in the OBJ file.
        Works for both single meshes (wrapped in list) and multiple meshes.
        Uses v X Y Z R G B format for vertices with RGB integer colors.
        No MTL file generation - colors are embedded in OBJ file.
        """
        obj_content = '# OBJ file generated by DDU_CSC\n'
        obj_content += '# Meshes with object declarations\n'
        obj_content += '# Vertex colors embedded (no MTL file)\n\n'

        vertex_offset = 0

        for i, mesh in enumerate(meshes):
            if mesh is None:
                continue

            # Add object declaration
            obj_content += f'o object_{i}\n'

            # Add vertices with coordinate system mapping (Rhino Z -> OBJ Y)
            # and colors in v X Y Z R G B format
            has_vertex_colors = mesh.VertexColors.Count > 0
            for i, vertex in enumerate(mesh.Vertices):
                # Map Rhino (X,Y,Z) to OBJ (X,Z,-Y) coordinate system
                if has_vertex_colors and i < mesh.VertexColors.Count:
                    # Use vertex color if available
                    color = mesh.VertexColors[i]
                    obj_content += (f'v {vertex.X} {vertex.Z} {-vertex.Y} '
                                    f'{color.R} {color.G} {color.B}\n')
                else:
                    # Use default white color if no vertex colors
                    obj_content += (f'v {vertex.X} {vertex.Z} {-vertex.Y} '
                                    f'255 255 255\n')

            # Add texture coordinates if available
            if mesh.TextureCoordinates.Count > 0:
                for tex_coord in mesh.TextureCoordinates:
                    obj_content += f'vt {tex_coord.X} {tex_coord.Y}\n'

            # Add faces (OBJ uses 1-based indexing, adjust for vertex offset)
            for face in mesh.Faces:
                if face.IsTriangle:
                    obj_content += (f'f {face.A + 1 + vertex_offset} '
                                    f'{face.B + 1 + vertex_offset} '
                                    f'{face.C + 1 + vertex_offset}\n')
                elif face.IsQuad:
                    obj_content += (f'f {face.A + 1 + vertex_offset} '
                                    f'{face.B + 1 + vertex_offset} '
                                    f'{face.C + 1 + vertex_offset} '
                                    f'{face.D + 1 + vertex_offset}\n')

            # Update vertex offset for next mesh
            vertex_offset += mesh.Vertices.Count
            obj_content += '\n'

        # Write OBJ file
        with open(file_path, 'w') as f:
            f.write(obj_content)

    def compute_pca_for_multiple_meshes(self, meshes):
        """
        Compute PCA for multiple meshes as a whole assembly.
        Centers the assembly at origin before computing PCA.
        Returns dimensions, principal components, translation vector,
        and bbx_origin.
        """
        if not meshes or len(meshes) == 0:
            return None, None, None, None

        # Collect all points from all meshes
        all_points = []
        for mesh in meshes:
            if mesh is None:
                continue
            for vertex in mesh.Vertices:
                all_points.append([vertex.X, vertex.Y, vertex.Z])

        if not all_points:
            return None, None, None, None

        # Convert to numpy array
        points_array = np.array(all_points)

        # Center the assembly at origin (like single meshes)
        # Compute centroid of all points
        centroid = np.mean(points_array, axis=0)
        translation_vector = -centroid

        # Center the points
        centered_points = points_array + translation_vector

        # Compute PCA for the centered combined geometry
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )

        return dimensions, principal_components, translation_vector, bbx_origin

    def compute_pca_for_first_mesh_only(self, meshes):
        """
        Compute PCA for only the first mesh, but apply transformations to all
        meshes.
        Centers only the first mesh at origin before computing PCA.
        Returns dimensions, principal components, translation vector,
        and bbx_origin.
        """
        # Retrieve the first mesh
        mesh = meshes[0]
        # Use the same centering approach as single mesh case
        # Center the first mesh at origin using volume centroid
        (centered_mesh, translation_vector) = (
            self.center_geometry_at_origin(mesh)
        )
        # Extract points from the centered first mesh
        centered_points, compute_3d = self.process_geometry(centered_mesh)
        # Compute PCA for the centered first mesh only
        dimensions, principal_components, bbx_origin = (
            self.compute_obb_3d(centered_points)
        )
        return dimensions, principal_components, translation_vector, bbx_origin

    def RunScript(self,
            ClearLocalStorage: bool,
            ComponentID: str,
            Name: str,
            Type: str,
            Material: str,
            Dataset: str,
            Complexity: int,
            Fragment: bool,
            Assembly: bool,
            Color: System.Drawing.Color,
            Location: Rhino.Geometry.Vector3d,
            Geometry: System.Collections.Generic.List[Rhino.Geometry.GeometryBase],
            MarkerPoints: System.Collections.Generic.List[Rhino.Geometry.Point3d]):

        # MESH REDUCTION SETTINGS
        # If mesh has tc above this but below reduced threshold,
        # only the primitive version will be computed
        MESH_PRIMITIVE_THRESHOLD = 8000
        # If mesh has tc above this, reduced and primitive versions
        # will be created
        MESH_REDUCED_THRESHOLD = 15000
        # target tc for reduced mesh
        MESH_REDUCED_TARGET = 10000
        # target tc for primitive mesh
        MESH_PRIMITIVE_TARGET = 500

        # set up output trees and results tuple
        ComponentData = Grasshopper.DataTree[System.Object]()
        try:
            # Handle ClearLocalStorage input
            if ClearLocalStorage:
                self._addRemark(
                    'Clearing create_component_geometry directory...'
                )
                if self.clear_create_component_geometry_directory():
                    self.Component.Message = (
                        'Local storage cleared successfully'
                    )
                else:
                    self.Component.Message = 'Failed to clear local storage'
                return ComponentData

            # Initialize schema validation
            self._addRemark('Initializing component creation with '
                            'schema validation...')

            # sanitize input and abort if not present
            if not ComponentID:
                msg = 'Input ComponentID failed to collect data!'
                self._addWarning(msg)
                return ComponentData
            elif not self.validate_uuid(ComponentID):
                msg = 'Input ComponentID is not a valid UUID! Aborting...'
                self._addError(msg)
                return ComponentData
            if not Name:
                msg = "Input Name failed to collect data. Using auto-generated name!"
                self._addRemark(msg)
                Name = ''
            if not Type:
                msg = 'Input Type failed to collect data!'
                self._addWarning(msg)
                return ComponentData
            if not Material:
                msg = 'Input Material failed to collect data!'
                self._addWarning(msg)
                return ComponentData
            if not Dataset:
                msg = 'Input Dataset failed to collect data!'
                self._addWarning(msg)
                return ComponentData
            if Complexity is None:
                msg = 'Input Complexity failed to collect data!'
                self._addWarning(msg)
                return ComponentData
            if (not isinstance(Complexity, int) or
                    Complexity < 0 or Complexity > 3):
                msg = 'Input Complexity must be an integer between 0 and 3!'
                self._addError(msg)
                return ComponentData

            # Set defaults for Fragment and Assembly if not provided
            if Fragment is None:
                Fragment = False
            if Assembly is None:
                Assembly = False

            # Handle Location parameter (X=latitude, Y=longitude, Z ignored)
            location_data = None
            if Location is not None:
                location_data = {
                    "lat": Location.X,
                    "lon": Location.Y
                }

            if not Color:
                msg = ('Input Color failed to collect data. '
                       'Will use Grey as default Color.')
                self._addRemark(msg)
                print(msg)
                Color = System.Drawing.Color.FromArgb(255, 175, 175, 175)
            if not Geometry:
                msg = 'Input Geometry failed to collect data!'
                self._addWarning(msg)
                return ComponentData

            # TYPE FILTERING
            if not Geometry or len(Geometry) == 0:
                msg = 'Input Geometry is invalid!'
                self._addError(msg)
                return ComponentData

            # Check if single or multiple objects
            if len(Geometry) == 1:
                # Single object validation
                single_geometry = Geometry[0]
                if Type == 'rubble':
                    if not isinstance(single_geometry, Rhino.Geometry.Mesh):
                        msg = ('The "rubble" type expects a Mesh as '
                               'geometry input! Please ensure and try again.')
                        raise ValueError(msg)
                elif Type == 'sheet':
                    if not isinstance(
                            single_geometry,
                            (Rhino.Geometry.Mesh, Rhino.Geometry.Extrusion)
                    ):
                        msg = (
                            'The "sheet" type expects a Mesh or Extrusion as '
                            'geometry input! Please ensure and try again.'
                        )
                        raise ValueError(msg)
            else:
                # Multiple objects - all must be meshes
                for i, geom in enumerate(Geometry):
                    if (geom is not None and
                            not isinstance(geom, Rhino.Geometry.Mesh)):
                        msg = (
                            f'The geometry input at index {i} is not a Mesh! '
                            'For multiple objects, all must be '
                            'Rhino.Geometry.Mesh objects.')
                        raise ValueError(msg)

            self.Component.Message = f'Processing {Type} component...'

            # Process geometry to extract points and compute PCA
            if len(Geometry) == 1:
                # Handle single geometry (existing logic)
                single_geometry = Geometry[0]
                # Center geometry at world origin FIRST
                (centered_geometry, translation_vector) = (
                    self.center_geometry_at_origin(single_geometry)
                )
                # Extract CENTEREDpoints from the CENTERED geometry
                centered_points, compute_3d = self.process_geometry(
                    centered_geometry
                )
                # Compute object oriented bounding box and PCA transformation
                if compute_3d:
                    dimensions, principal_components, bbx_origin = (
                        self.compute_obb_3d(centered_points))
                else:
                    # 2D APPROACH, i.e. used for Extrusions
                    height = centered_geometry.PathStart.DistanceTo(
                        centered_geometry.PathEnd
                    )
                    dimensions, principal_components, bbx_origin = (
                        self.compute_obb_2d(
                            centered_points, height)
                    )
            else:
                # Handle multiple meshes - choose PCA computation based on
                # Assembly parameter
                if Assembly:
                    # Assembly=True: compute PCA for whole assembly
                    (dimensions, principal_components, translation_vector,
                     bbx_origin) = self.compute_pca_for_multiple_meshes(
                         Geometry)
                else:
                    # Assembly=False: compute PCA only for first mesh, but
                    # apply to all meshes
                    (dimensions, principal_components, translation_vector,
                     bbx_origin) = self.compute_pca_for_first_mesh_only(
                         Geometry)
                centered_geometry = None  # Not used for multiple meshes
                compute_3d = True  # Always 3D for multiple meshes

            # Get component schema first
            schema = self.get_component_schema()

            # Process marker points - apply same transformation as geometry
            marker_points_data = []
            if MarkerPoints and len(MarkerPoints) > 0:
                for point in MarkerPoints:
                    if point is not None:
                        # Apply the same translation vector used for
                        # centering geometry
                        transformed_point = [
                            point.X + translation_vector[0],
                            point.Y + translation_vector[1],
                            point.Z + translation_vector[2]
                        ]
                        marker_points_data.append(transformed_point)

            # Create component data dictionary based on schema
            COMPDATA = self.build_component_data_from_schema(
                schema, ComponentID, Name, Type, Material, Dataset, Complexity,
                Fragment, Assembly, Color, dimensions, location_data,
                principal_components
            )

            # Set the computed bbx_origin
            COMPDATA['bbx_origin'] = bbx_origin

            # Add marker points to component data
            COMPDATA['marker_points'] = marker_points_data

            # Validate component data against schema
            if not self.validate_component_data(COMPDATA, schema):
                self._addWarning('Component data validation failed, '
                                 'but continuing...')

            # Process geometry input based on type
            if len(Geometry) == 1:
                # HANDLE SINGLE GEOMETRY
                single_geometry = Geometry[0]
                if isinstance(single_geometry, Rhino.Geometry.Mesh):
                    # Process single mesh
                    (original_mesh,
                     reduced_mesh,
                     primitive_mesh,
                     files_saved) = (
                        self.process_mesh_geometry(
                            centered_geometry,
                            ComponentID,
                            mesh_primitive_threshold=MESH_PRIMITIVE_THRESHOLD,
                            mesh_reduced_threshold=MESH_REDUCED_THRESHOLD,
                            mesh_reduced_target=MESH_REDUCED_TARGET,
                            mesh_primitive_target=MESH_PRIMITIVE_TARGET
                        )
                    )

                    # Use primitive mesh for JSON geometry data
                    vertices = [[p.X, p.Y, p.Z]
                                for p in primitive_mesh.Vertices]
                    faces = [[f[0], f[1], f[2]]
                             for f in primitive_mesh.Faces]

                    # Extract vertex colors if available
                    colors = []
                    if primitive_mesh.VertexColors.Count > 0:
                        colors = [[c.R, c.G, c.B]
                                  for c in primitive_mesh.VertexColors]
                    else:
                        # Use default color if no vertex colors
                        colors = [[Color.R, Color.G, Color.B]] * len(vertices)

                    # Use new meshes format even for single mesh
                    comp_geometry = {
                        'meshes': [{
                            'v': vertices,
                            'f': faces,
                            'c': colors
                        }]
                    }
                    COMPDATA['geometry'] = comp_geometry

                elif isinstance(single_geometry, Rhino.Geometry.Extrusion):
                    # Handle single extrusion (existing logic)
                    # Get the profile curve from the CENTERED geometry and
                    # convert to polyline
                    if centered_geometry.ProfileCount > 1:
                        raise RuntimeError(
                            'Extrusion has more than one profile!'
                        )
                    # Get first profile
                    profile_curve = centered_geometry.Profile3d(0, 0.0)
                    if profile_curve is None:
                        raise RuntimeError('Extrusion has no profile curve!')

                    # Convert profile to polyline
                    _tgpr, polyline = profile_curve.TryGetPolyline()
                    if _tgpr is False:
                        polyline = profile_curve.ToPolyline(0.01, 0.01, 0, 0)
                    if polyline is None:
                        raise RuntimeError(
                            'Failed to convert profile curve to polyline!'
                        )

                    # Get height
                    height = centered_geometry.PathStart.DistanceTo(
                        centered_geometry.PathEnd)

                    # Create extrusion geometry data
                    comp_extrusion = {
                        'extrusion': {
                            'profile': [[p.X, p.Y] for p in polyline],
                            'height': height
                        }
                    }
                    COMPDATA['geometry'] = comp_extrusion
            else:
                # HANDLE MULTIPLE MESHES
                # Center all meshes using the translation
                # vector from PCA computation
                centered_meshes = []
                for mesh in Geometry:
                    if mesh is not None:
                        # Create a copy of the mesh
                        centered_mesh = mesh.Duplicate()
                        # Apply the translation to center the mesh
                        translation_xform = (
                            Rhino.Geometry.Transform.Translation(
                                translation_vector[0],
                                translation_vector[1],
                                translation_vector[2]
                            )
                        )
                        centered_mesh.Transform(translation_xform)
                        centered_meshes.append(centered_mesh)
                    else:
                        centered_meshes.append(None)

                # Process multiple meshes (now centered)
                primitive_meshes, files_saved = (
                    self.process_multiple_meshes_geometry(
                        centered_meshes,
                        ComponentID,
                        mesh_primitive_threshold=MESH_PRIMITIVE_THRESHOLD,
                        mesh_reduced_threshold=MESH_REDUCED_THRESHOLD,
                        mesh_reduced_target=MESH_REDUCED_TARGET,
                        mesh_primitive_target=MESH_PRIMITIVE_TARGET
                    )
                )

                # Create meshes array for JSON geometry data
                meshes_data = []
                for primitive_mesh in primitive_meshes:
                    vertices = [[p.X, p.Y, p.Z]
                                for p in primitive_mesh.Vertices]
                    faces = [[f[0], f[1], f[2]]
                             for f in primitive_mesh.Faces]

                    # Extract vertex colors if available
                    colors = []
                    if primitive_mesh.VertexColors.Count > 0:
                        colors = [[c.R, c.G, c.B]
                                  for c in primitive_mesh.VertexColors]
                    else:
                        # Use default color if no vertex colors
                        colors = [[Color.R, Color.G, Color.B]] * len(vertices)

                    meshes_data.append({
                        'v': vertices,
                        'f': faces,
                        'c': colors
                    })

                comp_geometry = {
                    'meshes': meshes_data
                }
                COMPDATA['geometry'] = comp_geometry

            # create json string
            ComponentData = json.dumps(COMPDATA)

            # Update success message
            self.Component.Message = (
                f'Successfully created {Type} component {ComponentID}'
            )
            self._addRemark(f'Created {Type} component {ComponentID}')

            # return output
            return ComponentData

        except ValueError as e:
            msg = f'Validation error: {str(e)}'
            self._addError(msg)

        except RuntimeError as e:
            msg = f'Runtime error: {str(e)}'
            self._addError(msg)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            raise e

        return ComponentData
