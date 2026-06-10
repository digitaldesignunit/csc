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
ghenv.Component.Name = 'AddComponentSnapshot'  # NOQA
ghenv.Component.NickName = 'AddComponentSnapshot'  # NOQA
ghenv.Component.Category = 'DDU_CSC'  # NOQA
ghenv.Component.SubCategory = '2 Catalog Interface'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Creates a new snapshot for an existing identity via '
    'POST /identities/{id}/snapshots. Accepts CreateSnapshotRequest JSON '
    'from CreateComponentSnapshot and uploads staged PLY files from '
    'pending_snapshot_assets/{snapshot_id}/.'
)


class CSC_AddComponentSnapshot(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260609
    """

    def __init__(self):
        super().__init__()
        self.Component = ghenv.Component  # NOQA
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

    def BeforeRunScript(self):
        self.InputParams[0].Description = (
            'CreateSnapshotRequest JSON from CreateComponentSnapshot'
        )
        self.InputParams[1].Description = (
            'Toggle to execute the snapshot create operation'
        )
        i = 0
        if self.OutputParams[0].Name == 'out':
            i += 1
        self.OutputParams[0+i].Description = (
            'Compose response JSON ({identity, snapshot}) after create'
        )

    def get_auth_core_from_sticky(self):
        auth_core = sc.sticky.get('CSC_AuthCore')
        if auth_core is None:
            msg = ('No authentication found. Please use CSC_Session component '
                   'first.')
            self._addError(msg)
            self.Component.Message = msg
            return None
        return auth_core

    def get_pending_assets_root(self) -> str:
        if platform.system() == 'Windows':
            base_path = os.path.expandvars('%APPDATA%')
            return os.path.join(
                base_path, 'DDU_CSC', 'pending_snapshot_assets')
        base_path = os.path.expanduser('~')
        return os.path.join(
            base_path, 'Library', 'Application Support', 'DDU_CSC',
            'pending_snapshot_assets',
        )

    def get_snapshot_assets_dir(self, snapshot_id: str) -> str:
        return os.path.join(self.get_pending_assets_root(), snapshot_id)

    def load_staging_manifest(self, snapshot_id: str):
        manifest_path = os.path.join(
            self.get_snapshot_assets_dir(snapshot_id),
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

    def check_staged_ply_files(self, snapshot_id: str, manifest: dict) -> dict:
        assets_dir = self.get_snapshot_assets_dir(snapshot_id)
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

    def validate_snapshot_payload(self, payload: dict) -> list:
        errors = []
        required_fields = [
            'complexity', 'fragment', 'assembly', 'geometry', 'bbx',
            'bbx_origin', 'iframe', 'pca_frame',
        ]
        for field in required_fields:
            if field not in payload:
                errors.append(f'missing required field: {field}')

        identity_id = payload.get('identity_id', '')
        if not identity_id:
            errors.append('payload must contain identity_id')
        elif not self._validate_uuid(identity_id):
            errors.append('identity_id must be a valid UUID')

        snapshot_id = payload.get('_id', '')
        if not snapshot_id:
            errors.append('payload must contain _id (snapshot UUID)')
        elif not self._validate_uuid(snapshot_id):
            errors.append('_id must be a valid snapshot UUID')

        geometry = payload.get('geometry') or {}
        if not (
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
                    f'PLY upload timed out for primitive {primitive_index}.'
                )
                upload_success = False
                continue
            except requests.exceptions.ConnectionError:
                self._addWarning(
                    f'Connection lost uploading primitive {primitive_index}.'
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
                    f'Uploaded {resolution} PLY for primitive {primitive_index}'
                )
            else:
                detail = response.text
                try:
                    detail = response.json().get('detail', detail)
                except (json.JSONDecodeError, AttributeError):
                    pass
                self._addWarning(
                    f'Failed to upload {resolution} PLY '
                    f'({response.status_code}): {detail}'
                )
                upload_success = False

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
                        'Snapshot payload validation failed:\n'
                        + '\n'.join(lines)
                    )
                return f'Snapshot payload validation failed: {detail}'
            return f'Request failed: {error_detail}'
        except (json.JSONDecodeError, KeyError, AttributeError):
            return f'Request failed with status code {response.status_code}'

    def RunScript(self, SnapshotData: str, Run: bool):
        AddedSnapshotData = Grasshopper.DataTree[System.Object]()

        auth_core = self.get_auth_core_from_sticky()
        if auth_core is None:
            return AddedSnapshotData

        if not auth_core.is_valid():
            msg = ('Authentication expired. Please use CSC_Session '
                   'component to refresh.')
            self._addError(msg)
            self.Component.Message = msg
            return AddedSnapshotData

        if not SnapshotData:
            msg = 'Please provide CreateSnapshotRequest JSON.'
            self._addWarning(msg)
            self.Component.Message = msg
            return AddedSnapshotData

        try:
            payload = json.loads(SnapshotData)
        except json.JSONDecodeError:
            msg = 'SnapshotData must be valid JSON format.'
            self._addError(msg)
            self.Component.Message = msg
            return AddedSnapshotData

        validation_errors = self.validate_snapshot_payload(payload)
        if validation_errors:
            msg = 'Snapshot payload validation errors:\n' + '\n'.join(
                validation_errors)
            self._addError(msg)
            self.Component.Message = 'Validation failed'
            return AddedSnapshotData

        identity_id = payload['identity_id']
        snapshot_id = payload['_id']
        geometry = payload.get('geometry') or {}
        has_meshes = bool(geometry.get('meshes'))

        manifest = self.load_staging_manifest(snapshot_id)
        staged_status = None
        if has_meshes and manifest:
            if manifest.get('identity_id') != identity_id:
                self._addWarning(
                    'Manifest identity_id does not match payload identity_id'
                )
            staged_status = self.check_staged_ply_files(snapshot_id, manifest)
            if staged_status['pending']:
                self._addRemark(
                    f'Found {len(staged_status["pending"])} staged PLY file(s)'
                )
            if staged_status['missing']:
                missing_names = [
                    f'{item["primitive_index"]}/{item["resolution"]}.ply'
                    for item in staged_status['missing']
                ]
                self._addWarning(
                    'Manifest lists missing PLY files: '
                    + ', '.join(missing_names)
                )
        elif has_meshes:
            self._addRemark(
                f'No staging manifest for snapshot {snapshot_id}; '
                'inline mesh primitives only'
            )

        if not Run:
            status_msg = (
                f'Ready to create snapshot {snapshot_id} '
                f'for identity {identity_id}'
            )
            if staged_status and staged_status['pending']:
                status_msg += (
                    f' with {len(staged_status["pending"])} PLY file(s)'
                )
            status_msg += ' (toggle Run to execute)'
            self.Component.Message = status_msg
            return AddedSnapshotData

        request_body = dict(payload)
        request_body.pop('identity_id', None)

        try:
            self.Component.Message = 'Creating snapshot version...'

            response = auth_core.authorized_post(
                f'/identities/{identity_id}/snapshots',
                json_body=request_body,
            )

            if response.status_code == 201:
                compose = response.json()
                snapshots = compose.get('snapshots') or []
                snapshot_doc = snapshots[0] if snapshots else {}
                created_snapshot_id = snapshot_doc.get('_id', snapshot_id)

                ghp = Grasshopper.Kernel.Data.GH_Path(0)
                AddedSnapshotData.Add(json.dumps(compose), ghp)

                self._addRemark(
                    f'Created snapshot {created_snapshot_id} '
                    f'for identity {identity_id}'
                )
                self.Component.Message = (
                    f'Created snapshot {created_snapshot_id}'
                )

                if staged_status and staged_status['pending']:
                    self.Component.Message = 'Uploading staged PLY files...'
                    upload_success = self.upload_staged_ply_files(
                        auth_core,
                        created_snapshot_id,
                        staged_status['pending'],
                    )
                    if upload_success:
                        self.Component.Message = (
                            f'Created snapshot {created_snapshot_id} with PLY'
                        )
                    else:
                        self._addWarning(
                            'Snapshot created but some PLY uploads failed'
                        )

                return AddedSnapshotData

            if response.status_code in (400, 422):
                msg = self._format_http_error(response)
                self._addError(msg)
                self.Component.Message = 'Create failed (validation)'
                return AddedSnapshotData

            if response.status_code == 401:
                msg = 'Authentication failed. Please sign in again.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedSnapshotData

            if response.status_code == 403:
                msg = 'Access denied. Insufficient permissions.'
                self._addError(msg)
                self.Component.Message = msg
                return AddedSnapshotData

            if response.status_code == 404:
                msg = f'Identity {identity_id} not found.'
                self._addWarning(msg)
                self.Component.Message = msg
                return AddedSnapshotData

            if response.status_code == 409:
                msg = 'Snapshot already exists or version conflict.'
                self._addWarning(msg)
                self.Component.Message = msg
                return AddedSnapshotData

            if response.status_code == 500:
                msg = 'Server error. Please try again later.'
                self._addWarning(msg)
                self.Component.Message = msg
                return AddedSnapshotData

            msg = self._format_http_error(response)
            self._addError(msg)
            self.Component.Message = msg
            return AddedSnapshotData

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

        return AddedSnapshotData
