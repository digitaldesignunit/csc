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

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ConvertGeoLocation'  # NOQA
ghenv.Component.NickName = 'ConvertGeoLocation'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '6 Data Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Converts a latitude, longitude string (i.e. from Google Maps) '
    'to its individual components. Example input: "12.1231321, 9.1231231312" '
    'Returns the location as individual numbers and as vector.'
)


class CSC_ConvertGeoLocation(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260203
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
            'Latitude, Longitude string, e.g. "12.1231321, 9.1231231312" '
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Latitude component of the input string as float.'
        )
        self.OutputParams[1+i].Description = (
            'Longitude component of the input string as float.'
        )
        self.OutputParams[2+i].Description = (
            'Vector with lat/lon as X/Y.'
        )

    def RunScript(self, LatLonString: str):
        Lat = Grasshopper.DataTree[object]()
        Lon = Grasshopper.DataTree[object]()
        Vec = Grasshopper.DataTree[object]()
        _Results = [Lat, Lon, Vec]
        if not LatLonString:
            msg = 'Parameter LatLonString failed to collect data!'
            self._addWarning(msg)
            return _Results
        parts = LatLonString.split(',')
        if len(parts) > 2:
            msg = f'Splitting of Lat/Lon string failed! Raw result is {parts}...'
            self._addError(msg)
            return _Results
        Lat = float(parts[0].strip())
        Lon = float(parts[1].strip())
        Vec = Rhino.Geometry.Vector3d(Lat, Lon, 0)
        _Results = [Lat, Lon, Vec]
        return _Results
