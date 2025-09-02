#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

import json

import requests

import System
import Grasshopper
import Rhino

# GHENV COMPONENT SETTINGS
ghenv.Component.Name = "FetchAllUnvalidatedComponents"
ghenv.Component.NickName = "FetchAllUnvalidatedComponents"
ghenv.Component.Category = "DDU_CSC"
ghenv.Component.SubCategory = "9 Admin Actions"


class CSC_FetchAllUnvalidatedComponents(Grasshopper.Kernel.GH_ScriptInstance):
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

    def RunScript(self):
        # set up output trees and results tuple
        ComponentData = Grasshopper.DataTree[System.Object]()
        __Results = (ComponentData)
        # sanitize input and abort if not present
        if not Config:
            rml = ghenv.Component.RuntimeMessageLevel.Warning
            msg = 'Input CSCToken failed to collect data!'
            ghenv.Component.AddRuntimeMessage(rml, msg)
            return __Results
        else:
            config_data = json.loads(Config)
            self.BASEURL = config_data['base_url']
            self.TOKEN = config_data['token']
        # set endpoint
        endpoint = 'components?validated=-1'
        # perform request
        response = self._make_request('GET', endpoint)
        # convert response to json data
        json_comps = response.json()
        print(f'[CSC-API] Found {len(json_comps)} components on server.')
        # loop over all components and disassemble them
        for i, json_comp in enumerate(json_comps):
            # create datatree path
            ghp = Grasshopper.Kernel.Data.GH_Path(i)
            # add all things to the respective datatrees
            ComponentData.Add(json.dumps(json_comp), ghp)
        # return output trees
        return __Results
