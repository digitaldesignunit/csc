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
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'BakeComponents'  # NOQA
ghenv.Component.NickName = 'BakeComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Bakes component passports ({identity, snapshots[]}) into the Rhino document: the '
    'meshes, point clouds and authored shapes of a piece in its canonical '
    'orientation (frame applied, centred at the origin) or where its '
    'csc_placement puts it, plus one text tag per piece at the plane of the '
    'canonical piece. The tag carries the user text csc_identity_id, '
    'csc_snapshot_id, csc_placement (and csc_component, the component passport). Move '
    'the group in Rhino, then read it back with SyncWithRhinoDoc. Nothing '
    'is written to the server.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.read import (load_passport, parts)  # NOQA
    from csc_gh.convention import (ConventionError)  # NOQA
    from csc_gh.doc import (bake_level, bake_piece, piece_items)  # NOQA
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
    # (no outputs)
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_BakeComponents(Grasshopper.Kernel.GH_ScriptInstance):
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
            'Toggle to bake components to Rhino'
        )
        self.InputParams[1].Description = (
            'Component passport JSON strings ({identity, snapshots[]}) from the fetch '
            'components. A piece with a csc_placement (TransformComponent, '
            'ApplyFrame) is baked there, any other in its canonical '
            'orientation at the origin. Its snapshot needs a frame.'
        )
        self.InputParams[2].Description = (
            "Mesh level: 'original' (default, the full mesh, else reduced), "
            "'reduced' or 'preview' (the inline preview). Point clouds: the "
            'full cloud unless preview.'
        )
        self.InputParams[3].Description = (
            'Write the component passport JSON on the tag as csc_component '
            '(default true): SyncWithRhinoDoc then needs no sign-in. False '
            'keeps the document small; the component passport is fetched by id.'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self,
            Bake: bool,
            ComponentPassport: list[object],
            DetailLevel: str,
            WithComponentPassport: bool):
        if self._stop():
            return empty_outputs()
        if not Bake:
            self._state('Bake is off')
            self._addRemark('Bake toggle is off - no components baked')
            return empty_outputs()
        if not ComponentPassport or len(ComponentPassport) == 0:
            msg = ('No component data provided. Please connect '
                   'FetchComponent output.')
            self._addWarning(msg)
            return empty_outputs()
        try:
            level = bake_level(DetailLevel)
        except ValueError as error:
            self._addError(str(error))
            return empty_outputs()
        with_passport = True if WithComponentPassport is None else bool(WithComponentPassport)

        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None and level != 'preview':
            self._addWarning('No signed-in Session: the preview geometry is '
                             'baked instead of the PLY levels.')
            level = 'preview'

        doc = Rhino.RhinoDoc.ActiveDoc
        baked = 0
        record = doc.BeginUndoRecord('Bake CSC components')
        try:
            for index, text in enumerate(ComponentPassport):
                passport = load_passport(text)
                if passport is None:
                    self._addWarning(f'Item {index} is not component passport JSON '
                                     '({identity, snapshots[]})')
                    continue
                identity, snapshot = parts(passport)
                label = (identity or {}).get('_id') or f'item {index}'
                try:
                    items = piece_items(auth_core, snapshot, level,
                                        self._addWarning)
                    result = bake_piece(doc, passport, items, with_passport,
                                        self._addWarning)
                    baked += 1
                    self._addRemark(
                        f'Baked {label} ({len(result["ids"])} objects and '
                        'a tag)')
                except ConventionError as error:
                    self._addWarning(f'{label}: {error}')
                except Exception as error:
                    self._addError(f'Error baking {label}: {error}')
        finally:
            if record:
                doc.EndUndoRecord(record)
        doc.Views.Redraw()

        if baked > 0:
            self._state(f'Baked {baked}')
        else:
            self._addWarning('No components were baked')
