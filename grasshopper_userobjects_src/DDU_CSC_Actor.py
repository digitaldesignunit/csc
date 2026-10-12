#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
# r: charset_normalizer
# r: numpy==2.0.2
print('ENV OK!')

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA
import time  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'Actor'  # NOQA
ghenv.Component.NickName = 'Actor'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Builds one actor (a person or an organization, optionally a '
    'catalog account) as JSON for Origin or an evidence record. Kind is '
    'guessed when empty: a user id makes a user, only an organization '
    'an organization, else a person. With Me set to true the actor is the '
    'signed-in account (sign in with the Session component first): its '
    'id, name, organization, ROR and ORCID come from the profile in the '
    'web settings, the role from Role or else the profile\'s default role; '
    'any input you fill in overrides the profile value.'
)

# CSC LIBRARY (decision 8.111) ----------------------------------------------
CSC_GH_MINIMUM = '261012'
LIBRARY_PROBLEM = None
try:
    import csc_gh
    csc_gh.require(CSC_GH_MINIMUM)
    from csc_gh.build import (BuildError, actor, actor_from_profile, cached_profile)  # NOQA
    from csc_gh.upload import (http_error_text)  # NOQA
except ImportError:
    LIBRARY_PROBLEM = (
        'CSC library 261012 too old or missing: run CSC_Update, '
        'then restart Rhino')

NOT_SIGNED_IN = ('Me needs a signed-in session: sign in with the Session '
                 'component first')

# OPTIONAL HELPERS: they never block the component (decisions 8.112, 8.113) ---
try:
    from csc_gh.ports import ensure_outputs
    from csc_gh.messages import set_state
except ImportError:
    ensure_outputs = set_state = None

OUTPUTS = [
    ('Actor', 'Actor',
     'Actor JSON (a fragment of the API payload)'),
]


def empty_outputs():
    """What RunScript returns when it stops early."""
    if len(OUTPUTS) <= 1:
        return None
    return tuple(None for _ in OUTPUTS)


class CSC_Actor(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 261012
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
            'user, person or organization (empty: guessed)'
        )
        self.InputParams[1].Description = (
            'Id of a catalog account (kind user)'
        )
        self.InputParams[2].Description = (
            'Name of a person (shown to signed-in users only)'
        )
        self.InputParams[3].Description = (
            'Organization, e.g. a laboratory or contractor'
        )
        self.InputParams[4].Description = (
            'ROR identifier of the organization'
        )
        self.InputParams[5].Description = (
            'ORCID of a person'
        )
        self.InputParams[6].Description = (
            'E-mail address (shown to moderators only)'
        )
        self.InputParams[7].Description = (
            'operator, supervisor, laboratory, client or witness (with Me: '
            'empty takes the default role of your profile)'
        )
        self.InputParams[8].Description = (
            'True: the actor is the signed-in account, filled from its '
            'profile (name, organization, ROR, ORCID); what you fill in '
            'overrides it. Needs the Session component signed in'
        )
        # Initialize output param descriptions
        self._check_outputs()
        if LIBRARY_PROBLEM is None:
            csc_gh.dev_reload(globals())

    def read_profile(self):
        """The profile of the signed-in account (``GET /users/me``), read at
        most once a minute per server and user."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None or not auth_core.is_valid():
            raise BuildError(NOT_SIGNED_IN)

        def fetch():
            response = auth_core.authorized_get('/users/me')
            if response.status_code == 401:
                raise BuildError(NOT_SIGNED_IN)
            if response.status_code != 200:
                raise BuildError(http_error_text(
                    response, 'Reading the profile'))
            return response.json()

        key = (auth_core.base_url, auth_core.get_username())
        return cached_profile(sc.sticky, key, fetch, time.time())

    def RunScript(self,
            Kind: str,
            UserID: str,
            Name: str,
            Organization: str,
            OrganizationROR: str,
            ORCID: str,
            Email: str,
            Role: str,
            Me: bool):
        if self._stop():
            return empty_outputs()
        Actor = ''
        try:
            if Me:
                profile = self.read_profile()
                fragment = actor_from_profile(
                    profile, Kind, UserID, Name, Organization,
                    OrganizationROR, ORCID, Email, Role)
                own_id = str(profile.get('_id') or profile.get('id') or '')
                if fragment.get('user_id') != own_id:
                    self._addWarning(
                        'UserID differs from the signed-in account: the '
                        'actor names another account, with your profile '
                        'values for everything you did not fill in')
            else:
                fragment = actor(Kind, UserID, Name, Organization,
                                 OrganizationROR, ORCID, Email, Role)
            Actor = json.dumps(fragment)
            return Actor
        except BuildError as error:
            self._addError(str(error))
        except Exception as error:
            msg = f'Unexpected error: {error}'
            self._addError(msg)
        return Actor
