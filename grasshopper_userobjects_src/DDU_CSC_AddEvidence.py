#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: requests==2.32.5
# r: numpy==2.0.2
print('ENV OK!')

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
ghenv.Component.Name = 'AddEvidence'  # NOQA
ghenv.Component.NickName = 'AddEvidence'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Posts evidence records (an observation or a claim about a component, '
    'e.g. a ReinforcementLayout) with POST /evidence/bulk: all records are '
    'checked first and stored all or none. One IdentityID applies to every '
    'record; as many ids as records pair up one to one. The records land '
    'as drafts: complete them (files, checks) and submit them in the web, '
    'My work.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261008'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, evidence_bulk_body)  # NOQA
    from csc_gh.upload import (http_error_text)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261008 too old or missing: run CSC_Update, '
        'then restart Rhino')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Created', 'Created',
     'The stored evidence records as the server returns them (JSON)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_AddEvidence(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261008
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

    def _stop(self):
        """True when RunScript has to return early: the library is missing or
        too old, or the outputs were just updated (says why)."""
        if LIBRARY_PROBLEM:
            self._addError(LIBRARY_PROBLEM)
            return True
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
        self.InputParams[0].Description = (
            'Id(s) of the component(s) the records are about: one for all '
            'records or one per record'
        )
        self.InputParams[1].Description = (
            'Evidence record JSON, e.g. from ReinforcementLayout. An '
            'archival_document without a summary is a document (it never '
            'enters the properties); payload.document may carry a url '
            '(http or https) and retrieved_at, also in a '
            'reinforcement_layout'
        )
        self.InputParams[2].Description = (
            'Toggle to execute the create operation (the records land as '
            'drafts; submit them in the web)'
        )
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addWarning(msg)
            return None
        return auth_core

    def RunScript(self, IdentityID: list[object], Evidence: list[object], Run: bool):
        if self._stop():
            return empty_outputs()
        Stored = Grasshopper.DataTree[System.Object]()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return Stored
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return Stored

        try:
            body = evidence_bulk_body(list(Evidence or []),
                                      list(IdentityID or []))
        except BuildError as error:
            self._addWarning(str(error))
            return Stored

        count = len(body['records'])
        if not Run:
            self._state('Run is False')
            return Stored

        try:
            response = auth_core.authorized_post('/evidence/bulk',
                                                 json_body=body)
            if response.status_code != 201:
                msg = {
                    401: 'Authentication failed. Please sign in again.',
                    403: 'Access denied: you need the contributor role in '
                         'the dataset of every component.',
                    404: 'A component was not found.',
                }.get(response.status_code) or http_error_text(
                    response, 'Add evidence')
                self._addError(msg)
                return Stored
            stored = response.json().get('records') or []
            for index, record in enumerate(stored):
                Stored.Add(json.dumps(record),
                             Grasshopper.Kernel.Data.GH_Path(index))
            self._state(f'{len(stored)} created')
            return Stored

        except requests.exceptions.ConnectionError as error:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {error}')
        except requests.exceptions.Timeout as error:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {error}')
        except Exception as error:
            # includes CSCClientOutdated: its text names the fix
            self._addError(str(error))
        return Stored
