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
ghenv.Component.Name = 'FetchAllSnapshots'  # NOQA
ghenv.Component.NickName = 'FetchAllSnapshots'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Fetches component passport JSON with every snapshot for one identity '
    '({identity, snapshots[]}). Input can be an identity UUID or component passport '
    'JSON.'
)

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state, waits_for_data
except ImportError:
    ensure_outputs = set_state = waits_for_data = None

OUTPUTS = [
    ('ComponentPassport', 'ComponentPassport',
     'Component passport JSON string: {identity, snapshots[]} with every version'),
]


def empty_outputs():
    """What RunScript returns when it stops early or has no result: an empty
    Grasshopper tree per output (never '' or None)."""
    if not OUTPUTS:
        return None
    trees = tuple(Grasshopper.DataTree[System.Object]() for _ in OUTPUTS)
    return trees[0] if len(trees) == 1 else trees


def null_outputs():
    """One null per output: an item of an item-access component that has no
    result keeps its slot (decision 8.186)."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_FetchAllSnapshots(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261102
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

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

    def _state(self, text=''):
        """The one short state under the component (decision 8.113)."""
        if set_state is not None:
            set_state(self.Component, text)

    def _no_result(self, *ports):
        """The result of an iteration without one (decision 8.186): empty
        outputs when the inputs in ``ports`` carry no data at all (the
        component waits for data; no ports: a list or tree input is empty),
        else a null in the slot of this item, so the outputs stay one to one
        with the input list."""
        if not ports or (waits_for_data is not None
                         and waits_for_data(self, ports)):
            return empty_outputs()
        return null_outputs()

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
        self.InputParams[0].Description = (
            'Identity UUID or component passport JSON ({identity, snapshots[]})'
        )
        self._check_outputs()

    def get_auth_core_from_sticky(self):
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addWarning(msg)
            return None
        return auth_core

    def RunScript(self, Input):
        if self._stop():
            return empty_outputs()
        ComponentPassport = empty_outputs()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return ComponentPassport

        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return ComponentPassport

        if Input is None or (isinstance(Input, str) and not str(Input).strip()):
            msg = 'Please provide an identity UUID or component passport JSON.'
            self._addWarning(msg)
            return self._no_result('Input')

        identity_id = auth_core.resolve_identity_id_from_input(Input)
        if not identity_id:
            msg = 'Input is not a valid identity UUID or component passport JSON.'
            self._addError(msg)
            return null_outputs()

        try:
            response = auth_core.cached_get_passport(
                identity_id,
                snapshots='all',
            )

            if response.status_code == 200:
                data = response.json()
                ComponentPassport = auth_core.passport_json_string(data)
                count = len(data.get('snapshots') or [])
                self._state(f'{count} snapshot(s)')
                return ComponentPassport

            if response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
            elif response.status_code == 404:
                msg = f'Identity {identity_id} not found.'
            else:
                msg = f'Request failed with status code: {response.status_code}'
            self._addError(msg)

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            return null_outputs()
        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            return null_outputs()
        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            return null_outputs()

        return ComponentPassport
