#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from sklearn.decomposition import PCA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComputePCAOrientation'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'ComputePCAOrientation'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Computes Principal Component Analysis (PCA) orientation for input '
    'geometry. Returns the object oriented bounding box obtained using PCA, '
    'aligned geometry, translation vector, and PCA transformation matrix.'
)


class CSC_ComputePCAOrientation(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251010
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

    def compute_obb_3d(self, points):
        """
        Compute object oriented bounding box for 3D points using PCA.
        Returns dimensions sorted by length (X=longest, Y=second, Z=shortest).
        """
        # Apply PCA to find principal axes
        pca = PCA(n_components=3)
        pca.fit(points)
        # Get principal components (eigenvectors)
        principal_components = pca.components_
        # Transform points to PCA space
        pca_points = np.dot(points, principal_components.T)
        # Find bounds in PCA space
        min_bounds = np.min(pca_points, axis=0)
        max_bounds = np.max(pca_points, axis=0)
        # Compute dimensions
        dimensions = max_bounds - min_bounds
        return dimensions.tolist(), principal_components

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
            # Initialize param descriptions (this has to be done in RunScript)
            self.InputParams[0].Description = (
                'Input Rhino Geometry'
            )
            # Initialize output param descriptions
            self.OutputParams[0].Description = (
                'Object oriented bounding box, obtained using PCA, '
                ' at the location of the input geometry'
            )
            self.OutputParams[1].Description = (
                'Input geometry transformed using PCA method and centered at '
                'world origin'
            )
            self.OutputParams[2].Description = (
                'Object oriented bounding box transformed using the computed '
                'PCA frame, centered at the world origin'
            )
            self.OutputParams[3].Description = (
                'Translation vector that was used to move the geometry '
                'to the world origin'
            )
            self.OutputParams[4].Description = (
                'PCA frame that was used to transform the geometry '
                'converted to a Rhino XForm.'
            )
            # sanitize input and abort if not present
            self.Component.Message = None
            if not Geometry:
                msg = 'Input Geometry failed to collect data!'
                self._addWarning(msg)
                self.Component.Message = msg
                return (ObjectOrientedBBX, AlignedGeometry,
                        AlignedBBX, TranslationVector, PCAXForm)
            elif not Geometry.IsValid:
                msg = 'Input Geometry is invalid!'
                self._addError(msg)
                self.Component.Message = msg
                return (ObjectOrientedBBX, AlignedGeometry,
                        AlignedBBX, TranslationVector, PCAXForm)
            # Process geometry to extract points
            points, compute_3d = self.process_geometry(Geometry)
            # Center geometry at world origin
            (centered_geometry,
             translation_vector) = self.center_geometry_at_origin(Geometry)
            # Get Rhino translation vector
            TranslationVector = Rhino.Geometry.Vector3d(
                *translation_vector.tolist()
            )
            # Centered points
            centered_points = points - translation_vector
            # Compute object oriented bounding box and PCA transformation
            dimensions, principal_components = (
                self.compute_obb_3d(centered_points)
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
            self.Component.Message = msg
        except RuntimeError as e:
            msg = f'Runtime error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
        # Return empty results if there was an error
        return (ObjectOrientedBBX, AlignedGeometry,
                AlignedBBX, TranslationVector, PCAXForm)
