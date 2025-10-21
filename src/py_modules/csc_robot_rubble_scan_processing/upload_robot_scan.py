#!/usr/bin/env python3
"""
Robot Scan Upload Module

Uploads processed scan data to the CSC backend API.

Programmatic Usage:
    from upload_robot_scan import upload_scan_by_path
    success = upload_scan_by_path('/path/to/uuid-folder', credentials)
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
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

# Default API configuration
DEFAULT_API_BASE_URL = "https://api.ddu.uber.space"
DEFAULT_TIMEOUT = 30
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
        with open(cred_path, 'r') as f:
            credentials = json.load(f)

        # Validate required fields
        required_fields = ['server', 'user', 'pwd']
        missing_fields = [field for field in required_fields
                          if field not in credentials]

        if missing_fields:
            logger.error(f"[ERROR] Missing required fields in credentials "
                         f"file: {missing_fields}")
            sys.exit(1)

        logger.info(f"[OK] Loaded credentials from: {cred_path}")
        logger.info(f"[SERVER] Server: {credentials['server']}")
        logger.info(f"[USER] User: {credentials['user']}")

        return credentials

    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] Invalid JSON in credentials file: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[ERROR] Error loading credentials: {e}")
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
        """
        Create a requests session with retry strategy and JWT authentication
        """
        session = requests.Session()

        # Authenticate and get JWT token
        self.jwt_token = self._authenticate()
        if not self.jwt_token:
            raise Exception("Failed to authenticate with API")

        # Set up JWT authentication
        session.headers.update({
            'Authorization': f'Bearer {self.jwt_token}'
        })

        # Configure retry strategy
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

            # Prepare authentication data
            auth_data = {
                'username': self.username,
                'password': self.password
            }

            # Authenticate
            response = requests.post(
                f"{self.api_base_url}/auth/token",
                data=auth_data,  # Use form data for OAuth2PasswordRequestForm
                timeout=self.timeout
            )

            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                if access_token:
                    logger.info("[OK] Authentication successful")
                    return access_token
                else:
                    logger.error("[ERROR] No access token in response")
                    return None
            else:
                logger.error(
                    f"[ERROR] Authentication failed: {response.status_code}"
                )
                logger.error(f"   Response: {response.text}")
                return None

        except Exception as e:
            logger.error(f"[ERROR] Authentication error: {e}")
            return None

    def test_connection(self) -> bool:
        """Test connection to the API"""
        try:
            response = self.session.get(
                f"{self.api_base_url}/components",
                timeout=self.timeout
            )
            if response.status_code == 200:
                logger.info("[OK] API connection successful")
                return True
            else:
                logger.error(
                    f"[ERROR] API connection failed: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"[ERROR] API connection error: {e}")
            return False

    def upload_component_json(
        self, component_path: Path
    ) -> Tuple[bool, Optional[str]]:
        """Upload component JSON file"""
        try:
            logger.info(
                f"[FILE] Uploading component JSON: {component_path.name}"
            )
            # Read component data
            with open(component_path, 'r') as f:
                component_data = json.load(f)
            # Upload component
            response = self.session.post(
                f"{self.api_base_url}/components/add/",
                json=component_data,
                timeout=self.timeout
            )
            if response.status_code == 201:
                result = response.json()
                component_id = result.get('_id')
                logger.info(
                    f"[OK] Component uploaded successfully: {component_id}"
                )
                return True, component_id
            elif response.status_code == 409:
                # Component already exists, extract ID from the path
                component_id = component_path.stem
                logger.info(
                    "[OK] Component already exists, using existing "
                    f"ID: {component_id}"
                )
                return True, component_id
            else:
                logger.error(
                    "[ERROR] Failed to upload component: "
                    f"{response.status_code}"
                )
                logger.error(f"   Response: {response.text}")
                return False, None

        except Exception as e:
            logger.error(f"[ERROR] Error uploading component JSON: {e}")
            return False, None

    def upload_geometry_file(
            self,
            component_id: str,
            geometry_path: Path,
            geometry_type: str
    ) -> bool:
        """Upload geometry file (OBJ)"""
        try:
            logger.info(
                f"[UPLOAD] Uploading {geometry_type} geometry: "
                f"{geometry_path.name}"
            )
            # Determine the correct endpoint
            if geometry_type == "detailed":
                endpoint = (
                    f"{self.api_base_url}/components/"
                    f"{component_id}/geometry/add_detailed"
                )
            elif geometry_type == "reduced":
                endpoint = (
                    f"{self.api_base_url}/components/"
                    f"{component_id}/geometry/add_reduced"
                )
            else:
                logger.error(f"[ERROR] Unknown geometry type: {geometry_type}")
                return False
            # Upload geometry file
            with open(geometry_path, 'rb') as f:
                files = {'mesh_file': (geometry_path.name,
                                       f,
                                       'application/octet-stream')}
                response = self.session.post(
                    endpoint,
                    files=files,
                    timeout=self.timeout * 3  # Longer timeout for large files
                )

            if response.status_code == 200:
                logger.info(
                    f"[OK] {geometry_type.title()} geometry uploaded "
                    "successfully"
                )
                return True
            else:
                logger.error(
                    f"[ERROR] Failed to upload {geometry_type} "
                    f"geometry: {response.status_code}"
                )
                logger.error(f"   Response: {response.text}")
                return False

        except Exception as e:
            logger.error(
                f"[ERROR] Error uploading {geometry_type} geometry: {e}"
            )
            return False

    def upload_scan_folder(self, scan_folder: Path) -> bool:
        """Upload all files from a processed scan folder"""
        component_id = scan_folder.name
        logger.info(f"[START] Starting upload for scan: {component_id}")

        # Check if folder contains required files
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

        # Upload component JSON
        success, uploaded_component_id = self.upload_component_json(
            component_json
        )
        if not success:
            return False

        # Upload geometry files
        geometry_files = [
            ("detailed", "mesh.obj"),
            ("reduced", "mesh_reduced.obj")
        ]

        upload_success = True
        for geometry_type, filename in geometry_files:
            geometry_path = transcode_folder / filename
            if geometry_path.exists():
                if not self.upload_geometry_file(
                        uploaded_component_id,
                        geometry_path,
                        geometry_type
                ):
                    upload_success = False
            else:
                logger.info(
                    f"[WARNING] {geometry_type.title()} geometry not found: "
                    f"{filename}"
                )

        if upload_success:
            logger.info(f"[OK] Successfully uploaded scan: {component_id}")
        else:
            logger.error(
                f"[ERROR] Some files failed to upload for scan: {component_id}"
            )

        return upload_success

    def _is_valid_uuid(self, folder_name: str) -> bool:
        """Check if folder name is a valid UUID"""
        import uuid
        try:
            uuid.UUID(folder_name)
            return True
        except ValueError:
            return False


def upload_scan_by_path(scan_folder_path: str, credentials: Dict[str, str],
                        timeout: int = DEFAULT_TIMEOUT) -> bool:
    """
    Upload a single scan folder by its path (programmatic interface).

    This function provides a programmatic interface for uploading scan data
    without requiring command-line arguments or folder watching.

    Args:
        scan_folder_path (str): Path to the UUID-named scan folder to upload
        credentials (Dict[str, str]): API credentials containing 'server',
            'user', 'pwd'
        timeout (int): Request timeout in seconds (default: 30)

    Returns:
        bool: True if upload was successful, False otherwise

    Example:
        credentials = {
            'server': 'https://api.ddu.uber.space',
            'user': 'your-username',
            'pwd': 'your-password'
        }
        success = upload_scan_by_path('/path/to/scan/folder/uuid-12345',
                                      credentials)
    """
    scan_path = Path(scan_folder_path)

    if not scan_path.exists():
        logger.error(f"[ERROR] Scan folder does not exist: {scan_folder_path}")
        return False

    # Extract component ID from folder name
    component_id = scan_path.name

    # Validate UUID
    import uuid
    try:
        uuid.UUID(component_id)
    except ValueError:
        logger.error(f"[ERROR] Invalid UUID folder name: {component_id}")
        return False

    logger.info(f"[UPLOAD] Uploading scan folder: {component_id}")

    # Create uploader and upload
    try:
        uploader = ScanUploader(credentials, timeout)

        # Test connection
        if not uploader.test_connection():
            logger.error("[ERROR] Cannot connect to API")
            return False

        # Upload the scan folder
        return uploader.upload_scan_folder(scan_path)

    except Exception as e:
        logger.error(f"[ERROR] Upload error: {e}")
        return False


if __name__ == "__main__":
    # Simple CLI for testing
    import sys
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
