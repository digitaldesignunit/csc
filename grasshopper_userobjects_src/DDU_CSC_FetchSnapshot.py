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
ghenv.Component.Name = 'FetchSnapshot'  # NOQA
ghenv.Component.NickName = 'FetchSnapshot'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches compose JSON for one identity and a specific snapshot '
    '({identity, snapshots:[one]}). Identity input can be a UUID or compose '
    'JSON.'
)


class CSC_FetchSnapshot(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260610
    """

    def __init__(self):
        super().__init__()
        self.Component = ghenv.Component  # NOQA
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

    def BeforeRunScript(self):
        self.InputParams[0].Description = (
            'Identity UUID or compose JSON ({identity, snapshots[]})'
        )
        self.InputParams[1].Description = 'Snapshot UUID to fetch'
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0 + i].Description = (
            'Compose JSON string: {identity, snapshots:[requested snapshot]}'
        )

    def get_auth_core_from_sticky(self):
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self, Input, SnapshotID):
        ComposeJSON = ''

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return ComposeJSON

        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return ComposeJSON

        if Input is None or (isinstance(Input, str) and not str(Input).strip()):
            msg = 'Please provide an identity UUID or compose JSON.'
            self._addWarning(msg)
            self.Component.Message = msg
            return ComposeJSON

        snapshot_id = str(SnapshotID or '').strip()
        if not snapshot_id or not auth_core.validate_uuid(snapshot_id):
            msg = 'Please provide a valid snapshot UUID.'
            self._addError(msg)
            self.Component.Message = msg
            return ComposeJSON

        identity_id = auth_core.resolve_identity_id_from_input(Input)
        if not identity_id:
            msg = 'Input is not a valid identity UUID or compose JSON.'
            self._addError(msg)
            self.Component.Message = msg
            return ComposeJSON

        try:
            self.Component.Message = (
                f'Fetching snapshot {snapshot_id} for identity {identity_id}...'
            )
            response = auth_core.cached_get_compose(
                identity_id,
                snapshots=[snapshot_id],
            )

            if response.status_code == 200:
                data = response.json()
                ComposeJSON = auth_core.compose_json_string(data)
                self.Component.Message = 'Fetched compose for snapshot'
                return ComposeJSON

            if response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
            elif response.status_code == 404:
                msg = (
                    f'Identity {identity_id} or snapshot {snapshot_id} '
                    'not found.'
                )
            else:
                msg = f'Request failed with status code: {response.status_code}'
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
        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        return ComposeJSON
