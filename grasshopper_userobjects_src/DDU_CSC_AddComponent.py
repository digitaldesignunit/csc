#! python3
# venv: DDU_CSC
# r: requests==2.31.0
# r: numpy==1.26.4
# r: scipy==1.13.0
# r: scikit-learn==1.4.2

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os
import platform

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'AddComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'AddComponent'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '2 Catalogue Interface'  # type: ignore[reportUnedfinedVariable] # NOQA


class CSC_AddComponent(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251009
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
            msg = ('No authentication found. Please use CSC_SignIn component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def get_geometry_folder_path(self, component_id: str) -> str:
        """
        Get the geometry folder path for a component.
        Returns the appropriate path based on the operating system.
        """
        if platform.system() == 'Windows':
            base_path = os.path.expandvars('%APPDATA%')
            geometry_path = os.path.join(
                base_path, 'DDU_CSC', 'create_component_geometry', component_id
            )
        else:  # macOS and Linux
            base_path = os.path.expanduser('~')
            geometry_path = os.path.join(
                base_path, 'Library', 'Application Support', 'DDU_CSC',
                'create_component_geometry', component_id
            )
        return geometry_path

    def check_geometry_files(self, component_id: str) -> dict:
        """
        Check which geometry files exist for a component.
        Returns dict with file existence status.
        Note: Only OBJ files with embedded vertex colors are used.
        """
        folder_path = self.get_geometry_folder_path(component_id)
        files_status = {
            'detailed_obj': os.path.exists(
                os.path.join(folder_path, 'mesh.obj')),
            'reduced_obj': os.path.exists(
                os.path.join(folder_path, 'mesh_reduced.obj')),
            'folder_path': folder_path
        }
        return files_status

    def upload_geometry_files(
            self, auth_core, component_id: str, files_status: dict) -> bool:
        """
        Upload geometry files to the backend using the geometry routes.
        Now handles OBJ-only uploads (no MTL files).
        Returns True if successful, False otherwise.
        """
        try:
            folder_path = files_status['folder_path']
            upload_success = True
            # Upload detailed geometry if OBJ file exists
            if files_status['detailed_obj']:
                self.Component.Message = 'Uploading detailed geometry...'
                self._addRemark(
                    'Starting detailed geometry upload '
                    '(this may take a while)'
                )
                detailed_files = {
                    'mesh_file': open(os.path.join(
                        folder_path, 'mesh.obj'), 'rb')
                }
                try:
                    # Use longer timeout for file uploads
                    response = auth_core.authorized_post(
                        f'/components/{component_id}/geometry/add_detailed',
                        files=detailed_files,
                        timeout=300  # 5 minutes timeout for file uploads
                    )
                    if response.status_code == 200:
                        self._addRemark(
                            'Successfully uploaded detailed geometry'
                        )
                    else:
                        self._addWarning(
                            'Failed to upload detailed '
                            f'geometry: {response.status_code}'
                        )
                        upload_success = False
                except requests.exceptions.Timeout:
                    self._addWarning(
                        'Detailed geometry upload timed out. '
                        'File may be too large or connection slow.'
                    )
                    upload_success = False
                except requests.exceptions.ConnectionError:
                    self._addWarning(
                        'Connection lost during detailed geometry upload. '
                        'Please check your internet connection.'
                    )
                    upload_success = False
                finally:
                    # Close all opened files
                    for file_obj in detailed_files.values():
                        file_obj.close()

            # Upload reduced geometry if OBJ file exists
            if files_status['reduced_obj'] and upload_success:
                self.Component.Message = 'Uploading reduced geometry...'
                self._addRemark('Starting reduced geometry upload')
                reduced_files = {
                    'mesh_file': open(os.path.join(
                        folder_path, 'mesh_reduced.obj'), 'rb')
                }
                try:
                    # Use longer timeout for file uploads
                    response = auth_core.authorized_post(
                        f'/components/{component_id}/geometry/add_reduced',
                        files=reduced_files,
                        timeout=300  # 5 minutes timeout for file uploads
                    )
                    if response.status_code == 200:
                        self._addRemark(
                            'Successfully uploaded reduced geometry'
                        )
                    else:
                        self._addWarning(
                            'Failed to upload reduced '
                            f'geometry: {response.status_code}'
                        )
                        upload_success = False
                except requests.exceptions.Timeout:
                    self._addWarning(
                        'Reduced geometry upload timed out. '
                        'File may be too large or connection slow.'
                    )
                    upload_success = False
                except requests.exceptions.ConnectionError:
                    self._addWarning(
                        'Connection lost during reduced geometry upload. '
                        'Please check your internet connection.'
                    )
                    upload_success = False
                finally:
                    # Close all opened files
                    for file_obj in reduced_files.values():
                        file_obj.close()
            return upload_success
        except Exception as e:
            self._addWarning(f'Error uploading geometry files: {str(e)}')
            return False

    def RunScript(self, ComponentData: str, Run: bool):
        # Initialize param descriptions (this has to be done in RunScript)
        self.InputParams[0].Description = (
            'Component data as JSON string to add to the database')
        self.InputParams[1].Description = (
            'Toggle to execute the add operation')
        self.OutputParams[0].Description = (
            'The added component data returned from the server as JSON')

        # Set up output trees and results tuple
        AddedComponentData = Grasshopper.DataTree[System.Object]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return AddedComponentData

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_SignIn '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate ComponentData input
        if not ComponentData:
            msg = 'Please provide ComponentData to add.'
            self._addWarning(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate JSON format
        try:
            component_json = json.loads(ComponentData)
        except json.JSONDecodeError:
            msg = 'ComponentData must be valid JSON format.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Extract component ID for geometry file checking
        component_id = component_json.get('_id', '')
        if not component_id:
            msg = 'Component data must contain a valid _id field.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate required fields for component creation
        required_fields = [
            'type', 'material', 'dataset', 'complexity', 'fragment',
            'assembly', 'geometry', 'bbx', 'bbx_origin', 'iframe'
        ]
        missing_fields = []
        for field in required_fields:
            if field not in component_json:
                missing_fields.append(field)

        if missing_fields:
            fields_str = ", ".join(missing_fields)
            msg = f'Component data missing required fields: {fields_str}'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate geometry structure
        geometry = component_json.get('geometry', {})
        if not geometry:
            msg = 'Component data must contain a geometry field.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Check if geometry has mesh, meshes, or extrusion
        has_mesh = 'mesh' in geometry
        has_meshes = 'meshes' in geometry
        has_extrusion = 'extrusion' in geometry

        # Count how many geometry types are present
        geometry_types_count = sum([has_mesh, has_meshes, has_extrusion])

        if geometry_types_count == 0:
            msg = ('Component geometry must contain either mesh, meshes, or '
                   'extrusion field.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        if geometry_types_count > 1:
            msg = ('Component geometry must contain only one of: mesh, '
                   'meshes, or extrusion.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate field types
        validation_errors = []

        # Check complexity is integer
        if 'complexity' in component_json:
            if not isinstance(component_json['complexity'], int):
                validation_errors.append('complexity must be an integer')

        # Check fragment is boolean
        if 'fragment' in component_json:
            if not isinstance(component_json['fragment'], bool):
                validation_errors.append('fragment must be a boolean')

        # Check assembly is boolean
        if 'assembly' in component_json:
            if not isinstance(component_json['assembly'], bool):
                validation_errors.append('assembly must be a boolean')

        # Check dataset is string
        if 'dataset' in component_json:
            if not isinstance(component_json['dataset'], str):
                validation_errors.append('dataset must be a string')

        # Check bbx is list of 3 numbers
        if 'bbx' in component_json:
            bbx = component_json['bbx']
            if not isinstance(bbx, list) or len(bbx) != 3:
                validation_errors.append('bbx must be a list of 3 numbers')
            elif not all(isinstance(x, (int, float)) for x in bbx):
                validation_errors.append('bbx must contain only numbers')

        # Check bbx_origin is list of 3 numbers
        if 'bbx_origin' in component_json:
            bbx_origin = component_json['bbx_origin']
            if not isinstance(bbx_origin, list) or len(bbx_origin) != 3:
                validation_errors.append(
                    'bbx_origin must be a list of 3 numbers')
            elif not all(isinstance(x, (int, float)) for x in bbx_origin):
                validation_errors.append(
                    'bbx_origin must contain only numbers')

        # Check color format if present
        if 'color' in component_json:
            color = component_json['color']
            if color is not None:  # color is optional
                if not isinstance(color, list) or len(color) != 3:
                    validation_errors.append(
                        'color must be a list of 3 integers')
                elif not all(isinstance(x, int) and 0 <= x <= 255
                             for x in color):
                    validation_errors.append(
                        'color must contain integers between 0-255')

        if validation_errors:
            errors_str = '\n'.join(validation_errors)
            msg = f'Component data validation errors:\n{errors_str}'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Check for geometry files
        files_status = self.check_geometry_files(component_id)
        has_geometry_files = files_status['detailed_obj']

        if has_geometry_files:
            self._addRemark(
                f'Found geometry files for component {component_id}'
            )
            if files_status['reduced_obj']:
                self._addRemark(
                    'Found both detailed and reduced geometry files'
                )
        else:
            self._addRemark(
                f'No geometry files found for component {component_id}'
            )

        if not Run:
            status_msg = 'Ready to add component'
            if has_geometry_files:
                status_msg += ' with geometry files'
            status_msg += ' (toggle Run to execute)'
            self.Component.Message = status_msg
            return AddedComponentData

        try:
            self.Component.Message = 'Adding component to database...'

            # Make authenticated request to add component
            response = auth_core.authorized_post(
                '/components/add/', json_body=component_json)

            if response.status_code == 201:
                # Successfully added component
                json_comp = response.json()
                component_id = json_comp.get('_id', 'Unknown')

                # Create datatree path
                ghp = Grasshopper.Kernel.Data.GH_Path(0)
                # Add component data to the datatree
                AddedComponentData.Add(json.dumps(json_comp), ghp)

                self._addRemark(
                    f'Successfully added component {component_id} to database'
                )
                self.Component.Message = f'Added component {component_id}'

                # Upload geometry files if they exist
                if has_geometry_files:
                    self.Component.Message = 'Uploading geometry files...'
                    upload_success = self.upload_geometry_files(
                        auth_core, component_id, files_status
                    )
                    if upload_success:
                        self._addRemark(
                            'Successfully uploaded all geometry files'
                        )
                        self.Component.Message = (
                            f'Added component {component_id} with geometry'
                        )
                    else:
                        self._addWarning(
                            'Component added but some geometry uploads failed'
                        )
                        self.Component.Message = (
                            f'Added component {component_id} '
                            '(geometry upload issues)'
                        )

            elif response.status_code == 400:
                msg = 'Invalid component data format.'
                self._addError(msg)
                self.Component.Message = msg

            elif response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            elif response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            elif response.status_code == 409:
                msg = 'Component already exists with this data.'
                self._addWarning(msg)
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
                            msg = (f'Component data validation failed:\n'
                                   f'{errors_str}')
                        else:
                            detail = error_detail["detail"]
                            msg = (f'Component data validation failed: '
                                   f'{detail}')
                    else:
                        msg = (f'Component data validation failed: '
                               f'{error_detail}')
                except (json.JSONDecodeError, KeyError):
                    msg = 'Component data validation failed.'
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

            return AddedComponentData

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
        AddedComponentData = Grasshopper.DataTree[System.Object]()
        return AddedComponentData
