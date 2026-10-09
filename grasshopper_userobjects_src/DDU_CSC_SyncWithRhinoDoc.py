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
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SyncWithRhinoDoc'  # NOQA
ghenv.Component.NickName = 'SyncWithRhinoDoc'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '4 RhinoDoc Interaction'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Reads the pieces back from the active Rhino document: every text tag '
    'with the user text csc_identity_id / csc_snapshot_id / csc_placement '
    '(a piece baked by BakeComponents or by PassportToD2P) gives its '
    'component passport JSON with csc_placement set from where the tag is now, so '
    'moving or rotating a piece in Rhino moves it in Grasshopper. The '
    'component passport is the tag csc_component, else read by id through the '
    'Session. Nothing is written to the server.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261005'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.doc import (passport_fetcher, read_document)  # NOQA
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
    ('DocumentComponents', 'DocumentComponents',
     'DataTree of component passport JSON ({identity, snapshots[]}) of the pieces in the document, one per tag, with csc_placement set from the tag plane (feed it to Disassemble, ApplyFrame or TransformComponent)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_SyncWithRhinoDoc(Grasshopper.Kernel.GH_ScriptInstance):
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
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Trigger to sync components with Rhino document'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def RunScript(self, Sync: bool):
        # init outputs
        if self._stop():
            return empty_outputs()
        DocumentComponents = Grasshopper.DataTree[str]()
        if not Sync:
            # Return empty results if not syncing
            self._state('Sync is off')
            return DocumentComponents
        try:
            doc = Rhino.RhinoDoc.ActiveDoc
            fetch = passport_fetcher(sc.sticky.get('CSC_AuthCore'))
            pieces = read_document(doc, fetch)
            if not pieces:
                msg = 'No components found in document!'
                self._addWarning(msg)
                return DocumentComponents

            for i, piece in enumerate(pieces):
                label = piece['identity_id'] or 'a tag without an identity'
                for problem in piece['problems']:
                    self._addWarning(f'{label}: {problem}')
                if piece['passport'] is None:
                    continue
                ghp = Grasshopper.Kernel.Data.GH_Path(i)
                DocumentComponents.Add(json.dumps(piece['passport']), ghp)
                self._addRemark(f'Read {label} from its tag')

            if DocumentComponents.DataCount > 0:
                self._state(f'Synced {DocumentComponents.DataCount}')
            else:
                self._addWarning('No components were successfully synced')
            return DocumentComponents

        except Exception as e:
            msg = f'Unexpected error during sync: {str(e)}'
            self._addError(msg)
            return DocumentComponents
