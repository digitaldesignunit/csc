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
ghenv.Component.Name = 'ReinforcementLayout'  # NOQA
ghenv.Component.NickName = 'ReinforcementLayout'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '7 Geometry Tools'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds one evidence record of method reinforcement_layout from bar '
    'centrelines (curves), steel grades and diameters: where the '
    'reinforcement of a component lies, known from a drawing, a scan or an '
    'exposed bar. A layout belongs to one version of the component: its '
    'curves are in the stored coordinates (millimetres) of that version, '
    'named by SnapshotID. Curves drawn on an element that was moved (ApplyFrame, '
    'TransformComponent) need the ComponentPassport of that element: its '
    'placement is undone and its snapshot is used. Document units are '
    'taken as millimetres (1:1); a document in another unit gets a warning. '
    'Post the record with AddEvidence.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261102'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, MissingInput, reinforcement_layout_record)  # NOQA
    from csc_gh.layout import (bars_to_stored, layout_target, unit_warning)  # NOQA
    from csc_gh.rhino import (curve_points, mm_per_document_unit)  # NOQA
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
    ('Evidence', 'Evidence',
     'Evidence record JSON for AddEvidence'),
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


class CSC_ReinforcementLayout(Grasshopper.Kernel.GH_ScriptInstance):
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
        descriptions = [
            'Bar centrelines, one curve per bar (polylines are used as '
            'they are)',
            'Steel grade per bar, e.g. BSt III (optional: one for all bars '
            'or one per bar; empty: the bars carry no grade)',
            'Bar diameter in mm (one for all bars or one per bar)',
            'Id of the snapshot whose stored coordinates the curves are in '
            '(a layout belongs to one version; empty with a '
            'ComponentPassport: its snapshot)',
            'drawing, scan or exposed: where the layout is known from',
            'When it was observed (2024-05-03, ...; empty: now)',
            'Basis drawing: title of the drawing',
            'Basis drawing: date of the drawing',
            'Basis drawing: reference of the drawing',
            'Basis scan: covermeter, radar or other',
            'Basis scan: model of the instrument',
            'Accuracy, e.g. size and cover +-20 %',
            'Free text',
            'Basis drawing: link to the drawing online (http or https; '
            'needs DocumentTitle)',
            'Basis drawing: the day the link was read (2026-10-05)',
            'Passport of the element the curves were drawn on, with its '
            'placement if it was moved (ApplyFrame, TransformComponent): '
            'the curves are mapped back to the stored coordinates and the '
            'snapshot is taken from it. An explicit SnapshotID that '
            'disagrees is an error',
        ]
        for index, text_ in enumerate(descriptions):
            self.InputParams[index].Description = text_
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Curves: list[Rhino.Geometry.Curve],
            Spec: list[object],
            Diameter: list[float],
            SnapshotID: str,
            Basis: str,
            ObservedAt: str,
            DocumentTitle: str,
            DocumentDate: str,
            DocumentReference: str,
            InstrumentKind: str,
            InstrumentModel: str,
            AccuracyNote: str,
            Notes: str,
            DocumentUrl: str,
            DocumentRetrievedAt: str,
            ComponentPassport: str):
        if self._stop():
            return empty_outputs()
        Evidence = empty_outputs()
        try:
            curves = [c for c in (Curves or []) if c is not None]
            if not curves:
                raise MissingInput('Input Curves failed to collect data')
            specs = list(Spec or [])
            diameters = list(Diameter or [])
            if not diameters:
                raise MissingInput('Input Diameter failed to collect data')
            for name, items in (('Spec', specs), ('Diameter', diameters)):
                if name == 'Spec' and not items:
                    continue          # the steel grade is optional (8.187)
                if len(items) not in (1, len(curves)):
                    raise BuildError(
                        f'give one {name} for all bars or one per bar '
                        f'({len(curves)} curves, {len(items)} values)')
            target = layout_target(ComponentPassport, SnapshotID)
            if not target['snapshot_id']:
                raise MissingInput(
                    'SnapshotID is missing: give it, or a ComponentPassport',
                    ('SnapshotID', 'ComponentPassport'))
            scale, unit_name = mm_per_document_unit()
            bars = []
            for index, curve in enumerate(curves):
                bars.append({
                    'spec': (specs[0] if len(specs) == 1 else specs[index])
                    if specs else None,
                    'diameter_mm': (diameters[0] if len(diameters) == 1
                                    else diameters[index]),
                    'points': curve_points(curve),
                })
            bars = bars_to_stored(bars, target['placement'])
            record = reinforcement_layout_record(
                target['snapshot_id'], bars, Basis, ObservedAt,
                DocumentTitle, DocumentDate, DocumentReference,
                InstrumentKind, None, InstrumentModel, AccuracyNote, None,
                Notes, DocumentUrl, DocumentRetrievedAt)
            Evidence = json.dumps(record)
            self._addRemark(target['remark'])
            note = unit_warning(scale, unit_name)
            if note:
                self._addWarning(note)
            return Evidence
        except MissingInput as error:
            self._addWarning(str(error))
            return self._no_result(*error.ports)
        except BuildError as error:
            self._addError(str(error))
            return null_outputs()
        except ValueError as error:
            self._addError(str(error))
            return null_outputs()
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
            return null_outputs()
        return Evidence
