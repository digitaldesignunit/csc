#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
from scriptcontext import sticky as st  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateUUID'  # NOQA
ghenv.Component.NickName = 'CreateUUID'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Creates new UUIDs on request.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('UUID', 'UUID',
     'The current UUID'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) == 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_CreateUUID(Grasshopper.Kernel.GH_ScriptInstance):
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
        """True when RunScript has to return early: the outputs were just updated (says why)."""
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
            'If set to True, generates a new UUID'
        )
        self._check_outputs()

    def _updateComponent(self):
        """Updates this component using callback mechanism"""
        # Define callback action
        def callBack(e):
            st_key = f'{self.Component.InstanceGuid}__CreateUUIDComponent'
            new_uuid = uuid.uuid4()
            st[st_key] = new_uuid
            self.Component.ExpireSolution(False)  # NOQA
            return
        # Get grasshopper document
        ghDoc = ghenv.Component.OnPingDocument()  # NOQA
        # Schedule this component to expire
        ghDoc.ScheduleSolution(
            1,
            Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(callBack)
        )
        return False

    def RunScript(self, Refresh: bool):
        if self._stop():
            return empty_outputs()
        st_key = f'{self.Component.InstanceGuid}__CreateUUIDComponent'
        if Refresh or st_key not in st.keys():
            create_new_uuid = True
        else:
            create_new_uuid = False
        if create_new_uuid:
            create_new_uuid = self._updateComponent()
        return st[st_key]
