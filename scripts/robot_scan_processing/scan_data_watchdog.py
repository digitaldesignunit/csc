#!/usr/bin/env python3
"""
Scan Data Watchdog Script

This script monitors two folders and automatically processes scan data:
1. Watches 'scans_to_process' for new scan folders
2. Processes them and moves to 'scans_processed'
3. Watches 'scans_processed' for new processed folders
4. Uploads them to the backend API

Usage:
    python scan_data_watchdog.py <scans_to_process> <scans_processed> [--api-base-url URL]  # NOQA

Requirements:
    - watchdog
    - requests
"""

import sys
import time
import argparse
import logging
import subprocess
import json
from pathlib import Path
from typing import Set, Optional, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scan_watchdog.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Script paths (relative to this script)
SCRIPT_DIR = Path(__file__).parent
PROCESS_SCRIPT = SCRIPT_DIR / "process_robot_scan.py"
UPLOAD_SCRIPT = SCRIPT_DIR / "upload_robot_scan.py"
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
            logger.error(
                "[ERROR] Missing required fields in credentials "
                f"file: {missing_fields}"
            )
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


class ScanProcessingHandler(FileSystemEventHandler):
    """Handler for scan processing folder events"""

    def __init__(self, scans_processed_folder: str, api_base_url: str):
        self.scans_processed_folder = scans_processed_folder
        self.api_base_url = api_base_url
        self.processed_folders: Set[str] = set()
        self.processing_folders: Set[str] = set()

    def on_created(self, event):
        """Called when a file or directory is created"""
        if event.is_directory:
            folder_name = Path(event.src_path).name

            # Skip common subdirectories that are not UUID folders
            skip_dirs = {'frames', 'output', 'transcode', 'project.files',
                         'depth_maps', 'model', 'point_cloud', 'thumbnails',
                         '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'}

            if folder_name in skip_dirs:
                logger.debug(
                    f"[SKIP] Skipping known subdirectory: {folder_name}"
                )
                return

            logger.info(f"[FOLDER] New directory detected: {folder_name}")

            # Check if it's a valid UUID folder
            if self._is_valid_uuid(folder_name):
                logger.info(
                    f"[TARGET] Valid UUID folder detected: {folder_name}"
                )
                self._process_scan_folder(event.src_path, folder_name)
            else:
                logger.info(
                    f"[WARNING] Invalid UUID folder (skipping): {folder_name}"
                )

    def _is_valid_uuid(self, folder_name: str) -> bool:
        """Check if folder name is a valid UUID"""
        import uuid
        try:
            uuid.UUID(folder_name)
            return True
        except ValueError:
            return False

    def _process_scan_folder(self, folder_path: str, component_id: str):
        """Process a scan folder"""
        if component_id in self.processing_folders:
            logger.info(f"[PROCESSING] Already processing: {component_id}")
            return

        self.processing_folders.add(component_id)

        try:
            logger.info(f"[PROCESSING] Starting processing: {component_id}")

            # Run the processing script
            cmd = [
                sys.executable,
                str(PROCESS_SCRIPT),
                "--single",
                folder_path,
                self.scans_processed_folder
            ]

            logger.info(f"[PROCESSING] Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                logger.info(f"[OK] Processing completed: {component_id}")
                logger.info(
                    f"[FOLDER] Moved to: {self.scans_processed_folder}"
                )
            else:
                logger.error(f"[ERROR] Processing failed: {component_id}")
                logger.error(f"   stdout: {result.stdout}")
                logger.error(f"   stderr: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error(f"[PROCESSING] Processing timeout: {component_id}")
        except Exception as e:
            logger.error(f"[ERROR] Processing error: {component_id} - {e}")
        finally:
            self.processing_folders.discard(component_id)


class ScanUploadHandler(FileSystemEventHandler):
    """Handler for scan upload folder events"""

    def __init__(self, credentials: Dict[str, str]):
        self.credentials = credentials
        self.uploaded_folders: Set[str] = set()
        self.uploading_folders: Set[str] = set()

    def on_created(self, event):
        """Called when a file or directory is created"""
        if event.is_directory:
            folder_name = Path(event.src_path).name
            # Skip common subdirectories that are not UUID folders
            skip_dirs = {'frames', 'output', 'transcode', 'project.files',
                         'depth_maps', 'model', 'point_cloud', 'thumbnails',
                         '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'}
            if folder_name in skip_dirs:
                logger.debug(
                    f"[SKIP] Skipping known subdirectory: {folder_name}"
                )
                return
            logger.info(
                f"[FOLDER] New processed directory detected: {folder_name}"
            )
            # Check if it's a valid UUID folder
            if self._is_valid_uuid(folder_name):
                logger.info(
                    "[TARGET] Valid processed UUID folder "
                    f"detected: {folder_name}"
                )
                self._upload_scan_folder(event.src_path, folder_name)
            else:
                logger.info(
                    f"[WARNING] Invalid UUID folder (skipping): {folder_name}"
                )

    def _is_valid_uuid(self, folder_name: str) -> bool:
        """Check if folder name is a valid UUID"""
        import uuid
        try:
            uuid.UUID(folder_name)
            return True
        except ValueError:
            return False

    def _upload_scan_folder(self, folder_path: str, component_id: str):
        """Upload a processed scan folder"""
        if component_id in self.uploading_folders:
            logger.info(f"[UPLOADING] Already uploading: {component_id}")
            return

        self.uploading_folders.add(component_id)

        try:
            logger.info(f"[START] Starting upload: {component_id}")

            # Run the upload script
            cmd = [
                sys.executable,
                str(UPLOAD_SCRIPT),
                folder_path,
                "--credentials", "csc_credentials.json"
            ]

            logger.info(f"[UPLOADING] Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode == 0:
                logger.info(f"[OK] Upload completed: {component_id}")
                self.uploaded_folders.add(component_id)
            else:
                logger.error(f"[ERROR] Upload failed: {component_id}")
                logger.error(f"   stdout: {result.stdout}")
                logger.error(f"   stderr: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error(f"[UPLOADING] Upload timeout: {component_id}")
        except Exception as e:
            logger.error(f"[ERROR] Upload error: {component_id} - {e}")
        finally:
            self.uploading_folders.discard(component_id)


class ScanDataWatchdog:
    """Main watchdog class"""

    def __init__(
            self,
            scans_to_process: str,
            scans_processed: str,
            credentials: Dict[str, str]
    ):
        self.scans_to_process = Path(scans_to_process)
        self.scans_processed = Path(scans_processed)
        self.credentials = credentials

        # Create observers
        self.observer = Observer()

        # Create handlers
        self.processing_handler = ScanProcessingHandler(
            str(scans_processed),
            credentials['server']
        )
        self.upload_handler = ScanUploadHandler(credentials)

    def start_watching(self):
        """Start watching both folders"""
        # Ensure directories exist
        self.scans_to_process.mkdir(parents=True, exist_ok=True)
        self.scans_processed.mkdir(parents=True, exist_ok=True)

        logger.info("[WATCHDOG] Starting scan data watchdog...")
        logger.info(
            f"[FOLDER] Watching for new scans: {self.scans_to_process}"
        )
        logger.info(
            f"[FOLDER] Watching for processed scans: {self.scans_processed}"
        )
        logger.info(f"[SERVER] API base URL: {self.credentials['server']}")

        # Start watching processing folder
        self.observer.schedule(
            self.processing_handler,
            str(self.scans_to_process),
            recursive=True
        )

        # Start watching upload folder
        self.observer.schedule(
            self.upload_handler,
            str(self.scans_processed),
            recursive=True
        )

        # Start the observer
        self.observer.start()

        try:
            logger.info("[OK] Watchdog started successfully!")
            logger.info(
                "[MONITORING] Monitoring folders... (Press Ctrl+C to stop)"
            )
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[WATCHDOG] Stopping watchdog...")
            self.stop_watching()

    def stop_watching(self):
        """Stop watching folders"""
        self.observer.stop()
        self.observer.join()
        logger.info("[OK] Watchdog stopped")

    def process_existing_folders(self):
        """Process any existing folders in the directories"""
        logger.info("[SEARCH] Checking for existing folders to process...")

        # Process existing folders in scans_to_process
        for item in self.scans_to_process.iterdir():
            if (item.is_dir() and
                    self.processing_handler._is_valid_uuid(item.name)):
                logger.info(
                    f"[FOLDER] Found existing scan folder: {item.name}"
                )
                self.processing_handler._process_scan_folder(
                    str(item),
                    item.name
                )

        # Upload existing folders in scans_processed
        for item in self.scans_processed.iterdir():
            if item.is_dir() and self.upload_handler._is_valid_uuid(item.name):
                logger.info(
                    f"[FOLDER] Found existing processed folder: {item.name}"
                )
                self.upload_handler._upload_scan_folder(str(item), item.name)


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Watchdog for automatic scan data processing and upload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scan_data_watchdog.py /path/to/scans_to_process /path/to/scans_processed # NOQA
  python scan_data_watchdog.py /path/to/scans_to_process /path/to/scans_processed --credentials /path/to/credentials.json # NOQA
        """
    )

    parser.add_argument('scans_to_process',
                        help='Folder to watch for new scan data')
    parser.add_argument('scans_processed',
                        help='Folder to watch for processed scan data')
    parser.add_argument('--credentials',
                        default=CREDENTIALS_FILE,
                        help=('Path to credentials JSON file '
                              f'(default: {CREDENTIALS_FILE})'))
    parser.add_argument('--process-existing', action='store_true',
                        help='Process existing folders on startup')

    args = parser.parse_args()

    # Check if required scripts exist
    if not PROCESS_SCRIPT.exists():
        logger.error(f"[ERROR] Processing script not found: {PROCESS_SCRIPT}")
        sys.exit(1)

    if not UPLOAD_SCRIPT.exists():
        logger.error(f"[ERROR] Upload script not found: {UPLOAD_SCRIPT}")
        sys.exit(1)

    # Load credentials
    credentials = load_credentials(args.credentials)

    # Create and start watchdog
    watchdog = ScanDataWatchdog(
        args.scans_to_process,
        args.scans_processed,
        credentials
    )

    # Process existing folders if requested
    if args.process_existing:
        watchdog.process_existing_folders()

    # Start watching
    watchdog.start_watching()


if __name__ == "__main__":
    print("CSC Scan Data Watchdog")
    print("=" * 50)

    try:
        main()
    except KeyboardInterrupt:
        print("\n[WATCHDOG] Watchdog stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Watchdog error: {e}")
        sys.exit(1)
