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
ghenv.Component.Name = 'ApplyPCAFrame'  # NOQA
ghenv.Component.NickName = 'ApplyPCAFrame'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Applies an inverse PCA transformation to align geometry or compose data '
    'with the world coordinate system. Takes either compose JSON '
    '({identity, snapshot}) or Rhino geometry and transforms it to align '
    'with the world XY plane using the snapshot pca_frame.'
)


class CSC_ApplyPCAFrame(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Compose JSON string ({identity, snapshot}) or geometry objects '
            'with the \'csc_component\' compose userdata'
        )
        # Set "No type hint"
        self.InputParams[0].TypeHints.Select(System.Object)
        self.Component.VariableParameterMaintenance()
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Transformed compose JSON (if input was JSON) or '
            'transformed geometry with updated compose userdata '
            '(if input was geometry)'
        )

    def PlaneToFrameDict(self, plane: Rhino.Geometry.Plane) -> dict:
        """
        Convert a Rhino plane to a frame dictionary format.

        Args:
            plane: Rhino.Geometry.Plane object

        Returns:
            Dictionary with 'o', 'x', 'y', 'z' keys containing coordinate lists
        """
        iframe = {
            'o': [plane.OriginX, plane.OriginY, plane.OriginZ],
            'x': [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
            'y': [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
            'z': [plane.ZAxis.X, plane.ZAxis.Y, plane.ZAxis.Z]
        }
        return iframe

    def FrameDictToPlane(self, frame_dict: dict) -> Rhino.Geometry.Plane:
        """
        Convert a frame dictionary to a Rhino plane.

        Args:
            frame_dict: Dictionary with 'o', 'x', 'y' keys

        Returns:
            Rhino.Geometry.Plane object
        """
        origin = Rhino.Geometry.Point3d(*frame_dict.get('o', [0, 0, 0]))
        x_axis = Rhino.Geometry.Vector3d(*frame_dict.get('x', [1, 0, 0]))
        y_axis = Rhino.Geometry.Vector3d(*frame_dict.get('y', [0, 1, 0]))
        return Rhino.Geometry.Plane(origin, x_axis, y_axis)

    def extract_component_data_from_geometry(self, geometry):
        """
        Extract compose data ({identity, snapshot}) from geometry userdata.

        Args:
            geometry: Rhino geometry object with userdata

        Returns:
            Compose dictionary or None
        """
        try:
            userdata = geometry.GetUserString('csc_component')
            if userdata:
                return json.loads(userdata)
        except Exception as e:
            self._addWarning(f'Could not extract compose data: {str(e)}')
        return None

    def apply_pca_transform_to_geometry(self, geometry, pca_transform):
        """
        Apply PCA transform to geometry object.

        Args:
            geometry: Rhino geometry object
            pca_transform: Rhino transform

        Returns:
            Transformed geometry object
        """
        try:
            if hasattr(geometry, 'Transform'):
                geometry.Transform(pca_transform)
            elif hasattr(geometry, 'Duplicate'):
                # For objects that don't support Transform directly
                transformed_geometry = geometry.Duplicate()
                transformed_geometry.Transform(pca_transform)
                return transformed_geometry
        except Exception as e:
            self._addWarning(f'Could not transform geometry: {str(e)}')
        return geometry

    def RunScript(self, Input):
        # Set up output tree
        Output = Grasshopper.DataTree[System.Object]()

        # Validate input
        if not Input:
            msg = 'Input failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return Output

        try:
            self.Component.Message = 'Processing input...'

            # Determine input type and extract compose data
            compose = None
            geometry_objects = []
            input_is_geometry = False

            # Check if input is a compose JSON string
            if isinstance(Input, str):
                try:
                    compose = json.loads(Input)
                    self._addRemark('Input detected as compose JSON')
                except json.JSONDecodeError:
                    msg = 'Input is not valid compose JSON!'
                    self._addError(msg)
                    self.Component.Message = msg
                    return Output
            else:
                # Input is geometry - extract compose data from userdata
                input_is_geometry = True
                geometry_objects = (Input if isinstance(Input, list)
                                    else [Input])

                # Try to extract compose data from first geometry object
                compose = self.extract_component_data_from_geometry(
                    geometry_objects[0])
                if not compose:
                    msg = ('Could not extract compose data from '
                           'geometry userdata!')
                    self._addError(msg)
                    self.Component.Message = msg
                    return Output

                self._addRemark('Input detected as geometry with '
                                'compose userdata')

            # Resolve the snapshot (holds pca_frame + iframe)
            snapshot = (compose.get('snapshot')
                        if isinstance(compose, dict) else None)
            if not isinstance(snapshot, dict):
                msg = 'Compose JSON has no snapshot!'
                self._addError(msg)
                self.Component.Message = msg
                return Output

            # Extract PCA frame from the snapshot
            try:
                pca_frame = snapshot['pca_frame']
                pca_plane = self.FrameDictToPlane(pca_frame)

                # Create inverse PCA transform (from PCA space to world space)
                pca_transform = Rhino.Geometry.Transform.PlaneToPlane(
                    pca_plane, Rhino.Geometry.Plane.WorldXY)

                self._addRemark('PCA frame found, creating inverse transform')
            except KeyError:
                msg = 'Snapshot does not contain pca_frame!'
                self._addError(msg)
                self.Component.Message = msg
                return Output

            # Default identity frame
            DEFAULT_FRAME = {
                'o': [0.0, 0.0, 0.0],
                'x': [1.0, 0.0, 0.0],
                'y': [0.0, 1.0, 0.0],
                'z': [0.0, 0.0, 1.0]
            }

            # Build a transformed compose (copy identity + snapshot shallowly;
            # the iframe key is replaced wholesale, never mutated in place)
            transformed_compose = {
                'identity': compose.get('identity'),
                'snapshot': dict(snapshot),
            }
            transformed_snapshot = transformed_compose['snapshot']

            # Update iframe to preserve translation but update orientation
            try:
                # Get existing iframe or create default
                original_iframe = transformed_snapshot.get(
                    'iframe', DEFAULT_FRAME)

                # Convert iframe to plane
                iframe_plane = self.FrameDictToPlane(original_iframe)

                # Apply the SAME transformations to the iframe plane that we
                # apply to the geometry
                # For JSON input, just apply inverse PCA
                if not input_is_geometry:
                    iframe_plane.Transform(pca_transform)
                    transformed_snapshot['iframe'] = (
                        self.PlaneToFrameDict(iframe_plane))

                self._addRemark('Updated iframe with PCA orientation')
            except Exception as e:
                self._addWarning(f'Could not update iframe: {str(e)}')

            # Handle output based on input type
            if input_is_geometry:
                # For geometry input, we need to:
                # 1. Transform back to original space (inverse iframe)
                # 2. Apply PCA transformation
                # 3. Apply iframe transformation again
                try:
                    # Get the original iframe
                    original_iframe = snapshot.get('iframe', DEFAULT_FRAME)

                    # Convert iframe to plane
                    iframe_plane = self.FrameDictToPlane(original_iframe)

                    # Create iframe transform (from original space to world
                    # space)
                    iframe_transform = (
                        Rhino.Geometry.Transform.PlaneToPlane(
                            Rhino.Geometry.Plane.WorldXY, iframe_plane))

                    # Create inverse iframe transform (from world space to
                    # original space)
                    inverse_iframe_transform = (
                        Rhino.Geometry.Transform.PlaneToPlane(
                            iframe_plane, Rhino.Geometry.Plane.WorldXY))

                    # Apply the SAME transformations to the iframe plane that
                    # we apply to the geometry
                    compound_iframe_plane = self.FrameDictToPlane(
                        original_iframe)
                    compound_iframe_plane.Transform(inverse_iframe_transform)
                    compound_iframe_plane.Transform(pca_transform)

                    # Update the snapshot with the transformed iframe
                    transformed_snapshot['iframe'] = (
                        self.PlaneToFrameDict(compound_iframe_plane))

                    # Transform geometry objects: inverse iframe -> PCA ->
                    # iframe
                    for geometry in geometry_objects:
                        # Step 1: Transform back to original space
                        geometry.Transform(inverse_iframe_transform)

                        # Step 2: Apply PCA transformation
                        transformed_geometry = (
                            self.apply_pca_transform_to_geometry(
                                geometry, pca_transform))

                        # Step 3: Apply iframe transformation again
                        transformed_geometry.Transform(iframe_transform)

                        # Update userdata with transformed compose data
                        if hasattr(transformed_geometry, 'SetUserString'):
                            transformed_geometry.SetUserString(
                                'csc_component',
                                json.dumps(transformed_compose))
                        Output = transformed_geometry

                    self._addRemark(f'Transformed {len(geometry_objects)} '
                                    'geometry objects with PCA and iframe')
                except Exception as e:
                    self._addWarning(
                        f'Could not apply iframe transform: {str(e)}')
                    # Fallback to just PCA transformation
                    for geometry in geometry_objects:
                        transformed_geometry = (
                            self.apply_pca_transform_to_geometry(
                                geometry, pca_transform))

                        if hasattr(transformed_geometry, 'SetUserString'):
                            transformed_geometry.SetUserString(
                                'csc_component',
                                json.dumps(transformed_compose))

                        Output = transformed_geometry
                    self._addRemark(f'Transformed {len(geometry_objects)} '
                                    'geometry objects with PCA only')
            else:
                # Output transformed compose data as JSON
                Output = json.dumps(transformed_compose)
                self._addRemark('Output transformed compose JSON')

            # Update success message
            if input_is_geometry:
                self.Component.Message = (
                    f'Successfully applied PCA frame to '
                    f'{len(geometry_objects)} geometry objects'
                )
            else:
                self.Component.Message = ('Successfully applied PCA frame '
                                          'to compose JSON')

            return Output

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return Output
