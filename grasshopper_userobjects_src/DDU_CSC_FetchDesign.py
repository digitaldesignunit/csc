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
    'components. Updates each component\'s iframe with the design\'s iframe '
    'and returns both design JSON and components with updated iframes. Uses '
    'caching for optimal performance.'
)


class CSC_FetchDesign(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251015.2
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

    def create_additional_geometry_mesh(self, geometry_data, item_id):
        """
        Create Rhino mesh from additional geometry data.

        Args:
            geometry_data: Additional geometry data dictionary
            item_id: ID of the additional geometry item

        Returns:
            List of Rhino.Geometry.Mesh objects
        """
        meshes = []

        try:
            # Check if geometry has meshes array
            if ('meshes' in geometry_data and
                    isinstance(geometry_data['meshes'], list)):
                for i, mesh_data in enumerate(geometry_data['meshes']):
                    if 'v' in mesh_data and 'f' in mesh_data:
                        mesh = Rhino.Geometry.Mesh()
                        vl = mesh_data['v']
                        fl = mesh_data['f']

                        # Add vertices
                        [mesh.Vertices.Add(*v) for v in vl]
                        # Add faces
                        [mesh.Faces.AddFace(*f) for f in fl]

                        # Try to get mesh-specific colors
                        try:
                            cl = mesh_data['c']
                            [mesh.VertexColors.Add(
                                System.Drawing.Color.FromArgb(*c))
                             for c in cl]
                        except KeyError:
                            # Use default gray color
                            default_color = System.Drawing.Color.Gray
                            for _ in range(len(vl)):
                                mesh.VertexColors.Add(default_color)

                        # Set user strings for identification
                        mesh.SetUserString('csc_additional_geometry', item_id)
                        mesh.SetUserString('csc_mesh_index', str(i))

                        # Rebuild normals and compact
                        mesh.RebuildNormals()
                        mesh.UnifyNormals()
                        mesh.Compact()

                        meshes.append(mesh)

        except Exception as e:
            self._addWarning(
                f'Error creating mesh for additional geometry {item_id}: '
                f'{str(e)}')

        return meshes

    def apply_iframe_transformation(self, component_data, iframe):
        """
        Update component iframe with design iframe (geometry unchanged).

        Args:
            component_data: Component data dictionary
            iframe: Design iframe with o, x, y, z vectors

        Returns:
            Component data with updated iframe (geometry unchanged)
        """
        try:
            # Create a copy of the component data to avoid modifying original
            updated_component = component_data.copy()

            # Update the iframe field with the design's iframe
            # This is what we want: replace the component's iframe with the
            # design's iframe
            updated_component['iframe'] = iframe

            return updated_component

        except Exception as e:
            self._addWarning(f'Error updating iframe: {str(e)}')
            return component_data

    def RunScript(self, DesignID: str):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = 'Design ID to fetch'
        self.OutputParams[0].Description = 'Design JSON string'
        self.OutputParams[1].Description = (
            'Components with updated iframes from design')
        self.OutputParams[2].Description = (
            'Additional geometry items (list of JSON strings)')
        self.OutputParams[3].Description = (
            'Additional geometry as Rhino meshes')

        # Init outputs
        DesignData = Grasshopper.DataTree[str]()
        ComponentData = Grasshopper.DataTree[str]()
        AdditionalGeometryData = Grasshopper.DataTree[str]()
        AdditionalGeometry = Grasshopper.DataTree[System.Object]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)

        # Validate DesignID input
        if not DesignID or not DesignID.strip():
            msg = 'Please provide a Design ID to fetch.'
            self._addWarning(msg)
            self.Component.Message = msg
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)

        design_id = DesignID.strip()

        # Validate UUID format
        if not auth_core.validate_uuid(design_id):
            msg = f'Invalid Design ID format: {design_id}'
            self._addError(msg)
            self.Component.Message = msg
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)

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

                                # Update iframe with design iframe
                                updated_component = (
                                    self.apply_iframe_transformation(
                                        component_data, iframe))
                                components_data.append(updated_component)

                            else:
                                self._addWarning(
                                    f'Failed to fetch component {comp_id}: '
                                    f'{comp_response.status_code}')
                        else:
                            self._addWarning(
                                'Invalid component reference in design')

                # Extract additional geometry from design
                additional_geometry_data = []
                additional_geometry_meshes = []
                if 'additional_geometry' in design_data:
                    additional_geometry_data = design_data[
                        'additional_geometry']

                    # Create Rhino meshes for additional geometry
                    for item in additional_geometry_data:
                        item_id = item.get('id', 'unknown')
                        geometry_data = item.get('geometry', {})
                        iframe = item.get('iframe', {})

                        # Create meshes from geometry data
                        meshes = self.create_additional_geometry_mesh(
                            geometry_data, item_id)

                        # Apply iframe transformation to each mesh
                        if iframe and meshes:
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

                                # Convert to Rhino transform
                                rhino_transform = Rhino.Geometry.Transform()
                                for i in range(4):
                                    for j in range(4):
                                        rhino_transform[i, j] = (
                                            float(transform_matrix[i, j]))

                                # Apply transformation to each mesh
                                for mesh in meshes:
                                    mesh.Transform(rhino_transform)

                            except Exception as e:
                                self._addWarning(
                                    f'Error applying iframe transformation to '
                                    f'additional geometry {item_id}: {str(e)}')

                        additional_geometry_meshes.extend(meshes)

                # Set outputs
                design_json = json.dumps(design_data, indent=2)
                components_json = [json.dumps(c, indent=2)
                                   for c in components_data]
                additional_geometry_json = [
                    json.dumps(item, indent=2)
                    for item in additional_geometry_data]

                DesignData = design_json
                ComponentData = components_json
                AdditionalGeometryData = additional_geometry_json
                AdditionalGeometry = additional_geometry_meshes

                self.Component.Message = (
                    f'Design fetched: {len(components_data)} components, '
                    f'{len(additional_geometry_data)} additional geometry '
                    f'items')

                return (DesignData, ComponentData, AdditionalGeometryData,
                        AdditionalGeometry)

            elif response.status_code == 404:
                msg = f'Design not found: {design_id}'
                self._addError(msg)
                self.Component.Message = msg
                return (DesignData, ComponentData, AdditionalGeometryData,
                        AdditionalGeometry)

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return (DesignData, ComponentData, AdditionalGeometryData,
                        AdditionalGeometry)

            else:
                msg = f'Failed to fetch design: {response.status_code}'
                self._addError(msg)
                self.Component.Message = msg
                return (DesignData, ComponentData, AdditionalGeometryData,
                        AdditionalGeometry)

        except requests.exceptions.RequestException as e:
            msg = f'Network error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)

        except Exception as e:
            msg = f'Unexpected error: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return (DesignData, ComponentData, AdditionalGeometryData,
                    AdditionalGeometry)
