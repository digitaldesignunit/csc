#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportUnedfinedVariable] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'CreateDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'CreateDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '3 Component Operations'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Creates a design JSON string from component data, ready for posting to '
    'the catalogue. Validates input against design schema and generates '
    'complete design payload with UUID, timestamps, and component references. '
    'Does NOT post the design - only generates the JSON string.'
)


class CSC_CreateDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251014
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

    def _get_hardcoded_schema(self):
        """Get hardcoded design schema fallback."""
        return {
            "type": "object",
            "properties": {
                "_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "creator": {"type": "string"},
                "created": {"type": "string"},
                "lastmodified": {"type": "string"},
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "component": {"type": "string"},
                            "iframe": {
                                "type": "object",
                                "properties": {
                                    "o": {"type": "array",
                                          "items": {"type": "number"}},
                                    "x": {"type": "array",
                                          "items": {"type": "number"}},
                                    "y": {"type": "array",
                                          "items": {"type": "number"}},
                                    "z": {"type": "array",
                                          "items": {"type": "number"}}
                                },
                                "required": ["o", "x", "y", "z"]
                            }
                        },
                        "required": ["component", "iframe"]
                    }
                }
            },
            "required": ["_id", "creator", "created", "lastmodified",
                         "components"]
        }

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

    def get_design_schema(self, auth_core):
        """Get design schema with fallback."""
        try:
            # Try to get schema from cache
            schema = auth_core.get_design_schema()
            if schema:
                return schema
        except Exception:
            pass

        # Use hardcoded fallback
        self._addRemark('Using hardcoded design schema fallback')
        return self._get_hardcoded_schema()

    def validate_component_data(self, component_data: Dict[str, Any],
                                schema: Dict[str, Any]) -> bool:
        """Validate component data against schema."""
        try:
            # Check if component has required fields
            if '_id' not in component_data:
                self._addWarning('Component missing _id field')
                return False

            if 'iframe' not in component_data:
                self._addWarning('Component missing iframe field')
                return False

            # Validate iframe structure
            iframe = component_data['iframe']
            required_iframe_fields = ['o', 'x', 'y', 'z']
            for field in required_iframe_fields:
                if field not in iframe:
                    self._addWarning(f'Component iframe missing {field} field')
                    return False
                if not (isinstance(iframe[field], list) or
                        len(iframe[field]) != 3):
                    self._addWarning(
                        f'Component iframe {field} must be 3D vector'
                    )
                    return False

            return True
        except Exception as e:
            self._addWarning(f'Error validating component: {str(e)}')
            return False

    def create_design_payload(self, design_name: str, design_description: str,
                              component_data_list: List[str],
                              auth_core) -> Optional[Dict[str, Any]]:
        """Create design payload from component data."""
        try:
            # Get design schema
            schema = self.get_design_schema(auth_core)

            # Parse and validate component data
            components = []
            for i, component_json in enumerate(component_data_list):
                try:
                    component_data = json.loads(component_json)

                    # Validate component structure
                    if not self.validate_component_data(
                            component_data, schema):
                        self._addWarning(f'Invalid component at index {i}')
                        continue

                    # Extract component ID and iframe
                    component_id = component_data['_id']
                    iframe = component_data['iframe']

                    # Create design component entry
                    design_component = {
                        'component': component_id,
                        'iframe': iframe
                    }
                    components.append(design_component)

                except json.JSONDecodeError as e:
                    self._addWarning(f'Invalid JSON at index {i}: {str(e)}')
                    continue
                except Exception as e:
                    self._addWarning(
                        f'Error processing component {i}: {str(e)}'
                    )
                    continue

            if not components:
                self._addError('No valid components found')
                return None

            # Get current user ID from auth core
            user_id = auth_core.get_user_id()
            if not user_id:
                self._addError('Could not get user ID from authentication')
                return None

            # Generate timestamps
            current_time = datetime.utcnow().isoformat() + 'Z'

            # Create design payload
            design_payload = {
                '_id': str(uuid.uuid4()),
                'name': design_name,
                'description': design_description,
                'creator': user_id,
                'created': current_time,
                'lastmodified': current_time,
                'components': components
            }

            return design_payload

        except Exception as e:
            self._addError(f'Error creating design payload: {str(e)}')
            return None

    def RunScript(self,
            DesignName: str,
            DesignDescription: str,
            ComponentData: System.Collections.Generic.List[str]):
        # Initialize param descriptions
        self.InputParams[0].Description = 'Design name (mandatory)'
        self.InputParams[1].Description = 'Design description (optional)'
        self.InputParams[2].Description = 'List of component JSON strings'
        self.OutputParams[0].Description = (
            'Design JSON string ready for posting'
        )

        # Init outputs
        DesignJSON = Grasshopper.DataTree[str]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return DesignJSON

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return DesignJSON

        # Validate DesignName (mandatory)
        if not DesignName or not DesignName.strip():
            msg = 'Design name is mandatory and cannot be empty.'
            self._addWarning(msg)
            self.Component.Message = msg
            return DesignJSON

        # Set DesignDescription fallback
        if not DesignDescription:
            DesignDescription = 'No description provided.'

        # Validate ComponentData
        if not ComponentData:
            msg = 'Input ComponentData failed to collect data!'
            self._addWarning(msg)
            self.Component.Message = msg
            return

        try:
            # Create design payload
            design_payload = self.create_design_payload(
                DesignName.strip(),
                DesignDescription.strip(),
                ComponentData,
                auth_core
            )

            if design_payload is None:
                return DesignJSON

            # Convert to JSON string
            DesignJSON = json.dumps(design_payload, indent=2)

            self.Component.Message = (
                f'Design created: {len(design_payload["components"])} '
                'components'
            )

            return DesignJSON

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
