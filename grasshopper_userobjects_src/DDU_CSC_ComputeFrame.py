#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC_MATCH
# r: charset_normalizer
# r: numpy==2.0.2
# r: scipy==1.13.1
# r: trimesh==4.12.2
# r: networkx==3.2.1
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'ComputeFrame'  # NOQA
ghenv.Component.NickName = 'ComputeFrame'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Computes the frame of a piece offline, with the rules of the server: '
    'the minimum-volume oriented box of its points, longest side along X, '
    'middle along Y, shortest along Z (an IfcColumn at least twice as long '
    'as wide stands), signs and ties chosen closest to the axes you give, '
    'never upside down. A piece gets the same frame here as in the catalog '
    '(tests keep the two in step).'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, text)  # NOQA
    from csc_gh.frame import (compute_frame)  # NOQA
    from csc_gh.rhino import (canonical_transform, geometry_points, plane_from_frame)  # NOQA
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
    ('Frame', 'Frame',
     'The frame as a plane (centre of the box, axes x, y, z)'),
    ('Box', 'Box',
     'The oriented box of the piece'),
    ('Extents', 'Extents',
     'Extents of the box along X, Y and Z'),
    ('Transform', 'Transform',
     'Transform from the geometry as given to its canonical orientation (frame to world plane)'),
    ('FrameJSON', 'FrameJSON',
     'Frame JSON ({frame, bbx, version}), as the catalog stores it'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_ComputeFrame(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261005
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

    def __init__(self):
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
            'The geometry of one piece: meshes, point clouds, breps, '
            'extrusions (their vertices are used)'
        )
        self.InputParams[1].Description = (
            'Original function, e.g. IfcColumn (empty: not a column)'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Geometry: list[Rhino.Geometry.GeometryBase],
            OriginalFunction: str):
        if self._stop():
            return empty_outputs()
        Frame = None
        Box = None
        Extents = []
        Transform = None
        FrameJSON = ''
        try:
            items = [g for g in (Geometry or []) if g is not None]
            if not items:
                raise BuildError('Input Geometry failed to collect data')
            points = geometry_points(items)
            result = compute_frame(points, text(OriginalFunction))
            frame = result['frame']
            Frame = plane_from_frame(frame)
            sx, sy, sz = result['bbx']
            Box = Rhino.Geometry.Box(
                Frame, Rhino.Geometry.Interval(-sx / 2, sx / 2),
                Rhino.Geometry.Interval(-sy / 2, sy / 2),
                Rhino.Geometry.Interval(-sz / 2, sz / 2))
            Extents = [sx, sy, sz]
            Transform = canonical_transform(frame)
            FrameJSON = json.dumps({'frame': frame, 'bbx': list(result['bbx']),
                                    'version': result['version']})
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return Frame, Box, Extents, Transform, FrameJSON
