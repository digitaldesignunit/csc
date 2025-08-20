#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json
import uuid
from pprint import pprint

import requests

import System
import Grasshopper
import Rhino

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "CSC_AddComponent"
ghenv.Component.NickName = "CSC_AddComponent"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "2 Catalogue Interface"


class AddComponent(Grasshopper.Kernel.GH_ScriptInstance):
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

    def RunScript(self, Config: str, ComponentData: str, Run: bool):
        # set up output trees and results tuple
        AddedComponentData = Grasshopper.DataTree[System.Object]()
        # sanitize input and abort if not present
        if not Config:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input Config failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return AddedComponentData
        else:
            config_data = json.loads(Config)
            self.BASEURL = config_data['base_url']
            self.TOKEN = config_data['token']
        if not ComponentData:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input ComponentData failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return AddedComponentData

        if Run:
            # set endpoint
            endpoint = '/'
            # perform request
            response = self._make_request('POST', endpoint, data=ComponentData)
            # convert response to json data
            json_comp = response.json()
            print(f'[CSC-API] Added component {json_comp["_id"]} to database.')
            AddedComponentData = json.dumps(json_comp)
        return AddedComponentData
