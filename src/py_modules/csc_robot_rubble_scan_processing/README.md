# Robot Rubble Scan Processing

Processes 3D scan data and uploads to CSC backend API.

## Setup

1. Install dependencies:
```bash
pip install numpy trimesh scikit-learn scipy requests
```

2. Create credentials file:
```bash
cp csc_credentials.json.example csc_credentials.json
# Edit with your API credentials
```

```json
{
  "server": "https://api.ddu.uber.space",
  "user": "your-username", 
  "pwd": "your-password"
}
```

## Usage

### Programmatic Interface

```python
# Process only
from process_robot_scan import process_scan_by_path
success = process_scan_by_path('/path/to/uuid-folder')

# Upload only  
from upload_robot_scan import upload_scan_by_path
credentials = load_credentials('csc_credentials.json')
success = upload_scan_by_path('/path/to/uuid-folder', credentials)

# Process and upload
from process_and_upload_scan import main
main('/path/to/uuid-folder')
```

### Command Line (Testing)

```bash
# Process
python process_robot_scan.py /path/to/uuid-folder

# Upload
python upload_robot_scan.py /path/to/uuid-folder [credentials_file]

# Process and upload
python process_and_upload_scan.py /path/to/uuid-folder [credentials_file]
```
