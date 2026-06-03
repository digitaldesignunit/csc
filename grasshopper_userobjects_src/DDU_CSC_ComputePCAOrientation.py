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

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np  # NOQA
from scipy.spatial import ConvexHull  # NOQA
from sklearn.decomposition import PCA  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA

# One PCA sample per this many mm² of triangle area (3D mesh path).
REFERENCE_FACE_AREA_MM2 = 100.0

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComputePCAOrientation'  # NOQA
ghenv.Component.NickName = 'ComputePCAOrientation'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Computes PCA orientation for input geometry. 3D meshes and breps use '
    'face-area-weighted sampling before PCA; extrusions use a 2D minimum '
    'bounding rectangle. Returns OBB, aligned geometry, translation vector, '
    'and PCA transformation matrix.'
)


class CSC_ComputePCAOrientation(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260603
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
            'Input Rhino Geometry'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Object oriented bounding box, obtained using PCA, '
            ' at the location of the input geometry'
        )
        self.OutputParams[1+i].Description = (
            'Input geometry transformed using PCA method and centered at '
            'world origin'
        )
        self.OutputParams[2+i].Description = (
            'Object oriented bounding box transformed using the computed '
            'PCA frame, centered at the world origin'
        )
        self.OutputParams[3+i].Description = (
            'Translation vector that was used to move the geometry '
            'to the world origin'
        )
        self.OutputParams[4+i].Description = (
            'PCA frame that was used to transform the geometry '
            'converted to a Rhino XForm.'
        )

    def center_geometry_at_origin(self, geometry):
        """
        Center geometry at its volume centroid.
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
        # Create centered geometry
        centered_geometry = geometry.Duplicate()
        translation_xform = Rhino.Geometry.Transform.Translation(
            translation_vector[0], translation_vector[1], translation_vector[2]
        )
        centered_geometry.Transform(translation_xform)
        return centered_geometry, translation_vector

    def _triangle_area(self, v0, v1, v2):
        return float(0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0)))

    def sample_points_area_weighted_from_mesh(
            self,
            mesh,
            reference_face_area=REFERENCE_FACE_AREA_MM2,
            min_samples_per_face=1):
        """
        Build a PCA point cloud by repeating face centroids weighted by area.
        """
        vertices = np.array(
            [[v.X, v.Y, v.Z] for v in mesh.Vertices],
            dtype=np.float64,
        )
        if mesh.Faces.Count == 0:
            return vertices

        samples = []
        ref_area = max(reference_face_area, 1e-6)
        for face_idx in range(mesh.Faces.Count):
            face = mesh.Faces[face_idx]
            if face.IsTriangle:
                triangles = [[face.A, face.B, face.C]]
            elif face.IsQuad:
                triangles = [
                    [face.A, face.B, face.C],
                    [face.A, face.C, face.D],
                ]
            else:
                continue

            for tri in triangles:
                v0, v1, v2 = (
                    vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
                )
                area = self._triangle_area(v0, v1, v2)
                count = max(
                    min_samples_per_face,
                    int(round(area / ref_area)),
                )
                centroid = (v0 + v1 + v2) / 3.0
                samples.extend([centroid] * count)

        if not samples:
            return vertices
        return np.vstack(samples)

    def sample_points_for_pca_3d(self, geometry):
        """
        Collect area-weighted PCA samples from mesh or brep geometry.
        NOTE: Currently not used due to very long runtime
        """
        if isinstance(geometry, Rhino.Geometry.Mesh):
            return self.sample_points_area_weighted_from_mesh(geometry)

        if isinstance(geometry, Rhino.Geometry.Brep):
            mp = Rhino.Geometry.MeshingParameters.Default
            brep_meshes = Rhino.Geometry.Mesh.CreateFromBrep(geometry, mp)
            if brep_meshes:
                chunks = [
                    self.sample_points_area_weighted_from_mesh(m)
                    for m in brep_meshes
                ]
                return np.vstack(chunks)

            return np.array(
                [[p.Location.X, p.Location.Y, p.Location.Z]
                 for p in geometry.Vertices],
                dtype=np.float64,
            )

        raise RuntimeError(
            'Area-weighted 3D sampling not implemented for geometry of type '
            f'{type(geometry)}!'
        )

    def compute_obb_3d(self, points):
        """
        Compute object oriented bounding box for 3D points using PCA.
        Returns unsorted dimensions and bounding box origin.
        """
        pca = PCA(n_components=3)
        pca.fit(points)
        principal_components = pca.components_

        det = np.linalg.det(principal_components)
        if det < 0:
            principal_components[2] = -principal_components[2]

        pca_points = np.dot(points, principal_components.T)
        min_bounds = np.min(pca_points, axis=0)
        max_bounds = np.max(pca_points, axis=0)
        dimensions = max_bounds - min_bounds
        bbx_origin = (min_bounds + max_bounds) / 2.0

        return dimensions.tolist(), principal_components, bbx_origin.tolist()

    def minimum_bounding_rectangle(self, points):
        """
        Compute minimum bounding rectangle for 2D points.
        Returns rectangle corners and angle.
        """
        hull = ConvexHull(points)
        hull_points = points[hull.vertices]

        min_area = float('inf')
        best_rectangle = None
        best_angle = 0

        for i in range(len(hull_points)):
            p1 = hull_points[i]
            p2 = hull_points[(i + 1) % len(hull_points)]
            edge_vec = p2 - p1
            angle = np.arctan2(edge_vec[1], edge_vec[0])
            cos_angle = np.cos(-angle)
            sin_angle = np.sin(-angle)
            rot_matrix = np.array([[cos_angle, -sin_angle],
                                   [sin_angle, cos_angle]])
            rotated_points = np.dot(points, rot_matrix.T)

            min_x = np.min(rotated_points[:, 0])
            max_x = np.max(rotated_points[:, 0])
            min_y = np.min(rotated_points[:, 1])
            max_y = np.max(rotated_points[:, 1])
            area = (max_x - min_x) * (max_y - min_y)

            if area < min_area:
                min_area = area
                best_angle = angle
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
        Compute OBB for extrusions using minimum bounding rectangle in XY.
        Returns unsorted dimensions and bounding box origin.
        """
        points_2d = points[:, :2]
        mbr, optimal_angle = self.minimum_bounding_rectangle(points_2d)

        cos_angle = np.cos(-optimal_angle)
        sin_angle = np.sin(-optimal_angle)
        rot_matrix = np.array([
            [cos_angle, -sin_angle],
            [sin_angle, cos_angle]
        ])
        rotated_points = np.dot(points_2d, rot_matrix.T)

        min_x = np.min(rotated_points[:, 0])
        max_x = np.max(rotated_points[:, 0])
        min_y = np.min(rotated_points[:, 1])
        max_y = np.max(rotated_points[:, 1])

        x_dim = max_x - min_x
        y_dim = max_y - min_y
        bbx_center_2d = [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0]

        min_z = np.min(points[:, 2])
        max_z = np.max(points[:, 2])
        z_center = (min_z + max_z) / 2.0
        bbx_origin_2d = [bbx_center_2d[0], bbx_center_2d[1], z_center]

        if x_dim >= y_dim:
            dimensions = [x_dim, y_dim, height]
            principal_components = np.array([
                [cos_angle, -sin_angle, 0],
                [sin_angle, cos_angle, 0],
                [0, 0, 1]
            ])
        else:
            dimensions = [y_dim, x_dim, height]
            cos_angle_90 = np.cos(-optimal_angle + np.pi / 2)
            sin_angle_90 = np.sin(-optimal_angle + np.pi / 2)
            principal_components = np.array([
                [cos_angle_90, -sin_angle_90, 0],
                [sin_angle_90, cos_angle_90, 0],
                [0, 0, 1]
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

    def create_pca_transform_matrix(self, principal_components):
        """
        Create a 4x4 transformation matrix from PCA principal components.
        """
        # The principal components define the new coordinate system
        # To transform geometry TO align with this system, we need the INVERSE
        # The principal components are the new basis vectors
        # We want to rotate the geometry so it aligns with these vectors
        # This requires the inverse of the rotation matrix
        rotation_matrix = np.linalg.inv(principal_components.T)
        # Create 4x4 transformation matrix
        transform_matrix = np.eye(4)
        transform_matrix[:3, :3] = rotation_matrix
        # return results
        return transform_matrix

    def apply_pca_transform(self, geometry, principal_components):
        """
        Apply PCA transformation to geometry.
        """
        # Create transformation matrix
        transform_matrix = self.create_pca_transform_matrix(
            principal_components)
        # Convert to Rhino XForm
        xform = self.rhino_xform(transform_matrix)
        # Apply transformation
        transformed_geometry = geometry.Duplicate()
        transformed_geometry.Transform(xform)
        # return results
        return transformed_geometry

    def RunScript(self, Geometry: Rhino.Geometry.GeometryBase):
        # set up output variables
        ObjectOrientedBBX = Grasshopper.DataTree[System.Object]()
        AlignedGeometry = Grasshopper.DataTree[System.Object]()
        AlignedBBX = Grasshopper.DataTree[System.Object]()
        TranslationVector = Grasshopper.DataTree[System.Object]()
        PCAXForm = Grasshopper.DataTree[System.Object]()
        try:
            # sanitize input and abort if not present
            self.Component.Message = None
            if not Geometry:
                msg = 'Input Geometry failed to collect data!'
                self._addWarning(msg)
                return (ObjectOrientedBBX, AlignedGeometry,
                        AlignedBBX, TranslationVector, PCAXForm)
            elif not Geometry.IsValid:
                msg = 'Input Geometry is invalid!'
                self._addError(msg)
                return (ObjectOrientedBBX, AlignedGeometry,
                        AlignedBBX, TranslationVector, PCAXForm)
            # Center geometry at world origin
            (centered_geometry,
             translation_vector) = self.center_geometry_at_origin(Geometry)
            # Process geometry to extract points
            centered_points, compute_3d = self.process_geometry(
                centered_geometry
            )
            # Get Rhino translation vector
            TranslationVector = Rhino.Geometry.Vector3d(
                *translation_vector.tolist()
            )
            if compute_3d:
                # centered_points = self.sample_points_for_pca_3d(
                #     centered_geometry
                # )
                dimensions, principal_components, bbx_origin = (
                    self.compute_obb_3d(centered_points)
                )
            else:
                height = centered_geometry.PathStart.DistanceTo(
                    centered_geometry.PathEnd
                )
                dimensions, principal_components, bbx_origin = (
                    self.compute_obb_2d(centered_points, height)
                )
            # Create PCA transformation matrix and XForm
            # The principal components define the new coordinate system
            # We want to transform the geometry TO align with this system
            pca_transform_matrix = self.create_pca_transform_matrix(
                principal_components)
            PCAXForm = self.rhino_xform(pca_transform_matrix)
            # Apply PCA transformation to centered geometry
            # This will align the geometry with its principal axes
            AlignedGeometry = self.apply_pca_transform(
                centered_geometry, principal_components)
            # Create PCA-oriented bounding box
            AlignedBBX = AlignedGeometry.GetBoundingBox(True)
            # Now "transform back" the PCA-oriented bounding box
            # NOTE: we have to convert to a Rhino.Geometry.Box for the
            # correctly applying the transformation!
            ObjectOrientedBBX = Rhino.Geometry.Box(
                AlignedGeometry.GetBoundingBox(True)
            )
            _res, invPCAXForm = PCAXForm.TryGetInverse()
            if not _res:
                raise RuntimeError('Failed to get Inverse of PCA Transform!')
            ObjectOrientedBBX.Transform(invPCAXForm)
            ObjectOrientedBBX.Transform(
                Rhino.Geometry.Transform.Translation(-TranslationVector)
            )
            # return output
            return (ObjectOrientedBBX, AlignedGeometry,
                    AlignedBBX, TranslationVector, PCAXForm)
        except ValueError as e:
            msg = f'Validation error: {str(e)}'
            self._addError(msg)
        except RuntimeError as e:
            msg = f'Runtime error: {str(e)}'
            self._addError(msg)
        # Return empty results if there was an error
        return (ObjectOrientedBBX, AlignedGeometry,
                AlignedBBX, TranslationVector, PCAXForm)
