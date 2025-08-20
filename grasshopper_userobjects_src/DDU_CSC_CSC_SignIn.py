#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json

import System
import Rhino
import Grasshopper

import requests

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "CSC_SignIn"
ghenv.Component.NickName = "CSC_SignIn"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "1 User"

class CSC_SignIn(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """
    
    def __init__(self):
        super().__init__()
        # initialize props
        self.BASEURL = None
        self.TOKENURL = None
        self.USERNAME = None
        self.PASSWORD = None
        self.TOKEN = None

    def get_base_url(self):
        return self.__BASEURL

    def set_base_url(self, value):
        self.__BASEURL = value

    BASEURL = property(get_base_url, set_base_url, None, "Base URL Property")

    def get_token_url(self):
        return self.__TOKENURL

    def set_token_url(self, value):
        self.__TOKENURL = value

    TOKENURL = property(get_token_url, set_token_url, None, "Token URL Property")

    def get_user(self):
        return self.__USERNAME

    def set_user(self, value):
        self.__USERNAME = value

    USERNAME = property(get_user, set_user, None, "Username Property")

    def get_pass(self):
        return self.__PASSWORD

    def set_pass(self, value):
        self.__PASSWORD = value

    PASSWORD = property(get_pass, set_pass, None, "Password Property")

    def get_token(self):
        return self.__TOKEN

    def set_token(self, value):
        self.__TOKEN = value

    TOKEN = property(get_token, set_token, None, "Access Token Property")

    def slash_join(self, *args):
        """Joins together a bunch of strings using slashes."""
        return '/'.join(arg.strip('/') for arg in args)

    def _create_headers(self, token: str = ''):
        """
        Obtain correct headers for performing a request to FARO Component
        Repository API.
        """
        # if no token exists, we need to authenticate first
        if not token:
            token = self._fetch_access_token()
        # set header with authentication token
        return {'Authorization': f'Bearer {token}'}

    def _fetch_access_token(self,
                            tokenurl: str = '',
                            username: str = '',
                            password: str = ''):
        """
        Obtain an Access Token for the CSC Component API.
        """
        if not tokenurl:
            tokenurl = self.TOKENURL
        if not username:
            username = self.USERNAME
        if not password:
            password = self.PASSWORD
        # make authentication request
        print('[CSC-API] Obtaining authentication token...')
        response = requests.post(
            tokenurl,
            headers={'content-type': 'application/x-www-form-urlencoded'},
            data={'grant_type': 'password',
                  'username': username,
                  'password': password}
        )
        # store token during runtime
        token = response.json()['access_token']
        self.TOKEN = token
        return token

    def RunScript(self, BaseURL: str, TokenURL: str, Username: str, Password: str):

        BaseURL = str(BaseURL)
        TokenURL = str(TokenURL)
        Username = str(Username)
        Password = str(Password)

        self.BASEURL = BaseURL
        self.TOKENURL = TokenURL
        self.USERNAME = Username
        self.PASSWORD = Password

        Config = {
            'base_url': BaseURL,
            'token_url': TokenURL,
            'username': Username,
            'password': Password,
            'token': self._fetch_access_token()
        }

        return json.dumps(Config)
