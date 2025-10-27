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
ghenv.Component.Name = 'FetchAllComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FetchAllComponents'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Fetches all available components from the remote catalogue API with '
    'caching support. Returns all components as a list of JSON strings.'
)


class CSC_FetchAllComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251027
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
            msg = ('No authentication found. Please use CSC_SignIn component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self):
        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_SignIn '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return

        try:
            self.Component.Message = 'Fetching components (with cache)...'

            # Make cached request to fetch all components
            response = auth_core.cached_get('/components', 'all_components')

            if response.status_code == 200:
                # Successfully fetched components
                json_comps = response.json()
                component_count = len(json_comps)

                self.Component.Message = (
                    f'Found {component_count} components (cached)'
                )
                self._addRemark(
                    f'Successfully fetched {component_count} components'
                )

                # Set up output trees and results tuple
                ComponentData = Grasshopper.DataTree[System.Object]()
                __Results = (ComponentData,)

                # Loop over all components and add them to the data tree
                for i, json_comp in enumerate(json_comps):
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(0, i)
                    # Add component data to the datatree
                    ComponentData.Add(json.dumps(json_comp), ghp)

                return __Results

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
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
