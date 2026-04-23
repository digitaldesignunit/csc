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

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ExtrusionProfile'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'ExtrusionProfile'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Extract the profile curves of an Extrusion.'
)


class CSC_ExtrusionProfile(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260423
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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
            'A Rhino.Geometry.Extrusion to extract '
            'the profile curve from'
        )
        self.InputParams[1].Description = (
            'Index of the profile curve to extract. '
            'The outer profile has index 0.'
        )
        self.InputParams[2].Description = (
            'A relative parameter controlling which profile is returned. '
            '0 = bottom profile and 1 = top profile.'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'The extracted profile curve.'
        )

    def RunScript(self,
            ExtrusionGeometry: Rhino.Geometry.Extrusion,
            ProfileIndex: int,
            ProfileParameter: float):
        # init outputs
        ProfileCurve = Grasshopper.DataTree[System.Object]()
        # defaults
        if not ExtrusionGeometry:
            self._addWarning('Input Parameter ExtrusionGeometry failed to colect data.')
            self.Component.Message = (
                f'No Profile extracted.')
            return ProfileCurve
        if ProfileIndex is None:
            ProfileIndex = 0
        elif ProfileIndex < ExtrusionGeometry.ProfileCount - 1:
            self._addError('Input Parameter ProfileIndex is out of range!')
            return ProfileCurve
        elif ProfileIndex > ExtrusionGeometry.ProfileCount - 1:
            self._addError('Input Parameter ProfileIndex is out of range!')
            return ProfileCurve
        if ProfileParameter is None:
            ProfileParameter = 0.5
        elif ProfileParameter < 0:
            self._addWarning('ProfileParameter was set to 0.0! Must be >= 0.0 and <= 1.0!')
            ProfileParameter = 0.0
        elif ProfileParameter > 1:
            self._addWarning('ProfileParameter was set to 1.0! Must be >= 0.0 and <= 1.0!')
            ProfileParameter = 0.0
        # finally extract profile curve
        ProfileCurve = ExtrusionGeometry.Profile3d(0, 0.5)
        self.Component.Message = (
            f'Extrusion Profile at i = {ProfileIndex} | s = {ProfileParameter}')
        # return results
        return ProfileCurve

