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
ghenv.Component.Name = 'Origin'  # NOQA
ghenv.Component.NickName = 'Origin'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds the origin of a component, how it entered circulation '
    '(deinstallation, demolition, offcut, surplus or unknown), as JSON '
    'for IdentityMetadata. Dates: 2024, 2024-05, 2024-05-03 or '
    '2024-05-03T14:30:00Z; the precision follows the text. Planned marks '
    'a piece that is still in place (not yet deinstalled), At is then the '
    'planned date or empty.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005a'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, origin)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261005a too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Origin', 'Origin',
     'Origin JSON (a fragment of the API payload)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) == 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_Origin(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005a
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
            'deinstallation, demolition, offcut, surplus or unknown'
        )
        self.InputParams[1].Description = (
            'When the piece entered circulation (2024, 2024-05, ...)'
        )
        self.InputParams[2].Description = (
            'exact, day, month, year or unknown (empty: from At)'
        )
        self.InputParams[3].Description = (
            'Name of the place, e.g. a building or site'
        )
        self.InputParams[4].Description = (
            'Address of the place'
        )
        self.InputParams[5].Description = (
            'Latitude (X) and longitude (Y) of the place'
        )
        self.InputParams[6].Description = (
            'Name of the construction work the piece came from (deinstallation '
            '/ demolition only)'
        )
        self.InputParams[7].Description = (
            'Year the work was built'
        )
        self.InputParams[8].Description = (
            'Use of the work'
        )
        self.InputParams[9].Description = (
            'monolithic, prefabricated, mixed or unknown'
        )
        self.InputParams[10].Description = (
            'How the piece was recovered'
        )
        self.InputParams[11].Description = (
            'Actor JSON of who did it (from Actor)'
        )
        self.InputParams[12].Description = (
            'Free text'
        )
        self.InputParams[13].Description = (
            'Where in the construction work the piece sat, e.g. a floor '
            'or an axis (deinstallation / demolition only)'
        )
        if len(self.InputParams) > 14:      # an instance from before Planned
            self.InputParams[14].Description = (
                'True while the piece is still in place: identified in its '
                'works, not yet deinstalled (deinstallation / demolition '
                'only). At is then the planned date, or empty'
            )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Kind: str,
            At: str,
            AtPrecision: str,
            PlaceName: str,
            PlaceAddress: str,
            PlaceLocation: Rhino.Geometry.Vector3d,
            WorkName: str,
            WorkYear: str,
            WorkUse: str,
            WorkMethod: str,
            Method: str,
            PerformedBy: list[object],
            Notes: str,
            PositionInWork: str,
            Planned: bool):
        if self._stop():
            return empty_outputs()
        Origin = ''
        if not PositionInWork or PositionInWork == '':
            PositionInWork = None
        try:
            lat = lon = None
            if PlaceLocation is not None:
                lat, lon = PlaceLocation.X, PlaceLocation.Y
            fragment = origin(Kind, At, AtPrecision, PlaceName, PlaceAddress, lat,
                              lon, WorkName, WorkYear, WorkUse, WorkMethod, Method,
                              list(PerformedBy or []), Notes,
                              PositionInWork, bool(Planned))
            Origin = json.dumps(fragment)
            return Origin
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            self._addError(f'Unexpected error: {error}')
        return Origin
