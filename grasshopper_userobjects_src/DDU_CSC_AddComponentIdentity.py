#! python3
# -*- coding: utf-8 -*-
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json  # NOQA
import os  # NOQA
import platform  # NOQA
import uuid  # NOQA

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import requests  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Grasshopper  # NOQA
import Rhino  # NOQA
import scriptcontext as sc  # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'AddComponentIdentity'  # NOQA
ghenv.Component.NickName = 'AddComponentIdentity'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Creates a catalog identity and version-0 snapshot via POST /identities. '
    'Accepts CreateComponentRequest JSON from CreateComponentIdentity, '
    'uploads staged binary PLY mesh files from pending_identity_assets/, '
    'and optionally consumes a pending transmitted component ID.'
)


class CSC_AddComponentIdentity(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260609
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
            'CreateComponentRequest JSON from CreateComponentIdentity'
        )
        self.InputParams[1].Description = (
            'Toggle to execute the create operation'
        )
        # Initialize output param descriptions
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Compose response JSON ({identity, snapshot}) '
            'from POST /identities'
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

    def get_pending_assets_root(self) -> str:
        """
        Get the geometry folder path for a component.
        Returns the appropriate path based on the operating system.
        """
        if platform.system() == 'Windows':
            base_path = os.path.expandvars('%APPDATA%')
            return os.path.join(
                base_path, 'DDU_CSC', 'pending_identity_assets')
        base_path = os.path.expanduser('~')
        return os.path.join(
            base_path, 'Library', 'Application Support', 'DDU_CSC',
            'pending_identity_assets',
        )

    def get_identity_assets_dir(self, identity_id: str) -> str:
        return os.path.join(self.get_pending_assets_root(), identity_id)

    def load_staging_manifest(self, identity_id: str):
        manifest_path = os.path.join(
            self.get_identity_assets_dir(identity_id),
            'manifest.json',
        )
        if not os.path.isfile(manifest_path):
            return None
        try:
            with open(manifest_path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._addWarning(f'Failed to read staging manifest: {exc}')
            return None

    def check_staged_ply_files(self, identity_id: str, manifest: dict) -> dict:
        assets_dir = self.get_identity_assets_dir(identity_id)
        mesh_primitives = manifest.get('mesh_primitives') or {}
        pending = []
        missing = []

        for index_str, resolutions in mesh_primitives.items():
            if not isinstance(resolutions, list):
                continue
            for resolution in resolutions:
                rel_path = os.path.join(
                    'meshes', str(index_str), f'{resolution}.ply')
                full_path = os.path.join(assets_dir, rel_path)
                entry = {
                    'primitive_index': str(index_str),
                    'resolution': resolution,
                    'path': full_path,
                }
                if os.path.isfile(full_path):
                    pending.append(entry)
                else:
                    missing.append(entry)

        return {
            'assets_dir': assets_dir,
            'pending': pending,
            'missing': missing,
        }

    def validate_create_payload(self, payload: dict) -> list:
        errors = []
        required_fields = [
            'type', 'material', 'dataset', 'complexity', 'fragment',
            'assembly', 'geometry', 'bbx', 'bbx_origin', 'iframe',
            'pca_frame',
        ]
        for field in required_fields:
            if field not in payload:
                errors.append(f'missing required field: {field}')

        identity_id = payload.get('_id', '')
        if not identity_id:
            errors.append('payload must contain a valid _id (identity UUID)')
        elif not self._validate_uuid(identity_id):
            errors.append('_id must be a valid UUID')

        if 'complexity' in payload and not isinstance(payload['complexity'], int):  # NOQA
            errors.append('complexity must be an integer')
        if 'fragment' in payload and not isinstance(payload['fragment'], bool):
            errors.append('fragment must be a boolean')
        if 'assembly' in payload and not isinstance(payload['assembly'], bool):
            errors.append('assembly must be a boolean')
        if 'dataset' in payload and not isinstance(payload['dataset'], str):
            errors.append('dataset must be a string')

        for axis_field in ('bbx', 'bbx_origin'):
            values = payload.get(axis_field)
            if values is not None:
                if (not isinstance(values, list) or len(values) != 3 or
                        not all(isinstance(x, (int, float)) for x in values)):
                    errors.append(f'{axis_field} must be a list of 3 numbers')

        for frame_field in ('iframe', 'pca_frame'):
            if frame_field in payload and not isinstance(
                    payload[frame_field], dict):
                errors.append(f'{frame_field} must be a frame object')

        color = payload.get('color')
        if color is not None:
            if (not isinstance(color, list) or len(color) != 3 or
                    not all(isinstance(x, int) and 0 <= x <= 255 for x in color)):  # NOQA
                errors.append('color must be a list of 3 integers (0-255)')

        geometry = payload.get('geometry') or {}
        if not geometry:
            errors.append('geometry must be present')
        elif not (
            geometry.get('meshes')
            or geometry.get('extrusions')
            or geometry.get('point_clouds')
        ):
            errors.append(
                'geometry must include meshes, extrusions, or point_clouds'
            )

        return errors

    def _validate_uuid(self, uuid_to_test: str, version: int = 4) -> bool:
        try:
            uuid_obj = uuid.UUID(uuid_to_test, version=version)
        except ValueError:
            return False
        return str(uuid_obj) == uuid_to_test

    def upload_staged_ply_files(
            self,
            auth_core,
            snapshot_id: str,
            identity_id: str,
            staged_files: list) -> bool:
        if not staged_files:
            return True

        upload_success = True
        headers = auth_core.auth_header()

        for entry in staged_files:
            primitive_index = entry['primitive_index']
            resolution = entry['resolution']
            file_path = entry['path']
            self.Component.Message = (
                f'Uploading PLY primitive {primitive_index} ({resolution})...'
            )
            self._addRemark(
                f'Uploading {os.path.basename(file_path)} for snapshot '
                f'{snapshot_id}'
            )

            try:
                with open(file_path, 'rb') as handle:
                    response = requests.put(
                        auth_core.base_url + (
                            f'/snapshots/{snapshot_id}/meshes/'
                            f'{primitive_index}/{resolution}'
                        ),
                        files={
                            'mesh_file': (
                                os.path.basename(file_path),
                                handle,
                                'application/octet-stream',
                            ),
                        },
                        headers=headers,
                        timeout=300,
                    )
            except requests.exceptions.Timeout:
                self._addWarning(
                    f'PLY upload timed out for primitive {primitive_index} '
                    f'({resolution}).'
                )
                upload_success = False
                continue
            except requests.exceptions.ConnectionError:
                self._addWarning(
                    f'Connection lost uploading primitive {primitive_index} '
                    f'({resolution}).'
                )
                upload_success = False
                continue
            except OSError as exc:
                self._addWarning(
                    f'Could not read staged PLY {file_path}: {exc}'
                )
                upload_success = False
                continue

            if response.status_code == 200:
                self._addRemark(
                    f'Uploaded {resolution} PLY '
                    f'for primitive {primitive_index}'
                )
            else:
                detail = response.text
                try:
                    detail = response.json().get('detail', detail)
                except (json.JSONDecodeError, AttributeError):
                    pass
                self._addWarning(
                    f'Failed to upload {resolution} PLY for primitive '
                    f'{primitive_index} ({response.status_code}): {detail}'
                )
                upload_success = False

        if upload_success:
            self._addRemark(
                f'All staged PLY files uploaded for identity {identity_id}'
            )
        return upload_success

    def _format_http_error(self, response) -> str:
        try:
            error_detail = response.json()
            if 'detail' in error_detail:
                detail = error_detail['detail']
                if isinstance(detail, list):
                    lines = []
                    for error in detail:
                        field = error.get('loc', ['unknown'])[-1]
                        message = error.get('msg', 'validation error')
                        lines.append(f'{field}: {message}')
                    return (
                        'Create payload validation '
                        'failed:\n' + '\n'.join(lines)
                    )
                return f'Create payload validation failed: {detail}'
            return f'Request failed: {error_detail}'
        except (json.JSONDecodeError, KeyError, AttributeError):
            return f'Request failed with status code {response.status_code}'

    def RunScript(self, ComponentData: str, Run: bool):
        # Set up output trees and results tuple
        AddedComponentData = Grasshopper.DataTree[System.Object]()

        # Get AuthCore instance from sticky storage
        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return AddedComponentData

        # Check if authentication is valid
        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate ComponentData input
        if not ComponentData:
            msg = 'Please provide CreateComponentRequest JSON to add.'
            self._addWarning(msg)
            self.Component.Message = msg
            return AddedComponentData

        # Validate JSON format
        try:
            payload = json.loads(ComponentData)
        except json.JSONDecodeError:
            msg = 'ComponentData must be valid JSON format.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        validation_errors = self.validate_create_payload(payload)
        if validation_errors:
            msg = 'Create payload validation errors:\n' + '\n'.join(
                validation_errors)
            self._addError(msg)
            self.Component.Message = 'Validation failed'
            return AddedComponentData

        identity_id = payload['_id']
        geometry = payload.get('geometry') or {}
        has_meshes = bool(geometry.get('meshes'))

        manifest = self.load_staging_manifest(identity_id)
        staged_status = None
        if has_meshes and manifest:
            staged_status = self.check_staged_ply_files(identity_id, manifest)
            if staged_status['pending']:
                self._addRemark(
                    f'Found {len(staged_status["pending"])}'
                    ' staged PLY file(s) '
                    f'for identity {identity_id}'
                )
            if staged_status['missing']:
                missing_names = [
                    f'{item["primitive_index"]}/{item["resolution"]}.ply'
                    for item in staged_status['missing']
                ]
                self._addWarning(
                    'Manifest lists PLY files that are missing on disk: '
                    + ', '.join(missing_names)
                )
        elif has_meshes:
            self._addRemark(
                f'No staging manifest for identity {identity_id}; '
                'inline mesh primitives only'
            )

        if not Run:
            status_msg = f'Ready to create identity {identity_id}'
            if staged_status and staged_status['pending']:
                status_msg += (
                    f' with {len(staged_status["pending"])} '
                    'PLY file(s)'
                )
            status_msg += ' (toggle Run to execute)'
            self.Component.Message = status_msg
            return AddedComponentData

        try:
            self.Component.Message = 'Creating identity and snapshot...'

            response = auth_core.authorized_post(
                '/identities',
                json_body=payload,
            )

            if response.status_code == 201:
                compose = response.json()
                identity_doc = compose.get('identity') or {}
                snapshot_doc = compose.get('snapshot') or {}
                created_identity_id = identity_doc.get('_id', identity_id)
                snapshot_id = snapshot_doc.get('_id', '')

                # Create datatree path and add component to tree
                ghp = Grasshopper.Kernel.Data.GH_Path(0)
                AddedComponentData.Add(json.dumps(compose), ghp)

                self._addRemark(
                    f'Created identity {created_identity_id} '
                    f'(snapshot {snapshot_id})'
                )
                self.Component.Message = (
                    f'Created identity {created_identity_id}'
                )

                # Consume pending transmitted ID after successful DB insert.
                # This is intentionally non-fatal for AddComponent: if consume
                # fails, we keep the added component result and only warn.
                try:
                    consume_response = auth_core.authorized_post(
                        '/component_id_transmission/consume',
                        json_body={'identity_id': created_identity_id},
                    )
                    if consume_response.status_code == 200:
                        consume_payload = consume_response.json()
                        if consume_payload.get('consumed', False):
                            self._addRemark(
                                'Consumed pending transmitted ID after create.'
                            )
                        else:
                            self._addRemark(
                                'No matching transmitted ID to consume.'
                            )
                    else:
                        self._addWarning(
                            'Identity created, but transmitted ID consume '
                            f'failed ({consume_response.status_code}).'
                        )
                except Exception as exc:
                    self._addWarning(
                        'Identity created, but transmitted '
                        'ID consume errored: '
                        f'{str(exc)}'
                    )

                if (
                    snapshot_id
                    and staged_status
                    and staged_status['pending']
                ):
                    self.Component.Message = 'Uploading staged PLY files...'
                    upload_success = self.upload_staged_ply_files(
                        auth_core,
                        snapshot_id,
                        created_identity_id,
                        staged_status['pending'],
                    )
                    if upload_success:
                        self.Component.Message = (
                            f'Created identity {created_identity_id} with PLY'
                        )
                    else:
                        self._addWarning(
                            'Identity created but some PLY uploads failed'
                        )
                        self.Component.Message = (
                            f'Created identity {created_identity_id} '
                            '(PLY upload issues)'
                        )

                return AddedComponentData

            if response.status_code in (400, 422):
                msg = self._format_http_error(response)
                self._addError(msg)
                self.Component.Message = 'Create failed (validation)'
                return AddedComponentData

            if response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            if response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedComponentData

            if response.status_code == 409:
                msg = 'Identity already exists with this _id.'
                self._addWarning(msg)
                self.Component.Message = msg
                return AddedComponentData

            if response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)
                self.Component.Message = msg
                return AddedComponentData

            msg = self._format_http_error(response)
            self._addError(msg)
            self.Component.Message = msg
            return AddedComponentData

        except requests.exceptions.ConnectionError as exc:
            msg = 'Cannot connect to server. Please check your connection.'
            self._addError(msg + f'\nFull Error: {str(exc)}')
            self.Component.Message = msg

        except requests.exceptions.Timeout as exc:
            msg = 'Request timeout. Server may be slow.'
            self._addError(msg + f'\nFull Error: {str(exc)}')
            self.Component.Message = msg

        except requests.exceptions.RequestException as exc:
            msg = f'Request error: {str(exc)}'
            self._addError(msg)
            self.Component.Message = msg

        except Exception as exc:
            msg = f'Unexpected error: {str(exc)}'
            self._addError(msg)
            self.Component.Message = msg

        return AddedComponentData
