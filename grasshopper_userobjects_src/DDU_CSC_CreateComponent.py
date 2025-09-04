#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import uuid
import os
import platform
from datetime import datetime

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from scipy.spatial import ConvexHull
from sklearn.decomposition import PCA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'CreateComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_CreateComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250902
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

    def compute_minimum_bounding_box_3d(self, points):
        """
        Compute minimum bounding box for 3D points using PCA.
        Returns dimensions sorted by length (X=longest, Y=second, Z=shortest).
        """
        # Apply PCA to find principal axes
        pca = PCA(n_components=3)
        pca.fit(points)

        # Get principal components (eigenvectors)
        principal_components = pca.components_

        # Sort components by explained variance (largest first)
        explained_variance = pca.explained_variance_
        sorted_indices = np.argsort(-explained_variance)
        sorted_components = principal_components[sorted_indices]

        # Transform points to PCA space
        pca_points = np.dot(points, sorted_components.T)

        # Find bounds in PCA space
        min_bounds = np.min(pca_points, axis=0)
        max_bounds = np.max(pca_points, axis=0)

        # Compute dimensions (sorted by length: X=longest, Y=second,
        # Z=shortest)
        dimensions = max_bounds - min_bounds

        return dimensions.tolist(), sorted_components

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

    def compute_minimum_bounding_box_2d(self, points, height):
        """
        Compute minimum axis-aligned bounding box for extrusions using the
        minimum bounding rectangle method to find optimal 2D orientation.
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

        return dimensions, principal_components

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
                base_path, 'DDU_CSC', 'component_geometry', component_id
            )
        else:  # macOS and Linux
            base_path = os.path.expanduser('~')
            geometry_path = os.path.join(
                base_path, 'Library', 'Application Support', 'DDU_CSC',
                'component_geometry', component_id
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

    def generate_vertex_colors_from_texture(
            self, mesh: Rhino.Geometry.Mesh) -> Rhino.Geometry.Mesh:
        """
        Generate vertex colors from texture if mesh has texture but no vertex
        colors. Returns the mesh with generated vertex colors.
        """
        try:
            # Check if mesh has texture but no vertex colors
            if (mesh.VertexColors.Count == 0 and
                    mesh.TextureCoordinates.Count > 0 and
                    mesh.Material and mesh.Material.IsValid):
                texture = mesh.Material.GetBitmapTexture()
                if texture and texture.IsValid:
                    bitmap = texture.GetBitmap()
                    if bitmap:
                        # Create a copy of the mesh to modify
                        colored_mesh = mesh.Duplicate()
                        # Generate vertex colors from texture
                        for i in range(colored_mesh.Vertices.Count):
                            if i < colored_mesh.TextureCoordinates.Count:
                                tex_coord = colored_mesh.TextureCoordinates[i]
                                # Convert UV coordinates to pixel coordinates
                                u = int(tex_coord.X * (bitmap.Width - 1))
                                v = int(tex_coord.Y * (bitmap.Height - 1))
                                # Clamp coordinates
                                u = max(0, min(u, bitmap.Width - 1))
                                v = max(0, min(v, bitmap.Height - 1))
                                # Get pixel color
                                pixel_color = bitmap.GetPixel(u, v)
                                # Add vertex color
                                colored_mesh.VertexColors.Add(pixel_color)
                            else:
                                # Fallback to white if no texture coordinate
                                colored_mesh.VertexColors.Add(
                                    System.Drawing.Color.White
                                )
                        # add remark
                        self._addRemark('Generated vertex colors from texture')
                        return colored_mesh
            # Return original mesh if no texture or already has vertex colors
            return mesh
        except Exception as e:
            self._addWarning(
                f'Failed to generate vertex colors from texture: {str(e)}'
            )
            return mesh

    def save_mesh_as_obj(
        self, mesh: Rhino.Geometry.Mesh, file_path: str,
        material_name: str = 'default_material'
    ) -> bool:
        """
        Save a mesh as OBJ file with associated MTL file.
        Handles coordinate system mapping (Rhino Z -> OBJ Y) and textures.
        Returns True if successful, False otherwise.
        """
        try:
            # Create OBJ content
            obj_content = '# OBJ file generated by DDU_CSC\n'
            mtl_filename = os.path.basename(file_path).replace('.obj', '.mtl')
            obj_content += f'mtllib {mtl_filename}\n'
            obj_content += 'o mesh\n'

            # Add vertices with coordinate system mapping (Rhino Z -> OBJ Y)
            for vertex in mesh.Vertices:
                # Map Rhino (X,Y,Z) to OBJ (X,Z,-Y) coordinate system
                obj_content += f'v {vertex.X} {vertex.Z} {-vertex.Y}\n'

            # Add vertex colors if available
            has_vertex_colors = mesh.VertexColors.Count > 0
            if has_vertex_colors:
                for color in mesh.VertexColors:
                    # Normalize colors to 0-1 range
                    r = color.R / 255.0
                    g = color.G / 255.0
                    b = color.B / 255.0
                    obj_content += f'vc {r} {g} {b}\n'

            # Add texture coordinates if mesh has them
            has_texture_coords = mesh.TextureCoordinates.Count > 0
            if has_texture_coords:
                for tex_coord in mesh.TextureCoordinates:
                    obj_content += f'vt {tex_coord.X} {tex_coord.Y}\n'

            # Add faces (OBJ uses 1-based indexing)
            for i, face in enumerate(mesh.Faces):
                if face.IsTriangle:
                    if has_vertex_colors and has_texture_coords:
                        # v/vt/vc format
                        obj_content += (
                            f'f {face.A + 1}/{face.A + 1}/{face.A + 1} '
                            f'{face.B + 1}/{face.B + 1}/{face.B + 1} '
                            f'{face.C + 1}/{face.C + 1}/{face.C + 1}\n'
                        )
                    elif has_vertex_colors:
                        # v//vc format
                        obj_content += (
                            f'f {face.A + 1}//{face.A + 1} '
                            f'{face.B + 1}//{face.B + 1} '
                            f'{face.C + 1}//{face.C + 1}\n'
                        )
                    elif has_texture_coords:
                        # v/vt format
                        obj_content += (
                            f'f {face.A + 1}/{face.A + 1} '
                            f'{face.B + 1}/{face.B + 1} '
                            f'{face.C + 1}/{face.C + 1}\n'
                        )
                    else:
                        # v format
                        obj_content += (
                            f'f {face.A + 1} {face.B + 1} {face.C + 1}\n'
                        )
                elif face.IsQuad:
                    if has_vertex_colors and has_texture_coords:
                        obj_content += (
                            f'f {face.A + 1}/{face.A + 1}/{face.A + 1} '
                            f'{face.B + 1}/{face.B + 1}/{face.B + 1} '
                            f'{face.C + 1}/{face.C + 1}/{face.C + 1} '
                            f'{face.D + 1}/{face.D + 1}/{face.D + 1}\n'
                        )
                    elif has_vertex_colors:
                        obj_content += (
                            f'f {face.A + 1}//{face.A + 1} '
                            f'{face.B + 1}//{face.B + 1} '
                            f'{face.C + 1}//{face.C + 1} '
                            f'{face.D + 1}//{face.D + 1}\n'
                        )
                    elif has_texture_coords:
                        obj_content += (
                            f'f {face.A + 1}/{face.A + 1} '
                            f'{face.B + 1}/{face.B + 1} '
                            f'{face.C + 1}/{face.C + 1} '
                            f'{face.D + 1}/{face.D + 1}\n'
                        )
                    else:
                        obj_content += (
                            f'f {face.A + 1} {face.B + 1} {face.C + 1} '
                            f'{face.D + 1}\n'
                        )

            # Write OBJ file
            with open(file_path, 'w') as f:
                f.write(obj_content)

            # Create MTL file
            mtl_path = file_path.replace('.obj', '.mtl')
            mtl_content = '# MTL file generated by DDU_CSC\n'
            mtl_content += f'newmtl {material_name}\n'
            # Default material properties
            mtl_content += 'Ka 0.2 0.2 0.2\n'  # Ambient color
            mtl_content += 'Kd 0.8 0.8 0.8\n'  # Diffuse color
            mtl_content += 'Ks 0.0 0.0 0.0\n'  # Specular color
            mtl_content += 'Ns 0.0\n'          # Specular exponent
            mtl_content += 'illum 1\n'         # Illumination model

            # Write MTL file
            with open(mtl_path, 'w') as f:
                f.write(mtl_content)

            return True

        except Exception as e:
            self._addWarning(f'Failed to save mesh as OBJ: {str(e)}')
            return False

    def process_mesh_geometry(
        self, geometry: Rhino.Geometry.Mesh, component_id: str
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

        # Generate vertex colors from texture if needed
        processed_geometry = self.generate_vertex_colors_from_texture(geometry)

        # Determine what versions to create based on face count
        if face_count > 5000:
            # Create both reduced and primitive versions
            if not files_exist:
                reduced_mesh = self.reduce_mesh(processed_geometry, 1000)
            primitive_mesh = self.reduce_mesh(processed_geometry, 350)
            files_saved = not files_exist  # Only save if files don't exist
        elif face_count > 500:
            # Create only primitive version
            primitive_mesh = self.reduce_mesh(processed_geometry, 350)
            files_saved = not files_exist  # Only save if files don't exist
        else:
            # Use original as primitive, no files saved
            primitive_mesh = processed_geometry

        # Save files if needed and files don't already exist
        if files_saved:
            try:
                folder_path = self.create_geometry_folder(component_id)

                # Save original/detailed mesh
                detailed_obj_path = os.path.join(folder_path, 'mesh.obj')
                self.save_mesh_as_obj(
                    processed_geometry, detailed_obj_path, 'detailed_material'
                )

                # Save reduced mesh if created
                if reduced_mesh is not None:
                    reduced_obj_path = os.path.join(
                        folder_path, 'mesh_reduced.obj'
                    )
                    self.save_mesh_as_obj(
                        reduced_mesh, reduced_obj_path, 'reduced_material'
                    )

                self._addRemark(f'Saved geometry files to {folder_path}')

            except Exception as e:
                self._addWarning(f'Failed to save geometry files: {str(e)}')
                files_saved = False

        return processed_geometry, reduced_mesh, primitive_mesh, files_saved

    def RunScript(
            self,
            ComponentID: str,
            Type: str,
            Material: str,
            Complexity: int,
            Fragment: bool,
            Assembly: bool,
            Color: System.Drawing.Color,
            Location: Rhino.Geometry.Vector3d,
            Geometry: Rhino.Geometry.GeometryBase):
        try:
            # Initialize param descriptions (this has to be done in RunScript)
            self.InputParams[0].Description = (
                'Component ID (must be a valid UUID)'
            )
            self.InputParams[1].Description = (
                'Component type (e.g., "sheet", "rubble")'
            )
            self.InputParams[2].Description = (
                'Material type (e.g., "steel", "concrete", "wood")'
            )
            self.InputParams[3].Description = (
                'Complexity level '
                '(0=simple, 1=normal, 2=complex, 3=very complex)'
            )
            self.InputParams[4].Description = (
                'Fragment status (True for fragments, False for complete)'
            )
            self.InputParams[5].Description = (
                'Assembly status (True for assemblies, False for individual)'
            )
            self.InputParams[6].Description = (
                'Location as Vector3d (X=latitude, Y=longitude, Z ignored)'
            )
            self.InputParams[7].Description = (
                'Component color (System.Drawing.Color)'
            )
            self.InputParams[8].Description = (
                'Rhino geometry object (Mesh or Extrusion for sheets, '
                'Mesh for rubble)'
            )

            # Initialize output param descriptions
            self.OutputParams[0].Description = (
                'Component data as JSON string adhering to ComponentModel '
                'structure. Contains geometry, PCA frame, bounding box, '
                'and metadata.'
            )

            # set up output trees and results tuple
            ComponentData = Grasshopper.DataTree[System.Object]()

            # sanitize input and abort if not present
            if not ComponentID:
                msg = 'Input ComponentID failed to collect data!'
                self._addWarning(msg)
                self.Component.Message = msg
                return ComponentData
            elif not self.validate_uuid(ComponentID):
                msg = 'Input ComponentID is not a valid UUID! Aborting...'
                self._addError(msg)
                self.Component.Message = msg
                return ComponentData
            if not Type:
                msg = 'Input Type failed to collect data!'
                self._addWarning(msg)
                self.Component.Message = msg
                return ComponentData
            if not Material:
                msg = 'Input Material failed to collect data!'
                self._addWarning(msg)
                self.Component.Message = msg
                return ComponentData
            if Complexity is None:
                msg = 'Input Complexity failed to collect data!'
                self._addWarning(msg)
                self.Component.Message = msg
                return ComponentData
            if (not isinstance(Complexity, int) or
                    Complexity < 0 or Complexity > 3):
                msg = 'Input Complexity must be an integer between 0 and 3!'
                self._addError(msg)
                self.Component.Message = msg
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
                self.Component.Message = msg
                return ComponentData
            elif not Geometry.IsValid:
                msg = 'Input Geometry is invalid!'
                self._addError(msg)
                self.Component.Message = msg
                return ComponentData

            # TYPE FILTERING
            if Type == 'rubble':
                if not isinstance(Geometry, Rhino.Geometry.Mesh):
                    msg = ('The "rubble" type expects a Mesh as '
                           'geometry input! Please ensure and try again.')
                    print(msg)
                    raise ValueError(msg)
            elif Type == 'sheet':
                if not isinstance(
                        Geometry,
                        (Rhino.Geometry.Mesh, Rhino.Geometry.Extrusion)
                ):
                    msg = ('The "sheet" type expects a Mesh or Extrusion as '
                           'geometry input! Please ensure and try again.')
                    print(msg)
                    raise ValueError(msg)

            self.Component.Message = f'Processing {Type} component...'

            # Process geometry to extract points
            points, compute_3d = self.process_geometry(Geometry)

            # Center geometry at world origin
            (centered_geometry,
             translation_vector) = self.center_geometry_at_origin(Geometry)

            # Centered points
            centered_points = points - translation_vector

            # Compute minimum bounding box and PCA transformation
            if compute_3d:
                dimensions, principal_components = (
                    self.compute_minimum_bounding_box_3d(centered_points))
            else:
                # 2D APPROACH, i.e. used for Extrusions
                height = centered_geometry.PathStart.DistanceTo(
                    centered_geometry.PathEnd
                )
                dimensions, principal_components = (
                    self.compute_minimum_bounding_box_2d(
                        centered_points, height)
                )

            # Create component data dictionary adhering to ComponentModel
            current_time = datetime.utcnow().isoformat() + 'Z'

            COMPDATA = {
                '_id': ComponentID,
                'name': (f'{str(Type).capitalize()} Component '
                         f'made from {str(Material).capitalize()}'),
                'type': Type,
                'material': Material,
                'created': current_time,
                'lastmodified': current_time,
                'complexity': Complexity,  # User complexity level
                'fragment': Fragment,  # User fragment status
                'assembly': Assembly,  # User assembly status
                'geometry': {},
                'color': [Color.R, Color.G, Color.B],
                'bbx': dimensions,  # [X, Y, Z] dimensions
                'location': location_data,  # {lat, lon} or None
                'descriptors': {},
                'processes': {},
                'iframe': {
                    'o': [0.0, 0.0, 0.0],
                    'x': [1.0, 0.0, 0.0],
                    'y': [0.0, 1.0, 0.0],
                    'z': [0.0, 0.0, 1.0]
                },
                'pca_frame': {
                    'o': [0.0, 0.0, 0.0],
                    'x': principal_components[0].tolist(),
                    'y': principal_components[1].tolist(),
                    'z': principal_components[2].tolist()
                },
                'reserved': '',  # Empty string when not reserved
                'attributes': {},  # Empty attributes dict
                'validated': False
            }

            # Process geometry input based on type
            # HANDLE MESH
            if isinstance(Geometry, Rhino.Geometry.Mesh):
                # Process the centered geometry for mesh reduction
                # and file saving
                (original_mesh, reduced_mesh, primitive_mesh, files_saved) = (
                    self.process_mesh_geometry(centered_geometry, ComponentID)
                )

                # Use primitive mesh for JSON geometry data
                # create geometry dict for mesh with colors
                vertices = [[p.X, p.Y, p.Z]
                            for p in primitive_mesh.Vertices]
                faces = [[f[0], f[1], f[2]] for f in primitive_mesh.Faces]

                # Extract vertex colors if available
                colors = []
                if primitive_mesh.VertexColors.Count > 0:
                    colors = [[c.R, c.G, c.B]
                              for c in primitive_mesh.VertexColors]
                else:
                    # Use default color if no vertex colors
                    colors = [[Color.R, Color.G, Color.B]] * len(vertices)

                comp_mesh = {
                    'mesh': {
                        'v': vertices,
                        'f': faces,
                        'c': colors
                    }
                }
                COMPDATA['geometry'].update(comp_mesh)

            # HANDLE EXTRUSION
            elif isinstance(Geometry, Rhino.Geometry.Extrusion):
                # Get the profile curve from the CENTERED geometry and
                # convert to polyline
                if centered_geometry.ProfileCount > 1:
                    raise RuntimeError('Extrusion has more than one profile!')
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
                        'Could not convert profile curve to polyline!'
                    )

                # Extract 2D points from polyline
                profile_points = [[p.X, p.Y] for p in polyline]

                # Get extrusion height from centered geometry
                height = centered_geometry.PathStart.DistanceTo(
                    centered_geometry.PathEnd)

                comp_extrusion = {
                    'extrusion': {
                        'height': height,
                        'profile': profile_points
                    }
                }
                COMPDATA['geometry'].update(comp_extrusion)

            # HANDLE BREP
            elif isinstance(Geometry, Rhino.Geometry.Brep):
                raise RuntimeError(
                    'Geometry Processing for geometry of '
                    f'type {type(Geometry)} not implemented yet! '
                    'Please convert to Mesh and try again.')
            else:
                raise RuntimeError(
                    'Geometry Processing for geometry of '
                    f'type {type(Geometry)} not implemented yet! '
                    'Please convert to Mesh and try again.')

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
            self.Component.Message = msg

        except RuntimeError as e:
            msg = f'Runtime error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        # Return empty results if there was an error
        ComponentData = Grasshopper.DataTree[System.Object]()
        return ComponentData
