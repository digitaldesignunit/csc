#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SnapshotMetadata'  # NOQA
ghenv.Component.NickName = 'SnapshotMetadata'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds the fields of one recorded state (name, fragment, quantity, '
    'colour, location, notes, start date) as JSON for '
    'CreateComponentSnapshot / CreateComponentIdentity. Shape class and '
    'complexity are derived by the server; set them only to override.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, snapshot_metadata)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('SnapshotMetadata', 'SnapshotMetadata',
     'SnapshotMetadata JSON (a fragment of the API payload)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_SnapshotMetadata(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        self.Component = ghenv.Component  # NOQA
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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _stop(self):
        """True when RunScript has to return early: the library is missing or
        too old, or the outputs were just updated (says why)."""
        if LIBRARY_PROBLEM:
            self._addError(LIBRARY_PROBLEM)
            return True
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
        self.InputParams[0].Description = (
            'Name of the component (empty: its catalog number)'
        )
        self.InputParams[1].Description = (
            'The piece is a fragment of a bigger one'
        )
        self.InputParams[2].Description = (
            'Number of identical pieces (default 1)'
        )
        self.InputParams[3].Description = (
            'Colour of the piece'
        )
        self.InputParams[4].Description = (
            'Latitude (X) and longitude (Y)'
        )
        self.InputParams[5].Description = (
            'Free text (up to 5000 characters)'
        )
        self.InputParams[6].Description = (
            'When this state started (empty: now; 2024-05-03, ...)'
        )
        self.InputParams[7].Description = (
            'Override: linear, planar, block, irregular or composite'
        )
        self.InputParams[8].Description = (
            'Override: 0 to 3'
        )
        self.InputParams[9].Description = (
            'exact, day, month, year or unknown (empty: from '
            'EffectiveFrom)'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Name: str,
            Fragment: bool,
            Quantity: int,
            Color: System.Drawing.Color,
            Location: Rhino.Geometry.Vector3d,
            Notes: str,
            EffectiveFrom: str,
            ShapeClass: str,
            Complexity: int,
            EffectiveFromPrecision: str):
        if self._stop():
            return empty_outputs()
        SnapshotMetadata = ''
        if not EffectiveFromPrecision or EffectiveFromPrecision == '':
            EffectiveFromPrecision = None
        try:
            rgb_value = None
            if Color is not None:
                rgb_value = [Color.R, Color.G, Color.B]
            lat = lon = None
            if Location is not None:
                lat, lon = Location.X, Location.Y
            fragment = snapshot_metadata(
                Name, Fragment, Quantity, rgb_value, lat, lon, Notes, EffectiveFrom,
                EffectiveFromPrecision, ShapeClass, Complexity)
            SnapshotMetadata = json.dumps(fragment)
            return SnapshotMetadata
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return SnapshotMetadata
