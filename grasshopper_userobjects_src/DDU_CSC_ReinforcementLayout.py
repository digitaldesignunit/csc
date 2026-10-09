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
    'exposed bar. The curves must be in the stored coordinates of the state '
    'named by SnapshotID (millimetres). Post the record with AddEvidence.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, reinforcement_layout_record)  # NOQA
    from csc_gh.rhino import (curve_points)  # NOQA
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
    ('Evidence', 'Evidence',
     'Evidence record JSON for AddEvidence'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_ReinforcementLayout(Grasshopper.Kernel.GH_ScriptInstance):
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
        descriptions = [
            'Bar centrelines, one curve per bar (polylines are used as '
            'they are)',
            'Steel grade per bar, e.g. BSt III (one for all bars or one '
            'per bar)',
            'Bar diameter in mm (one for all bars or one per bar)',
            'Id of the state whose stored coordinates the curves are in',
            'drawing, scan or exposed: where the layout is known from',
            'When it was observed (2024-05-03, ...; empty: now)',
            'Basis drawing: title of the drawing',
            'Basis drawing: date of the drawing',
            'Basis drawing: reference of the drawing',
            'Basis scan: covermeter, radar or other',
            'Basis scan: model of the instrument',
            'Accuracy, e.g. size and cover +-20 %',
            'Free text',
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
            Notes: str):
        if self._stop():
            return empty_outputs()
        Evidence = ''
        try:
            curves = [c for c in (Curves or []) if c is not None]
            if not curves:
                raise BuildError('Input Curves failed to collect data')
            specs = list(Spec or [])
            diameters = list(Diameter or [])
            for name, items in (('Spec', specs), ('Diameter', diameters)):
                if len(items) not in (1, len(curves)):
                    raise BuildError(
                        f'give one {name} for all bars or one per bar '
                        f'({len(curves)} curves, {len(items)} values)')
            if not diameters:
                raise BuildError('Input Diameter failed to collect data')
            bars = []
            for index, curve in enumerate(curves):
                bars.append({
                    'spec': (specs[0] if len(specs) == 1 else specs[index])
                    if specs else None,
                    'diameter_mm': (diameters[0] if len(diameters) == 1
                                    else diameters[index]),
                    'points': curve_points(curve),
                })
            record = reinforcement_layout_record(
                SnapshotID, bars, Basis, ObservedAt, DocumentTitle,
                DocumentDate, DocumentReference, InstrumentKind, None,
                InstrumentModel, AccuracyNote, None, Notes)
            Evidence = json.dumps(record)
            return Evidence
        except BuildError as error:
            self._addError(str(error))
        except ValueError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return Evidence
