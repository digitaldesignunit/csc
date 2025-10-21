#!/usr/bin/env python3
"""
Process and upload robot scan data to CSC backend.
"""

import sys
import json
import argparse
from process_robot_scan import process_scan_by_path
from upload_robot_scan import upload_scan_by_path


def load_credentials(credentials_path: str = "csc_credentials.json"):
    """Load credentials from JSON file"""
    with open(credentials_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Process and upload robot scan data")
    parser.add_argument('scan_folder_path',
                        help='Path to UUID-named scan folder')
    parser.add_argument('--credentials', default="csc_credentials.json",
                        help='Credentials file path')
    args = parser.parse_args()

    # Load credentials
    credentials = load_credentials(args.credentials)

    # Process scan
    print(f"Processing scan: {args.scan_folder_path}")
    if not process_scan_by_path(args.scan_folder_path):
        print("Processing failed!")
        sys.exit(1)

    # Upload scan
    print("Uploading scan...")
    if not upload_scan_by_path(args.scan_folder_path, credentials):
        print("Upload failed!")
        sys.exit(1)

    print("Success!")


if __name__ == "__main__":
    main()
