# -*- coding: utf-8 -*-
#! python3
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System
import Rhino
import Grasshopper
from scriptcontext import sticky as st

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateUUID'
ghenv.Component.NickName = 'CreateUUID'
ghenv.Component.Category = 'DDU_CSC'
ghenv.Component.SubCategory = '3 Component Operations'
ghenv.Component.Description = (
    'Creates new UUIDs on request.'
)


class CSC_CreateUUID(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023.1
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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
    
    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'If set to True, generates a new UUID'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'The current UUID'
        )
    
    def _updateComponent(self):
        """Updates this component using callback mechanism"""
        # Define callback action
        def callBack(e):
            st_key = f'{self.Component.InstanceGuid}__CreateUUIDComponent'
            new_uuid = uuid.uuid4()
            st[st_key] = new_uuid
            ghenv.Component.ExpireSolution(False)
        # Get grasshopper document
        ghDoc = ghenv.Component.OnPingDocument()
        # Schedule this component to expire
        ghDoc.ScheduleSolution(
            1,
            Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(callBack)
        )

    def RunScript(self, Refresh: bool):
        st_key = f'{self.Component.InstanceGuid}__CreateUUIDComponent'
        if Refresh or st_key not in st.keys():
            self._updateComponent()
        return st[st_key]
