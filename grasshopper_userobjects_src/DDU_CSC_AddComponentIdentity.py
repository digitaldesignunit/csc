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
ghenv.Component.Name = 'AddComponentIdentity'  # NOQA
ghenv.Component.NickName = 'AddComponentIdentity'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Records a new component with its first state: POST /identities '
    'and uploads the files staged by CreateComponentIdentity; consumes a '
    'pending transmitted component ID. The state lands as a draft: complete '
    'it (files, checks) and submit it in the web, My work.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261008'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (problems_of_identity, staging_key)  # NOQA
    from csc_gh.upload import (http_error_text, load_manifest, passport_after, staged_plan, staging_dir, upload_staged)  # NOQA
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
     'Component passport JSON ({identity, snapshots[]}) of the new component'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_AddComponentIdentity(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261008
    """

    _outputs_ready = True       # set by BeforeRunScript (8.112)
    _outputs_note = None

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
            'Request JSON from CreateComponentIdentity'
        )
        self.InputParams[1].Description = (
            'Toggle to execute the create operation (the new state lands '
            'as a draft; submit it in the web)'
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

    def consume_transmitted_id(self, auth_core, identity_id):
        """Consume a pending transmitted ID after the create; never fatal."""
        try:
            response = auth_core.authorized_post(
                '/component_id_transmission/consume',
                json_body={'identity_id': identity_id})
            if response.status_code == 200 and response.json().get(
                    'consumed', False):
                self._addRemark('Consumed pending transmitted ID.')
            elif response.status_code != 200:
                self._addWarning(
                    'Component created, but consuming the transmitted ID '
                    f'failed ({response.status_code}).')
        except Exception as error:
            self._addWarning('Component created, but consuming the '
                             f'transmitted ID failed: {error}')

    def RunScript(self, IdentityRequest: str, Run: bool):
        if self._stop():
            return empty_outputs()
        Created = Grasshopper.DataTree[System.Object]()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return Created
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addWarning(msg)
            return Created
        if not IdentityRequest:
            msg = 'Please provide the request JSON of CreateComponentIdentity.'
            self._addWarning(msg)
            return Created

        try:
            body = json.loads(IdentityRequest)
        except json.JSONDecodeError:
            msg = 'IdentityRequest must be valid JSON.'
            self._addError(msg)
            return Created
        problems = problems_of_identity(body)
        if problems:
            msg = 'The request is not a new-component request:\n' + \
                '\n'.join(problems)
            self._addError(msg)
            return Created

        directory = staging_dir(staging_key(IdentityRequest))
        manifest_dict = load_manifest(directory)
        pending, missing = ([], [])
        geometry = body['snapshot'].get('geometry', {})
        if manifest_dict:
            pending, missing = staged_plan(directory, manifest_dict)
        elif geometry.get('meshes') or geometry.get('point_clouds'):
            self._addRemark('No staged files for this request: only the '
                            'inline Preview geometry is stored.')
        if missing:
            self._addWarning('Staged files are missing: ' + ', '.join(
                entry['path'] for entry in missing))

        if not Run:
            self._state('Run is False')
            return Created

        try:
            response = auth_core.authorized_post('/identities',
                                                 json_body=body)
            if response.status_code != 201:
                msg = {
                    401: 'Authentication failed. Please sign in again.',
                    403: 'Access denied: you need the contributor role in '
                         'this dataset.',
                    409: 'A component with this IdentityID already exists.',
                }.get(response.status_code) or http_error_text(
                    response, 'Create')
                self._addError(msg)
                return Created
            created = response.json()
            identity_doc = created.get('identity') or {}
            snapshot_doc = created.get('snapshot') or {}
            identity_id = identity_doc.get('_id')
            snapshot_id = snapshot_doc.get('_id')
            self._addRemark(f'Created {identity_id} (state {snapshot_id}, '
                            'a draft)')
            self.consume_transmitted_id(auth_core, identity_id)

            upload_ok = True
            if pending:
                done, failed = upload_staged(
                    auth_core, snapshot_id, pending,
                    progress=self._state)
                for entry, reason in failed:
                    self._addWarning(reason)
                upload_ok = not failed
                self._addRemark(f'Uploaded {len(done)} of {len(pending)} '
                                'staged file(s).')

            if not upload_ok:
                self._addWarning('Some files failed to upload. The state is '
                                 'a draft: complete it in the web (My work) '
                                 'and submit it there.')
            self._state('draft')

            passport = passport_after(auth_core, identity_doc, snapshot_doc)
            Created.Add(json.dumps(passport),
                                   Grasshopper.Kernel.Data.GH_Path(0))
            return Created

        except requests.exceptions.ConnectionError as error:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {error}')
        except requests.exceptions.Timeout as error:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {error}')
        except Exception as error:
            # includes CSCClientOutdated: its text names the fix
            self._addError(str(error))
        return Created
