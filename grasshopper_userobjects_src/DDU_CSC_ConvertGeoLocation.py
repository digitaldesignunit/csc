#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

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

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state, waits_for_data
except ImportError:
    ensure_outputs = set_state = waits_for_data = None

OUTPUTS = [
    ('Lat', 'Lat',
     'Latitude component of the input string as float.'),
    ('Lon', 'Lon',
     'Longitude component of the input string as float.'),
    ('Vec', 'Vec',
     'Vector with lat/lon as X/Y.'),
]


def empty_outputs():
    """What RunScript returns when it stops early or has no result: an empty
    Grasshopper tree per output (never '' or None)."""
    if not OUTPUTS:
        return None
    trees = tuple(Grasshopper.DataTree[System.Object]() for _ in OUTPUTS)
    return trees[0] if len(trees) == 1 else trees


def null_outputs():
    """One null per output: an item of an item-access component that has no
    result keeps its slot (decision 8.186)."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_ConvertGeoLocation(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261102
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _no_result(self, *ports):
        """The result of an iteration without one (decision 8.186): empty
        outputs when the inputs in ``ports`` carry no data at all (the
        component waits for data; no ports: a list or tree input is empty),
        else a null in the slot of this item, so the outputs stay one to one
        with the input list."""
        if not ports or (waits_for_data is not None
                         and waits_for_data(self, ports)):
            return empty_outputs()
        return null_outputs()

    def _stop(self):
        """True when RunScript has to return early: the outputs were just
        updated (says why)."""
        if self._outputs_note:
            self._addRemark(self._outputs_note)
        return not self._outputs_ready

    def _check_outputs(self):
        """Make the outputs match OUTPUTS before the script runs (8.112)."""
        self._outputs_ready, self._outputs_note = True, None
        if ensure_outputs is None:
            self._outputs_note = (
                'output check skipped: CSC library not installed')
            return
        status = ensure_outputs(self.Component, OUTPUTS)
        self._outputs_ready, self._outputs_note = status.ready, status.remark

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Latitude, Longitude string, e.g. "12.1231321, 9.1231231312" '
        )
        # Initialize output param descriptions
        self._check_outputs()

    def RunScript(self, LatLonString: str):
        if self._stop():
            return empty_outputs()
        Lat = Grasshopper.DataTree[object]()
        Lon = Grasshopper.DataTree[object]()
        Vec = Grasshopper.DataTree[object]()
        _Results = [Lat, Lon, Vec]
        if not LatLonString:
            msg = 'Parameter LatLonString failed to collect data!'
            self._addWarning(msg)
            return self._no_result('LatLonString')
        parts = LatLonString.split(',')
        if len(parts) > 2:
            msg = f'Splitting of Lat/Lon string failed! Raw result is {parts}...'
            self._addError(msg)
            return null_outputs()
        Lat = float(parts[0].strip())
        Lon = float(parts[1].strip())
        Vec = Rhino.Geometry.Vector3d(Lat, Lon, 0)
        _Results = [Lat, Lon, Vec]
        return _Results
