#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

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
ghenv.Component.Name = 'AddDesign'  # NOQA
ghenv.Component.NickName = 'AddDesign'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Adds a new design to the remote database. Takes design data (JSON), '
    'validates it, and makes an authenticated POST request to add the design '
    'to the catalogue. Designs contain component references and additional '
    'geometry embedded directly in the JSON.'
)


class CSC_AddDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251203
    """

    def __init__(self):
        """Initialize this component and set component parameters."""
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def BeforeRunScript(self):
        """Perform some setup actions."""
        # Initialize input param descriptions
        self.InputParams[0].Description = (
            'Design data as JSON string to add to the database'
        )
        self.InputParams[1].Description = (
            'Toggle to execute the add operation'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'The added design data returned from the server as JSON'
        )

    def get_auth_core_from_sticky(self):
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def RunScript(self, DesignData: str, Run: bool):
        # Set up output trees and results tuple
        AddedDesignData = Grasshopper.DataTree[System.Object]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return AddedDesignData

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedDesignData

        # Validate DesignData input
        if not DesignData:
            msg = 'Input parameter DesignData failed to collect data'
            self._addWarning(msg)
            return AddedDesignData

        # Validate JSON format
        try:
            design_json = json.loads(DesignData)
        except json.JSONDecodeError:
            msg = 'DesignData must be valid JSON format.'
            self._addError(msg)
            return AddedDesignData

        # Extract design ID for validation
        design_id = design_json.get('_id', '')
        if not design_id:
            msg = 'Design data must contain a valid _id field.'
            self._addError(msg)
            return AddedDesignData

        # Validate required fields for design creation
        required_fields = [
            'name', 'created', 'lastmodified', 'components'
        ]
        missing_fields = []
        for field in required_fields:
            if field not in design_json:
                missing_fields.append(field)

        if missing_fields:
            fields_str = ", ".join(missing_fields)
            msg = f'Design data missing required fields: {fields_str}'
            self._addError(msg)
            return AddedDesignData

        # Validate components structure
        components = design_json.get('components', [])
        if not isinstance(components, list):
            msg = 'Design components must be a list.'
            self._addError(msg)
            return AddedDesignData

        if len(components) == 0:
            msg = 'Design must contain at least one component.'
            self._addError(msg)
            return AddedDesignData

        # Validate each component entry
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                msg = f'Component at index {i} must be a dictionary.'
                self._addError(msg)
                return AddedDesignData

            if 'component' not in comp:
                msg = f'Component at index {i} missing "component" field.'
                self._addError(msg)
                return AddedDesignData

            if 'iframe' not in comp:
                msg = f'Component at index {i} missing "iframe" field.'
                self._addError(msg)
                return AddedDesignData

            # Validate iframe structure
            iframe = comp['iframe']
            if not isinstance(iframe, dict):
                msg = f'Component at index {i} iframe must be a dictionary.'
                self._addError(msg)
                return AddedDesignData

            required_iframe_fields = ['o', 'x', 'y', 'z']
            for field in required_iframe_fields:
                if field not in iframe:
                    msg = (
                        f'Component at index {i} iframe missing {field} field.'
                    )
                    self._addError(msg)
                    self.Component.Message = msg
                    return AddedDesignData

                if (not isinstance(iframe[field], list) or
                        len(iframe[field]) != 3):
                    msg = (f'Component at index {i} iframe {field} must '
                           'be 3D vector')
                    self._addError(msg)
                    return AddedDesignData

        # Validate additional_geometry if present
        additional_geometry = design_json.get('additional_geometry', [])
        if not isinstance(additional_geometry, list):
            msg = 'Design additional_geometry must be a list.'
            self._addError(msg)
            return AddedDesignData

        if len(additional_geometry) > 25:
            msg = 'Design cannot have more than 25 additional geometries.'
            self._addError(msg)
            return AddedDesignData

        # Validate each additional geometry entry
        for i, ag in enumerate(additional_geometry):
            if not isinstance(ag, dict):
                msg = f'Additional geometry at index {i} must be a dictionary.'
                self._addError(msg)
                return AddedDesignData

            if 'id' not in ag:
                msg = f'Additional geometry at index {i} missing "id" field.'
                self._addError(msg)
                return AddedDesignData

            if 'iframe' not in ag:
                msg = (f'Additional geometry at index {i} missing '
                       '"iframe" field.')
                self._addError(msg)
                return AddedDesignData

            if 'geometry' not in ag:
                msg = (f'Additional geometry at index {i} missing '
                       '"geometry" field.')
                self._addError(msg)
                return AddedDesignData

            # Validate iframe structure for additional geometry
            iframe = ag['iframe']
            if not isinstance(iframe, dict):
                msg = (f'Additional geometry at index {i} iframe must be '
                       'a dictionary.')
                self._addError(msg)
                return AddedDesignData

            required_iframe_fields = ['o', 'x', 'y', 'z']
            for field in required_iframe_fields:
                if field not in iframe:
                    msg = (f'Additional geometry at index {i} iframe missing '
                           f'{field} field.')
                    self._addError(msg)
                    return AddedDesignData

                if (not isinstance(iframe[field], list) or
                        len(iframe[field]) != 3):
                    msg = (f'Additional geometry at index {i} iframe {field} '
                           'must be 3D vector.')
                    self._addError(msg)
                    return AddedDesignData

        # Check payload size (rough estimate)
        try:
            payload_size = len(json.dumps(design_json))
            if payload_size > 10 * 1024 * 1024:  # 10MB
                msg = 'Design payload exceeds 10MB limit.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedDesignData
        except Exception:
            pass  # Skip size check if serialization fails

        if not Run:
            status_msg = (f'Ready to add design with {len(components)} '
                          'components')
            if additional_geometry:
                status_msg += (f' and {len(additional_geometry)} additional '
                               'geometries')
            status_msg += ' (toggle Run to execute)'
            self.Component.Message = status_msg
            return AddedDesignData

        try:
            self.Component.Message = 'Adding design to database...'

            # Make authenticated request to add design
            response = auth_core.authorized_post(
                '/designs', json_body=design_json)

            if response.status_code == 201:
                # Successfully added design
                json_design = response.json()
                design_id = json_design.get('_id', 'Unknown')

                # Create datatree path
                ghp = Grasshopper.Kernel.Data.GH_Path(0)
                # Add design data to the datatree
                AddedDesignData.Add(json.dumps(json_design), ghp)

                self._addRemark(
                    f'Successfully added design {design_id} to database'
                )
                self.Component.Message = f'Added design {design_id}'

            elif response.status_code == 400:
                msg = 'Invalid design data format.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedDesignData

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedDesignData

            elif response.status_code == 409:
                msg = 'Design already exists with this data.'
                self._addWarning(msg)
                self.Component.Message = msg

            elif response.status_code == 413:
                msg = 'Design payload exceeds 10MB limit.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 422:
                # Try to get detailed validation error from response
                try:
                    error_detail = response.json()
                    if 'detail' in error_detail:
                        if isinstance(error_detail['detail'], list):
                            # Pydantic validation errors
                            validation_errors = []
                            for error in error_detail['detail']:
                                field = error.get('loc', ['unknown'])[-1]
                                message = error.get('msg', 'validation error')
                                validation_errors.append(f"{field}: {message}")
                            errors_str = '\n'.join(validation_errors)
                            msg = (f'Design data validation failed:\n'
                                   f'{errors_str}')
                        else:
                            detail = error_detail["detail"]
                            msg = (f'Design data validation failed: '
                                   f'{detail}')
                    else:
                        msg = (f'Design data validation failed: '
                               f'{error_detail}')
                except (json.JSONDecodeError, KeyError):
                    msg = 'Design data validation failed.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)
                self.Component.Message = msg

            else:
                msg = (f'Request failed with status code: '
                       f'{response.status_code}')
                self._addError(msg)
                self.Component.Message = msg

            return AddedDesignData

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as e:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(e)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Request error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        # Return empty results if there was an error
        AddedDesignData = Grasshopper.DataTree[System.Object]()
        return AddedDesignData
