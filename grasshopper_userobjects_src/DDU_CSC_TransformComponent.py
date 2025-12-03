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

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'TransformComponent'  # NOQA
ghenv.Component.NickName = 'TransformComponent'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Applies a Rhino transformation to the iframe (insertion frame) of a '
    'component\'s JSON data. Updates the component\'s coordinate system '
    'based on the applied transformation.'
)


class CSC_TransformComponent(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Component data as JSON string from previous components.'
        )
        self.InputParams[1].Description = (
            'Rhino transform to apply to the component insertion frame.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Transformed component data as JSON string!'
        )

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
