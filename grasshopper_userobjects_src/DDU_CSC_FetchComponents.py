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
import json

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FetchComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Fetches specific components from the remote catalogue by their IDs. '
    'Supports caching and handles individual component retrieval with error '
    'handling for missing components.'
)


class CSC_FetchComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251030
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
        self.InputParams[0].Description = 'One or many ComponentIDs to fetch'
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'The ComponentData that was fetched from the server as JSON. '
            'Use \'DisassembleComponent\' to access the individual fields '
            'ready for Grasshopper'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self, ComponentID: list[str]):
        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return

        # Validate ComponentID input
        if not ComponentID:
            msg = 'Please provide ComponentID(s) to fetch.'
            self._addWarning(msg)
            self.Component.Message = msg
            return

        # Convert to list and validate UUIDs
        component_ids = list(ComponentID)
        for _id in component_ids:
            if not auth_core.validate_uuid(_id):
                msg = f'ComponentID <{_id}> is not a valid UUID!'
                self._addWarning(msg)
                self.Component.Message = msg
                return

        try:
            self.Component.Message = (
                f'Fetching {len(component_ids)} component(s) (with cache)...'
            )

            # Set up output trees and results tuple
            ComponentData = Grasshopper.DataTree[System.Object]()
            __Results = (ComponentData,)

            # Fetch each component
            for i, _id in enumerate(component_ids):
                try:
                    # Make cached request to fetch specific component
                    response = auth_core.cached_get(
                        f'/components/{_id}', f'component:{_id}')

                    if response.status_code == 200:
                        # Successfully fetched component (from server or cache)
                        json_comp = response.json()

                        # Create datatree path
                        ghp = Grasshopper.Kernel.Data.GH_Path(i)
                        # Add component data to the datatree
                        ComponentData.Add(json.dumps(json_comp), ghp)

                        self._addRemark(
                            f'Successfully fetched component {_id}'
                        )

                    elif response.status_code == 404:
                        msg = f'Component {_id} not found on server.'
                        self._addWarning(msg)
                        self.Component.Message = msg

                    elif response.status_code == 401:
                        msg = 'Authentication failed. Please sign in again.'
                        self._addError(msg)
                        self.Component.Message = msg
                        return __Results

                    elif response.status_code == 403:
                        msg = 'Access denied. Insufficient permissions.'
                        self._addError(msg)
                        self.Component.Message = msg
                        return __Results

                    elif response.status_code == 500:
                        msg = 'Server error. Please try again later.'
                        self._addWarning(msg)
                        self.Component.Message = msg

                    else:
                        msg = (f'Request failed for component {_id} with '
                               f'status code: {response.status_code}')
                        self._addError(msg)
                        self.Component.Message = msg

                except Exception as e:
                    msg = f'Error fetching component {_id}: {str(e)}'
                    self._addError(msg)
                    self.Component.Message = msg

            # Update success message
            if ComponentData.DataCount > 0:
                self.Component.Message = (
                    f'Fetched {ComponentData.DataCount} component(s) (cached)'
                )
            else:
                self.Component.Message = 'No components fetched'

            return __Results

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
        ComponentData = Grasshopper.DataTree[System.Object]()
        __Results = (ComponentData,)
        return __Results
