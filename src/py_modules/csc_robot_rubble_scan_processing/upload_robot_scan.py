#!/usr/bin/env python3
"""
Robot Scan Upload Module

Uploads a processed scan as a new catalog identity plus version-0 snapshot:

* POST /identities  (CreateComponentRequest JSON)
* PUT  /snapshots/{snapshot_id}/meshes/{i}/{reduced|detailed}  (PLY)

Programmatic Usage:
    from upload_robot_scan import upload_scan_by_path
    success = upload_scan_by_path('/path/to/uuid-folder', credentials)
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scan_upload.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
PLY_UPLOAD_TIMEOUT = 300
CREDENTIALS_FILE = "csc_credentials.json"


def load_credentials(credentials_path: Optional[str] = None) -> Dict[str, str]:
    """Load authentication credentials from JSON file"""
    if credentials_path is None:
        credentials_path = CREDENTIALS_FILE

    cred_path = Path(credentials_path)

    if not cred_path.exists():
        logger.error(f"[ERROR] Credentials file not found: {cred_path}")
        logger.error("   Please create a csc_credentials.json file with:")
        logger.error("   {")
        logger.error("     \"server\": \"http://your-api-url/api/backend\",")
        logger.error("     \"user\": \"your-username\",")
        logger.error("     \"pwd\": \"your-password\"")
        logger.error("   }")
        sys.exit(1)

    try:
        with open(cred_path, 'r', encoding='utf-8') as handle:
            credentials = json.load(handle)

        required_fields = ['server', 'user', 'pwd']
        missing_fields = [field for field in required_fields
                          if field not in credentials]

        if missing_fields:
            logger.error(
                f"[ERROR] Missing required fields in credentials "
                f"file: {missing_fields}"
            )
            sys.exit(1)

        logger.info(f"[OK] Loaded credentials from: {cred_path}")
        logger.info(f"[SERVER] Server: {credentials['server']}")
        logger.info(f"[USER] User: {credentials['user']}")
        return credentials

    except json.JSONDecodeError as exc:
        logger.error(f"[ERROR] Invalid JSON in credentials file: {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"[ERROR] Error loading credentials: {exc}")
        sys.exit(1)


class ScanUploader:
    """Handles uploading scan data to the CSC backend"""

    def __init__(
            self,
            credentials: Dict[str, str],
            timeout: int = DEFAULT_TIMEOUT):
        self.api_base_url = credentials['server'].rstrip('/')
        self.username = credentials['user']
        self.password = credentials['pwd']
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy and JWT auth."""
        session = requests.Session()

        self.jwt_token = self._authenticate()
        if not self.jwt_token:
            raise Exception("Failed to authenticate with API")

        session.headers.update({
            'Authorization': f'Bearer {self.jwt_token}'
        })

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _authenticate(self) -> Optional[str]:
        """Authenticate with the API and return JWT token"""
        try:
            logger.info("[AUTH] Authenticating with API...")
            auth_data = {
                'username': self.username,
                'password': self.password
            }
            response = requests.post(
                f"{self.api_base_url}/auth/token",
                data=auth_data,
                timeout=self.timeout
            )
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                if access_token:
                    logger.info("[OK] Authentication successful")
                    return access_token
                logger.error("[ERROR] No access token in response")
                return None
            logger.error(
                f"[ERROR] Authentication failed: {response.status_code}"
            )
            logger.error(f"   Response: {response.text}")
            return None
        except Exception as exc:
            logger.error(f"[ERROR] Authentication error: {exc}")
            return None

    def test_connection(self) -> bool:
        """Test connection to the identities API"""
        try:
            response = self.session.get(
                f"{self.api_base_url}/identities",
                params={'page': 1, 'size': 1},
                timeout=self.timeout
            )
            if response.status_code == 200:
                logger.info("[OK] API connection successful")
                return True
            logger.error(
                f"[ERROR] API connection failed: {response.status_code}"
            )
            return False
        except Exception as exc:
            logger.error(f"[ERROR] API connection error: {exc}")
            return False

    def upload_identity_json(
        self, component_path: Path
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        POST CreateComponentRequest to /identities.

        Returns (success, identity_id, snapshot_id).
        """
        try:
            logger.info(
                f"[FILE] Creating identity from: {component_path.name}"
            )
            with open(component_path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)

            response = self.session.post(
                f"{self.api_base_url}/identities",
                json=payload,
                timeout=self.timeout
            )
            if response.status_code == 201:
                compose = response.json()
                identity_doc = compose.get('identity') or {}
                snapshots = compose.get('snapshots') or []
                snapshot_doc = snapshots[0] if snapshots else {}
                identity_id = identity_doc.get('_id') or payload.get('_id')
                snapshot_id = snapshot_doc.get('_id')
                logger.info(
                    f"[OK] Identity created: {identity_id} "
                    f"(v0 snapshot {snapshot_id})"
                )
                return True, identity_id, snapshot_id

            if response.status_code == 409:
                logger.error(
                    "[ERROR] Identity already exists "
                    f"({component_path.stem}); not uploading a second v0"
                )
                logger.error(f"   Response: {response.text}")
                return False, None, None

            logger.error(
                "[ERROR] Failed to create identity: "
                f"{response.status_code}"
            )
            logger.error(f"   Response: {response.text}")
            return False, None, None

        except Exception as exc:
            logger.error(f"[ERROR] Error uploading identity JSON: {exc}")
            return False, None, None

    def upload_mesh_ply(
            self,
            snapshot_id: str,
            primitive_index: int,
            resolution: str,
            ply_path: Path
    ) -> bool:
        """PUT a mesh PLY onto a snapshot primitive."""
        try:
            logger.info(
                f"[UPLOAD] Uploading {resolution} PLY for primitive "
                f"{primitive_index}: {ply_path.name}"
            )
            endpoint = (
                f"{self.api_base_url}/snapshots/{snapshot_id}/meshes/"
                f"{primitive_index}/{resolution}"
            )
            with open(ply_path, 'rb') as handle:
                files = {
                    'mesh_file': (
                        ply_path.name,
                        handle,
                        'application/octet-stream',
                    )
                }
                response = self.session.put(
                    endpoint,
                    files=files,
                    timeout=PLY_UPLOAD_TIMEOUT,
                )

            if response.status_code == 200:
                logger.info(
                    f"[OK] Uploaded {resolution} PLY "
                    f"for primitive {primitive_index}"
                )
                return True
            logger.error(
                f"[ERROR] Failed to upload {resolution} PLY for "
                f"primitive {primitive_index}: {response.status_code}"
            )
            logger.error(f"   Response: {response.text}")
            return False
        except Exception as exc:
            logger.error(
                f"[ERROR] Error uploading {resolution} PLY for "
                f"primitive {primitive_index}: {exc}"
            )
            return False

    def _collect_staged_ply_files(self, transcode_folder: Path) -> List[Dict]:
        """Read ply_manifest.json, falling back to meshes/*/*.ply on disk."""
        manifest_path = transcode_folder / 'ply_manifest.json'
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as handle:
                manifest = json.load(handle)
            files = manifest.get('files') or []
            staged = []
            for entry in files:
                rel = entry.get('path')
                if not rel:
                    continue
                path = transcode_folder / rel
                if path.exists():
                    staged.append({
                        'primitive_index': int(entry['primitive_index']),
                        'resolution': entry['resolution'],
                        'path': path,
                    })
                else:
                    logger.warning(f"[WARNING] Staged PLY missing: {rel}")
            if staged:
                return staged

        staged = []
        meshes_root = transcode_folder / 'meshes'
        if not meshes_root.exists():
            return staged
        for primitive_dir in sorted(meshes_root.iterdir()):
            if not primitive_dir.is_dir():
                continue
            try:
                primitive_index = int(primitive_dir.name)
            except ValueError:
                continue
            for resolution in ('reduced', 'detailed'):
                path = primitive_dir / f'{resolution}.ply'
                if path.exists():
                    staged.append({
                        'primitive_index': primitive_index,
                        'resolution': resolution,
                        'path': path,
                    })
        return staged

    def upload_scan_folder(self, scan_folder: Path) -> bool:
        """Upload identity JSON and staged mesh PLY files."""
        component_id = scan_folder.name
        logger.info(f"[START] Starting upload for scan: {component_id}")

        transcode_folder = scan_folder / "transcode"
        component_json = transcode_folder / f"{component_id}.json"

        if not transcode_folder.exists():
            logger.error(
                f"[ERROR] Transcode folder not found: {transcode_folder}"
            )
            return False

        if not component_json.exists():
            logger.error(f"[ERROR] Component JSON not found: {component_json}")
            return False

        success, identity_id, snapshot_id = self.upload_identity_json(
            component_json
        )
        if not success or not snapshot_id:
            return False

        staged = self._collect_staged_ply_files(transcode_folder)
        if not staged:
            logger.info(
                "[WARNING] No staged mesh PLY files; "
                "identity uses inline primitives only"
            )
            logger.info(f"[OK] Successfully uploaded scan: {component_id}")
            return True

        upload_success = True
        for entry in staged:
            if not self.upload_mesh_ply(
                    snapshot_id,
                    entry['primitive_index'],
                    entry['resolution'],
                    entry['path']
            ):
                upload_success = False

        if upload_success:
            logger.info(
                f"[OK] Successfully uploaded identity {identity_id} "
                f"and {len(staged)} PLY file(s)"
            )
        else:
            logger.error(
                f"[ERROR] Some PLY files failed to upload for scan: "
                f"{component_id}"
            )
        return upload_success


def upload_scan_by_path(scan_folder_path: str, credentials: Dict[str, str],
                        timeout: int = DEFAULT_TIMEOUT) -> bool:
    """
    Upload a single processed scan folder by its path.

    Args:
        scan_folder_path (str): Path to the UUID-named scan folder
        credentials (Dict[str, str]): API credentials with 'server',
            'user', 'pwd'
        timeout (int): Request timeout in seconds (default: 30)
    """
    scan_path = Path(scan_folder_path)

    if not scan_path.exists():
        logger.error(f"[ERROR] Scan folder does not exist: {scan_folder_path}")
        return False

    component_id = scan_path.name
    import uuid
    try:
        uuid.UUID(component_id)
    except ValueError:
        logger.error(f"[ERROR] Invalid UUID folder name: {component_id}")
        return False

    logger.info(f"[UPLOAD] Uploading scan folder: {component_id}")

    try:
        uploader = ScanUploader(credentials, timeout)
        if not uploader.test_connection():
            logger.error("[ERROR] Cannot connect to API")
            return False
        return uploader.upload_scan_folder(scan_path)
    except Exception as exc:
        logger.error(f"[ERROR] Upload error: {exc}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_robot_scan.py <scan_folder_path> "
              "[credentials_file]")
        sys.exit(1)

    scan_path = sys.argv[1]
    credentials_file = sys.argv[2] if len(sys.argv) > 2 else None

    credentials = load_credentials(credentials_file)
    success = upload_scan_by_path(scan_path, credentials)
    if not success:
        sys.exit(1)
