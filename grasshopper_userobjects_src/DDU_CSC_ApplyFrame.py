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
ghenv.Component.Name = 'ApplyFrame'  # NOQA
ghenv.Component.NickName = 'ApplyFrame'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Moves a component to its canonical orientation: longest side along X, '
    'middle along Y, shortest along Z (a column stands), centre at the '
    'origin. Takes component passport JSON or Rhino geometry fetched from the '
    'catalog and uses the frame the server stored for the state. A piece '
    'without a frame (a design target, geometry not in the catalog) gets '
    'the same frame computed locally with the rules of the server.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, text)  # NOQA
    from csc_gh.read import (canonical_placement, frame_ok, load_passport, parts, passport_points, placement_of, with_placement)  # NOQA
    from csc_gh.frame import (compute_frame)  # NOQA
    from csc_gh.rhino import (canonical_transform, geometry_points, placement_transform, plane_from_frame)  # NOQA
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
    ('Output', 'Output',
     'The component passport JSON with its client-side csc_placement set, or the geometry moved to its canonical orientation'),
    ('Frame', 'Frame',
     'The frame used: a plane in the stored coordinates of the piece'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_ApplyFrame(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Component passport JSON ({identity, snapshots[]}) or Rhino geometry '
            'carrying one (from the Fetch components), or any geometry'
        )
        self.InputParams[1].Description = (
            'Original function (e.g. IfcColumn) for a frame computed '
            'locally; empty: taken from the component passport'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def passport_of(self, geometry):
        """The passport carried by a geometry's csc_component user text."""
        try:
            value = geometry.GetUserString('csc_component')
        except Exception:
            return None
        return load_passport(value) if value else None

    def frame_for(self, passport, points, original_function):
        """The stored frame of the passport's state, else a local one."""
        identity, snapshot = parts(passport) if passport else (None, None)
        frame = (snapshot or {}).get('frame')
        if frame_ok(frame):
            return frame
        function = text(original_function) or (identity or {}).get(
            'original_function')
        if points is None or len(points) < 4:
            raise BuildError('no frame in the component passport and not enough '
                             'geometry to compute one')
        result = compute_frame(points, function)
        self._addRemark(
            'No frame in the component passport: computed locally '
            f'(frame version {result["version"]}, original function '
            f'{function or "unknown"}).')
        return result['frame']

    def RunScript(self, Input, OriginalFunction: str):
        if self._stop():
            return empty_outputs()
        Output = None
        Frame = None
        if Input is None:
            msg = 'Input failed to collect data!'
            self._addWarning(msg)
            return Output, Frame
        try:
            if isinstance(Input, str):
                passport = load_passport(Input)
                if passport is None:
                    raise BuildError('Input is not component passport JSON')
                _, snapshot = parts(passport)
                points = passport_points(snapshot)
                frame = self.frame_for(passport, points, OriginalFunction)
                Output = json.dumps(with_placement(
                    passport, canonical_placement(frame)))
                Frame = plane_from_frame(frame)
                return Output, Frame

            geometry = Input.Duplicate()
            passport = self.passport_of(Input)
            points = None
            if not (passport and frame_ok(
                    (parts(passport)[1] or {}).get('frame'))):
                points = geometry_points([Input])
            frame = self.frame_for(passport, points, OriginalFunction)
            # undo a client-side placement first: stored -> canonical
            if passport and placement_of(passport):
                placed = placement_transform(placement_of(passport))
                ok, back = placed.TryGetInverse()
                if ok:
                    geometry.Transform(back)
            geometry.Transform(canonical_transform(frame))
            if passport:
                geometry.SetUserString('csc_component', json.dumps(
                    with_placement(passport, canonical_placement(frame))))
            Output = geometry
            Frame = plane_from_frame(frame)
            return Output, Frame
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return Output, Frame
