#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'AddComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'AddComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_AddComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250828
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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_SignIn component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self, ComponentData: str, Run: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Component data as JSON string to add to the database')
        self.InputParams[1].Description = (
            'Toggle to execute the add operation')
        self.OutputParams[0].Description = (
            'The added component data returned from the server as JSON')

        # Set up output trees and results tuple
        AddedComponentData = Grasshopper.DataTree[System.Object]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return AddedComponentData

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_SignIn '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate ComponentData input
        if not ComponentData:
            msg = 'Please provide ComponentData to add.'
            self._addWarning(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate JSON format
        try:
            component_json = json.loads(ComponentData)
        except json.JSONDecodeError:
            msg = 'ComponentData must be valid JSON format.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        if not Run:
            self.Component.Message = (
                'Ready to add component (toggle Run to execute)')
            return AddedComponentData

        try:
            self.Component.Message = 'Adding component to database...'

            # Make authenticated request to add component
            response = auth_core.authorized_post(
                '/components/add/', json_body=component_json)

            if response.status_code == 201:
                # Successfully added component
                json_comp = response.json()
                component_id = json_comp.get('_id', 'Unknown')

                # Create datatree path
                ghp = Grasshopper.Kernel.Data.GH_Path(0)
                # Add component data to the datatree
                AddedComponentData.Add(json.dumps(json_comp), ghp)

                self._addRemark(
                    f'Successfully added component {component_id} to database'
                )
                self.Component.Message = f'Added component {component_id}'

            elif response.status_code == 400:
                msg = 'Invalid component data format.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            elif response.status_code == 409:
                msg = 'Component already exists with this data.'
                self._addWarning(msg)
                self.Component.Message = msg

            elif response.status_code == 422:
                msg = 'Component data validation failed.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)
                self.Component.Message = msg

            else:
                msg = (f'Request failed with status code: '
                       f'{response.status_code}')
                self._addError(msg)
                self.Component.Message = msg

            return AddedComponentData

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        # Return empty results if there was an error
        AddedComponentData = Grasshopper.DataTree[System.Object]()
        return AddedComponentData
