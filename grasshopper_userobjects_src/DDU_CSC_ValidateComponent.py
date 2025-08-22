#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json
import uuid

import requests

import System
import Grasshopper
import Rhino

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "ValidateComponent"
ghenv.Component.NickName = "ValidateComponent"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "9 Admin Actions"


class CSC_ValidateComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 250820
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.TOKEN = None

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
            token = self.TOKEN
        # set header with authentication token
        return {'Authorization': f'Bearer {token}'}

    def _make_request(self,
                      method: str,
                      endpoint: str,
                      params=None,
                      data=None):
        """
        Perform a request to the API
        """
        # create correct url
        url = self.slash_join(self.BASEURL, endpoint)
        # set header with authentication token
        headers = self._create_headers(token=self.TOKEN)
        # perform request
        print(f'[CSC-API] Performing {method} request using token...')
        response = requests.request(method=method,
                                    url=url,
                                    params=params,
                                    data=data,
                                    headers=headers)
        # if response has status code for Unauthorized request,
        # get new token and try again one time
        if response.status_code == 401:
            print('[CSC-API] Request failed, retrying...')
            headers = self._create_headers(token='')
            response = requests.request(method=method,
                                        url=url,
                                        params=params,
                                        data=data,
                                        headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f'Request failed with status code {response.status_code}')
        return response

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

    def RunScript(self, Config: str, Validate: bool, ComponentID: str):
        # set up output trees and results tuple
        ComponentData = Grasshopper.DataTree[System.Object]()
        # sanitize input and abort if not present
        if not Config:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input Config failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        else:
            Config = str(Config)
            config_data = json.loads(Config)
            self.BASEURL = config_data['base_url']
            self.TOKEN = config_data['token']
        if not ComponentID:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input ComponentID failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        ComponentID = str(ComponentID)
        if not  self.validate_uuid(ComponentID):
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = f'ComponentID {ComponentID} is not a valid UUID!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return ComponentData
        if Validate is True:
            # set endpoint
            endpoint = f'validate/{ComponentID}'
            # perform request
            response = self._make_request('GET', endpoint)
            # convert response to json data
            json_comp = response.json()
            print(json_comp['validated'])
            print(f'[CSC-API] Validated component {ComponentID} on server.')
            # add all things to the respective datatrees
            ComponentData = json.dumps(json_comp)
        # return output trees
        return ComponentData
