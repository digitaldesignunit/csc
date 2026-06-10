#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchComponents'  # NOQA
ghenv.Component.NickName = 'FetchComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches specific identities (with their current snapshot) from the '
    'remote Catalog by their identity IDs. Supports caching and returns '
    'compose JSON ({identity, snapshots[]}) with error handling for missing '
    'identities.'
)


class CSC_FetchComponents(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260610
    """

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

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'One or many identity IDs (UUIDs) to fetch'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Compose JSON per entry ({identity, snapshots[]}) fetched from the '
            'server. Use \'DisassembleComponent\' to access the individual '
            'fields ready for Grasshopper'
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

        # Validate identity ID input
        if not ComponentID:
            msg = 'Please provide identity ID(s) to fetch.'
            self._addWarning(msg)
            self.Component.Message = msg
            return

        # Convert to list and validate UUIDs
        component_ids = list(ComponentID)
        for _id in component_ids:
            if not auth_core.validate_uuid(_id):
                msg = f'Identity ID <{_id}> is not a valid UUID!'
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

            # Fetch each identity's current-snapshot compose
            for i, _id in enumerate(component_ids):
                try:
                    # Unified catalog cache (identity + snapshot stored
                    # independently, compose assembled on read).
                    response = auth_core.cached_get_compose(_id)

                    if response.status_code == 200:
                        # Successfully fetched compose (from server or cache)
                        json_comp = response.json()

                        # Create datatree path
                        ghp = Grasshopper.Kernel.Data.GH_Path(i)
                        # Add canonical compose JSON to the datatree
                        ComponentData.Add(
                            auth_core.compose_json_string(json_comp), ghp)

                        self._addRemark(
                            f'Successfully fetched component {_id}'
                        )

                    elif response.status_code == 404:
                        msg = f'Identity {_id} not found on server.'
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
