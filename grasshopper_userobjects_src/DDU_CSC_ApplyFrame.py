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
    'catalog and uses the frame the server stored for the state. An element '
    'without a frame (a design target, geometry not in the catalog) gets '
    'the same frame computed locally with the rules of the server. The '
    'Frame output is the frame that was used, in the stored coordinates '
    '(where the element sat before the move), not the frame of the moved '
    'element: DisassembleComponent gives the frame where the moved element '
    'sits.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261102'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, text)  # NOQA
    from csc_gh.read import (canonical_placement, frame_ok, load_passport, parts, passport_points, placement_of, with_placement)  # NOQA
    from csc_gh.frame import (compute_frame)  # NOQA
    from csc_gh.rhino import (canonical_transform, geometry_points, placement_transform, plane_from_frame)  # NOQA
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
    ('Output', 'Output',
     'The component passport JSON with its client-side csc_placement set, or the geometry moved to its canonical orientation'),
    ('Frame', 'Frame',
     'The frame that was used, a plane in the stored coordinates of the element (where it sat before the move), not the frame of the moved element. For the frame where the moved element sits, take the Frame output of DisassembleComponent, which applies csc_placement'),
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


class CSC_ApplyFrame(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261102
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
        Output, Frame = empty_outputs()
        if Input is None or (isinstance(Input, str) and not Input.strip()):
            msg = 'Input failed to collect data!'
            self._addWarning(msg)
            return self._no_result('Input')
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
            return null_outputs()
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
            return null_outputs()
        return Output, Frame
