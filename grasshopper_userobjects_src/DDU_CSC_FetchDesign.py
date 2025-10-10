#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import numpy as np

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportUnedfinedVariable] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'FetchDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'FetchDesign'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Fetches a design from the remote catalogue along with all its contained '
    'components. Applies the design\'s iframe transformations to each '
    'component and returns both design JSON and transformed components. Uses '
    'caching for optimal performance.'
)


class CSC_FetchDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251010
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
        """Get AuthCore instance from sticky storage."""
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def apply_iframe_transformation(self, component_data, iframe):
        """
        Apply iframe transformation to component data.

        Args:
            component_data: Component data dictionary
            iframe: Design iframe with o, x, y, z vectors

        Returns:
            Component data with transformed geometry
        """
        try:
            # Create transformation matrix from iframe
            o = np.array(iframe['o'])
            x = np.array(iframe['x'])
            y = np.array(iframe['y'])
            z = np.array(iframe['z'])

            # Create 4x4 transformation matrix
            transform_matrix = np.array([
                [x[0], y[0], z[0], o[0]],
                [x[1], y[1], z[1], o[1]],
                [x[2], y[2], z[2], o[2]],
                [0, 0, 0, 1]
            ])

            # Apply transformation to geometry if present
            if 'geometry' in component_data:
                geometry = component_data['geometry']

                # Transform mesh vertices if present
                if 'mesh' in geometry and 'v' in geometry['mesh']:
                    vertices = np.array(geometry['mesh']['v'])
                    # Convert to homogeneous coordinates
                    vertices_homogeneous = np.column_stack([
                        vertices, np.ones(vertices.shape[0])
                    ])
                    # Apply transformation
                    transformed_vertices = (vertices_homogeneous @
                                            transform_matrix.T)
                    # Convert back to 3D coordinates
                    geometry['mesh']['v'] = (
                        transformed_vertices[:, :3].tolist())

                # Transform multiple meshes if present
                if ('meshes' in geometry and
                        isinstance(geometry['meshes'], list)):
                    for mesh in geometry['meshes']:
                        if 'v' in mesh:
                            vertices = np.array(mesh['v'])
                            vertices_homogeneous = np.column_stack([
                                vertices, np.ones(vertices.shape[0])
                            ])
                            transformed_vertices = (vertices_homogeneous @
                                                    transform_matrix.T)
                            mesh['v'] = transformed_vertices[:, :3].tolist()

                # Transform extrusion profile if present
                if ('extrusion' in geometry and
                        'profile' in geometry['extrusion']):
                    profile = np.array(geometry['extrusion']['profile'])
                    profile_homogeneous = np.column_stack([
                        profile, np.zeros(profile.shape[0]),
                        np.ones(profile.shape[0])
                    ])
                    transformed_profile = (profile_homogeneous @
                                           transform_matrix.T)
                    geometry['extrusion']['profile'] = (
                        transformed_profile[:, :2].tolist())

            # Store the applied iframe in the component data
            component_data['applied_iframe'] = iframe

            return component_data

        except Exception as e:
            self._addWarning(f'Error applying iframe transformation: {str(e)}')
            return component_data

    def RunScript(self, DesignID: str):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Design ID to fetch'
        self.OutputParams[0].Description = 'Design JSON string'
        self.OutputParams[1].Description = (
            'Components with iframe transformations applied')

        # Init outputs
        DesignData = Grasshopper.DataTree[str]()
        ComponentData = Grasshopper.DataTree[str]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return

        # Validate DesignID input
        if not DesignID or not DesignID.strip():
            msg = 'Please provide a Design ID to fetch.'
            self._addWarning(msg)
            self.Component.Message = msg
            return

        design_id = DesignID.strip()

        # Validate UUID format
        if not auth_core.validate_uuid(design_id):
            msg = f'Invalid Design ID format: {design_id}'
            self._addError(msg)
            self.Component.Message = msg
            return

        try:
            # Fetch design using cached_get
            response = auth_core.cached_get(
                f'/designs/{design_id}', f'design:{design_id}')

            if response.status_code == 200:
                design_data = response.json()
                self._addRemark(f'Successfully fetched design: {design_id}')

                # Extract component IDs and iframes from design
                components_data = []
                if 'components' in design_data:
                    for comp_ref in design_data['components']:
                        comp_id = comp_ref.get('component')
                        iframe = comp_ref.get('iframe')

                        if comp_id and iframe:
                            # Fetch component data using cached_get
                            comp_response = auth_core.cached_get(
                                f'/components/{comp_id}',
                                f'component:{comp_id}')

                            if comp_response.status_code == 200:
                                component_data = comp_response.json()

                                # Apply iframe transformation
                                transformed_component = (
                                    self.apply_iframe_transformation(
                                        component_data, iframe))
                                components_data.append(transformed_component)

                            else:
                                self._addWarning(
                                    f'Failed to fetch component {comp_id}: '
                                    f'{comp_response.status_code}')
                        else:
                            self._addWarning(
                                'Invalid component reference in design')

                # Set outputs
                design_json = json.dumps(design_data, indent=2)
                components_json = [json.dumps(c, indent=2)
                                   for c in components_data]
                DesignData = design_json
                ComponentData = components_json

                self.Component.Message = (
                    f'Design fetched: {len(components_data)} components')

                return DesignData, ComponentData

            elif response.status_code == 404:
                msg = f'Design not found: {design_id}'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg

            else:
                msg = f'Failed to fetch design: {response.status_code}'
                self._addError(msg)
                self.Component.Message = msg

        except requests.exceptions.RequestException as e:
            msg = f'Network error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
