#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import time
import json
import base64
from threading import RLock
import uuid

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'SignIn'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '1 User'  # type: ignore[reportUnedfinedVariable] # NOQA


# AuthCore - Embedded ---------------------------------------------------------

class _AuthCore(object):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250902
    """

    def __init__(self, base_url, leeway=30):
        self.base_url = (base_url or 'https://api.ddu.uber.space').rstrip('/')
        self.leeway = int(leeway) if leeway is not None else 30
        self._lock = RLock()
        self._token = None
        self._exp = 0
        self._username = None

    @staticmethod
    def _now():
        return int(time.time())

    @staticmethod
    def _b64url_decode(seg):
        rem = len(seg) % 4
        if rem:
            seg += '=' * (4 - rem)
        return base64.urlsafe_b64decode(seg.encode('utf-8'))

    @classmethod
    def _jwt_payload(cls, token):
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            return json.loads(cls._b64url_decode(parts[1]).decode('utf-8'))
        except Exception:
            return {}

    def set_access_token(self, token, username=None):
        payload = self._jwt_payload(token)
        exp = int(payload.get('exp', 0))
        if exp <= 0:
            exp = self._now() + 3600  # 1h fallback if no exp claim
        with self._lock:
            self._token = token
            self._exp = exp
            if username:
                self._username = username

    def clear(self):
        with self._lock:
            self._token = None
            self._exp = 0
            self._username = None

    def is_valid(self):
        with self._lock:
            if not self._token or self._exp <= 0:
                return False
            return (self._now() + self.leeway) < self._exp

    def get_username(self):
        with self._lock:
            return self._username

    def auth_header(self):
        with self._lock:
            return ({'Authorization': 'Bearer ' + self._token}
                    if self._token else {})

    def authorized_get(
            self,
            path,
            params=None,
            extra_headers=None,
            timeout=20):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        return requests.get(
            self.base_url + path,
            params=params,
            headers=headers,
            timeout=timeout
        )

    def authorized_post(
            self,
            path,
            json_body=None,
            files=None,
            extra_headers=None,
            timeout=60):
        if not self.is_valid():
            raise RuntimeError(
                'Access token missing or expired. Please sign in again.'
            )
        headers = self.auth_header()
        if extra_headers:
            headers.update(extra_headers)
        # Handle file uploads vs JSON requests
        if files is not None:
            # For file uploads, don't set Content-Type header
            # (let requests handle it)
            # and use data instead of json
            return requests.post(
                self.base_url + path,
                files=files,
                headers=headers,
                timeout=timeout
            )
        else:
            # For JSON requests, use json parameter
            return requests.post(
                self.base_url + path,
                json=json_body,
                headers=headers,
                timeout=timeout
            )

    def validate_uuid(self, uuid_to_test: str, version: int = 4):
        """
        Check if uuid_to_test is a valid UUID.
        Returns True if uuid_to_test is a valid UUID, otherwise False.
        """
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test


class CSC_SignIn(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250902
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
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

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage or create new one."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            # Create new AuthCore instance with default settings
            auth_core = _AuthCore(base_url='https://api.ddu.uber.space')
            sc.sticky['CSC_AuthCore'] = auth_core
        return auth_core

    def RunScript(self, Username: str, Password: str, Refresh: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Your Username or E-Mail'
        self.InputParams[1].Description = 'Your password'
        self.InputParams[2].Description = (
            'Refresh toggle, press when your token expired'
        )

        # Get or create AuthCore instance
        auth_core = self.get_auth_core_from_sticky()

        # Input validation
        if not Username or not Username.strip():
            self.Component.Message = 'Please provide username/email'
            return

        if not Password or not Password.strip():
            self.Component.Message = 'Please provide password'
            return

        username = Username.strip()
        password = Password.strip()

        try:
            if Refresh:
                # Refresh authentication - clear existing token and re-auth
                auth_core.clear()
                self.Component.Message = 'Refreshing authentication...'
            else:
                # Check if we already have a valid token
                if auth_core.is_valid():
                    current_user = auth_core.get_username()
                    self.Component.Message = (
                        f'Already signed in as: {current_user}'
                    )
                    return

                self.Component.Message = 'Signing in...'

            # Prepare login data
            login_data = {
                'username': username,
                'password': password
            }

            # Make login request
            response = requests.post(
                f'{auth_core.base_url}/auth/token',
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout=20
            )

            if response.status_code == 200:
                # Login successful
                token_data = response.json()
                access_token = token_data.get('access_token')

                if access_token:
                    # Store token in AuthCore
                    auth_core.set_access_token(access_token, username)

                    # Update sticky storage
                    sc.sticky['CSC_AuthCore'] = auth_core

                    self.Component.Message = f'Signed in as: {username}'
                else:
                    msg = 'Login failed: No token received'
                    self._addWarning(msg)
                    self.Component.Message = msg

            elif response.status_code == 401:
                msg = 'Invalid username or password'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 422:
                msg = 'Invalid input data'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 500:
                msg = 'Server error - please try again'
                self._addWarning(msg)
                self.Component.Message = msg

            else:
                msg = 'Login failed: {response.status_code}'
                self._addError(msg)
                self.Component.Message = msg

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server - check URL'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout - server may be slow'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            self.Component.Message = f'Unexpected error: {str(e)}'
