# -*- coding: utf-8 -*-
#! python3
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
import json

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'TransformComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'TransformComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Applies a Rhino transformation to the iframe (insertion frame) of a '
    'component\'s JSON data. Updates the component\'s coordinate system '
    'based on the applied transformation.'
)


class CSC_TransformComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def PlaneToFrameDict(self, plane: Rhino.Geometry.Plane) -> dict:
        """
        Convert a Rhino plane to a frame dictionary format.

        This method converts the plane's origin and axis vectors to the format
        expected by the component system for insertion frames.

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

    def RunScript(self, ComponentData: str, XForm: Rhino.Geometry.Transform):
        """
        Main execution method for transforming component insertion frames.

        This method takes a component JSON string and a Rhino transform,
        applies the transform to the component's insertion frame, and
        returns the updated component data as a JSON string.

        Args:
            ComponentData: JSON string containing component data
            XForm: Rhino transform to apply to the insertion frame

        Returns:
            JSON string of the transformed component data
        """
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Component data as JSON string from previous components.'
        )
        self.InputParams[1].Description = (
            'Rhino transform to apply to the component insertion frame.'
        )

        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'Transformed component data as JSON string'
        )

        # set up output trees and results tuple
        XComponentData = System.Collections.Generic.List[System.Object]()

        # Validate input parameters
        if not ComponentData:
            msg = 'Input ComponentData failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return XComponentData

        if not XForm:
            msg = 'Input XForm failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return XComponentData

        try:
            # Load and parse component JSON data
            jcomp = json.loads(ComponentData)

            # Process insertion frame
            try:
                # Try to extract existing insertion frame from component
                iframe = jcomp['iframe']
                iplane = Rhino.Geometry.Plane(
                    Rhino.Geometry.Point3d(*iframe['o']),
                    Rhino.Geometry.Vector3d(*iframe['x']),
                    Rhino.Geometry.Vector3d(*iframe['y']),
                )
                self._addRemark(
                    'Using existing insertion frame from component'
                )
            except KeyError:
                # If there is no insertion frame,
                # create world XY plane as default
                iplane = Rhino.Geometry.Plane.WorldXY
                self._addRemark(
                    'No insertion frame found, using WorldXY plane'
                )

            # Apply the input transform to the insertion frame plane
            iplane.Transform(XForm)

            # Replace the insertion frame in the component data
            # with the transformed one
            jcomp['iframe'] = self.PlaneToFrameDict(iplane)

            # Convert back to JSON string for output
            XComponentData = json.dumps(jcomp)

            # Update component message to indicate success
            self.Component.Message = (
                'Component insertion frame transformed successfully'
            )
            self._addRemark(
                'Successfully transformed component insertion frame'
            )

            return XComponentData

        except json.JSONDecodeError as e:
            msg = f'Failed to parse component JSON data: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return XComponentData

        except Exception as e:
            msg = f'Unexpected error during transformation: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return XComponentData
