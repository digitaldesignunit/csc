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
ghenv.Component.Name = 'ListIdentitySnapshots'  # NOQA
ghenv.Component.NickName = 'ListIdentitySnapshots'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Lists all snapshots for one identity (id and name). Input can '
    'be an identity UUID or compose JSON ({identity, snapshots[]}).'
)


class CSC_ListIdentitySnapshots(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260610
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
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
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0 + i].Description = 'Snapshot UUIDs (ordered by version)'
        self.OutputParams[1 + i].Description = 'Snapshot names (parallel to SnapshotID)'

    def get_auth_core_from_sticky(self):
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self, Input):
        SnapshotID = Grasshopper.DataTree[str]()
        SnapshotName = Grasshopper.DataTree[str]()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return SnapshotID, SnapshotName

        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return SnapshotID, SnapshotName

        if Input is None or (isinstance(Input, str) and not str(Input).strip()):
            msg = 'Please provide an identity UUID or compose JSON.'
            self._addWarning(msg)
            self.Component.Message = msg
            return SnapshotID, SnapshotName

        identity_id = auth_core.resolve_identity_id_from_input(Input)
        if not identity_id:
            msg = 'Input is not a valid identity UUID or compose JSON.'
            self._addError(msg)
            self.Component.Message = msg
            return SnapshotID, SnapshotName

        try:
            self.Component.Message = (
                f'Listing snapshots for identity {identity_id}...'
            )
            response = auth_core.authorized_get(
                f'/identities/{identity_id}/snapshots'
            )

            if response.status_code == 200:
                rows = response.json()
                if not isinstance(rows, list):
                    msg = 'Unexpected response from snapshot list endpoint.'
                    self._addError(msg)
                    self.Component.Message = msg
                    return SnapshotID, SnapshotName

                path = Grasshopper.Kernel.Data.GH_Path(0)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    snap_id = str(row.get('_id') or '')
                    name = str(row.get('name') or '')
                    if snap_id:
                        SnapshotID.Add(snap_id, path)
                        SnapshotName.Add(name, path)

                self.Component.Message = (
                    f'Listed {SnapshotID.DataCount} snapshot(s)'
                )
                return SnapshotID, SnapshotName

            if response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
            elif response.status_code == 404:
                msg = f'Identity {identity_id} not found.'
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

        return SnapshotID, SnapshotName
