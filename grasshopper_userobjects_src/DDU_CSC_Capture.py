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
ghenv.Component.Name = 'Capture'  # NOQA
ghenv.Component.NickName = 'Capture'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds how the geometry of a state was recorded (method, device, '
    'software, coordinate system, markers, fixtures) as JSON for '
    'CreateComponentSnapshot / CreateComponentIdentity. Markers and '
    'fixtures (a scanning rig) are never part of the geometry of the '
    'component itself.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261102'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, capture)  # NOQA
    from csc_gh.messages import (waits_for_data)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261102 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Capture', 'Capture',
     'Capture JSON (a fragment of the API payload)'),
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


class CSC_Capture(Grasshopper.Kernel.GH_ScriptInstance):
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
            'photogrammetry, lidar, structured_light or manual'
        )
        self.InputParams[1].Description = (
            'Scanner or camera'
        )
        self.InputParams[2].Description = (
            'Software that made the geometry'
        )
        self.InputParams[3].Description = (
            'When it was captured (2024-05-03, ...)'
        )
        self.InputParams[4].Description = (
            'Free text'
        )
        self.InputParams[5].Description = (
            'Name of the coordinate system the geometry is in, e.g. the gripper '
            'marker plane'
        )
        self.InputParams[6].Description = (
            'Description of that coordinate system'
        )
        self.InputParams[7].Description = (
            'Marker points'
        )
        self.InputParams[8].Description = (
            'One label per marker point'
        )
        self.InputParams[9].Description = (
            'rig or component, one per marker point (default component)'
        )
        self.InputParams[10].Description = (
            'Fixtures as label|file name'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Method: str,
            Device: str,
            Software: str,
            CapturedAt: str,
            Notes: str,
            CoordinateSystem: str,
            CoordinateSystemNote: str,
            MarkerPoints: list[Rhino.Geometry.Point3d],
            MarkerLabels: list[object],
            MarkerRoles: list[object],
            Fixtures: list[object]):
        if self._stop():
            return empty_outputs()
        Capture = empty_outputs()
        try:
            points = list(MarkerPoints or [])
            labels = list(MarkerLabels or [])
            roles = list(MarkerRoles or [])
            if points and len(labels) not in (len(points),):
                raise BuildError('give one MarkerLabel per marker point '
                                 f'({len(points)} points, {len(labels)} labels)')
            if roles and len(roles) not in (1, len(points)):
                raise BuildError('give one MarkerRole for all points or one per '
                                 'point')
            marker_items = []
            for index, point in enumerate(points):
                role = (roles[0] if len(roles) == 1 else roles[index]) \
                    if roles else None
                marker_items.append((labels[index], role,
                                     (point.X, point.Y, point.Z)))
            fixture_items = []
            for item in Fixtures or []:
                label, _, file_name = str(item).partition('|')
                fixture_items.append((label, file_name))
            fragment = capture(Method, Device, Software, CapturedAt, Notes,
                               CoordinateSystem, CoordinateSystemNote, marker_items,
                               fixture_items)
            Capture = json.dumps(fragment)
            return Capture
        except BuildError as error:
            self._addError(str(error))
            return null_outputs()
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
            return null_outputs()
        return Capture
