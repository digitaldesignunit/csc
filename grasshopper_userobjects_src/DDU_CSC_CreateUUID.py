#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

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


class CreateUUID(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251021
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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

    def RunScript(self, Refresh: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'If set to True, generates a new UUID'
        )
        # Initialize output param descriptions
        self.OutputParams[0].Description = (
            'The current UUID'
        )
        st_key = f'{self.Component.InstanceGuid}__CreateUUIDComponent'
        new_uuid = ''
        if Refresh or st_key not in st.keys():
            new_uuid = uuid.uuid4()
            st[st_key] = new_uuid
        return st[st_key]
