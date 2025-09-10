# Robot Rubble Scan Processing System

This system automatically processes 3D scan data from robots and uploads it to the CSC backend API.

## Overview

The system consists of three main scripts:

1. **`process_robot_scan.py`** - Processes scan data and creates CSC components
2. **`upload_robot_scan.py`** - Uploads processed data to the backend API
3. **`scan_data_watchdog.py`** - Monitors folders and orchestrates the pipeline

## Workflow

```
scans_to_process/          scans_processed/          Backend API
     ↓                           ↓                      ↓
[New scan folder] → [Process & move] → [Upload data] → [CSC Database]
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create credentials file:
```bash
cp csc_credentials.json.example csc_credentials.json
# Edit csc_credentials.json with your API credentials
```

3. Ensure the backend API is running and accessible.

## Usage

### Manual Processing

Process a single scan folder:
```bash
python process_robot_scan.py --single /path/to/scan_folder /path/to/scans_processed
```

Process all scan folders in a directory:
```bash
python process_robot_scan.py /path/to/scans_to_process /path/to/scans_processed
```

### Manual Upload

Upload processed scan data:
```bash
python upload_robot_scan.py /path/to/scans_processed
```

With custom credentials file:
```bash
python upload_robot_scan.py /path/to/scans_processed --credentials /path/to/credentials.json
```

### Automatic Processing (Watchdog)

Start the watchdog to monitor folders automatically:
```bash
python scan_data_watchdog.py /path/to/scans_to_process /path/to/scans_processed
```

With custom credentials file:
```bash
python scan_data_watchdog.py /path/to/scans_to_process /path/to/scans_processed --credentials /path/to/credentials.json
```

Process existing folders on startup:
```bash
python scan_data_watchdog.py /path/to/scans_to_process /path/to/scans_processed --process-existing
```

## Folder Structure

### Input Scan Folder Structure
```
scans_to_process/
└── {uuid}/
    ├── metadata.json
    └── output/
        └── aligned_mesh.obj
```

### Processed Scan Folder Structure
```
scans_processed/
└── {uuid}/
    ├── metadata.json
    ├── output/
    │   └── aligned_mesh.obj
    └── transcode/
        ├── mesh.obj
        ├── mesh_reduced.obj (if needed)
        └── {uuid}.json
```

## Configuration

### Credentials File
Create a `csc_credentials.json` file with your API credentials:
```json
{
  "server": "https://api.ddu.uber.space",
  "user": "your-username",
  "pwd": "your-password"
}
```

**Security Note**: Keep this file secure and never commit it to version control. Use the `.gitignore` file to exclude it.

### Logging
- All scripts create log files: `scan_processing.log`, `scan_upload.log`, `scan_watchdog.log`
- Logs are also output to console

## Error Handling

- **Processing failures**: Failed scans remain in `scans_to_process` for manual inspection
- **Upload failures**: Failed uploads remain in `scans_processed` for retry
- **Timeout handling**: Long-running operations have timeouts (5 min processing, 2 min upload)
- **Retry logic**: Upload script includes HTTP retry strategy

## Monitoring

The watchdog provides real-time monitoring:
- [OK] Successful processing and upload
- [ERROR] Failed operations with error details
- [PROCESSING] Currently processing/uploading
- [FOLDER] New folders detected

## Troubleshooting

### Common Issues

1. **API Connection Failed**
   - Check if backend API is running
   - Verify API base URL is correct
   - Check network connectivity

2. **Processing Failed**
   - Check scan folder structure
   - Verify required files exist (metadata.json, aligned_mesh.obj)
   - Check log files for detailed error messages

3. **Upload Failed**
   - Check API authentication
   - Verify component JSON format
   - Check file permissions

### Log Files
- `scan_processing.log` - Processing script logs
- `scan_upload.log` - Upload script logs  
- `scan_watchdog.log` - Watchdog monitoring logs

## API Endpoints Used

- `POST /auth/token` - Authenticate and get JWT token
- `POST /components/add/` - Create component
- `POST /components/{id}/geometry/add_detailed` - Upload detailed geometry
- `POST /components/{id}/geometry/add_reduced` - Upload reduced geometry

## Development

To extend the system:

1. **Add new processing steps**: Modify `process_robot_scan.py`
2. **Add new upload endpoints**: Modify `upload_robot_scan.py`
3. **Add new monitoring logic**: Modify `scan_data_watchdog.py`

All scripts support command-line arguments and can be integrated into larger systems.
