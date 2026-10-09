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
ghenv.Component.Name = 'FetchAllComponents'  # NOQA
ghenv.Component.NickName = 'FetchAllComponents'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches all catalog identities (joined with their current snapshot) '
    'from the remote Catalog API via GET /identities with caching support. '
    'Returns each entry as a component passport JSON string ({identity, snapshots[]}).'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('ComponentPassport', 'ComponentPassport',
     "Component passport JSON per entry ({identity, snapshots[]}) fetched from GET /identities. Use 'DisassembleComponent' to access the individual fields ready for Grasshopper"),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FetchAllComponents(Grasshopper.Kernel.GH_ScriptInstance):
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
        """True when RunScript has to return early: the outputs were just
        updated (says why)."""
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
        # Initialize output param descriptions
        self._check_outputs()

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addWarning(msg)
            return None
        return auth_core

    def RunScript(self):
        # Get AuthCore instance from sticky storage
        if self._stop():
            return empty_outputs()
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return empty_outputs()

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return empty_outputs()

        try:

            # Unified catalog cache: stores identity + snapshot independently
            # and reassembles passport rows (no separate all_identities blob).
            response = auth_core.cached_list_identities(
                {'expand': 'current_snapshot'},
            )

            if response.status_code == 200:
                # Successfully fetched identities (from server or cache)
                json_comps = response.json()
                component_count = len(json_comps)
                self._state(f'{component_count} fetched')

                self._addRemark(
                    f'Successfully fetched {component_count} components'
                )

                # Set up output trees and results tuple
                ComponentPassport = Grasshopper.DataTree[System.Object]()
                __Results = (ComponentPassport,)

                # Loop over all passport entries and add them to the data tree
                for i, json_comp in enumerate(json_comps):
                    # Create datatree path
                    ghp = Grasshopper.Kernel.Data.GH_Path(0, i)
                    # Add canonical passport JSON to the datatree
                    ComponentPassport.Add(
                        auth_core.passport_json_string(json_comp), ghp)

                return __Results

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)

            elif response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)

            else:
                msg = (f'Request failed with status code: '
                       f'{response.status_code}')
                self._addError(msg)

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)

        # Return empty results if there was an error
        ComponentPassport = Grasshopper.DataTree[System.Object]()
        __Results = (ComponentPassport,)
        return __Results
